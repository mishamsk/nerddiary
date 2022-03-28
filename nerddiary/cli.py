""" CLI. """
import logging
import os
import sys
from logging.config import dictConfig

from nerddiary import __version__
from nerddiary.log import get_log_config

import click

logger = logging.getLogger("nerddiary")


def version_msg() -> str:
    """Return the version, location and Python powering it."""
    python_version = sys.version
    location = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    message = "Migrelyzer %(version)s from {} (Python {})"
    return message.format(location, python_version)


@click.group(context_settings=dict(help_option_names=["-h", "--help"]))
@click.version_option(__version__, "-V", "--version", message=version_msg())
@click.option("-v", "--verbose", is_flag=True, help="Force all log levels to debug", default=False)
@click.option(
    "-i",
    "--interactive",
    is_flag=True,
    help="Whether to output interactive prompts",
    default=False,
)
@click.option(
    "--log-file",
    type=click.Path(dir_okay=False, writable=True),
    default=None,
    help="File to be used for logging",
)
@click.option(
    "--log-level",
    type=click.Choice(
        [
            "DEBUG",
            "INFO",
            "WARNING",
            "ERROR",
            "CRITICAL",
        ],
        case_sensitive=False,
    ),
    help="Log level",
    default="INFO",
    show_default=True,
)
def cli(
    log_file: str,
    log_level: str,
    verbose: bool,
    interactive: bool,
) -> None:
    """Main entry point"""

    dictConfig(get_log_config("nerddiary", log_level=log_level if not verbose else "DEBUG", log_file=log_file))
    logger.debug("Init cli succesful")


try:
    # TODO: make a better detection mechanism
    from fastapi import APIRouter  # noqa:F401

    logger.debug("Found TG Server module. Creating Server CLI")
    import uvicorn

    @cli.command()
    @click.pass_context
    @click.option(
        "-p",
        "--port",
        help="Port to run the server on",
        default=80,
    )
    @click.option(
        "-r",
        "--reload",
        is_flag=True,
        help="Whether to auto reload server on file change",
        default=False,
    )
    def server(ctx: click.Context, port: int, reload: bool) -> None:

        interactive = ctx.parent.params["interactive"]  # type: ignore
        log_level: str = ctx.parent.params["log_level"]  # type: ignore
        log_file: str = ctx.parent.params["log_file"]  # type: ignore
        verbose: str = ctx.parent.params["verbose"]  # type: ignore

        if interactive:
            click.echo(click.style("Starting the server!", fg="green"))

        try:
            # TODO: Separate development config with reload from normal cli
            uvicorn.run(
                "nerddiary.server.main:app",
                host="0.0.0.0",
                reload=reload,
                reload_dirs=["nerddiary"],
                reload_excludes=["nerddiary/bots", "nerddiary/core/client"],
                port=port,
                log_level="info",
                log_config=get_log_config(
                    "nerddiary", log_level=log_level if not verbose else "DEBUG", log_file=log_file
                ),
            )
        except KeyboardInterrupt:
            pass
        finally:
            logger.info("Server was stopped")

except ImportError:
    logger.debug("TG Bot module doesn't exist. Skipping")

if __name__ == "__main__":
    cli(auto_envvar_prefix="NERDDY")
