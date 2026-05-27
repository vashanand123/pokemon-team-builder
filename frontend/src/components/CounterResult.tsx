import { useEffect, useState } from 'react'
import type { CounterPreview, SavedCounter } from '../api/counter'
import { TYPE_COLORS, TYPE_TINTS } from '../lib/typeColors'
import { btnPrimary, btnSecondary } from '../lib/ui'
import type { Pokemon } from '../types'
import { Sprite } from './Sprite'

function Bar({ label, value }: { label: string; value: number }) {
  return (
    <div className="flex items-center gap-2 text-xs">
      <span className="w-36 text-slate-500">{label}</span>
      <div className="h-2 flex-1 rounded-full bg-slate-100">
        <div className="h-2 rounded-full bg-indigo-500" style={{ width: `${Math.round(value * 100)}%` }} />
      </div>
      <span className="w-10 text-right tabular-nums">{Math.round(value * 100)}%</span>
    </div>
  )
}

function BstBadge({ team, opp }: { team: number; opp: number }) {
  return (
    <span
      className="text-xs tabular-nums text-slate-500"
      title="Sum of base-stat totals — counter team vs the team it counters"
    >
      BST {team}{' '}
      <span className={team <= opp ? 'text-green-600' : 'text-amber-600'}>vs {opp}</span>
    </span>
  )
}

function TeamGrid({ team }: { team: Pokemon[] }) {
  return (
    <div className="mb-4 grid grid-cols-3 gap-3 sm:grid-cols-6">
      {team.map((p) => (
        <div key={p.id} className="rounded-xl border border-slate-200 bg-white p-2 text-center shadow-sm">
          <div
            className={`mx-auto mb-1 flex h-16 w-16 items-center justify-center rounded-lg bg-gradient-to-b to-white ${
              TYPE_TINTS[p.types[0]] ?? 'from-slate-100'
            }`}
          >
            <Sprite url={p.sprite_url} name={p.name} className="h-14 w-14 object-contain drop-shadow-sm" />
          </div>
          <div className="truncate text-xs capitalize">{p.name.replace(/-/g, ' ')}</div>
          <div className="mt-1 flex flex-wrap justify-center gap-1">
            {p.types.map((t) => (
              <span
                key={t}
                className={`rounded-full px-1.5 py-0.5 text-[9px] font-semibold uppercase text-white ${
                  TYPE_COLORS[t] ?? 'bg-slate-400'
                }`}
              >
                {t}
              </span>
            ))}
          </div>
        </div>
      ))}
    </div>
  )
}

function ScoreBars({ score }: { score: CounterPreview['score'] }) {
  // The sbgames-2020 objective: a signed `fitness` (CP × type-effectiveness, summed over
  // every matchup) plus a readable head-to-head win rate and the two teams' total CP.
  const cpEdge = score.opponent_cp > 0 ? score.team_cp / score.opponent_cp : 1
  return (
    <div className="space-y-1">
      <Bar label="Head-to-head win rate" value={score.win_rate} />
      <div className="flex items-center gap-2 pt-1 text-xs">
        <span className="w-36 text-slate-500">Fitness (paper objective)</span>
        <span
          className={`tabular-nums font-medium ${score.fitness >= 0 ? 'text-green-600' : 'text-amber-600'}`}
          title="Σ over every (counter × rival) pairing of CP×effectiveness — higher is a stronger counter"
        >
          {Math.round(score.fitness).toLocaleString()}
        </span>
      </div>
      <div className="flex items-center gap-2 text-xs">
        <span className="w-36 text-slate-500">Combat Power</span>
        <span className="tabular-nums text-slate-600" title="Counter team CP vs the countered team's CP">
          {Math.round(score.team_cp).toLocaleString()}{' '}
          <span className={cpEdge >= 1 ? 'text-green-600' : 'text-amber-600'}>
            vs {Math.round(score.opponent_cp).toLocaleString()}
          </span>
        </span>
      </div>
    </div>
  )
}

