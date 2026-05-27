import pytest

pytestmark = pytest.mark.integration


def test_healthz_returns_ok(api_client) -> None:
    """The liveness probe stays a 200 even with no session — the lifespan creates
    tables + seeds the fixture before the route serves."""
    resp = api_client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
