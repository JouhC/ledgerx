# utils/google_oauth.py
from __future__ import annotations
import requests
from typing import Dict, Tuple
import streamlit as st
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests
from google_auth_oauthlib.flow import Flow
from google.oauth2.credentials import Credentials
from config import settings

# ---- Load config from st.secrets ----
CLIENT_CONFIG = settings.GOOGLE_OAUTH
CONF = CLIENT_CONFIG.get("web", {})

# -------- Helpers (stateless) --------
def get_redirect_uri() -> str:
    """
    Return the base URL the app is served on.
    Prefer explicit redirect_uri in secrets to avoid mismatch issues.
    """
    return CONF.get("redirect_uri", "http://localhost:8501")


def build_flow(redirect_uri: str) -> Flow:
    """Create a Google OAuth flow instance."""
    return Flow.from_client_config(
        client_config=CLIENT_CONFIG,
        scopes=CONF.get("scopes", ["openid", "https://www.googleapis.com/auth/userinfo.profile", "https://www.googleapis.com/auth/userinfo.email"]),
        redirect_uri=redirect_uri,
    )


def get_auth_url() -> Tuple[str, str]:
    """
    Build the authorization URL and return (auth_url, state).
    Also stores 'state' in session for CSRF protection (done by caller).
    """
    flow = build_flow(get_redirect_uri())
    auth_url, state = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",  # helpful during testing
    )
    return auth_url, state


def exchange_code_for_tokens(query_params: Dict[str, list]) -> Tuple[dict, dict]:
    """
    Exchange ?code=... for tokens, verify ID token, and fetch OIDC userinfo.
    Returns (credentials_dict, user_profile_dict).
    Raises on failure.
    """
    redirect_uri = get_redirect_uri()
    flow = build_flow(redirect_uri)

    # Rebuild the current URL Google redirected to (must match exactly)
    pairs = []
    for k, v in query_params.items():
        for item in v:
            pairs.append(f"{k}={item}")
    current_url = f"{redirect_uri}?{'&'.join(pairs)}" if pairs else redirect_uri

    # Fetch tokens
    flow.fetch_token(authorization_response=current_url)
    creds = flow.credentials

    # Optional: verify ID token’s signature, exp, and audience
    idinfo = {}
    if creds.id_token:
        request = google_requests.Request()
        idinfo = id_token.verify_oauth2_token(
            creds.id_token, request, audience=CLIENT_CONFIG["web"]["client_id"]
        )

    # OIDC userinfo profile
    userinfo = _fetch_userinfo(creds.token)

    credentials = {
        "token": creds.token,
        "refresh_token": getattr(creds, "refresh_token", None),
        "id_token": getattr(creds, "id_token", None),
        "token_uri": creds.token_uri,
        "client_id": creds.client_id,
        "client_secret": CONF["client_secret"],
        "scopes": creds.scopes,
    }
    user = {
        "sub": idinfo.get("sub", userinfo.get("sub")),
        "email": userinfo.get("email"),
        "name": userinfo.get("name"),
        "picture": userinfo.get("picture"),
        "email_verified": userinfo.get("email_verified"),
    }
    return credentials, user


def _fetch_userinfo(access_token: str) -> dict:
    r = requests.get(
        "https://www.googleapis.com/oauth2/v3/userinfo",
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=10,
    )
    r.raise_for_status()
    return r.json()


# -------- Session utilities (stateful) --------
def is_signed_in() -> bool:
    return "credentials" in st.session_state and "user" in st.session_state


def start_login() -> None:
    """Start the OAuth flow and render the login button."""
    auth_url, state = get_auth_url()
    st.session_state["state"] = state
    st.write("Please sign in with your Google account to continue.")
    st.link_button("Sign in with Google", auth_url)


def complete_login(query_params: Dict[str, list]) -> None:
    """
    Handle the callback (with ?code & ?state), exchange token,
    and persist session. Displays errors inline on failure.
    """
    if "state" not in st.session_state:
        st.error("Missing login state. Please start again.")
        return

    if "state" not in query_params or "code" not in query_params:
        st.error("Invalid callback parameters.")
        return

    if query_params["state"][0] != st.session_state["state"]:
        st.error("State mismatch. Please try signing in again.")
        return

    try:
        creds, user = exchange_code_for_tokens(query_params)
        st.session_state["credentials"] = creds
        st.session_state["user"] = user
        # Clean URL
        st.experimental_set_query_params()
        st.rerun()
    except Exception as e:
        st.error(f"OAuth exchange failed: {e}")


def logout() -> None:
    for k in ["credentials", "user", "state"]:
        st.session_state.pop(k, None)
    st.experimental_set_query_params()
