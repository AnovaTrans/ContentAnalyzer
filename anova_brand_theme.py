"""
Anova Translation — Unified Streamlit Brand Theme
===================================================
Drop this file into any Streamlit app repo and call:
    from anova_brand_theme import apply_anova_theme, anova_header, anova_footer
"""

import streamlit as st
import base64, os

# ---------------------------------------------------------------------------
# Brand Palette
# ---------------------------------------------------------------------------
CHARCOAL = "#3A3A3A"
CORAL    = "#E85C4A"
TEAL     = "#4ECDC4"
AMBER    = "#F7931E"
WHITE    = "#FFFFFF"
LIGHT_GREY = "#F4F4F4"
MID_GREY   = "#9B9B9B"

# ---------------------------------------------------------------------------
# Logo (loaded from file next to this module)
# ---------------------------------------------------------------------------
def _logo_b64() -> str:
    logo_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ANOVA_PNG.png")
    if os.path.exists(logo_path):
        with open(logo_path, "rb") as f:
            return base64.b64encode(f.read()).decode()
    return ""

# ---------------------------------------------------------------------------
# CSS Theme
# ---------------------------------------------------------------------------
ANOVA_CSS = f"""
<style>
    /* ---- Import Google Fonts ---- */
    @import url('https://fonts.googleapis.com/css2?family=Montserrat:wght@500;600;700;900&family=Open+Sans:wght@300;400;600&display=swap');

    /* ---- Hide default Streamlit chrome ---- */
    #MainMenu {{visibility: hidden !important; display: none !important;}}
    header {{visibility: hidden !important; display: none !important;}}
    .stApp > header {{visibility: hidden !important; display: none !important;}}
    footer {{visibility: hidden !important; display: none !important;}}
    .stFooter {{visibility: hidden !important; display: none !important;}}
    .stAppToolbar {{visibility: hidden !important; display: none !important; height: 0px !important;}}
    [data-testid="stToolbar"] {{visibility: hidden !important; display: none !important; height: 0px !important;}}
    button[title="View fullscreen"] {{visibility: hidden !important; display: none !important;}}
    .viewerBadge_container__1QSob {{display: none !important;}}
    div[class*="viewerBadge"] {{display: none !important;}}
    .stDeployButton {{display: none !important;}}

    /* ---- Sidebar: always visible, hide collapse button ---- */
    [data-testid="collapsedControl"] {{display: none !important;}}
    [data-testid="stSidebarCollapsedControl"] {{display: none !important;}}
    button[kind="header"] {{display: none !important;}}
    section[data-testid="stSidebar"] {{
        min-width: 240px !important;
        max-width: 320px !important;
        transform: none !important;
        position: relative !important;
    }}
    section[data-testid="stSidebar"] > div {{
        width: 100% !important;
    }}

    /* ---- Global Typography ---- */
    html, body, [class*="css"] {{
        font-family: 'Open Sans', Calibri, Arial, sans-serif !important;
        color: {CHARCOAL} !important;
    }}

    /* ---- Headings ---- */
    h1, h2, h3 {{
        font-family: 'Montserrat', Calibri, Arial, sans-serif !important;
        color: {CHARCOAL} !important;
    }}
    h1 {{ font-weight: 700 !important; }}
    h2 {{ font-weight: 600 !important; }}
    h3 {{ font-weight: 500 !important; }}

    /* ---- Sidebar ---- */
    [data-testid="stSidebar"] {{
        background-color: {CHARCOAL} !important;
    }}
    [data-testid="stSidebar"] * {{
        color: {WHITE} !important;
    }}
    [data-testid="stSidebar"] .stSelectbox label,
    [data-testid="stSidebar"] .stTextInput label,
    [data-testid="stSidebar"] .stRadio label,
    [data-testid="stSidebar"] .stNumberInput label,
    [data-testid="stSidebar"] .stMultiSelect label {{
        color: {LIGHT_GREY} !important;
        font-family: 'Open Sans', Calibri, sans-serif !important;
        font-size: 0.85rem !important;
    }}
    [data-testid="stSidebar"] hr {{
        border-color: rgba(78, 205, 196, 0.3) !important;
    }}

    /* ---- Primary Button ---- */
    .stButton > button[kind="primary"],
    .stButton > button {{
        background-color: {CORAL} !important;
        color: {WHITE} !important;
        border: none !important;
        border-radius: 6px !important;
        font-family: 'Montserrat', sans-serif !important;
        font-weight: 600 !important;
        transition: all 0.2s ease !important;
    }}
    .stButton > button:hover {{
        background-color: #D04A38 !important;
        box-shadow: 0 2px 8px rgba(232, 92, 74, 0.3) !important;
    }}

    /* ---- Download Button ---- */
    .stDownloadButton > button {{
        background-color: {TEAL} !important;
        color: {WHITE} !important;
        border: none !important;
        border-radius: 6px !important;
        font-weight: 600 !important;
    }}
    .stDownloadButton > button:hover {{
        background-color: #3DBDB5 !important;
    }}

    /* ---- Tabs ---- */
    .stTabs [data-baseweb="tab-list"] {{
        gap: 8px;
        border-bottom: 2px solid {LIGHT_GREY};
    }}
    .stTabs [data-baseweb="tab"] {{
        font-family: 'Montserrat', sans-serif !important;
        font-weight: 600 !important;
        color: {MID_GREY} !important;
        border-radius: 6px 6px 0 0 !important;
    }}
    .stTabs [aria-selected="true"] {{
        color: {CORAL} !important;
        border-bottom: 3px solid {CORAL} !important;
    }}

    /* ---- Metrics ---- */
    [data-testid="stMetricValue"] {{
        font-family: 'Montserrat', sans-serif !important;
        font-weight: 700 !important;
        color: {CHARCOAL} !important;
    }}

    /* ---- File uploader ---- */
    [data-testid="stFileUploader"] {{
        border: 2px dashed {TEAL} !important;
        border-radius: 10px !important;
        padding: 1rem !important;
    }}

    /* ---- Expander ---- */
    .streamlit-expanderHeader {{
        font-family: 'Montserrat', sans-serif !important;
        font-weight: 600 !important;
        color: {CHARCOAL} !important;
    }}

    /* ---- Top padding reduction ---- */
    .block-container {{
        padding-top: 1rem !important;
    }}

    /* ---- Anova custom classes ---- */
    .anova-header {{
        display: flex;
        align-items: center;
        gap: 16px;
        padding: 0.8rem 0;
        border-bottom: 3px solid {TEAL};
        margin-bottom: 1.5rem;
    }}
    .anova-header img {{
        height: 52px;
    }}
    .anova-header .app-title {{
        font-family: 'Montserrat', sans-serif;
        font-weight: 700;
        font-size: 1.6rem;
        color: {CHARCOAL};
    }}
    .anova-header .app-subtitle {{
        font-family: 'Open Sans', sans-serif;
        font-weight: 300;
        font-size: 0.9rem;
        color: {MID_GREY};
    }}
    .anova-footer {{
        text-align: center;
        padding: 1.5rem 0 0.5rem 0;
        border-top: 2px solid {TEAL};
        margin-top: 3rem;
        font-family: 'Open Sans', sans-serif;
        font-size: 0.78rem;
        color: {MID_GREY};
    }}
    .anova-footer a {{
        color: {CORAL};
        text-decoration: none;
    }}
    .anova-divider {{
        border: none;
        height: 2px;
        background: {TEAL};
        margin: 1.5rem 0;
    }}
</style>
"""


