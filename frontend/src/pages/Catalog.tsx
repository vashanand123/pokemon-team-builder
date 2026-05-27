import { useEffect, useMemo, useRef, useState } from 'react'
import { usePokemonCatalog } from '../api/pokemon'
import { PokemonCard } from '../components/PokemonCard'
import { Sprite } from '../components/Sprite'
import { CatalogFilters } from '../components/CatalogFilters'
import {
  activeFilterCount,
  applyFilter,
  emptyFilter,
  type CatalogFilter,
} from '../lib/filter'
import type { Pokemon } from '../types'

const PAGE = 48
const SORTS: { value: string; label: string }[] = [
  { value: 'id', label: '# Pokédex' },
  { value: 'name', label: 'Name' },
  { value: 'total', label: 'Total stats' },
  { value: 'hp', label: 'HP' },
  { value: 'attack', label: 'Attack' },
  { value: 'defense', label: 'Defense' },
  { value: 'special_attack', label: 'Sp. Atk' },
  { value: 'special_defense', label: 'Sp. Def' },
  { value: 'speed', label: 'Speed' },
]

// Names/id read naturally ascending; stat sorts default to high→low (what people want).
const defaultOrder = (sort: string): 'asc' | 'desc' =>
  sort === 'name' || sort === 'id' ? 'asc' : 'desc'

export function Catalog({
  onAdd,
  canAdd,
  teamIds,
  usedTypeSets,
}: {
  onAdd?: (p: Pokemon) => void
  canAdd?: boolean
  teamIds?: Set<number>
  /** The type SETS already taken by the active team (sorted-types-joined-by-'|'
   *  keys). Cards whose type SET matches one of these get a disabled "Type
   *  clash" CTA — the ADR-043 soft rule: shared single type is allowed if the
   *  full sets differ. Undefined / empty = no clash filter (signed-out view). */
  usedTypeSets?: Set<string>
}) {
  const { data, isLoading, isError } = usePokemonCatalog()
  const [filter, setFilter] = useState<CatalogFilter>(emptyFilter)
  const [visible, setVisible] = useState(PAGE)
  const [open, setOpen] = useState(false) // search-suggestions dropdown
  const [showFilters, setShowFilters] = useState(false) // the facet panel
  const blurTimer = useRef<number | undefined>(undefined)

  // Any change to the filter resets paging back to the first page.
  useEffect(() => setVisible(PAGE), [filter])

  const needle = filter.q.trim().toLowerCase()

  const suggestions = useMemo(() => {
    if (!needle) return []
    return (data?.items ?? []).filter((p) => p.name.includes(needle)).slice(0, 8)
  }, [data, needle])

  // The whole catalog is already in memory, so the faceted filter runs client-side
  // (instant, no round-trips); the backend's list() params are the scale-time path.
  const filtered = useMemo(() => applyFilter(data?.items ?? [], filter), [data, filter])

  if (isLoading) return <p className="text-slate-500">Loading catalog…</p>
  if (isError)
    return <p className="text-red-600">Failed to load catalog. Is the backend running?</p>

  const shown = filtered.slice(0, visible)
  const activeCount = activeFilterCount(filter)
  const pick = (name: string) => {
    setFilter((f) => ({ ...f, q: name }))
    setOpen(false)
  }

  return (
    <div>
      <div className="mb-4 flex flex-wrap items-center gap-2">
        <div className="relative">
          <input
            value={filter.q}
            onChange={(e) => {
              setFilter((f) => ({ ...f, q: e.target.value }))
              setOpen(true)
            }}
            onFocus={() => setOpen(true)}
            onBlur={() => {
              blurTimer.current = window.setTimeout(() => setOpen(false), 120)
            }}
            onKeyDown={(e) => {
              if (e.key === 'Escape') setOpen(false)
              if (e.key === 'Enter' && suggestions.length) pick(suggestions[0].name)
            }}
            placeholder="Search name…"
            className="rounded-md border px-3 py-1.5 text-sm"
          />
          {open && suggestions.length > 0 && (
            <ul className="absolute z-20 mt-1 max-h-72 w-64 overflow-auto rounded-md border bg-white py-1 shadow-lg">
              {suggestions.map((p) => (
                <li key={p.id}>
                  <button
                    // onMouseDown (not onClick) fires before the input's blur closes the list.
                    onMouseDown={(e) => {
                      e.preventDefault()
                      window.clearTimeout(blurTimer.current)
                      pick(p.name)
                    }}
                    className="flex w-full items-center gap-2 px-2 py-1 text-left text-sm capitalize hover:bg-slate-100"
                  >
                    <Sprite url={p.sprite_url} name={p.name} className="h-8 w-8 object-contain" />
                    {p.name.replace(/-/g, ' ')}
                    <span className="ml-auto text-xs text-slate-400">#{p.id}</span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
        <button
          onClick={() => setShowFilters((v) => !v)}
          aria-expanded={showFilters}
          className={`rounded-md border px-3 py-1.5 text-sm transition ${
            activeCount
              ? 'border-indigo-300 bg-indigo-50 text-indigo-700'
              : 'hover:bg-slate-50'
          }`}
        >
          {showFilters ? 'Filters ▴' : 'Filters ▾'}
          {activeCount > 0 && (
            <span className="ml-1 rounded-full bg-indigo-600 px-1.5 text-[10px] font-semibold text-white">
              {activeCount}
            </span>
          )}
        </button>
        <select
          value={filter.sort}
          onChange={(e) => {
            const sort = e.target.value
            setFilter((f) => ({ ...f, sort, order: defaultOrder(sort) }))
          }}
          className="rounded-md border py-1.5 pl-3 pr-9 text-sm"
        >
          {SORTS.map((s) => (
            <option key={s.value} value={s.value}>
              Sort: {s.label}
            </option>
          ))}
        </select>
        <button
          onClick={() =>
            setFilter((f) => ({ ...f, order: f.order === 'asc' ? 'desc' : 'asc' }))
          }
          title="Toggle sort direction"
          className="rounded-md border px-3 py-1.5 text-sm hover:bg-slate-50"
        >
          {filter.sort === 'name'
            ? filter.order === 'asc'
              ? 'A → Z'
              : 'Z → A'
            : filter.order === 'desc'
              ? '↓ High–Low'
              : '↑ Low–High'}
        </button>
        <span className="ml-auto text-sm text-slate-500">{filtered.length} Pokémon</span>
      </div>

      {showFilters && <CatalogFilters filter={filter} onChange={setFilter} />}

      {filtered.length === 0 ? (
        <p className="py-12 text-center text-sm text-slate-500">
          No Pokémon match these filters.
        </p>
      ) : (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6">
          {shown.map((p) => (
            <PokemonCard
              key={p.id}
              p={p}
              onAdd={onAdd ? () => onAdd(p) : undefined}
              addDisabled={!canAdd}
              inTeam={teamIds?.has(p.id) ?? false}
              typeClash={
                !!usedTypeSets && usedTypeSets.has([...p.types].sort().join('|'))
              }
            />
          ))}
        </div>
      )}

      {shown.length < filtered.length && (
        <div className="mt-6 text-center">
          <button
            onClick={() => setVisible((v) => v + PAGE)}
            className="rounded-md border bg-white px-4 py-2 text-sm font-medium shadow-sm hover:bg-slate-50"
          >
            Load more ({filtered.length - shown.length} left)
          </button>
        </div>
      )}
    </div>
  )
}
