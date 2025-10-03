import streamlit as st
import requests

API_URL = "http://localhost:8000/auth"

if st.button("Login with Google"):
    r = requests.get(f"{API_URL}/login").json()
    st.query_params.clear()  # clear old params
    st.markdown(
        f'<meta http-equiv="refresh" content="0; url={r["auth_url"]}">',
        unsafe_allow_html=True,
    )

# After redirect from Google (via FastAPI callback)
params = st.query_params
if "code" in params and "state" in params:
    code = params["code"]
    state = params["state"]
    r = requests.get(f"{API_URL}/callback?code={code}&state={state}")
    st.json(r.json())
