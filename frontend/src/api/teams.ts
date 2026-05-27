import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { fetchJson, mutateJson } from './client'
import type { Pokemon } from '../types'

export interface TeamMember {
  slot: number
  pokemon: Pokemon
}

export interface Team {
  id: string
  name: string
  members: TeamMember[]
  created_at: string
  updated_at: string
}

const KEY = ['teams']

export function useTeams() {
  return useQuery({ queryKey: KEY, queryFn: () => fetchJson<Team[]>('/api/teams') })
}

export function useCreateTeam() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (vars: { name: string; member_ids?: number[] }) =>
      mutateJson<Team>('/api/teams', 'POST', vars),
    onSuccess: () => qc.invalidateQueries({ queryKey: KEY }),
  })
}

export function useUpdateTeam() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (vars: { id: string; name?: string; member_ids?: number[] }) =>
      mutateJson<Team>(`/api/teams/${vars.id}`, 'PUT', {
        name: vars.name,
        member_ids: vars.member_ids,
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: KEY }),
  })
}

export function useDeleteTeam() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => mutateJson<void>(`/api/teams/${id}`, 'DELETE'),
    onSuccess: () => qc.invalidateQueries({ queryKey: KEY }),
  })
}