def apply_anova_theme():
    """Inject the unified Anova CSS into the Streamlit page. Call once at app start."""
    st.markdown(ANOVA_CSS, unsafe_allow_html=True)


def anova_header(app_title: str, app_subtitle: str = ""):
    """Render the branded Anova header with logo, title, and optional subtitle."""
    b64 = _logo_b64()
    if b64:
        logo_html = f'<img src="data:image/png;base64,{b64}" alt="Anova Translation">'
    else:
        logo_html = '<span style="font-weight:900;font-size:1.4rem;color:#E85C4A;">ANOVA</span>'

    subtitle_html = f'<div class="app-subtitle">{app_subtitle}</div>' if app_subtitle else ""
    st.markdown(f"""
        <div class="anova-header">
            {logo_html}
            <div>
                <div class="app-title">{app_title}</div>
                {subtitle_html}
            </div>
        </div>
    """, unsafe_allow_html=True)


def anova_footer():
    """Render the branded Anova footer with copyright."""
    import datetime
    year = datetime.datetime.now().year
    st.markdown(f"""
        <div class="anova-footer">
            &copy; {year} <strong>Anova Translation</strong> &nbsp;|&nbsp;
            <a href="https://www.anova.bg" target="_blank">www.anova.bg</a> &nbsp;|&nbsp;
            info@anova.bg &nbsp;|&nbsp; +359 896 225 332<br>
            152 Shesti Septemvri Blvd., floor 3, Office 306, Plovdiv 4000, Bulgaria
        </div>
    """, unsafe_allow_html=True)


def anova_sidebar_logo():
    """Show a small Anova logo at the top of the sidebar."""
    b64 = _logo_b64()
    if b64:
        st.sidebar.markdown(f"""
            <div style="text-align:center; padding: 0.5rem 0 1rem 0;">
                <img src="data:image/png;base64,{b64}" style="height:40px;" alt="Anova">
            </div>
        """, unsafe_allow_html=True)
