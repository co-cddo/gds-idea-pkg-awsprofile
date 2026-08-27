"""Sign-in flow and profile/alias/credentials inspection helpers.

Reads and writes `~/.aws/config` and `~/.aws/credentials` directly via
`configparser` (through `awsprofile.utils._config_set`/`_credentials_set`),
and uses `botocore`/`boto3` to resolve temporary session credentials for a
given profile (assuming a role via MFA where the profile requires it).
"""

import configparser
import datetime
import os
import sys

import boto3
import botocore.session
import click
from botocore import credentials

from awsprofile.utils import _config_set, _credentials_set


def _list_profiles() -> list[str]:
    """List all aws profile names known to this machine.

    Combines section names found in both `~/.aws/credentials` (section name
    is the profile name directly) and `~/.aws/config` (section name is
    `profile <name>`, except for `default`), deduplicated.

    Returns:
        AWS profile names list, e.g. `["default", "gds-users", "assume-ds-role-dev-readonly"]`.
    """
    profiles = []

    credentials_config = configparser.RawConfigParser()
    credentials_config.read(os.path.expanduser("~/.aws/credentials"))
    profiles.extend(credentials_config.sections())

    config = configparser.RawConfigParser()
    config.read(os.path.expanduser("~/.aws/config"))
    for section in config.sections():
        section_parsed = section.replace("profile", "").strip()
        if section_parsed not in profiles:
            profiles.append(section_parsed)

    return profiles


def _dict_aliases() -> tuple[dict[str, str], list[str]]:
    """Get a dictionary of aliases to profiles, along with the full profile list.

    Reads the `alias` field of every section in `~/.aws/config`.

    Returns:
        - Dictionary mapping alias name to the profile name it points to,
          e.g. `{"dev": "assume-ds-role-dev-poweraccess"}`.
        - List of all profile names found in `~/.aws/config` (whether or
          not they have an alias).
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


def _dict_credentials_profiles() -> dict[str, str]:
    """Get a dictionary of export profiles to the source profile they were signed in from.

    Reads the `credentials_profile` field (set by `_export_credentials`
    after a successful sign-in) of every section in `~/.aws/config`.

    Returns:
        Dictionary mapping export profile name to the source profile name
        whose credentials it currently holds, e.g.
        `{"default": "assume-ds-role-dev-poweraccess"}`.
    """
    config = configparser.RawConfigParser()
    config.read(os.path.expanduser("~/.aws/config"))
    profiles = {}
    for section in config.sections():
        credentials_profile = config.get(section, "credentials_profile", fallback=None)
        if credentials_profile is not None:
            sections_parsed = section.replace("profile", "").strip()
            profiles[sections_parsed] = credentials_profile

    return profiles


def _set_alias(alias: str, profile: str) -> None:
    """Set alias to aws profile.

    Create or update alias field for aws profile. Exits with status 1 if
    `profile` doesn't exist, or if `alias` is already in use by another
    profile (printing the available profiles/aliases in either case).

    Args:
        alias: Alias name to set.
        profile: Profile name to set alias for.

    Example:
        >>> _set_alias("dev", "assume-ds-role-dev-poweraccess")
        # Lets you sign in with `awsprofile dev` instead of the full name.
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

    _config_set(profile, "alias", alias)


def _export_credentials(profile: str, export_profile: str = None) -> None:
    """Sign in to a profile (assuming a role via MFA if required) and write
    the resulting temporary credentials to another profile on disk.

    Resolves `profile` through any configured alias, then obtains
    credentials for it via `botocore`/`boto3` (caching assume-role results
    in `~/.aws/cli/cache`, same as the AWS CLI). The resulting access key,
    secret key and session token are written into `export_profile` in
    `~/.aws/credentials`, and `export_profile`'s `credentials_profile`
    field in `~/.aws/config` is set to `profile`, so `awsprofile list` can
    later report where those credentials came from.

    Args:
        profile: Profile or alias name to sign in with.
        export_profile: Profile to write the temporary credentials to.
            Defaults to `"default"`. Must not be an `assume-ds-role-*` or
            `gds-users` profile, since those are only ever used as sign-in
            sources, never as credential export targets.

    Example:
        >>> _export_credentials(profile="dev")
        # Signs in to the "dev" alias and writes into ~/.aws/credentials
        # under [default].
        >>> _export_credentials(profile="bedrock", export_profile="bedrockonly")
        # Signs in to the "bedrock" alias without touching [default].
    """
    export_profile = "default" if export_profile is None else export_profile
    if export_profile.startswith("assume-ds-role") or export_profile == "gds-users":
        click.echo("Invalid export profile name!", err=True)
        sys.exit(1)

    aliases, profiles = _dict_aliases()
    profile = aliases.get(profile, profile)

    if profile in profiles:
        cli_cache = os.path.join(os.path.expanduser("~"), ".aws/cli/cache")

        # Construct botocore session with cache
        session = botocore.session.Session(profile=profile)
        session.get_component("credential_provider").get_provider("assume-role").cache = credentials.JSONFileCache(
            cli_cache
        )

        session_boto = boto3.Session(botocore_session=session)

        try:
            aws_credentials = session_boto.get_credentials()
            frozen_credentials = aws_credentials.get_frozen_credentials()
        except botocore.exceptions.ClientError as e:
            click.echo(click.style(e, fg="red"), err=True)
            sys.exit(1)
        except botocore.exceptions.ParamValidationError as e:
            click.echo(click.style(e, fg="red"), err=True)
            sys.exit(1)

        access_key_id = frozen_credentials.access_key
        secret_access_key = frozen_credentials.secret_key
        session_token = frozen_credentials.token
        time_expiration = getattr(aws_credentials, "_expiry_time", None)

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

    _credentials_set(export_profile, "aws_access_key_id", access_key_id)
    _credentials_set(export_profile, "aws_secret_access_key", secret_access_key)
    _credentials_set(export_profile, "aws_session_token", session_token)
    _config_set(export_profile, "credentials_profile", profile)
    if time_expiration is not None:
        time_now = datetime.datetime.now(datetime.UTC)
        time_diff = time_expiration - time_now

        if time_diff > datetime.timedelta():
            echo_time_diff = time_diff.total_seconds() // 60
            click.echo(f"Session valid, {echo_time_diff} minutes left", err=False)
    else:
        click.echo("Session valid", err=False)
