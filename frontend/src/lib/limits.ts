// Mirrors backend app/core/config.py + schemas.py (kept in sync manually across the
// language boundary). The backend enforces these; the UI uses them to disable controls
// early so users see "Name is too long" before they try to submit.
export const MAX_TEAMS = 20
export const MAX_TEAM_MEMBERS = 6
export const MIN_TEAM_NAME_LENGTH = 1   // schemas.TeamCreate.name min_length
export const MAX_TEAM_NAME_LENGTH = 60  // schemas.TeamCreate.name max_length
