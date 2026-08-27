"""Tests for `awsprofile.utils` (the configparser helpers)."""

import configparser
import datetime
import json
import os
import stat

import botocore.credentials

from awsprofile.utils import (
    _boto3_session,
    _cached_credential_fetcher,
    _config_set,
    _credentials_set,
    _get_cached_expiration,
)


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


class _RaisingSTSClient:
    """A fake STS client that fails the test if it's ever actually called."""

    def assume_role(self, **kwargs):
        raise AssertionError("assume_role must never be called by _cached_credential_fetcher/_get_cached_expiration")


class _FakeSourceCredentials:
    access_key = "AKIAFAKESOURCE"
    secret_key = "fakesourcesecret"
    token = None
    method = "explicit"


def _make_fetcher(cache_dir):
    """Build a real `AssumeRoleCredentialFetcher` backed by a cache in `cache_dir`.

    Uses fakes for the STS client and MFA prompter (both raise if called) so
    tests can assert that reading the cache never triggers a live AssumeRole
    call or an MFA prompt.
    """
    return botocore.credentials.AssumeRoleCredentialFetcher(
        client_creator=lambda *args, **kwargs: _RaisingSTSClient(),
        source_credentials=_FakeSourceCredentials(),
        role_arn="arn:aws:iam::123456789012:role/test",
        extra_args={},
        mfa_prompter=lambda prompt: (_ for _ in ()).throw(AssertionError("must not prompt for MFA")),
        cache=botocore.credentials.JSONFileCache(str(cache_dir)),
    )


def _write_cache_entry(cache_dir, fetcher, expiration: datetime.datetime):
    """Write a fake assume-role cache entry, as botocore itself would."""
    entry = {
        "Credentials": {
            "AccessKeyId": "AKIAASSUMED",
            "SecretAccessKey": "assumedsecret",
            "SessionToken": "assumedtoken",
            "Expiration": expiration.strftime("%Y-%m-%dT%H:%M:%S%Z"),
        }
    }
    cache_path = cache_dir / f"{fetcher._cache_key}.json"
    cache_path.write_text(json.dumps(entry))


class TestBoto3Session:
    def test_returns_boto3_session_with_assume_role_cache_configured(self, aws_home):
        _config_set("gds-users", "region", "eu-west-2")

        session = _boto3_session("gds-users")

        provider = session._session.get_component("credential_provider").get_provider("assume-role")
        assert isinstance(provider.cache, botocore.credentials.JSONFileCache)


class TestCachedCredentialFetcher:
    def test_unwraps_mfa_serial_refresher_wrapper(self, tmp_path):
        fetcher = _make_fetcher(tmp_path)
        refresher = botocore.credentials.create_mfa_serial_refresher(fetcher.fetch_credentials)
        creds = botocore.credentials.DeferredRefreshableCredentials(method="assume-role", refresh_using=refresher)

        assert _cached_credential_fetcher(creds) is fetcher

    def test_finds_fetcher_without_mfa_wrapper(self, tmp_path):
        fetcher = _make_fetcher(tmp_path)
        creds = botocore.credentials.DeferredRefreshableCredentials(
            method="assume-role", refresh_using=fetcher.fetch_credentials
        )

        assert _cached_credential_fetcher(creds) is fetcher

    def test_returns_none_for_static_credentials(self):
        creds = botocore.credentials.Credentials("AKIA", "secret", None)

        assert _cached_credential_fetcher(creds) is None


class TestGetCachedExpiration:
    def test_returns_expiration_from_valid_cache_entry(self, tmp_path):
        fetcher = _make_fetcher(tmp_path)
        creds = botocore.credentials.DeferredRefreshableCredentials(
            method="assume-role", refresh_using=fetcher.fetch_credentials
        )
        expiry = datetime.datetime.now(datetime.UTC) + datetime.timedelta(hours=2)
        _write_cache_entry(tmp_path, fetcher, expiry)

        result = _get_cached_expiration(creds)

        assert result is not None
        assert abs((result - expiry).total_seconds()) < 1

    def test_returns_actual_past_expiration_for_expired_cache_entry(self, tmp_path):
        """An expired cache entry must still report its real (past) expiration.

        `CachedCredentialFetcher._load_from_cache()` would filter this out and
        return `None` - `_get_cached_expiration` deliberately bypasses that so
        `status` can report "expired N minutes ago" instead of treating an
        expired sign-in the same as never having signed in at all.
        """
        fetcher = _make_fetcher(tmp_path)
        creds = botocore.credentials.DeferredRefreshableCredentials(
            method="assume-role", refresh_using=fetcher.fetch_credentials
        )
        expired = datetime.datetime.now(datetime.UTC) - datetime.timedelta(hours=2)
        _write_cache_entry(tmp_path, fetcher, expired)

        result = _get_cached_expiration(creds)

        assert result is not None
        assert abs((result - expired).total_seconds()) < 1

    def test_returns_none_when_no_cache_entry_exists(self, tmp_path):
        fetcher = _make_fetcher(tmp_path)
        creds = botocore.credentials.DeferredRefreshableCredentials(
            method="assume-role", refresh_using=fetcher.fetch_credentials
        )

        assert _get_cached_expiration(creds) is None

    def test_returns_none_for_static_credentials(self):
        creds = botocore.credentials.Credentials("AKIA", "secret", None)

        assert _get_cached_expiration(creds) is None
