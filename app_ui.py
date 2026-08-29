"""
Anova Content Analyzer
======================================================
Enterprise document analysis for translation projects.
"""

import streamlit as st
import os
import datetime
from pathlib import Path
import traceback
import json

# Backend Mantığı
from extractors import FileExtractor, chunk_text
from llm_engine import LLMEngine
from reporters import ReportGenerator
from config_data import calculate_blended_price_factor
from models import FinancialEstimates

# Anova Brand Theme
from anova_brand_theme import apply_anova_theme, anova_header, anova_footer, anova_sidebar_logo

# 1. SAYFA AYARLARI
st.set_page_config(page_title="Anova Content Analyzer", page_icon="📄", layout="wide", initial_sidebar_state="expanded")

# 2. ANOVA BRAND TEMASI
apply_anova_theme()

def save_uploaded_file(uploaded_file):
    try:
        temp_dir = Path("temp_uploads")
        temp_dir.mkdir(exist_ok=True)
        file_path = temp_dir / uploaded_file.name
        with open(file_path, "wb") as f:
            f.write(uploaded_file.getbuffer())
        return str(file_path)
    except Exception as e:
        st.error(f"File Save Error: {e}")
        return None

def display_dashboard(model, out_dir, original_filename):
    # ... (Mevcut dashboard kodlarınız aynı kalıyor) ...
    st.markdown("---")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("💰 Price Factor", f"{model.financial_metrics.suggested_price_factor}x")
    c2.metric("📊 Difficulty", f"{model.difficulty_complexity.overall_difficulty_level}/10")
    c3.metric("📈 Density", model.difficulty_complexity.drivers.technical_density_score)
    c4.metric("🏷️ Domains", len(model.domain_breakdown))

    st.markdown("### 🏢 Executive Summary")
    st.info(model.high_level_description)
    
    c1, c2 = st.columns([2, 1])
    with c1:
        st.markdown("### 📊 Domain Breakdown")
        chart_data = {item.domain: item.percentage for item in model.domain_breakdown}
        st.bar_chart(chart_data)
    with c2:
        st.markdown("### ⚠️ Critical Risks")
        for risk in model.risks_and_mitigations:
            st.warning(f"**{risk.category}:** {risk.name}")

    st.markdown("---")
    st.markdown("### 📋 Resource Qualifications")
    res = model.recommended_resources
    st.table({
        "Profile": [res.headline_profile],
        "Experience": [f"{res.min_years_experience} Years"],
        "Education": [res.education_requirement],
        "Tools": [", ".join(res.tool_recommendations)]
    })
    
    st.subheader("📥 Downloads")
    import glob
    docx_files = sorted(glob.glob(str(out_dir / "*_analysis_report.docx")), reverse=True)
    json_files = sorted(glob.glob(str(out_dir / "*_analysis.json")), reverse=True)
    col1, col2 = st.columns(2)
    if docx_files:
        docx_path = Path(docx_files[0])
        with open(docx_path, "rb") as f:
            col1.download_button("📄 Download Report (DOCX)", f, file_name=docx_path.name)
    if json_files:
        json_path = Path(json_files[0])
        with open(json_path, "rb") as f:
            col2.download_button("📋 Download Data (JSON)", f, file_name=json_path.name)

