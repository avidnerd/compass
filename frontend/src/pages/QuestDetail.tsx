import { useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, idempotencyKey, resetIdempotencyKey } from '../api/client'
import type { FocusSession, Quest, Subgoal } from '../api/types'
import { Card, ErrorNote, EVIDENCE_LABELS, Spinner } from '../components/ui'
import { useFocusMonitoring } from '../components/FocusMonitoringProvider'

function SubgoalEditor({ subgoal, onChange, onDelete }: {
  subgoal: Subgoal
  onChange: (s: Subgoal) => void
  onDelete: () => void
}) {
  return (
    <div className="card" style={{ padding: '0.7rem' }}>
      <input aria-label="Subgoal title" value={subgoal.title}
        onChange={(e) => onChange({ ...subgoal, title: e.target.value })} />
      <label>Acceptance criterion</label>
      <input value={subgoal.acceptance_criterion}
        onChange={(e) => onChange({ ...subgoal, acceptance_criterion: e.target.value })} />
      <p className="small muted">Evidence: {subgoal.evidence_specs.map((e) => EVIDENCE_LABELS[e] ?? e).join(', ')}
        {' '}· difficulty {subgoal.difficulty}/5 · ~{subgoal.estimated_sessions} session(s)</p>
      <button className="danger" onClick={onDelete}>Remove</button>
    </div>
  )
}

export function QuestDetail() {
  const { questId } = useParams()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState<Subgoal[] | null>(null)
  const [preparingFocus, setPreparingFocus] = useState(false)
  const monitoring = useFocusMonitoring()

  const quest = useQuery({
    queryKey: ['quest', questId],
    queryFn: () => api<Quest>(`/quests/${questId}`),
    refetchInterval: (q) => (q.state.data?.data.state === 'planning' ? 1500 : false),
  })

  const saveSubgoals = useMutation({
    mutationFn: (subgoals: Subgoal[]) => api<Quest>(`/quests/${questId}`, {
      method: 'PATCH', body: { subgoals }, ifMatch: quest.data?.data.version,
    }),
    onSuccess: () => {
      setEditing(false)
      setDraft(null)
      queryClient.invalidateQueries({ queryKey: ['quest', questId] })
    },
  })
  const activate = useMutation({
    mutationFn: () => api<Quest>(`/quests/${questId}:activate`, { body: {} }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['quest', questId] }),
  })
  const archive = useMutation({
    mutationFn: () => api<Quest>(`/quests/${questId}:archive`, { body: {} }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['quest', questId] }),
  })
  const startSession = useMutation({
    mutationFn: (subgoalId: string) => {
      const scope = `focus-${subgoalId}`
      return api<FocusSession>('/focus-sessions', {
        body: { subgoal_id: subgoalId, planned_minutes: quest.data?.data.session_length_minutes ?? 25 },
        idempotencyKey: idempotencyKey(scope),
      }).finally(() => resetIdempotencyKey(scope))
    },
    onSuccess: async (resp) => {
      try {
        await monitoring.activateSession(resp.data)
      } catch {
        monitoring.abandonCapture()
      } finally {
        setPreparingFocus(false)
        navigate(`/focus/${resp.data.id}`)
      }
    },
    onError: () => {
      monitoring.abandonCapture()
      setPreparingFocus(false)
    },
  })

  const startMonitoredSession = async (subgoalId: string) => {
    setPreparingFocus(true)
    const sharing = await monitoring.requestScreen()
    if (!sharing) {
      setPreparingFocus(false)
      return
    }
    startSession.mutate(subgoalId)
  }

  if (quest.isPending) return <Spinner />
  if (quest.isError) return <ErrorNote error={quest.error} />
  const q = quest.data.data
  const subgoals = draft ?? q.subgoals ?? []

  return (
    <>
      <h1>{q.goal}</h1>
      <p className="muted">{q.meaning}</p>
      <p className="small">
        <span className="badge">{q.state}</span>
        {q.plan_model_id && <> · planned by <code>{q.plan_model_id}</code></>}
        {!q.plan_model_id && q.subgoals?.length ? ' · manual plan (free AI was unavailable)' : ''}
      </p>

      {q.state === 'planning' && <Card><p aria-busy="true">The free model is decomposing your
        goal into measurable steps…</p></Card>}

      {subgoals.map((sg, i) => editing ? (
        <SubgoalEditor key={sg.id ?? i} subgoal={sg}
          onChange={(next) => setDraft(subgoals.map((x, j) => (j === i ? next : x)))}
          onDelete={() => setDraft(subgoals.filter((_, j) => j !== i))} />
      ) : (
        <Card key={sg.id ?? i}>
          <div className="row spread">
            <div>
              <strong>{i + 1}. {sg.title}</strong>{' '}
              <span className={`badge ${sg.state === 'needs_confirmation' ? 'badge-warn' : ''}`}>{sg.state}</span>
              <p className="small muted" style={{ margin: '0.25rem 0 0' }}>{sg.rationale}</p>
              <p className="small" style={{ margin: '0.25rem 0 0' }}>
                ✅ Done when: {sg.acceptance_criterion}</p>
              <p className="small muted" style={{ margin: '0.25rem 0 0' }}>
                Evidence: {sg.evidence_specs.map((e) => EVIDENCE_LABELS[e] ?? e).join(', ')}</p>
            </div>
            {q.state === 'active' && ['todo', 'in_progress'].includes(sg.state) && (
              <button className="primary" onClick={() => void startMonitoredSession(sg.id)}
                disabled={startSession.isPending || preparingFocus}>
                {preparingFocus ? 'Choosing a screen…' : 'Share screen & focus'}
              </button>
            )}
          </div>
        </Card>
      ))}

      <ErrorNote error={saveSubgoals.error || activate.error || startSession.error || monitoring.shareError} />
      <div className="row" style={{ marginTop: '0.6rem' }}>
        {!editing && q.state !== 'archived' && subgoals.length > 0 && (
          <button onClick={() => { setDraft(q.subgoals ?? []); setEditing(true) }}>Edit steps</button>
        )}
        {editing && (
          <>
            <button onClick={() => setDraft([...subgoals, {
              id: '', position: subgoals.length, title: 'New step', rationale: '',
              acceptance_criterion: 'Done when you say so.', difficulty: 2, estimated_sessions: 1,
              state: 'todo', evidence_specs: ['manual_confirmation'], manual_fallback: 'Did you finish this step?',
            }])}>Add step</button>
            <button className="primary" onClick={() => saveSubgoals.mutate(subgoals)}
              disabled={saveSubgoals.isPending}>Save changes</button>
            <button onClick={() => { setEditing(false); setDraft(null) }}>Discard</button>
          </>
        )}
        {q.state === 'draft' && subgoals.length > 0 && !editing && (
          <button className="primary" onClick={() => activate.mutate()} disabled={activate.isPending}>
            Activate quest
          </button>
        )}
        {q.state !== 'archived' && !editing && (
          <button onClick={() => archive.mutate()} disabled={archive.isPending}>Archive</button>
        )}
      </div>
    </>
  )
}
