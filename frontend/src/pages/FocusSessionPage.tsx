import { useEffect } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, idempotencyKey, resetIdempotencyKey } from '../api/client'
import type { Character, FocusSession, Verification } from '../api/types'
import { Companion } from '../components/Companion'
import { FocusAttentionCard } from '../components/FocusAttentionCard'
import { useFocusMonitoring } from '../components/FocusMonitoringProvider'
import { Card, CONNECTOR_LABELS, ErrorNote, EVIDENCE_LABELS, Spinner } from '../components/ui'
import { formatSeconds, useServerNow } from '../hooks/useServerTimer'
import { PixelIcon } from '../components/PixelIcon'

function EvidenceCard({ verification }: { verification: Verification }) {
  return (
    <Card title="Evidence card">
      <p><strong>What Compass observed:</strong> {verification.observed || '—'}</p>
      <p><strong>What it could not observe:</strong> {verification.not_observed || '—'}</p>
      <p className="small muted">
        Sources: {verification.sources.length
          ? verification.sources.map((s) => CONNECTOR_LABELS[s] ?? s).join(', ')
          : 'none'} ·
        {verification.model_id
          ? <> interpreted by <code>{verification.model_id}</code> (confidence {Math.round(verification.confidence * 100)}%)</>
          : ' no free model was available — deterministic evidence only'}
      </p>
      <p>{verification.explanation}</p>
      {verification.evidence.length > 0 && (
        <ul className="small">
          {verification.evidence.slice(0, 10).map((e) => (
            <li key={e.id}>
              [{CONNECTOR_LABELS[e.source] ?? e.source}] {EVIDENCE_LABELS[e.event_type] ?? e.event_type}: {e.summary}
              {e.debug_excerpt && (
                <details style={{ marginTop: '0.25rem' }}>
                  <summary className="muted">Debug: content Compass read ({e.debug_excerpt.length} chars)</summary>
                  <pre style={{ whiteSpace: 'pre-wrap', background: 'var(--accent-soft)',
                    padding: '0.5rem', borderRadius: 8, maxHeight: 220, overflow: 'auto' }}>
                    {e.debug_excerpt}
                  </pre>
                </details>
              )}
            </li>
          ))}
        </ul>
      )}
    </Card>
  )
}

