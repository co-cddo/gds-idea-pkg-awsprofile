"""Tests for `awsprofile.export_credentials`."""

import configparser
import datetime

import botocore.exceptions
import pytest

from awsprofile import export_credentials as ec
from awsprofile import utils


def _write_config(path, sections):
    """Write a fake `~/.aws/config`-shaped file.

    Args:
        path: File to write to (e.g. `aws_home.config`).
        sections: Mapping of raw section name (e.g. `"default"` or
            `"profile dev"`) to a dict of key/value pairs for that section.
    """
    config = configparser.RawConfigParser()
    for section, fields in sections.items():
        config.add_section(section)
        for key, value in fields.items():
            config.set(section, key, value)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as config_file:
        config.write(config_file)


def _read(path):
    config = configparser.RawConfigParser()
    config.read(path)
    return config


class _FakeFrozenCredentials:
    def __init__(self, access_key, secret_key, token):
        self.access_key = access_key
        self.secret_key = secret_key
        self.token = token


class _FakeCredentials:
    """Stands in for the object returned by `boto3.Session.get_credentials()`."""

    def __init__(self, access_key="AKIAFAKE", secret_key="secretfake", token="tokenfake", expiry_time=None):
        self._frozen = _FakeFrozenCredentials(access_key, secret_key, token)
        if expiry_time is not None:
            # Only `botocore.credentials.RefreshableCredentials` (used for
            # assume-role/SSO) has this attribute - static credentials don't.
            self._expiry_time = expiry_time

    def get_frozen_credentials(self):
        return self._frozen


class _FakeAssumeRoleProvider:
    def __init__(self):
        self.cache = None


class _FakeCredentialProviderComponent:
    def __init__(self):
        self._provider = _FakeAssumeRoleProvider()

    def get_provider(self, name):
        return self._provider


class _FakeBotocoreSession:
    """Stands in for `botocore.session.Session`."""

    def __init__(self, profile=None):
        self.profile = profile

    def get_component(self, name):
        assert name == "credential_provider"
        return _FakeCredentialProviderComponent()


def _fake_boto3_session_factory(fake_credentials=None, raise_error=None):
    """Build a fake `boto3.Session` class that returns `fake_credentials` (or raises)."""

    class _FakeBoto3Session:
        def __init__(self, botocore_session=None):
            self.botocore_session = botocore_session

        def get_credentials(self):
            if raise_error is not None:
                raise raise_error
            return fake_credentials if fake_credentials is not None else _FakeCredentials()

    return _FakeBoto3Session


@pytest.fixture(autouse=True)
def _patch_botocore_session(monkeypatch):
    """Every `_export_credentials` test needs the botocore session faked out."""
    monkeypatch.setattr(utils.botocore.session, "Session", _FakeBotocoreSession)


class TestListProfiles:
    def test_combines_credentials_and_config_sections_deduplicated(self, aws_home):
        _write_config(aws_home.credentials, {"default": {"aws_access_key_id": "x"}, "gds-users": {}})
        _write_config(
            aws_home.config,
            {
                "default": {},
                "profile gds-users": {},
                "profile assume-ds-role-dev-readonly": {},
            },
        )

        profiles = ec._list_profiles()

        assert set(profiles) == {"default", "gds-users", "assume-ds-role-dev-readonly"}

    def test_no_files_returns_empty_list(self, aws_home):
        assert ec._list_profiles() == []


class TestDictAliases:
    def test_maps_alias_to_profile_and_lists_all_profiles(self, aws_home):
        _write_config(
            aws_home.config,
            {
                "default": {},
                "profile assume-ds-role-dev-readonly": {"alias": "devr"},
                "profile assume-ds-role-dev-poweraccess": {"alias": "dev"},
            },
        )

        aliases, profiles = ec._dict_aliases()

        assert aliases == {"devr": "assume-ds-role-dev-readonly", "dev": "assume-ds-role-dev-poweraccess"}
        assert set(profiles) == {"default", "assume-ds-role-dev-readonly", "assume-ds-role-dev-poweraccess"}

    def test_profiles_without_alias_are_listed_but_not_aliased(self, aws_home):
        _write_config(aws_home.config, {"profile gds-users": {}})

        aliases, profiles = ec._dict_aliases()

        assert aliases == {}
        assert profiles == ["gds-users"]

    def test_warns_on_duplicate_alias(self, aws_home, capsys):
        _write_config(
            aws_home.config,
            {"profile a": {"alias": "dup"}, "profile b": {"alias": "dup"}},
        )

        ec._dict_aliases()

        assert "duplicated alias" in capsys.readouterr().err


