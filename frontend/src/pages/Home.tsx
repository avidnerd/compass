import { useEffect, useRef, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, idempotencyKey, resetIdempotencyKey } from '../api/client'
import type { Character, CollegeLink, FocusSession, Quest } from '../api/types'
import { Companion } from '../components/Companion'
import { PixelIcon } from '../components/PixelIcon'
import { useFocusMonitoring } from '../components/FocusMonitoringProvider'
import { Card, ErrorNote, Meter, PageTitle, StateBox } from '../components/ui'

function stamp(iso: string | null) {
  if (!iso) return '--:--'
  const d = new Date(iso)
  return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
}

function day(iso: string | null) {
  if (!iso) return ''
  const d = new Date(iso)
  const today = new Date()
  const same = d.toDateString() === today.toDateString()
  return same ? 'Today' : d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
}

const SESSION_STATE: Record<string, string> = {
  running: 'Running', paused: 'Paused', ending: 'Wrapping up',
  completed: 'Completed', canceled: 'Canceled',
}

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
  const recent = sessions.data?.data.items ?? []
  const activeSession = recent.find((s) => ['running', 'paused', 'ending'].includes(s.state))

  // A row prints in only when it is genuinely new, never on every mount.
  const seen = useRef<Set<string> | null>(null)
  const [fresh, setFresh] = useState<Set<string>>(new Set())
  useEffect(() => {
    if (!recent.length) return
    const ids = recent.map((s) => s.id)
    if (seen.current === null) {
      seen.current = new Set(ids)
      return
    }
    const added = ids.filter((id) => !seen.current!.has(id))
    if (!added.length) return
    added.forEach((id) => seen.current!.add(id))
    setFresh(new Set(added))
    const t = setTimeout(() => setFresh(new Set()), 600)
    return () => clearTimeout(t)
  }, [recent])

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

  const minutes = activeQuest?.session_length_minutes ?? 25
  const done = activeQuest?.subgoal_done ?? 0
  const total = activeQuest?.subgoal_total ?? 0

  return (
    <div className="grid-2">
      <PageTitle>Home</PageTitle>
      <div>
        <Card
          title={ch.name}
          status={[`LV ${ch.level}`, `XP ${ch.xp}`, `CARE ${ch.care_points}`]}
        >
          <Companion character={ch} size={240} />
          <p className="small" style={{ textAlign: 'center', margin: '10px 0 12px' }}>
            {ch.species} · {ch.personality} · {ch.pronouns}
          </p>

          <Meter label="Energy" value={ch.energy} />
          <Meter label="Mood" value={ch.mood} />
          <Meter label="Bond" value={ch.bond} />

          <div className="row" style={{ marginTop: 12 }}>
            <button onClick={() => care.mutate({ action: 'feed' })} disabled={care.isPending}>
              <PixelIcon name="feed" /> Feed
            </button>
            <button onClick={() => care.mutate({ action: 'play' })} disabled={care.isPending}>
              <PixelIcon name="play" /> Play
            </button>
            <button onClick={() => care.mutate({ action: 'rest' })} disabled={care.isPending}>
              <PixelIcon name="rest" /> Rest
            </button>
            <Link to="/character/customize">
              <button><PixelIcon name="customize" /> Customize</button>
            </Link>
          </div>

          <label htmlFor="encouragement">Leave a note in the journal</label>
          <div className="row">
            <input id="encouragement" placeholder="Something worth remembering later…"
              value={note} onChange={(e) => setNote(e.target.value)} maxLength={240}
              style={{ flex: 1 }} />
            <button onClick={() => note.trim() && care.mutate({ action: 'encourage', note })}
              disabled={care.isPending || !note.trim()}>
              <PixelIcon name="note" /> Save
            </button>
          </div>
          {careMsg && <p className="small" role="status" style={{ marginTop: 8 }}>{careMsg}</p>}
          <ErrorNote error={care.error} />
        </Card>

        <Card title="Stats" status={['6 channels']}>
          <Meter label="Focus" value={ch.stat_focus} />
          <Meter label="Curiosity" value={ch.stat_curiosity} />
          <Meter label="Craft" value={ch.stat_craft} />
          <Meter label="Communication" value={ch.stat_communication} />
          <Meter label="Collaboration" value={ch.stat_collaboration} />
          <Meter label="Balance" value={ch.stat_balance} />
        </Card>
      </div>

      <div>
        <Card
          title="Focus"
          actions={activeSession &&
            <Link to={`/focus/${activeSession.id}`}><button className="primary">Return to session</button></Link>}
          status={[activeSession ? SESSION_STATE[activeSession.state] ?? activeSession.state : 'Idle',
            `${minutes} min`]}
        >
          {activeSession ? (
            <p>A session is {SESSION_STATE[activeSession.state]?.toLowerCase() ?? activeSession.state}. Jump back in.</p>
          ) : (
            <>
              <p>Start a focus session. Verified effort is what feeds your companion's growth —
                nothing here grows because you said it did.</p>
              <div className="monitoring-disclosure">
                <strong>Private attention view included</strong>
                Compass samples the screen you choose. It never records audio, camera, keystrokes
                or clipboard, and raw images are deleted after analysis.
              </div>
              <div className="row">
                <button className="primary" onClick={() => void startFocus(false)}
                  disabled={quickFocus.isPending || preparingFocus}>
                  <PixelIcon name="run" />
                  {preparingFocus ? ' Choosing a screen…' : ` Share screen & focus ${minutes} min`}
                </button>
                <button onClick={() => void startFocus(true)}
                  disabled={quickFocus.isPending || preparingFocus}>
                  <PixelIcon name="demo" /> 1-min demo
                </button>
              </div>
              <ErrorNote error={quickFocus.error || monitoring.shareError} />
            </>
          )}
        </Card>

        <Card
          title="Active quest"
          actions={<Link to="/quests/new"><button><PixelIcon name="plus" /> New</button></Link>}
          status={activeQuest ? [`${done}/${total} verified`,
            activeQuest.target_date ? `Target ${activeQuest.target_date}` : 'No target date'] : undefined}
        >
          {activeQuest ? (
            <>
              <p><strong>{activeQuest.goal}</strong></p>
              <div className="row" style={{ gap: 4, margin: '10px 0' }}>
                {Array.from({ length: total }, (_, i) => (
                  <StateBox key={i} on={i < done}
                    label={i < done ? `Subgoal ${i + 1} verified` : `Subgoal ${i + 1} not yet verified`} />
                ))}
              </div>
              <Link to={`/quests/${activeQuest.id}`}><button>Open quest</button></Link>
            </>
          ) : (
            <p>No active quest. <Link to="/quests/new">Set a goal</Link> and Compass will break it
              into steps it can actually verify.</p>
          )}
        </Card>

        {college.data?.data.status === 'linked' && (
          <Card title="College OS"
            actions={<Link to="/college"><button>Open</button></Link>}>
            <p className="small" style={{ margin: 0 }}>
              Linked to <strong>{college.data.data.dashboard_name}</strong>. Import this week's Big 3
              and semester goals as quests — the sheet's Definition of Done becomes the acceptance
              criterion Compass verifies.
            </p>
          </Card>
        )}

        <Card title="Recent sessions" status={[`${recent.length} of last 5`]}>
          {recent.length === 0 ? (
            <p className="log-empty" style={{ padding: 0 }}>
              No sessions recorded yet. The log fills itself — you can't write to it.
            </p>
          ) : (
            <div className="log">
              {recent.map((s) => (
                <div key={s.id} className={`log-row ${fresh.has(s.id) ? 'fresh' : ''}`}>
                  <StateBox on={s.state === 'completed'}
                    label={s.state === 'completed' ? 'Completed' : SESSION_STATE[s.state] ?? s.state} />
                  <span className="log-what">
                    <strong>{Math.round(s.planned_seconds / 60)} min focus{s.demo ? ' (demo)' : ''}</strong>
                    <small>{SESSION_STATE[s.state] ?? s.state}
                      {s.focus_score !== null ? ` · score ${s.focus_score}` : ''}</small>
                  </span>
                  <span className="log-stamp">
                    {day(s.finished_at ?? s.started_at)} {stamp(s.finished_at ?? s.started_at)}
                  </span>
                </div>
              ))}
            </div>
          )}
        </Card>
      </div>
    </div>
  )
}
