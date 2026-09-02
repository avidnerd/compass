import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '../api/client'
import type { CanvasOverview } from '../api/types'
import { Card, ErrorNote, PageTitle, Spinner, StateBox } from '../components/ui'
import { PixelIcon } from '../components/PixelIcon'
import { CanvasSetup } from '../components/CanvasSetup'

function dueLabel(iso: string, allDay: boolean) {
  const due = new Date(iso)
  const days = Math.ceil((due.getTime() - Date.now()) / 86_400_000)
  const date = due.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
  const time = allDay ? '' : ` ${due.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' })}`
  if (days < 0) return `${date} · overdue`
  if (days === 0) return `${date}${time} · today`
  if (days === 1) return `${date}${time} · tomorrow`
  return `${date}${time} · ${days} days`
}

export function CanvasPage() {
  const queryClient = useQueryClient()
  const [selected, setSelected] = useState<Set<string>>(new Set())

  const overview = useQuery({
    queryKey: ['canvas'],
    queryFn: () => api<CanvasOverview>('/canvas'),
    retry: false,
  })
  const refresh = useMutation({
    mutationFn: () => api<CanvasOverview>('/canvas?refresh=true'),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['canvas'] }),
  })
  const runImport = useMutation({
    mutationFn: () => api('/canvas/quests:import', {
      body: { source_keys: [...selected], plan: true },
    }),
    onSuccess: () => {
      setSelected(new Set())
      queryClient.invalidateQueries({ queryKey: ['canvas'] })
      queryClient.invalidateQueries({ queryKey: ['quests'] })
    },
  })

  const toggle = (uid: string) => setSelected((cur) => {
    const next = new Set(cur)
    next.has(uid) ? next.delete(uid) : next.add(uid)
    return next
  })

  if (overview.isPending) return <Spinner label="Reading your feeds…" />

  const data = overview.data?.data
  const linked = data?.link.status === 'linked'
  const items = data?.assignments ?? []
  const importable = items.filter((a) => !a.imported_quest_id)

  return (
    <>
      <PageTitle>Deadlines</PageTitle>
      <CanvasSetup />

      {linked && (
        <Card
          title="Upcoming deadlines"
          actions={
            <button onClick={() => refresh.mutate()} disabled={refresh.isPending}>
              <PixelIcon name="refresh" /> {refresh.isPending ? 'Reading…' : 'Re-read feeds'}
            </button>
          }
          status={[`${items.length} in the next 60 days`,
            `${(data?.link.feeds?.length ?? 0)} ${(data?.link.feeds?.length ?? 0) === 1 ? 'feed' : 'feeds'}`,
            `${selected.size} selected`]}
        >
          {data?.error && (
            <ErrorNote error={new Error(`${data.error.message} (${data.error.code})`)} />
          )}
          {/* One dead feed does not blank out the rest — say which one broke. */}
          {(data?.feed_errors ?? []).map((e) => (
            <ErrorNote key={e.feed_id ?? e.code}
              error={new Error(`${e.label ?? 'A feed'} could not be read: ${e.message}`)} />
          ))}
          {items.length === 0 && !data?.error && (
            <p>Nothing due in the next 60 days. A feed only carries what was actually put in
              it, so a quiet list can also mean a deadline lives somewhere Compass cannot see.</p>
          )}

          {items.length > 0 && (
            <div className="log">
              {items.map((a) => (
                <div key={a.uid} className="log-row">
                  {a.imported_quest_id ? (
                    <StateBox on label="Already a quest" />
                  ) : (
                    <input type="checkbox" checked={selected.has(a.uid)}
                      onChange={() => toggle(a.uid)}
                      aria-label={`Import ${a.title}`} />
                  )}
                  <span className="log-what">
                    <strong>{a.title}</strong>
                    <small>{a.course ?? a.feed_label ?? 'No course'}
                      {(data?.link.feeds?.length ?? 0) > 1 && a.course ? ` · ${a.feed_label}` : ''}
                      {a.imported_quest_id ? ' · imported' : ''}</small>
                  </span>
                  <span className="log-stamp">{dueLabel(a.due_at, a.all_day)}</span>
                </div>
              ))}
            </div>
          )}

          {importable.length > 0 && (
            <div className="coop-launcher" style={{ marginTop: 12 }}>
              <span>Each becomes a quest with its due date. Steps are yours to confirm
                unless Drive or GitHub is connected.</span>
              <button className="primary" onClick={() => runImport.mutate()}
                disabled={!selected.size || runImport.isPending}>
                {runImport.isPending ? 'Importing…' : `Import ${selected.size || ''}`}
              </button>
            </div>
          )}
          <ErrorNote error={runImport.error} />
        </Card>
      )}

      {linked && (
        <Card title="What a feed can and cannot do" status={['Due dates only']}>
          <p className="small">
            A calendar feed tells Compass <strong>when</strong> something is due. It cannot tell
            Compass whether you did it — no feed carries submission status or grades. That is a
            limit of the format, not a setting.
          </p>
          <p className="small">
            Canvas also only carries what your instructors entered <em>in Canvas</em>. Courses
            graded through Gradescope, Pearson or LabFlow often sync a due date across, but
            extensions, late deadlines and section-specific dates never do. If a deadline is
            missing here, it is missing from Canvas — add that tool&apos;s own calendar under
            Deadline feeds, or paste the assignment into <Link to="/quests/new">a new quest</Link>.
          </p>
          <p className="small">
            To have a step close itself, connect Google or GitHub on{' '}
            <Link to="/settings/connections">Connections</Link>. Then editing the doc or pushing
            the commit is what marks it done.
          </p>
        </Card>
      )}
    </>
  )
}
