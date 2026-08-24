import { Link, useParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { api } from '../api/client'
import type { BossEncounter } from '../api/types'
import { Card, ErrorNote, Spinner } from '../components/ui'

export function BossScene() {
  const { partyId, encounterId } = useParams()
  const boss = useQuery({
    queryKey: ['boss', encounterId],
    queryFn: () => api<BossEncounter>(`/parties/${partyId}/boss-encounters/${encounterId}`),
    refetchInterval: (q) => (q.state.data?.data.state === 'active' ? 5000 : false),
  })

  if (boss.isPending) return <Spinner />
  if (boss.isError) return <ErrorNote error={boss.error} />
  const b = boss.data.data
  const pct = (b.hp_current / b.hp_max) * 100

  return (
    <div style={{ maxWidth: 640, margin: '0 auto', textAlign: 'center' }}>
      <h1>{b.theme.name ?? 'The Boss'}</h1>
      <p className="muted">{b.theme.narration}</p>
      <div style={{ fontSize: '5rem' }} aria-hidden="true">
        {b.state === 'defeated' ? '💥' : pct > 66 ? '🐲' : pct > 33 ? '😤' : '🥵'}
      </div>
      <div className="boss-hp" role="meter" aria-valuenow={b.hp_current} aria-valuemin={0}
        aria-valuemax={b.hp_max} aria-label="Boss HP">
        <div className="boss-hp-fill" style={{ width: `${pct}%` }} />
      </div>
      <p>{b.hp_current} / {b.hp_max} HP</p>
      {b.state === 'defeated' && (
        <Card>
          <h2>🎉 Defeated!</h2>
          <p>{b.theme.defeat_line ?? 'The party stands victorious.'}</p>
          <p className="small muted">Everyone who contributed earned a cosmetic crown, a trophy
            prop, and a journal memory.</p>
        </Card>
      )}
      {b.state === 'expired' && <p className="muted">This encounter expired peacefully. No
        punishment — bosses are patient.</p>}
      <Card title="Damage dealt">
        {b.contributions.length === 0 && <p className="muted">No strikes yet — finish a verified
          focus session to attack.</p>}
        {b.contributions.map((c) => (
          <div key={c.profile_id} className="list-item">
            <span>{c.display_name}</span><span>{c.damage} dmg · {c.sessions} session(s)</span>
          </div>
        ))}
      </Card>
      <Link to={`/party/${partyId}`}><button>Back to party</button></Link>
    </div>
  )
}
