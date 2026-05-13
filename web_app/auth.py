"""Authentication Module — THIWASCO Leak Detection System"""

import base64
import os
import sys

import bcrypt
import streamlit as st

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from backend.mysql_database_manager import db_manager
from backend.session_manager import SessionManager

session_manager = SessionManager(db_manager)


LOGIN_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Syne:wght@700;800&family=DM+Sans:wght@300;400;500;600&display=swap');

/* ── Hide Streamlit chrome ── */
[data-testid="stSidebar"],
#MainMenu, footer, header,
[data-testid="stToolbar"],
[data-testid="stDecoration"],
.stApp > header { display: none !important; }

/* ── Full-page canvas ── */
html, body, .stApp {
    background: #020c1a !important;
    min-height: 100vh;
    overflow-x: hidden;
}

/* ── Ambient light spots ── */
.stApp::before {
    content: '';
    position: fixed;
    inset: 0;
    background:
        radial-gradient(ellipse 70% 60% at 16% 68%, rgba(0, 72, 160, 0.42) 0%, transparent 60%),
        radial-gradient(ellipse 48% 52% at 84% 18%, rgba(0, 100, 200, 0.20) 0%, transparent 55%);
    pointer-events: none;
    z-index: 0;
}

/* ── Grid texture ── */
.stApp::after {
    content: '';
    position: fixed;
    inset: 0;
    background-image:
        linear-gradient(rgba(0, 140, 255, 0.036) 1px, transparent 1px),
        linear-gradient(90deg, rgba(0, 140, 255, 0.036) 1px, transparent 1px);
    background-size: 55px 55px;
    pointer-events: none;
    z-index: 0;
}

/* ── Vertical + horizontal centering ── */
.main {
    display: flex !important;
    align-items: center !important;
    min-height: 100vh !important;
}

.main .block-container {
    position: relative;
    z-index: 10;
    padding: 2rem 1rem !important;
    max-width: 420px !important;
    width: 100% !important;
    margin: 0 auto !important;
}

/* ── Brand header (above card) ── */
.login-header {
    text-align: center;
    margin-bottom: 28px;
}

.brand-logo {
    width: 80px;
    height: 80px;
    object-fit: cover;
    border-radius: 50%;
    display: block;
    margin: 0 auto 14px;
}

.brand-name {
    font-family: 'Syne', sans-serif;
    font-weight: 800;
    font-size: 1.9rem;
    letter-spacing: 0.26em;
    color: #ffffff;
    margin: 0 0 6px;
    text-align: center;
}

.brand-tagline {
    font-family: 'DM Sans', sans-serif;
    font-weight: 600;
    font-size: 0.68rem;
    letter-spacing: 0.34em;
    text-transform: uppercase;
    color: #00c8ff;
    text-align: center;
    margin: 0;
}

/* ── Card — target Streamlit's form container directly ── */
[data-testid="stForm"] {
    background: rgba(6, 16, 36, 0.90) !important;
    border: 1px solid rgba(0, 120, 255, 0.18) !important;
    border-radius: 14px !important;
    padding: 28px 32px 22px !important;
    box-shadow:
        0 28px 70px rgba(0, 0, 0, 0.60),
        0 0 0 1px rgba(0, 120, 255, 0.05) !important;
}

/* ── Card heading ── */
.card-heading {
    margin-bottom: 20px;
}

.card-heading-text {
    display: block;
    font-family: 'DM Sans', sans-serif;
    font-weight: 600;
    font-size: 1.05rem;
    color: #ddeeff;
    margin-bottom: 8px;
}

.card-heading-bar {
    width: 36px;
    height: 3px;
    background: #0080ff;
    border-radius: 2px;
}

/* ── Input labels ── */
div[data-testid="stTextInput"] label {
    font-family: 'DM Sans', sans-serif !important;
    font-size: 0.67rem !important;
    font-weight: 600 !important;
    letter-spacing: 0.16em !important;
    text-transform: uppercase !important;
    color: rgba(120, 168, 220, 0.90) !important;
}

/* ── Input fields ── */
div[data-testid="stTextInput"] input {
    background: rgba(2, 10, 26, 0.65) !important;
    border: 1px solid rgba(0, 115, 240, 0.22) !important;
    border-radius: 8px !important;
    color: #d8eeff !important;
    font-family: 'DM Sans', sans-serif !important;
    font-size: 0.91rem !important;
    transition: border-color 0.2s ease, box-shadow 0.2s ease !important;
}

div[data-testid="stTextInput"] input:focus {
    border-color: rgba(0, 150, 255, 0.52) !important;
    box-shadow: 0 0 0 3px rgba(0, 120, 255, 0.13) !important;
    background: rgba(2, 13, 32, 0.80) !important;
}

div[data-testid="stTextInput"] input::placeholder {
    color: rgba(90, 140, 195, 0.58) !important;
}

