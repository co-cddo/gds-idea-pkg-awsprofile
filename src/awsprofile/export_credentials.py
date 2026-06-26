import configparser
import datetime
import json
import os
import subprocess
import sys

import click


def _list_profiles() -> list[str]:
    try:
        completed_process = subprocess.run(
            ["aws", "configure", "list-profiles"], check=True, capture_output=True, text=True
        )
    except subprocess.CalledProcessError as e:
        raise e

    stdout = completed_process.stdout
    stdout_list = stdout.strip("\n").split("\n")
    return stdout_list


def _dict_aliases() -> tuple[dict[str, str], list[str]]:
    config = configparser.RawConfigParser()
    config.read(os.path.expanduser("~/.aws/config"))
    aliases = {}
    sections_parsed = []
    for section in config.sections():
        alias = config.get(section, "alias", fallback=None)
        section_parsed = section.replace("profile", "").strip()
        sections_parsed.append(section_parsed)
        if alias is not None:
            if alias in aliases:
                click.echo("Discoverd duplicated aliases in your cofig file!", err=True)
            aliases[alias] = section_parsed

    sections_parsed = list(set(sections_parsed))
    return aliases, sections_parsed


def _set_alias(alias, profile):
    aliases, profiles = _dict_aliases()

    if profile not in profiles:
        click.echo(f"Profile '{profile}' does not exist", err=True)
        click.echo("", err=True)
        reversed_aliases = {profile: alias for alias, profile in aliases.items()}
        echo_profiles = [
            f"{profile} ({reversed_aliases[profile]})" if profile in reversed_aliases else profile
            for profile in profiles
        ]
        click.echo(f"Available profiles:\n{'\n'.join(echo_profiles)}", err=True)
        sys.exit(1)
    if alias in aliases:
        click.echo(f"Alias '{alias}' does exist", err=True)
        click.echo("", err=True)
        echo_aliases = [f"{profile} ({alias})" for alias, profile in aliases.items()]
        click.echo(f"Existing aliases:\n{'\n'.join(echo_aliases)}", err=True)
        sys.exit(1)

    subprocess.run(
        ["aws", "configure", "set", "alias", alias, "--profile", profile], check=True, capture_output=True, text=True
    )


def _export_credentials(profile: str):
    aliases, profiles = _dict_aliases()
    profile = aliases.get(profile, profile)
    if profile in profiles:
        completed_process = subprocess.run(
            ["aws", "configure", "export-credentials", "--profile", profile], check=True, capture_output=True, text=True
        )
    else:
        click.echo(f"Profile or alias: '{profile}' does not exist", err=True)
        click.echo("", err=True)
        reversed_aliases = {profile: alias for alias, profile in aliases.items()}
        echo_profiles = [
            f"{profile} ({reversed_aliases[profile]})" if profile in reversed_aliases else profile
            for profile in profiles
        ]
        click.echo(f"Available profiles:\n{'\n'.join(echo_profiles)}", err=True)
        sys.exit(1)

    stdout = completed_process.stdout
    stdout_json = json.loads(stdout)

    try:
        completed_process = subprocess.run(
            ["aws", "configure", "set", "aws_access_key_id", stdout_json["AccessKeyId"], "--profile", "default"],
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as e:
        raise e
    try:
        completed_process = subprocess.run(
            [
                "aws",
                "configure",
                "set",
                "aws_secret_access_key",
                stdout_json["SecretAccessKey"],
                "--profile",
                "default",
            ],
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as e:
        raise e
    try:
        completed_process = subprocess.run(
            ["aws", "configure", "set", "aws_session_token", stdout_json["SessionToken"], "--profile", "default"],
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as e:
        raise e

    time_now = datetime.datetime.now(datetime.UTC)
    time_expiration = datetime.datetime.strptime(stdout_json["Expiration"], "%Y-%m-%dT%H:%M:%S%z")
    time_diff = time_expiration - time_now

    if time_diff > datetime.timedelta():
        click.echo(f"Session valid, {time_diff.total_seconds() // 60} minutes left", err=True)
