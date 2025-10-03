from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import RedirectResponse, JSONResponse
import requests, secrets
from utils.google_oauth import get_google_flow
from utils.session_store import put, get as get_session
from config import settings

router = APIRouter(prefix="/auth", tags=["auth"])

@router.get("/login")
def login():
    # Create a CSRF state you control (not Google's state yet)
    server_state = secrets.token_urlsafe(24)
    flow = get_google_flow(state=server_state)
    auth_url, google_state = flow.authorization_url(
        prompt="consent",
        access_type="offline",
        include_granted_scopes="true",
    )
    # We use *your* state. Google will echo it back.
    # You can pre-store server_state if you want CSRF validation before token exchange.
    put(server_state, {"preauth": True})
    return {"auth_url": auth_url, "state": server_state}

@router.get("/callback")
def callback(request: Request):
    state = request.query_params.get("state")
    code = request.query_params.get("code")
    if not state or not code:
        raise HTTPException(status_code=400, detail="Missing state or code")

    if not get_session(state):
        # Optional: harden CSRF check (state should exist from /login)
        raise HTTPException(status_code=400, detail="Invalid state")

    flow = get_google_flow(state=state)
    flow.fetch_token(code=code)
    creds = flow.credentials

    user_info = requests.get(
        "https://www.googleapis.com/oauth2/v3/userinfo",
        headers={"Authorization": f"Bearer {creds.token}"}
    ).json()

    # Save a compact session (avoid sending tokens to the frontend)
    put(state, {
        "user": user_info,
        "tokens": {
            "access_token": creds.token,
            "id_token": creds.id_token,
            "refresh_token": creds.refresh_token,
            "expiry": creds.expiry.isoformat() if creds.expiry else None,
        }
    })

    # <-- IMPORTANT: Redirect the browser to Streamlit, not JSON
    return RedirectResponse(url=f"{settings.FRONTEND_URL}?session={state}", status_code=302)

@router.get("/sessions/{session_id}")
def read_session(session_id: str):
    data = get_session(session_id)
    if not data:
        raise HTTPException(status_code=404, detail="Session not found or expired")
    # Return only what the client needs
    return JSONResponse({"user": data["user"]})
