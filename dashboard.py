import base64
from pathlib import Path

import pandas as pd
import pydantic

pydantic.class_validators._FUNCS.clear()  # ignore
import streamlit as st


from app_db import get_app_by_name, read_all_apps, upsert, AppConfig
from render import run_app


st.set_page_config(page_title="Pheonix Dashboard", page_icon="icon.png")


def main():
    st.title("Phoenix Dashboard")
    st.header("Apps")

    apps = read_all_apps()
    st.subheader("Active Apps")
    for app in [app for app in apps if app.enabled and app.active]:
        display_app_details(app)

    st.subheader("Enabled Apps")
    for app in [app for app in apps if app.enabled and not app.active]:
        display_app_details(app)

    st.subheader("Disabled Apps")
    for app in [app for app in apps if not app.enabled]:
        display_app_details(app)

    st.header("App data")
    df = apps_to_frame(apps)
    st.table(df)


def apps_to_frame(apps: list[AppConfig]) -> pd.DataFrame:
    df = pd.DataFrame([app.dict() for app in apps])
    df.refresh_interval = df.refresh_interval.apply(lambda x: x.total_seconds()).astype(
        "int"
    )
    df["age"] = (
        (pd.Timestamp.now() - df.last_updated)
        .apply(lambda x: x.total_seconds())
        .astype("int")
    )
    return df


def display_app_details(app: AppConfig):
    st.markdown(f"### {app.name}")
    display_animated_image(app.output_filename_large)
    st.markdown(f"Last updated: {app.last_updated}")

    # enable / disable button
    if not app.enabled:
        if st.button(f"Enable {app.name}"):
            upsert(app.name, enabled=True)
            st.experimental_rerun()

    if app.enabled:
        if st.button(f"Disable {app.name}"):
            upsert(app.name, enabled=False)
            st.experimental_rerun()

        # render button if enabled
        if st.button(f"Render {app.name}"):
            run_app(app.name)
            st.experimental_rerun()


def display_animated_image(path: Path, element: st.empty = None):
    contents = path.read_bytes()
    data_url = base64.b64encode(contents).decode("utf-8")

    if element is None:
        element = st

    element.markdown(
        f'<img src="data:image/webp;base64,{data_url}">',
        unsafe_allow_html=True,
    )


if __name__ == "__main__":
    main()