class TestDictCredentialsProfiles:
    def test_maps_export_profile_to_source_profile(self, aws_home):
        _write_config(
            aws_home.config,
            {
                "default": {"credentials_profile": "assume-ds-role-dev-poweraccess"},
                "profile assume-ds-role-dev-poweraccess": {},
            },
        )

        assert ec._dict_credentials_profiles() == {"default": "assume-ds-role-dev-poweraccess"}

    def test_profiles_without_credentials_profile_are_omitted(self, aws_home):
        _write_config(aws_home.config, {"default": {}})

        assert ec._dict_credentials_profiles() == {}


class TestGetExpiration:
    def test_returns_expiry_time_when_present(self, aws_home, monkeypatch):
        expiry = datetime.datetime.now(datetime.UTC) + datetime.timedelta(minutes=15)
        monkeypatch.setattr(utils.boto3, "Session", _fake_boto3_session_factory(_FakeCredentials(expiry_time=expiry)))

        assert ec._get_expiration("assume-ds-role-dev-readonly") == expiry

    def test_returns_none_for_static_credentials(self, aws_home, monkeypatch):
        monkeypatch.setattr(utils.boto3, "Session", _fake_boto3_session_factory(_FakeCredentials()))

        assert ec._get_expiration("gds-users") is None

    def test_returns_none_when_no_credentials_resolved(self, aws_home, monkeypatch):
        class _NoCredsSession:
            def __init__(self, botocore_session=None):
                pass

            def get_credentials(self):
                return None

        monkeypatch.setattr(utils.boto3, "Session", _NoCredsSession)

        assert ec._get_expiration("default") is None

    def test_returns_none_on_client_error(self, aws_home, monkeypatch):
        error = botocore.exceptions.ClientError({"Error": {"Code": "AccessDenied", "Message": "boom"}}, "AssumeRole")
        monkeypatch.setattr(utils.boto3, "Session", _fake_boto3_session_factory(raise_error=error))

        assert ec._get_expiration("assume-ds-role-dev-readonly") is None

    def test_returns_none_on_param_validation_error(self, aws_home, monkeypatch):
        error = botocore.exceptions.ParamValidationError(report="bad params")
        monkeypatch.setattr(utils.boto3, "Session", _fake_boto3_session_factory(raise_error=error))

        assert ec._get_expiration("assume-ds-role-dev-readonly") is None


class TestSetAlias:
    def test_sets_alias_on_existing_profile(self, aws_home):
        _write_config(aws_home.config, {"profile assume-ds-role-dev-readonly": {}})

        ec._set_alias("devr", "assume-ds-role-dev-readonly")

        aliases, _ = ec._dict_aliases()
        assert aliases == {"devr": "assume-ds-role-dev-readonly"}

    def test_exits_when_profile_does_not_exist(self, aws_home, capsys):
        _write_config(aws_home.config, {"profile assume-ds-role-dev-readonly": {}})

        with pytest.raises(SystemExit) as exc_info:
            ec._set_alias("devr", "does-not-exist")

        assert exc_info.value.code == 1
        assert "does not exist" in capsys.readouterr().err

    def test_exits_when_alias_already_in_use(self, aws_home, capsys):
        _write_config(
            aws_home.config,
            {
                "profile assume-ds-role-dev-readonly": {"alias": "devr"},
                "profile assume-ds-role-dev-poweraccess": {},
            },
        )

        with pytest.raises(SystemExit) as exc_info:
            ec._set_alias("devr", "assume-ds-role-dev-poweraccess")

        assert exc_info.value.code == 1
        assert "does exist" in capsys.readouterr().err


