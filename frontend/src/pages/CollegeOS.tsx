import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '../api/client'
import type { CollegeImportResult, CollegeLink, CollegeOverview } from '../api/types'
import { Card, ErrorNote, EVIDENCE_LABELS, Meter, Spinner, StatTile } from '../components/ui'
import { PixelIcon } from '../components/PixelIcon'

const TAB_ORDER = ['THIS WEEK', 'SEMESTER GOALS', 'OPPORTUNITIES']

export function CollegeOS() {
  const queryClient = useQueryClient()
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [importMsg, setImportMsg] = useState<string | null>(null)

  const overview = useQuery({
    queryKey: ['college'],
    queryFn: () => api<CollegeOverview>('/college'),
    retry: false,
  })

  const detect = useMutation({
    mutationFn: () => api<CollegeLink>('/college/detect', { body: {} }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['college'] }),
  })

  const refresh = useMutation({
    mutationFn: () => api<CollegeOverview>('/college?refresh=true'),
    onSuccess: (resp) => queryClient.setQueryData(['college'], resp),
  })

  const runImport = useMutation({
    mutationFn: (sourceKeys: string[]) =>
      api<CollegeImportResult>('/college/quests:import', { body: { source_keys: sourceKeys } }),
    onSuccess: (resp) => {
      const { created, skipped } = resp.data
      setImportMsg(
        `Imported ${created.length} row${created.length === 1 ? '' : 's'} as quests` +
        (skipped.length ? ` · ${skipped.length} already imported` : '') +
        '. Review the generated steps before activating.')
      setSelected(new Set())
      queryClient.invalidateQueries({ queryKey: ['college'] })
      queryClient.invalidateQueries({ queryKey: ['quests'] })
    },
  })

  const unlink = useMutation({
    mutationFn: () => api<{ unlinked: boolean }>('/college/link', { method: 'DELETE' }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['college'] }),
  })

  const toggle = (key: string) => {
    setSelected((prev) => {
      const next = new Set(prev)
      if (next.has(key)) next.delete(key)
      else next.add(key)
      return next
    })
  }

  if (overview.isPending) return <Spinner label="Looking for your College OS…" />
  if (overview.isError) {
    return (
      <Card title="College OS">
        <ErrorNote error={overview.error} />
        <button onClick={() => detect.mutate()} disabled={detect.isPending}>
          {detect.isPending ? 'Scanning Drive…' : 'Scan Drive for College OS'}
        </button>
      </Card>
    )
  }

  const data = overview.data.data
  const link = data.link
  const sections = data.dashboard?.sections ?? {}
  const thisWeek = sections['THIS WEEK']
  const opportunities = sections.OPPORTUNITIES ?? []
  const reviews = sections['WEEKLY REVIEWS']
  const timeLog = sections['TIME LOG']

  if (link.status !== 'linked') {
    return (
      <Card title="College OS">
        <p className="muted">{data.hint ?? 'No College OS detected in this Google account yet.'}</p>
        <p className="small muted">
          College OS is the Apps Script provisioner in <code>college-os/</code>. Running
          {' '}<code>setUp()</code> creates the COLLEGE Drive tree, the COLLEGE DASHBOARD
          spreadsheet, five calendars, six Tasks lists, and the Gmail label tree in your own
          account. Compass then reads that structure — read-only — and turns its goal rows
          into verifiable quests.
        </p>
        {link.status === 'partial' && (
          <p className="small">Found the <strong>{link.root_folder_name}</strong> Drive folder but
            no dashboard spreadsheet. Re-run <code>setUp()</code> with
            {' '}<code>CONFIG.run.dashboard = true</code>.</p>
        )}
        <div className="row">
          <button className="primary" onClick={() => detect.mutate()} disabled={detect.isPending}>
            {detect.isPending ? 'Scanning Drive…' : <><PixelIcon name="scan" /> Detect College OS</>}
          </button>
        </div>
        <ErrorNote error={detect.error} />
      </Card>
    )
  }

  const importable = data.importable.filter((d) => !d.imported_quest_id)
  const byTab = TAB_ORDER.map((tab) => ({ tab, rows: importable.filter((d) => d.tab === tab) }))
    .filter((group) => group.rows.length > 0)

  return (
    <div>
      <Card
        title="College OS"
        actions={
          <div className="row">
            <button onClick={() => refresh.mutate()} disabled={refresh.isPending}>
              {refresh.isPending ? 'Reading sheet…' : <><PixelIcon name="refresh" /> Re-read dashboard</>}
            </button>
            <button onClick={() => detect.mutate()} disabled={detect.isPending}>Re-detect</button>
          </div>
        }
      >
        <p className="muted" style={{ marginTop: 0 }}>
          Linked to <strong>{link.dashboard_name}</strong>
          {link.last_synced_at && ` · last read ${new Date(link.last_synced_at).toLocaleString()}`}
        </p>
        <div className="grid-tiles">
          <StatTile label="Big 3 this week" value={thisWeek?.big_three.length ?? 0} />
          <StatTile label="Open opportunities" value={opportunities.filter((o) => o.open).length} />
          <StatTile label="Imported as quests" value={data.imports.length} />
          <StatTile label="Project Home docs" value={link.project_home_count} />
        </div>
        {link.calendars.length > 0 && (
          <p className="small muted">
            Calendars: {link.calendars.map((c, i) => (
              <span key={c.name}>{i > 0 ? ' · ' : ''}<PixelIcon name={c.present ? 'check' : 'cross'} label={c.present ? 'Present' : 'Missing'} /> {c.name}</span>
            ))}
          </p>
        )}
        {data.dashboard && data.dashboard.missing_tabs.length > 0 && (
          <p className="small">
            <span className="badge badge-warn">Missing tabs</span>{' '}
            {data.dashboard.missing_tabs.join(', ')} — Compass read what it could.
          </p>
        )}
        <p className="small muted">
          Read-only: Compass can never create, edit, or delete anything in your Google account.
          Dashboard cell contents are held in memory for this page only and are never written to
          the local database.
        </p>
      </Card>

      {thisWeek && (
        <Card title="This week">
          {thisWeek.big_three.length > 0 ? (
            <ol>{thisWeek.big_three.map((b) => <li key={b.source_key}>{b.text}</li>)}</ol>
          ) : (
            <p className="muted">No Big 3 set yet — fill them in during the Sunday Weekly Reset.</p>
          )}
          {thisWeek.areas.length > 0 && (
            <table className="simple">
              <thead>
                <tr><th>Area</th><th>Goal</th><th>Definition of done</th><th>Evidence</th></tr>
              </thead>
              <tbody>
                {thisWeek.areas.map((a) => (
                  <tr key={a.source_key}>
                    <td>{a.area}</td>
                    <td>{a.goal}</td>
                    <td className="muted">{a.definition_of_done || '—'}</td>
                    <td className="small">{a.evidence || '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          {thisWeek.not_this_week.length > 0 && (
            <p className="small muted" style={{ marginBottom: 0 }}>
              <strong>Not this week:</strong> {thisWeek.not_this_week.join(' · ')}
            </p>
          )}
        </Card>
      )}

      <Card
        title="Import as quests"
        actions={
          <button className="primary" disabled={selected.size === 0 || runImport.isPending}
            onClick={() => runImport.mutate([...selected])}>
            {runImport.isPending ? 'Importing…' : <>Import {selected.size || ''} <PixelIcon name="right" /></>}
          </button>
        }
      >
        <p className="muted" style={{ marginTop: 0 }}>
          Each row becomes a Compass quest. The sheet's Definition of Done travels with it, and its
          Evidence column picks the evidence Compass will look for after a focus session.
        </p>
        {byTab.length === 0 ? (
          <p className="muted">Every importable row is already a quest. Nice.</p>
        ) : byTab.map((group) => (
          <div key={group.tab}>
            <h3>{group.tab}</h3>
            {group.rows.map((row) => (
              <label key={row.source_key} className="list-item" style={{ cursor: 'pointer' }}>
                <span style={{ display: 'flex', gap: '0.6rem', alignItems: 'flex-start' }}>
                  <input type="checkbox" checked={selected.has(row.source_key)}
                    onChange={() => toggle(row.source_key)} style={{ marginTop: '0.25rem' }} />
                  <span>
                    <strong>{row.title}</strong>
                    <br />
                    <span className="small muted">
                      {row.area} · done when: {row.acceptance_criterion}
                      {row.target_date ? ` · target ${row.target_date}` : ''}
                    </span>
                  </span>
                </span>
                <span className="small">
                  {row.evidence_specs.map((spec) => (
                    <span key={spec} className="badge">{EVIDENCE_LABELS[spec] ?? spec}</span>
                  ))}
                </span>
              </label>
            ))}
          </div>
        ))}
        {importMsg && <p className="small" role="status">{importMsg}</p>}
        <ErrorNote error={runImport.error} />
      </Card>

      {data.imports.length > 0 && (
        <Card title="Already imported">
          {data.imports.map((row) => (
            <div key={row.source_key} className="list-item">
              <span>
                <Link to={`/quests/${row.quest_id}`}>{row.title}</Link>
                <br /><span className="small muted">{row.tab} · {row.area}</span>
              </span>
              <span className="badge">{row.quest_state ?? 'quest'}</span>
            </div>
          ))}
        </Card>
      )}

      {opportunities.length > 0 && (
        <Card title="Opportunity pipeline">
          <table className="simple">
            <thead>
              <tr><th>Opportunity</th><th>Type</th><th>Deadline</th><th>Next action</th><th>Status</th></tr>
            </thead>
            <tbody>
              {opportunities.map((o) => (
                <tr key={o.source_key} style={{ opacity: o.open ? 1 : 0.55 }}>
                  <td>{o.title}</td>
                  <td className="small">{o.type || '—'}</td>
                  <td className="small">{o.deadline || '—'}</td>
                  <td className="small muted">{o.next_action || '—'}</td>
                  <td><span className="badge">{o.status}</span></td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="small muted" style={{ marginBottom: 0 }}>
            The weekly Duke scan writes DISCOVERED rows here. You still make every attend/pass call
            yourself.
          </p>
        </Card>
      )}

      <div className="grid-2">
        {reviews && reviews.total > 0 && (
          <Card title="Weekly reviews">
            <div className="grid-tiles">
              <StatTile label="Reviewed goals" value={reviews.total} />
              <StatTile label="Cited evidence"
                value={reviews.evidence_rate === null ? '—' : `${Math.round(reviews.evidence_rate * 100)}%`}
                hint="Evidence, not vibes" />
              <StatTile label="Usual failure" value={reviews.dominant_failure ?? '—'}
                hint="GOAL / PLAN / EXECUTION" />
            </div>
            {(['YES', 'PARTIAL', 'NO'] as const).map((key) => (
              <Meter key={key} label={key} value={reviews.outcomes[key] ?? 0} max={reviews.total} />
            ))}
            {reviews.dominant_failure && (
              <p className="small muted" style={{ marginBottom: 0 }}>
                Most misses were diagnosed as <strong>{reviews.dominant_failure}</strong> failures —
                {reviews.dominant_failure === 'GOAL' && ' the goal itself was wrong.'}
                {reviews.dominant_failure === 'PLAN' && ' the plan, not the effort.'}
                {reviews.dominant_failure === 'EXECUTION' && ' the plan was fine; the week got away.'}
              </p>
            )}
          </Card>
        )}

        {timeLog && timeLog.samples > 0 && (
          <Card title="Estimate calibration">
            <p className="muted" style={{ marginTop: 0 }}>
              How long things actually take versus what you predicted.
              {timeLog.overall_multiplier &&
                ` Overall you run ${timeLog.overall_multiplier}× your estimate.`}
            </p>
            <table className="simple">
              <thead><tr><th>Category</th><th>Multiplier</th><th>Samples</th></tr></thead>
              <tbody>
                {timeLog.multipliers.map((m) => (
                  <tr key={m.category}>
                    <td>{m.category}</td>
                    <td>{m.confident ? `${m.multiplier}×` : <span className="muted">{m.multiplier}×</span>}</td>
                    <td className="small muted">
                      {m.samples}{m.confident ? '' : ` (need ${timeLog.min_samples})`}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            <p className="small muted" style={{ marginBottom: 0 }}>
              Greyed rows have too few samples to trust yet.
            </p>
          </Card>
        )}
      </div>

      <Card title="Unlink">
        <p className="small muted">
          Forgets the dashboard link and the import ledger stored locally. Your quests, your sheet,
          and your Google account are untouched.
        </p>
        <button className="danger" onClick={() => unlink.mutate()} disabled={unlink.isPending}>
          Unlink College OS
        </button>
        <ErrorNote error={unlink.error} />
      </Card>
    </div>
  )
}
