import click


@click.group()
@click.option('--debug/--no-debug', default=False)
def cli(debug):
    click.echo(f"Debug mode is {'on' if debug else 'off'}")


@cli.command()
def render():
    from pheonix.render import run_all_apps_sync
    run_all_apps_sync()


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