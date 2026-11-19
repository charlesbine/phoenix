"""Push a paired serial display's playback state from the dashboard to its local USB player."""

import hashlib
import logging
import re
import ssl
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event, Thread
from typing import Literal

import httpx
from pydantic import BaseModel, Field

from phoenix.db import AppDatabase, DeviceDatabase
from phoenix.models import (
    AppConfig, BrightnessSchedule, DisplaySettings, brightness_schedule_for, display_settings_from_json,
)
from phoenix.paths import output_path, show_now_file
from phoenix.settings import Settings

NODE_PATH = "/api/display-node"
MAX_FRAME_BYTES = 32 * 1024 * 1024
logger = logging.getLogger(__name__)


class NodeCommand(BaseModel):
    name: str
    revision: int


class NodeState(BaseModel):
    layout_mode: Literal["cycle", "random", "single"]
    cycle_interval: int = Field(gt=0)
    brightness: int = Field(ge=0, le=255)
    enabled: bool
    brightness_schedule: BrightnessSchedule | None
    display_settings: DisplaySettings | None = None
    apps: list[AppConfig]
    frames: dict[str, str]
    show_now: NodeCommand | None = None
    single_app: str | None = None

    def payload(self) -> str:
        # Keep the unpinned revision compatible with older peers.
        return self.model_dump_json(exclude={"single_app"} if self.single_app is None else None)

    def revision(self) -> str:
        return hashlib.sha256(self.payload().encode()).hexdigest()


class NodeStatus(BaseModel):
    revision: str | None = None
    now_playing: str | None = None
    frames: dict[str, str] = Field(default_factory=dict)


def valid_name(name: str) -> bool:
    return re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_-]{0,127}", name) is not None


def frame_version(path: Path) -> str | None:
    try:
        stat = path.stat()
    except FileNotFoundError:
        return None
    return f"{stat.st_mtime_ns:x}-{stat.st_size:x}" if 0 < stat.st_size <= MAX_FRAME_BYTES else None


def read_node_token(settings: Settings) -> str:
    if not settings.node_token_file:
        raise ValueError("Display node token file is required")
    token = Path(settings.node_token_file).read_text().strip()
    if len(token) < 32:
        raise ValueError("Display node token must be at least 32 characters")
    return token


def read_text(path: Path) -> str:
    try:
        return path.read_text().strip()
    except FileNotFoundError:
        return ""


def write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=path.parent) as temp:
        staged = Path(temp) / path.name
        staged.write_text(value)
        staged.replace(path)


def build_state(device_id: str) -> NodeState:
    devices = DeviceDatabase()
    device = devices.get(device_id)
    if device is None or device["backend"] != "serial":
        raise ValueError("Paired serial display does not exist")
    definitions = AppDatabase()
    apps = []
    frames = {}
    command = None
    requested = show_now_file(device_id)
    requested_name = read_text(requested)
    for member in devices.list_apps(device_id):
        name = member["app_name"]
        app = definitions.get(name)
        if app is None or not valid_name(name):
            continue
        apps.append(app.model_copy(update={
            "enabled": bool(member["enabled"]),
            "priority": member["priority"],
            "sort_order": member["sort_order"],
            "last_updated": None,
            "pixlet_config": app.pixlet_config if app.runtime.startswith("live_") else {},
        }))
        if member["enabled"] or name == requested_name:
            if version := frame_version(output_path(name)):
                frames[name] = version
        if name == requested_name and (name in frames or app.runtime.startswith("live_")):
            command = NodeCommand(name=name, revision=requested.stat().st_mtime_ns)

    return NodeState(
        layout_mode=device["layout_mode"], cycle_interval=device["cycle_interval"],
        brightness=device["brightness"], enabled=bool(device["enabled"]),
        brightness_schedule=brightness_schedule_for(device),
        display_settings=display_settings_from_json(device.get("display_settings")),
        apps=apps, frames=frames, show_now=command,
        single_app=device["single_app"],
    )


class NodePublisher:
    """Send controls on demand and refresh renders/status in the background."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.report: NodeStatus | None = None
        self.pending = True
        self._wake = Event()
        self._stop = Event()

    @property
    def sync_status(self) -> str:
        if self.report is None:
            return "offline"
        return "pending" if self.pending or self._wake.is_set() else "synced"

    def notify(self) -> None:
        self._wake.set()

    def start(self) -> None:
        Thread(target=self._run, daemon=True, name="phoenix-node-publisher").start()

    def stop(self) -> None:
        self._stop.set()
        self._wake.set()

    def sync_once(self, client: httpx.Client) -> None:
        response = client.get(f"{NODE_PATH}/status")
        response.raise_for_status()
        self.report = NodeStatus.model_validate(response.json())
        state = build_state(self.settings.node_device)
        self.pending = self.report.revision != state.revision() or any(
            self.report.frames.get(name) != version for name, version in state.frames.items()
        )
        if not self.pending:
            return

        for name, version in state.frames.items():
            if self.report.frames.get(name) == version:
                continue
            with output_path(name).open("rb") as artifact:
                response = client.put(f"{NODE_PATH}/frames/{name}", params={"version": version},
                                      content=artifact)
            response.raise_for_status()

        response = client.put(f"{NODE_PATH}/state", content=state.payload(),
                              headers={"Content-Type": "application/json"})
        response.raise_for_status()
        self.report = NodeStatus.model_validate(response.json())
        self.pending = self.report.revision != state.revision()

    def _run(self) -> None:
        if not self.settings.node_url.startswith("https://") or not self.settings.node_ca_file:
            logger.error("Display node publishing requires an HTTPS origin and trusted certificate file")
            return
        context = ssl.create_default_context(cafile=self.settings.node_ca_file)
        headers = {"Authorization": f"Bearer {read_node_token(self.settings)}"}
        with httpx.Client(base_url=self.settings.node_url, headers=headers, timeout=4,
                          verify=context, trust_env=False) as client:
            failed = False
            while not self._stop.is_set():
                self._wake.clear()
                try:
                    self.sync_once(client)
                    if failed:
                        logger.info("Display node reconnected")
                    failed = False
                except (httpx.HTTPError, OSError, ValueError) as exc:
                    if not failed:
                        logger.warning("Display node sync failed: %s", exc)
                    failed = True
                    self.report = None
                    self.pending = True
                self._wake.wait(2 if not failed else 4)
