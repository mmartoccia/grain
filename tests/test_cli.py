"""Tests for grain CLI commands."""
from __future__ import annotations

import argparse

from grain import __version__
from grain.cli import cmd_init, cmd_status


def test_init_writes_default_config(monkeypatch, tmp_path, capsys):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "tests").mkdir()
    (tmp_path / "dist").mkdir()

    code = cmd_init(argparse.Namespace())

    assert code == 0
    config = (tmp_path / ".grain.toml").read_text(encoding="utf-8")
    assert '[grain]' in config
    assert 'fail_on   = ["OBVIOUS_COMMENT", "NAKED_EXCEPT", "HEDGE_WORD", "VAGUE_TODO", "VAGUE_COMMIT"]' in config
    assert '"tests/*"' in config
    assert '"dist/*"' in config
    assert "test_patterns" in config
    assert "created .grain.toml" in capsys.readouterr().out


def test_init_refuses_to_overwrite_existing_config(monkeypatch, tmp_path, capsys):
    monkeypatch.chdir(tmp_path)
    config_path = tmp_path / ".grain.toml"
    config_path.write_text("[grain]\nignore = []\n", encoding="utf-8")

    code = cmd_init(argparse.Namespace())

    assert code == 1
    assert config_path.read_text(encoding="utf-8") == "[grain]\nignore = []\n"
    assert "already exists" in capsys.readouterr().out


def test_status_reports_package_version(monkeypatch, tmp_path, capsys):
    monkeypatch.chdir(tmp_path)

    code = cmd_status(argparse.Namespace())

    assert code == 0
    assert f"grain v{__version__}" in capsys.readouterr().out
