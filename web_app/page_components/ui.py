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
            :root {
                --brand-950: #0a1628;
                --brand-900: #0d1f3a;
                --brand-800: #123661;
                --brand-700: #1b4a7d;
                --accent: #18a0fb;
                --canvas: #0d1f3a;
                --surface: rgba(18, 54, 97, 0.6);
                --text-strong: #e8f4f8;
                --text-muted: #8ba3b8;
                --border: rgba(255, 255, 255, 0.08);
                --success: #22c55e;
                --warning: #f59e0b;
                --danger: #ef4444;
                --neutral: #9ca3af;
                --shadow: 0 18px 48px rgba(0, 0, 0, 0.3);
            }

            .stApp {
                background: linear-gradient(180deg, #0a1628 0%, #0d1f3a 100%);
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
                background: linear-gradient(180deg, #0a1628, #050d1a);
                border-right: 1px solid rgba(255, 255, 255, 0.06);
            }

            [data-testid="stSidebar"] * {
                color: #e8f4f8;
            }

            [data-testid="stSidebar"] .stRadio > label,
            [data-testid="stSidebar"] .stCheckbox > label,
            [data-testid="stSidebar"] .stSelectbox > label,
            [data-testid="stSidebar"] .stSlider > label {
                color: #8ba3b8 !important;
                font-weight: 600;
            }

            [data-baseweb="select"] > div,
            .stTextInput input,
            .stNumberInput input,
            .stDateInput input,
            .stTextArea textarea {
                border-radius: 12px !important;
                border: 1px solid var(--border) !important;
                background: rgba(13, 31, 58, 0.8) !important;
                color: var(--text-strong) !important;
            }

            .stButton > button {
                border-radius: 12px;
                border: 1px solid rgba(24, 160, 251, 0.3);
                background: linear-gradient(135deg, var(--brand-950), var(--brand-800));
                color: #ffffff;
                font-weight: 600;
                box-shadow: 0 12px 28px rgba(0, 0, 0, 0.3);
            }

            .stButton > button:hover {
                border-color: rgba(24, 160, 251, 0.5);
                background: linear-gradient(135deg, var(--brand-900), var(--brand-700));
            }

            .page-header {
                padding: 1.4rem 1.6rem;
                border-radius: 24px;
                background: linear-gradient(135deg, rgba(18, 54, 97, 0.8), rgba(13, 31, 58, 0.9));
                border: 1px solid rgba(255, 255, 255, 0.08);
                box-shadow: var(--shadow);
                margin-bottom: 1.2rem;
            }

            .page-eyebrow {
                font-size: 0.78rem;
                font-weight: 700;
                letter-spacing: 0.16em;
                text-transform: uppercase;
                color: var(--brand-700);
                margin-bottom: 0.35rem;
            }

            .page-title {
                font-size: 2.1rem;
                font-weight: 800;
                color: var(--text-strong);
                margin: 0;
            }

            .page-subtitle {
                font-size: 1rem;
                color: var(--text-muted);
                margin: 0.4rem 0 0;
            }

            .metric-card {
                padding: 1rem 1.05rem;
                border-radius: 20px;
                background: var(--surface);
                border: 1px solid var(--border);
                box-shadow: var(--shadow);
                min-height: 122px;
            }

            .metric-card--neutral { border-top: 4px solid var(--brand-700); }
            .metric-card--success { border-top: 4px solid var(--success); }
            .metric-card--warning { border-top: 4px solid var(--warning); }
            .metric-card--danger  { border-top: 4px solid var(--danger); }

            .metric-label {
                font-size: 0.82rem;
                font-weight: 700;
                text-transform: uppercase;
                letter-spacing: 0.08em;
                color: var(--text-muted);
                margin: 0 0 0.65rem;
            }

            .metric-value {
                font-size: 1.95rem;
                line-height: 1.1;
                font-weight: 800;
                color: var(--text-strong);
                margin: 0;
            }

            .metric-detail {
                margin-top: 0.55rem;
                color: var(--text-muted);
                font-size: 0.9rem;
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
                color: var(--text-strong);
                font-size: 1.15rem;
                font-weight: 700;
            }

            .section-copy {
                margin: 0.3rem 0 0;
                color: var(--text-muted);
                font-size: 0.92rem;
            }

            .status-pill {
                display: inline-flex;
                align-items: center;
                gap: 0.4rem;
                padding: 0.32rem 0.72rem;
                border-radius: 999px;
                font-size: 0.8rem;
                font-weight: 700;
                border: 1px solid transparent;
                white-space: nowrap;
            }

            .status-pill--success {
                background: rgba(34, 197, 94, 0.15);
                color: var(--success);
                border-color: rgba(34, 197, 94, 0.3);
            }

            .status-pill--warning {
                background: rgba(245, 158, 11, 0.15);
                color: var(--warning);
                border-color: rgba(245, 158, 11, 0.3);
            }

            .status-pill--danger {
                background: rgba(239, 68, 68, 0.15);
                color: var(--danger);
                border-color: rgba(239, 68, 68, 0.3);
            }

            .status-pill--neutral {
                background: rgba(156, 163, 175, 0.15);
                color: var(--neutral);
                border-color: rgba(156, 163, 175, 0.3);
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
                background: rgba(18, 54, 97, 0.4);
                border: 1px dashed rgba(255, 255, 255, 0.2);
                color: var(--text-muted);
            }
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
                font-size: 0.78rem;
                font-weight: 700;
                letter-spacing: 0.16em;
                text-transform: uppercase;
                color: var(--brand-700);
                margin-bottom: 0.35rem;
            }

            .page-title {
                font-size: 2.1rem;
                font-weight: 800;
                color: var(--brand-950);
                margin: 0;
            }

            .page-subtitle {
                font-size: 1rem;
                color: var(--text-muted);
                margin: 0.4rem 0 0;
            }

            .metric-card {
                padding: 1rem 1.05rem;
                border-radius: 20px;
                background: var(--surface);
                border: 1px solid var(--border);
                box-shadow: var(--shadow);
                min-height: 122px;
            }

            .metric-card--neutral { border-top: 4px solid var(--brand-700); }
            .metric-card--success { border-top: 4px solid var(--success); }
            .metric-card--warning { border-top: 4px solid var(--warning); }
            .metric-card--danger  { border-top: 4px solid var(--danger); }

            .metric-label {
                font-size: 0.82rem;
                font-weight: 700;
                text-transform: uppercase;
                letter-spacing: 0.08em;
                color: var(--text-muted);
                margin: 0 0 0.65rem;
            }

            .metric-value {
                font-size: 1.95rem;
                line-height: 1.1;
                font-weight: 800;
                color: var(--brand-950);
                margin: 0;
            }

            .metric-detail {
                margin-top: 0.55rem;
                color: var(--text-muted);
                font-size: 0.9rem;
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
                font-size: 1.15rem;
                font-weight: 700;
            }

            .section-copy {
                margin: 0.3rem 0 0;
                color: var(--text-muted);
                font-size: 0.92rem;
            }

            .status-pill {
                display: inline-flex;
                align-items: center;
                gap: 0.4rem;
                padding: 0.32rem 0.72rem;
                border-radius: 999px;
                font-size: 0.8rem;
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
