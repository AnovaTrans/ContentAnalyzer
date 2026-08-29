"""
LLM Engine - Anthropic Only Version
====================================
- OpenAI desteği kaldırıldı
- Sadece Claude modelleri kullanılıyor
- Tüm teknik düzeltmeler uygulandı
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
        "claude-sonnet-4-6",   # Primary — best price/performance
        "claude-opus-4-6",     # Premium fallback
        "claude-haiku-4-5",    # Budget fallback
    ]

    def __init__(self, api_key: str, model: Optional[str] = None):
        """
        Args:
            api_key: Anthropic API anahtarı
            model: UI-selected model (tried first; CLAUDE_MODELS stay as fallbacks)
        """
        self.api_key = api_key
        self.client = Anthropic(api_key=self.api_key)
        if model:
            self.models = [model] + [m for m in self.CLAUDE_MODELS if m != model]
        else:
            self.models = list(self.CLAUDE_MODELS)
        print(f"LLM Engine initialized with Anthropic Claude ({self.models[0]})")

    def analyze_document(
        self, 
        text_chunks: List[str], 
        metadata: Dict, 
        progress_callback: Optional[Callable[[int, int, str], None]] = None
    ) -> DocumentAnalysis:
        """
        Ana giriş noktası. Küçük dosyalar için tek geçiş,
        büyük dosyalar için çoklu batch analizi yapar.
        """
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
        system_prompt = self._get_system_prompt()
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
                callback(current_step, total, status_msg)
            
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
            callback(total, total, "Synthesizing final report...")
            
        return self._synthesize_batches(batch_insights, metadata, structure)

    def _analyze_single_chunk_light(self, text: str, index: int, total: int) -> Dict:
        """Tek chunk'tan temel verileri çıkar."""
        prompt = f"""You are analyzing PART {index} of {total} of a large document.

TASK: Extract structured data from this content.

CONTENT:
{text[:80000]}

CRITICAL INSTRUCTIONS:
1. Return ONLY valid JSON
2. NO markdown code blocks (no ```)
3. NO explanations or text outside the JSON
4. Start your response with {{ and end with }}

OUTPUT FORMAT:
{{
    "domains": ["domain1", "domain2"],
    "terms": ["term1", "term2", "term3"],
    "risks": ["risk1", "risk2"],
    "measurements": ["measurement1", "measurement2"]
}}
"""
        try:
            response = self._call_claude(prompt)
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
        """Tüm batch sonuçlarını birleştirip final rapor oluştur."""
        if not insights:
            print("WARNING: No insights collected. Using fallback.")
            return self._analyze_single_pass(
                "Document content was too large or complex to process.", 
                metadata, 
                structure
            )
        
        # Verileri topla
        all_domains = []
        all_terms = []
        all_risks = []
        all_measurements = []
        
        for item in insights:
            all_domains.extend(item.get('domains', []))
            all_terms.extend(item.get('terms', []))
            all_risks.extend(item.get('risks', []))
            all_measurements.extend(item.get('measurements', []))
        
        # Tekrarları kaldır (dict'leri de handle et)
        def safe_stringify(items):
            result = []
            seen = set()
            for item in items:
                s = json.dumps(item, sort_keys=True) if isinstance(item, dict) else str(item)
                if s not in seen:
                    seen.add(s)
                    result.append(str(item) if isinstance(item, dict) else s)
            return result
        
        unique_domains = safe_stringify(all_domains)
        unique_terms = safe_stringify(all_terms)[:50]
        unique_risks = safe_stringify(all_risks)[:20]
        unique_measurements = safe_stringify(all_measurements)[:20]
            
        synthesis_context = f"""
AGGREGATED FINDINGS FROM {len(insights)} BATCHES:
- DOMAINS: {", ".join(unique_domains)}
- TERMINOLOGY: {", ".join(unique_terms)}
- RISKS: {", ".join(unique_risks)}
- MEASUREMENTS: {", ".join(unique_measurements)}
"""

        system_prompt = self._get_system_prompt()
        schema_json = json.dumps(DocumentAnalysis.model_json_schema(), indent=2)
        
        user_prompt = f"""Generate a FINAL ANALYSIS REPORT.

DOCUMENT: {metadata.get('filename')}
{synthesis_context}

CRITICAL: Return ONLY valid JSON matching the schema. NO markdown, NO explanations.

OUTPUT JSON SCHEMA:
{schema_json}
"""

        return self._execute_llm_call(system_prompt, user_prompt, metadata)

    def _call_claude(self, user_msg: str, system_prompt: str = "You are a helpful assistant.") -> str:
        """Claude API'ye istek gönder (model fallback ile)."""
        
        print("Attempting Claude models...")
        last_error = None
        
        for model_id in self.models:
            try:
                print(f"  Trying: {model_id}")

                response = self.client.messages.create(
                    model=model_id,
                    max_tokens=8192,
                    system=system_prompt,
                    messages=[{"role": "user", "content": user_msg}],
                )

                content = _response_text(response)
                
                if not content or not content.strip():
                    print(f"  Warning: {model_id} returned empty response")
                    continue
                
                print(f"  Success: {model_id} ({len(content)} chars)")
                return content
                
            except Exception as e:
                last_error = e
                print(f"  Failed: {model_id} - {str(e)}")
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
        """LLM çağrısı yap ve DocumentAnalysis objesi döndür."""
        raw_json = None
        cleaned_json = None
        
        try:
            raw_json = self._call_claude(user_prompt, sys_prompt)
            
            print(f"DEBUG: Response length: {len(raw_json) if raw_json else 0}")
            
            if not raw_json or not raw_json.strip():
                raise ValueError("Empty response from Claude")
            
            cleaned_json = self._clean_json_response(raw_json)
            
            print(f"DEBUG: Cleaned JSON length: {len(cleaned_json) if cleaned_json else 0}")
            
            if not cleaned_json:
                print(f"Failed to extract JSON. Raw: {raw_json[:1000]}")
                raise ValueError("Could not extract valid JSON")
            
            print(f"DEBUG: JSON starts with: {cleaned_json[:150]}...")
                 
            data = json.loads(cleaned_json)
            data['document_names'] = [metadata['filename']]
            data['original_file_types'] = [metadata['doc_type']]
            data['analysis_date'] = metadata.get('analysis_date', 'Today')
            
            return DocumentAnalysis(**data)
            
        except json.JSONDecodeError as e:
            print(f"JSON Parse Error: {e}")
            print(f"Raw: {raw_json[:1500] if raw_json else 'None'}")
            raise e
        except Exception as e:
            print(f"Analysis failed: {e}")
            raise e

    def _get_system_prompt(self) -> str:
        """Sistem prompt'u oluştur."""
        taxonomy_str = json.dumps(MASTER_TAXONOMY, indent=2)
        return f"""You are an Enterprise Localization Architect specialized in document analysis.

Your task is to analyze documents and provide structured JSON output for translation project planning.

*** TAXONOMY RULES (STRICT) ***
You MUST use domain categories from this taxonomy:
{taxonomy_str}

*** OUTPUT RULES ***
1. Always output valid JSON only
2. Never include markdown formatting
3. Never include explanatory text outside the JSON
4. Start with {{ and end with }}
"""

    def _get_user_prompt_full(self, text: str, metadata: Dict, structure: Dict) -> str:
        """Tam analiz için user prompt oluştur."""
        schema_json = json.dumps(DocumentAnalysis.model_json_schema(), indent=2)
        
        return f"""Analyze this document and generate a comprehensive analysis report.

DOCUMENT CONTENT:
{text[:80000]}

METADATA: {json.dumps(metadata, indent=2)}
STRUCTURE: {json.dumps(structure, indent=2)}

CRITICAL INSTRUCTIONS:
1. Return ONLY valid JSON matching the schema below
2. NO markdown code blocks (no ```)
3. NO explanations before or after the JSON
4. Start your response with {{ and end with }}

OUTPUT JSON SCHEMA:
{schema_json}
"""
