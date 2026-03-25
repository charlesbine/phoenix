"""FastAPI dashboard — JSON API + static SPA frontend."""

import asyncio
import humanize
from datetime import datetime
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from phoenix.paths import APPS_DIR, DATA_DIR, OUTPUTS_DIR, TEMPLATES_DIR, ensure_dirs
from phoenix.service import PhoenixService


def create_app() -> FastAPI:
    app = FastAPI(title="Phoenix Dashboard")
    ensure_dirs()

    # Serve rendered app images
    OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
    app.mount("/static/outputs", StaticFiles(directory=str(OUTPUTS_DIR)), name="outputs")

    # Serve preprocessor data files
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    app.mount("/data", StaticFiles(directory=str(DATA_DIR)), name="data")

    def get_svc() -> PhoenixService:
        return PhoenixService()

    def _serialize_app(a):
        return {
            "name": a.name,
            "enabled": a.enabled,
            "active": a.active,
            "refresh_interval": a.refresh_interval.total_seconds(),
            "last_updated": a.last_updated.isoformat() if a.last_updated else None,
            "last_updated_human": humanize.naturaltime(datetime.now() - a.last_updated) if a.last_updated else "never",
            "priority": a.priority,
        }

    # -- SPA entry point --

    @app.get("/", response_class=HTMLResponse)
    async def index():
        return FileResponse(TEMPLATES_DIR / "dashboard.html")

    # -- JSON API --

    @app.get("/api/apps")
    async def list_apps():
        svc = get_svc()
        apps = svc.list_apps()
        return [_serialize_app(a) for a in apps]

    @app.get("/api/apps/available")
    async def available_apps():
        svc = get_svc()
        known = {a.name for a in svc.list_apps()}
        return sorted(p.stem for p in APPS_DIR.glob("*.star") if p.stem not in known)

    @app.get("/api/apps/{name}")
    async def get_app(name: str):
        return _serialize_app(get_svc().get_app(name))

    @app.post("/api/apps/{name}/enable")
    async def enable_app(name: str):
        return _serialize_app(get_svc().enable_app(name))

    @app.post("/api/apps/{name}/disable")
    async def disable_app(name: str):
        return _serialize_app(get_svc().disable_app(name))

    @app.post("/api/apps/{name}/activate")
    async def activate_app(name: str):
        return _serialize_app(get_svc().set_active(name, True))

    @app.post("/api/apps/{name}/deactivate")
    async def deactivate_app(name: str):
        return _serialize_app(get_svc().set_active(name, False))

    @app.post("/api/apps/{name}/add")
    async def add_app(name: str):
        return _serialize_app(get_svc().create_app(name))

    @app.post("/api/apps/{name}/render")
    async def render_app(name: str):
        try:
            await asyncio.to_thread(get_svc().render_app, name)
            return _serialize_app(get_svc().get_app(name))
        except Exception as e:
            return {"error": str(e)}

    @app.get("/api/config")
    async def get_config():
        cfg = get_svc().get_display_config()
        return {"layout_mode": cfg.layout_mode, "cycle_interval": cfg.cycle_interval}

    @app.put("/api/config")
    async def update_config(request: Request):
        body = await request.json()
        cfg = get_svc().update_display_config(**body)
        return {"layout_mode": cfg.layout_mode, "cycle_interval": cfg.cycle_interval}

    return app
