"""Tests for awsprofile.create_credentials._set_default_configuration."""

from unittest.mock import patch

from awsprofile.create_credentials import _set_default_configuration

ORG_ACCOUNT = "622626885786"

ASSUME_ROLE_PROFILES = [
    "assume-ds-role-prod-admin",
    "assume-ds-role-prod-poweraccess",
    "assume-ds-role-prod-readonly",
    "assume-ds-role-dev-admin",
    "assume-ds-role-dev-poweraccess",
    "assume-ds-role-dev-readonly",
    "assume-ds-role-dev-bedrockonly",
    "assume-ds-role-integration-admin",
]


def _configured_fields(mock_run) -> dict[str, str]:
    """Collect key/value pairs from `aws configure set ...` calls into a dict."""
    fields = {}
    for call in mock_run.call_args_list:
        args = call.args[0]
        assert args[:3] == ["aws", "configure", "set"]
        _, _, _, key, value = args
        fields[key] = value
    return fields


@patch("awsprofile.create_credentials.subprocess.run")
def test_email_only_derives_mfa_serial_from_email(mock_run):
    _set_default_configuration(email="jane.doe@example.com")

    fields = _configured_fields(mock_run)

    expected_mfa_serial = f"arn:aws:iam::{ORG_ACCOUNT}:mfa/jane.doe@example.com"
    assert fields["profile.gds-users.mfa_serial"] == expected_mfa_serial
    for profile in ASSUME_ROLE_PROFILES:
        assert fields[f"profile.{profile}.mfa_serial"] == expected_mfa_serial
        assert f"profile.{profile}.role_arn" in fields


@patch("awsprofile.create_credentials.subprocess.run")
def test_mfa_serial_overrides_full_arn_without_email(mock_run):
    override = "arn:aws:iam::999999999999:mfa/custom-device"

    _set_default_configuration(email=None, mfa_serial=override)

    fields = _configured_fields(mock_run)

    assert fields["profile.gds-users.mfa_serial"] == override
    for profile in ASSUME_ROLE_PROFILES:
        assert fields[f"profile.{profile}.mfa_serial"] == override
        assert f"profile.{profile}.role_arn" not in fields


@patch("awsprofile.create_credentials.subprocess.run")
def test_mfa_suffix_overrides_device_name_without_email(mock_run):
    _set_default_configuration(email=None, mfa_suffix="jane.doe")

    fields = _configured_fields(mock_run)

    expected_mfa_serial = f"arn:aws:iam::{ORG_ACCOUNT}:mfa/jane.doe"
    assert fields["profile.gds-users.mfa_serial"] == expected_mfa_serial
    for profile in ASSUME_ROLE_PROFILES:
        assert fields[f"profile.{profile}.mfa_serial"] == expected_mfa_serial
        assert f"profile.{profile}.role_arn" not in fields


@patch("awsprofile.create_credentials.subprocess.run")
def test_mfa_serial_takes_precedence_over_mfa_suffix_and_email(mock_run):
    override = "arn:aws:iam::999999999999:mfa/custom-device"

    _set_default_configuration(email="jane.doe@example.com", mfa_serial=override, mfa_suffix="unused")

    fields = _configured_fields(mock_run)

    assert fields["profile.gds-users.mfa_serial"] == override
    for profile in ASSUME_ROLE_PROFILES:
        assert fields[f"profile.{profile}.mfa_serial"] == override
    # email is still used for role_arn even when overriding mfa_serial
    assert fields["profile.assume-ds-role-prod-admin.role_arn"] == "arn:aws:iam::588077357019:role/jane.doe-admin"


@patch("awsprofile.create_credentials.subprocess.run")
def test_no_mfa_related_options_sets_no_mfa_serial(mock_run):
    _set_default_configuration()

    fields = _configured_fields(mock_run)

    assert "profile.gds-users.mfa_serial" not in fields
    for profile in ASSUME_ROLE_PROFILES:
        assert f"profile.{profile}.mfa_serial" not in fields
        assert f"profile.{profile}.role_arn" not in fields
