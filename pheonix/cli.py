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
