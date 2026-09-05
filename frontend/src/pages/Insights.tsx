import { NavLink, Route, Routes } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { api, type Envelope } from '../api/client'
import { BarChart, Card, CacheBadge, ErrorNote, Spinner, StatTile } from '../components/ui'

const TABS = [
  { to: '', label: 'Baseline' },
  { to: 'calendar', label: 'Calendar' },
  { to: 'documents', label: 'Documents' },
  { to: 'email', label: 'Email' },
  { to: 'meet', label: 'Meet' },
  { to: 'github', label: 'GitHub' },
  { to: 'collaboration', label: 'Collaboration' },
  { to: 'trends', label: 'Trends' },
  { to: 'system', label: 'System' },
]

function useInsight<T>(key: string, path: string) {
  return useQuery({
    queryKey: ['analytics', key],
    queryFn: () => api<T>(path),
    staleTime: 60_000,
    retry: false,
  })
}

function toBars(record: Record<string, number> | undefined) {
  return Object.entries(record ?? {}).map(([label, value]) => ({ label, value }))
}

function Panel<T>({ query, children }: {
  query: { isPending: boolean; isError: boolean; error: unknown; data?: Envelope<T> }
  children: (data: T, meta?: Envelope<T>['meta']) => React.ReactNode
}) {
  if (query.isPending) return <Spinner />
  if (query.isError) return (
    <Card>
      <ErrorNote error={query.error} />
      <p className="small muted">This usually means the connector isn't connected yet, or the
        Apps Script bridge is unreachable. Stale cached data is served automatically when
        available.</p>
    </Card>
  )
  return <>{children(query.data!.data, query.data!.meta)}</>
}

interface Baseline {
  eligible_sessions: number
  average_focus_score: number | null
  best_focus_score: number | null
  recent_scores: number[]
  baseline_ready: boolean
}

