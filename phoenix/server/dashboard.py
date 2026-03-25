"""FastAPI dashboard — REST API + Jinja2/HTMX server-rendered pages."""

import humanize
from datetime import datetime
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from phoenix.paths import DATA_DIR, OUTPUTS_DIR, TEMPLATES_DIR, ensure_dirs
from phoenix.service import PhoenixService


def create_app() -> FastAPI:
    app = FastAPI(title="Phoenix Dashboard")
    ensure_dirs()

    templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
    templates.env.filters["humanize_time"] = _humanize_time

    # Serve rendered app images as static files
    OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
    app.mount("/static/outputs", StaticFiles(directory=str(OUTPUTS_DIR)), name="outputs")

    # Serve preprocessor data files (replaces standalone data server)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    app.mount("/data", StaticFiles(directory=str(DATA_DIR)), name="data")

    def get_svc() -> PhoenixService:
        return PhoenixService()

    # -- HTML Pages --

    @app.get("/", response_class=HTMLResponse)
    async def dashboard_page(request: Request):
        svc = get_svc()
        apps = svc.list_apps()
        config = svc.get_display_config()

        active = [a for a in apps if a.enabled and a.active]
        enabled = [a for a in apps if a.enabled and not a.active]
        disabled = [a for a in apps if not a.enabled]

        return templates.TemplateResponse("dashboard.html", {
            "request": request,
            "active_apps": active,
            "enabled_apps": enabled,
            "disabled_apps": disabled,
            "config": config,
            "now": datetime.now(),
        })

    # -- API Endpoints --

    @app.get("/api/apps")
    async def list_apps():
        return get_svc().list_apps()

    @app.get("/api/apps/{name}")
    async def get_app(name: str):
        return get_svc().get_app(name)

    @app.post("/api/apps/{name}/enable")
    async def enable_app(name: str):
        get_svc().enable_app(name)
        return RedirectResponse("/", status_code=303)

    @app.post("/api/apps/{name}/disable")
    async def disable_app(name: str):
        get_svc().disable_app(name)
        return RedirectResponse("/", status_code=303)

    @app.post("/api/apps/{name}/activate")
    async def activate_app(name: str):
        get_svc().set_active(name, True)
        return RedirectResponse("/", status_code=303)

    @app.post("/api/apps/{name}/deactivate")
    async def deactivate_app(name: str):
        get_svc().set_active(name, False)
        return RedirectResponse("/", status_code=303)

    @app.post("/api/apps/{name}/render")
    async def render_app(name: str):
        try:
            get_svc().render_app(name)
            return RedirectResponse("/", status_code=303)
        except Exception as e:
            return {"error": str(e)}

    @app.get("/api/config")
    async def get_config():
        return get_svc().get_display_config()

    @app.put("/api/config")
    async def update_config(request: Request):
        body = await request.json()
        return get_svc().update_display_config(**body)

    @app.post("/api/config")
    async def update_config_form(request: Request):
        form = await request.form()
        updates = {}
        if "layout_mode" in form:
            updates["layout_mode"] = form["layout_mode"]
        if "cycle_interval" in form:
            updates["cycle_interval"] = int(form["cycle_interval"])
        get_svc().update_display_config(**updates)
        return RedirectResponse("/", status_code=303)

    return app


def _humanize_time(dt: datetime | None) -> str:
    if dt is None:
        return "never"
    return humanize.naturaltime(datetime.now() - dt)
