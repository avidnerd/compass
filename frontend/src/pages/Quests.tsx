import { Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { api } from '../api/client'
import type { Quest } from '../api/types'
import { Card, ErrorNote, PageTitle, Spinner, StateBox } from '../components/ui'
import { PixelIcon } from '../components/PixelIcon'

const STATE_BADGE: Record<string, string> = {
  draft: 'draft', planning: 'planning…', active: 'active', completed: 'completed', archived: 'archived',
}

export function Quests() {
  const quests = useQuery({
    queryKey: ['quests'],
    queryFn: () => api<{ items: Quest[] }>('/quests'),
  })

  const items = quests.data?.data.items ?? []
  const active = items.filter((q) => q.state === 'active').length

  return (
    <>
    <PageTitle>Quests</PageTitle>
    <Card
      title="Quests"
      actions={<Link to="/quests/new"><button className="primary"><PixelIcon name="plus" /> New quest</button></Link>}
      status={[`${items.length} ${items.length === 1 ? 'quest' : 'quests'}`, `${active} active`]}
    >
      {quests.isPending && <Spinner />}
      <ErrorNote error={quests.error} />
      {items.length === 0 && !quests.isPending && (
        <p>No quests yet. Your first goal becomes a quest with subgoals Compass can verify.</p>
      )}
      {items.map((q) => {
        const done = q.subgoal_done ?? 0
        const total = q.subgoal_total ?? 0
        return (
          <div key={q.id} className="list-item">
            <span style={{ minWidth: 0, flex: 1 }}>
              <Link to={`/quests/${q.id}`}><strong>{q.goal}</strong></Link>
              <span className="row small" style={{ gap: 6, marginTop: 4 }}>
                <span className="badge">{STATE_BADGE[q.state]}</span>
                <span className="row" style={{ gap: 3 }}>
                  {Array.from({ length: total }, (_, i) => (
                    <StateBox key={i} on={i < done}
                      label={i < done ? `Step ${i + 1} verified` : `Step ${i + 1} not yet verified`} />
                  ))}
                </span>
                <span>{done}/{total} steps{q.target_date ? ` · target ${q.target_date}` : ''}</span>
              </span>
            </span>
            <Link to={`/quests/${q.id}`}><button>Open</button></Link>
          </div>
        )
      })}
    </Card>
    </>
  )
}
