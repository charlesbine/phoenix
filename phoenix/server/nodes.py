"""The paired Aurora player accepts playback state and 64×64 WebPs."""

import json
import re
import secrets
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from PIL import Image
from pydantic import ValidationError

from phoenix.db import DeviceDatabase
from phoenix.node import MAX_FRAME_BYTES, NODE_PATH, NodeState, NodeStatus, read_node_token, read_text, valid_name, write_text
from phoenix.paths import current_app_file, ensure_dirs, output_path, show_now_file
from phoenix.settings import Settings


MAX_ANIMATION_FRAMES = 4096


def create_receiver(settings: Settings, db: DeviceDatabase, wake: Event) -> FastAPI:
    device_id = settings.node_device
    if not valid_name(device_id) or not settings.node_peer:
        raise ValueError("The display receiver requires a paired device and controller address")
    ensure_dirs()
    expected = f"Bearer {read_node_token(settings)}".encode()
    now_playing = current_app_file(device_id)
    stamp = now_playing.with_name(f"pushed_state__{device_id}.json")
    versions = now_playing.with_name(f"pushed_frames__{device_id}.json")

    def authorize(request: Request, authorization: str = Header(default="")) -> None:
        if request.client is None or request.client.host != settings.node_peer:
            raise HTTPException(status_code=403, detail="Unrecognized display controller")
        if not secrets.compare_digest(authorization.encode(), expected):
            raise HTTPException(status_code=401, detail="Display-controller token required")

    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None, dependencies=[Depends(authorize)])

    def cached_state() -> NodeState | None:
        contents = read_text(stamp)
        return NodeState.model_validate_json(contents) if contents else None

    def cached_frames() -> dict[str, str]:
        return json.loads(read_text(versions) or "{}")

    def report(state: NodeState | None) -> NodeStatus:
        frames = cached_frames()
        return NodeStatus(revision=state.revision() if state else None, now_playing=read_text(now_playing) or None,
                          frames={name: version for name, version in frames.items() if output_path(name).is_file()})

    @app.get(f"{NODE_PATH}/status", response_model=NodeStatus)
    async def status():
        return report(cached_state())

    @app.put(f"{NODE_PATH}/frames/{{name}}")
    async def put_frame(name: str, version: str, request: Request):
        if not valid_name(name) or not re.fullmatch(r"[0-9a-f]{1,32}-[0-9a-f]{1,8}", version):
            raise HTTPException(status_code=400, detail="Invalid frame name or revision")
        expected_size = int(version.rsplit("-", 1)[1], 16)
        if not 12 <= expected_size <= MAX_FRAME_BYTES:
            raise HTTPException(status_code=413, detail="Display frame exceeds its size limit")
        target = output_path(name)
        with TemporaryDirectory(dir=target.parent) as temp:
            staged = Path(temp) / target.name
            size = 0
            with staged.open("wb") as output:
                async for block in request.stream():
                    size += len(block)
                    if size > expected_size:
                        raise HTTPException(status_code=413, detail="Display frame exceeds its expected size")
                    output.write(block)
            with staged.open("rb") as file:
                header = file.read(12)
            if (size != expected_size or header[:4] != b"RIFF" or header[8:] != b"WEBP"
                    or int.from_bytes(header[4:8], "little") + 8 != size):
                raise HTTPException(status_code=422, detail="Incomplete or invalid WebP")
            try:
                with Image.open(staged, formats=("WEBP",)) as image:
                    if image.size != (64, 64) or image.n_frames > MAX_ANIMATION_FRAMES:
                        raise ValueError("Expected a 64×64 WebP with at most 4096 frames")
            except (OSError, ValueError) as exc:
                raise HTTPException(status_code=422, detail="Invalid native display WebP") from exc
            staged.replace(target)
        frames = cached_frames()
        frames[name] = version
        write_text(versions, json.dumps(frames))
        return {"ok": True}

    @app.put(f"{NODE_PATH}/state", response_model=NodeStatus)
    async def put_state(request: Request):
        body = bytearray()
        async for block in request.stream():
            if len(body) + len(block) > 512 * 1024:
                raise HTTPException(status_code=413, detail="Playback state exceeds its size limit")
            body.extend(block)
        try:
            state = NodeState.model_validate_json(body)
        except ValidationError as exc:
            raise HTTPException(status_code=422, detail="Invalid playback state") from exc
        previous = cached_state()
        if previous and state.revision() == previous.revision():
            return report(previous)
        names = {app.name for app in state.apps}
        if (any(not valid_name(name) for name in names) or not state.frames.keys() <= names
                or (state.single_app is not None and not valid_name(state.single_app))
                or (state.show_now and state.show_now.name not in names)):
            raise HTTPException(status_code=400, detail="Invalid playback rotation")
        frames = cached_frames()
        if any(frames.get(name) != version or not output_path(name).is_file()
               for name, version in state.frames.items()):
            raise HTTPException(status_code=409, detail="Playback requires an uploaded frame")
        available = [app if app.runtime or app.name in state.frames
                     else app.model_copy(update={"active": False}) for app in state.apps]
        db.apply_node_rotation(device_id, state.model_dump(), state.brightness_schedule,
                               available, state.display_settings)
        if state.show_now and (not previous or state.show_now != previous.show_now):
            write_text(show_now_file(device_id), state.show_now.name)
        write_text(stamp, state.model_dump_json())
        fields = {"layout_mode", "cycle_interval", "enabled", "apps", "show_now", "single_app"}
        if (not previous or previous.model_dump(include=fields) != state.model_dump(include=fields)
                or previous.frames.keys() != state.frames.keys()):
            wake.set()
        return report(state)

    return app
