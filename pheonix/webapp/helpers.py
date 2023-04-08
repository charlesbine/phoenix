from pathlib import Path
import base64

import streamlit as st


def display_animated_image(path: Path, element: st.empty = None):
    contents = path.read_bytes()
    data_url = base64.b64encode(contents).decode("utf-8")

    if element is None:
        element = st

    element.markdown(
        f'<img src="data:image/webp;base64,{data_url}">',
        unsafe_allow_html=True,
    )
