import configparser
import datetime
import json
import os
import subprocess
import sys

import boto3
import botocore.session
import click
from botocore import credentials


def _list_profiles() -> list[str]:
    """List aws profiles

    Returns:
        AWS profiles names list.
    """
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
    """Get aws profiles list and and aliases to profiles dictionary

    Returns:
        - Dictionary alias to profile name.
        - List profiles names.
    """
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
                click.echo(f"Discoverd duplicated alias '{alias}' in your cofig file!", err=True)
            aliases[alias] = section_parsed

    sections_parsed = list(set(sections_parsed))
    return aliases, sections_parsed


def _set_alias(alias, profile):
    """Set alias to aws profile.

    Create or update alias field for aws profile.

    Args:
        alias: Alias name to set.
        profile: Profile name to set alias for.
    """
    aliases, profiles = _dict_aliases()

    if profile not in profiles:
        click.echo(f"Profile '{profile}' does not exist", err=True)
        click.echo("", err=True)
        reversed_aliases = {profile: alias for alias, profile in aliases.items()}
        echo_profiles = [
            f"{profile} ({reversed_aliases[profile]})" if profile in reversed_aliases else profile
            for profile in profiles
        ]
        echo_profiles = "\n".join(echo_profiles)
        click.echo(f"Available profiles:\n{echo_profiles}", err=True)
        sys.exit(1)
    if alias in aliases:
        click.echo(f"Alias '{alias}' does exist", err=True)
        click.echo("", err=True)
        echo_aliases = [f"{profile} ({alias})" for alias, profile in aliases.items()]
        echo_aliases = "\n".join(echo_aliases)
        click.echo(f"Existing aliases:\n{echo_aliases}", err=True)
        sys.exit(1)

    subprocess.run(
        ["aws", "configure", "set", "alias", alias, "--profile", profile], check=True, capture_output=True, text=True
    )


def _export_credentials(profile: str, export_profile: str = None):
    """Log in and set aws profile temporary credentials in default profile.

    Args:
        profile: Profile or alias name to set as export_profile.
        export_profile: (Optional) Profile to export credentials to, defaults to default
    """
    export_profile = "default" if export_profile is None else export_profile
    if export_profile.startswith("assume-ds-role") or export_profile == "gds-users":
        click.echo("Invalid export profile name!", err=True)
        sys.exit(1)

    aliases, profiles = _dict_aliases()
    profile = aliases.get(profile, profile)

    if profile in profiles:
        completed_process = subprocess.run(["aws", "--version"], check=True, capture_output=True, text=True)
        aws_cli_version = completed_process.stdout
        aws_cli_version = int(aws_cli_version.split(" ", 1)[0].split("/", 1)[1].split(".", 1)[0])

        if aws_cli_version < 2:
            click.echo("AWS CLI old version discovered. the app functionality might be limited.", err=True)

            cli_cache = os.path.join(os.path.expanduser("~"), ".aws/cli/cache")

            # Construct botocore session with cache
            session = botocore.session.Session(profile=profile)
            session.get_component("credential_provider").get_provider("assume-role").cache = credentials.JSONFileCache(
                cli_cache
            )

            session_boto = boto3.Session(botocore_session=session)

            try:
                frozen_credentials = session_boto.get_credentials().get_frozen_credentials()
            except botocore.exceptions.ClientError as e:
                click.echo(click.style(e, fg="red"), err=True)
                sys.exit(1)
            except botocore.exceptions.ParamValidationError as e:
                click.echo(click.style(e, fg="red"), err=True)
                sys.exit(1)

            access_key_id = frozen_credentials.access_key
            secret_access_key = frozen_credentials.secret_key
            session_token = frozen_credentials.token
            expiration = None

        else:
            completed_process = subprocess.run(
                ["aws", "configure", "export-credentials", "--profile", profile],
                check=True,
                capture_output=True,
                text=True,
            )

            stdout = completed_process.stdout
            stdout_json = json.loads(stdout)

            access_key_id = stdout_json["AccessKeyId"]
            secret_access_key = stdout_json["SecretAccessKey"]
            session_token = stdout_json["SessionToken"]
            expiration = stdout_json["Expiration"]

    else:
        click.echo(f"Profile or alias: '{profile}' does not exist", err=True)
        click.echo("", err=True)
        reversed_aliases = {profile: alias for alias, profile in aliases.items()}
        echo_profiles = [
            f"{profile} ({reversed_aliases[profile]})" if profile in reversed_aliases else profile
            for profile in profiles
        ]
        echo_profiles = "\n".join(echo_profiles)
        click.echo(f"Available profiles:\n{echo_profiles}", err=True)
        sys.exit(1)

    try:
        completed_process = subprocess.run(
            ["aws", "configure", "set", "aws_access_key_id", access_key_id, "--profile", export_profile],
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
                secret_access_key,
                "--profile",
                export_profile,
            ],
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as e:
        raise e
    try:
        completed_process = subprocess.run(
            ["aws", "configure", "set", "aws_session_token", session_token, "--profile", export_profile],
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as e:
        raise e
    try:
        completed_process = subprocess.run(
            ["aws", "configure", "set", "credentials_profile", profile, "--profile", export_profile],
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as e:
        raise e

    if expiration is not None:
        time_now = datetime.datetime.now(datetime.UTC)
        time_expiration = datetime.datetime.strptime(expiration, "%Y-%m-%dT%H:%M:%S%z")
        time_diff = time_expiration - time_now

        if time_diff > datetime.timedelta():
            echo_time_diff = time_diff.total_seconds() // 60
            click.echo(f"Session valid, {echo_time_diff} minutes left", err=False)
    else:
        click.echo("Session valid", err=False)
