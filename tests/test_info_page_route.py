from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_info_route_serves_the_react_entrypoint() -> None:
    server = (ROOT / "src" / "app" / "server" / "main.py").read_text()
    index = ROOT / "src" / "app" / "static" / "index.html"

    assert '@app.get("/info", include_in_schema=False)' in server
    assert 'def info() -> FileResponse:' in server
    assert 'return FileResponse(static_root / "index.html")' in server
    assert '<div id="root"></div>' in index.read_text()
