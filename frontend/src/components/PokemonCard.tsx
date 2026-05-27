import type { Pokemon } from '../types'
import { TYPE_COLORS, TYPE_TINTS } from '../lib/typeColors'
import { btnPrimary } from '../lib/ui'
import { Sprite } from './Sprite'
import { StatBars } from './StatBars'

export function PokemonCard({
  p,
  onAdd,
  addDisabled,
  inTeam,
  typeClash,
}: {
  p: Pokemon
  onAdd?: () => void
  addDisabled?: boolean
  inTeam?: boolean
  /** True if adding this Pokémon would duplicate the type *set* of an existing
   *  member — the ADR-043 soft rule. The card disables its Add CTA with a
   *  "Type clash" label so the user sees the rule before clicking (the backend
   *  would also 400 with "same type combination"). */
  typeClash?: boolean
}) {
  const total = Object.values(p.stats).reduce((a, b) => a + b, 0)
  return (
    <div className="group rounded-xl border border-slate-200 bg-white p-3 shadow-sm transition duration-200 hover:-translate-y-0.5 hover:shadow-md">
      <div className="flex items-center justify-between text-xs text-slate-400">
        <span>
          #{p.id}
          {(p.is_legendary || p.is_mythical) && (
            <span className="ml-1 text-amber-500" title="Legendary / Mythical">
              ★
            </span>
          )}
        </span>
        <span>BST {total}</span>
      </div>
      <div
        className={`mx-auto my-1 flex h-28 items-center justify-center rounded-xl bg-gradient-to-b to-white ${
          TYPE_TINTS[p.types[0]] ?? 'from-slate-100'
        }`}
      >
        <Sprite
          url={p.sprite_url}
          name={p.name}
          className="h-24 w-24 object-contain drop-shadow-sm transition duration-200 group-hover:scale-105"
        />
      </div>
      <h3 className="text-center text-sm font-semibold capitalize">{p.name.replace(/-/g, ' ')}</h3>
      <div className="mt-2 flex flex-wrap justify-center gap-1">
        {p.types.map((t) => (
          <span
            key={t}
            className={`rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-white shadow-sm ${
              TYPE_COLORS[t] ?? 'bg-slate-400'
            }`}
          >
            {t}
          </span>
        ))}
      </div>
      <StatBars stats={p.stats} />
      {onAdd && (
        <button
          onClick={onAdd}
          disabled={addDisabled || inTeam || typeClash}
          title={
            typeClash
              ? 'A team cannot contain two Pokémon with the same type combination (ADR-043)'
              : undefined
          }
          className={
            inTeam
              ? 'mt-2 inline-flex w-full items-center justify-center rounded-lg bg-emerald-500 px-2 py-1.5 text-xs font-semibold text-white shadow-sm disabled:opacity-60'
              : typeClash
                ? 'mt-2 inline-flex w-full items-center justify-center rounded-lg border border-amber-200 bg-amber-50 px-2 py-1.5 text-xs font-semibold text-amber-700 disabled:cursor-not-allowed'
                : `${btnPrimary} mt-2 w-full px-2 py-1.5 text-xs`
          }
        >
          {inTeam ? '✓ Added' : typeClash ? 'Type clash' : '+ Add'}
        </button>
      )}
    </div>
  )
}
