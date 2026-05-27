import asyncio

import httpx
from tenacity import (
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential_jitter,
)

from app.core.config import settings

_RETRYABLE_STATUS = {429, 500, 502, 503, 504}


def _is_retryable(exc: BaseException) -> bool:
    """Retry transient failures only — never a 404 or other client error."""
    if isinstance(exc, httpx.TransportError):  # timeouts, connection errors
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code in _RETRYABLE_STATUS
    return False


class HttpPokeApiClient:
    """Real PokeApiClient: async httpx with bounded concurrency and tenacity retry."""

    def __init__(self, base_url: str | None = None, concurrency: int = 20) -> None:
        """Build the underlying httpx client + a semaphore that caps in-flight requests.
        Default `concurrency=20` is the budget the seed pipeline + the change-scan share —
        polite toward PokéAPI without throttling the ~1,350-fetch seed too aggressively."""
        self._base = (base_url or settings.pokeapi_base_url).rstrip("/")
        self._sem = asyncio.Semaphore(concurrency)
        self._client = httpx.AsyncClient(
            timeout=30.0,
            limits=httpx.Limits(max_connections=40, max_keepalive_connections=20),
            headers={"User-Agent": "pokemon-team-builder/0.1"},
        )

    async def __aenter__(self) -> "HttpPokeApiClient":
        """Async-context-manager entry — lets callers write `async with HttpPokeApiClient()
        as client:` so the connection pool is closed cleanly on exit."""
        return self

    async def __aexit__(self, *_exc: object) -> None:
        """Async-context-manager exit — close the underlying httpx connection pool."""
        await self._client.aclose()

    @retry(
        reraise=True,
        stop=stop_after_attempt(4),
        wait=wait_exponential_jitter(initial=0.5, max=8),
        retry=retry_if_exception(_is_retryable),
    )
    async def _get(self, url: str) -> dict:
        """Single GET → JSON dict, with semaphore-bounded concurrency and tenacity retry
        (4 tries, exponential backoff + jitter, only on transient failures). Raises on a
        4xx other than 429 — those are NOT retried (would be pointless)."""
        async with self._sem:
            resp = await self._client.get(url)
            resp.raise_for_status()
            return resp.json()

    async def list_pokemon_refs(self) -> list[dict]:
        """`GET /pokemon?limit=100000` → the full index. Each entry is `{name, url}`;
        the id is the last path segment of the url (see `_id_from_ref_url` in
        `services/changes.py`)."""
        data = await self._get(f"{self._base}/pokemon?limit=100000&offset=0")
        return data["results"]

    async def get_pokemon(self, ref: int | str) -> dict:
        """Fetch one Pokémon by id (`get_pokemon(25)`) or by URL (`get_pokemon(ref["url"])`).
        Both shapes accepted so the seed and the change-scan can pass whichever they
        have — saves a URL→id parse-then-rebuild round trip."""
        url = (
            ref
            if isinstance(ref, str) and ref.startswith("http")
            else f"{self._base}/pokemon/{ref}"
        )
        return await self._get(url)

    async def list_type_names(self) -> list[str]:
        """All type names from /type (includes non-battle types; the caller filters)."""
        data = await self._get(f"{self._base}/type?limit=100000&offset=0")
        return [t["name"] for t in data["results"]]

    async def get_type(self, name: str) -> dict:
        """Fetch one type's full record (including `damage_relations`) — used by the
        seed to derive the 18×18 effectiveness chart."""
        return await self._get(f"{self._base}/type/{name}")

    async def get_species(self, url: str) -> dict:
        """Fetch one Pokémon species — used by the seed and the discovery pass to read
        the `is_legendary` / `is_mythical` flags (not present on the /pokemon endpoint)."""
        return await self._get(url)
