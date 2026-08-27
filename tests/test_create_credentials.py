"""Tests for `awsprofile.create_credentials`."""

import configparser

import pytest

from awsprofile.create_credentials import _set_default_configuration


def _read(path):
    config = configparser.RawConfigParser()
    config.read(path)
    return config


class TestSetDefaultConfiguration:
    def test_writes_common_fields_for_every_profile_with_no_optional_args(self, aws_home):
        _set_default_configuration()

        config = _read(aws_home.config)
        assert config.get("default", "region") == "eu-west-2"
        assert config.get("default", "output") == "json"
        assert config.get("default", "duration_seconds") == "28800"
        assert config.get("profile assume-ds-role-dev-poweraccess", "alias") == "dev"
        assert config.get("profile assume-ds-role-dev-poweraccess", "source_profile") == "gds-users"

        # Nothing that depends on email/mfa/access-secret keys should be set.
        assert not config.has_option("profile assume-ds-role-dev-poweraccess", "role_arn")
        assert not config.has_option("profile assume-ds-role-dev-poweraccess", "mfa_serial")
        assert not config.has_option("gds-users", "mfa_serial")
        assert not aws_home.credentials.exists()

    def test_email_sets_role_arn_using_prefix(self, aws_home):
        _set_default_configuration(email="jane.doe@example.com")

        config = _read(aws_home.config)
        assert (
            config.get("profile assume-ds-role-dev-poweraccess", "role_arn")
            == "arn:aws:iam::992382722318:role/jane.doe-poweraccess"
        )
        assert (
            config.get("profile assume-ds-role-prod-admin", "role_arn")
            == "arn:aws:iam::588077357019:role/jane.doe-admin"
        )
        assert (
            config.get("profile assume-ds-role-integration-admin", "role_arn")
            == "arn:aws:iam::539502489680:role/jane.doe-admin"
        )

    def test_mfa_sets_mfa_serial_on_gds_users_and_role_profiles(self, aws_home):
        _set_default_configuration(mfa="jane.doe@example.com")

        config = _read(aws_home.config)
        assert config.get("profile gds-users", "mfa_serial") == "arn:aws:iam::622626885786:mfa/jane.doe@example.com"
        assert (
            config.get("profile assume-ds-role-dev-poweraccess", "mfa_serial")
            == "arn:aws:iam::622626885786:mfa/jane.doe@example.com"
        )

    def test_mfa_suffix_combines_with_email_to_form_mfa_serial(self, aws_home):
        _set_default_configuration(email="jane.doe@example.com", mfa_suffix="-work-phone")

        config = _read(aws_home.config)
        assert (
            config.get("profile gds-users", "mfa_serial")
            == "arn:aws:iam::622626885786:mfa/jane.doe@example.com-work-phone"
        )

    def test_mfa_suffix_takes_precedence_over_mfa(self, aws_home):
        _set_default_configuration(email="jane.doe@example.com", mfa="ignored-value", mfa_suffix="-work-phone")

        config = _read(aws_home.config)
        assert (
            config.get("profile gds-users", "mfa_serial")
            == "arn:aws:iam::622626885786:mfa/jane.doe@example.com-work-phone"
        )

    def test_mfa_suffix_without_email_raises(self, aws_home):
        with pytest.raises(ValueError, match="mfa_suffix requires email"):
            _set_default_configuration(mfa_suffix="-work-phone")

        assert not aws_home.config.exists()

    def test_access_and_secret_key_are_written_to_credentials_not_config(self, aws_home):
        _set_default_configuration(access_key="AKIA123", secret_key="SECRET123")

        creds = _read(aws_home.credentials)
        assert creds.sections() == ["gds-users"]
        assert creds.get("gds-users", "aws_access_key_id") == "AKIA123"
        assert creds.get("gds-users", "aws_secret_access_key") == "SECRET123"

        config = _read(aws_home.config)
        assert not config.has_option("gds-users", "aws_access_key_id")
        assert not config.has_option("gds-users", "aws_secret_access_key")

    def test_all_options_together(self, aws_home):
        _set_default_configuration(
            email="jane.doe@example.com",
            access_key="AKIA123",
            secret_key="SECRET123",
            mfa_suffix="-work-phone",
        )

        config = _read(aws_home.config)
        creds = _read(aws_home.credentials)

        assert (
            config.get("profile assume-ds-role-dev-poweraccess", "role_arn")
            == "arn:aws:iam::992382722318:role/jane.doe-poweraccess"
        )
        assert (
            config.get("profile assume-ds-role-dev-poweraccess", "mfa_serial")
            == "arn:aws:iam::622626885786:mfa/jane.doe@example.com-work-phone"
        )
        assert creds.get("gds-users", "aws_access_key_id") == "AKIA123"

    def test_every_expected_profile_is_written(self, aws_home):
        _set_default_configuration()

        config = _read(aws_home.config)
        expected_sections = {
            "default",
            "profile gds-users",
            "profile bedrockonly",
            "profile assume-ds-role-prod-admin",
            "profile assume-ds-role-prod-poweraccess",
            "profile assume-ds-role-prod-readonly",
            "profile assume-ds-role-dev-admin",
            "profile assume-ds-role-dev-poweraccess",
            "profile assume-ds-role-dev-readonly",
            "profile assume-ds-role-dev-bedrockonly",
            "profile assume-ds-role-integration-admin",
        }
        assert set(config.sections()) == expected_sections
