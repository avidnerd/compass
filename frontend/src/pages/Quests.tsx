import { Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { api } from '../api/client'
import type { Quest } from '../api/types'
import { Card, ErrorNote, Spinner } from '../components/ui'

const STATE_BADGE: Record<string, string> = {
  draft: 'draft', planning: 'planning…', active: 'active', completed: 'completed', archived: 'archived',
}

export function Quests() {
  const quests = useQuery({
    queryKey: ['quests'],
    queryFn: () => api<{ items: Quest[] }>('/quests'),
  })

  return (
    <>
      <div className="row spread">
        <h1>Quests</h1>
        <Link to="/quests/new"><button className="primary">New quest</button></Link>
      </div>
      {quests.isPending && <Spinner />}
      <ErrorNote error={quests.error} />
      {quests.data?.data.items.length === 0 && (
        <Card><p className="muted">No quests yet. Your first goal becomes a quest with
          verifiable subgoals.</p></Card>
      )}
      {quests.data?.data.items.map((q) => (
        <Card key={q.id}>
          <div className="row spread">
            <div>
              <Link to={`/quests/${q.id}`}><strong>{q.goal}</strong></Link>
              <p className="small muted" style={{ margin: '0.2rem 0 0' }}>
                <span className="badge">{STATE_BADGE[q.state]}</span>{' '}
                {q.subgoal_done ?? 0}/{q.subgoal_total ?? 0} steps
                {q.target_date ? ` · target ${q.target_date}` : ''}
              </p>
            </div>
            <Link to={`/quests/${q.id}`}><button>Open</button></Link>
          </div>
        </Card>
      ))}
    </>
  )
}
