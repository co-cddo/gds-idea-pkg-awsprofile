"""Shared test configuration and fixtures."""

import os
from pathlib import Path

import pytest


class FakeAwsHome:
    """Paths that stand in for `~/.aws/config` and `~/.aws/credentials` in tests.

    Neither file exists until a test (or the code under test) creates it -
    this class just fixes where they will live for the duration of a test.
    """

    def __init__(self, base: Path):
        self.base = base
        self.config = base / "aws_config"
        self.credentials = base / "aws_creds"


@pytest.fixture
def aws_home(tmp_path, monkeypatch):
    """Redirect every `os.path.expanduser("~...")` call made by awsprofile to a tmp dir.

    awsprofile reads/writes `~/.aws/config` and `~/.aws/credentials` (and
    resolves `~` for the assume-role cache dir) via plain
    `os.path.expanduser` calls. Patching `os.path.expanduser` itself (rather
    than each module's `os` import) means every module under test picks up
    the redirect, and tests never touch the real files on the machine
    running the test suite.

    Returns:
        A `FakeAwsHome` with `.config` and `.credentials` `Path`s that tests
        can seed (write to) or inspect (read from) directly.
    """
    home = FakeAwsHome(tmp_path)
    real_expanduser = os.path.expanduser

    def fake_expanduser(path):
        if path == "~/.aws/config":
            return str(home.config)
        if path == "~/.aws/credentials":
            return str(home.credentials)
        if path == "~":
            return str(tmp_path)
        return real_expanduser(path)

    monkeypatch.setattr(os.path, "expanduser", fake_expanduser)
    return home


def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line("markers", "integration: tests that require external services")
