"""CLI entry point."""

import click

from cli.scan import scan
from cli.report import score_report
from cli.flatten import flatten


@click.group()
def cli() -> None:
    """Options Alpha Agent CLI"""
    pass


cli.add_command(scan)
cli.add_command(score_report)
cli.add_command(flatten)


if __name__ == "__main__":
    cli()
