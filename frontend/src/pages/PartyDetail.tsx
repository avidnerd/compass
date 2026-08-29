import { Link, useNavigate, useParams } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '../api/client'
import type { Party } from '../api/types'
import { Card, ErrorNote, Spinner } from '../components/ui'
import { PixelIcon } from '../components/PixelIcon'

const EMOTES = [
  { id: 'cheer', glyph: 'megaphone' }, { id: 'heart', glyph: 'heart' }, { id: 'spark', glyph: 'sparkle' },
  { id: 'flex', glyph: 'bolt' }, { id: 'tea', glyph: 'kettle' }, { id: 'confetti', glyph: 'sparkle' },
]

export function PartyDetail() {
  const { partyId } = useParams()
  const navigate = useNavigate()
  const queryClient = useQueryClient()

  const party = useQuery({
    queryKey: ['party', partyId],
    queryFn: () => api<Party>(`/parties/${partyId}`),
  })
  const emote = useMutation({
    mutationFn: (id: string) => api(`/parties/${partyId}/emotes`, { body: { emote: id } }),
  })
  const startBoss = useMutation({
    mutationFn: (difficulty: string) =>
      api<Party>(`/parties/${partyId}/boss-encounters`, { body: { difficulty } }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['party', partyId] }),
  })
  const leave = useMutation({
    mutationFn: () => api(`/parties/${partyId}:leave`, { body: {} }),
    onSuccess: () => navigate('/party'),
  })

  if (party.isPending) return <Spinner />
  if (party.isError) return <ErrorNote error={party.error} />
  const p = party.data.data
  const boss = p.active_boss

  return (
    <>
      <div className="row spread">
        <h1>{p.name}</h1>
        <span className="badge">invite code: {p.code}</span>
      </div>

      {boss && boss.state === 'active' ? (
        <Card title={`${boss.theme.name ?? 'A mysterious boss'}`}>
          <p className="muted">{boss.theme.narration}</p>
          <div className="boss-hp" role="meter" aria-valuenow={boss.hp_current}
            aria-valuemin={0} aria-valuemax={boss.hp_max} aria-label="Boss HP">
            <div className="boss-hp-fill" style={{ width: `${(boss.hp_current / boss.hp_max) * 100}%` }} />
          </div>
          <p className="small muted">{boss.hp_current}/{boss.hp_max} HP · {boss.difficulty} ·
            expires {new Date(boss.expires_at).toLocaleString()}</p>
          <p className="small">Damage = 20 + 60% focus score + level bonus. Finish verified focus
            sessions to strike!</p>
          <Link to={`/party/${p.id}/boss/${boss.id}`}><button className="primary">Open boss scene</button></Link>
        </Card>
      ) : (
        <Card title="Summon a boss">
          {boss?.state === 'defeated' && <p>Last boss defeated. Ready for another?</p>}
          {boss?.state === 'expired' && <p className="muted">The last boss wandered off (no harm
            done). Summon a fresh one?</p>}
          <div className="row">
            {['easy', 'standard', 'epic'].map((d) => (
              <button key={d} onClick={() => startBoss.mutate(d)} disabled={startBoss.isPending}>
                <PixelIcon name={d === 'easy' ? 'leaf' : d === 'standard' ? 'fire' : 'skull'} /> {d}
              </button>
            ))}
          </div>
          <ErrorNote error={startBoss.error} />
        </Card>
      )}

      <div className="grid-2">
        <Card title="Members">
          {p.members.map((m) => (
            <div key={m.profile_id} className="list-item">
              <span className="room-player">
                <span className="mini-avatar" aria-hidden="true"><PixelIcon name="compass" size={24} /></span>
                <span><strong>{m.display_name}</strong>{m.profile_id === p.owner_profile_id ? <> <PixelIcon name="crown" label="Party owner" /></> : null}
                  {m.title && <small>{m.title}</small>}</span>
              </span>
              {m.is_simulated && <span className="badge">co-op teammate</span>}
            </div>
          ))}
        </Card>
        <Card title="Emotes">
          <p className="small muted">Preset emotes only — cozy, no moderation needed.</p>
          <div className="row">
            {EMOTES.map((e) => (
              <button key={e.id} aria-label={`Send ${e.id} emote`}
                onClick={() => emote.mutate(e.id)}>{e.glyph}</button>
            ))}
          </div>
        </Card>
      </div>

      {boss && boss.contributions.length > 0 && (
        <Card title="Contributions">
          <table className="simple">
            <thead><tr><th>Member</th><th>Sessions</th><th>Damage</th></tr></thead>
            <tbody>
              {boss.contributions.map((c) => (
                <tr key={c.profile_id}><td>{c.display_name}</td><td>{c.sessions}</td><td>{c.damage}</td></tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}

      <button onClick={() => leave.mutate()}>Leave party</button>
    </>
  )
}
