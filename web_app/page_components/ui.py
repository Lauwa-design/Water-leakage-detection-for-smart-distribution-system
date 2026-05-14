"""Shared UI helpers for the THIWASCO Streamlit dashboard."""

from __future__ import annotations

import html

import streamlit as st


def apply_theme(dark_mode: bool = True) -> None:
    """Inject the shared application theme once per session."""
    if st.session_state.get("_thiwasco_theme_applied"):
        return

    st.session_state["_thiwasco_theme_applied"] = True

    if dark_mode:
        theme_css = """
        <style>
            @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap');

            /* ── Global typography to match Leak Analysis crisp style ── */
            h1, .stApp h1 { font-size: 1.94rem !important; font-weight: 800 !important; color: #e2e8f0 !important; letter-spacing: -0.01em; }
            h2, .stApp h2 { font-size: 1.44rem !important; font-weight: 700 !important; color: #e2e8f0 !important; }
            h3, .stApp h3 { font-size: 1.24rem !important; font-weight: 700 !important; color: #e2e8f0 !important; }
            p,  .stApp p  { font-size: 1.07rem !important; font-weight: 400 !important; color: #94a3b8 !important; }

            /* st.title */
            [data-testid="stHeading"] h1 { font-size: 1.94rem !important; font-weight: 800 !important; }
            /* st.subheader */
            [data-testid="stHeading"] h2 { font-size: 1.29rem !important; font-weight: 700 !important; }

            /* st.write / st.markdown body text */
            .stMarkdown p   { font-size: 1.07rem !important; color: #94a3b8 !important; line-height: 1.6; }
            .stMarkdown li  { font-size: 1.07rem !important; color: #94a3b8 !important; }
            .stMarkdown strong, .stMarkdown b { color: #e2e8f0 !important; font-weight: 700 !important; }

            /* st.caption */
            [data-testid="stCaptionContainer"] p { font-size: 0.94rem !important; color: #475569 !important; }

            /* Widget labels */
            label[data-testid="stWidgetLabel"] p,
            .stSelectbox label p,
            .stMultiselect label p,
            .stTextInput label p,
            .stNumberInput label p,
            .stTextArea label p,
            .stCheckbox label p {
                font-size: 0.97rem !important;
                font-weight: 600 !important;
                color: #64748b !important;
                text-transform: uppercase;
                letter-spacing: 0.07em;
            }

            /* st.metric */
            [data-testid="stMetricLabel"]  p { font-size: 0.91rem !important; font-weight: 700 !important; text-transform: uppercase; letter-spacing: 0.08em; color: #475569 !important; }
            [data-testid="stMetricValue"]    { font-size: 2.09rem !important; font-weight: 800 !important; color: #e2e8f0 !important; }
            [data-testid="stMetricDelta"]    { font-size: 0.97rem !important; font-weight: 600 !important; }

            /* Dataframe / table text */
            [data-testid="stDataFrame"] th  { font-size: 0.87rem !important; font-weight: 700 !important; text-transform: uppercase; letter-spacing: 0.09em; color: #475569 !important; }
            [data-testid="stDataFrame"] td  { font-size: 1.01rem !important; color: #cbd5e1 !important; }

            /* Buttons */
            .stButton > button { font-size: 1.02rem !important; font-weight: 600 !important; letter-spacing: 0.03em; }

            /* Sidebar nav items */
            [data-testid="stSidebar"] label { font-size: 1.04rem !important; font-weight: 500 !important; }

            /* Tab labels */
            [data-testid="stTabs"] button { font-size: 1.01rem !important; font-weight: 600 !important; }

            :root {
                --canvas:  #080f1e;
                --surface: #0d1526;
                --card:    #111d35;
                --border:  rgba(255,255,255,0.07);
                --green:   #22c55e;
                --blue:    #3b82f6;
                --amber:   #f59e0b;
                --red:     #ef4444;
                --text-1:  #e2e8f0;
                --text-2:  #94a3b8;
                --text-3:  #475569;
                --shadow:  0 4px 16px rgba(0,0,0,0.35);
                /* legacy aliases used by page components */
                --success: #22c55e;
                --warning: #f59e0b;
                --danger:  #ef4444;
                --neutral: #94a3b8;
                --text-strong: #e2e8f0;
                --text-muted:  #94a3b8;
            }

            .stApp {
                background:
                    radial-gradient(ellipse 80% 50% at 50% -10%,
                        rgba(255,255,255,0.06) 0%, transparent 70%),
                    var(--canvas) !important;
                color: var(--text-1);
            }
            [data-testid="stAppViewContainer"] { background: transparent; }
            .main .block-container { max-width: 1360px; padding-top: 1.5rem; padding-bottom: 3rem; }

            /* ── Sidebar ── */
            [data-testid="stSidebar"] {
                background: var(--surface) !important;
                border-right: 1px solid var(--border) !important;
            }
            [data-testid="stSidebar"] * { color: var(--text-1); }

            /* Hide "Navigation" radio label */
            [data-testid="stSidebar"] .stRadio > label { display: none !important; }

            [data-testid="stSidebar"] .stCheckbox > label,
            [data-testid="stSidebar"] .stSelectbox > label {
                color: var(--text-2) !important; font-weight: 600;
            }

            /* ── Sidebar radio nav ── */
            [data-testid="stSidebar"] [data-testid="stRadio"] [role="radiogroup"] {
                gap: 2px !important; padding: 4px 0 !important;
            }
            [data-testid="stSidebar"] [data-testid="stRadio"] [role="radiogroup"] > label {
                display: flex !important; align-items: center !important;
                padding: 8px 12px 8px 12px !important;
                border-left: 3px solid transparent !important;
                border-radius: 0 8px 8px 0 !important;
                cursor: pointer !important;
                color: var(--text-2) !important;
                font-size: 0.875rem !important; font-weight: 500 !important;
                width: 100% !important; margin: 0 !important;
                transition: background 0.15s, color 0.15s !important;
            }
            [data-testid="stSidebar"] [data-testid="stRadio"] [role="radiogroup"] > label:hover {
                background: rgba(255,255,255,0.05) !important; color: var(--text-1) !important;
            }
            [data-testid="stSidebar"] [data-testid="stRadio"] [role="radiogroup"] > label > div:first-child {
                display: none !important;
            }
            [data-testid="stSidebar"] [data-testid="stRadio"] [role="radiogroup"] > label:has(input:checked) {
                color: var(--green) !important; font-weight: 600 !important;
                border-left-color: var(--green) !important;
                background: rgba(34,197,94,0.07) !important;
            }

            /* ── Inputs ── */
            [data-baseweb="select"] > div,
            .stTextInput input, .stNumberInput input,
            .stDateInput input, .stTextArea textarea {
                border-radius: 8px !important;
                border: 1px solid var(--border) !important;
                background: var(--card) !important;
                color: var(--text-1) !important;
            }

            /* ── Buttons ── */
            .stButton > button {
                border-radius: 8px;
                border: 1px solid rgba(255,255,255,0.1);
                background: var(--card);
                color: var(--text-1);
                font-weight: 600; font-size: 0.85rem;
            }
            .stButton > button:hover {
                border-color: rgba(59,130,246,0.5); color: #fff;
            }

            /* ── Sign Out button glow ── */
            [data-testid="stSidebar"] .stButton > button {
                border: 1px solid rgba(59,130,246,0.40) !important;
                color: #93c5fd !important;
                background: rgba(59,130,246,0.08) !important;
                box-shadow: 0 0 10px 1px rgba(59,130,246,0.30),
                            0 0 20px 2px rgba(59,130,246,0.14) !important;
                transition: box-shadow 0.2s, border-color 0.2s !important;
            }
            [data-testid="stSidebar"] .stButton > button:hover {
                border-color: rgba(59,130,246,0.70) !important;
                color: #fff !important;
                background: rgba(59,130,246,0.18) !important;
                box-shadow: 0 0 14px 2px rgba(59,130,246,0.55),
                            0 0 28px 4px rgba(59,130,246,0.25) !important;
            }

            /* ── Active status badge — green glow ── */
            .badge-active {
                display: inline-block;
                background: rgba(34,197,94,0.10);
                color: #22c55e;
                border: 1px solid rgba(34,197,94,0.35);
                border-radius: 4px;
                font-size: 0.68rem;
                font-weight: 700;
                padding: 1px 8px;
                letter-spacing: 0.06em;
                box-shadow: 0 0 8px 1px rgba(34,197,94,0.50),
                            0 0 18px 2px rgba(34,197,94,0.22);
            }

            /* ── Shared card component (used by non-overview pages) ── */
            .page-header {
                padding: 1.1rem 1.4rem;
                border-radius: 10px;
                background: var(--card);
                border: 1px solid var(--border);
                border-left: 3px solid var(--blue);
                box-shadow: var(--shadow);
                margin-bottom: 1.25rem;
            }
            .page-eyebrow {
                font-size: 0.87rem; font-weight: 700;
                letter-spacing: 0.14em; text-transform: uppercase;
                color: var(--blue); margin-bottom: 0.2rem;
            }
            .page-title  { font-size: 1.69rem; font-weight: 700; color: var(--text-1); margin: 0; }
            .page-subtitle { font-size: 1.04rem; color: var(--text-2); margin: 0.25rem 0 0; }

            .metric-card {
                padding: 1rem 1.15rem;
                border-radius: 10px;
                background: var(--card);
                border: 1px solid var(--border);
                box-shadow: var(--shadow);
                min-height: 130px;
            }
            .metric-card--neutral { box-shadow: 0 0 20px 2px rgba(40,112,184,.22), var(--shadow); border-color: rgba(40,112,184,.28); }
            .metric-card--success { box-shadow: 0 0 20px 2px rgba(21,128,61,.20),  var(--shadow); border-color: rgba(21,128,61,.28); }
            .metric-card--warning { box-shadow: 0 0 20px 2px rgba(180,83,9,.22),   var(--shadow); border-color: rgba(180,83,9,.28); }
            .metric-card--danger  { box-shadow: 0 0 20px 2px rgba(185,28,28,.22),  var(--shadow); border-color: rgba(185,28,28,.28); }

            .metric-label {
                font-size: 0.87rem; font-weight: 700; text-transform: uppercase;
                letter-spacing: 0.1em; color: var(--text-2); margin: 0 0 0.5rem;
            }
            .metric-value {
                font-size: 1.9rem; line-height: 1.15; font-weight: 800;
                color: var(--text-1); margin: 0; white-space: nowrap; overflow: hidden;
                text-overflow: ellipsis;
            }
            .metric-detail { margin-top: 0.4rem; color: var(--text-2); font-size: 0.88rem; }

            /* Overview metric value color classes */
            .text-cyan    { color: #06b6d4 !important; }
            .text-emerald { color: #22c55e !important; }
            .text-amber   { color: #f59e0b !important; }
            .text-red     { color: #ef4444 !important; }

            .section-card {
                padding: 1rem 1.15rem;
                border-radius: 10px;
                background: var(--card);
                border: 1px solid var(--border);
                box-shadow: var(--shadow);
                margin-bottom: 0.75rem;
            }
            .section-title { margin: 0; color: var(--text-1); font-size: 1.14rem; font-weight: 700; }
            .section-copy  { margin: 0.2rem 0 0; color: var(--text-2); font-size: 1.01rem; }

            .status-pill {
                display: inline-flex; align-items: center; gap: 0.35rem;
                padding: 0.22rem 0.6rem; border-radius: 4px;
                font-size: 0.91rem; font-weight: 700;
                border: 1px solid transparent; white-space: nowrap;
            }
            .status-pill--success { background: rgba(34,197,94,0.12);  color: var(--green);  border-color: rgba(34,197,94,0.25); }
            .status-pill--warning { background: rgba(245,158,11,0.12); color: var(--amber);  border-color: rgba(245,158,11,0.25); }
            .status-pill--danger  { background: rgba(239,68,68,0.12);  color: var(--red);    border-color: rgba(239,68,68,0.25); }
            .status-pill--neutral { background: rgba(148,163,184,0.1); color: var(--text-2); border-color: rgba(148,163,184,0.2); }

            .status-row { display: flex; flex-wrap: wrap; gap: 0.4rem; margin-top: 0.75rem; }

            .empty-state {
                border-radius: 8px; padding: 1rem 1.15rem;
                background: rgba(17,29,53,0.6);
                border: 1px dashed rgba(255,255,255,0.1);
                color: var(--text-2);
            }

            [data-testid="stDataFrame"] > div { background: transparent !important; }
        </style>
        """
        st.markdown(theme_css, unsafe_allow_html=True)
        return

    # Light theme
    theme_css = """
        <style>
            :root {
                --brand-950: #0d2b52;
                --brand-900: #123661;
                --brand-800: #1b4a7d;
                --brand-700: #2870b8;
                --accent: #18a0fb;
                --canvas: #eef4f8;
                --surface: rgba(255, 255, 255, 0.94);
                --text-strong: #10233b;
                --text-muted: #5f7188;
                --border: rgba(17, 43, 73, 0.12);
                --success: #15803d;
                --warning: #b45309;
                --danger: #b91c1c;
                --neutral: #4b5563;
                --shadow: 0 18px 48px rgba(13, 43, 82, 0.08);
            }

            .stApp {
                background:
                    radial-gradient(circle at top left, rgba(24, 160, 251, 0.12), transparent 34%),
                    linear-gradient(180deg, #f7fbfe 0%, var(--canvas) 100%);
                color: var(--text-strong);
            }

            [data-testid="stAppViewContainer"] {
                background: transparent;
            }

            .main .block-container {
                max-width: 1280px;
                padding-top: 1.5rem;
                padding-bottom: 3rem;
            }

            [data-testid="stSidebar"] {
                background: linear-gradient(180deg, var(--brand-950), #0a1f3a);
                border-right: 1px solid rgba(255, 255, 255, 0.06);
            }

            [data-testid="stSidebar"] * {
                color: #edf6ff;
            }

            [data-testid="stSidebar"] .stRadio > label,
            [data-testid="stSidebar"] .stCheckbox > label,
            [data-testid="stSidebar"] .stSelectbox > label,
            [data-testid="stSidebar"] .stSlider > label {
                color: #b8d8f5 !important;
                font-weight: 600;
            }

            [data-baseweb="select"] > div,
            .stTextInput input,
            .stNumberInput input,
            .stDateInput input,
            .stTextArea textarea {
                border-radius: 12px !important;
                border: 1px solid var(--border) !important;
                background: rgba(255, 255, 255, 0.96) !important;
                color: var(--text-strong) !important;
            }

            .stButton > button {
                border-radius: 12px;
                border: 1px solid rgba(18, 54, 97, 0.14);
                background: linear-gradient(135deg, var(--brand-950), var(--brand-800));
                color: #ffffff;
                font-weight: 600;
                box-shadow: 0 12px 28px rgba(18, 54, 97, 0.16);
            }

            .stButton > button:hover {
                border-color: rgba(24, 160, 251, 0.25);
                background: linear-gradient(135deg, var(--brand-900), var(--brand-700));
            }

            .page-header {
                padding: 1.4rem 1.6rem;
                border-radius: 24px;
                background: linear-gradient(135deg, rgba(255,255,255,0.92), rgba(240,248,255,0.95));
                border: 1px solid rgba(17, 43, 73, 0.08);
                box-shadow: var(--shadow);
                margin-bottom: 1.2rem;
            }

            .page-eyebrow {
                font-size: 0.97rem;
                font-weight: 700;
                letter-spacing: 0.16em;
                text-transform: uppercase;
                color: var(--brand-700);
                margin-bottom: 0.35rem;
            }

            .page-title {
                font-size: 2.29rem;
                font-weight: 800;
                color: var(--brand-950);
                margin: 0;
            }

            .page-subtitle {
                font-size: 1.19rem;
                color: var(--text-muted);
                margin: 0.4rem 0 0;
            }

            .metric-card {
                padding: 1rem 1.05rem;
                border-radius: 20px;
                background: var(--surface);
                border: 1px solid var(--border);
                box-shadow: var(--shadow);
                min-height: 130px;
            }

            .metric-card--neutral { box-shadow: 0 0 20px 2px rgba(59,130,246,.28), var(--shadow); border-color: rgba(59,130,246,.22); }
            .metric-card--success { box-shadow: 0 0 20px 2px rgba(34,197,94,.30), var(--shadow); border-color: rgba(34,197,94,.22); }
            .metric-card--warning { box-shadow: 0 0 20px 2px rgba(245,158,11,.30), var(--shadow); border-color: rgba(245,158,11,.22); }
            .metric-card--danger  { box-shadow: 0 0 20px 2px rgba(239,68,68,.30),  var(--shadow); border-color: rgba(239,68,68,.22); }

            .metric-label {
                font-size: 0.72rem;
                font-weight: 700;
                text-transform: uppercase;
                letter-spacing: 0.08em;
                color: var(--text-muted);
                margin: 0 0 0.5rem;
            }

            .metric-value {
                font-size: 1.9rem;
                line-height: 1.15;
                font-weight: 800;
                color: var(--brand-950);
                margin: 0;
                white-space: nowrap;
                overflow: hidden;
                text-overflow: ellipsis;
            }

            .metric-detail {
                margin-top: 0.4rem;
                color: var(--text-muted);
                font-size: 0.82rem;
            }

            .section-card {
                padding: 1.15rem 1.2rem;
                border-radius: 20px;
                background: var(--surface);
                border: 1px solid var(--border);
                box-shadow: var(--shadow);
                margin-bottom: 0.85rem;
            }

            .section-title {
                margin: 0;
                color: var(--brand-950);
                font-size: 1.34rem;
                font-weight: 700;
            }

            .section-copy {
                margin: 0.3rem 0 0;
                color: var(--text-muted);
                font-size: 1.11rem;
            }

            .status-pill {
                display: inline-flex;
                align-items: center;
                gap: 0.4rem;
                padding: 0.32rem 0.72rem;
                border-radius: 999px;
                font-size: 0.99rem;
                font-weight: 700;
                border: 1px solid transparent;
                white-space: nowrap;
            }

            .status-pill--success {
                background: rgba(21, 128, 61, 0.12);
                color: var(--success);
                border-color: rgba(21, 128, 61, 0.18);
            }

            .status-pill--warning {
                background: rgba(180, 83, 9, 0.12);
                color: var(--warning);
                border-color: rgba(180, 83, 9, 0.18);
            }

            .status-pill--danger {
                background: rgba(185, 28, 28, 0.12);
                color: var(--danger);
                border-color: rgba(185, 28, 28, 0.18);
            }

            .status-pill--neutral {
                background: rgba(75, 85, 99, 0.1);
                color: var(--neutral);
                border-color: rgba(75, 85, 99, 0.14);
            }

            .status-row {
                display: flex;
                flex-wrap: wrap;
                gap: 0.55rem;
                margin-top: 0.9rem;
            }

            .empty-state {
                border-radius: 18px;
                padding: 1.2rem 1.3rem;
                background: rgba(255,255,255,0.9);
                border: 1px dashed rgba(17, 43, 73, 0.18);
                color: var(--text-muted);
            }
        </style>
        """
    st.markdown(theme_css, unsafe_allow_html=True)


