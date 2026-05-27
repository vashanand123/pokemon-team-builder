// Full class strings (not built dynamically) so Tailwind's scanner picks them up.
export const TYPE_COLORS: Record<string, string> = {
  normal: 'bg-stone-400',
  fire: 'bg-orange-500',
  water: 'bg-blue-500',
  electric: 'bg-yellow-400',
  grass: 'bg-green-500',
  ice: 'bg-cyan-300',
  fighting: 'bg-red-700',
  poison: 'bg-purple-500',
  ground: 'bg-amber-600',
  flying: 'bg-indigo-300',
  psychic: 'bg-pink-500',
  bug: 'bg-lime-500',
  rock: 'bg-yellow-700',
  ghost: 'bg-violet-700',
  dragon: 'bg-indigo-600',
  dark: 'bg-stone-700',
  steel: 'bg-slate-400',
  fairy: 'bg-pink-300',
}

// Soft gradient-start tints (full class strings for the scanner) for type-colored
// backgrounds behind sprites — paired with `to-white` in a `bg-gradient-to-b`.
export const TYPE_TINTS: Record<string, string> = {
  normal: 'from-stone-100',
  fire: 'from-orange-100',
  water: 'from-blue-100',
  electric: 'from-yellow-100',
  grass: 'from-green-100',
  ice: 'from-cyan-100',
  fighting: 'from-red-100',
  poison: 'from-purple-100',
  ground: 'from-amber-100',
  flying: 'from-indigo-100',
  psychic: 'from-pink-100',
  bug: 'from-lime-100',
  rock: 'from-yellow-100',
  ghost: 'from-violet-100',
  dragon: 'from-indigo-100',
  dark: 'from-stone-200',
  steel: 'from-slate-100',
  fairy: 'from-pink-100',
}

export const ALL_TYPES = Object.keys(TYPE_COLORS)
