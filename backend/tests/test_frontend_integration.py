from fastapi.testclient import TestClient

from app.main import create_app


def test_built_spa_is_served_for_root_and_client_routes(settings):
    settings.frontend_dist = settings.data_dir.parent / "frontend-dist"
    assets = settings.frontend_dist / "assets"
    assets.mkdir(parents=True)
    (settings.frontend_dist / "index.html").write_text(
        '<div id="app"></div><script src="/assets/app.js"></script>',
        encoding="utf-8",
    )
    (assets / "app.js").write_text("window.MEETFLOW = true", encoding="utf-8")

    with TestClient(create_app(settings)) as client:
        root = client.get("/")
        nested = client.get("/meetings/example-id")
        asset = client.get("/assets/app.js")
        missing_api = client.get("/api/not-a-real-endpoint")

    assert root.status_code == 200
    assert '<div id="app"></div>' in root.text
    assert nested.status_code == 200
    assert '<div id="app"></div>' in nested.text
    assert asset.status_code == 200
    assert asset.text == "window.MEETFLOW = true"
    assert missing_api.status_code == 404
