import { useQuery } from '@tanstack/react-query'
import { fetchJson } from './client'
import type { PokemonList } from '../types'

// The catalog is static within a session, so fetch it once and filter client-side.
export function usePokemonCatalog() {
  return useQuery({
    queryKey: ['pokemon', 'all'],
    queryFn: () => fetchJson<PokemonList>('/api/pokemon'),
    staleTime: Infinity,
  })
}
