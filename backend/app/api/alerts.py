from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.business.changes import recent_alerts_for_user
from app.business.user import User
from app.db.session import get_session
from app.schemas import AlertOut

router = APIRouter(prefix="/api/me", tags=["alerts"])


@router.get("/alerts", response_model=list[AlertOut])
async def my_alerts(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Return the current user's recent (last 7 days) Pokémon-change alerts.

    An "alert" is a `change_events` row whose `pokemon_id` appears in one of this user's
    teams — computed on demand via a join, not stored. `recent_alerts_for_user` returns
    business `Alert`s (translation lives in `business/changes.py`), so this router only
    ever sees business shapes.
    """
    return await recent_alerts_for_user(session, user.id)
