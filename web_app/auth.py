"""Authentication Module — THIWASCO Leak Detection System"""

import streamlit as st
import time
import sys
import os
import bcrypt

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from backend.mysql_database_manager import db_manager


# ─────────────────────────────────────────────
#  CSS — Full-page premium dark water aesthetic
# ─────────────────────────────────────────────
LOGIN_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Syne:wght@400;700;800&family=DM+Sans:ital,wght@0,300;0,400;0,500;1,300&display=swap');

/* Hide Streamlit chrome only */
[data-testid="stSidebar"],
section[data-testid="stSidebar"],
#MainMenu, footer, header,
[data-testid="stToolbar"],
[data-testid="stDecoration"],
.stApp > header { display: none !important; }

/* Hide any empty input containers or extra widgets above the card */
.login-card ~ div:not(.login-card):not(.system-status):not(.login-footer) {
    display: none !important;
}

/* Full viewport dark canvas */
html, body, .stApp {
    background: #04111F !important;
    min-height: 100vh;
    overflow-x: hidden;
}

/* Atmospheric gradient mesh */
.stApp::before {
    content: '';
    position: fixed;
    inset: 0;
    background:
        radial-gradient(ellipse 70% 55% at 12% 85%, rgba(0, 85, 170, 0.28) 0%, transparent 65%),
        radial-gradient(ellipse 55% 65% at 88% 8%,  rgba(0, 130, 210, 0.18) 0%, transparent 60%),
        radial-gradient(ellipse 40% 40% at 55% 45%, rgba(3,  35,  80, 0.45) 0%, transparent 70%);
    pointer-events: none;
    z-index: 0;
    animation: ambience 10s ease-in-out infinite alternate;
}

/* Fine grid texture */
.stApp::after {
    content: '';
    position: fixed;
    inset: 0;
    background-image:
        linear-gradient(rgba(0, 145, 255, 0.035) 1px, transparent 1px),
        linear-gradient(90deg, rgba(0, 145, 255, 0.035) 1px, transparent 1px);
    background-size: 52px 52px;
    pointer-events: none;
    z-index: 0;
}

@keyframes ambience {
    from { opacity: 0.75; }
    to   { opacity: 1.0;  }
}

/* Keep Streamlit content above effects */
.main .block-container {
    position: relative;
    z-index: 10;
    padding: 0 !important;
    max-width: 420px !important;
    margin: 0 auto !important;
}

/* Hide any text inputs or form elements outside the login card */
.main .block-container > div:not(:has(.login-card)) div[data-testid="stTextInput"],
.main .block-container > div:not(:has(.login-card)) [data-testid="stForm"] {
    display: none !important;
}

/* ── Glass card ── */
.login-card {
    max-width: 380px;
    width: 100%;
    margin: 80px auto 0 auto;
    background: rgba(6, 18, 42, 0.80);
    border: 1px solid rgba(0, 145, 255, 0.16);
    border-radius: 22px;
    padding: 48px 40px 40px;
    backdrop-filter: blur(28px);
    -webkit-backdrop-filter: blur(28px);
    box-shadow:
        0 0 0 1px rgba(0, 145, 255, 0.05),
        0 40px 90px rgba(0, 0, 0, 0.60),
        0 6px 30px rgba(0, 90, 200, 0.14);
    animation: slide-up 0.55s cubic-bezier(0.22, 1, 0.36, 1) both;
}

@keyframes slide-up {
    from { opacity: 0; transform: translateY(32px) scale(0.975); }
    to   { opacity: 1; transform: translateY(0)    scale(1);     }
}

