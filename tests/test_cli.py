"""CLI argument resolution (brief §58) — `tr file.pdf` sugar for `tr open file.pdf`,
alongside real subcommands like `config`/`doctor`/`cache`."""

from __future__ import annotations

from click.testing import CliRunner

from pinax import cli as cli_module


def test_bare_path_resolves_to_open(monkeypatch, md_file):
    captured = {}
    monkeypatch.setattr(cli_module, "_run_app", lambda path, page, search: captured.update(path=path, page=page, search=search))

    runner = CliRunner()
    result = runner.invoke(cli_module.main, [str(md_file)])
    assert result.exit_code == 0, result.output
    assert captured == {"path": str(md_file), "page": None, "search": None}


def test_path_with_flags(monkeypatch, md_file):
    captured = {}
    monkeypatch.setattr(cli_module, "_run_app", lambda path, page, search: captured.update(path=path, page=page, search=search))

    runner = CliRunner()
    result = runner.invoke(cli_module.main, [str(md_file), "--page", "3", "--search", "attention"])
    assert result.exit_code == 0, result.output
    assert captured == {"path": str(md_file), "page": 3, "search": "attention"}


def test_no_args_opens_library(monkeypatch):
    captured = {}
    monkeypatch.setattr(cli_module, "_run_app", lambda path, page, search: captured.update(path=path))

    runner = CliRunner()
    result = runner.invoke(cli_module.main, [])
    assert result.exit_code == 0, result.output
    assert captured == {"path": None}


def test_doctor_subcommand_still_resolves(isolated_home):
    runner = CliRunner()
    result = runner.invoke(cli_module.main, ["doctor"])
    assert result.exit_code == 0, result.output
    assert "pinax" in result.output
    assert "SQLite FTS5" in result.output


def test_config_subcommand_still_resolves(isolated_home):
    runner = CliRunner()
    result = runner.invoke(cli_module.main, ["config"], input="\n")
    assert result.exit_code == 0, result.output
    assert "Config file:" in result.output


def test_cache_status_subcommand(isolated_home):
    runner = CliRunner()
    result = runner.invoke(cli_module.main, ["cache", "status"])
    assert result.exit_code == 0, result.output


def test_nonexistent_path_gives_clean_error(monkeypatch):
    monkeypatch.setattr(cli_module, "_run_app", lambda *a: None)
    runner = CliRunner()
    result = runner.invoke(cli_module.main, ["/no/such/file.pdf"])
    assert result.exit_code != 0
    assert "does not exist" in result.output.lower() or "no such" in result.output.lower()
