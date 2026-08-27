"""Tests for `awsprofile.cli` - the click command wiring.

These tests use `click.testing.CliRunner` to invoke each command and
monkeypatch the (lazily-imported) underlying functions from
`export_credentials.py`/`create_credentials.py`/`prerequisites.py`, so they
only verify the CLI wiring (option/argument parsing, defaults, and which
function gets called with which arguments) - the underlying behaviour is
covered by `test_export_credentials.py`, `test_create_credentials.py` and
`test_prerequisites.py`.
"""

import datetime

from click.testing import CliRunner

from awsprofile.cli import cli


def invoke(*args):
    return CliRunner().invoke(cli, list(args))


class TestSignInShortcuts:
    def test_dev_signs_in_with_dev_profile(self, monkeypatch):
        calls = []
        monkeypatch.setattr("awsprofile.export_credentials._export_credentials", lambda **kw: calls.append(kw))

        result = invoke("dev")

        assert result.exit_code == 0
        assert calls == [{"profile": "dev", "force_refresh": False}]

    def test_dev_passes_through_refresh_flag(self, monkeypatch):
        calls = []
        monkeypatch.setattr("awsprofile.export_credentials._export_credentials", lambda **kw: calls.append(kw))

        result = invoke("dev", "--refresh")

        assert result.exit_code == 0
        assert calls == [{"profile": "dev", "force_refresh": True}]

    def test_prod_signs_in_with_prod_profile(self, monkeypatch):
        calls = []
        monkeypatch.setattr("awsprofile.export_credentials._export_credentials", lambda **kw: calls.append(kw))

        result = invoke("prod")

        assert result.exit_code == 0
        assert calls == [{"profile": "prod", "force_refresh": False}]

    def test_prod_passes_through_refresh_flag(self, monkeypatch):
        calls = []
        monkeypatch.setattr("awsprofile.export_credentials._export_credentials", lambda **kw: calls.append(kw))

        result = invoke("prod", "-r")

        assert result.exit_code == 0
        assert calls == [{"profile": "prod", "force_refresh": True}]

    def test_integration_signs_in_with_integration_profile(self, monkeypatch):
        calls = []
        monkeypatch.setattr("awsprofile.export_credentials._export_credentials", lambda **kw: calls.append(kw))

        result = invoke("integration")

        assert result.exit_code == 0
        assert calls == [{"profile": "integration", "force_refresh": False}]

    def test_integration_passes_through_refresh_flag(self, monkeypatch):
        calls = []
        monkeypatch.setattr("awsprofile.export_credentials._export_credentials", lambda **kw: calls.append(kw))

        result = invoke("integration", "--refresh")

        assert result.exit_code == 0
        assert calls == [{"profile": "integration", "force_refresh": True}]

    def test_bedrock_signs_in_to_bedrockonly_export_profile(self, monkeypatch):
        calls = []
        monkeypatch.setattr("awsprofile.export_credentials._export_credentials", lambda **kw: calls.append(kw))

        result = invoke("bedrock")

        assert result.exit_code == 0
        assert calls == [{"profile": "bedrock", "export_profile": "bedrockonly", "force_refresh": False}]

    def test_bedrock_passes_through_refresh_flag(self, monkeypatch):
        calls = []
        monkeypatch.setattr("awsprofile.export_credentials._export_credentials", lambda **kw: calls.append(kw))

        result = invoke("bedrock", "--refresh")

        assert result.exit_code == 0
        assert calls == [{"profile": "bedrock", "export_profile": "bedrockonly", "force_refresh": True}]


class TestProfileCommand:
    def test_defaults_to_dev_and_default(self, monkeypatch):
        calls = []
        monkeypatch.setattr("awsprofile.export_credentials._export_credentials", lambda **kw: calls.append(kw))

        result = invoke("profile")

        assert result.exit_code == 0
        assert calls == [{"profile": "dev", "export_profile": "default", "force_refresh": False}]

    def test_accepts_explicit_profile_and_export_profile(self, monkeypatch):
        calls = []
        monkeypatch.setattr("awsprofile.export_credentials._export_credentials", lambda **kw: calls.append(kw))

        result = invoke("profile", "prod", "bedrockonly")

        assert result.exit_code == 0
        assert calls == [{"profile": "prod", "export_profile": "bedrockonly", "force_refresh": False}]

    def test_passes_through_refresh_flag(self, monkeypatch):
        calls = []
        monkeypatch.setattr("awsprofile.export_credentials._export_credentials", lambda **kw: calls.append(kw))

        result = invoke("profile", "prod", "bedrockonly", "--refresh")

        assert result.exit_code == 0
        assert calls == [{"profile": "prod", "export_profile": "bedrockonly", "force_refresh": True}]


class TestListCommand:
    def test_prints_assume_role_profiles_with_aliases_and_credential_profiles(self, monkeypatch):
        monkeypatch.setattr(
            "awsprofile.export_credentials._dict_aliases",
            lambda: ({"dev": "assume-ds-role-dev-poweraccess"}, ["assume-ds-role-dev-poweraccess", "default"]),
        )
        monkeypatch.setattr(
            "awsprofile.export_credentials._dict_credentials_profiles",
            lambda: {"default": "assume-ds-role-dev-poweraccess"},
        )

        result = invoke("list")

        assert result.exit_code == 0
        assert "assume-ds-role-dev-poweraccess (dev)" in result.output
        assert "default (assume-ds-role-dev-poweraccess)" in result.output


