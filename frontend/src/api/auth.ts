// Auth hooks against the /api/auth/* endpoints (ADR-039). The session cookie is
// HttpOnly so we never touch it from JS — `credentials: 'include'` (in client.ts)
// is enough for the browser to ship it with every request.

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { fetchJson, HttpError, mutateJson } from './client'

export type User = {
  id: string
  username: string
  is_admin: boolean
  created_at: string
}

/** Current user, or `null` when unauthenticated. A 401 is treated as "logged out"
 *  (returns null); every other failure rethrows so the boundary shows it.
 *
 *  **null vs undefined matters here.** TanStack Query v5 treats `data === undefined`
 *  as the sentinel for "no fetch has completed yet" — `setQueryData(key, undefined)`
 *  is effectively a no-op (doesn't notify subscribers). So we use `null` as the
 *  explicit "logged out" value. `useLogout` then sets the cache to `null` and every
 *  `useMe()` subscriber re-renders this turn. Components check `!me` which is true
 *  for both null (logged out) and undefined (still loading) — same shape on the
 *  consumer side, but the wire is now unambiguous. */
export function useMe() {
  return useQuery<User | null>({
    queryKey: ['me'],
    queryFn: async () => {
      try {
        return await fetchJson<User>('/api/auth/me')
      } catch (err) {
        if (err instanceof HttpError && err.status === 401) return null
        throw err
      }
    },
    // No automatic background refetch — `me` only changes via the auth mutations
    // below, and they all invalidate this query themselves.
    staleTime: Infinity,
    refetchOnWindowFocus: false,
    retry: false,
  })
}

export function useSignup() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: { username: string; password: string }) =>
      mutateJson<User>('/api/auth/signup', 'POST', body),
    // Signup logs the user in (cookie set), so refresh everything user-scoped.
    onSuccess: () => qc.invalidateQueries(),
  })
}

export function useLogin() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: { username: string; password: string }) =>
      mutateJson<User>('/api/auth/login', 'POST', body),
    onSuccess: () => qc.invalidateQueries(),
  })
}

export function useLogout() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () => mutateJson<void>('/api/auth/logout', 'POST'),
    onSuccess: () => {
      // Pin the `me` cache to `null` (the explicit "logged out" sentinel — see
      // the doc on `useMe`). TanStack Query v5 propagates this synchronously,
      // so every subscriber (App, UserBadge) re-renders this turn:
      // AuthenticatedApp unmounts, AuthOverlay appears, no refresh needed.
      //
      // History: we previously tried `qc.clear()` (which empties the cache but
      // doesn't reliably notify subscribers — UserBadge re-rendered via its
      // own mutation hook but App didn't), then `setQueryData(['me'], undefined)`
      // (which v5 treats as a no-op because undefined is the "no fetch yet"
      // sentinel). `null` is a real value, so it definitely updates.
      qc.setQueryData<User | null>(['me'], null)
      // Drop every other query — teams/counters/alerts belong to the previous
      // user and would briefly render to the next one if we kept them around.
      // Keep the `me` entry (we just wrote it).
      qc.removeQueries({ predicate: (q) => q.queryKey[0] !== 'me' })
    },
  })
}
