import { useEffect, useState } from 'react'
import { useAlerts } from '../api/alerts'
import { useMe } from '../api/auth'

// localStorage persistence for "I've seen alerts up to this timestamp."
// Scoped per-user so logging out + back in as someone else doesn't inherit
// dismissals — the alert feed is per-user on the server, so the dismissed-state
// has to be per-user on the client too.
const storageKey = (userId: string) => `ptb_alerts_dismissed_until:${userId}`

export function AlertBanner() {
  const { data: me } = useMe()
  const { data: alerts = [] } = useAlerts()

  // Tracks the ISO timestamp of the latest alert the user has dismissed. Newer
  // alerts (e.g. a fresh simulate-change) still surface because their detected_at
  // is strictly greater than this mark. Null = nothing dismissed yet.
  const [dismissedUntil, setDismissedUntil] = useState<string | null>(null)

  // Load the persisted mark on mount and whenever the signed-in user changes.
  // ISO 8601 timestamps compare correctly as strings, so we never need to parse.
  useEffect(() => {
    if (!me) {
      setDismissedUntil(null)
      return
    }
    setDismissedUntil(localStorage.getItem(storageKey(me.id)))
  }, [me?.id])

  // Hide everything we've already acknowledged. A newly-arrived alert (e.g. the
  // 60-second poll picks up a fresh simulate-change) re-opens the banner because
  // its detected_at is newer than the stored mark.
  const visible = dismissedUntil
    ? alerts.filter((a) => a.detected_at > dismissedUntil)
    : alerts

  if (!me || visible.length === 0) return null

  const dismiss = () => {
    // "I've seen everything up to now." Use the latest visible alert's
    // detected_at rather than `new Date()` so a clock-skew edge case (server
    // ahead of client) can't accidentally hide a future alert.
    const mark = visible.reduce(
      (max, a) => (a.detected_at > max ? a.detected_at : max),
      visible[0].detected_at,
    )
    localStorage.setItem(storageKey(me.id), mark)
    setDismissedUntil(mark)
  }

  return (
    <div className="mb-4 rounded-lg border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900">
      <div className="flex items-start gap-2">
        <span aria-hidden>⚠️</span>
        <div className="flex-1">
          <p className="font-semibold">
            PokéAPI data changed for {visible.length} of your Pokémon (last 7 days)
          </p>
          <ul className="mt-1 list-disc pl-5">
            {visible.map((a, i) => (
              <li key={i} className="capitalize">
                {a.pokemon.name.replace(/-/g, ' ')} — {Object.keys(a.diff).join(', ')} changed
              </li>
            ))}
          </ul>
        </div>
        <button
          onClick={dismiss}
          className="text-amber-700 hover:text-amber-900"
          aria-label="Dismiss alerts"
        >
          ✕
        </button>
      </div>
    </div>
  )
}
