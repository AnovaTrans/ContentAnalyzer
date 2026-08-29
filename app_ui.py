"""
Enterprise Document Analyzer - Anthropic Only Version
======================================================
- OpenAI seçeneği kaldırıldı
- Sadece Claude modelleri kullanılıyor
"""

import streamlit as st
import os
import datetime
from pathlib import Path
import traceback

# Import backend logic
from extractors import FileExtractor, chunk_text
from llm_engine import LLMEngine
from model_utils import list_model_ids, default_model, FALLBACK_MODELS
from reporters import ReportGenerator
from config_data import calculate_blended_price_factor
from models import FinancialEstimates

st.set_page_config(page_title="AICONTEXT Document Analyzer", page_icon="🚀", layout="wide", initial_sidebar_state="expanded")

# --- GÜNCELLENMİŞ GİZLEME KODU (Fullscreen ve Footer Yok Edici) ---
hide_streamlit_style = """
<style>
/* Üst menü ve standart footer gizleme.
   NOTE: 'header' is NOT hidden — in current Streamlit the sidebar
   collapse/expand toggle lives there; hiding it makes the sidebar
   (API key + model selector) unreachable. */
#MainMenu {visibility: hidden; display: none;}
footer {visibility: hidden; display: none;}

/* KRİTİK GÜNCELLEME: Alt çubuk ve Fullscreen butonunu yok etme */
/* İsimleri değişse bile 'viewerBadge' içeren tüm elementleri gizler */
div[class*="viewerBadge"] {display: none !important;}
.viewerBadge_container {display: none !important;}

/* Eğer Fullscreen butonu hala görünüyorsa, toolbar'ı hedef alalım */
[data-testid="stToolbar"] {visibility: hidden; display: none !important;}
[data-testid="stDecoration"] {visibility: hidden; display: none !important;}
[data-testid="stStatusWidget"] {visibility: hidden; display: none !important;}

/* Alt kısımda oluşabilecek boşluğu silme */
footer {display: none !important;}
</style>
"""
st.markdown(hide_streamlit_style, unsafe_allow_html=True)

# Styling
st.markdown("""
<style>
    .reportview-container { background: #f0f2f6 }
    .metric-card { background-color: white; padding: 15px; border-radius: 10px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); text-align: center; }
    .main-header { font-size: 2.5rem; font-weight: bold; color: #1976D2; text-align: center; margin-bottom: 1rem; }
    .success-box { background-color: #E8F5E9; padding: 1rem; border-radius: 10px; border-left: 4px solid #2E7D32; }
</style>
""", unsafe_allow_html=True)


def save_uploaded_file(uploaded_file):
    """Yüklenen dosyayı geçici klasöre kaydet."""
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
    """Analiz sonuçlarını dashboard olarak göster."""
    st.markdown("---")
    
    # Metrics Row
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("💰 Price Factor", f"{model.financial_metrics.suggested_price_factor}x")
    c2.metric("📊 Difficulty", f"{model.difficulty_complexity.overall_difficulty_level}/10")
    c3.metric("📈 Density", model.difficulty_complexity.drivers.technical_density_score)
    c4.metric("🏷️ Domains", len(model.domain_breakdown))

    # Executive Summary
    st.markdown("### 🏢 Executive Summary")
    st.info(model.high_level_description)
    
    # Two Column Layout
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
    
    # Resource Qualifications Table
    st.markdown("### 📋 Resource Qualifications")
    res = model.recommended_resources
    st.table({
        "Profile": [res.headline_profile],
        "Experience": [f"{res.min_years_experience} Years"],
        "Education": [res.education_requirement],
        "Tools": [", ".join(res.tool_recommendations)]
    })
    
    # Download Buttons - Find files with timestamp pattern
    st.subheader("📥 Downloads")
    
    import glob
    
    # Find the most recent files matching the pattern
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


