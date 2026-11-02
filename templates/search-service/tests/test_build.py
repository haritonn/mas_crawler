import hashlib
import json

import pytest


def test_build_records_corpus_and_never_overwrites_an_index(project):
    from search_service.build import build

    report = build(project)
    index = project.parent / "indexes/v1"
    metadata = json.loads((index / "build.json").read_text())
    assert metadata["indexed_documents"] == 2
    assert (
        metadata["corpus_sha256"]
        == hashlib.sha256((project.parent / "documents.jsonl").read_bytes()).hexdigest()
    )
    assert report["index_path"] == str(index)
    before = {
        path.name: path.read_bytes() for path in index.iterdir() if path.is_file()
    }
    with pytest.raises(FileExistsError):
        build(project)
    assert before == {
        path.name: path.read_bytes() for path in index.iterdir() if path.is_file()
    }
    second = build(project, project.parent / "indexes/v2")
    assert second["indexed_documents"] == 2
    assert (index / "build.json").is_file()


@pytest.mark.parametrize(
    "contents",
    [
        "",
        "not-json\n",
        '{"url":"u","title":"t","text":""}\n',
        '{"url":"u","title":"t","text":"x"}\n' * 2,
    ],
)
def test_invalid_corpus_does_not_create_an_index(project, contents):
    from search_service.build import build

    (project.parent / "documents.jsonl").write_text(contents, encoding="utf-8")
    with pytest.raises((ValueError, RuntimeError)):
        build(project)
    assert not (project.parent / "indexes/v1").exists()
