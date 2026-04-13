"""
THIWASCO Frontend Styles
Centralized styling for the application
"""

def load_css():
    """Load professional CSS styling"""
    return """
    <style>
    :root {
        --navy-950: #0d2b52;
        --navy-900: #123661;
        --slate-700: #41536b;
        --slate-500: #7a8798;
        --surface: #ffffff;
        --canvas: #eef3f8;
        --critical: #cd2b2b;
        --critical-soft: #fff2f1;
        --moderate: #f17a0a;
        --moderate-soft: #fff6ec;
        --success: #2e7d32;
        --success-soft: #edf7ef;
        --shadow: 0 8px 24px rgba(13, 43, 82, 0.08);
    }

    html, body, [class*="css"] {
        font-family: "Aptos", "Segoe UI", "Trebuchet MS", sans-serif;
    }
    
    /* AGGRESSIVE GLOBAL TEXT COLOR FIXES - Maximum specificity */
    html body p, html body span, html body div, html body h1, html body h2, html body h3, html body h4, html body h5, html body h6, html body li,
    body p, body span, body div, body h1, body h2, body h3, body h4, body h5, body h6, body li,
    [data-testid="stAppViewContainer"] p, [data-testid="stAppViewContainer"] span, [data-testid="stAppViewContainer"] div,
    [data-testid="stAppViewContainer"] h1, [data-testid="stAppViewContainer"] h2, [data-testid="stAppViewContainer"] h3,
    [data-testid="stAppViewContainer"] h4, [data-testid="stAppViewContainer"] h5, [data-testid="stAppViewContainer"] h6,
    [data-testid="stAppViewContainer"] li {
        color: #1f2937 !important;
        opacity: 1 !important;
    }
    
    /* Specific overrides for our custom classes with maximum specificity */
    html body .login-subtitle, html body .login-info-text, html body .login-footer,
    html body .metric-title, html body .topbar-time, html body .breadcrumb-separator,
    html body .page-heading p, html body .section-subtitle,
    body .login-subtitle, body .login-info-text, body .login-footer,
    body .metric-title, body .topbar-time, body .breadcrumb-separator,
    body .page-heading p, body .section-subtitle {
        color: #475569 !important;
        opacity: 1 !important;
    }
    
    /* Sidebar text visibility */
    [data-testid="stSidebar"] p, [data-testid="stSidebar"] span, [data-testid="stSidebar"] div,
    [data-testid="stSidebar"] h1, [data-testid="stSidebar"] h2, [data-testid="stSidebar"] h3,
    [data-testid="stSidebar"] h4, [data-testid="stSidebar"] h5, [data-testid="stSidebar"] h6,
    [data-testid="stSidebar"] li, [data-testid="stSidebar"] button {
        color: white !important;
        opacity: 1 !important;
    }
    
    /* Ensure data tables remain visible */
    [data-testid*="stTable"], [data-testid*="stDataFrame"], [class*="dataframe"] {
        color: #1f2937 !important;
        opacity: 1 !important;
    }
    
    [data-testid*="stTable"] *, [data-testid*="stDataFrame"] *, [class*="dataframe"] * {
        color: #1f2937 !important;
        opacity: 1 !important;
    }

    [data-testid="stAppViewContainer"] {
        background: var(--canvas);
    }

    [data-testid="stHeader"] {
        background: transparent;
    }

    .block-container {
        padding-top: 1.5rem;
        padding-bottom: 2rem;
        max-width: 1400px;
    }

    /* Sidebar styling */
    [data-testid="stSidebar"] {
        background: linear-gradient(180deg, var(--navy-950) 0%, var(--navy-900) 100%);
        color: white;
        display: block !important;
        visibility: visible !important;
    }

    [data-testid="stSidebar"] * {
        color: white !important;
    }
    
    /* Ensure sidebar is visible after login */
    .stSidebar {
        display: block !important;
        visibility: visible !important;
    }
    
    /* Force sidebar visibility with higher specificity */
    div[data-testid="stSidebar"] {
        display: block !important;
        visibility: visible !important;
        width: 300px !important;
        min-width: 300px !important;
    }
    
    /* Hide sidebar only on login page */
    .stApp[data-testid="stApp"] .stSidebar {
        display: block !important;
        visibility: visible !important;
    }
    
    /* Override login CSS - show sidebar after login with maximum specificity */
    html body div[data-testid="stAppViewContainer"] div[data-testid="stSidebar"],
    body div[data-testid="stAppViewContainer"] div[data-testid="stSidebar"],
    div[data-testid="stSidebar"] {
        display: block !important;
        visibility: visible !important;
        width: 300px !important;
        min-width: 300px !important;
    }
    
    /* TARGETED TEXT VISIBILITY FIX - Exclude charts */
    html body p, html body span, html body div, html body h1, html body h2, html body h3, html body h4, html body h5, html body h6, html body li,
    body p, body span, body div, body h1, body h2, body h3, body h4, body h5, body h6, body li,
    [data-testid="stAppViewContainer"] p, [data-testid="stAppViewContainer"] span, [data-testid="stAppViewContainer"] div,
    [data-testid="stAppViewContainer"] h1, [data-testid="stAppViewContainer"] h2, [data-testid="stAppViewContainer"] h3,
    [data-testid="stAppViewContainer"] h4, [data-testid="stAppViewContainer"] h5, [data-testid="stAppViewContainer"] h6,
    [data-testid="stAppViewContainer"] li {
        color: #1f2937 !important;
        opacity: 1 !important;
    }
    
    /* Preserve specific colors for important elements */
    html body [data-testid="stSidebar"] *, body [data-testid="stSidebar"] *, 
    [data-testid="stAppViewContainer"] [data-testid="stSidebar"] * {
        color: white !important;
        opacity: 1 !important;
    }
    
    html body .login-title, body .login-title, 
    [data-testid="stAppViewContainer"] .login-title {
        color: #0d2b52 !important;
        opacity: 1 !important;
    }
    
    html body .login-subtitle, body .login-subtitle,
    [data-testid="stAppViewContainer"] .login-subtitle {
        color: #475569 !important;
        opacity: 1 !important;
    }
    
    html body .metric-title, body .metric-title,
    [data-testid="stAppViewContainer"] .metric-title {
        color: #475569 !important;
        opacity: 1 !important;
    }
    
    html body .section-subtitle, body .section-subtitle,
    [data-testid="stAppViewContainer"] .section-subtitle {
        color: #475569 !important;
        opacity: 1 !important;
    }
    
    html body .topbar-time, body .topbar-time,
    [data-testid="stAppViewContainer"] .topbar-time {
        color: #475569 !important;
        opacity: 1 !important;
    }
    
    html body .breadcrumb-separator, body .breadcrumb-separator,
    [data-testid="stAppViewContainer"] .breadcrumb-separator {
        color: #475569 !important;
        opacity: 1 !important;
    }
    
    html body .page-heading p, body .page-heading p,
    [data-testid="stAppViewContainer"] .page-heading p {
        color: #475569 !important;
        opacity: 1 !important;
    }
    
    html body .metric-foot span, body .metric-foot span,
    [data-testid="stAppViewContainer"] .metric-foot span {
        color: #475569 !important;
        opacity: 1 !important;
    }

    
    .login-container {
        max-width: 480px;
        margin: 0 auto;
        padding: 3rem 2rem;
        background: white;
        border-radius: 24px;
        box-shadow: var(--shadow);
        border: 1px solid rgba(13, 43, 82, 0.08);
    }

    .login-header {
        text-align: center;
        margin-bottom: 2.5rem;
    }

    .login-icon {
        width: 120px;
        height: 120px;
        border-radius: 50%;
        background: linear-gradient(135deg, var(--navy-950) 0%, var(--navy-900) 100%);
        color: white;
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 3.5rem;
        font-weight: 900;
        margin: 0 auto 1.5rem;
        border: 4px solid white;
        box-shadow: 0 12px 32px rgba(13, 43, 82, 0.25);
    }

    .login-title {
        font-size: 3rem;
        font-weight: 900;
        color: var(--navy-950);
        margin: 0 0 0.5rem;
        text-transform: uppercase;
        letter-spacing: -0.02em;
        text-decoration: underline;
        text-decoration-color: var(--navy-950);
        text-decoration-thickness: 3px;
        text-underline-offset: 8px;
    }

    .login-subtitle {
        color: #475569 !important;
        font-size: 1.1rem;
        font-weight: 600;
        margin: 0.25rem 0;
    }

    .login-info-box {
        background: linear-gradient(135deg, #f8fafc 0%, #eef3f8 100%);
        border: 1px solid rgba(13, 43, 82, 0.08);
        border-left: 4px solid var(--navy-950);
        border-radius: 12px;
        padding: 1.5rem;
        margin: 2rem 0;
    }

    .login-info-title {
        font-size: 1.1rem;
        font-weight: 700;
        color: var(--navy-950);
        margin-bottom: 0.75rem;
    }

    .login-info-text {
        color: #475569 !important;
        font-size: 0.95rem;
        line-height: 1.6;
        margin: 0;
    }

    .login-footer {
        text-align: center;
        margin-top: 2rem;
        color: #475569 !important;
        font-size: 0.9rem;
    }

    /* Navigation styling */
    .brand-lockup {
        display: flex;
        align-items: center;
        gap: 1rem;
        padding: 1.5rem;
        margin-bottom: 1rem;
    }

    .brand-mark {
        width: 48px;
        height: 48px;
        border-radius: 12px;
        background: rgba(255, 255, 255, 0.2);
        color: white;
        display: grid;
        place-items: center;
        font-weight: 900;
        font-size: 1.5rem;
    }

    .brand-title {
        font-size: 1.3rem;
        font-weight: 800;
        color: white;
        margin: 0;
    }

    .brand-subtitle {
        font-size: 0.85rem;
        color: rgba(255, 255, 255, 0.7);
        margin: 0;
    }

    /* Metric cards */
    .metric-card {
        background: white;
        border-radius: 16px;
        padding: 1.5rem;
        box-shadow: 0 4px 12px rgba(13, 43, 82, 0.06);
        border: 1px solid rgba(13, 43, 82, 0.08);
        transition: all 0.3s ease;
        position: relative;
        overflow: hidden;
    }

    .metric-card:hover {
        transform: translateY(-2px);
        box-shadow: 0 8px 24px rgba(13, 43, 82, 0.12);
    }

    .metric-header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: 1rem;
    }

    .metric-title {
        font-size: 0.9rem;
        font-weight: 600;
        color: #475569 !important;
        text-transform: uppercase;
        letter-spacing: 0.05em;
    }

    .metric-accent {
        width: 4px;
        height: 24px;
        border-radius: 2px;
    }

    .accent-critical { background: var(--critical); }
    .accent-moderate { background: var(--moderate); }
    .accent-success { background: var(--success); }
    .accent-neutral { background: var(--slate-500); }

    .metric-value {
        font-size: 2.5rem;
        font-weight: 800;
        color: var(--navy-950);
        margin: 0.5rem 0;
    }

    .metric-foot {
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-top: 1rem;
    }
    
    .metric-foot span {
        color: #475569 !important;
        font-weight: 700 !important;
        font-size: 0.94rem !important;
        opacity: 1 !important;
    }
    
    /* Metric card text with maximum specificity */
    html body .metric-card, body .metric-card,
    [data-testid="stAppViewContainer"] .metric-card {
        color: #1f2937 !important;
        opacity: 1 !important;
    }
    
    html body .metric-card *, body .metric-card *,
    [data-testid="stAppViewContainer"] .metric-card * {
        color: #1f2937 !important;
        opacity: 1 !important;
    }
    
    html body .metric-card .metric-title, body .metric-card .metric-title,
    [data-testid="stAppViewContainer"] .metric-card .metric-title {
        color: #475569 !important;
        opacity: 1 !important;
    }
    
    html body .metric-card .metric-foot span, body .metric-card .metric-foot span,
    [data-testid="stAppViewContainer"] .metric-card .metric-foot span {
        color: #475569 !important;
        opacity: 1 !important;
    }

    /* Topbar */
    .topbar {
        display: flex;
        justify-content: space-between;
        align-items: center;
        padding: 1rem 1.5rem;
        background: white;
        border-radius: 12px;
        box-shadow: 0 2px 8px rgba(13, 43, 82, 0.06);
        margin-bottom: 2rem;
    }

    .topbar-time {
        font-size: 0.9rem;
        color: #475569 !important;
        font-weight: 600;
    }

    .topbar-user {
        display: flex;
        align-items: center;
        gap: 1rem;
    }

    /* Breadcrumbs */
    .breadcrumb {
        display: flex;
        align-items: center;
        gap: 0.5rem;
        margin-bottom: 1.5rem;
        font-size: 0.9rem;
    }

    .breadcrumb-separator {
        color: #475569 !important;
        font-weight: 600;
    }

    .breadcrumb-active {
        color: var(--navy-950);
        font-weight: 700;
    }

    /* Page sections */
    .page-heading {
        margin-bottom: 2rem;
    }

    .page-heading h1 {
        font-size: 2rem;
        font-weight: 800;
        color: var(--navy-950);
        margin: 0 0 0.5rem;
    }

    .page-heading p {
        color: #475569 !important;
        font-size: 1.1rem;
        margin: 0;
    }

    .section-card {
        background: white;
        border-radius: 12px;
        padding: 1.5rem;
        margin-bottom: 1.5rem;
        border: 1px solid rgba(13, 43, 82, 0.08);
    }

    .section-title {
        font-size: 1.2rem;
        font-weight: 700;
        color: var(--navy-950);
        margin: 0 0 0.5rem;
    }

    .section-subtitle {
        color: #475569 !important;
        font-size: 0.95rem;
        margin: 0;
    }

    /* Page transitions */
    .page-transition {
        animation: fadeIn 0.3s ease-in;
    }

    @keyframes fadeIn {
        from { opacity: 0; transform: translateY(10px); }
        to { opacity: 1; transform: translateY(0); }
    }
    
    /* Fix for plotly charts and graph information with maximum specificity */
    html body .js-plotly-plot, body .js-plotly-plot, [data-testid="stAppViewContainer"] .js-plotly-plot,
    html body .plotly, body .plotly, [data-testid="stAppViewContainer"] .plotly,
    html body .modebar, body .modebar, [data-testid="stAppViewContainer"] .modebar {
        color: #1f2937 !important;
        opacity: 1 !important;
    }
    
    html body .js-plotly-plot *, body .js-plotly-plot *, [data-testid="stAppViewContainer"] .js-plotly-plot *,
    html body .plotly *, body .plotly *, [data-testid="stAppViewContainer"] .plotly *,
    html body .modebar *, body .modebar *, [data-testid="stAppViewContainer"] .modebar * {
        color: #1f2937 !important;
        opacity: 1 !important;
    }
    
    /* Fix for streamlit elements around charts */
    html body [data-testid="stPlotlyChart"], body [data-testid="stPlotlyChart"], 
    [data-testid="stAppViewContainer"] [data-testid="stPlotlyChart"] {
        color: #1f2937 !important;
        opacity: 1 !important;
    }
    
    html body [data-testid="stPlotlyChart"] *, body [data-testid="stPlotlyChart"] *, 
    [data-testid="stAppViewContainer"] [data-testid="stPlotlyChart"] * {
        color: #1f2937 !important;
        opacity: 1 !important;
    }
    
    /* Specific fix for regional distribution chart */
    html body .plotly .gtitle, body .plotly .gtitle, [data-testid="stAppViewContainer"] .plotly .gtitle,
    html body .plotly .xtitle, body .plotly .xtitle, [data-testid="stAppViewContainer"] .plotly .xtitle,
    html body .plotly .ytitle, body .plotly .ytitle, [data-testid="stAppViewContainer"] .plotly .ytitle,
    html body .plotly .xtick text, body .plotly .xtick text, [data-testid="stAppViewContainer"] .plotly .xtick text,
    html body .plotly .ytick text, body .plotly .ytick text, [data-testid="stAppViewContainer"] .plotly .ytick text,
    html body .plotly .legend text, body .plotly .legend text, [data-testid="stAppViewContainer"] .plotly .legend text {
        color: #1f2937 !important;
        opacity: 1 !important;
        fill: #1f2937 !important;
    }
    
    /* Fix for chart container and surrounding elements */
    html body .stPlotlyChartContainer, body .stPlotlyChartContainer, 
    [data-testid="stAppViewContainer"] .stPlotlyChartContainer {
        color: #1f2937 !important;
        opacity: 1 !important;
    }
    
    html body .stPlotlyChartContainer *, body .stPlotlyChartContainer *, 
    [data-testid="stAppViewContainer"] .stPlotlyChartContainer * {
        color: #1f2937 !important;
        opacity: 1 !important;
    }
    
    /* GENTLE FIX FOR PLOTLY CHART TEXT - Don't break chart rendering */
    html body .plotly .gtitle, body .plotly .gtitle, [data-testid="stAppViewContainer"] .plotly .gtitle,
    html body .plotly .xtitle, body .plotly .xtitle, [data-testid="stAppViewContainer"] .plotly .xtitle,
    html body .plotly .ytitle, body .plotly .ytitle, [data-testid="stAppViewContainer"] .plotly .ytitle,
    html body .plotly .legend, body .plotly .legend, [data-testid="stAppViewContainer"] .plotly .legend {
        color: #1f2937 !important;
        opacity: 1 !important;
    }
    
    /* Fix only text elements, not all SVG elements */
    html body .plotly text, body .plotly text, [data-testid="stAppViewContainer"] .plotly text {
        color: #1f2937 !important;
        opacity: 1 !important;
    }
    
    /* Fix for section cards - more targeted approach */
    html body .section-card, body .section-card,
    [data-testid="stAppViewContainer"] .section-card {
        color: #1f2937 !important;
    }
    
    html body .section-card .section-title, body .section-card .section-title,
    [data-testid="stAppViewContainer"] .section-card .section-title {
        color: #0d2b52 !important;
    }
    
    html body .section-card .section-subtitle, body .section-card .section-subtitle,
    [data-testid="stAppViewContainer"] .section-card .section-subtitle {
        color: #475569 !important;
    }

    /* Fix for input fields */
    .stTextInput > div > div > input {
        background: white !important;
        border: 2px solid #e5e7eb !important;
        border-radius: 12px !important;
        padding: 14px 18px !important;
        font-size: 16px !important;
        transition: all 0.3s ease !important;
        width: 100% !important;
        box-sizing: border-box !important;
        color: #1f2937 !important;
    }
    
    .stTextInput > div > div > input:focus {
        border-color: #0d2b52 !important;
        box-shadow: 0 0 0 3px rgba(13, 43, 82, 0.1) !important;
        outline: none !important;
    }
    
    .stTextInput > div > div > input::placeholder {
        color: #9ca3af !important;
        font-style: italic !important;
    }
    
    .stTextInput > div {
        margin-bottom: 16px !important;
    }

    /* Fix for form submit button */
    div[data-testid="stVerticalBlock"] > div > div > button {
        background: linear-gradient(135deg, #0d2b52 0%, #123661 100%) !important;
        color: white !important;
        border: none !important;
        border-radius: 16px !important;
        padding: 16px 32px !important;
        font-weight: 700 !important;
        font-size: 16px !important;
        transition: all 0.3s ease !important;
        box-shadow: 0 8px 24px rgba(13, 43, 82, 0.25) !important;
    }
    
    div[data-testid="stVerticalBlock"] > div > div > button:hover {
        transform: translateY(-3px) !important;
        box-shadow: 0 12px 32px rgba(13, 43, 82, 0.35) !important;
    }
    </style>
    """