function BaselineTab() {
  const q = useInsight<Baseline>('baseline', '/analytics/baseline')
  const sessions = useInsight<{ id: string; state: string; focus_score: number | null; started_at: string; verification_result: string | null; demo: number }[]>('sessions', '/analytics/sessions')
  return (
    <Panel query={q}>
      {(b) => (
        <>
          <Card title="Personal baseline">
            <p className="small muted">Compass compares you only to your own recent sessions,
              never to other people or other professions.</p>
            <div className="grid-tiles">
              <StatTile label="Eligible sessions" value={b.eligible_sessions} />
              <StatTile label="Average focus" value={b.average_focus_score ?? '—'} />
              <StatTile label="Personal best" value={b.best_focus_score ?? '—'} />
              <StatTile label="Baseline ready" value={b.baseline_ready ? 'yes' : `${b.eligible_sessions}/5`} />
            </div>
            <BarChart data={b.recent_scores.map((v, i) => ({ label: `#${i + 1}`, value: v })).reverse()} />
          </Card>
          <Card title="Session history">
            <Panel query={sessions}>
              {(items) => (
                <table className="simple">
                  <thead><tr><th>When</th><th>State</th><th>Score</th><th>Verification</th></tr></thead>
                  <tbody>
                    {items.slice(0, 20).map((s) => (
                      <tr key={s.id}>
                        <td>{new Date(s.started_at).toLocaleString()}{s.demo ? ' (demo)' : ''}</td>
                        <td>{s.state}</td><td>{s.focus_score ?? '—'}</td>
                        <td>{s.verification_result ?? '—'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </Panel>
          </Card>
        </>
      )}
    </Panel>
  )
}

function CalendarTab() {
  const q = useInsight<Record<string, unknown>>('calendar', '/analytics/calendar')
  return (
    <Panel query={q}>
      {(d, meta) => (
        <Card title="Calendar load" actions={<CacheBadge meta={meta} />}>
          <div className="grid-tiles">
            <StatTile label="Total meeting hours" value={String(d.total_meeting_hours ?? 0)} />
            <StatTile label="Work-hours meetings" value={String(d.work_hours_meeting_hours ?? 0)} />
            <StatTile label="After-hours meetings" value={String(d.after_hours_meeting_hours ?? 0)} />
          </div>
          <h3>Meeting hours per day</h3>
          <BarChart data={toBars(d.meeting_hours_per_day as Record<string, number>)} />
          <h3>Free focus hours per day</h3>
          <BarChart data={toBars(d.free_focus_hours_per_day as Record<string, number>)} />
        </Card>
      )}
    </Panel>
  )
}

function DocumentsTab() {
  const q = useInsight<Record<string, unknown>>('documents', '/analytics/documents')
  return (
    <Panel query={q}>
      {(d, meta) => (
        <Card title="Workspace documents" actions={<CacheBadge meta={meta} />}>
          <div className="grid-tiles">
            <StatTile label="Total documents" value={String(d.total_documents ?? 0)} />
            <StatTile label="Recently active" value={(d.recently_active as unknown[])?.length ?? 0} />
            <StatTile label="Stale (90d+)" value={(d.stale_documents as unknown[])?.length ?? 0} />
          </div>
          <h3>Most recently active</h3>
          <ul className="small">
            {((d.most_active_documents as { id: string; name: string; modified_time: string }[]) ?? [])
              .slice(0, 8).map((f) => (
                <li key={f.id}>{f.name}: {f.modified_time ? new Date(f.modified_time).toLocaleDateString() : ''}</li>
              ))}
          </ul>
        </Card>
      )}
    </Panel>
  )
}

function EmailTab() {
  const q = useInsight<Record<string, unknown>>('email', '/analytics/email')
  return (
    <Panel query={q}>
      {(d, meta) => (
        <Card title="Email activity" actions={<CacheBadge meta={meta} />}>
          <div className="grid-tiles">
            <StatTile label="Unread" value={String(d.unread_count ?? 0)} />
          </div>
          <h3>Messages per week (directional)</h3>
          <BarChart data={toBars(d.messages_per_week as Record<string, number>)} />
          <h3>Top senders</h3>
          <ul className="small">
            {((d.top_senders as { sender: string; count: number }[]) ?? []).map((s) => (
              <li key={s.sender}>{s.sender}: {s.count}</li>
            ))}
          </ul>
        </Card>
      )}
    </Panel>
  )
}

function MeetTab() {
  const q = useInsight<Record<string, unknown>>('meet', '/analytics/meet')
  return (
    <Panel query={q}>
      {(d, meta) => (
        <Card title="Google Meet" actions={<CacheBadge meta={meta} />}>
          <div className="grid-tiles">
            <StatTile label="Total calls" value={String(d.total_meetings ?? 0)} />
            <StatTile label="Hours" value={String(d.total_meeting_hours ?? 0)} />
            <StatTile label="Avg minutes" value={String(d.average_meeting_minutes ?? 0)} />
            <StatTile label="Longest (min)" value={String(d.longest_meeting_minutes ?? 0)} />
          </div>
          <h3>Meetings per week</h3>
          <BarChart data={toBars(d.meetings_per_week as Record<string, number>)} />
        </Card>
      )}
    </Panel>
  )
}

function GitHubTab() {
  const q = useInsight<Record<string, unknown>>('github', '/analytics/github')
  return (
    <Panel query={q}>
      {(d, meta) => (
        <Card title="GitHub" actions={<CacheBadge meta={meta} />}>
          <div className="grid-tiles">
            <StatTile label="Commits" value={String(d.total_commits ?? 0)} />
            <StatTile label="Open PRs" value={String(d.open_pr_count ?? 0)} />
          </div>
          <h3>Commits per week</h3>
          <BarChart data={toBars(d.commits_per_week as Record<string, number>)} />
          <h3>Top repos</h3>
          <ul className="small">
            {((d.top_repos_by_commits as { repo: string; commits: number }[]) ?? []).map((r) => (
              <li key={r.repo}>{r.repo}: {r.commits}</li>
            ))}
          </ul>
        </Card>
      )}
    </Panel>
  )
}

function CollaborationTab() {
  const q = useInsight<Record<string, unknown>>('collaboration', '/analytics/collaboration')
  return (
    <Panel query={q}>
      {(d, meta) => (
        <Card title="Collaboration" actions={<CacheBadge meta={meta} />}>
          <div className="grid-tiles">
            <StatTile label="Solo blocks" value={String(d.solo_meetings ?? 0)} />
            <StatTile label="Group meetings" value={String(d.group_meetings ?? 0)} />
            <StatTile label="Shared docs" value={String(d.shared_document_count ?? 0)} />
          </div>
          <h3>Top collaborators</h3>
          <ul className="small">
            {((d.top_collaborators as { email: string; meetings: number }[]) ?? []).map((c) => (
              <li key={c.email}>{c.email}: {c.meetings} meetings</li>
            ))}
          </ul>
        </Card>
      )}
    </Panel>
  )
}

function TrendsTab() {
  const q = useInsight<{ weeks: { week: string; meeting_hours: number; doc_edits: number }[] }>('timeline', '/analytics/timeline')
  return (
    <Panel query={q}>
      {(d, meta) => (
        <Card title="Week-over-week trends" actions={<CacheBadge meta={meta} />}>
          <h3>Meeting hours</h3>
          <BarChart data={d.weeks.map((w) => ({ label: w.week, value: w.meeting_hours }))} />
          <h3>Doc edits</h3>
          <BarChart data={d.weeks.map((w) => ({ label: w.week, value: w.doc_edits }))} />
        </Card>
      )}
    </Panel>
  )
}

interface CacheStats {
  hits: number; misses: number; stale_serves: number; avoided_calls: number
  tools: { connector: string; rows: number; hits: number }[]
}

function SystemTab() {
  const cacheQ = useInsight<CacheStats>('cache', '/cache/stats')
  const freshQ = useInsight<{ connector: string; status: string; last_fetched_at: string | null; cached_rows: number; generation: number }[]>('freshness', '/telemetry/freshness')
  const verifQ = useInsight<{ id: string; result: string; confidence: number; model_id: string | null; created_at: string; subgoal_title: string | null }[]>('verifications', '/analytics/verifications')
  return (
    <>
      <Panel query={cacheQ}>
        {(c) => (
          <Card title="Cache savings">
            <div className="grid-tiles">
              <StatTile label="Cache hits" value={c.hits} />
              <StatTile label="Misses" value={c.misses} />
              <StatTile label="Stale serves" value={c.stale_serves} />
              <StatTile label="Provider calls avoided" value={c.avoided_calls} />
            </div>
          </Card>
        )}
      </Panel>
      <Panel query={freshQ}>
        {(rows) => (
          <Card title="Provider freshness">
            <table className="simple">
              <thead><tr><th>Connector</th><th>Status</th><th>Last fetch</th><th>Rows</th><th>Gen</th></tr></thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.connector}>
                    <td>{r.connector}</td><td>{r.status}</td>
                    <td>{r.last_fetched_at ? new Date(r.last_fetched_at).toLocaleTimeString() : '—'}</td>
                    <td>{r.cached_rows}</td><td>{r.generation}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Card>
        )}
      </Panel>
      <Panel query={verifQ}>
        {(rows) => (
          <Card title="Verification history">
            <table className="simple">
              <thead><tr><th>When</th><th>Subgoal</th><th>Result</th><th>Confidence</th><th>Model</th></tr></thead>
              <tbody>
                {rows.slice(0, 15).map((v) => (
                  <tr key={v.id}>
                    <td>{new Date(v.created_at).toLocaleString()}</td>
                    <td>{v.subgoal_title ?? '—'}</td><td>{v.result}</td>
                    <td>{Math.round(v.confidence * 100)}%</td><td>{v.model_id ?? 'none'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Card>
        )}
      </Panel>
    </>
  )
}

export function Insights() {
  return (
    <>
      <div className="page-head">
        <h1>Insights</h1>
        <nav className="row" aria-label="Insights sections">
          {TABS.map((t) => (
            <NavLink key={t.to} to={t.to} end={t.to === ''}
              className={({ isActive }) => isActive ? 'badge' : 'small'}>
              {t.label}
            </NavLink>
          ))}
        </nav>
      </div>
      <Routes>
        <Route index element={<BaselineTab />} />
        <Route path="calendar" element={<CalendarTab />} />
        <Route path="documents" element={<DocumentsTab />} />
        <Route path="email" element={<EmailTab />} />
        <Route path="meet" element={<MeetTab />} />
        <Route path="github" element={<GitHubTab />} />
        <Route path="collaboration" element={<CollaborationTab />} />
        <Route path="trends" element={<TrendsTab />} />
        <Route path="system" element={<SystemTab />} />
      </Routes>
    </>
  )
}
