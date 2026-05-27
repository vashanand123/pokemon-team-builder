const STAT_META: [string, string][] = [
  ['hp', 'HP'],
  ['attack', 'Atk'],
  ['defense', 'Def'],
  ['special_attack', 'SpA'],
  ['special_defense', 'SpD'],
  ['speed', 'Spe'],
]

// Compact per-stat bars so you can compare Pokémon while building a team.
export function StatBars({ stats }: { stats: Record<string, number> }) {
  return (
    <div className="mt-2 space-y-0.5">
      {STAT_META.map(([key, label]) => {
        const value = stats[key] ?? 0
        const pct = Math.min(100, (value / 200) * 100)
        return (
          <div key={key} className="flex items-center gap-1 text-[10px] text-slate-500">
            <span className="w-7 shrink-0">{label}</span>
            <div className="h-1.5 flex-1 rounded bg-slate-100">
              <div className="h-1.5 rounded bg-slate-400" style={{ width: `${pct}%` }} />
            </div>
            <span className="w-6 shrink-0 text-right tabular-nums">{value}</span>
          </div>
        )
      })}
    </div>
  )
}
