import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { fetchJson, mutateJson } from './client'
import type { Pokemon } from '../types'
import type { Team } from './teams'

export interface ScoreBreakdown {
  fitness: number // the paper's summed battle value (higher = better; unbounded)
  win_rate: number // fraction of head-to-head pairings the counter wins (0..1)
  team_cp: number // total Combat Power of the counter team
  opponent_cp: number // total Combat Power of the team being countered
}

export interface CounterPreview {
  team: Pokemon[]
  score: ScoreBreakdown
  team_bst: number
  opponent_bst: number
}

export interface SavedCounter extends CounterPreview {
  id: string
  source_team_id: string
  created_at: string
}

export function useTeamCounters(teamId: string | null) {
  return useQuery({
    queryKey: ['counters', teamId],
    queryFn: () => fetchJson<SavedCounter[]>(`/api/teams/${teamId}/counters`),
    enabled: !!teamId,
  })
}

// Generate a preview (stochastic) — NOT persisted until the user hits Save.
export function useGenerateCounter() {
  return useMutation({
    mutationFn: (vars: { teamId: string; includeForms?: boolean }) =>
      mutateJson<CounterPreview>(
        `/api/teams/${vars.teamId}/counters/generate`,
        'POST',
        { include_forms: vars.includeForms ?? false },
      ),
  })
}

export function useSaveCounter() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (vars: { teamId: string; member_ids: number[] }) =>
      mutateJson<SavedCounter>(`/api/teams/${vars.teamId}/counters`, 'POST', {
        member_ids: vars.member_ids,
      }),
    onSuccess: (_data, vars) =>
      qc.invalidateQueries({ queryKey: ['counters', vars.teamId] }),
  })
}

export function useDeleteCounter() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (vars: { id: string; teamId: string }) =>
      mutateJson<void>(`/api/counters/${vars.id}`, 'DELETE'),
    onSuccess: (_data, vars) =>
      qc.invalidateQueries({ queryKey: ['counters', vars.teamId] }),
  })
}

export function useAutofill() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (teamId: string) =>
      mutateJson<Team>(`/api/teams/${teamId}/autofill`, 'POST'),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['teams'] }),
  })
}
