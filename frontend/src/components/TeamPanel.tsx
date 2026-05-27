import { useState } from 'react'
import type { Team } from '../api/teams'
import {
  MAX_TEAM_NAME_LENGTH,
  MAX_TEAMS,
  MIN_TEAM_NAME_LENGTH,
} from '../lib/limits'
import { btnDanger, btnPrimary, btnSecondary } from '../lib/ui'
import { TeamSlots } from './TeamSlots'

export function TeamPanel({
  teams,
  active,
  onSelect,
  onNew,
  onRename,
  onDelete,
  onReorder,
  onRemoveAt,
  onAutofill,
  onCounter,
  counterPending,
  includeForms,
  onIncludeFormsChange,
}: {
  teams: Team[]
  active: Team | null
  onSelect: (id: string) => void
  /** Create a new team with the chosen name. Resolves when the team is created
   *  so the form can close + select the new team. */
  onNew: (name: string) => Promise<void> | void
  onRename: (name: string) => void
  onDelete: () => void
  onReorder: (ids: number[]) => void
  onRemoveAt: (index: number) => void
  onAutofill: () => void
  onCounter: () => void
  counterPending: boolean
  includeForms: boolean
  onIncludeFormsChange: (value: boolean) => void
}) {
  // Inline "name your team" form. Replaces the old auto-create flow (which
  // immediately POSTed a "Team N" stub) so the user sees their typed name go
  // through one explicit Save click, with frontend-side validation before the
  // request leaves the browser.
  const [newName, setNewName] = useState<string | null>(null)  // null = form closed
  const [creating, setCreating] = useState(false)

  const trimmedNewName = (newName ?? '').trim()
  const newNameValid =
    trimmedNewName.length >= MIN_TEAM_NAME_LENGTH &&
    trimmedNewName.length <= MAX_TEAM_NAME_LENGTH
  const canCreate = newName !== null && newNameValid && !creating

  const openNewForm = () => setNewName(`Team ${teams.length + 1}`)  // suggested default
  const cancelNewForm = () => {
    setNewName(null)
    setCreating(false)
  }
  const submitNewForm = async () => {
    if (!canCreate) return
    setCreating(true)
    try {
      await onNew(trimmedNewName)
      cancelNewForm()
    } catch {
      // Leave the form open so the user can correct / retry; App surfaces
      // server errors via the mutation's state if needed.
      setCreating(false)
    }
  }

  return (
    <section className="mb-6 rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
      <div className="mb-3 flex flex-wrap items-center gap-2">
        {teams.map((t) => (
          <button
            key={t.id}
            onClick={() => onSelect(t.id)}
            className={`rounded-lg border px-3 py-1 text-sm transition ${
              active?.id === t.id
                ? 'border-indigo-600 bg-indigo-600 text-white shadow-sm'
                : 'border-slate-200 bg-white text-slate-700 hover:bg-slate-50'
            }`}
          >
            {t.name} <span className="opacity-60">({t.members.length})</span>
          </button>
        ))}
        {newName === null ? (
          <button
            onClick={openNewForm}
            disabled={teams.length >= MAX_TEAMS}
            title={
              teams.length >= MAX_TEAMS ? `Team limit reached (max ${MAX_TEAMS})` : undefined
            }
            className="rounded-lg border border-dashed border-slate-300 px-3 py-1 text-sm text-slate-600 transition hover:bg-slate-50 disabled:opacity-40"
          >
            + New team
          </button>
        ) : (
          <span className="flex items-center gap-1 rounded-lg border border-indigo-300 bg-indigo-50/60 px-2 py-1">
            <input
              autoFocus
              value={newName}
              maxLength={MAX_TEAM_NAME_LENGTH}
              onChange={(e) => setNewName(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') submitNewForm()
                if (e.key === 'Escape') cancelNewForm()
              }}
              placeholder="Team name"
              aria-label="New team name"
              className="rounded-md border border-slate-200 bg-white px-2 py-0.5 text-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
            />
            <button
              onClick={submitNewForm}
              disabled={!canCreate}
              className={`${btnPrimary} px-2 py-0.5 text-xs disabled:cursor-not-allowed disabled:bg-slate-300`}
              title={
                trimmedNewName.length === 0
                  ? 'Enter a name first'
                  : trimmedNewName.length > MAX_TEAM_NAME_LENGTH
                    ? `Max ${MAX_TEAM_NAME_LENGTH} characters`
                    : undefined
              }
            >
              {creating ? '…' : 'Save'}
            </button>
            <button
              onClick={cancelNewForm}
              disabled={creating}
              className="rounded-md px-2 py-0.5 text-xs text-slate-500 transition hover:text-slate-800 disabled:opacity-50"
            >
              Cancel
            </button>
          </span>
        )}
      </div>

      {active ? (
        <>
          <div className="mb-3 flex items-center gap-2">
            <input
              key={active.id}
              defaultValue={active.name}
              maxLength={MAX_TEAM_NAME_LENGTH}
              onBlur={(e) => {
                const v = e.target.value.trim()
                // Reject blanks + over-cap (the latter shouldn't reach here
                // thanks to maxLength, but defence in depth costs nothing).
                if (
                  v.length >= MIN_TEAM_NAME_LENGTH &&
                  v.length <= MAX_TEAM_NAME_LENGTH &&
                  v !== active.name
                ) {
                  onRename(v)
                } else if (v !== active.name) {
                  // Snap back to the last good name so the input doesn't lie.
                  e.target.value = active.name
                }
              }}
              className="rounded-lg border border-slate-200 px-2 py-1 text-sm font-medium focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500"
              aria-label="Team name"
            />
            <span className="text-xs text-slate-400">{active.members.length}/6</span>
            <button
              onClick={onAutofill}
              disabled={active.members.length >= 6}
              className={`${btnSecondary} px-3 py-1 text-sm`}
            >
              Auto-fill
            </button>
            <button
              onClick={onCounter}
              disabled={active.members.length === 0 || counterPending}
              className={`${btnPrimary} px-3 py-1 text-sm`}
              title="Evolve a counter team (genetic algorithm); each click finds a new, type-diverse team"
            >
              {counterPending ? 'Generating…' : 'Counter this team'}
            </button>
            <label
              className="flex items-center gap-1 text-xs text-slate-600"
              title="Allow Megas / Primals / other forms in the counter pool (off = base species only)"
            >
              <input
                type="checkbox"
                checked={includeForms}
                onChange={(e) => onIncludeFormsChange(e.target.checked)}
              />
              Include forms
            </label>
            <button onClick={onDelete} className={`${btnDanger} ml-auto px-3 py-1 text-sm`}>
              Delete team
            </button>
          </div>
          <TeamSlots members={active.members} onReorder={onReorder} onRemoveAt={onRemoveAt} />
          <p className="mt-2 text-xs text-slate-400">
            Drag to reorder · × to remove · add from the catalog below
          </p>
        </>
      ) : (
        <p className="text-sm text-slate-500">No team selected. Create one to start building.</p>
      )}
    </section>
  )
}
