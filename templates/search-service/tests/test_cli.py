def test_cli_help_does_not_require_an_index(capsys):
    import pytest

    from search_service.cli import main

    with pytest.raises(SystemExit) as error:
        main(["--help"])
    assert error.value.code == 0
    assert "build" in capsys.readouterr().out


def test_cli_reports_invalid_config_without_a_traceback(tmp_path, capsys):
    from search_service.cli import main

    config = tmp_path / "invalid.toml"
    config.write_text("schema_version = 99", encoding="utf-8")
    assert main(["build", "--config", str(config)]) == 1
    assert "schema_version" in capsys.readouterr().err
