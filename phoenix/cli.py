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


@app.command()
def display():
    """Run the display loop (backend selected by PHOENIX_PLATFORM env var)."""
    from phoenix.display.manager import DisplayManager
    from phoenix.settings import get_settings

    settings = get_settings()

    if settings.platform == "matrix":
        from phoenix.display.matrix import MatrixDisplayBackend

        backend = MatrixDisplayBackend()
    elif settings.platform == "serial":
        from phoenix.display.serial import SerialDisplayBackend

        backend = SerialDisplayBackend()
    elif settings.platform == "wled":
        from phoenix.display.wled import WLEDDisplayBackend

        backend = WLEDDisplayBackend()
    else:
        from phoenix.display.web import WebDisplayBackend

        backend = WebDisplayBackend()

    console.print(f"Starting display ({settings.platform} backend)...")
    dm = DisplayManager(backend)
    try:
        dm.run()
    except KeyboardInterrupt:
        console.print("Display stopped.")


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