def page_header(title: str, subtitle: str, eyebrow: str = "THIWASCO Monitoring") -> None:
    """Render a consistent page header."""
    st.markdown(
        f"""
        <div class="page-header">
            <div class="page-eyebrow">{html.escape(eyebrow)}</div>
            <h1 class="page-title">{html.escape(title)}</h1>
            <p class="page-subtitle">{html.escape(subtitle)}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def metric_card(label: str, value: str, detail: str = "", tone: str = "neutral") -> None:
    """Render a styled KPI card."""
    detail_html = f'<div class="metric-detail">{html.escape(detail)}</div>' if detail else ""
    st.markdown(
        f"""
        <div class="metric-card metric-card--{html.escape(tone)}">
            <div class="metric-label">{html.escape(label)}</div>
            <div class="metric-value">{html.escape(value)}</div>
            {detail_html}
        </div>
        """,
        unsafe_allow_html=True,
    )


def section_header(title: str, copy: str = "") -> None:
    """Render a compact section header."""
    copy_html = f'<p class="section-copy">{html.escape(copy)}</p>' if copy else ""
    st.markdown(
        f"""
        <div class="section-card">
            <h2 class="section-title">{html.escape(title)}</h2>
            {copy_html}
        </div>
        """,
        unsafe_allow_html=True,
    )


def status_pill(label: str, tone: str = "neutral") -> str:
    """Return HTML for a compact status pill."""
    return f'<span class="status-pill status-pill--{html.escape(tone)}">{html.escape(label)}</span>'


def render_status_row(items: list[tuple[str, str]]) -> None:
    """Render a horizontal row of status pills."""
    markup = "".join(status_pill(label, tone) for label, tone in items)
    st.markdown(f'<div class="status-row">{markup}</div>', unsafe_allow_html=True)


def empty_state(message: str) -> None:
    """Render a lightweight empty state."""
    st.markdown(f'<div class="empty-state">{html.escape(message)}</div>', unsafe_allow_html=True)


_METRIC_GLOW = {
    "text-cyan":    ("rgba(6,182,212,.30)",  "rgba(6,182,212,.22)"),
    "text-emerald": ("rgba(34,197,94,.30)",  "rgba(34,197,94,.22)"),
    "text-amber":   ("rgba(245,158,11,.30)", "rgba(245,158,11,.22)"),
    "text-red":     ("rgba(239,68,68,.30)",  "rgba(239,68,68,.22)"),
}


def render_metric(label: str, value: str, color_class: str = "text-emerald") -> None:
    """Render a compact metric inside a glowing section card."""
    glow, border = _METRIC_GLOW.get(color_class, ("rgba(59,130,246,.25)", "rgba(59,130,246,.18)"))
    st.markdown(
        f'<div class="section-card" style="box-shadow:0 0 22px 2px {glow};border-color:{border};">'
        f'<div class="metric-label">{html.escape(label)}</div>'
        f'<div class="metric-value {html.escape(color_class)}">{html.escape(str(value))}</div>'
        f'</div>',
        unsafe_allow_html=True,
    )


def render_status_pill(text: str, is_healthy: bool = True) -> None:
    """Render a small inline status badge."""
    tone = "success" if is_healthy else "danger"
    st.markdown(
        f'<span class="status-pill status-pill--{tone}">{html.escape(text.upper())}</span>',
        unsafe_allow_html=True,
    )


# ── Glow colour map ───────────────────────────────────────────────────────────
_GLOW_MAP: dict[str, tuple[str, str, str]] = {
    # value (lower)  : (text_color,  inner_glow,               outer_glow)
    "critical":  ("#ef4444", "rgba(239,68,68,0.95)",  "rgba(239,68,68,0.50)"),
    "warning":   ("#f59e0b", "rgba(245,158,11,0.95)", "rgba(245,158,11,0.50)"),
    "suspected": ("#a855f7", "rgba(168,85,247,0.95)", "rgba(168,85,247,0.50)"),
    "active":    ("#22c55e", "rgba(34,197,94,0.90)",  "rgba(34,197,94,0.45)"),
    "inactive":  ("#ef4444", "rgba(239,68,68,0.80)",  "rgba(239,68,68,0.35)"),
    "resolved":  ("#22c55e", "rgba(34,197,94,0.70)",  "rgba(34,197,94,0.25)"),
    "new":       ("#3b82f6", "rgba(59,130,246,0.80)",  "rgba(59,130,246,0.30)"),
    "assigned":  ("#f59e0b", "rgba(245,158,11,0.75)", "rgba(245,158,11,0.28)"),
    "normal":    ("#94a3b8", "rgba(148,163,184,0.60)", "rgba(148,163,184,0.20)"),
    "none":      ("#475569", "rgba(71,85,105,0.50)",   "rgba(71,85,105,0.15)"),
}

_TABLE_CSS = """
<style>
.glow-table-wrap{
    overflow-x:auto;overflow-y:auto;max-height:260px;
    border-radius:10px;border:1px solid rgba(255,255,255,0.07);
}
.glow-table{width:100%;border-collapse:collapse;font-size:0.88rem;}
.glow-table th{
    background:#111d35;color:#475569;font-size:0.7rem;font-weight:700;
    letter-spacing:0.09em;text-transform:uppercase;padding:9px 14px;
    border-bottom:1px solid rgba(255,255,255,0.07);text-align:left;
    position:sticky;top:0;z-index:1;
}
.glow-table td{
    padding:8px 14px;color:#cbd5e1;border-bottom:1px solid rgba(255,255,255,0.04);
}
.glow-table tr:last-child td{border-bottom:none;}
.glow-table tr:hover td{background:rgba(255,255,255,0.02);}
</style>
"""


def _glow_cell(raw_val) -> str:
    """Return an HTML cell value — glowing badge if the value is a known status."""
    if raw_val is None:
        return "—"
    s = str(raw_val).strip()
    key = s.lower()
    if key in _GLOW_MAP:
        color, g1, g2 = _GLOW_MAP[key]
        return (
            f"<span style='color:{color};font-weight:700;"
            f"text-shadow:0 0 7px {g1},0 0 18px {g2};'>"
            f"{html.escape(s)}</span>"
        )
    return html.escape(s)


def show_glowing_table(
    df,
    use_container_width: bool = True,
    max_rows: int = 200,
) -> None:
    """Render a DataFrame as an HTML table with glow effects on status/severity cells.

    Drop-in replacement for ``st.dataframe()`` wherever status/severity columns appear.
    Recognised values (case-insensitive): critical, warning, suspected, active,
    inactive, resolved, new, assigned, normal, none.
    """
    import pandas as pd

    if df is None or (hasattr(df, "empty") and df.empty):
        st.info("No data to display.")
        return

    if not isinstance(df, pd.DataFrame):
        df = pd.DataFrame(df)

    df = df.head(max_rows)

    ths = "".join(f"<th>{html.escape(str(c))}</th>" for c in df.columns)
    rows_html = ""
    for _, row in df.iterrows():
        cells = "".join(f"<td>{_glow_cell(v)}</td>" for v in row)
        rows_html += f"<tr>{cells}</tr>"

    table_html = (
        _TABLE_CSS
        + f"<div class='glow-table-wrap'>"
        f"<table class='glow-table'>"
        f"<thead><tr>{ths}</tr></thead>"
        f"<tbody>{rows_html}</tbody>"
        f"</table></div>"
    )
    st.html(table_html)
