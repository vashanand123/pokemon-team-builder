from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.pokeapi_client import HttpPokeApiClient
from app.business.changes import scan_all, simulate_change
from app.db.session import get_session

router = APIRouter(prefix="/admin", tags=["admin"])


@router.post("/scan-changes")
async def scan_changes(session: AsyncSession = Depends(get_session)):
    """Run the full change-detection job now (same `scan_all` orchestrator the scheduler
    runs): discovers new Pokémon, diffs every catalog row, and detects new types (ADR-036).
    """
    async with HttpPokeApiClient() as client:
        summary = await scan_all(session, client)
    return summary


@router.post("/simulate-change")
async def simulate(pokemon_id: int, session: AsyncSession = Depends(get_session)):
    """Dev hook: inject a synthetic change so the alert banner can be demoed."""
    alert = await simulate_change(session, pokemon_id)
    if alert is None:
        raise HTTPException(status_code=404, detail="Pokémon not found")
    return {"ok": True, "pokemon_id": pokemon_id}
