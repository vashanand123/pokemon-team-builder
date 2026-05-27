from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration, overridable via environment variables or a .env file."""

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # SQLite by default; swap to a Postgres URL in production (see DECISIONS.md ADR-003).
    database_url: str = "sqlite+aiosqlite:///./pokemon.db"
    # Name of the cookie carrying the opaque session token (ADR-039).
    session_cookie_name: str = "ptb_session"
    pokeapi_base_url: str = "https://pokeapi.co/api/v2"
    scheduler_enabled: bool = True  # in-process change-scan scheduler (off in tests)


settings = Settings()


# Resource limits (guardrails on user-created data). Kept beside config so the caps
# live in one discoverable place; enforced at the API/service layer (DECISIONS.md
# ADR-026 / ADR-028).
MAX_TEAMS_PER_USER = 20  # max teams a single (anonymous) user may create
MAX_TEAM_MEMBERS = 6  # max Pokémon on a team (also enforced by the team schema)
MAX_COUNTERS_PER_TEAM = 10  # max saved counter teams per source team
