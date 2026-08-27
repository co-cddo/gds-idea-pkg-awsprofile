"""Tests for `awsprofile.utils` (the configparser helpers)."""

import configparser
import os
import stat

from awsprofile.utils import _config_set, _credentials_set


def _read(path):
    config = configparser.RawConfigParser()
    config.read(path)
    return config


class TestConfigSet:
    def test_creates_file_and_writes_under_default_section(self, aws_home):
        _config_set("default", "region", "eu-west-2")

        assert aws_home.config.exists()
        config = _read(aws_home.config)
        assert config.sections() == ["default"]
        assert config.get("default", "region") == "eu-west-2"

    def test_non_default_profile_uses_profile_prefixed_section(self, aws_home):
        _config_set("dev", "alias", "d")

        config = _read(aws_home.config)
        assert config.sections() == ["profile dev"]
        assert config.get("profile dev", "alias") == "d"

    def test_updating_a_key_does_not_drop_other_keys_or_sections(self, aws_home):
        _config_set("dev", "alias", "d")
        _config_set("dev", "region", "eu-west-2")
        _config_set("prod", "alias", "p")

        config = _read(aws_home.config)
        assert set(config.sections()) == {"profile dev", "profile prod"}
        assert config.get("profile dev", "alias") == "d"
        assert config.get("profile dev", "region") == "eu-west-2"
        assert config.get("profile prod", "alias") == "p"

    def test_overwrites_an_existing_value(self, aws_home):
        _config_set("dev", "alias", "old")
        _config_set("dev", "alias", "new")

        config = _read(aws_home.config)
        assert config.get("profile dev", "alias") == "new"


class TestCredentialsSet:
    def test_creates_file_and_uses_profile_name_directly_as_section(self, aws_home):
        _credentials_set("default", "aws_access_key_id", "AKIA123")

        assert aws_home.credentials.exists()
        config = _read(aws_home.credentials)
        assert config.sections() == ["default"]
        assert config.get("default", "aws_access_key_id") == "AKIA123"

    def test_non_default_profile_section_has_no_prefix(self, aws_home):
        _credentials_set("gds-users", "aws_access_key_id", "AKIA123")

        config = _read(aws_home.credentials)
        assert config.sections() == ["gds-users"]

    def test_restricts_file_permissions_to_owner_read_write(self, aws_home):
        _credentials_set("default", "aws_access_key_id", "AKIA123")

        mode = stat.S_IMODE(os.stat(aws_home.credentials).st_mode)
        assert mode == 0o600

    def test_updating_a_key_does_not_drop_other_keys(self, aws_home):
        _credentials_set("gds-users", "aws_access_key_id", "AKIA1")
        _credentials_set("gds-users", "aws_secret_access_key", "SECRET1")

        config = _read(aws_home.credentials)
        assert config.get("gds-users", "aws_access_key_id") == "AKIA1"
        assert config.get("gds-users", "aws_secret_access_key") == "SECRET1"

    def test_overwrites_an_existing_value(self, aws_home):
        _credentials_set("default", "aws_session_token", "old-token")
        _credentials_set("default", "aws_session_token", "new-token")

        config = _read(aws_home.credentials)
        assert config.get("default", "aws_session_token") == "new-token"
