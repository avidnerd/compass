import { useNavigate, useParams } from 'react-router-dom'
import { useMutation, useQuery } from '@tanstack/react-query'
import { api } from '../api/client'
import type { Party } from '../api/types'
import { Card, ErrorNote, PageTitle, Spinner } from '../components/ui'
import { PixelIcon } from '../components/PixelIcon'

/** A focus room shares presence and nothing else: who is here, who is working
 *  right now, and a way to say "I see you". No goals, no filenames, no evidence
 *  and no score — see PRODUCT.md, "Privacy survives multiplayer". */

const REACTIONS = [
  { id: 'cheer', glyph: 'megaphone', label: 'Cheer' },
  { id: 'heart', glyph: 'heart', label: 'Nice work' },
  { id: 'spark', glyph: 'sparkle', label: 'Good luck' },
  { id: 'flex', glyph: 'bolt', label: 'Keep going' },
  { id: 'tea', glyph: 'kettle', label: 'Take a break' },
]

const PRESENCE: Record<string, string> = {
  in_focus: 'Focusing now', online: 'Here', offline: 'Away',
}

export function PartyDetail() {
  const { partyId } = useParams()
  const navigate = useNavigate()

  const party = useQuery({
    queryKey: ['party', partyId],
    queryFn: () => api<Party>(`/parties/${partyId}`),
    refetchInterval: 15000,
  })
  const react = useMutation({
    mutationFn: (id: string) => api(`/parties/${partyId}/emotes`, { body: { emote: id } }),
  })
  const leave = useMutation({
    mutationFn: () => api(`/parties/${partyId}:leave`, { body: {} }),
    onSuccess: () => navigate('/party'),
  })

  if (party.isPending) return <Spinner />
  if (party.isError) return <ErrorNote error={party.error} />
  const p = party.data.data
  const focusing = p.members.filter((m) => m.status === 'in_focus').length

  return (
    <>
      <PageTitle>{p.name}</PageTitle>
      <Card
        title={p.name}
        actions={<span className="badge">Invite code {p.code}</span>}
        status={[`${p.members.length} here`, `${focusing} focusing`]}
      >
        <p>Everyone in this room can see that you are working and for how long. Nobody
          can see what you are working on. Not the goal, not the file, not the evidence.</p>

        <div className="log">
          {p.members.map((m) => (
            <div key={m.profile_id} className="log-row">
              <span className={`presence presence-${m.status ?? 'online'}`} aria-hidden="true"><span /></span>
              <span className="log-what">
                <strong>{m.display_name}</strong>
                <small>{PRESENCE[m.status ?? 'online'] ?? 'Here'}
                  {m.profile_id === p.owner_profile_id ? ' · host' : ''}</small>
              </span>
              {m.is_simulated && <span className="badge">demo</span>}
            </div>
          ))}
        </div>
      </Card>

      <Card title="Say something" status={['5 presets · no free text']}>
        <p className="small">Preset reactions only. Nothing typed, nothing to moderate.</p>
        <div className="row">
          {REACTIONS.map((r) => (
            <button key={r.id} onClick={() => react.mutate(r.id)} disabled={react.isPending}>
              <PixelIcon name={r.glyph} /> {r.label}
            </button>
          ))}
        </div>
        <ErrorNote error={react.error} />
      </Card>

      <button onClick={() => leave.mutate()} disabled={leave.isPending}>Leave room</button>
      <ErrorNote error={leave.error} />
    </>
  )
}
