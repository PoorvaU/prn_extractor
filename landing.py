

import streamlit as st
import pg1
import pg22
import pg44
import pg3
import pg5

# Set the page configuration
st.set_page_config(
    page_title="Landing Page",
    layout="centered",
    initial_sidebar_state="expanded",
)

# CSS for better styling
st.markdown("""
    <style>
    .main {
        background-color: #f5f5f5;
        padding: 20px;
        border-radius: 10px;
    }
    .sidebar .sidebar-content {
        background-image: linear-gradient(#2e7bcf,#2e7bcf);
        color: white;
    }
    .stButton button {
        background-color: #4CAF50;
        color: white;
        border: none;
        padding: 10px 24px;
        text-align: center;
        text-decoration: none;
        display: inline-block;
        font-size: 16px;
        margin: 4px 2px;
        transition-duration: 0.4s;
        cursor: pointer;
    }
    .stButton button:hover {
        background-color: white;
        color: black;
        border: 2px solid #4CAF50;
    }
    </style>
    """, unsafe_allow_html=True)

# Title and introduction
st.title("PRN Extractor")
st.write("Select a tab below.")

tab_labels = [
    "🏠",
    "⚡️",
    "⚖️",
    "⬇️",
    "🥈",
    "📄"
]

# Tab interface with symbols
tabs = st.tabs(tab_labels)

with tabs[0]:
    st.write("This is the home tab. Select another tab to run a script.")

with tabs[1]:
    pg1.main()

with tabs[5]:
    pg22.main()

with tabs[2]:
    pg3.main()

with tabs[3]:
    pg44.main()

with tabs[4]:
    pg5.main()
