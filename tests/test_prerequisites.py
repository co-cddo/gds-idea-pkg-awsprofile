"""Tests for `awsprofile.prerequisites`."""

import subprocess

import pytest

from awsprofile import prerequisites
from awsprofile.prerequisites import _check_prerequisites


class TestCheckPrerequisites:
    def test_no_prerequisites_defined_is_a_noop(self, monkeypatch):
        monkeypatch.setattr(prerequisites, "PREREQUISITES", [])

        _check_prerequisites()  # must not raise or exit

    def test_installed_tool_does_not_exit(self, monkeypatch):
        monkeypatch.setattr(
            prerequisites,
            "PREREQUISITES",
            [("foo", ["foo", "--version"], "brew install foo", None)],
        )
        monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: None)

        _check_prerequisites()  # must not raise or exit

    def test_missing_tool_exits_with_hint_and_url(self, monkeypatch, capsys):
        monkeypatch.setattr(
            prerequisites,
            "PREREQUISITES",
            [("foo", ["foo", "--version"], "brew install foo", "https://example.com/foo")],
        )

        def fake_run(*args, **kwargs):
            raise FileNotFoundError()

        monkeypatch.setattr(subprocess, "run", fake_run)

        with pytest.raises(SystemExit) as exc_info:
            _check_prerequisites()

        assert exc_info.value.code == 1
        err = capsys.readouterr().err
        assert "foo" in err
        assert "brew install foo" in err
        assert "https://example.com/foo" in err

    def test_called_process_error_is_treated_as_missing(self, monkeypatch, capsys):
        monkeypatch.setattr(
            prerequisites,
            "PREREQUISITES",
            [("foo", ["foo", "--version"], "brew install foo", None)],
        )

        def fake_run(*args, **kwargs):
            raise subprocess.CalledProcessError(returncode=1, cmd=["foo", "--version"])

        monkeypatch.setattr(subprocess, "run", fake_run)

        with pytest.raises(SystemExit) as exc_info:
            _check_prerequisites()

        assert exc_info.value.code == 1

    def test_reports_every_missing_tool_in_one_pass(self, monkeypatch, capsys):
        monkeypatch.setattr(
            prerequisites,
            "PREREQUISITES",
            [
                ("foo", ["foo", "--version"], "brew install foo", None),
                ("bar", ["bar", "--version"], "brew install bar", None),
            ],
        )
        monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: (_ for _ in ()).throw(FileNotFoundError()))

        with pytest.raises(SystemExit):
            _check_prerequisites()

        err = capsys.readouterr().err
        assert "foo" in err
        assert "bar" in err

    def test_only_filters_which_tools_are_checked(self, monkeypatch):
        calls = []
        monkeypatch.setattr(
            prerequisites,
            "PREREQUISITES",
            [
                ("foo", ["foo", "--version"], "hint", None),
                ("bar", ["bar", "--version"], "hint", None),
            ],
        )

        def fake_run(cmd, **kwargs):
            calls.append(cmd)

        monkeypatch.setattr(subprocess, "run", fake_run)

        _check_prerequisites(only=["bar"])

        assert calls == [["bar", "--version"]]
