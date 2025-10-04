import streamlit as st
import requests

API = "http://localhost:8000"

st.title("Login Demo")

if st.button("Login with Google"):
    r = requests.get(f"{API}/auth/login").json()
    st.query_params.clear()
    st.markdown(
        f'<meta http-equiv="refresh" content="0; url={r["auth_url"]}">',
        unsafe_allow_html=True,
    )

params = st.query_params
if "session" in params:
    sid = params["session"]
    try:
        data = requests.get(f"{API}/auth/sessions/{sid}", timeout=10).json()
        st.success("Logged in!")
        st.json(data["user"])
    except Exception as e:
        st.error(f"Session fetch failed: {e}")