export function FocusSessionPage() {
  const { sessionId } = useParams()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const monitoring = useFocusMonitoring()
  const syncMonitoringSession = monitoring.syncSession

  const detail = useQuery({
    queryKey: ['session', sessionId],
    queryFn: () => api<{ session: FocusSession; verification: Verification | null }>(
      `/focus-sessions/${sessionId}`),
    refetchInterval: (q) => {
      const state = q.state.data?.data.session.state
      return state === 'ending' ? 1500 : state === 'running' ? 15000 : false
    },
  })
  const character = useQuery({
    queryKey: ['character'],
    queryFn: () => api<Character>('/character'),
    retry: false,
  })

  const act = useMutation({
    mutationFn: (action: 'pause' | 'resume') =>
      api<FocusSession>(`/focus-sessions/${sessionId}:${action}`, { body: {} }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['session', sessionId] }),
  })
  const finish = useMutation({
    mutationFn: async () => {
      await monitoring.finishAndStop()
      return api<FocusSession>(`/focus-sessions/${sessionId}:finish`, {
        body: {}, idempotencyKey: idempotencyKey(`finish-${sessionId}`),
      })
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['session', sessionId] }),
  })
  const cancel = useMutation({
    mutationFn: async () => {
      await monitoring.cancelAndStop()
      return api<FocusSession>(`/focus-sessions/${sessionId}:cancel`, { body: {} })
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['session', sessionId] }),
  })
  const confirm = useMutation({
    mutationFn: (vars: { id: string; accepted: boolean }) =>
      api<Verification>(`/verifications/${vars.id}:confirm`, { body: { accepted: vars.accepted } }),
    onSuccess: () => {
      resetIdempotencyKey(`finish-${sessionId}`)
      queryClient.invalidateQueries()
    },
  })
  const recheck = useMutation({
    mutationFn: (id: string) => api(`/verifications/${id}:recheck`, { body: {} }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['session', sessionId] }),
  })

  const serverNow = useServerNow(detail.data?.data.session.server_time)

  const currentSession = detail.data?.data.session
  useEffect(() => {
    if (currentSession) syncMonitoringSession(currentSession)
  }, [currentSession, syncMonitoringSession])

  if (detail.isPending) return <Spinner />
  if (detail.isError) return <ErrorNote error={detail.error} />
  const { session, verification } = detail.data.data

  const startedMs = new Date(session.started_at).getTime()
  const pausedMs = (session.paused_total_seconds ?? 0) * 1000 +
    (session.state === 'paused' && session.paused_at
      ? serverNow - new Date(session.paused_at).getTime() : 0)
  const elapsed = session.finished_at
    ? (new Date(session.finished_at).getTime() - startedMs) / 1000 - session.paused_total_seconds
    : (serverNow - startedMs - pausedMs) / 1000
  const remaining = session.planned_seconds - elapsed

  return (
    <div style={{ maxWidth: 620, margin: '0 auto' }}>
      {session.demo && <p className="badge badge-warn" style={{ display: 'inline-block' }}>
        1-minute demo session</p>}

      {(session.state === 'running' || session.state === 'paused') && (
        <Card>
          <div className="timer-big" aria-live="off">{formatSeconds(Math.max(0, remaining))}</div>
          <p className="timer-state">{session.state === 'paused' ? 'Paused — no judgment, breathe.' :
            remaining <= 0 ? 'Time! Finish whenever you are ready.' : 'Focusing…'}</p>
          {character.data && <Companion character={{ ...character.data.data, animation: session.state === 'paused' ? 'rest' : 'idle' }} size={150} showHabitat={false} />}
          <div className={`live-monitor ${monitoring.isSharing ? 'sharing' : ''}`}>
            <div className="live-monitor-title">
              <span className="monitor-dot" aria-hidden="true" />
              <strong>{monitoring.isSharing
                ? session.state === 'paused' ? 'Screen shared · sampling paused' : 'Watching your chosen screen'
                : session.monitoring_enabled ? 'Screen sharing stopped' : 'Screen monitoring not started'}</strong>
            </div>
            {monitoring.isSharing ? (
              <p className="small muted">
                {monitoring.capturedCount} moments captured · {monitoring.uploadedCount} saved locally
                {monitoring.pendingCount ? ` · ${monitoring.pendingCount} sending` : ''}
              </p>
            ) : (
              <>
                <p className="small muted">Choose what Compass can see. It samples still moments only —
                  never audio, camera, keystrokes, or clipboard.</p>
                <button className="primary" onClick={() => void monitoring.requestForSession(session)}>
                  Share a screen & resume monitoring
                </button>
              </>
            )}
            {monitoring.surfaceWarning && <p className="small badge badge-warn">{monitoring.surfaceWarning}</p>}
            <ErrorNote error={monitoring.shareError || monitoring.frameError} />
          </div>
          <div className="row" style={{ justifyContent: 'center' }}>
            {session.state === 'running'
              ? <button onClick={() => act.mutate('pause')}>Pause</button>
              : <button onClick={() => act.mutate('resume')}><PixelIcon name="run" /> Resume</button>}
            <button className="primary" onClick={() => finish.mutate()} disabled={finish.isPending}>
              <PixelIcon name="check" /> Finish & verify
            </button>
            <button onClick={() => cancel.mutate()} disabled={cancel.isPending}>Cancel</button>
          </div>
          <ErrorNote error={act.error || finish.error || cancel.error} />
        </Card>
      )}

      {session.state === 'ending' && !verification && (
        <Card><p aria-busy="true">Session frozen. Refreshing only the needed connectors and
          extracting evidence…</p></Card>
      )}

      {session.state === 'ending' && verification?.result === 'needs_confirmation' && (
        <>
          <Card title="Compass isn't sure — you decide">
            <p>{verification.human_confirmed === null
              ? 'The evidence was inconclusive. Did you complete this step?'
              : 'Thanks — recorded.'}</p>
            <div className="row">
              <button className="primary" disabled={confirm.isPending}
                onClick={() => confirm.mutate({ id: verification.id, accepted: true })}>
                Yes, I completed it
              </button>
              <button disabled={confirm.isPending}
                onClick={() => confirm.mutate({ id: verification.id, accepted: false })}>
                Not yet
              </button>
              <button disabled={recheck.isPending}
                onClick={() => recheck.mutate(verification.id)}>
                Recheck evidence
              </button>
            </div>
            <p className="small muted">Confirming yourself grants 80% of normal rewards. The gap
              is deliberate: it keeps verified progress worth more than asserted progress.</p>
            <ErrorNote error={confirm.error || recheck.error} />
          </Card>
          <EvidenceCard verification={verification} />
          {session.focus_evaluation && <FocusAttentionCard evaluation={session.focus_evaluation} />}
        </>
      )}

      {session.state === 'completed' && (
        <>
          <Card title={verification?.result === 'verified' ? 'Verified' :
            verification?.human_confirmed ? 'Counted — you confirmed it' : 'Session complete'}>
            <div className="grid-tiles">
              <div className="stat-tile"><div className="stat-value">{session.focus_score ?? '—'}</div>
                <div className="stat-label">Focus score</div></div>
              <div className="stat-tile"><div className="stat-value">{formatSeconds(elapsed)}</div>
                <div className="stat-label">Focused time</div></div>
            </div>
            {verification?.result === 'not_completed' && (
              <p>This one didn't land — that's okay. Maybe pick a smaller slice next session;
                your companion suggests just opening the file counts as a start.</p>
            )}
            <div className="row">
              <button className="primary" onClick={() => navigate(session.quest_id ? `/quests/${session.quest_id}` : '/home')}>
                Continue
              </button>
            </div>
          </Card>
          {verification && <EvidenceCard verification={verification} />}
          {session.focus_evaluation && <FocusAttentionCard evaluation={session.focus_evaluation} />}
        </>
      )}

      {session.state === 'canceled' && (
        <Card><p>Session canceled — no worries. <button onClick={() => navigate('/home')}>Home</button></p></Card>
      )}
    </div>
  )
}
