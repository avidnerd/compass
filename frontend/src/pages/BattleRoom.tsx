import { useNavigate, useParams } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '../api/client'
import type { Battle, Profile, Quest, Subgoal } from '../api/types'
import { Card, ErrorNote, Spinner } from '../components/ui'
import { formatSeconds, useServerNow } from '../hooks/useServerTimer'

export function BattleRoom() {
  const { battleId } = useParams()
  const navigate = useNavigate()
  const queryClient = useQueryClient()

  const battle = useQuery({
    queryKey: ['battle', battleId],
    queryFn: () => api<Battle>(`/battles/${battleId}`),
    refetchInterval: (q) => {
      const s = q.state.data?.data.state
      return s === 'countdown' ? 700 : s && ['waiting', 'active', 'resolving'].includes(s) ? 3000 : false
    },
  })
  const me = useQuery({ queryKey: ['me'], queryFn: () => api<Profile>('/me') })
  const quests = useQuery({ queryKey: ['quests'], queryFn: () => api<{ items: Quest[] }>('/quests') })
  const activeQuest = quests.data?.data.items.find((q) => q.state === 'active')
  const questDetail = useQuery({
    queryKey: ['quest', activeQuest?.id],
    queryFn: () => api<Quest>(`/quests/${activeQuest!.id}`),
    enabled: !!activeQuest,
  })

  const ready = useMutation({
    mutationFn: (vars: { ready: boolean; subgoal_id?: string | null }) =>
      api<Battle>(`/battles/${battleId}:ready`, { body: vars }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['battle', battleId] }),
  })
  const start = useMutation({
    mutationFn: () => api<Battle>(`/battles/${battleId}:start`, { body: {} }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['battle', battleId] }),
  })
  const leave = useMutation({
    mutationFn: () => api<Battle>(`/battles/${battleId}:leave`, { body: {} }),
    onSuccess: () => navigate('/battle'),
  })

  const serverNow = useServerNow(battle.data?.data.server_time)

  if (battle.isPending) return <Spinner />
  if (battle.isError) return <ErrorNote error={battle.error} />
  const b = battle.data.data
  const myId = me.data?.data.id
  const mine = b.players.find((p) => p.profile_id === myId)
  const isHost = b.host_profile_id === myId
  const subgoals: Subgoal[] = (questDetail.data?.data.subgoals ?? [])
    .filter((s) => ['todo', 'in_progress'].includes(s.state))

  const remaining = b.ends_at ? (new Date(b.ends_at).getTime() - serverNow) / 1000 : null

  return (
    <>
      <div className="row spread">
        <h1>Battle room</h1>
        <span className="badge">code: {b.code}</span>
      </div>

      {b.state === 'waiting' && (
        <Card title="Lobby">
          <p className="muted small">Pick a private subgoal (others only see that you picked one),
            then mark ready. The host starts when everyone's set.</p>
          <label htmlFor="sg">My private subgoal (optional)</label>
          <select id="sg" value={mine?.subgoal_id ?? ''} onChange={(e) =>
            ready.mutate({ ready: mine?.ready ?? false, subgoal_id: e.target.value || null })}>
            <option value="">Just focus (no subgoal)</option>
            {subgoals.map((s) => <option key={s.id} value={s.id}>{s.title}</option>)}
          </select>
          <div className="row" style={{ marginTop: '0.7rem' }}>
            <button className={mine?.ready ? '' : 'primary'}
              onClick={() => ready.mutate({ ready: !mine?.ready, subgoal_id: mine?.subgoal_id })}>
              {mine?.ready ? 'Unready' : 'I am ready'}
            </button>
            {isHost && (
              <button className="primary" onClick={() => start.mutate()}
                disabled={start.isPending || b.players.filter((p) => !p.left).length < 2 ||
                  !b.players.filter((p) => !p.left).every((p) => p.ready)}>
                Start battle
              </button>
            )}
            <button onClick={() => leave.mutate()}>Leave</button>
          </div>
          <ErrorNote error={start.error || ready.error} />
        </Card>
      )}

      {b.state === 'countdown' && (
        <Card><div className="timer-big">Starting…</div>
          <p className="timer-state">Take a breath. The sprint begins in seconds.</p></Card>
      )}

      {(b.state === 'active' || b.state === 'resolving') && (
        <Card>
          <div className="timer-big">
            {b.state === 'resolving' ? 'Verifying…' : remaining !== null ? formatSeconds(remaining) : '—'}
          </div>
          <p className="timer-state">
            {b.state === 'resolving'
              ? 'Everyone finished — Compass is checking evidence independently for each player.'
              : 'Synchronized sprint in progress. Your session runs on the focus page too.'}
          </p>
          {mine?.session_id && b.state === 'active' && (
            <div className="row" style={{ justifyContent: 'center' }}>
              <button className="primary" onClick={() => navigate(`/focus/${mine.session_id}`)}>
                Open my focus session
              </button>
            </div>
          )}
        </Card>
      )}

      {b.state === 'completed' && (
        <Card title="Results">
          <div className="podium">
            {[...b.players].filter((p) => !p.left).sort((a, c) => (a.placement ?? 9) - (c.placement ?? 9))
              .map((p) => (
                <div key={p.profile_id} className="podium-slot">
                  <div>{p.placement === 1 ? '👑' : p.placement === 2 ? '🥈' : '🥉'}</div>
                  <div className="podium-bar" style={{ height: 30 + (p.power ?? 0) }}>
                    {p.power ?? '—'}
                  </div>
                  <div className="small">{p.display_name}</div>
                </div>
              ))}
          </div>
          <p className="small muted" style={{ textAlign: 'center' }}>
            Power = 75% personal-baseline focus score + verification bonus + stats. Scores within
            two points count as a draw.</p>
          <div className="row" style={{ justifyContent: 'center' }}>
            <button className="primary" onClick={() => navigate('/battle')}>Back to battles</button>
          </div>
        </Card>
      )}

      {b.state === 'canceled' && (
        <Card><p>This battle was canceled.</p>
          <button onClick={() => navigate('/battle')}>Back</button></Card>
      )}

      <Card title="Players">
        {b.players.map((p) => (
          <div key={p.profile_id} className="list-item">
            <span className="room-player">
              <span className="mini-avatar" aria-hidden="true">{p.avatar ?? '🧭'}</span>
              <span><strong>{p.display_name}</strong>{p.profile_id === b.host_profile_id ? ' (host)' : ''}
                {p.left ? ' — left' : ''}
                {p.title && <small>{p.title}</small>}</span>
            </span>
            <span className="row">
              {p.is_simulated && <span className="badge">demo rival</span>}
              {b.state === 'waiting' && (
                <span className={`badge ${p.ready ? '' : 'badge-warn'}`}>
                  {p.ready ? 'ready' : 'not ready'}{p.has_subgoal ? ' · has subgoal' : ''}
                </span>
              )}
              {b.state === 'completed' && p.placement != null && (
                <span className="badge">#{p.placement} · power {p.power}</span>
              )}
            </span>
          </div>
        ))}
      </Card>
    </>
  )
}
