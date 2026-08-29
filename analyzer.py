import os
import datetime
import argparse
from dotenv import load_dotenv
from extractors import FileExtractor, chunk_text
from llm_engine import LLMEngine
from reporters import ReportGenerator
from config_data import calculate_blended_price_factor
from models import FinancialEstimates

# Load env vars
load_dotenv()

def run_document_analysis(
    file_paths: list, 
    provider: str, 
    api_key: str, 
    output_folder: str = "analysis_output"
):
    print(f"--- Starting Analysis using {provider.upper()} ---")
    
    try:
        llm = LLMEngine(provider, api_key)
    except Exception as e:
        print(f"Failed to init LLM: {e}")
        return

    for f_path in file_paths:
        if not os.path.exists(f_path):
            print(f"File not found: {f_path}")
            continue

        print(f"\nProcessing: {f_path}")
        
        # 1. Extract
        extractor = FileExtractor(f_path)
        extract_result = extractor.extract()
        
        if extract_result.get('error'):
            print(f"Skipping {f_path} due to error: {extract_result['error']}")
            continue

        full_text = extract_result['full_text']
        structure_metrics = extract_result.get('structure_metrics', {})
        
        if not full_text:
            print(f"No text extracted from {f_path}")
            continue

        chunks = chunk_text(full_text)
        extract_result['analysis_date'] = datetime.date.today().isoformat()
        
        # 3. LLM Analysis
        try:
            analysis_model = llm.analyze_document(chunks, extract_result)
            
            # --- ADVANCED FINANCIAL LOGIC ---
            
            # 1. Domain & Base Factor
            domain_breakdown_dicts = [item.model_dump() for item in analysis_model.domain_breakdown]
            diff = analysis_model.difficulty_complexity.overall_difficulty_level
            
            # DTP Risk Check
            img_count = structure_metrics.get('image_count', 0)
            tbl_count = structure_metrics.get('table_count', 0)
            has_dtp = img_count > 0 or tbl_count > 5
            
            factor, weighted_base = calculate_blended_price_factor(
                domain_breakdown_dicts, diff, has_dtp
            )
            
            # 2. Component Cost Add-ons
            cost_breakdown = []
            if img_count > 0:
                factor += 0.10
                cost_breakdown.append(f"OCR Processing (+10%): {img_count} images detected")
            
            if tbl_count > 3:
                factor += 0.05
                cost_breakdown.append(f"Complex Formatting (+5%): {tbl_count} tables detected")
            
            if has_dtp:
                cost_breakdown.append("DTP Surcharge (+15%): Layout work required")
                
            # 3. Density Calculation
            word_count = len(full_text.split())
            term_count = analysis_model.difficulty_complexity.drivers.terminology_count
            calc_density = (term_count / word_count) * 100 if word_count > 0 else 0
            analysis_model.difficulty_complexity.drivers.technical_density_score = f"{calc_density:.1f}% ({term_count} terms / {word_count} words)"

            # 4. Finalize Financials
            explanation = f"Base ({weighted_base:.2f}) x Diff ({diff}/10)"
            
            analysis_model.financial_metrics = FinancialEstimates(
                suggested_price_factor=round(factor, 2),
                explanation=explanation,
                component_impact_breakdown=cost_breakdown,
                weighted_base_coefficient=weighted_base,
                difficulty_multiplier=1.2 if diff >= 8 else 1.0,
                dtp_surcharge=has_dtp
            )
            
            # Runtime overrides
            if hasattr(analysis_model, 'analysis_date'):
                analysis_model.analysis_date = datetime.date.today().isoformat()
            
            # 4. Report
            file_safe_name = os.path.basename(f_path).replace('.', '_')
            target_dir = os.path.join(output_folder, file_safe_name)
            
            reporter = ReportGenerator(analysis_model, target_dir)
            reporter.generate_json()
            reporter.generate_docx()
            
        except Exception as e:
            print(f"Analysis failed for {f_path}: {e}")
            import traceback
            traceback.print_exc()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AI Document Analyzer")
    parser.add_argument("files", nargs='+', help="List of files to analyze")
    parser.add_argument("--provider", choices=['openai', 'claude'], default='openai', help="LLM Provider")
    parser.add_argument("--key", help="API Key (optional, defaults to env var)")
    
    args = parser.parse_args()
    
    api_key = args.key
    if not api_key:
        if args.provider == 'openai':
            api_key = os.getenv("OPENAI_API_KEY")
        elif args.provider == 'claude':
            api_key = os.getenv("ANTHROPIC_API_KEY")
            
    if not api_key:
        print(f"Error: No API key provided for {args.provider}. Set env var or use --key")
        exit(1)

    run_document_analysis(args.files, args.provider, api_key)