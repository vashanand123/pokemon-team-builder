import { useEffect, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { fetchJson } from './api/client'
import { useLogout, useMe } from './api/auth'
import { Catalog } from './pages/Catalog'
import { TeamPanel } from './components/TeamPanel'
import { useCreateTeam, useDeleteTeam, useTeams, useUpdateTeam } from './api/teams'
import {
  useAutofill,
  useDeleteCounter,
  useGenerateCounter,
  useSaveCounter,
  useTeamCounters,
  type CounterPreview,
} from './api/counter'
import { CounterPreviewCard, SavedCounters } from './components/CounterResult'
import { AlertBanner } from './components/AlertBanner'
import { AuthOverlay } from './components/AuthOverlay'
import type { Pokemon } from './types'

function HealthDot() {
  const { data } = useQuery({
    queryKey: ['health'],
    queryFn: () => fetchJson<{ status: string }>('/healthz'),
  })
  const ok = data?.status === 'ok'
  return (
    <span
      className={`inline-block h-2 w-2 rounded-full ${ok ? 'bg-green-500' : 'bg-slate-300'}`}
      title={ok ? 'backend ok' : 'backend…'}
    />
  )
}

function UserBadge() {
  const { data: me } = useMe()
  const logout = useLogout()
  if (!me) return null
  return (
    <div className="ml-auto flex items-center gap-3 text-xs text-slate-600">
      <span className="max-w-[14rem] truncate" title={me.username}>
        @{me.username}
      </span>
      <button
        type="button"
        onClick={() => logout.mutate()}
        disabled={logout.isPending}
        className="rounded-md border border-slate-200 px-2 py-1 text-slate-700 transition hover:border-slate-400 hover:text-slate-900 disabled:opacity-50"
      >
        Log out
      </button>
    </div>
  )
}

function AuthenticatedApp() {
  const { data: teams = [] } = useTeams()
  const [activeId, setActiveId] = useState<string | null>(null)
  const [includeForms, setIncludeForms] = useState(false)
  const [preview, setPreview] = useState<CounterPreview | null>(null)

  useEffect(() => {
    if (teams.length && (!activeId || !teams.some((t) => t.id === activeId))) {
      setActiveId(teams[0].id)
    }
    if (!teams.length && activeId) setActiveId(null)
  }, [teams, activeId])

  // Drop a stale preview when switching teams.
  useEffect(() => setPreview(null), [activeId])

  const active = teams.find((t) => t.id === activeId) ?? null
  const memberIds = active ? active.members.map((m) => m.pokemon.id) : []
  // The type SETS already taken by the active team — feeds the Catalog's
  // per-card "Type clash" disabled state under the ADR-043 soft rule. The
  // string key is the sorted types joined with '|'; JS doesn't have frozensets
  // so this gives us O(1) lookup with a canonical representation.
  const typeSetKey = (types: readonly string[]) => [...types].sort().join('|')
  const usedTypeSets = new Set(
    active ? active.members.map((m) => typeSetKey(m.pokemon.types)) : [],
  )

  const createTeam = useCreateTeam()
  const updateTeam = useUpdateTeam()
  const deleteTeam = useDeleteTeam()
  const generateCounter = useGenerateCounter()
  const saveCounter = useSaveCounter()
  const deleteCounter = useDeleteCounter()
  const counters = useTeamCounters(activeId)
  const autofill = useAutofill()

  const addPokemon = (p: Pokemon) => {
    if (!active || active.members.length >= 6 || memberIds.includes(p.id)) return
    // ADR-043 soft rule: reject only if the candidate's type SET is already
    // represented (two fire/flying mons = clash; fire/flying + normal/flying
    // is fine). The catalog card is already disabled when this hits; the
    // re-check is defence in depth against stale renders.
    if (usedTypeSets.has(typeSetKey(p.types))) return
    updateTeam.mutate({ id: active.id, member_ids: [...memberIds, p.id] })
  }
  const removeAt = (i: number) => {
    if (active) updateTeam.mutate({ id: active.id, member_ids: memberIds.filter((_, idx) => idx !== i) })
  }
  const reorder = (ids: number[]) => {
    if (active) updateTeam.mutate({ id: active.id, member_ids: ids })
  }
  const rename = (name: string) => {
    if (active) updateTeam.mutate({ id: active.id, name })
  }
  const remove = () => {
    if (active) deleteTeam.mutate(active.id)
  }
  const newTeam = async (name: string) => {
    // TeamPanel's inline form already trims + validates; we re-trim here so a
    // direct caller (tests, future flows) can't sneak whitespace past us.
    const created = await createTeam.mutateAsync({ name: name.trim() })
    setActiveId(created.id)
  }
  const doAutofill = () => {
    if (active) autofill.mutate(active.id)
  }
  const doCounter = () => {
    if (active && active.members.length)
      generateCounter.mutate(
        { teamId: active.id, includeForms },
        { onSuccess: (data) => setPreview(data) },
      )
  }
  const savePreview = () => {
    if (active && preview)
      saveCounter.mutate(
        { teamId: active.id, member_ids: preview.team.map((p) => p.id) },
        { onSuccess: () => setPreview(null) },
      )
  }

  return (
    <>
      <AlertBanner />
      <TeamPanel
        teams={teams}
        active={active}
        onSelect={setActiveId}
        onNew={newTeam}
        onRename={rename}
        onDelete={remove}
        onReorder={reorder}
        onRemoveAt={removeAt}
        onAutofill={doAutofill}
        onCounter={doCounter}
        counterPending={generateCounter.isPending}
        includeForms={includeForms}
        onIncludeFormsChange={setIncludeForms}
      />
      {preview && (
        <CounterPreviewCard
          preview={preview}
          onSave={savePreview}
          onRegenerate={doCounter}
          onDiscard={() => setPreview(null)}
          busy={generateCounter.isPending || saveCounter.isPending}
        />
      )}
      <SavedCounters
        counters={counters.data ?? []}
        onDelete={(id) => activeId && deleteCounter.mutate({ id, teamId: activeId })}
      />
      <Catalog
        onAdd={addPokemon}
        canAdd={!!active && active.members.length < 6}
        teamIds={new Set(memberIds)}
        usedTypeSets={usedTypeSets}
      />
    </>
  )
}

function App() {
  // Catalog is public; team/counter UI is gated behind a signed-in `me`. When
  // `me` is absent we render the catalog read-only behind the modal overlay so
  // the signed-out landing isn't a blank screen.
  const { data: me, isPending: meLoading } = useMe()

  return (
    <div className="min-h-screen bg-slate-50 text-slate-900">
      <header className="sticky top-0 z-20 border-b border-slate-200 bg-white/80 backdrop-blur">
        <div className="mx-auto flex max-w-6xl items-center gap-2.5 px-6 py-3">
          <span
            className="grid h-7 w-7 place-items-center rounded-lg bg-gradient-to-br from-indigo-500 to-violet-500 text-sm shadow-sm"
            aria-hidden
          >
            ⚡
          </span>
          <h1 className="bg-gradient-to-r from-indigo-600 to-violet-600 bg-clip-text text-lg font-bold tracking-tight text-transparent">
            Pokémon Team Builder
          </h1>
          <HealthDot />
          <UserBadge />
        </div>
      </header>
      <main className="mx-auto max-w-6xl px-6 py-6">
        {me ? (
          <AuthenticatedApp />
        ) : (
          <Catalog onAdd={() => {}} canAdd={false} teamIds={new Set()} />
        )}
      </main>
      {!me && !meLoading && <AuthOverlay />}
    </div>
  )
}

export default App
