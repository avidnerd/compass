import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useMutation, useQuery } from '@tanstack/react-query'
import { api, idempotencyKey, resetIdempotencyKey } from '../api/client'
import type { Battle, SimulatedPlayer } from '../api/types'
import { SimulatedPlayerCard } from '../components/SimulatedPlayerCard'
import { Card, ErrorNote, Spinner } from '../components/ui'
import { PixelIcon } from '../components/PixelIcon'

export function BattleHub() {
  const navigate = useNavigate()
  const [minutes, setMinutes] = useState(25)
  const [demo, setDemo] = useState(false)
  const [code, setCode] = useState('')
  const players = useQuery({
    queryKey: ['multiplayer-players'],
    queryFn: () => api<SimulatedPlayer[]>('/multiplayer/players'),
  })

  const create = useMutation({
    mutationFn: (opponentId?: string) => api<Battle>('/battles', {
      body: opponentId
        ? { minutes: 1, demo: true, opponent_ids: [opponentId] }
        : { minutes, demo },
      idempotencyKey: idempotencyKey(opponentId ? `battle-duel-${opponentId}` : 'battle-create'),
    }),
    onSuccess: (resp, opponentId) => {
      resetIdempotencyKey(opponentId ? `battle-duel-${opponentId}` : 'battle-create')
      navigate(`/battle/${resp.data.id}`)
    },
  })
  const join = useMutation({
    mutationFn: () => api<Battle>('/battles:join', { body: { code } }),
    onSuccess: (resp) => navigate(`/battle/${resp.data.id}`),
  })

  return (
    <>
      <header className="social-hero battle-hero">
        <div>
          <h1>Focus battles</h1>
          <p>A synchronized sprint where your work stays private and only the momentum is shared.</p>
        </div>
        <Link className="hero-link" to="/leaderboards">View league board <PixelIcon name="right" /></Link>
      </header>

      <section className="social-section">
        <div className="section-heading">
          <div><h2>Choose a demo rival</h2></div>
          <span className="badge">1-minute quick match</span>
        </div>
        <p className="muted small">These simulated players arrive ready. Pick a rival, ready up in
          the lobby, and run a complete 1v1 demo without a second browser.</p>
        {players.isPending && <Spinner label="Finding rivals…" />}
        <ErrorNote error={players.error} />
        <div className="player-grid">
          {players.data?.data.map((player) => (
            <SimulatedPlayerCard key={player.id} player={player} actionLabel="Challenge · 1 min"
              onAction={() => create.mutate(player.id)}
              disabled={create.isPending || player.status === 'away'} />
          ))}
        </div>
        <ErrorNote error={create.error} />
      </section>

      <div className="section-heading standard-match-heading">
        <div><h2>Host or join a friend</h2></div>
      </div>
      <div className="grid-2">
        <Card title="Host a battle">
          <label>Length</label>
          <div className="row" role="radiogroup" aria-label="Battle length">
            {[15, 25, 50].map((m) => (
              <button key={m} role="radio" aria-checked={minutes === m && !demo}
                className={minutes === m && !demo ? 'primary' : ''}
                onClick={() => { setMinutes(m); setDemo(false) }}>{m} min</button>
            ))}
            <button role="radio" aria-checked={demo} className={demo ? 'primary' : ''}
              onClick={() => setDemo(true)}>1 min (demo)</button>
          </div>
          <ErrorNote error={create.error} />
          <button className="primary" style={{ marginTop: '0.8rem' }}
            onClick={() => create.mutate(undefined)} disabled={create.isPending}>Create battle</button>
        </Card>
        <Card title="Join with a code">
          <label htmlFor="code">Six-character code</label>
          <input id="code" value={code} onChange={(e) => setCode(e.target.value.toUpperCase())}
            maxLength={6} placeholder="ABC123" />
          <ErrorNote error={join.error} />
          <button className="primary" style={{ marginTop: '0.8rem' }}
            onClick={() => join.mutate()} disabled={join.isPending || code.length < 6}>Join</button>
        </Card>
      </div>
    </>
  )
}
