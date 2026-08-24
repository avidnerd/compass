import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, idempotencyKey, resetIdempotencyKey } from '../api/client'
import type { Character, CollegeLink, FocusSession, Quest } from '../api/types'
import { Companion } from '../components/Companion'
import { useFocusMonitoring } from '../components/FocusMonitoringProvider'
import { Card, ErrorNote, Meter, StatTile } from '../components/ui'

export function Home() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [note, setNote] = useState('')
  const [careMsg, setCareMsg] = useState<string | null>(null)
  const [preparingFocus, setPreparingFocus] = useState(false)
  const monitoring = useFocusMonitoring()

  const character = useQuery({
    queryKey: ['character'],
    queryFn: () => api<Character>('/character'),
    retry: false,
  })
  const quests = useQuery({
    queryKey: ['quests'],
    queryFn: () => api<{ items: Quest[] }>('/quests'),
  })
  const sessions = useQuery({
    queryKey: ['sessions'],
    queryFn: () => api<{ items: FocusSession[] }>('/focus-sessions?limit=5'),
  })
  // Cheap local-only lookup — reading the dashboard itself happens on /college.
  const college = useQuery({
    queryKey: ['college-status'],
    queryFn: () => api<CollegeLink>('/college/status'),
    retry: false,
  })

  const care = useMutation({
    mutationFn: (body: { action: string; note?: string }) =>
      api<{ character: Character; message: string }>('/character/actions', { body }),
    onSuccess: (resp) => {
      setCareMsg(resp.data.message)
      queryClient.invalidateQueries({ queryKey: ['character'] })
      setNote('')
    },
  })

  const activeQuest = quests.data?.data.items.find((q) => q.state === 'active')
  const activeSession = sessions.data?.data.items.find((s) =>
    ['running', 'paused', 'ending'].includes(s.state))

  const quickFocus = useMutation({
    mutationFn: (demo: boolean) => {
      const scope = `quick-focus-${demo}`
      return api<FocusSession>('/focus-sessions', {
        body: { planned_minutes: demo ? 1 : activeQuest?.session_length_minutes ?? 25, demo },
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

  const startFocus = async (demo: boolean) => {
    setPreparingFocus(true)
    const sharing = await monitoring.requestScreen()
    if (!sharing) {
      setPreparingFocus(false)
      return
    }
    quickFocus.mutate(demo)
  }

  if (character.isError) {
    return (
      <Card title="No companion yet">
        <p>Finish onboarding to hatch your companion.</p>
        <Link to="/onboarding/companion"><button className="primary">Continue onboarding</button></Link>
      </Card>
    )
  }
  const ch = character.data?.data
  if (!ch) return <p aria-busy="true">Loading the habitat…</p>

  return (
    <div className="grid-2">
      <Card>
        <Companion character={ch} size={260} />
        <h1 style={{ textAlign: 'center' }}>{ch.name}</h1>
        <p className="muted" style={{ textAlign: 'center', marginTop: 0 }}>
          Level {ch.level} {ch.species} · {ch.personality} · {ch.pronouns}
        </p>
        <div className="grid-tiles">
          <StatTile label="Level" value={ch.level} />
          <StatTile label="XP" value={ch.xp} />
          <StatTile label="Care points" value={ch.care_points} />
        </div>
        <Meter label="Energy" value={ch.energy} />
        <Meter label="Mood" value={ch.mood} />
        <Meter label="Bond" value={ch.bond} />
        <div className="row" style={{ marginTop: '0.6rem' }}>
          <button onClick={() => care.mutate({ action: 'feed' })} disabled={care.isPending}>🍎 Feed</button>
          <button onClick={() => care.mutate({ action: 'play' })} disabled={care.isPending}>🪀 Play</button>
          <button onClick={() => care.mutate({ action: 'rest' })} disabled={care.isPending}>😴 Rest</button>
          <Link to="/character/customize"><button>🎨 Customize</button></Link>
        </div>
        <div className="row" style={{ marginTop: '0.5rem' }}>
          <input aria-label="Encouragement note" placeholder="Leave a little note for the journal…"
            value={note} onChange={(e) => setNote(e.target.value)} maxLength={240} style={{ flex: 1 }} />
          <button onClick={() => note.trim() && care.mutate({ action: 'encourage', note })}
            disabled={care.isPending || !note.trim()}>💌</button>
        </div>
        {careMsg && <p className="small muted" role="status">{careMsg}</p>}
        <ErrorNote error={care.error} />
      </Card>

      <div>
        <Card title="Focus" actions={activeSession &&
          <Link to={`/focus/${activeSession.id}`}><button className="primary">Return to session</button></Link>}>
          {activeSession ? (
            <p>A session is {activeSession.state}. Jump back in!</p>
          ) : (
            <>
              <p className="muted">Start a focus session — verified effort feeds your companion's growth.</p>
              <div className="monitoring-disclosure">
                <strong>Private attention view included.</strong> Compass samples the screen you choose;
                it never records audio, camera, keystrokes, or clipboard. Raw images are deleted after analysis.
              </div>
              <div className="row">
                <button className="primary" onClick={() => void startFocus(false)}
                  disabled={quickFocus.isPending || preparingFocus}>
                  {preparingFocus ? 'Choosing a screen…' : `▶ Share screen & focus ${activeQuest?.session_length_minutes ?? 25} min`}
                </button>
                <button onClick={() => void startFocus(true)}
                  disabled={quickFocus.isPending || preparingFocus}>
                  🎬 1-min demo session
                </button>
              </div>
              <ErrorNote error={quickFocus.error || monitoring.shareError} />
            </>
          )}
        </Card>

        <Card title="Active quest" actions={<Link to="/quests/new"><button>New quest</button></Link>}>
          {activeQuest ? (
            <>
              <p><strong>{activeQuest.goal}</strong></p>
              <p className="small muted">{activeQuest.subgoal_done ?? 0}/{activeQuest.subgoal_total ?? 0} subgoals done
                {activeQuest.target_date ? ` · target ${activeQuest.target_date}` : ''}</p>
              <Link to={`/quests/${activeQuest.id}`}><button>Open quest</button></Link>
            </>
          ) : (
            <p className="muted">No active quest. <Link to="/quests/new">Set a goal</Link> and let
              Compass break it into verifiable steps.</p>
          )}
        </Card>

        {college.data?.data.status === 'linked' && (
          <Card title="College OS"
            actions={<Link to="/college"><button>Open</button></Link>}>
            <p className="small muted" style={{ margin: 0 }}>
              Linked to <strong>{college.data.data.dashboard_name}</strong>. Import this week's Big 3
              and semester goals as quests — the sheet's Definition of Done becomes the acceptance
              criterion Compass verifies.
            </p>
          </Card>
        )}

        <Card title="Stats">
          <Meter label="Focus" value={ch.stat_focus} />
          <Meter label="Curiosity" value={ch.stat_curiosity} />
          <Meter label="Craft" value={ch.stat_craft} />
          <Meter label="Communication" value={ch.stat_communication} />
          <Meter label="Collaboration" value={ch.stat_collaboration} />
          <Meter label="Balance" value={ch.stat_balance} />
        </Card>
      </div>
    </div>
  )
}
