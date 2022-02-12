""" CLI. """
import logging
import os
import sys

from nerddiary import __version__
from nerddiary.log import configure_logger

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

    logger = configure_logger("nerddiary", log_level=log_level if not verbose else "DEBUG", log_file=log_file)
    logger.debug("Init cli succesful")


try:
    from nerddiary.bots.tgbot.bot import NerdDiaryTGBot

    logger.debug("Found TG Bot module. Creating Bot CLI")

    @cli.command()
    @click.pass_context
    def bot(ctx: click.Context) -> None:

        interactive = ctx.parent.params["interactive"]  # type: ignore

        if interactive:
            click.echo(click.style("Starting the bot!", fg="green"))

        try:
            NerdDiaryTGBot().run()
        except KeyboardInterrupt:
            pass
        finally:
            logger.info("Bot was stopped")

except ImportError:
    logger.debug("TG Bot module doesn't exist. Skipping")

if __name__ == "__main__":
    cli(auto_envvar_prefix="NERDDY")
