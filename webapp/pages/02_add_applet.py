from pathlib import Path

import pandas as pd
import pydantic
import shutil


pydantic.class_validators._FUNCS.clear()  # ignore
import streamlit as st


from app_db import get_app_by_name, read_all_apps, upsert, AppConfig
from render import run_app
from utils import get_downloaded_app_names, apps_dir
from shop import get_community_repo, get_all_community_app_names, get_community_app_starlark_path, get_community_app_manifest

st.set_page_config(page_title="Pheonix Dashboard", page_icon="icon.png")

st.title("Add a new applet")


def main():
    if st.button("Pull community apps from github"):
        get_community_repo()
    
    available_app_names = get_all_community_app_names()
    app_name = st.selectbox("Applet name", available_app_names)
    app_community_path = get_community_app_starlark_path(app_name)
    app_manifest = get_community_app_manifest(app_name)

    st.table(pd.DataFrame([app_manifest]).set_index("id").T)

    if app_community_path.stem in get_downloaded_app_names():
        st.warning(f"Applet {app_name} already exists.")
        st.stop()
        # TODO: implement update

    if st.button("Import applet"):
        status = st.empty()
        status.info(f"Importing applet {app_name}")
        shutil.copyfile(app_community_path, apps_dir() / app_community_path.name)
        status.success(f"Applet {app_name} imported")


if __name__ == "__main__":
    main()