class TestClearCredentials:
    def test_clears_default_profile_by_default(self, aws_home, capsys):
        _write_config(aws_home.config, {"default": {"credentials_profile": "assume-ds-role-dev-readonly"}})
        _write_config(
            aws_home.credentials,
            {
                "default": {
                    "aws_access_key_id": "AKIAFAKE",
                    "aws_secret_access_key": "secretfake",
                    "aws_session_token": "tokenfake",
                }
            },
        )

        ec._clear_credentials()

        creds = _read(aws_home.credentials)
        assert creds.has_option("default", "aws_access_key_id") is False
        assert creds.has_option("default", "aws_secret_access_key") is False
        assert creds.has_option("default", "aws_session_token") is False
        config = _read(aws_home.config)
        assert config.has_option("default", "credentials_profile") is False

        assert "Cleared exported credentials from 'default'." in capsys.readouterr().out

    def test_clears_custom_export_profile(self, aws_home):
        _write_config(
            aws_home.config, {"profile bedrockonly": {"credentials_profile": "assume-ds-role-dev-bedrockonly"}}
        )
        _write_config(aws_home.credentials, {"bedrockonly": {"aws_access_key_id": "AKIAFAKE"}})

        ec._clear_credentials("bedrockonly")

        creds = _read(aws_home.credentials)
        assert creds.has_option("bedrockonly", "aws_access_key_id") is False
        config = _read(aws_home.config)
        assert config.has_option("profile bedrockonly", "credentials_profile") is False

    def test_leaves_other_profiles_untouched(self, aws_home):
        _write_config(
            aws_home.config,
            {
                "default": {"credentials_profile": "assume-ds-role-dev-readonly"},
                "profile bedrockonly": {"credentials_profile": "assume-ds-role-dev-bedrockonly", "alias": "keep-me"},
            },
        )
        _write_config(
            aws_home.credentials,
            {
                "default": {"aws_access_key_id": "AKIAFAKE"},
                "bedrockonly": {"aws_access_key_id": "AKIAOTHER"},
            },
        )

        ec._clear_credentials("default")

        creds = _read(aws_home.credentials)
        assert creds.get("bedrockonly", "aws_access_key_id") == "AKIAOTHER"
        config = _read(aws_home.config)
        assert config.get("profile bedrockonly", "credentials_profile") == "assume-ds-role-dev-bedrockonly"
        assert config.get("profile bedrockonly", "alias") == "keep-me"

    def test_no_op_when_nothing_was_ever_exported(self, aws_home, capsys):
        ec._clear_credentials()

        assert not aws_home.credentials.exists()
        out = capsys.readouterr().out
        assert "Cleared exported credentials from 'default'." in out

    def test_writes_credentials_and_credentials_profile_to_default(self, aws_home, monkeypatch, capsys):
        _write_config(aws_home.config, {"profile assume-ds-role-dev-readonly": {}})
        monkeypatch.setattr(utils.boto3, "Session", _fake_boto3_session_factory(_FakeCredentials()))

        ec._export_credentials("assume-ds-role-dev-readonly")

        creds = _read(aws_home.credentials)
        assert creds.get("default", "aws_access_key_id") == "AKIAFAKE"
        assert creds.get("default", "aws_secret_access_key") == "secretfake"
        assert creds.get("default", "aws_session_token") == "tokenfake"

        config = _read(aws_home.config)
        assert config.get("default", "credentials_profile") == "assume-ds-role-dev-readonly"

        out = capsys.readouterr().out
        assert "Session valid" in out
        assert "Note: credentials written to 'default'." in out
        assert "was not changed" not in out

    def test_resolves_alias_before_signing_in(self, aws_home, monkeypatch):
        _write_config(aws_home.config, {"profile assume-ds-role-dev-poweraccess": {"alias": "dev"}})
        monkeypatch.setattr(utils.boto3, "Session", _fake_boto3_session_factory(_FakeCredentials()))

        ec._export_credentials("dev")

        config = _read(aws_home.config)
        assert config.get("default", "credentials_profile") == "assume-ds-role-dev-poweraccess"

    def test_writes_to_custom_export_profile(self, aws_home, monkeypatch, capsys):
        _write_config(aws_home.config, {"profile assume-ds-role-dev-bedrockonly": {"alias": "bedrock"}})
        monkeypatch.setattr(utils.boto3, "Session", _fake_boto3_session_factory(_FakeCredentials()))

        ec._export_credentials("bedrock", export_profile="bedrockonly")

        creds = _read(aws_home.credentials)
        assert creds.sections() == ["bedrockonly"]
        config = _read(aws_home.config)
        assert config.get("profile bedrockonly", "credentials_profile") == "assume-ds-role-dev-bedrockonly"

        out = capsys.readouterr().out
        assert "Note: credentials written to 'bedrockonly' - 'default' was not changed." in out

    def test_reports_minutes_left_when_expiry_time_is_set(self, aws_home, monkeypatch, capsys):
        _write_config(aws_home.config, {"profile assume-ds-role-dev-readonly": {}})
        expiry = datetime.datetime.now(datetime.UTC) + datetime.timedelta(minutes=30)
        monkeypatch.setattr(utils.boto3, "Session", _fake_boto3_session_factory(_FakeCredentials(expiry_time=expiry)))

        ec._export_credentials("assume-ds-role-dev-readonly")

        assert "minutes left" in capsys.readouterr().out

    def test_status_to_stderr_sends_informational_messages_to_stderr(self, aws_home, monkeypatch, capsys):
        _write_config(aws_home.config, {"profile assume-ds-role-dev-readonly": {}})
        monkeypatch.setattr(utils.boto3, "Session", _fake_boto3_session_factory(_FakeCredentials()))

        ec._export_credentials("assume-ds-role-dev-readonly", status_to_stderr=True)

        out, err = capsys.readouterr()
        assert out == ""
        assert "Session valid" in err
        assert "Note: credentials written to 'default'." in err

    def test_rejects_assume_role_export_profile(self, aws_home):
        with pytest.raises(SystemExit) as exc_info:
            ec._export_credentials("dev", export_profile="assume-ds-role-dev-readonly")

        assert exc_info.value.code == 1

    def test_rejects_gds_users_export_profile(self, aws_home):
        with pytest.raises(SystemExit) as exc_info:
            ec._export_credentials("dev", export_profile="gds-users")

        assert exc_info.value.code == 1

    def test_exits_when_profile_or_alias_does_not_exist(self, aws_home, capsys):
        _write_config(aws_home.config, {"profile assume-ds-role-dev-readonly": {}})

        with pytest.raises(SystemExit) as exc_info:
            ec._export_credentials("does-not-exist")

        assert exc_info.value.code == 1
        assert "does not exist" in capsys.readouterr().err

    def test_exits_on_client_error(self, aws_home, monkeypatch, capsys):
        _write_config(aws_home.config, {"profile assume-ds-role-dev-readonly": {}})
        error = botocore.exceptions.ClientError({"Error": {"Code": "AccessDenied", "Message": "boom"}}, "AssumeRole")
        monkeypatch.setattr(utils.boto3, "Session", _fake_boto3_session_factory(raise_error=error))

        with pytest.raises(SystemExit) as exc_info:
            ec._export_credentials("assume-ds-role-dev-readonly")

        assert exc_info.value.code == 1
        assert "boom" in capsys.readouterr().err

    def test_exits_on_param_validation_error(self, aws_home, monkeypatch, capsys):
        _write_config(aws_home.config, {"profile assume-ds-role-dev-readonly": {}})
        error = botocore.exceptions.ParamValidationError(report="bad params")
        monkeypatch.setattr(utils.boto3, "Session", _fake_boto3_session_factory(raise_error=error))

        with pytest.raises(SystemExit) as exc_info:
            ec._export_credentials("assume-ds-role-dev-readonly")

        assert exc_info.value.code == 1

    def test_does_not_invalidate_cache_by_default(self, aws_home, monkeypatch):
        _write_config(aws_home.config, {"profile assume-ds-role-dev-readonly": {}})
        monkeypatch.setattr(utils.boto3, "Session", _fake_boto3_session_factory(_FakeCredentials()))
        calls = []
        monkeypatch.setattr(ec, "_invalidate_cached_credentials", lambda creds: calls.append(creds))

        ec._export_credentials("assume-ds-role-dev-readonly")

        assert calls == []

    def test_force_refresh_invalidates_cache_before_freezing(self, aws_home, monkeypatch):
        _write_config(aws_home.config, {"profile assume-ds-role-dev-readonly": {}})
        fake_credentials = _FakeCredentials()
        monkeypatch.setattr(utils.boto3, "Session", _fake_boto3_session_factory(fake_credentials))
        calls = []
        monkeypatch.setattr(ec, "_invalidate_cached_credentials", lambda creds: calls.append(creds))

        ec._export_credentials("assume-ds-role-dev-readonly", force_refresh=True)

        assert calls == [fake_credentials]
