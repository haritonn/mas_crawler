import pytest


def test_paths_are_relative_to_config_not_working_directory(tmp_path, monkeypatch):
    from search_service.config import load_config

    project = tmp_path / "project"
    project.mkdir()
    config = project / "search.toml"
    config.write_text(
        '[project]\nname = "Example"\n'
        '[storage]\ncorpus = "data/documents.jsonl"\nindex = "indexes/v1"\n'
        "[search]\ntitle_weight = 3.0\ntext_weight = 1.0\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    settings = load_config(config)
    assert settings.corpus == project / "data/documents.jsonl"
    assert settings.index == project / "indexes/v1"
    assert settings.search.title_weight == 3.0
    assert settings.name == "Example"


@pytest.mark.parametrize(
    "contents",
    [
        "[search]\ntitle_weight = -1.0",
        "[search]\ntitle_weight = 0.0\ntext_weight = 0.0",
        "[search]\ntitle_weight = nan",
        "[search]\ntext_weight = inf",
        "[search]\ntitle_boost = 3.0",
        "schema_version = 2",
    ],
)
def test_invalid_config_is_rejected(tmp_path, contents):
    from pydantic import ValidationError

    from search_service.config import load_config

    path = tmp_path / "search.toml"
    path.write_text(contents, encoding="utf-8")
    with pytest.raises(ValidationError):
        load_config(path)