/* ── Icon badge ── */
.icon-badge {
    width: 60px;
    height: 60px;
    border-radius: 18px;
    background: linear-gradient(140deg, #0A6EBD 0%, #04ADEF 100%);
    display: flex;
    align-items: center;
    justify-content: center;
    margin: 0 auto 22px;
    box-shadow: 0 8px 28px rgba(4, 146, 194, 0.40);
    animation: badge-pop 0.6s 0.15s cubic-bezier(0.34, 1.56, 0.64, 1) both;
}

@keyframes badge-pop {
    from { opacity: 0; transform: scale(0.6); }
    to   { opacity: 1; transform: scale(1);   }
}

/* ── Headings ── */
.brand-name {
    font-family: 'Syne', sans-serif;
    font-weight: 800;
    font-size: 1.65rem;
    letter-spacing: 0.15em;
    color: #FFFFFF;
    text-align: center;
    margin: 0 0 5px;
}

.brand-tagline {
    font-family: 'DM Sans', sans-serif;
    font-weight: 400;
    font-size: 0.74rem;
    letter-spacing: 0.28em;
    text-transform: uppercase;
    color: rgba(100, 210, 255, 0.90);
    text-align: center;
    margin: 0 0 30px;
}

.divider {
    height: 1px;
    background: linear-gradient(90deg, transparent, rgba(0, 145, 255, 0.28), transparent);
    margin-bottom: 28px;
}

.form-section-label {
    font-family: 'DM Sans', sans-serif;
    font-weight: 500;
    font-size: 0.75rem;
    letter-spacing: 0.18em;
    text-transform: uppercase;
    color: rgba(160, 200, 255, 0.85);
    margin-bottom: 16px;
}

/* ── Input labels ── */
div[data-testid="stTextInput"] label {
    font-family: 'DM Sans', sans-serif !important;
    font-size: 0.72rem !important;
    font-weight: 600 !important;
    letter-spacing: 0.14em !important;
    text-transform: uppercase !important;
    color: rgba(180, 210, 255, 0.90) !important;
}

/* ── Input fields ── */
div[data-testid="stTextInput"] input {
    background: rgba(255, 255, 255, 0.04) !important;
    border: 1px solid rgba(0, 145, 255, 0.18) !important;
    border-radius: 11px !important;
    color: #DFF0FF !important;
    font-family: 'DM Sans', sans-serif !important;
    font-size: 0.92rem !important;
    transition: border-color 0.2s ease, background 0.2s ease, box-shadow 0.2s ease !important;
}

div[data-testid="stTextInput"] input:focus {
    background: rgba(0, 145, 255, 0.07) !important;
    border-color: rgba(0, 185, 255, 0.50) !important;
    box-shadow: 0 0 0 3px rgba(0, 145, 255, 0.12) !important;
}

div[data-testid="stTextInput"] input::placeholder {
    color: rgba(140, 180, 220, 0.70) !important;
}

/* ── Submit button ── */
div[data-testid="stFormSubmitButton"] button {
    width: 100% !important;
    background: linear-gradient(135deg, #0A6EBD 0%, #04ADEF 100%) !important;
    border: none !important;
    border-radius: 11px !important;
    color: #FFFFFF !important;
    font-family: 'Syne', sans-serif !important;
    font-weight: 700 !important;
    font-size: 0.82rem !important;
    letter-spacing: 0.16em !important;
    text-transform: uppercase !important;
    padding: 13px 0 !important;
    margin-top: 10px !important;
    box-shadow: 0 6px 24px rgba(4, 146, 194, 0.38) !important;
    transition: opacity 0.2s, transform 0.15s, box-shadow 0.2s !important;
}

div[data-testid="stFormSubmitButton"] button:hover {
    opacity: 0.88 !important;
    transform: translateY(-1px) !important;
    box-shadow: 0 10px 32px rgba(4, 146, 194, 0.50) !important;
}

div[data-testid="stFormSubmitButton"] button:active {
    transform: translateY(0px) scale(0.99) !important;
}

/* ── Error alert ── */
div[data-testid="stAlert"] {
    background: rgba(220, 50, 50, 0.09) !important;
    border: 1px solid rgba(220, 80, 80, 0.25) !important;
    border-radius: 11px !important;
    color: #FF9B9B !important;
    font-family: 'DM Sans', sans-serif !important;
    font-size: 0.85rem !important;
}

/* ── Status pulse footer ── */
.system-status {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 7px;
    font-family: 'DM Sans', sans-serif;
    font-size: 0.7rem;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    color: rgba(120, 230, 180, 0.90);
    margin-top: 28px;
}

.pulse-dot {
    width: 6px;
    height: 6px;
    background: #00E5A0;
    border-radius: 50%;
    box-shadow: 0 0 8px rgba(0, 229, 160, 0.70);
    animation: pulse 2.8s ease-in-out infinite;
    flex-shrink: 0;
}

@keyframes pulse {
    0%, 100% { opacity: 1;    transform: scale(1);    }
    50%       { opacity: 0.3; transform: scale(0.75); }
}

.login-footer {
    font-family: 'DM Sans', sans-serif;
    font-size: 0.66rem;
    letter-spacing: 0.10em;
    color: rgba(120, 160, 200, 0.75);
    text-align: center;
    margin-top: 8px;
    padding-bottom: 2px;
}
</style>
"""

# THIWASCO Logo path
THIWASCO_LOGO_PATH = os.path.join(os.path.dirname(__file__), "page_components", "thiwasco_icons", "thiwasco_logo.png")




def show_login():
    """Renders the THIWASCO login page."""

    # ── Session state init ──────────────────────
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

    # Inject global styles
    st.markdown(LOGIN_CSS, unsafe_allow_html=True)

    # ── Login card centered ──────────────────
    st.markdown('<div class="login-card">', unsafe_allow_html=True)
    
    # Logo above THIWASCO name - centered
    if os.path.exists(THIWASCO_LOGO_PATH):
        import base64
        with open(THIWASCO_LOGO_PATH, "rb") as img_file:
            img_base64 = base64.b64encode(img_file.read()).decode()
        st.markdown(f'<div style="text-align: center; margin-bottom: 10px;"><img src="data:image/png;base64,{img_base64}" width="60"></div>', unsafe_allow_html=True)
    
    st.markdown(
        '<p class="brand-name">THIWASCO</p>'
        '<p class="brand-tagline">Leak Detection System</p>'
        '<div class="divider"></div>'
        '<p class="form-section-label">Authorised Access</p>',
        unsafe_allow_html=True,
    )

    # ── Login form ──────────────────────────
    with st.form("login_form", clear_on_submit=False):
        user_id  = st.text_input("User ID",  placeholder="e.g. THW-001")
        password = st.text_input("Password", placeholder="Enter your password",
                                 type="password")
        submitted = st.form_submit_button("Sign In →", use_container_width=True)

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
                    st.error("Account is inactive. Please contact your administrator.")
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
                        db_manager.update_last_login(user_id.strip())
                        st.session_state.authenticated = True
                        st.session_state.user_id       = user["user_id"]
                        st.session_state.user_email    = user["email"]
                        st.session_state.user_name     = user["name"]
                        st.session_state.user_role     = user["role"]
                        st.success(f"Welcome back, {user['name']}.")
                        time.sleep(1)
                        st.rerun()
                    else:
                        st.error("Invalid User ID or password.")

    # System status + footer
    st.markdown(
        '<div class="system-status">'
        '  <div class="pulse-dot"></div>'
        '  All systems operational'
        '</div>'
        '<p class="login-footer">© THIWASCO &nbsp;·&nbsp; Authorised personnel only</p>',
        unsafe_allow_html=True,
    )

    # ── Glass card (close) ──────────────────
    st.markdown("</div>", unsafe_allow_html=True)