class TestStatusCommand:
    def test_prints_source_profile_alias_and_expiration_for_each_export_profile(self, monkeypatch):
        monkeypatch.setattr(
            "awsprofile.export_credentials._dict_aliases",
            lambda: ({"dev": "assume-ds-role-dev-poweraccess"}, ["assume-ds-role-dev-poweraccess", "default"]),
        )
        monkeypatch.setattr(
            "awsprofile.export_credentials._dict_credentials_profiles",
            lambda: {"default": "assume-ds-role-dev-poweraccess"},
        )
        monkeypatch.setattr(
            "awsprofile.export_credentials._get_expiration",
            lambda profile: datetime.datetime(2099, 1, 1, tzinfo=datetime.UTC),
        )

        result = invoke("status")

        assert result.exit_code == 0
        assert "default: signed in from assume-ds-role-dev-poweraccess (dev) - expires in" in result.output

    def test_prints_no_expiration_recorded_when_expiration_missing(self, monkeypatch):
        monkeypatch.setattr("awsprofile.export_credentials._dict_aliases", lambda: ({}, ["default"]))
        monkeypatch.setattr(
            "awsprofile.export_credentials._dict_credentials_profiles",
            lambda: {"default": "assume-ds-role-dev-poweraccess"},
        )
        monkeypatch.setattr("awsprofile.export_credentials._get_expiration", lambda profile: None)

        result = invoke("status")

        assert result.exit_code == 0
        assert "default: signed in from assume-ds-role-dev-poweraccess - no expiration recorded" in result.output

    def test_prints_expired_when_expiration_is_in_the_past(self, monkeypatch):
        monkeypatch.setattr("awsprofile.export_credentials._dict_aliases", lambda: ({}, ["default"]))
        monkeypatch.setattr(
            "awsprofile.export_credentials._dict_credentials_profiles",
            lambda: {"default": "assume-ds-role-dev-poweraccess"},
        )
        monkeypatch.setattr(
            "awsprofile.export_credentials._get_expiration",
            lambda profile: datetime.datetime(2000, 1, 1, tzinfo=datetime.UTC),
        )

        result = invoke("status")

        assert result.exit_code == 0
        assert "expired" in result.output
        assert "ago" in result.output

    def test_prints_message_when_no_profiles_have_credentials(self, monkeypatch):
        monkeypatch.setattr("awsprofile.export_credentials._dict_aliases", lambda: ({}, []))
        monkeypatch.setattr("awsprofile.export_credentials._dict_credentials_profiles", lambda: {})

        result = invoke("status")

        assert result.exit_code == 0
        assert "No profiles currently hold exported credentials." in result.output


class TestClearCommand:
    def test_defaults_to_default_profile(self, monkeypatch):
        calls = []
        monkeypatch.setattr("awsprofile.export_credentials._clear_credentials", lambda *args: calls.append(args))

        result = invoke("clear")

        assert result.exit_code == 0
        assert calls == [("default",)]

    def test_accepts_explicit_profile(self, monkeypatch):
        calls = []
        monkeypatch.setattr("awsprofile.export_credentials._clear_credentials", lambda *args: calls.append(args))

        result = invoke("clear", "bedrockonly")

        assert result.exit_code == 0
        assert calls == [("bedrockonly",)]


class TestSetCommand:
    def test_calls_set_alias_with_alias_and_profile(self, monkeypatch):
        calls = []
        monkeypatch.setattr("awsprofile.export_credentials._set_alias", lambda *args: calls.append(args))

        result = invoke("set", "assume-ds-role-dev-readonly", "devr")

        assert result.exit_code == 0
        assert calls == [("devr", "assume-ds-role-dev-readonly")]


class TestInitCommand:
    def test_checks_prerequisites_before_writing_configuration(self, monkeypatch):
        calls = []
        monkeypatch.setattr(
            "awsprofile.prerequisites._check_prerequisites", lambda: calls.append("check_prerequisites")
        )
        monkeypatch.setattr(
            "awsprofile.create_credentials._set_default_configuration",
            lambda *args: calls.append(("set_default_configuration", args)),
        )

        result = invoke(
            "init",
            "--email",
            "jane.doe@example.com",
            "--access-key",
            "AKIA123",
            "--secret-key",
            "SECRET123",
            "--mfa-suffix",
            "-work-phone",
        )

        assert result.exit_code == 0
        assert calls[0] == "check_prerequisites"
        assert calls[1] == (
            "set_default_configuration",
            ("jane.doe@example.com", "AKIA123", "SECRET123", None, "-work-phone"),
        )

    def test_mfa_option_is_passed_through(self, monkeypatch):
        calls = []
        monkeypatch.setattr("awsprofile.prerequisites._check_prerequisites", lambda: None)
        monkeypatch.setattr(
            "awsprofile.create_credentials._set_default_configuration",
            lambda *args: calls.append(args),
        )

        result = invoke("init", "--mfa", "jane.doe@example.com-phone")

        assert result.exit_code == 0
        assert calls == [(None, None, None, "jane.doe@example.com-phone", None)]


class TestHelpAndVersion:
    def test_top_level_help(self):
        result = invoke("--help")
        assert result.exit_code == 0
        assert "manage aws credentials" in result.output.lower()

    def test_top_level_version(self):
        result = invoke("--version")
        assert result.exit_code == 0
        assert "awsprofile" in result.output

    def test_every_command_help_succeeds(self):
        for command in ("dev", "prod", "integration", "bedrock", "profile", "list", "status", "clear", "set", "init"):
            result = invoke(command, "--help")
            assert result.exit_code == 0, f"{command} --help failed: {result.output}"
