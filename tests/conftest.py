import pytest
import streamlit as st


@pytest.fixture(autouse=True)
def clear_streamlit_resources():
    st.cache_resource.clear()
    yield
    st.cache_resource.clear()
