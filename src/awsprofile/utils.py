import subprocess
import sys

import click


def _execute_command(command: list[str], capture_output=True):
    try:
        completed_process = subprocess.run(
            command,
            check=True,
            capture_output=capture_output,
            text=True,
        )
    except subprocess.CalledProcessError as e:
        click.echo(e.stderr, err=True)
        sys.exit(1)

    return completed_process
