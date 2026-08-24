import type { ReactNode } from 'react'
import type { Meta } from '../api/client'

export function Card({ title, children, actions }: { title?: string; children: ReactNode; actions?: ReactNode }) {
  return (
    <section className="card">
      {(title || actions) && (
        <header className="card-header">
          {title && <h2>{title}</h2>}
          {actions}
        </header>
      )}
      {children}
    </section>
  )
}

export function StatTile({ label, value, hint }: { label: string; value: ReactNode; hint?: string }) {
  return (
    <div className="stat-tile">
      <div className="stat-value">{value}</div>
      <div className="stat-label">{label}</div>
      {hint && <div className="stat-hint">{hint}</div>}
    </div>
  )
}

export function Meter({ label, value, max = 100 }: { label: string; value: number; max?: number }) {
  const pct = Math.max(0, Math.min(100, (value / max) * 100))
  return (
    <div className="meter" role="meter" aria-valuenow={value} aria-valuemin={0} aria-valuemax={max}
      aria-label={label}>
      <div className="meter-head"><span>{label}</span><span>{value}</span></div>
      <div className="meter-track"><div className="meter-fill" style={{ width: `${pct}%` }} /></div>
    </div>
  )
}

export function CacheBadge({ meta }: { meta?: Meta }) {
  if (!meta || meta.from_cache === undefined) return null
  return (
    <span className={`badge ${meta.stale ? 'badge-warn' : ''}`}>
      {meta.stale ? 'stale data (provider unreachable)' : meta.from_cache ? 'cached' : 'fresh'}
    </span>
  )
}

export function BarChart({ data, height = 120, formatValue }: {
  data: { label: string; value: number }[]
  height?: number
  formatValue?: (v: number) => string
}) {
  if (!data.length) return <p className="muted">No data yet.</p>
  const max = Math.max(...data.map((d) => d.value), 1)
  return (
    <div className="bar-chart" style={{ height }}>
      {data.map((d) => (
        <div key={d.label} className="bar-col" title={`${d.label}: ${formatValue ? formatValue(d.value) : d.value}`}>
          <div className="bar" style={{ height: `${(d.value / max) * 100}%` }} />
          <div className="bar-label">{d.label.slice(-5)}</div>
        </div>
      ))}
    </div>
  )
}

export function ErrorNote({ error }: { error: unknown }) {
  if (!error) return null
  const message = error instanceof Error ? error.message : String(error)
  return <p className="error-note" role="alert">{message}</p>
}

export function Spinner({ label = 'Loading…' }: { label?: string }) {
  return <p className="muted" aria-busy="true">{label}</p>
}

export const CONNECTOR_LABELS: Record<string, string> = {
  google_calendar: 'Google Calendar',
  google_drive: 'Google Drive',
  google_docs: 'Google Docs',
  google_sheets: 'Google Sheets',
  google_slides: 'Google Slides',
  gmail: 'Gmail',
  google_meet: 'Google Meet',
  github: 'GitHub',
}

export const EVIDENCE_LABELS: Record<string, string> = {
  file_created: 'New file created',
  file_modified: 'File modified',
  document_content_changed: 'Doc content changed',
  sheet_values_changed: 'Sheet values changed',
  presentation_content_changed: 'Slides changed',
  email_sent: 'Email sent',
  calendar_event_completed: 'Calendar block completed',
  github_commit_created: 'Commit created',
  github_pull_request_opened: 'PR opened',
  github_pull_request_merged: 'PR merged',
  github_checks_passed: 'Checks passed',
  meet_attended: 'Meet attended',
  manual_confirmation: 'You confirm it',
}
