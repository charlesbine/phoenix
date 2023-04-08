import humanize
import pandas as pd
import pydantic

pydantic.class_validators._FUNCS.clear()  # ignore
import streamlit as st


from pheonix.app_db import get_app_by_name, read_all_apps, upsert, AppConfig
from pheonix.render import run_app
from pheonix.config import Config, get_config, set_config
from pheonix.webapp.helpers import display_animated_image


DEBUG = False

st.set_page_config(page_title="Pheonix Dashboard", page_icon="icon.png")


def main():
    st.title("Phoenix Dashboard")
    st.header("Config")
    config = get_config()
    st.markdown("Use this section to control how the apps will show up")

    if DEBUG:
        st.json(config.dict())

    layout_mode = st.selectbox(
        "Layout mode",
        options=Config.SUPPORTED_LAYOUT_MODES,
        index=Config.SUPPORTED_LAYOUT_MODES.index(config.layout_mode),
    )
    if layout_mode != config.layout_mode:
        config.layout_mode = layout_mode
        set_config(config)

    cycle_interval = st.slider(
        "Duration of each face",
        value=config.cycle_interval,
        min_value=1,
        max_value=100,
        step=1,
    )
    if cycle_interval != config.cycle_interval:
        config.cycle_interval = cycle_interval
        set_config(config)

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
    st.dataframe(df)


def apps_to_frame(apps: list[AppConfig]) -> pd.DataFrame:
    df = pd.DataFrame([app.dict() for app in apps])
    df.refresh_interval = df.refresh_interval.apply(lambda x: x.total_seconds()).astype(
        "int"
    )
    df["age"] = (
        (pd.Timestamp.now() - df.last_updated)
        .apply(lambda x: x.total_seconds())
        .round(0)
    )
    styled = df.style.format("{:.0f}", subset=["age"])
    return styled


def display_app_details(app: AppConfig):
    st.markdown(f"### {app.name}")
    if app.output_filename_large.is_file():
        display_animated_image(app.output_filename_large)
    else:
        st.error(
            f"No output file found for app {app.name} under {app.output_filename_large}"
        )

    st.markdown(f"Last updated: {humanize.naturaltime(app.last_updated)}")

    # enable / disable button
    if not app.enabled:
        if st.button(f"Enable {app.name}"):
            upsert(app.name, enabled=True)
            st.experimental_rerun()

    if app.enabled:
        if st.button(f"Disable {app.name}"):
            upsert(app.name, enabled=False)
            st.experimental_rerun()

        if not app.active:
            if st.button(f"Add to cycle {app.name}"):
                upsert(app.name, active=True)
                st.experimental_rerun()
        else:
            if st.button(f"Remove from cycle {app.name}"):
                upsert(app.name, active=False)
                st.experimental_rerun()

        # render button if enabled
        if st.button(f"Render {app.name}"):
            run_app(app.name)
            st.experimental_rerun()

    if st.checkbox(f"Show config for {app.name}"):
        st.json(app.dict())


if __name__ == "__main__":
    main()
