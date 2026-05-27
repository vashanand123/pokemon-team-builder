export interface Pokemon {
  id: number
  name: string
  types: string[]
  stats: Record<string, number>
  sprite_url: string | null
  is_legendary?: boolean
  is_mythical?: boolean
}

export interface PokemonList {
  items: Pokemon[]
  total: number
}
