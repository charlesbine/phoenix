import click


@click.group()
@click.option("--debug/--no-debug", default=False)
def cli(debug):
    click.echo(f"Debug mode is {'on' if debug else 'off'}")


@cli.command()
@click.argument("applet", required=False)
@click.option("--list", is_flag=True, help="List all available applets")
def render(applet, list):
    """Render applets.

    If APPLET is provided, renders only that applet once and exits.
    Without arguments, runs all applets in a continuous loop.
    """
    if list:
        from pheonix.app_db import read_all_apps

        all_apps = read_all_apps()
        click.echo("\n" + click.style("Available Applets:", bold=True))
        click.echo(click.style("─" * 50, dim=True))

        # Count enabled and disabled applets
        enabled_count = sum(1 for app in all_apps if app.enabled)
        disabled_count = len(all_apps) - enabled_count

        for app in all_apps:
            status = "enabled" if app.enabled else "disabled"
            # Use green for enabled applets and red for disabled ones
            name_colored = click.style(app.name, fg="green" if app.enabled else "red", bold=True)
            status_colored = click.style(status, fg="green" if app.enabled else "red")

            # Add a symbol to indicate status
            symbol = click.style("●", fg="green") if app.enabled else click.style("○", fg="red")

            click.echo(f"  {symbol} {name_colored} ({status_colored})")

        # Summary line
        click.echo(click.style("─" * 50, dim=True))
        click.echo(
            f"  Total: {len(all_apps)} applets "
            + f"({click.style(str(enabled_count), fg='green')} enabled, "
            + f"{click.style(str(disabled_count), fg='red')} disabled)"
        )
        click.echo("")
        return

    if applet:
        # Run a single applet and exit
        from pheonix.render import run_app

        try:
            run_app(applet)
            click.echo(f"Successfully rendered applet: {applet}")
        except Exception as e:
            click.echo(f"Error rendering applet {applet}: {e}", err=True)
            raise click.Abort()
    else:
        # Run all apps in a loop (original behavior)
        from pheonix.render import run_all_apps

        run_all_apps()


@cli.command()
@click.argument("name", required=True)
@click.option("--enabled/--disabled", default=True)
@click.option("--config", "-c", multiple=True, help="Key-value pairs in the format key=value")
def new(name: str, enabled: bool, config, **kwargs):
    """Create a new applet.

    Example:
        pheonix new clock --enabled -c timezone=America/New_York -c color=blue
    """
    from pheonix.app_db import create_new_app

    # Process config key-value pairs
    config_dict = {}
    for item in config:
        if "=" not in item:
            click.echo(
                f"Warning: Ignoring invalid config item '{item}'. Format should be key=value",
                err=True,
            )
            continue

        key, value = item.split("=", 1)
        config_dict[key.strip()] = value.strip()

    if config_dict:
        click.echo(f"Adding configuration: {config_dict}")

    # Merge config_dict with kwargs
    kwargs.update(config_dict)

    # Create the new app
    try:
        app = create_new_app(name, enabled=enabled, **kwargs)
        click.echo(f"Successfully created applet: {click.style(name, fg='green', bold=True)}")

        # Show a summary of the created app
        click.echo("\nApplet details:")
        click.echo(f"  Name: {click.style(app.name, bold=True)}")
        click.echo(
            f"  Status: {click.style('enabled' if app.enabled else 'disabled', fg='green' if app.enabled else 'red')}"
        )
        click.echo(f"  File: {app.filename}")

        if config_dict:
            click.echo("  Configuration:")
            for key, value in config_dict.items():
                click.echo(f"    {key}: {value}")
    except Exception as e:
        click.echo(f"Error creating applet: {e}", err=True)
        raise click.Abort()


@cli.command()
def display():
    from pheonix.display import DisplayManager

    dm = DisplayManager()
    dm.run_display()


@cli.command()
def server():
    from pheonix.http_server import run_server

    run_server()


if __name__ == "__main__":
    cli()