def run_analysis_pipeline(file_path: str, api_key: str, model: str = None):
    """Ana analiz pipeline'ı."""
    
    # Progress UI
    status_text = st.empty()
    main_progress_bar = st.progress(0)
    
    def progress_callback(current_batch, total_batches, message):
        percent = int((current_batch / total_batches) * 100)
        percent = min(percent, 100)
        main_progress_bar.progress(percent)
        status_text.text(f"⏳ {message} ({percent}%)")

    try:
        # Initialize Engine
        status_text.text("🔧 Initializing Claude Engine...")
        llm = LLMEngine(api_key, model=model)
        
        # Extract Content
        status_text.text("📄 Extracting Text & Structure...")
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
        
        # Chunk text
        chunks = chunk_text(full_text, max_chars=80000)
        extract_result['analysis_date'] = datetime.date.today().isoformat()
        
        st.info(f"📊 Document split into {len(chunks)} chunk(s) for analysis")
        
        # Analyze
        try:
            analysis_model = llm.analyze_document(
                chunks, 
                extract_result, 
                progress_callback=progress_callback
            )
        except RuntimeError as e:
            st.error(f"❌ Claude API Error: {str(e)}")
            st.info("💡 Please check your API key and try again.")
            return None

        # Calculate Financials
        status_text.text("💰 Calculating Commercial Estimates...")
        domain_breakdown_dicts = [item.model_dump() for item in analysis_model.domain_breakdown]
        diff = analysis_model.difficulty_complexity.overall_difficulty_level
        
        img_count = structure_metrics.get('image_count', 0)
        tbl_count = structure_metrics.get('table_count', 0)
        has_dtp = img_count > 0 or tbl_count > 5
        
        factor, weighted_base = calculate_blended_price_factor(
            domain_breakdown_dicts, diff, has_dtp
        )
        
        # Cost breakdown
        cost_breakdown = []
        if img_count > 0:
            factor += 0.10
            cost_breakdown.append(f"OCR Processing (+10%): {img_count} images")
        if tbl_count > 3:
            factor += 0.05
            cost_breakdown.append(f"Complex Formatting (+5%): {tbl_count} tables")
        if has_dtp:
            cost_breakdown.append("DTP Surcharge (+15%)")

        # Calculate density
        word_count = len(full_text.split())
        term_count = analysis_model.difficulty_complexity.drivers.terminology_count
        calc_density = (term_count / word_count) * 100 if word_count > 0 else 0
        analysis_model.difficulty_complexity.drivers.technical_density_score = f"{calc_density:.1f}%"

        explanation = f"Base ({weighted_base:.2f}) x Difficulty ({diff}/10)"
        
        analysis_model.financial_metrics = FinancialEstimates(
            suggested_price_factor=round(factor, 2),
            explanation=explanation,
            component_impact_breakdown=cost_breakdown,
            weighted_base_coefficient=weighted_base,
            difficulty_multiplier=1.2 if diff >= 8 else 1.0,
            dtp_surcharge=has_dtp
        )
        
        # Generate Reports
        status_text.text("📝 Generating Reports...")
        base_name = os.path.basename(file_path)
        file_safe_name = os.path.splitext(base_name)[0].replace('.', '_').replace(' ', '_')
        output_dir = Path("analysis_output").resolve() / file_safe_name
        output_dir.mkdir(parents=True, exist_ok=True)
        
        reporter = ReportGenerator(analysis_model, str(output_dir))
        reporter.generate_json()
        reporter.generate_docx()
        
        # Done
        main_progress_bar.progress(100)
        status_text.empty()
        st.success("✅ Analysis Complete!")
        
        return analysis_model, output_dir, base_name

    except Exception as e:
        st.error(f"❌ An error occurred: {str(e)}")
        st.text(traceback.format_exc())
        return None


# ============================================================================
# SIDEBAR
# ============================================================================
with st.sidebar:
    st.image("https://cdn-icons-png.flaticon.com/512/2083/2083213.png", width=50)
    st.title("⚙️ Configuration")
    
    # API Key Input
    st.markdown("### 🔑 Anthropic API Key")
    default_key = os.getenv("ANTHROPIC_API_KEY", "")
    api_key = st.text_input(
        "Enter your API key",
        value=default_key,
        type="password",
        help="Get your API key from console.anthropic.com"
    )
    
    # Model — live list from the account (fetched on load, refreshable).
    st.markdown("---")
    st.markdown("### 🤖 Model")
    selected_model = None
    if api_key:
        if st.button("🔄 Refresh model list") or "model_ids" not in st.session_state:
            st.session_state.model_ids = list_model_ids(api_key)
        ids = st.session_state.get("model_ids") or FALLBACK_MODELS
        if not st.session_state.get("model_ids"):
            st.caption("Live model list unavailable — showing current defaults.")
        dflt = default_model(ids)
        selected_model = st.selectbox(
            "Model", ids,
            index=ids.index(dflt) if dflt in ids else 0,
            help="Fetched live from your account. Falls back to Sonnet 4.6 / Opus 4.6 / Haiku 4.5 on error.",
        )
    else:
        st.caption("Enter the API key above to choose a model.")

    st.markdown("---")
    st.info("📌 AICONTEXT - Anthropic Edition")


# ============================================================================
# MAIN CONTENT
# ============================================================================
st.markdown('<p class="main-header">🚀 AICONTEXT Document Analyzer</p>', unsafe_allow_html=True)
st.markdown("Upload a document for comprehensive translation project analysis.")

# File Uploader
uploaded_file = st.file_uploader(
    "Choose a file",
    type=['docx', 'pdf', 'xlsx', 'mqxliff', 'xliff', 'xml', 'txt', 'html', 'json'],
    help="Supported formats: Word, PDF, Excel, XLIFF, XML, TXT, HTML, JSON"
)

# Analyze Button
if uploaded_file:
    st.markdown(f"**Selected file:** `{uploaded_file.name}`")
    
    if st.button("🔍 Analyze Document", type="primary", use_container_width=True):
        if not api_key:
            st.error("⚠️ Please enter your Anthropic API key in the sidebar.")
        else:
            file_path = save_uploaded_file(uploaded_file)
            if file_path:
                result = run_analysis_pipeline(file_path, api_key, model=selected_model)
                if result:
                    display_dashboard(*result)
else:
    # Empty state
    st.markdown("""
    <div style="text-align: center; padding: 3rem; color: #666;">
        <h3>👆 Upload a document to get started</h3>
        <p>The analyzer will extract content, identify domains, assess complexity, and generate a comprehensive translation project report.</p>
    </div>
    """, unsafe_allow_html=True)
