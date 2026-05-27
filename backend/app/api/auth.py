"""Auth router: signup / login / logout / me (ADR-039).

The session cookie is HttpOnly + SameSite=Lax + Max-Age = SESSION_TTL — same
posture the Phase-1 anonymous cookie used. JS can't read the cookie (HttpOnly),
and the API treats the token as a bearer credential: whoever sends it is that
user. The store is server-side so revocation is one row update.
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.exc import IntegrityError

from app.api.deps import (
    get_auth_repo,
    get_current_user,
    get_password_hasher,
    get_session_store,
)
from app.business.auth import SESSION_TTL
from app.business.user import User
from app.core.config import settings
from app.schemas import LoginRequest, SignupRequest, UserOut

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _set_session_cookie(response: Response, token: str, expires_at: datetime) -> None:
    """Apply our standard cookie attributes for the opaque session token.

    HttpOnly so JS can't read it (mitigates XSS exfiltration). SameSite=Lax so
    cross-site GETs ride along (login flows) but POSTs don't (CSRF mitigation).
    Max-Age in seconds matches the row's `expires_at` so the browser forgets the
    cookie when the server-side row expires anyway.
    """
    max_age = int((expires_at - datetime.now(timezone.utc)).total_seconds())
    response.set_cookie(
        key=settings.session_cookie_name,
        value=token,
        httponly=True,
        samesite="lax",
        max_age=max_age,
        path="/",
    )


@router.post("/signup", response_model=UserOut, status_code=201)
async def signup(
    body: SignupRequest,
    response: Response,
    repo=Depends(get_auth_repo),
    hasher=Depends(get_password_hasher),
    store=Depends(get_session_store),
):
    """Create a new user and start a session (so the UI doesn't bounce them to
    a separate login step). Duplicate username → 409."""
    try:
        user = await repo.create_user(body.username, hasher.hash(body.password))
    except IntegrityError as exc:
        # The UNIQUE constraint on users.username is the source of truth —
        # checking via SELECT first would race anyway. Translate to 409 once.
        raise HTTPException(
            status_code=409, detail="That username is already taken"
        ) from exc
    token, expires_at = await store.create(user.id)
    _set_session_cookie(response, token, expires_at)
    return user


@router.post("/login", response_model=UserOut)
async def login(
    body: LoginRequest,
    response: Response,
    repo=Depends(get_auth_repo),
    hasher=Depends(get_password_hasher),
    store=Depends(get_session_store),
):
    """Verify credentials and start a session. Returns the same 401 detail for
    "unknown username" and "wrong password" so we don't leak which accounts exist."""
    found = await repo.credentials_for_username(body.username)
    if found is None:
        raise HTTPException(status_code=401, detail="Invalid username or password")
    user, password_hash = found
    if not hasher.verify(body.password, password_hash):
        raise HTTPException(status_code=401, detail="Invalid username or password")
    token, expires_at = await store.create(user.id)
    _set_session_cookie(response, token, expires_at)
    return user


@router.post("/logout", status_code=204)
async def logout(
    request: Request,
    response: Response,
    store=Depends(get_session_store),
):
    """Revoke the current session (if any) and clear the cookie. Idempotent —
    calling logout while already logged out is a 204 too."""
    token = request.cookies.get(settings.session_cookie_name)
    if token:
        await store.revoke(token)
    # Match the path + samesite + httponly attributes from `_set_session_cookie`
    # so every browser identifies this as the same cookie and clears it. (Some
    # browsers are strict about matching attributes on delete.)
    response.delete_cookie(
        key=settings.session_cookie_name,
        path="/",
        samesite="lax",
        httponly=True,
    )


@router.get("/me", response_model=UserOut)
async def me(user: User = Depends(get_current_user)):
    """Return the current user. 401 if unauthenticated (the dep raises). Used by
    the frontend's `useAuth` hook to decide whether to show the login overlay
    and what email to render in the header."""
    return user


# Re-export so other modules can read the session TTL without importing business.auth.
__all__ = ["router", "SESSION_TTL"]
