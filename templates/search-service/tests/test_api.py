import pytest
from fastapi.testclient import TestClient


def test_server_refuses_to_start_without_an_index(tmp_path):
    from search_service.app import create_app

    config = tmp_path / "search.toml"
    config.write_text('[storage]\nindex = "missing"\n', encoding="utf-8")
    with (
        pytest.raises(FileNotFoundError, match="Build an index"),
        TestClient(create_app(config)),
    ):
        pass


def test_real_index_health_search_and_configuration_restart(project):
    from search_service.app import create_app
    from search_service.build import build

    build(project)
    with TestClient(create_app(project)) as client:
        assert client.get("/health").json() == {
            "status": "ok",
            "project": "Fixture search",
        }
        response = client.post("/search", json={"query": " quartz ", "top_k": 1})
        assert response.status_code == 200
        result = response.json()
        assert result["query"] == "quartz"
        assert len(result["hits"]) == 1
        assert result["hits"][0]["id"] == "https://example.invalid/title"
        assert set(result["hits"][0]) == {"id", "url", "title", "score"}
        assert client.post("/search", json={"query": "absentword"}).json()["hits"] == []
        assert client.post("/search", json={"query": "std::ffi"}).status_code == 200
        paths = client.get("/openapi.json").json()["paths"]
        assert set(paths) == {"/health", "/search"}

    project.write_text(
        project.read_text()
        .replace("title_weight = 20.0", "title_weight = 1.0")
        .replace("text_weight = 1.0", "text_weight = 20.0"),
        encoding="utf-8",
    )
    with TestClient(create_app(project)) as client:
        hits = client.post("/search", json={"query": "quartz"}).json()["hits"]
        assert hits[0]["id"] == "https://example.invalid/text"


@pytest.mark.parametrize(
    "payload",
    [
        {"query": ""},
        {"query": "   "},
        {"query": "q" * 4001},
        {"query": "quartz", "top_k": 0},
        {"query": "quartz", "top_k": 101},
        {"query": "quartz", "top_k": True},
        {"query": "quartz", "top_k": "5"},
        {"query": "quartz", "unknown_option": True},
    ],
)
def test_invalid_search_requests_are_rejected(project, payload):
    from search_service.app import create_app
    from search_service.build import build

    build(project)
    with TestClient(create_app(project)) as client:
        assert client.post("/search", json=payload).status_code == 422
