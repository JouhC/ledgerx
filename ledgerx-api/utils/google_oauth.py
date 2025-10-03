from google_auth_oauthlib.flow import Flow
from core.config import settings

SCOPES = [
    "openid",
    "https://www.googleapis.com/auth/userinfo.profile",
    "https://www.googleapis.com/auth/userinfo.email",
]

def get_google_flow(state=None):
    client_config = settings.google_client_config
    flow = Flow.from_client_config(
        client_config,
        scopes=SCOPES,
        state=state,
        redirect_uri=client_config["web"]["redirect_uris"][1],
    )
    return flow
