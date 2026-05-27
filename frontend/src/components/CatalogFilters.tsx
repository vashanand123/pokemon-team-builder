import { ALL_TYPES, TYPE_COLORS } from '../lib/typeColors'
import {
  STAT_KEYS,
  activeFilterCount,
  type CatalogFilter,
  type StatRange,
} from '../lib/filter'

const STAT_LABEL: Record<string, string> = {
  hp: 'HP',
  attack: 'Attack',
  defense: 'Defense',
  special_attack: 'Sp. Atk',
  special_defense: 'Sp. Def',
  speed: 'Speed',
}

/** The faceted filter panel: multi-select types (Any/All) + per-stat min/max ranges.
 * Stateless — it edits the `filter` value the Catalog owns and reports changes via `onChange`. */
export function CatalogFilters({
  filter,
  onChange,
}: {
  filter: CatalogFilter
  onChange: (f: CatalogFilter) => void
}) {
  const toggleType = (t: string) =>
    onChange({
      ...filter,
      types: filter.types.includes(t)
        ? filter.types.filter((x) => x !== t)
        : [...filter.types, t],
    })

  const setStat = (key: string, side: keyof StatRange, raw: string) => {
    const value = raw === '' ? undefined : Number(raw)
    const next: StatRange = { ...filter.stats[key], [side]: value }
    const stats = { ...filter.stats }
    if (next.min == null && next.max == null) delete stats[key]
    else stats[key] = next
    onChange({ ...filter, stats })
  }

  const clear = () => onChange({ ...filter, types: [], typeMatch: 'any', stats: {} })

  return (
    <section className="mb-4 rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
      {/* Types — multi-select chips + Any/All */}
      <div className="mb-3">
        <div className="mb-1.5 flex items-center gap-2">
          <span className="text-xs font-semibold text-slate-600">Types</span>
          <div className="inline-flex overflow-hidden rounded-md border border-slate-200 text-[11px]">
            {(['any', 'all'] as const).map((m) => (
              <button
                key={m}
                onClick={() => onChange({ ...filter, typeMatch: m })}
                title={
                  m === 'any'
                    ? 'Match ANY selected type (union)'
                    : 'Match ALL selected types (dual-types)'
                }
                className={`px-2 py-0.5 transition ${
                  filter.typeMatch === m
                    ? 'bg-indigo-600 text-white'
                    : 'bg-white text-slate-600 hover:bg-slate-50'
                }`}
              >
                {m === 'any' ? 'Any' : 'All'}
              </button>
            ))}
          </div>
        </div>
        <div className="flex flex-wrap gap-1">
          {ALL_TYPES.map((t) => {
            const on = filter.types.includes(t)
            return (
              <button
                key={t}
                onClick={() => toggleType(t)}
                aria-pressed={on}
                className={`rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide transition ${
                  on
                    ? `${TYPE_COLORS[t] ?? 'bg-slate-500'} text-white shadow-sm`
                    : 'bg-slate-100 text-slate-500 hover:bg-slate-200'
                }`}
              >
                {t}
              </button>
            )
          })}
        </div>
      </div>

      {/* Stat ranges — min/max per stat (AND together) */}
      <div>
        <span className="mb-1.5 block text-xs font-semibold text-slate-600">
          Stat ranges{' '}
          <span className="font-normal text-slate-400">(min–max; blank = no limit)</span>
        </span>
        <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-3">
          {STAT_KEYS.map((k) => {
            const r = filter.stats[k] ?? {}
            return (
              <div key={k} className="flex items-center gap-1.5 text-xs">
                <span className="w-16 text-slate-500">{STAT_LABEL[k]}</span>
                <input
                  type="number"
                  min={0}
                  max={255}
                  value={r.min ?? ''}
                  onChange={(e) => setStat(k, 'min', e.target.value)}
                  placeholder="min"
                  aria-label={`${STAT_LABEL[k]} minimum`}
                  className="w-16 rounded border border-slate-200 px-1.5 py-0.5 focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500"
                />
                <span className="text-slate-300">–</span>
                <input
                  type="number"
                  min={0}
                  max={255}
                  value={r.max ?? ''}
                  onChange={(e) => setStat(k, 'max', e.target.value)}
                  placeholder="max"
                  aria-label={`${STAT_LABEL[k]} maximum`}
                  className="w-16 rounded border border-slate-200 px-1.5 py-0.5 focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500"
                />
              </div>
            )
          })}
        </div>
      </div>

      {activeFilterCount(filter) > 0 && (
        <div className="mt-3 text-right">
          <button
            onClick={clear}
            className="text-xs text-slate-400 transition hover:text-red-600"
          >
            Clear filters ✕
          </button>
        </div>
      )}
    </section>
  )
}
