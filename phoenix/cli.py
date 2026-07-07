"""Typer CLI — thin dispatch over the service layer."""

import logging
from typing import Annotated, Optional

import typer
from rich.console import Console
from rich.logging import RichHandler
from rich.table import Table

app = typer.Typer(name="phoenix", help="LED matrix display manager for Starlark applets.")
console = Console()


@app.callback()
def _setup(
    verbose: Annotated[bool, typer.Option("--verbose", "-v", help="Enable debug logging")] = False,
):
    """LED matrix display manager for Starlark applets."""
    level = logging.DEBUG if verbose else logging.INFO

    from phoenix.paths import PACKAGE_DIR
    log_dir = PACKAGE_DIR / "logs"
    log_dir.mkdir(exist_ok=True)

    # File handler — rotates daily, keeps 7 days
    from logging.handlers import TimedRotatingFileHandler
    file_handler = TimedRotatingFileHandler(
        log_dir / "phoenix.log",
        when="midnight",
        backupCount=7,
        encoding="utf-8",
    )
    file_handler.setFormatter(logging.Formatter(
        "%(asctime)s %(levelname)-8s [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    ))
    file_handler.setLevel(logging.DEBUG)

    logging.basicConfig(
        level=level,
        format="%(message)s",
        datefmt="[%X]",
        handlers=[
            RichHandler(rich_tracebacks=True, show_path=False),
            file_handler,
        ],
    )


def get_service():
    from phoenix.service import PhoenixService

    return PhoenixService()


@app.command()
def render(
    applet: Annotated[Optional[str], typer.Argument(help="Applet name to render once")] = None,
    list_apps: Annotated[bool, typer.Option("--list", "-l", help="List all applets")] = False,
):
    """Render applets. Without args, runs all in a continuous loop."""
    svc = get_service()

    if list_apps:
        apps = svc.list_apps()
        table = Table(title="Applets")
        table.add_column("Status", style="bold")
        table.add_column("Name", style="bold")
        table.add_column("Refresh")
        table.add_column("Priority", justify="right")

        for a in sorted(apps, key=lambda x: x.name):
            status = "[green]●[/]" if a.enabled else "[red]○[/]"
            name_style = "green" if a.enabled else "red"
            table.add_row(
                status,
                f"[{name_style}]{a.name}[/]",
                str(a.refresh_interval),
                str(a.priority),
            )

        console.print(table)
        enabled = sum(1 for a in apps if a.enabled)
        console.print(
            f"  [green]{enabled}[/] enabled, [red]{len(apps) - enabled}[/] disabled"
        )
        return

    if applet:
        try:
            svc.render_app(applet)
            console.print(f"[green]Rendered:[/] {applet}")
        except Exception as e:
            console.print(f"[red]Error:[/] {e}", style="bold red")
            raise typer.Exit(1)
    else:
        svc.render_all()


@app.command()
def enable(name: Annotated[str, typer.Argument(help="Applet name")]):
    """Enable an applet."""
    svc = get_service()
    svc.enable_app(name)
    console.print(f"[green]Enabled:[/] {name}")


@app.command()
def disable(name: Annotated[str, typer.Argument(help="Applet name")]):
    """Disable an applet."""
    svc = get_service()
    svc.disable_app(name)
    console.print(f"[red]Disabled:[/] {name}")


@app.command()
def new(
    name: Annotated[str, typer.Argument(help="Applet name")],
    enabled: Annotated[bool, typer.Option(help="Create as enabled")] = True,
    config: Annotated[Optional[list[str]], typer.Option("-c", help="Config key=value pairs")] = None,
):
    """Create a new applet entry."""
    svc = get_service()
    pixlet_config: dict[str, str] = {}
    for item in config or []:
        if "=" not in item:
            console.print(f"[yellow]Warning:[/] Ignoring '{item}' (expected key=value)")
            continue
        key, value = item.split("=", 1)
        pixlet_config[key.strip()] = value.strip()

    try:
        app_config = svc.create_app(name, enabled=enabled, pixlet_config=pixlet_config)
        console.print(f"[green]Created:[/] {app_config.name}")
        if pixlet_config:
            for k, v in pixlet_config.items():
                console.print(f"  {k}: {v}")
    except Exception as e:
        console.print(f"[red]Error:[/] {e}")
        raise typer.Exit(1)


@app.command("config")
def config_cmd(
    layout_mode: Annotated[Optional[str], typer.Option(help="Layout mode: cycle, single, random")] = None,
    cycle_interval: Annotated[Optional[int], typer.Option(help="Seconds between app switches")] = None,
):
    """View or update display configuration."""
    svc = get_service()

    if layout_mode is None and cycle_interval is None:
        cfg = svc.get_display_config()
        console.print(f"  layout_mode: [bold]{cfg.layout_mode}[/]")
        console.print(f"  cycle_interval: [bold]{cfg.cycle_interval}s[/]")
        return

    updates: dict[str, object] = {}
    if layout_mode is not None:
        updates["layout_mode"] = layout_mode
    if cycle_interval is not None:
        updates["cycle_interval"] = cycle_interval

    cfg = svc.update_display_config(**updates)
    console.print(f"[green]Updated:[/] {cfg.model_dump()}")


def _make_backend(backend_type: str, device_id: str | None = None):
    """Instantiate a display backend by name, bound to a device when given."""
    if backend_type == "matrix":
        from phoenix.display.matrix import MatrixDisplayBackend

        return MatrixDisplayBackend(device_id=device_id)
    elif backend_type == "serial":
        from phoenix.display.serial import SerialDisplayBackend

        return SerialDisplayBackend(device_id=device_id)
    elif backend_type == "wled":
        from phoenix.display.wled import WLEDDisplayBackend

        return WLEDDisplayBackend(device_id=device_id)
    else:
        from phoenix.display.web import WebDisplayBackend

        return WebDisplayBackend(device_id=device_id)


@app.command()
def display(
    device: Annotated[
        Optional[str], typer.Option("--device", "-d", help="Run only this device's loop")
    ] = None,
):
    """Run a display loop per enabled device.

    On first run the legacy single-panel state is migrated into a 'main' device
    (backend from PHOENIX_PLATFORM). Each enabled device gets its own loop and
    backend; mirror devices follow their target.
    """
    import threading

    from phoenix.db import DeviceDatabase, seed_default_device
    from phoenix.display.manager import DisplayManager
    from phoenix.settings import get_settings

    settings = get_settings()
    # Migrate the current single-device world into one 'main' device the first
    # time this runs; no-op once devices exist.
    seed_default_device(backend=settings.platform)

    ddb = DeviceDatabase()
    devices = [d for d in ddb.list_devices() if d["enabled"]]
    if device:
        devices = [d for d in devices if d["id"] == device]
        if not devices:
            console.print(f"[red]No enabled device named[/] {device}")
            raise typer.Exit(1)

    if not devices:
        console.print("[yellow]No enabled devices to drive.[/]")
        raise typer.Exit(1)

    threads: list[threading.Thread] = []
    for i, d in enumerate(devices):
        backend = _make_backend(d["backend"], d["id"])
        dm = DisplayManager(backend, device_id=d["id"], primary=(i == 0))
        mode = f"mirror→{d['mirror_of']}" if d.get("mirror_of") else d["backend"]
        console.print(f"Starting device [bold]{d['id']}[/] ({mode})...")
        t = threading.Thread(target=dm.run, name=f"display-{d['id']}", daemon=True)
        t.start()
        threads.append(t)

    try:
        while any(t.is_alive() for t in threads):
            for t in threads:
                t.join(timeout=0.5)
    except KeyboardInterrupt:
        console.print("Display stopped.")


@app.command()
def visualize(
    ip: Annotated[Optional[str], typer.Option("--ip", help="WLED panel IP (else PHOENIX_WLED_IP / mDNS)")] = None,
    device: Annotated[Optional[str], typer.Option("--device", "-D", help="Audio input device (name substring or index)")] = None,
    file: Annotated[Optional[str], typer.Option("--file", "-f", help="Visualize an audio file instead of live capture")] = None,
    record: Annotated[Optional[str], typer.Option("--record", "-r", help="Write the visualization to a video file (no panel needed)")] = None,
    start: Annotated[float, typer.Option(help="Seconds into the file to start (with --file)")] = 0.0,
    duration: Annotated[Optional[float], typer.Option(help="Seconds to render (with --file)")] = None,
    scale: Annotated[int, typer.Option(help="Upscale factor for the recorded video")] = 8,
    mode: Annotated[str, typer.Option("--mode", "-m", help="Visualizer: bars | vu | spectrogram")] = "bars",
    bands: Annotated[int, typer.Option(help="Spectrum bands (bars)")] = 24,
    tilt: Annotated[float, typer.Option(help="dB/octave lift on highs (evens the spectrum)")] = 3.0,
    gain: Annotated[float, typer.Option(help="Overall sensitivity in dB")] = 6.0,
    samplerate: Annotated[int, typer.Option(help="Sample rate (Hz)")] = 44100,
    block: Annotated[int, typer.Option(help="Samples per block; fps ≈ samplerate/block")] = 1024,
    brightness: Annotated[Optional[int], typer.Option(help="Set WLED master brightness 0-255 on start")] = None,
    redundancy: Annotated[int, typer.Option(help="Send each UDP packet N times — insurance on a lossy WiFi link")] = 1,
    fps: Annotated[Optional[float], typer.Option(help="Cap output frames/sec (fewer, more-complete frames on a bad link)")] = None,
    protocol: Annotated[str, typer.Option(help="Transport: ddp (atomic frames, no tearing) | dnrgb")] = "ddp",
    list_devices: Annotated[bool, typer.Option("--list-devices", help="List audio input devices and exit")] = False,
):
    """Stream a live audio spectrum visualizer to the WLED panel.

    Live from a loopback of what the Mac is playing:

        phoenix visualize --list-devices
        phoenix visualize --ip 192.168.1.50 --device "Loopback"

    Or render an audio file to a video (no panel needed):

        phoenix visualize --file song.webm --record out.mp4 --duration 25
    """
    try:
        from phoenix.audio.analyzer import SpectrumAnalyzer
        from phoenix.audio.source import DeviceAudioSource, FileAudioSource, list_input_devices
        from phoenix.audio.visualizer import make_visualizer
    except ImportError as e:
        console.print(f"[red]Audio extra not installed.[/] Run: [bold]uv sync --extra audio[/]  ({e})")
        raise typer.Exit(1)

    if list_devices:
        for i, name in list_input_devices():
            console.print(f"  [{i}] {name}")
        return

    native_fps = max(1.0, samplerate / block)
    stride = max(1, round(native_fps / fps)) if fps else 1  # emit every Nth block
    out_fps = native_fps / stride

    # Outputs: a panel (default), a recorded video, or both.
    recorder = None
    if record:
        from phoenix.audio.record import FrameRecorder

        recorder = FrameRecorder(record, fps=out_fps, scale=scale)

    sink = None
    if ip is not None or recorder is None:  # panel is the default unless only recording
        from phoenix.display.wled import WLEDDisplayBackend

        sink = WLEDDisplayBackend(ip=ip, redundancy=redundancy, protocol=protocol, max_fps=(fps or 15.0))
        if not sink._ip:
            if recorder is None:
                console.print("[red]No WLED panel found.[/] Pass --ip or set PHOENIX_WLED_IP.")
                raise typer.Exit(1)
            sink = None  # recording-only, panel not required
        elif brightness is not None:
            sink.set_brightness(brightness)

    if file:
        source = FileAudioSource(
            file, samplerate=samplerate, blocksize=block, start=start, duration=duration,
            realtime=(sink is not None and record is None),  # pace to the panel; full-speed for --record
        )
    else:
        source = DeviceAudioSource(device=device, samplerate=samplerate, blocksize=block)

    analyzer = SpectrumAnalyzer(samplerate=samplerate, fft_size=block, bands=bands, tilt=tilt, gain_db=gain)
    try:
        viz = make_visualizer(mode, bands=bands)
    except ValueError as e:
        console.print(f"[red]{e}[/]")
        raise typer.Exit(1)

    dest = " + ".join(x for x in [f"WLED {sink._ip}" if sink else None, record] if x)
    rtag = f" · {redundancy}x" if redundancy > 1 else ""
    console.print(
        f"[green]Visualizing[/] {file or 'live'} → {dest} · {bands} bands · ~{out_fps:.0f}fps{rtag}"
    )
    frames = 0
    try:
        for i, blk in enumerate(source.blocks()):
            levels_peaks = analyzer.process(blk)  # run every block to keep smoothing continuous
            if i % stride:
                continue  # fps cap: skip emitting this block's frame
            frame = viz.render(*levels_peaks)
            if sink:
                sink.send_frame(frame)
            if recorder:
                recorder.add(frame)
            frames += 1
    except KeyboardInterrupt:
        pass
    finally:
        source.close()
        if recorder:
            recorder.close()
        if sink:
            sink.clear()
        console.print(f"\nDone — {frames} frames.")


@app.command()
def play(
    file: Annotated[str, typer.Argument(help="Image / GIF / WebP / APNG to display")],
    ip: Annotated[Optional[str], typer.Option("--ip", help="WLED panel IP (else PHOENIX_WLED_IP / mDNS)")] = None,
    duration: Annotated[float, typer.Option(help="Seconds to loop it (0 = forever, Ctrl-C to stop)")] = 15.0,
    brightness: Annotated[int, typer.Option(help="WLED master brightness 0-255")] = 110,
    redundancy: Annotated[int, typer.Option(help="Send each UDP packet N times (lossy-link insurance)")] = 1,
    protocol: Annotated[str, typer.Option(help="Transport: ddp (atomic frames, no tearing) | dnrgb")] = "ddp",
    fps: Annotated[float, typer.Option(help="Cap frames/sec sent to the panel (WiFi can't sustain much past ~15)")] = 15.0,
):
    """Stream an image or animated GIF/WebP to the WLED panel (host-decoded, looped).

        phoenix play cat.gif --ip 192.168.1.166
    """
    from pathlib import Path

    from phoenix.display.sink import FramePlayer
    from phoenix.display.wled import WLEDDisplayBackend

    p = Path(file)
    if not p.exists():
        console.print(f"[red]No such file:[/] {file}")
        raise typer.Exit(1)

    sink = WLEDDisplayBackend(ip=ip, redundancy=redundancy, protocol=protocol, max_fps=fps)
    if not sink._ip:
        console.print("[red]No WLED panel found.[/] Pass --ip or set PHOENIX_WLED_IP.")
        raise typer.Exit(1)

    player = FramePlayer(sink)
    dur = int(duration) if duration > 0 else 10**9
    console.print(f"[green]Playing[/] {p.name} → WLED [bold]{sink._ip}[/] · {brightness} bri · Ctrl-C to stop")
    try:
        player.play(p, dur, lambda: brightness, lambda: False)
    except KeyboardInterrupt:
        pass
    finally:
        sink.clear()
        console.print("\nStopped.")


@app.command()
def nowplaying(
    ip: Annotated[Optional[str], typer.Option("--ip", help="WLED panel IP (else PHOENIX_WLED_IP / mDNS)")] = None,
    brightness: Annotated[int, typer.Option(help="WLED master brightness 0-255")] = 120,
    fps: Annotated[float, typer.Option(help="Cap frames/sec sent to the panel")] = 15.0,
):
    """Stream a live now-playing card (album art + scrolling title + progress) to the panel.

        phoenix nowplaying --ip 192.168.1.166
    """
    import time

    from phoenix.display.wled import WLEDDisplayBackend
    from phoenix.nowplaying.render import NowPlayingRenderer
    from phoenix.nowplaying.source import HANowPlayingSource
    from phoenix.settings import get_settings

    settings = get_settings()
    if not settings.ha_url or not settings.ha_token:
        console.print("[yellow]Home Assistant not configured[/] (PHOENIX_HA_URL / PHOENIX_HA_TOKEN) — showing idle card.")

    sink = WLEDDisplayBackend(ip=ip, max_fps=fps)
    if not sink._ip:
        console.print("[red]No WLED panel found.[/] Pass --ip or set PHOENIX_WLED_IP.")
        raise typer.Exit(1)
    sink.set_brightness(brightness)

    source = HANowPlayingSource(settings)
    renderer = NowPlayingRenderer()
    console.print(f"[green]Now playing[/] → WLED [bold]{sink._ip}[/] · Ctrl-C to stop")
    last = time.perf_counter()
    try:
        while True:
            now = time.perf_counter()
            dt, last = now - last, now
            track = source.get()
            frame = renderer.render(track, dt) if track else renderer.render_idle()
            sink.send_frame(frame)
            time.sleep(1 / 20)  # render ~20fps; the sink caps the wire rate
    except KeyboardInterrupt:
        pass
    finally:
        sink.clear()
        console.print("\nStopped.")


@app.command()
def dashboard():
    """Run the FastAPI web dashboard."""
    import uvicorn

    from phoenix.settings import get_settings

    settings = get_settings()
    uvicorn.run(
        "phoenix.server.dashboard:create_app",
        factory=True,
        host="0.0.0.0",
        port=settings.dashboard_port,
        reload=False,
    )


@app.command()
def shop(
    query: Annotated[Optional[str], typer.Argument(help="Search community apps")] = None,
    install: Annotated[Optional[str], typer.Option("--install", "-i", help="Import a community app by name")] = None,
    category: Annotated[Optional[str], typer.Option("--category", "-c", help="Filter by category")] = None,
    tag: Annotated[Optional[str], typer.Option("--tag", "-t", help="Filter by tag")] = None,
    categories: Annotated[bool, typer.Option("--categories", help="List all categories")] = False,
):
    """Browse and import community apps from phoenix-apps."""
    from phoenix.shop import ensure_repo, import_app, list_categories, search_apps
    from phoenix.models import REFRESH_PRESETS

    from phoenix.paths import APPS_DIR, COMMUNITY_DIR

    ensure_repo(COMMUNITY_DIR)

    if categories:
        cats = list_categories(COMMUNITY_DIR)
        for c in cats:
            console.print(f"  {c}")
        console.print(f"\n  {len(cats)} categories")
        return

    if install:
        svc = get_service()
        dest = import_app(COMMUNITY_DIR, install, APPS_DIR)
        svc.create_app(install, source="community", refresh_interval=REFRESH_PRESETS["ambient"])
        console.print(f"[green]Imported:[/] {install} -> {dest}")
        return

    apps = search_apps(COMMUNITY_DIR, query=query or "", category=category or "", tag=tag or "")

    table = Table(title="Community Apps (phoenix-apps)")
    table.add_column("Name")
    table.add_column("Category", style="dim")
    table.add_column("Summary")
    table.add_column("Author", style="dim")

    for a in sorted(apps, key=lambda x: x.name):
        table.add_row(a.name, a.category, a.summary, a.author)

    console.print(table)
    console.print(f"  {len(apps)} apps found")
