import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '../api/client'
import type { Party, SimulatedPlayer } from '../api/types'
import { SimulatedPlayerCard } from '../components/SimulatedPlayerCard'
import { Card, ErrorNote, Spinner } from '../components/ui'

export function PartyHub() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [name, setName] = useState('')
  const [code, setCode] = useState('')
  const [selectedPlayers, setSelectedPlayers] = useState<string[]>([])

  const parties = useQuery({ queryKey: ['parties'], queryFn: () => api<Party[]>('/parties') })
  const players = useQuery({
    queryKey: ['multiplayer-players'],
    queryFn: () => api<SimulatedPlayer[]>('/multiplayer/players'),
  })
  const create = useMutation({
    mutationFn: () => api<Party>('/parties', { body: { name } }),
    onSuccess: (resp) => {
      queryClient.invalidateQueries({ queryKey: ['parties'] })
      navigate(`/party/${resp.data.id}`)
    },
  })
  const join = useMutation({
    mutationFn: () => api<Party>('/parties:join', { body: { code } }),
    onSuccess: (resp) => {
      queryClient.invalidateQueries({ queryKey: ['parties'] })
      navigate(`/party/${resp.data.id}`)
    },
  })
  const createCoop = useMutation({
    mutationFn: () => api<Party>('/parties', {
      body: { name: 'The Trailblazers', theme: 'meadow', simulated_player_ids: selectedPlayers },
    }),
    onSuccess: (resp) => {
      queryClient.invalidateQueries({ queryKey: ['parties'] })
      navigate(`/party/${resp.data.id}`)
    },
  })

  const togglePlayer = (playerId: string) => {
    setSelectedPlayers((current) => current.includes(playerId)
      ? current.filter((id) => id !== playerId)
      : current.length < 3 ? [...current, playerId] : current)
  }

  return (
    <>
      <header className="social-hero party-hero">
        <div>
          <p className="social-kicker">Better together</p>
          <h1>Parties</h1>
          <p>Gather a small crew, turn verified focus into boss damage, and keep every private goal private.</p>
        </div>
        <Link className="hero-link" to="/leaderboards">View league board <span aria-hidden="true">→</span></Link>
      </header>

      <section className="social-section">
        <div className="section-heading">
          <div><p className="social-kicker">Build a demo party</p><h2>Choose your co-op crew</h2></div>
          <span className="selection-count">{selectedPlayers.length}/3 selected</span>
        </div>
        <p className="muted small">Pick up to three simulated teammates. They join instantly and
          land an opening hit when you summon a boss.</p>
        {players.isPending && <Spinner label="Checking the clubhouse…" />}
        <ErrorNote error={players.error} />
        <div className="player-grid">
          {players.data?.data.map((player) => {
            const selected = selectedPlayers.includes(player.id)
            return <SimulatedPlayerCard key={player.id} player={player} actionLabel="Add to party"
              active={selected} onAction={() => togglePlayer(player.id)}
              disabled={!selected && selectedPlayers.length >= 3} />
          })}
        </div>
        <div className="coop-launcher">
          <div><strong>{selectedPlayers.length ? 'Your crew is ready.' : 'Choose at least one teammate.'}</strong>
            <span> You can still invite real friends afterward.</span></div>
          <button className="primary" onClick={() => createCoop.mutate()}
            disabled={!selectedPlayers.length || createCoop.isPending}>
            {createCoop.isPending ? 'Forming party…' : `Start co-op party${selectedPlayers.length ? ` · ${selectedPlayers.length + 1}` : ''}`}
          </button>
        </div>
        <ErrorNote error={createCoop.error} />
      </section>

      <div className="section-heading standard-match-heading">
        <div><p className="social-kicker">Invite your people</p><h2>Create or join with a code</h2></div>
      </div>
      <div className="grid-2">
        <Card title="Create a party">
          <label htmlFor="pname">Party name</label>
          <input id="pname" value={name} onChange={(e) => setName(e.target.value)} maxLength={60}
            placeholder="The Focus Friends" />
          <ErrorNote error={create.error} />
          <button className="primary" style={{ marginTop: '0.8rem' }} onClick={() => create.mutate()}
            disabled={create.isPending || !name.trim()}>Create</button>
        </Card>
        <Card title="Join a party">
          <label htmlFor="pcode">Invite code</label>
          <input id="pcode" value={code} onChange={(e) => setCode(e.target.value.toUpperCase())}
            maxLength={6} placeholder="ABC123" />
          <ErrorNote error={join.error} />
          <button className="primary" style={{ marginTop: '0.8rem' }} onClick={() => join.mutate()}
            disabled={join.isPending || code.length < 6}>Join</button>
        </Card>
      </div>
      {parties.isPending && <Spinner />}
      {!!parties.data?.data.length && <div className="section-heading"><h2>Your parties</h2></div>}
      {parties.data?.data.map((p) => (
        <Card key={p.id}>
          <div className="row spread">
            <div>
              <Link to={`/party/${p.id}`}><strong>{p.name}</strong></Link>
              <p className="small muted" style={{ margin: 0 }}>
                {p.members.length} member(s) · theme {p.theme}
                {p.active_boss?.state === 'active' && ' · ⚔️ boss active!'}
              </p>
            </div>
            <Link to={`/party/${p.id}`}><button>Open</button></Link>
          </div>
        </Card>
      ))}
    </>
  )
}
