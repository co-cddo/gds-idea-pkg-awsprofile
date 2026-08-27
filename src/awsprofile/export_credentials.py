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
import dateutil.parser
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


def _boto3_session(profile: str) -> boto3.Session:
    """Build a boto3 session for `profile`, caching assume-role results.

    Shared by `_export_credentials` (to sign in) and `_get_expiration` (to
    inspect currently resolved credentials without necessarily forcing a
    fresh sign-in) so both use the exact same caching behaviour as the AWS
    CLI (`~/.aws/cli/cache`).

    Args:
        profile: Profile name to build the session for.

    Returns:
        A `boto3.Session` wrapping a `botocore.session.Session` configured
        with the assume-role provider's on-disk cache.
    """
    cli_cache = os.path.join(os.path.expanduser("~"), ".aws/cli/cache")

    session = botocore.session.Session(profile=profile)
    session.get_component("credential_provider").get_provider("assume-role").cache = credentials.JSONFileCache(
        cli_cache
    )

    return boto3.Session(botocore_session=session)


def _cached_credential_fetcher(aws_credentials):
    """Find the `CachedCredentialFetcher` backing a deferred credentials object.

    For assume-role profiles, `botocore` resolves credentials lazily: the
    `Credentials` object returned by `get_credentials()` starts out with no
    `_expiry_time` at all, and only fetches (and populates it) the first
    time it's refreshed, e.g. via `get_frozen_credentials()`. That refresh
    calls straight through to AWS (and prompts for an MFA code on the
    terminal) whenever the on-disk `~/.aws/cli/cache` entry is missing or
    expired - which makes it unsafe to use from a read-only command like
    `status`.

    To read the expiration without triggering that refresh, this digs
    through `botocore`'s private `_refresh_using` callable (optionally
    unwrapping the MFA-serial refresher wrapper it's given when the profile
    has an `mfa_serial`) to reach the underlying `CachedCredentialFetcher`
    instance, whose `_cache`/`_cache_key` attributes can be read directly
    (local cache file only, never talks to AWS). Nothing in `botocore` is
    modified; this only introspects objects it already constructed.

    Args:
        aws_credentials: A `botocore.credentials.Credentials` (or subclass)
            instance, as returned by `Session.get_credentials()`.

    Returns:
        The `CachedCredentialFetcher` instance, or `None` if `aws_credentials`
        isn't backed by one (e.g. static, long-lived credentials).
    """
    refresher = getattr(aws_credentials, "_refresh_using", None)
    # Unwrap botocore's MFA-serial refresher wrapper, if present, to reach
    # the fetcher's own bound `fetch_credentials` method underneath it.
    refresher = getattr(refresher, "_refresh", refresher)
    fetcher = getattr(refresher, "__self__", None)
    if fetcher is not None and hasattr(fetcher, "_cache_key"):
        return fetcher
    return None


def _get_cached_expiration(aws_credentials) -> datetime.datetime | None:
    """Peek at a deferred assume-role credential's on-disk cache entry.

    Reads the fetcher's `~/.aws/cli/cache` entry directly through its
    `_cache`/`_cache_key` attributes (local file read only, no AWS calls,
    no MFA prompt). Deliberately bypasses `CachedCredentialFetcher._load_from_cache()`,
    which would filter out (return `None` for) an expired entry - we want
    the actual expiration timestamp even when it's in the past, so callers
    like `status` can report "expired N minutes ago" instead of treating
    it the same as "never signed in".

    Args:
        aws_credentials: A `botocore.credentials.Credentials` (or subclass)
            instance, as returned by `Session.get_credentials()`.

    Returns:
        The cached credentials' expiration time (even if it's already in
        the past), or `None` if there's no cached entry at all.
    """
    fetcher = _cached_credential_fetcher(aws_credentials)
    if fetcher is None:
        return None

    try:
        if fetcher._cache_key not in fetcher._cache:
            return None
        cached = fetcher._cache[fetcher._cache_key]
    except Exception:
        return None

    if not cached:
        return None
    expiration = cached.get("Credentials", {}).get("Expiration")
    if expiration is None:
        return None

    return dateutil.parser.parse(expiration)


def _get_expiration(profile: str) -> datetime.datetime | None:
    """Get the expiration time of a profile's currently resolved credentials.

    Resolves `profile`'s credentials via `boto3`/`botocore` (the same
    session/cache construction as `_export_credentials`) and reads the
    `_expiry_time` attribute straight off the resulting credentials object,
    without freezing/refreshing them. Static (non-refreshable) credentials,
    such as `gds-users`'s long-lived access key, don't have this attribute
    and are treated as never expiring.

    For assume-role profiles, `_expiry_time` is only populated once the
    credentials have actually been refreshed at least once (e.g. by a
    prior `awsprofile <profile>` sign-in in this same process). If it's not
    set yet, this falls back to `_get_cached_expiration`, which reads the
    same on-disk `~/.aws/cli/cache` entry the AWS CLI uses, without ever
    forcing a fresh (and possibly MFA-prompting) sign-in.

    Args:
        profile: Profile name to inspect.

    Returns:
        The credentials' expiration time, or `None` if the profile has no
        resolvable/cached credentials, or its credentials don't expire.
    """
    try:
        aws_credentials = _boto3_session(profile).get_credentials()
    except (botocore.exceptions.ClientError, botocore.exceptions.ParamValidationError):
        return None

    if aws_credentials is None:
        return None

    expiry_time = getattr(aws_credentials, "_expiry_time", None)
    if expiry_time is not None:
        return expiry_time

    return _get_cached_expiration(aws_credentials)


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
    field in `~/.aws/config` is set to `profile`, so `awsprofile list`/
    `awsprofile status` can later report where those credentials came
    from (`awsprofile status` re-resolves the expiration directly from
    `boto3`/`botocore` via `_get_expiration` rather than storing it).
    After signing in, an
    informational note is always printed stating which profile the
    credentials were written to, and additionally that `"default"` was
    not changed if `export_profile` isn't `"default"` (since it's easy to
    assume every sign-in updates `"default"` when it doesn't).

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
        session_boto = _boto3_session(profile)

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
            echo_time_diff = int(time_diff.total_seconds() // 60)
            click.echo(f"Session valid, {echo_time_diff} minutes left", err=False)
    else:
        click.echo("Session valid", err=False)

    if export_profile == "default":
        click.echo(f"Note: credentials written to '{export_profile}'.", err=False)
    else:
        click.echo(f"Note: credentials written to '{export_profile}' - 'default' was not changed.", err=False)