def run_analysis_pipeline(file_path: str, api_key: str, detail_level: str = "comprehensive"):
    # ... (Mevcut pipeline kodlarınız aynı kalıyor) ...
    status_text = st.empty()
    main_progress_bar = st.progress(0)

    def update_progress(percent, message):
        """Real-time progress callback."""
        percent = max(0, min(100, percent))
        main_progress_bar.progress(percent / 100.0)
        status_text.text(f"⏳ {message} ({percent}%)")

    def progress_callback(current_batch, total_batches, message):
        # Map batch progress into the 20-80% range (extraction=0-15%, batches=20-80%, reports=85-100%)
        batch_percent = 20 + int((current_batch / total_batches) * 60)
        batch_percent = min(batch_percent, 80)
        main_progress_bar.progress(batch_percent / 100.0)
        status_text.text(f"⏳ {message} ({batch_percent}%)")

    try:
        update_progress(2, "Initializing Claude Engine...")
        llm = LLMEngine(api_key)

        update_progress(5, "Extracting text and structure...")
        extractor = FileExtractor(file_path)
        extract_result = extractor.extract()
        
        if extract_result.get('error'):
            st.error(f"❌ Extraction Error: {extract_result['error']}")
            return None

        full_text = extract_result['full_text']
        structure_metrics = extract_result.get('structure_metrics', {})
        
        if not full_text:
            st.error("❌ No text could be extracted from the document.")
            return None
        
        chunks = chunk_text(full_text, max_chars=200000)  # Leverage Sonnet 4.6's 1M context
        extract_result['analysis_date'] = datetime.date.today().isoformat()

        update_progress(15, f"Document split into {len(chunks)} chunk(s) — starting analysis...")

        try:
            analysis_model = llm.analyze_document(
                chunks, extract_result,
                progress_callback=progress_callback,
                detail_level=detail_level,
            )
        except RuntimeError as e:
            st.error(f"❌ Claude API Error: {str(e)}")
            return None

        update_progress(82, "Calculating commercial estimates...")
        domain_breakdown_dicts = [item.model_dump() for item in analysis_model.domain_breakdown]
        diff = analysis_model.difficulty_complexity.overall_difficulty_level
        img_count = structure_metrics.get('image_count', 0)
        tbl_count = structure_metrics.get('table_count', 0)
        has_dtp = img_count > 0 or tbl_count > 5
        
        factor, weighted_base = calculate_blended_price_factor(domain_breakdown_dicts, diff, has_dtp)
        
        cost_breakdown = []
        if img_count > 0: cost_breakdown.append(f"OCR Processing (+10%): {img_count} images")
        if tbl_count > 3: cost_breakdown.append(f"Complex Formatting (+5%): {tbl_count} tables")
        if has_dtp: cost_breakdown.append("DTP Surcharge (+15%)")

        word_count = len(full_text.split())
        term_count = analysis_model.difficulty_complexity.drivers.terminology_count
        calc_density = (term_count / word_count) * 100 if word_count > 0 else 0
        analysis_model.difficulty_complexity.drivers.technical_density_score = f"{calc_density:.1f}%"

        analysis_model.financial_metrics = FinancialEstimates(
            suggested_price_factor=round(factor, 2),
            explanation=f"Base ({weighted_base:.2f}) x Difficulty ({diff}/10)",
            component_impact_breakdown=cost_breakdown,
            weighted_base_coefficient=weighted_base,
            difficulty_multiplier=1.2 if diff >= 8 else 1.0,
            dtp_surcharge=has_dtp
        )
        
        update_progress(90, "Generating reports...")
        base_name = os.path.basename(file_path)
        file_safe_name = os.path.splitext(base_name)[0].replace('.', '_').replace(' ', '_')
        output_dir = Path("analysis_output").resolve() / file_safe_name
        output_dir.mkdir(parents=True, exist_ok=True)
        
        reporter = ReportGenerator(analysis_model, str(output_dir))
        reporter.generate_json()
        reporter.generate_docx()
        
        update_progress(100, "Complete!")
        status_text.empty()
        st.success(f"✅ Analysis complete! ({detail_level.capitalize()} level)")
        return analysis_model, output_dir, base_name

    except Exception as e:
        st.error(f"❌ An error occurred: {str(e)}")
        st.text(traceback.format_exc())
        return None

# ---------------------------------------------------------
# SIDEBAR (API Key Girişini Kaldırdık - Otomatik Alıyoruz)
# ---------------------------------------------------------
with st.sidebar:
    anova_sidebar_logo()
    st.title("⚙️ Configuration")
    
    # API Key artık çevreden alınıyor (Secrets)
    # Eğer localde test ediyorsanız burayı açabilirsiniz, ama canlıda kapalı kalsın.
    # api_key = st.text_input("API Key", type="password") 
    api_key = os.getenv("ANTHROPIC_API_KEY") or st.secrets.get("ANTHROPIC_API_KEY", "")
    
    if not api_key:
        st.error("⚠️ Server API Key missing!")

    st.markdown("---")
    st.markdown("### 📏 Detail Level")
    detail_level_choice = st.radio(
        "Analysis detail level",
        [
            "Comprehensive (~2000 words)",
            "Standard (~1500 words)",
            "Basic (~1000 words)",
        ],
        index=0,
        help="All levels cover the same analysis sections. Higher levels include more terms and deeper analysis.",
    )
    if "Comprehensive" in detail_level_choice:
        selected_detail_level = "comprehensive"
    elif "Standard" in detail_level_choice:
        selected_detail_level = "standard"
    else:
        selected_detail_level = "basic"

    st.markdown("---")
    st.markdown("### 🤖 AI Models")
    st.markdown("**Primary:** Claude Sonnet 4.6 (1M context)")
    st.markdown("**Fallback:** Opus 4.6 → Haiku 4.5")

# ---------------------------------------------------------
# MAIN CONTENT
# ---------------------------------------------------------
anova_header("Content Analyzer", "Enterprise document analysis for translation projects")

uploaded_file = st.file_uploader("Choose a file", type=['docx', 'pdf', 'xlsx', 'mqxliff', 'xliff', 'xml', 'txt', 'html', 'json'])

if uploaded_file:
    st.markdown(f"**Selected file:** `{uploaded_file.name}`")
    
    if st.button("🔍 Analyze Document", type="primary", use_container_width=True):
        if not api_key:
            st.error("⚠️ API Key not found on server settings.")
        else:
            file_path = save_uploaded_file(uploaded_file)
            if file_path:
                result = run_analysis_pipeline(file_path, api_key, detail_level=selected_detail_level)
                if result:
                    display_dashboard(*result)
else:
    st.markdown("""
    <div style="text-align: center; padding: 3rem; color: #9B9B9B;">
        <h3>Upload a document to get started</h3>
    </div>
    """, unsafe_allow_html=True)

anova_footer()
