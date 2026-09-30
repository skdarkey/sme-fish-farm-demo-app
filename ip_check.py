import streamlit as st
import requests

try:
    # Query an external service to find the app's current outbound IP
    outbound_ip = requests.get('https://sme-fishfarmdemo.streamlit.app/').text
    st.write(f"**Current Outbound IP Address:** `{outbound_ip}`")
except Exception as e:
    st.error(f"Could not retrieve outbound IP: {e}")