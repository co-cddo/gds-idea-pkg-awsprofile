"""Tests for awsprofile.cli."""

from unittest.mock import patch

from click.testing import CliRunner

from awsprofile.cli import cli


def test_init_rejects_mfa_serial_and_mfa_suffix_together():
    runner = CliRunner()

    result = runner.invoke(cli, ["init", "--mfa-serial", "arn:aws:iam::123456789012:mfa/foo", "--mfa-suffix", "bar"])

    assert result.exit_code != 0
    assert "mutually exclusive" in result.output


@patch("awsprofile.create_credentials._set_default_configuration")
@patch("awsprofile.prerequisites._check_prerequisites")
def test_init_passes_mfa_options_through(mock_check_prerequisites, mock_set_default_configuration):
    runner = CliRunner()

    result = runner.invoke(cli, ["init", "--mfa-suffix", "jane.doe"])

    assert result.exit_code == 0
    mock_check_prerequisites.assert_called_once()
    mock_set_default_configuration.assert_called_once_with(None, None, None, None, "jane.doe")
