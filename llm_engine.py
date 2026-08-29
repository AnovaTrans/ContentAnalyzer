"""
LLM Engine — Anthropic Claude (Current-Gen Models)
====================================================
- Updated to Claude Sonnet 4.6 / Opus 4.6 / Haiku 4.5
- max_tokens increased from 8192 to 16000-32000
- Enhanced system prompts for evaluation-winning output
- Improved multi-batch synthesis with deduplication
- Anti-hallucination guards using actual structure_metrics
- Prompt caching for cost optimization
"""

import json
import time
import re
from typing import List, Dict, Callable, Optional
from anthropic import Anthropic
from models import DocumentAnalysis
from config_data import MASTER_TAXONOMY


def _response_text(response) -> str:
    """Concatenate text blocks of a Messages response, skipping thinking blocks.
    Current models (Sonnet 5, Opus 4.7+) return a ThinkingBlock first, so
    response.content[0].text raises 'ThinkingBlock has no attribute text'."""
    parts = []
    for block in getattr(response, "content", None) or []:
        if getattr(block, "type", "") == "text":
            parts.append(getattr(block, "text", "") or "")
    return "".join(parts).strip()


class LLMEngine:
    """Anthropic Claude API ile doküman analizi yapan motor."""

    # Current-gen fallbacks (the UI-selected model is tried first — see __init__).
    CLAUDE_MODELS = [
        "claude-sonnet-4-6",   # Primary — best price/performance, 1M context
        "claude-opus-4-6",     # Premium fallback
        "claude-haiku-4-5",    # Budget fallback (bare id — no date suffix)
    ]

    # ── Detail level tiers ──────────────────────────────────
    # NOTE: Final DOCX report adds ~400 words of headers/labels/formatting
    # on top of JSON content, so JSON word budget = target - 400.
    # Token budget ≈ JSON word budget / 0.75 (words per token) + JSON overhead (~30%).
    DETAIL_LEVELS = {
        "comprehensive": {
            "label": "Comprehensive",
            "max_words": 2000,
            "max_tokens": 8000,       # ~1600 JSON words → ~2000 in final report
            "retry_tokens": 6000,
            "chunk_tokens": 4000,
            "min_terms": 20,
            "word_instruction": (
                "HARD WORD LIMIT: The final report must be ~2000 words. Your JSON content "
                "must not exceed ~1600 words of text (the report template adds ~400 words). "
                "Be thorough but concise — fill every field with specific content. "
                "Include at least 20 categorized terms. No filler, no repetition."
            ),
        },
        "standard": {
            "label": "Standard",
            "max_words": 1500,
            "max_tokens": 6000,       # ~1100 JSON words → ~1500 in final report
            "retry_tokens": 4000,
            "chunk_tokens": 3000,
            "min_terms": 15,
            "word_instruction": (
                "HARD WORD LIMIT: The final report must be ~1500 words. Your JSON content "
                "must not exceed ~1100 words of text (the report template adds ~400 words). "
                "Be focused and concise — cover all sections but keep descriptions brief. "
                "Include at least 15 categorized terms. No filler."
            ),
        },
        "basic": {
            "label": "Basic",
            "max_words": 1000,
            "max_tokens": 4000,       # ~600 JSON words → ~1000 in final report
            "retry_tokens": 3000,
            "chunk_tokens": 2500,
            "min_terms": 10,
            "word_instruction": (
                "HARD WORD LIMIT: The final report must be ~1000 words. Your JSON content "
                "must not exceed ~600 words of text (the report template adds ~400 words). "
                "Be EXTREMELY concise — one-sentence descriptions, compact term lists, "
                "no explanations. Include at least 10 categorized terms. Every word must "
                "carry unique value. DO NOT EXCEED THIS LIMIT."
            ),
        },
    }

    def __init__(self, api_key: str, model: Optional[str] = None):
        self.api_key = api_key
        self.client = Anthropic(api_key=self.api_key)
        # UI-selected model is tried first; CLAUDE_MODELS stay as fallbacks.
        if model:
            self.models = [model] + [m for m in self.CLAUDE_MODELS if m != model]
        else:
            self.models = list(self.CLAUDE_MODELS)
        print(f"LLM Engine initialized with Anthropic Claude ({self.models[0]})")

    def analyze_document(
        self,
        text_chunks: List[str],
        metadata: Dict,
        progress_callback: Optional[Callable[[int, int, str], None]] = None,
        detail_level: str = "comprehensive",
    ) -> DocumentAnalysis:
        """
        Ana giriş noktası. Küçük dosyalar için tek geçiş,
        büyük dosyalar için çoklu batch analizi yapar.
        """
        self._detail_config = self.DETAIL_LEVELS.get(detail_level, self.DETAIL_LEVELS["comprehensive"])
        total_chunks = len(text_chunks)
        structure_info = metadata.get('structure_metrics', {})

        if total_chunks == 1:
            if progress_callback:
                progress_callback(1, 1, "Analyzing document...")
            return self._analyze_single_pass(text_chunks[0], metadata, structure_info)
        else:
            return self._analyze_multi_batch(text_chunks, metadata, structure_info, progress_callback)

    def _analyze_single_pass(self, text: str, metadata: Dict, structure: Dict) -> DocumentAnalysis:
        """Tek parça doküman analizi."""
        system_prompt = self._get_system_prompt(structure)
        user_prompt = self._get_user_prompt_full(text, metadata, structure)
        return self._execute_llm_call(system_prompt, user_prompt, metadata)

    def _analyze_multi_batch(
        self,
        chunks: List[str],
        metadata: Dict,
        structure: Dict,
        callback: Optional[Callable]
    ) -> DocumentAnalysis:
        """Çoklu batch analizi (büyük dokümanlar için)."""
        total = len(chunks)
        batch_insights = []

        print(f"Starting Batch Analysis for {total} chunks...")

        for i, chunk in enumerate(chunks):
            current_step = i + 1
            status_msg = f"Scanning Batch {current_step} of {total}..."

            if callback:
                callback(current_step, total + 1, status_msg)  # +1 for synthesis step

            # Retry mantığı
            max_retries = 3
            insight = None

            for attempt in range(max_retries):
                try:
                    insight = self._analyze_single_chunk_light(chunk, current_step, total)
                    if insight:
                        break
                except Exception as e:
                    print(f"Batch {current_step} failed (Attempt {attempt+1}/{max_retries}): {e}")
                    time.sleep(2 * (attempt + 1))

            if insight:
                batch_insights.append(insight)
            else:
                print(f"SKIPPING Batch {current_step} after {max_retries} failed attempts.")

            time.sleep(0.2)  # Rate limit koruması

        if callback:
            callback(total + 1, total + 1, "Synthesizing final report...")

        return self._synthesize_batches(batch_insights, metadata, structure)

    def _analyze_single_chunk_light(self, text: str, index: int, total: int) -> Dict:
        """Tek chunk'tan temel verileri çıkar — enhanced with more categories."""
        prompt = f"""You are analyzing PART {index} of {total} of a large document.

TASK: Extract structured data from this content. Be thorough and extract ALL relevant items.

CONTENT:
{text[:120000]}

CRITICAL INSTRUCTIONS:
1. Return ONLY valid JSON
2. NO markdown code blocks (no ```)
3. NO explanations or text outside the JSON
4. Start your response with {{ and end with }}
5. Extract as many items as possible — be comprehensive

OUTPUT FORMAT:
{{
    "domains": ["domain1 > subcategory", "domain2 > subcategory"],
    "terms": {{
        "technical": ["term1", "term2"],
        "legal": ["term3"],
        "industry": ["term4", "term5"],
        "general": ["term6"]
    }},
    "risks": [
        {{"name": "risk name", "category": "Terminology|Formatting|Legal|Technical|Cultural", "description": "brief description", "evidence": "quote from text"}}
    ],
    "measurements": ["8.821,8 kWp", "1.234,56 EUR"],
    "entities": {{
        "companies": ["company names found"],
        "products": ["product/brand names"],
        "people": ["person names"],
        "places": ["locations"]
    }},
    "abbreviations": ["kWp", "GmbH", "EUR"],
    "date_patterns": ["DD.MM.YYYY"],
    "number_patterns": ["German: 1.234,56"]
}}
"""
        try:
            chunk_tokens = getattr(self, '_detail_config', self.DETAIL_LEVELS["comprehensive"]).get("chunk_tokens", 4000)
            response = self._call_claude(prompt, max_tokens=chunk_tokens)
            if not response or not response.strip():
                raise ValueError("Empty response from Claude")

            cleaned = self._clean_json_response(response)
            if not cleaned:
                print(f"Batch {index}: Failed to extract JSON")
                raise ValueError("Could not extract valid JSON")

            return json.loads(cleaned)
        except json.JSONDecodeError as e:
            print(f"JSON Parse Error in batch {index}: {e}")
            raise e

    def _synthesize_batches(self, insights: List[Dict], metadata: Dict, structure: Dict) -> DocumentAnalysis:
        """Tüm batch sonuçlarını birleştirip final rapor oluştur — enhanced synthesis."""
        if not insights:
            print("WARNING: No insights collected. Using fallback.")
            return self._analyze_single_pass(
                "Document content was too large or complex to process.",
                metadata,
                structure
            )

        # ── Aggregate and deduplicate across batches ──
        all_domains = []
        all_terms = {}
        all_risks = []
        all_measurements = []
        all_entities = {"companies": [], "products": [], "people": [], "places": []}
        all_abbreviations = []
        all_date_patterns = []
        all_number_patterns = []

        for item in insights:
            # Domains
            all_domains.extend(item.get('domains', []))

            # Terms (may be dict or list)
            terms = item.get('terms', {})
            if isinstance(terms, dict):
                for cat, t_list in terms.items():
                    if cat not in all_terms:
                        all_terms[cat] = []
                    if isinstance(t_list, list):
                        all_terms[cat].extend(t_list)
            elif isinstance(terms, list):
                all_terms.setdefault('general', []).extend(terms)

            # Risks
            risks = item.get('risks', [])
            if isinstance(risks, list):
                all_risks.extend(risks)

            # Measurements
            all_measurements.extend(item.get('measurements', []))

            # Entities
            entities = item.get('entities', {})
            if isinstance(entities, dict):
                for key in all_entities:
                    all_entities[key].extend(entities.get(key, []))

            # Patterns
            all_abbreviations.extend(item.get('abbreviations', []))
            all_date_patterns.extend(item.get('date_patterns', []))
            all_number_patterns.extend(item.get('number_patterns', []))

        # Deduplicate
        def dedup(items):
            seen = set()
            result = []
            for item in items:
                s = json.dumps(item, sort_keys=True) if isinstance(item, dict) else str(item)
                if s.lower() not in seen:
                    seen.add(s.lower())
                    result.append(item)
            return result

        unique_domains = dedup(all_domains)[:15]
        unique_risks = dedup(all_risks)[:20]
        unique_measurements = dedup(all_measurements)[:30]
        deduped_terms = {cat: dedup(terms)[:25] for cat, terms in all_terms.items()}
        deduped_entities = {k: dedup(v)[:15] for k, v in all_entities.items()}
        unique_abbreviations = dedup(all_abbreviations)[:20]

        # ── Build rich synthesis prompt ──
        synthesis_context = f"""
AGGREGATED FINDINGS FROM {len(insights)} DOCUMENT CHUNKS:

DOMAINS IDENTIFIED: {", ".join(str(d) for d in unique_domains)}

TERMINOLOGY (categorized):
{json.dumps(deduped_terms, indent=2, ensure_ascii=False)}

NAMED ENTITIES:
{json.dumps(deduped_entities, indent=2, ensure_ascii=False)}

RISKS IDENTIFIED:
{json.dumps(unique_risks, indent=2, ensure_ascii=False)}

MEASUREMENTS & NUMBERS FOUND:
{", ".join(str(m) for m in unique_measurements)}

ABBREVIATIONS: {", ".join(str(a) for a in unique_abbreviations)}
DATE PATTERNS: {", ".join(str(d) for d in dedup(all_date_patterns))}
NUMBER PATTERNS: {", ".join(str(n) for n in dedup(all_number_patterns))}
"""

        system_prompt = self._get_system_prompt(structure)
        schema_json = json.dumps(DocumentAnalysis.model_json_schema(), indent=2)

        cfg = getattr(self, '_detail_config', self.DETAIL_LEVELS["comprehensive"])

        user_prompt = f"""Generate a FINAL ANALYSIS REPORT from the aggregated batch findings.

DOCUMENT: {metadata.get('filename')}
DOCUMENT TYPE: {metadata.get('doc_type', 'unknown')}
DETECTED LANGUAGE: {metadata.get('detected_lang', 'unknown')}

ACTUAL DOCUMENT STRUCTURE (verified counts — do NOT hallucinate different numbers):
- Tables: {structure.get('table_count', 0)}
- Images: {structure.get('image_count', 0)}
- Hyperlinks: {structure.get('hyperlink_count', 0)}
- Pages: {structure.get('page_count', 'Unknown')}
- OCR Needed: {structure.get('ocr_needed', False)}

{synthesis_context}

WORD LIMIT: {cfg['word_instruction']}

CRITICAL REQUIREMENTS:
1. Return ONLY valid JSON matching the schema below
2. NO markdown code blocks
3. Start with {{ and end with }}
4. Include AT LEAST {cfg['min_terms']} categorized terminology terms
5. Include specific measurement conversion rules based on actual numbers found
6. Include real evidence quotes for each risk
7. Report ONLY the actual image/table counts from STRUCTURE above — do NOT invent additional ones
8. RESPECT THE WORD LIMIT — maximize coverage per word, be concise and dense

OUTPUT JSON SCHEMA:
{schema_json}
"""

        return self._execute_llm_call(system_prompt, user_prompt, metadata)

    def _call_claude(
        self,
        user_msg: str,
        system_prompt: str = "You are a helpful assistant.",
        max_tokens: int = 16000,
        use_cache: bool = False,
    ) -> str:
        """Claude API'ye istek gönder (model fallback ile)."""

        print("Attempting Claude models...")
        last_error = None

        for model_id in self.models:
            for attempt in range(3):
                try:
                    print(f"  Trying: {model_id} (attempt {attempt+1})")

                    # Build system message with optional caching
                    if use_cache:
                        sys_msg = [
                            {
                                "type": "text",
                                "text": system_prompt,
                                "cache_control": {"type": "ephemeral"},
                            }
                        ]
                    else:
                        sys_msg = system_prompt

                    response = self.client.messages.create(
                        model=model_id,
                        max_tokens=max_tokens,
                        system=sys_msg,
                        messages=[{"role": "user", "content": user_msg}],
                    )

                    content = _response_text(response)

                    if not content or not content.strip():
                        print(f"  Warning: {model_id} returned empty response")
                        break  # Try next model

                    # Log token usage
                    if hasattr(response, 'usage'):
                        usage = response.usage
                        print(f"  Success: {model_id} ({len(content)} chars, "
                              f"in={getattr(usage, 'input_tokens', '?')}, "
                              f"out={getattr(usage, 'output_tokens', '?')})")

                    return content

                except Exception as e:
                    last_error = e
                    error_str = str(e).lower()
                    if "rate" in error_str or "overloaded" in error_str:
                        print(f"  Rate limited: {model_id} - waiting...")
                        time.sleep(5 * (attempt + 1))
                        continue
                    elif "not_found" in error_str or "invalid" in error_str:
                        print(f"  Model not available: {model_id}")
                        break  # Skip to next model
                    else:
                        print(f"  Failed: {model_id} - {str(e)}")
                        time.sleep(2 * (attempt + 1))
                        continue

        raise RuntimeError(f"All Claude models failed. Last error: {last_error}")

    def _clean_json_response(self, response: str) -> str:
        """LLM yanıtından temiz JSON çıkar."""
        if not response:
            return ""

        cleaned = response.strip()

        # Markdown code block'ları temizle
        if "```" in cleaned:
            pattern = r'```(?:json)?\s*([\s\S]*?)\s*```'
            matches = re.findall(pattern, cleaned)
            if matches:
                for match in matches:
                    match = match.strip()
                    if match.startswith('{'):
                        cleaned = match
                        break
            else:
                lines = [l for l in cleaned.split('\n') if not l.strip().startswith('```')]
                cleaned = '\n'.join(lines)

        cleaned = cleaned.strip()

        # JSON başlangıcını bul
        if not cleaned.startswith('{'):
            start = cleaned.find('{')
            if start == -1:
                return ""
            cleaned = cleaned[start:]

        # Doğru kapanış brace'i bul
        if not cleaned.endswith('}'):
            brace_count = 0
            end_pos = -1
            for i, char in enumerate(cleaned):
                if char == '{':
                    brace_count += 1
                elif char == '}':
                    brace_count -= 1
                    if brace_count == 0:
                        end_pos = i
                        break
            if end_pos != -1:
                cleaned = cleaned[:end_pos + 1]

        return cleaned.strip()

    def _execute_llm_call(self, sys_prompt: str, user_prompt: str, metadata: Dict) -> DocumentAnalysis:
        """LLM çağrısı yap ve DocumentAnalysis objesi döndür — with retry for incomplete output."""
        raw_json = None
        cleaned_json = None

        cfg = getattr(self, '_detail_config', self.DETAIL_LEVELS["comprehensive"])
        max_attempts = 2
        for attempt in range(max_attempts):
            try:
                # Use detail-level-aware max_tokens
                raw_json = self._call_claude(
                    user_prompt,
                    sys_prompt,
                    max_tokens=cfg["max_tokens"] if attempt == 0 else cfg["retry_tokens"],
                    use_cache=True,
                )

                print(f"DEBUG: Response length: {len(raw_json) if raw_json else 0}")

                if not raw_json or not raw_json.strip():
                    raise ValueError("Empty response from Claude")

                cleaned_json = self._clean_json_response(raw_json)

                print(f"DEBUG: Cleaned JSON length: {len(cleaned_json) if cleaned_json else 0}")

                if not cleaned_json:
                    print(f"Failed to extract JSON. Raw: {raw_json[:1000]}")
                    raise ValueError("Could not extract valid JSON")

                data = json.loads(cleaned_json)
                data['document_names'] = [metadata['filename']]
                data['original_file_types'] = [metadata['doc_type']]
                data['analysis_date'] = metadata.get('analysis_date', 'Today')

                # Validate critical fields exist
                model = DocumentAnalysis(**data)

                # Post-validation: ensure terminology count is reasonable
                term_count = model.difficulty_complexity.drivers.terminology_count
                actual_terms = model.terminology_and_resources.categorized_terms
                total_actual = sum(len(v) for v in actual_terms.values()) if actual_terms else 0
                if total_actual < 5 and term_count > 5:
                    print(f"WARNING: terminology_count={term_count} but only {total_actual} actual terms listed")

                return model

            except json.JSONDecodeError as e:
                print(f"JSON Parse Error (attempt {attempt+1}): {e}")
                if attempt < max_attempts - 1:
                    print("Retrying with fresh call...")
                    time.sleep(2)
                    continue
                print(f"Raw: {raw_json[:2000] if raw_json else 'None'}")
                raise e
            except Exception as e:
                print(f"Analysis failed (attempt {attempt+1}): {e}")
                if attempt < max_attempts - 1:
                    print("Retrying...")
                    time.sleep(2)
                    continue
                raise e

    def _get_system_prompt(self, structure: Dict = None) -> str:
        """Enhanced system prompt with taxonomy, anti-hallucination, and quality requirements."""
        taxonomy_str = json.dumps(MASTER_TAXONOMY, indent=2)

        structure_warning = ""
        if structure:
            structure_warning = f"""
*** ANTI-HALLUCINATION: ACTUAL DOCUMENT STRUCTURE ***
The document extraction system has detected:
- Tables: {structure.get('table_count', 0)}
- Images: {structure.get('image_count', 0)}
- Hyperlinks: {structure.get('hyperlink_count', 0)}
- Pages: {structure.get('page_count', 'Unknown')}

You MUST report these EXACT counts in your analysis. Do NOT claim the document
contains more images, tables, or elements than listed above. If image_count is 0,
state that no images were detected. Accuracy here is critical.
"""

        return f"""You are an Enterprise Localization Architect specialized in comprehensive document analysis
for professional translation project planning.

Your analysis must be THOROUGH, SPECIFIC, and GROUNDED in the actual document content.
Every claim must be supported by evidence from the text.

*** CONSISTENCY & DETERMINISM (reduce run-to-run drift) ***
Classify strictly from measurable content, never impression — the SAME document must
yield the SAME analysis on repeated runs. Specifically:
- DOMAIN BREAKDOWN: rank domains by the share of actual string/content VOLUME they
  occupy; the #1 domain MUST be the one covering the largest portion of the text.
  Round every percentage to the nearest 5%. Do not reshuffle the ranking based on
  secondary or incidental details.
- FORMATTING IMPACT and DIFFICULTY: derive the score from the concrete structure and
  content, not a general impression; identical structure and content ⇒ identical score.
- COUNTRIES/LOCALES: report only those explicitly present in the text; never add
  plausible-but-unseen ones.
- PRICE FACTOR: compute it the same way every time from difficulty and content type.

{structure_warning}

*** TAXONOMY RULES (STRICT) ***
You MUST use domain categories from this taxonomy. Use the format "Category > Subcategory":
{taxonomy_str}

*** QUALITY REQUIREMENTS ***
1. HIGH-LEVEL DESCRIPTION: Write 3-5 sentences summarizing the document purpose, audience, and key content areas
2. CORPORATE CONTEXT: Identify the primary company, parent organization, and brand consistency requirements
3. DOMAIN BREAKDOWN: Use taxonomy categories with percentages that sum to 100%
4. TERMINOLOGY: Extract and categorize AT LEAST 20 terms from the actual document
5. MEASUREMENT RULES: Identify actual numbers, dates, and units in the document and specify conversion rules
6. RISKS: For each risk, provide a name, category, description, evidence quote from the text, and mitigation
7. WORKFLOW: Specify concrete pre-processing, translation, QA, and post-processing steps
8. PM NOTES: Write an executive summary, special considerations, and questions for the client
9. RESOURCE QUALIFICATIONS: Specify seniority, years of experience, education, domain expertise, and tools
10. LOCALIZATION STRATEGY: Cultural adaptation notes, geographic handling, and tone/style guidance

*** STRICT WORD LIMIT — THIS IS A HARD CONSTRAINT ***
{getattr(self, '_detail_config', self.DETAIL_LEVELS['comprehensive'])['word_instruction']}
STRICTLY RESPECT THIS LIMIT. If you exceed it, your output FAILS the task.
- Use the shortest possible descriptions that still convey the meaning
- One sentence per field where possible, never three when one will do
- Compact term lists: "term1, term2, term3" not verbose explanations per term
- Risk evidence: one short quote per risk, not paragraphs
- Workflow: terse action items, not detailed process descriptions
- Do NOT pad with filler or repeat information across sections

*** OUTPUT RULES ***
1. Always output valid JSON only — no markdown, no explanations
2. Start with {{ and end with }}
3. Every field must be filled with meaningful, specific content — no empty strings or generic placeholders
4. terminology_count must match the actual number of terms you list in categorized_terms
"""

    def _get_user_prompt_full(self, text: str, metadata: Dict, structure: Dict) -> str:
        """Tam analiz için user prompt oluştur — enhanced with structure info."""
        schema_json = json.dumps(DocumentAnalysis.model_json_schema(), indent=2)

        return f"""Analyze this document and generate a COMPREHENSIVE analysis report.
Fill EVERY field with specific, detailed content based on the actual document.

DOCUMENT CONTENT:
{text[:200000]}

FILE METADATA:
- Filename: {metadata.get('filename', 'Unknown')}
- Document Type: {metadata.get('doc_type', 'Unknown')}
- Detected Language: {metadata.get('detected_lang', 'Unknown')}
- Analysis Date: {metadata.get('analysis_date', 'Today')}

ACTUAL DOCUMENT STRUCTURE (use these EXACT counts — do NOT invent different numbers):
- Tables detected: {structure.get('table_count', 0)}
- Images detected: {structure.get('image_count', 0)}
- Hyperlinks detected: {structure.get('hyperlink_count', 0)}
- Page count: {structure.get('page_count', 'Unknown')}
- OCR needed: {structure.get('ocr_needed', False)}

WORD LIMIT: {getattr(self, '_detail_config', self.DETAIL_LEVELS['comprehensive'])['word_instruction']}

CRITICAL REQUIREMENTS:
1. Return ONLY valid JSON matching the schema below
2. NO markdown code blocks (no ```)
3. Start with {{ and end with }}
4. Fill EVERY field — no empty strings, no placeholders
5. Extract AT LEAST {getattr(self, '_detail_config', self.DETAIL_LEVELS['comprehensive'])['min_terms']} categorized terminology terms from the document
6. Identify ALL named entities (companies, products, people, places)
7. Provide SPECIFIC measurement conversion rules based on actual numbers in the document
8. For each risk, include an actual quote from the document as evidence
9. Report the EXACT image/table counts from STRUCTURE above
10. RESPECT THE WORD LIMIT — maximize coverage per word, be concise and dense

OUTPUT JSON SCHEMA:
{schema_json}
"""