export function CounterPreviewCard({
  preview,
  onSave,
  onRegenerate,
  onDiscard,
  busy,
}: {
  preview: CounterPreview
  onSave: () => void
  onRegenerate: () => void
  onDiscard: () => void
  busy: boolean
}) {
  return (
    <section className="mb-6 rounded-xl border-2 border-dashed border-indigo-300 bg-indigo-50/40 p-4 shadow-sm">
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <h2 className="text-sm font-semibold">Generated counter (preview)</h2>
        <BstBadge team={preview.team_bst} opp={preview.opponent_bst} />
        <div className="ml-auto flex gap-2">
          <button onClick={onRegenerate} disabled={busy} className={`${btnSecondary} px-3 py-1 text-xs`}>
            ↻ Regenerate
          </button>
          <button onClick={onSave} disabled={busy} className={`${btnPrimary} px-3 py-1 text-xs`}>
            Save
          </button>
          <button
            onClick={onDiscard}
            disabled={busy}
            className="rounded-lg px-2 py-1 text-xs text-slate-400 transition hover:text-slate-700"
          >
            Discard
          </button>
        </div>
      </div>
      <TeamGrid team={preview.team} />
      <ScoreBars score={preview.score} />
    </section>
  )
}

export function SavedCounters({
  counters,
  onDelete,
}: {
  counters: SavedCounter[]
  onDelete: (id: string) => void
}) {
  // One card, tabs across the top. The active tab's counter renders inside.
  // We keep `activeId` here (the card knows which tab is selected) — switching
  // teams unmounts this component entirely, so the state resets naturally.
  const [activeId, setActiveId] = useState<string | null>(null)

  // Keep `activeId` in sync with the live counters list:
  //   - first arrival: pick the newest (which is `counters[0]` — list is newest-first)
  //   - deletion of the active tab: fall back to the new neighbour at the same index
  //   - all counters gone: clear
  useEffect(() => {
    if (!counters.length) {
      if (activeId !== null) setActiveId(null)
      return
    }
    if (activeId === null || !counters.some((c) => c.id === activeId)) {
      setActiveId(counters[0].id)
    }
  }, [counters, activeId])

  if (!counters.length) return null
  const active = counters.find((c) => c.id === activeId) ?? counters[0]
  // Render the tabs in CHRONOLOGICAL order (oldest first) so labels "Counter 1",
  // "Counter 2", … stay stable as new ones are appended. The repo lists
  // newest-first, so reverse for display + numbering.
  const ordered = [...counters].reverse()

  return (
    <section className="mb-6 rounded-xl border border-indigo-200 bg-indigo-50/40 shadow-sm">
      {/* Tab strip */}
      <div className="flex flex-wrap items-center gap-1 border-b border-indigo-200 px-3 pt-3">
        {ordered.map((c, idx) => {
          const isActive = c.id === active.id
          return (
            <button
              key={c.id}
              onClick={() => setActiveId(c.id)}
              className={`-mb-px rounded-t-lg border px-3 py-1.5 text-xs font-medium transition ${
                isActive
                  ? 'border-indigo-200 border-b-indigo-50/40 bg-indigo-50/40 text-indigo-700'
                  : 'border-transparent text-slate-500 hover:text-slate-800'
              }`}
              title={`Saved ${new Date(c.created_at).toLocaleString()}`}
            >
              Counter {idx + 1}
            </button>
          )
        })}
        <span className="ml-auto pb-1.5 pr-1 text-xs text-slate-500">
          {counters.length} saved
        </span>
      </div>

      {/* Active counter body */}
      <div className="p-4">
        <div className="mb-3 flex flex-wrap items-center gap-2">
          <h3 className="text-sm font-semibold">
            Counter {ordered.findIndex((c) => c.id === active.id) + 1}
          </h3>
          <BstBadge team={active.team_bst} opp={active.opponent_bst} />
          <button
            onClick={() => onDelete(active.id)}
            className="ml-auto text-xs text-slate-400 transition hover:text-red-600"
            title="Delete this saved counter"
          >
            delete ✕
          </button>
        </div>
        <TeamGrid team={active.team} />
        <ScoreBars score={active.score} />
      </div>
    </section>
  )
}