/* ── Submit button ── */
div[data-testid="stFormSubmitButton"] button {
    width: 100% !important;
    background: linear-gradient(90deg, #0062cc 0%, #009aee 100%) !important;
    border: none !important;
    border-radius: 8px !important;
    color: #ffffff !important;
    font-family: 'Syne', sans-serif !important;
    font-weight: 700 !important;
    font-size: 0.78rem !important;
    letter-spacing: 0.20em !important;
    text-transform: uppercase !important;
    padding: 14px 0 !important;
    margin-top: 8px !important;
    box-shadow: 0 4px 22px rgba(0, 120, 220, 0.42) !important;
    transition: opacity 0.2s, transform 0.15s, box-shadow 0.2s !important;
}

div[data-testid="stFormSubmitButton"] button:hover {
    opacity: 0.88 !important;
    transform: translateY(-1px) !important;
    box-shadow: 0 8px 30px rgba(0, 120, 220, 0.55) !important;
}

div[data-testid="stFormSubmitButton"] button:active {
    transform: translateY(0) scale(0.99) !important;
}

/* ── Card footer row ── */
.card-footer {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-top: 16px;
}

.forgot-link {
    font-family: 'DM Sans', sans-serif;
    font-size: 0.76rem;
    color: rgba(95, 140, 192, 0.82);
}

.system-online {
    font-family: 'DM Sans', sans-serif;
    font-size: 0.76rem;
    color: rgba(95, 140, 192, 0.82);
    display: inline-flex;
    align-items: center;
    gap: 5px;
}

.online-dot {
    width: 7px;
    height: 7px;
    border-radius: 50%;
    background: #00d080;
    display: inline-block;
    box-shadow: 0 0 6px rgba(0, 208, 128, 0.65);
    flex-shrink: 0;
}

/* ── Error / success alerts ── */
div[data-testid="stAlert"] {
    background: rgba(200, 38, 38, 0.10) !important;
    border: 1px solid rgba(220, 55, 55, 0.28) !important;
    border-radius: 8px !important;
    color: #ff9f9f !important;
    font-family: 'DM Sans', sans-serif !important;
    font-size: 0.84rem !important;
}

/* ── Page footer ── */
.page-footer {
    text-align: center;
    font-family: 'DM Sans', sans-serif;
    font-size: 0.62rem;
    color: rgba(80, 125, 175, 0.52);
    margin-top: 20px;
    letter-spacing: 0.04em;
}
</style>
"""

THIWASCO_LOGO_PATH = os.path.join(
    os.path.dirname(__file__), "page_components", "thiwasco_icons", "thiwasco_logo.png"
)


def show_login() -> None:
    """Renders the THIWASCO login page."""
    defaults = {
        "authenticated": False,
        "user_id":       None,
        "user_email":    None,
        "user_name":     None,
        "user_role":     None,
    }
    for key, default in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = default

    st.markdown(LOGIN_CSS, unsafe_allow_html=True)

    # ── Brand header — logo + name + tagline above the card ────
    if os.path.exists(THIWASCO_LOGO_PATH):
        with open(THIWASCO_LOGO_PATH, "rb") as img_file:
            img_b64 = base64.b64encode(img_file.read()).decode()
        logo_html = f'<img src="data:image/png;base64,{img_b64}" class="brand-logo" alt="THIWASCO">'
    else:
        logo_html = ""

    st.markdown(
        f"""
        <div class="login-header">
            {logo_html}
            <p class="brand-name">THIWASCO</p>
            <p class="brand-tagline">Leak Detection System</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # ── Card ───────────────────────────────────────────────────
    with st.form("login_form", clear_on_submit=False):
        st.markdown(
            """
            <div class="card-heading">
                <span class="card-heading-text">Authorised Access</span>
                <div class="card-heading-bar"></div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        user_id     = st.text_input("User ID",  placeholder="e.g. THW-001")
        password    = st.text_input("Password", placeholder="Enter your password", type="password")
        remember_me = st.checkbox("Remember me for 30 days")
        submitted   = st.form_submit_button("Sign In →", use_container_width=True)

        if submitted:
            if not user_id.strip():
                st.error("Please enter your User ID.")
            elif not password:
                st.error("Please enter your password.")
            else:
                user = db_manager.get_user(user_id.strip())

                if not user:
                    st.error("Invalid User ID or password.")
                elif user.get("status") != "active":
                    st.error("Account is inactive. Contact your administrator.")
                else:
                    stored_hash = user.get("password_hash", "")
                    try:
                        valid = bcrypt.checkpw(
                            password.encode("utf-8"),
                            stored_hash.encode("utf-8"),
                        )
                    except Exception:
                        valid = False

                    if valid:
                        # Validate all required fields before creating session
                        required = {"user_id", "email", "name", "role"}
                        missing  = required - set(k for k, v in user.items() if v)
                        if missing:
                            st.error(f"Account data incomplete ({', '.join(missing)}). Contact your administrator.")
                        else:
                            token = session_manager.create_session(
                                user["user_id"], remember_me=remember_me
                            )
                            # Persist token in URL so it survives page refresh
                            st.query_params["_t"] = token
                            # Populate session state
                            st.session_state.authenticated = True
                            st.session_state.user_id       = user["user_id"]
                            st.session_state.user_email    = user["email"]
                            st.session_state.user_name     = user["name"]
                            st.session_state.user_role     = user["role"]
                            db_manager.update_last_login(user["user_id"])
                            st.rerun()
                    else:
                        st.error("Invalid User ID or password.")

    # Card footer row
    st.markdown(
        """
        <div class="card-footer">
            <span class="forgot-link">Forgot password?</span>
            <span class="system-online">
                <span class="online-dot"></span> System Online
            </span>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # ── Page footer ────────────────────────────────────────────
    st.markdown(
        '<p class="page-footer">© 2023 Thika Water and Sewerage Company Ltd. All rights reserved.</p>',
        unsafe_allow_html=True,
    )
