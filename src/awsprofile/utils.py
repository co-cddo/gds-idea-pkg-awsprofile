"""Low-level helpers shared across the package.

Configparser-based helpers used to write directly to `~/.aws/config` and
`~/.aws/credentials`, without shelling out to the AWS CLI, plus
`botocore`/`boto3` session and credentials-cache helpers used to resolve
and inspect temporary session credentials.
"""

import configparser
import datetime
import os

import boto3
import botocore.session
import dateutil.parser
from botocore import credentials


def _config_set(profile: str, key: str, value: str) -> None:
    """Set a key/value pair for a profile in the aws config file (~/.aws/config).

    Mirrors `aws configure set <key> <value> --profile <profile>` for keys that
    the AWS CLI stores in the config file (e.g. alias, credentials_profile).
    Creates the `~/.aws/config` file and/or the profile's section if either
    doesn't already exist.

    Args:
        profile: Profile name to set the value for.
        key: Config key to set.
        value: Value to set.

    Example:
        >>> _config_set("dev", "alias", "d")
        # Writes `alias = d` under `[profile dev]` in ~/.aws/config.
    """
    config_path = os.path.expanduser("~/.aws/config")
    config = configparser.RawConfigParser()
    config.read(config_path)

    section = "default" if profile == "default" else f"profile {profile}"
    if not config.has_section(section):
        config.add_section(section)
    config.set(section, key, value)

    with open(config_path, "w") as config_file:
        config.write(config_file)


def _credentials_set(profile: str, key: str, value: str) -> None:
    """Set a key/value pair for a profile in the aws credentials file (~/.aws/credentials).

    Mirrors `aws configure set <key> <value> --profile <profile>` for keys that
    the AWS CLI stores in the credentials file (e.g. aws_access_key_id,
    aws_secret_access_key, aws_session_token). Creates the `~/.aws/credentials`
    file and/or the profile's section if either doesn't already exist, and
    restricts the file's permissions to `0o600` (owner read/write only) to
    match the AWS CLI's own handling of this file, since it can contain
    long-lived secrets.

    Args:
        profile: Profile name to set the value for. Unlike `_config_set`,
            this is used as the section name directly (no `profile ` prefix,
            even for non-`default` profiles) - this matches how the AWS CLI
            itself lays out `~/.aws/credentials`.
        key: Credentials key to set.
        value: Value to set.

    Example:
        >>> _credentials_set("default", "aws_access_key_id", "AKIA...")
        # Writes `aws_access_key_id = AKIA...` under `[default]` in
        # ~/.aws/credentials, and chmods the file to 0o600.
    """
    credentials_path = os.path.expanduser("~/.aws/credentials")
    config = configparser.RawConfigParser()
    config.read(credentials_path)

    if not config.has_section(profile):
        config.add_section(profile)
    config.set(profile, key, value)

    with open(credentials_path, "w") as credentials_file:
        config.write(credentials_file)
    os.chmod(credentials_path, 0o600)


def _boto3_session(profile: str) -> boto3.Session:
    """Build a boto3 session for `profile`, caching assume-role results.

    Shared by `awsprofile.export_credentials._export_credentials` (to sign
    in) and `awsprofile.export_credentials._get_expiration` (to inspect
    currently resolved credentials without necessarily forcing a fresh
    sign-in) so both use the exact same caching behaviour as the AWS CLI
    (`~/.aws/cli/cache`).

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


def _format_expiration(expiration: datetime.datetime | None) -> str:
    """Turn a credentials expiration time into a human-readable status.

    Args:
        expiration: A profile's credentials expiration time, as returned by
            `awsprofile.export_credentials._get_expiration`, or `None` if
            the profile's credentials have no known expiration (e.g.
            static/long-lived keys).

    Returns:
        A short human-readable description, e.g. `"expires in 42 minutes"`,
        `"expired 3 minutes ago"` or `"no expiration recorded"`.
    """
    if expiration is None:
        return "no expiration recorded"

    time_diff = expiration - datetime.datetime.now(datetime.UTC)
    if time_diff > datetime.timedelta():
        minutes_left = int(time_diff.total_seconds() // 60)
        return f"expires in {minutes_left} minutes"

    minutes_ago = int(-time_diff.total_seconds() // 60)
    return f"expired {minutes_ago} minutes ago"
