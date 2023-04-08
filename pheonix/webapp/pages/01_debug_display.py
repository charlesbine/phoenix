import base64
from pathlib import Path

import pandas as pd
import pydantic

pydantic.class_validators._FUNCS.clear()  # ignore
import streamlit as st


from pheonix.display import DisplayManager


def main():
    st.title("Phoenix Debug Display")
    placeholder = st.empty()  # placeholder for image
    dm = DisplayManager(debug_display_element=placeholder)
    assert dm.debug

    dm.run_display()


if __name__ == "__main__":
    main()
