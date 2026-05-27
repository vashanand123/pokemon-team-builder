import { useQuery } from '@tanstack/react-query'
import { fetchJson } from './client'
import type { Pokemon } from '../types'

export interface Alert {
  pokemon: Pokemon
  detected_at: string
  diff: Record<string, { old: unknown; new: unknown }>
}

export function useAlerts() {
  return useQuery({
    queryKey: ['alerts'],
    queryFn: () => fetchJson<Alert[]>('/api/me/alerts'),
    refetchInterval: 60_000,
  })
}
