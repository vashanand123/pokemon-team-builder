"""Integration tests for the public catalog router."""

import pytest

pytestmark = pytest.mark.integration


def test_list_returns_catalog(api_client):
    resp = api_client.get("/api/pokemon", params={"limit": 5})
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] >= 1000
    assert len(body["items"]) == 5
    assert {"id", "name", "types", "stats", "sprite_url"} <= body["items"][0].keys()


def test_get_single_pokemon(api_client):
    resp = api_client.get("/api/pokemon/1")
    assert resp.status_code == 200
    assert resp.json()["name"] == "bulbasaur"


def test_filter_by_type(api_client):
    resp = api_client.get("/api/pokemon", params={"type": "fire", "limit": 50})
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert items and all("fire" in p["types"] for p in items)


def test_missing_pokemon_404(api_client):
    assert api_client.get("/api/pokemon/999999").status_code == 404
