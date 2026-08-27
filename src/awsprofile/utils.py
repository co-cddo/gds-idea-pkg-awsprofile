"""Low-level helpers shared across the package.

Configparser-based helpers used to write directly to `~/.aws/config` and
`~/.aws/credentials`, without shelling out to the AWS CLI.
"""

import configparser
import os


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
