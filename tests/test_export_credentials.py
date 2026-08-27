"""Tests for `awsprofile.export_credentials`."""

import configparser
import datetime

import botocore.exceptions
import pytest

from awsprofile import export_credentials as ec


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
    monkeypatch.setattr(ec.botocore.session, "Session", _FakeBotocoreSession)


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


class TestExportCredentials:
    def test_writes_credentials_and_credentials_profile_to_default(self, aws_home, monkeypatch, capsys):
        _write_config(aws_home.config, {"profile assume-ds-role-dev-readonly": {}})
        monkeypatch.setattr(ec.boto3, "Session", _fake_boto3_session_factory(_FakeCredentials()))

        ec._export_credentials("assume-ds-role-dev-readonly")

        creds = _read(aws_home.credentials)
        assert creds.get("default", "aws_access_key_id") == "AKIAFAKE"
        assert creds.get("default", "aws_secret_access_key") == "secretfake"
        assert creds.get("default", "aws_session_token") == "tokenfake"

        config = _read(aws_home.config)
        assert config.get("default", "credentials_profile") == "assume-ds-role-dev-readonly"

        assert "Session valid" in capsys.readouterr().out

    def test_resolves_alias_before_signing_in(self, aws_home, monkeypatch):
        _write_config(aws_home.config, {"profile assume-ds-role-dev-poweraccess": {"alias": "dev"}})
        monkeypatch.setattr(ec.boto3, "Session", _fake_boto3_session_factory(_FakeCredentials()))

        ec._export_credentials("dev")

        config = _read(aws_home.config)
        assert config.get("default", "credentials_profile") == "assume-ds-role-dev-poweraccess"

    def test_writes_to_custom_export_profile(self, aws_home, monkeypatch):
        _write_config(aws_home.config, {"profile assume-ds-role-dev-bedrockonly": {"alias": "bedrock"}})
        monkeypatch.setattr(ec.boto3, "Session", _fake_boto3_session_factory(_FakeCredentials()))

        ec._export_credentials("bedrock", export_profile="bedrockonly")

        creds = _read(aws_home.credentials)
        assert creds.sections() == ["bedrockonly"]
        config = _read(aws_home.config)
        assert config.get("profile bedrockonly", "credentials_profile") == "assume-ds-role-dev-bedrockonly"

    def test_reports_minutes_left_when_expiry_time_is_set(self, aws_home, monkeypatch, capsys):
        _write_config(aws_home.config, {"profile assume-ds-role-dev-readonly": {}})
        expiry = datetime.datetime.now(datetime.UTC) + datetime.timedelta(minutes=30)
        monkeypatch.setattr(ec.boto3, "Session", _fake_boto3_session_factory(_FakeCredentials(expiry_time=expiry)))

        ec._export_credentials("assume-ds-role-dev-readonly")

        assert "minutes left" in capsys.readouterr().out

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
        monkeypatch.setattr(ec.boto3, "Session", _fake_boto3_session_factory(raise_error=error))

        with pytest.raises(SystemExit) as exc_info:
            ec._export_credentials("assume-ds-role-dev-readonly")

        assert exc_info.value.code == 1
        assert "boom" in capsys.readouterr().err

    def test_exits_on_param_validation_error(self, aws_home, monkeypatch, capsys):
        _write_config(aws_home.config, {"profile assume-ds-role-dev-readonly": {}})
        error = botocore.exceptions.ParamValidationError(report="bad params")
        monkeypatch.setattr(ec.boto3, "Session", _fake_boto3_session_factory(raise_error=error))

        with pytest.raises(SystemExit) as exc_info:
            ec._export_credentials("assume-ds-role-dev-readonly")

        assert exc_info.value.code == 1
