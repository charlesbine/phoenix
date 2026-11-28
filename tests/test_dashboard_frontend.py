"""Production dashboard static serving."""

from fastapi.testclient import TestClient


def make_client(tmp_path, monkeypatch, frontend_dist):
    import phoenix.db as db_mod
    import phoenix.paths as paths_mod
    import phoenix.server.dashboard as dashboard_mod

    data_dir = tmp_path / "data"
    output_dir = tmp_path / "outputs"
    (data_dir / "output").mkdir(parents=True)

    monkeypatch.setattr(db_mod, "DB_PATH", tmp_path / "dash.db")
    monkeypatch.setattr(paths_mod, "DATA_DIR", data_dir)
    monkeypatch.setattr(paths_mod, "OUTPUTS_DIR", output_dir)
    monkeypatch.setattr(paths_mod, "FRONTEND_DIST_DIR", frontend_dist)
    monkeypatch.setattr(dashboard_mod, "DATA_DIR", data_dir)
    monkeypatch.setattr(dashboard_mod, "OUTPUTS_DIR", output_dir)

    return TestClient(dashboard_mod.create_app())


def test_serves_built_vue_dashboard_and_spa_routes(tmp_path, monkeypatch):
    frontend_dist = tmp_path / "dist"
    (frontend_dist / "assets").mkdir(parents=True)
    (frontend_dist / "index.html").write_text("<div id=\"app\"></div>")
    (frontend_dist / "phoenix.png").write_bytes(b"png")

    client = make_client(tmp_path, monkeypatch, frontend_dist)

    root = client.get("/")
    assert root.text == "<div id=\"app\"></div>"
    assert root.headers.get("cache-control") == "no-cache"

    spa = client.get("/devices")
    assert spa.text == "<div id=\"app\"></div>"
    assert spa.headers.get("cache-control") == "no-cache"

    assert client.get("/phoenix.png").content == b"png"
    assert client.get("/api/not-a-route").status_code == 404


def test_missing_frontend_build_is_explicit(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch, tmp_path / "missing-dist")

    response = client.get("/")

    assert response.status_code == 503
    assert "Phoenix dashboard is not built" in response.text
    assert "bun run build" in response.text
