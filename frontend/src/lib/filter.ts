import type { Pokemon } from '../types'

// The catalog's faceted filter, kept as one pure value so the filtering logic lives in a
// single testable function (applyFilter) and the UI just edits this object. Deliberately
// bounded: multi-type with Any/All, per-stat min/max ranges, and a single sort key — NOT a
// general query-builder (no nested AND/OR, no free-form operators). See DECISIONS.md ADR-035.

export type TypeMatch = 'any' | 'all'

export interface StatRange {
  min?: number
  max?: number
}

export interface CatalogFilter {
  q: string // case-insensitive name search
  types: string[] // selected types
  typeMatch: TypeMatch // 'any' = union (OR), 'all' = dual-type (AND)
  stats: Record<string, StatRange> // stat key -> {min?, max?}; absent = unconstrained
  sort: string // 'id' | 'name' | 'total' | <stat key>
  order: 'asc' | 'desc'
}

export const STAT_KEYS = [
  'hp',
  'attack',
  'defense',
  'special_attack',
  'special_defense',
  'speed',
] as const

export const emptyFilter = (): CatalogFilter => ({
  q: '',
  types: [],
  typeMatch: 'any',
  stats: {},
  sort: 'id',
  order: 'asc',
})

const bst = (p: Pokemon): number => Object.values(p.stats).reduce((a, b) => a + b, 0)

/** How many *narrowing* facets are active (types + stat ranges) — drives the "Filters (N)" badge. */
export function activeFilterCount(f: CatalogFilter): number {
  let n = f.types.length
  for (const k of STAT_KEYS) {
    const r = f.stats[k]
    if (r && (r.min != null || r.max != null)) n++
  }
  return n
}

/** Pure: apply the whole filter (name + types + stat ranges) then sort. */
export function applyFilter(items: Pokemon[], f: CatalogFilter): Pokemon[] {
  const needle = f.q.trim().toLowerCase()
  let list = items

  if (needle) list = list.filter((p) => p.name.includes(needle))

  if (f.types.length) {
    list = list.filter((p) =>
      f.typeMatch === 'all'
        ? f.types.every((t) => p.types.includes(t)) // dual-type AND
        : f.types.some((t) => p.types.includes(t)), // union OR
    )
  }

  for (const k of STAT_KEYS) {
    const r = f.stats[k]
    if (!r) continue
    if (r.min != null) list = list.filter((p) => (p.stats[k] ?? 0) >= r.min!)
    if (r.max != null) list = list.filter((p) => (p.stats[k] ?? 0) <= r.max!)
  }

  const val = (p: Pokemon): number | string =>
    f.sort === 'name'
      ? p.name
      : f.sort === 'total'
        ? bst(p)
        : f.sort === 'id'
          ? p.id
          : (p.stats[f.sort] ?? 0)
  const dir = f.order === 'desc' ? -1 : 1
  return [...list].sort((a, b) => {
    const av = val(a)
    const bv = val(b)
    return (av < bv ? -1 : av > bv ? 1 : 0) * dir
  })
}
