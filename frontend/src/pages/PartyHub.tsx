import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '../api/client'
import type { Party, SimulatedPlayer } from '../api/types'
import { SimulatedPlayerCard } from '../components/SimulatedPlayerCard'
import { Card, ErrorNote, PageTitle, Spinner } from '../components/ui'

/** Focus rooms: working alongside other people, which is the one social
 *  mechanism with real evidence behind it. No ranking, no scores, no contest. */

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
  const afterCreate = (resp: { data: Party }) => {
    queryClient.invalidateQueries({ queryKey: ['parties'] })
    navigate(`/party/${resp.data.id}`)
  }
  const create = useMutation({
    mutationFn: () => api<Party>('/parties', { body: { name } }),
    onSuccess: afterCreate,
  })
  const join = useMutation({
    mutationFn: () => api<Party>('/parties:join', { body: { code } }),
    onSuccess: afterCreate,
  })
  const createDemo = useMutation({
    mutationFn: () => api<Party>('/parties', {
      body: { name: 'Study room', theme: 'meadow', simulated_player_ids: selectedPlayers },
    }),
    onSuccess: afterCreate,
  })

  const togglePlayer = (playerId: string) => {
    setSelectedPlayers((current) => current.includes(playerId)
      ? current.filter((id) => id !== playerId)
      : current.length < 3 ? [...current, playerId] : current)
  }

  return (
    <>
      <PageTitle>Focus rooms</PageTitle>

      <Card title="Focus rooms" status={[`${parties.data?.data.length ?? 0} joined`]}>
        <p>Working alongside other people makes it easier to start and easier to keep going.
          A room shares only that you are focusing and for how long. Never the goal, the file
          or the evidence behind it.</p>
      </Card>

      <div className="grid-2">
        <Card title="Start a room">
          <label htmlFor="pname">Room name</label>
          <input id="pname" value={name} onChange={(e) => setName(e.target.value)} maxLength={60}
            placeholder="Thursday afternoon" />
          <ErrorNote error={create.error} />
          <button className="primary" style={{ marginTop: 12 }} onClick={() => create.mutate()}
            disabled={create.isPending || !name.trim()}>Create</button>
        </Card>
        <Card title="Join a room">
          <label htmlFor="pcode">Invite code</label>
          <input id="pcode" value={code} onChange={(e) => setCode(e.target.value.toUpperCase())}
            maxLength={6} placeholder="ABC123" />
          <ErrorNote error={join.error} />
          <button className="primary" style={{ marginTop: 12 }} onClick={() => join.mutate()}
            disabled={join.isPending || code.length < 6}>Join</button>
        </Card>
      </div>

      {!!parties.data?.data.length && (
        <Card title="Your rooms" status={[`${parties.data.data.length} joined`]}>
          {parties.data.data.map((p) => (
            <div key={p.id} className="list-item">
              <span>
                <Link to={`/party/${p.id}`}><strong>{p.name}</strong></Link>
                <span className="small"> · {p.members.length} here</span>
              </span>
              <Link to={`/party/${p.id}`}><button>Open</button></Link>
            </div>
          ))}
        </Card>
      )}
      {parties.isPending && <Spinner />}

      <Card
        title="Try it with demo company"
        status={[`${selectedPlayers.length}/3 chosen`]}
      >
        <p className="small">Compass has no other real users yet, so these are simulated
          companions for trying the room out. They are clearly marked as demo everywhere
          they appear.</p>
        {players.isPending && <Spinner label="Loading…" />}
        <ErrorNote error={players.error} />
        <div className="player-grid">
          {players.data?.data.map((player) => {
            const selected = selectedPlayers.includes(player.id)
            return <SimulatedPlayerCard key={player.id} player={player} actionLabel="Add"
              active={selected} onAction={() => togglePlayer(player.id)}
              disabled={!selected && selectedPlayers.length >= 3} />
          })}
        </div>
        <div className="coop-launcher">
          <span>{selectedPlayers.length ? 'Ready when you are.' : 'Choose at least one.'}</span>
          <button className="primary" onClick={() => createDemo.mutate()}
            disabled={!selectedPlayers.length || createDemo.isPending}>
            {createDemo.isPending ? 'Opening room…' : 'Open demo room'}
          </button>
        </div>
        <ErrorNote error={createDemo.error} />
      </Card>
    </>
  )
}
