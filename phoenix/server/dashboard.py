"""FastAPI dashboard — JSON API + static SPA frontend."""

import asyncio
import humanize
from datetime import datetime
from urllib.parse import unquote

from fastapi import FastAPI, Query, Request
from fastapi.responses import FileResponse, HTMLResponse, Response
from fastapi.staticfiles import StaticFiles

from phoenix.cache import cache_get
from phoenix.db import PanelDatabase
from phoenix.mqtt import get_mqtt_client, list_notifications, push_notification, get_message
from phoenix.paths import APPS_DIR, DATA_DIR, OUTPUTS_DIR, TEMPLATES_DIR, app_type, ensure_dirs
from phoenix.schema_parser import parse_schema
from phoenix.service import PhoenixService
from phoenix.settings import get_settings


def create_app() -> FastAPI:
    app = FastAPI(title="Phoenix Dashboard")
    ensure_dirs()

    # Start MQTT client
    settings = get_settings()
    mqtt_client = get_mqtt_client(settings)
    mqtt_client.start()

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
            "sort_order": a.sort_order,
            "pixlet_config": a.pixlet_config,
            "app_type": app_type(a.name),
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
        # Find all app files: .star, .py, .webp, .gif, .png
        names = set()
        for ext in ("*.star", "*.py", "*.webp", "*.gif", "*.png", "*.apng"):
            for p in APPS_DIR.glob(ext):
                if p.stem not in known and not p.stem.startswith("__"):
                    names.add(p.stem)
        return sorted(names)

    @app.post("/api/preview-all")
    async def preview_all_apps():
        """Preview all available (unregistered) applets."""
        svc = get_svc()
        known = {a.name for a in svc.list_apps()}
        names = set()
        for ext in ("*.star", "*.py", "*.webp", "*.gif", "*.png", "*.apng"):
            for p in APPS_DIR.glob(ext):
                if p.stem not in known and not p.stem.startswith("__"):
                    names.add(p.stem)
        available = sorted(names)
        results = []
        for name in available:
            try:
                await asyncio.to_thread(svc.render_preview, name)
                results.append({"name": name, "preview": True})
            except Exception as e:
                results.append({"name": name, "error": str(e)})
        return results

    @app.put("/api/reorder")
    async def reorder_apps(request: Request):
        """Set sort_order for active apps. Body: {"order": ["app1", "app2", ...]}"""
        body = await request.json()
        names = body.get("order", [])
        svc = get_svc()
        for i, name in enumerate(names):
            svc.app_db.upsert(name, sort_order=i)
        return {"ok": True}

    @app.get("/api/apps/{name}")
    async def get_app(name: str):
        return _serialize_app(get_svc().get_app(name))

    @app.get("/api/apps/{name}/schema")
    async def get_app_schema(name: str):
        from phoenix.paths import star_path
        path = star_path(name)
        if not path.exists():
            return []
        return parse_schema(path) or []

    @app.delete("/api/apps/{name}")
    async def delete_app(name: str):
        get_svc().app_db.delete(name)
        return {"ok": True}

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

    @app.put("/api/apps/{name}/priority")
    async def update_priority(name: str, request: Request):
        body = await request.json()
        priority = body.get("priority")
        if priority is not None:
            return _serialize_app(get_svc().app_db.upsert(name, priority=int(priority)))
        return {"error": "missing priority"}

    @app.put("/api/apps/{name}/refresh-interval")
    async def update_refresh_interval(name: str, request: Request):
        body = await request.json()
        seconds = body.get("refresh_interval")
        if seconds is not None:
            from datetime import timedelta
            return _serialize_app(get_svc().app_db.upsert(name, refresh_interval=timedelta(seconds=float(seconds))))
        return {"error": "missing refresh_interval"}

    @app.put("/api/apps/{name}/config")
    async def update_app_config(name: str, request: Request):
        body = await request.json()
        svc = get_svc()
        return _serialize_app(svc.app_db.upsert(name, pixlet_config=body))

    @app.post("/api/apps/{name}/render")
    async def render_app(name: str):
        try:
            svc = get_svc()
            app_obj = svc.app_db.get(name)
            if app_obj and not app_obj.enabled:
                # Disabled apps use preview path (render_app skips disabled)
                await asyncio.to_thread(svc.render_preview, name)
            else:
                await asyncio.to_thread(svc.render_app, name)
            fresh = svc.app_db.get(name)
            return _serialize_app(fresh) if fresh else {"ok": True}
        except Exception as e:
            return {"error": str(e)}

    @app.post("/api/apps/{name}/preview")
    async def preview_app(name: str):
        """Render a preview for any app (even if not in DB or disabled)."""
        try:
            await asyncio.to_thread(get_svc().render_preview, name)
            return {"name": name, "preview": True}
        except Exception as e:
            return {"error": str(e)}

    # -- Dashboard panels --

    def get_panel_db() -> PanelDatabase:
        return PanelDatabase()

    @app.get("/api/panels")
    async def list_panels():
        return get_panel_db().list_panels()

    @app.post("/api/panels")
    async def create_panel(request: Request):
        body = await request.json()
        panel_id = body.get("id", "").strip().lower().replace(" ", "_")
        if not panel_id:
            return {"error": "id is required"}
        panel_db = get_panel_db()
        if panel_db.get(panel_id):
            return {"error": f"Panel '{panel_id}' already exists"}

        panel = panel_db.create(
            panel_id=panel_id,
            layout=body.get("layout", "big_number"),
            title=body.get("title", ""),
            config=body.get("config", {}),
            data_source=body.get("data_source", {}),
        )

        # Register as an app so it appears in the display cycle
        svc = get_svc()
        app_name = f"panel_{panel_id}"
        try:
            svc.create_app(app_name, pixlet_config={"instance_id": panel_id})
        except ValueError:
            pass  # Already exists

        # Render initial preview
        try:
            await asyncio.to_thread(svc.render_preview, app_name)
        except Exception:
            pass

        return panel

    @app.post("/api/panels/preview")
    async def preview_panel(request: Request):
        """Render a preview of a panel config without saving it."""
        import json as json_mod
        from phoenix.paths import data_path, star_path, output_path_large
        from phoenix.render import _run_pixlet
        from phoenix.models import AppConfig
        from phoenix.paths import ensure_dirs as _ensure

        _ensure()
        body = await request.json()
        preview_id = "_preview"

        # Build panel data from the request body (same as preprocessor would)
        from phoenix.preprocessors.dashboard_panel import _build_panel_data, _fetch_http_source
        panel = {
            "layout": body.get("layout", "big_number"),
            "title": body.get("title", ""),
            "config": body.get("config", {}),
            "data_source": body.get("data_source", {}),
        }
        source = panel["data_source"]
        fetched = {}
        if source.get("type") == "http" and source.get("url"):
            try:
                fetched = _fetch_http_source(source)
            except Exception:
                pass
        panel_data = _build_panel_data(panel, fetched)
        data_path(f"dashboard_panel_{preview_id}").write_text(json_mod.dumps(panel_data))

        # Render
        try:
            app = AppConfig(name=f"panel_{preview_id}", pixlet_config={"instance_id": preview_id})
            await asyncio.to_thread(_run_pixlet, app, get_svc().settings, True, star_path("dashboard_panel"))
            return {"preview_url": f"/static/outputs/panel_{preview_id}.large.webp?t={__import__('time').time()}"}
        except Exception as e:
            return {"error": str(e)}

    @app.get("/api/panels/{panel_id}")
    async def get_panel(panel_id: str):
        panel = get_panel_db().get(panel_id)
        if panel is None:
            return {"error": "not found"}
        return panel

    @app.put("/api/panels/{panel_id}")
    async def update_panel(panel_id: str, request: Request):
        body = await request.json()
        panel_db = get_panel_db()
        try:
            panel = panel_db.update(panel_id, **body)
        except ValueError as e:
            return {"error": str(e)}

        # Re-render
        svc = get_svc()
        app_name = f"panel_{panel_id}"
        try:
            await asyncio.to_thread(svc.render_preview, app_name)
        except Exception:
            pass

        return panel

    @app.delete("/api/panels/{panel_id}")
    async def delete_panel(panel_id: str):
        panel_db = get_panel_db()
        panel_db.delete(panel_id)
        # Also remove the app
        svc = get_svc()
        try:
            svc.app_db.delete(f"panel_{panel_id}")
        except Exception:
            pass
        return {"ok": True}

    # -- Notifications & MQTT --

    @app.post("/api/notify")
    async def send_notification(request: Request):
        """Send a notification to the display."""
        body = await request.json()
        text = body.get("text", "")
        if not text:
            return {"error": "text is required"}
        push_notification(
            text=text,
            color=body.get("color", "#FFFFFF"),
            duration=body.get("duration", 10),
            layout=body.get("layout", "marquee"),
        )
        return {"ok": True}

    @app.get("/api/notifications")
    async def get_notifications():
        return list_notifications()

    @app.get("/api/mqtt/status")
    async def mqtt_status():
        return {
            "connected": mqtt_client.connected,
            "broker": settings.mqtt_broker or None,
            "notify_topic": settings.mqtt_notify_topic,
        }

    @app.get("/api/mqtt/messages/{topic:path}")
    async def get_mqtt_message(topic: str):
        msg = get_message(topic)
        if msg is None:
            return {"error": "no message for topic"}
        return msg

    @app.get("/api/now-playing")
    async def now_playing():
        txt = DATA_DIR / "output" / "current_app.txt"
        if txt.exists():
            return {"app": txt.read_text().strip()}
        return {"app": None}

    # -- Cache proxy --

    @app.get("/proxy")
    async def proxy(
        url: str = Query(..., description="URL to fetch"),
        ttl: int = Query(300, description="Cache TTL in seconds"),
    ):
        url = unquote(url)
        try:
            status_code, body, content_type = cache_get(url, ttl)
            return Response(content=body, status_code=status_code, media_type=content_type)
        except Exception as e:
            return Response(content=str(e).encode(), status_code=502)

    @app.get("/api/cache/stats")
    async def cache_stats():
        from phoenix.cache import _connect
        import time
        with _connect() as conn:
            rows = conn.execute(
                "SELECT url, fetched_at, ttl, length(body) as size FROM http_cache ORDER BY fetched_at DESC"
            ).fetchall()
            now = time.time()
            return [
                {
                    "url": r["url"],
                    "age_seconds": round(now - r["fetched_at"]),
                    "ttl": r["ttl"],
                    "fresh": (now - r["fetched_at"]) < r["ttl"],
                    "size_bytes": r["size"],
                }
                for r in rows
            ]

    # -- Config --

    @app.get("/api/config")
    async def get_config():
        cfg = get_svc().get_display_config()
        return {"layout_mode": cfg.layout_mode, "cycle_interval": cfg.cycle_interval, "brightness": cfg.brightness}

    @app.put("/api/config")
    async def update_config(request: Request):
        body = await request.json()
        cfg = get_svc().update_display_config(**body)
        return {"layout_mode": cfg.layout_mode, "cycle_interval": cfg.cycle_interval, "brightness": cfg.brightness}

    return app
