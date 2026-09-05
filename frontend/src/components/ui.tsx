import type { ReactNode } from 'react'
import type { Meta } from '../api/client'
import { PixelIcon } from './PixelIcon'

/** Every panel in this system is a window: title bar, body, optional segmented
 *  status bar, hatched resize grip. `Card` keeps its name so screens that have
 *  not been individually art-directed still land inside the world. */
/** A window title bar is chrome, never the document heading. Screens whose
 *  structure is windows rather than a banner name themselves here instead, so
 *  every page has exactly one h1 and only one visible page-title treatment. */
export function PageTitle({ children }: { children: ReactNode }) {
  return <h1 className="sr-only">{children}</h1>
}

export function Card({ title, children, actions, status, grip = true }: {
  title?: string
  children: ReactNode
  actions?: ReactNode
  /** Segmented status-bar fields, rendered left to right; the last is pushed right. */
  status?: ReactNode[]
  grip?: boolean
}) {
  return (
    <section className="win">
      {(title || actions) && (
        <header className="win-title">
          {title && <h2>{title}</h2>}
          {actions && <span className="win-actions">{actions}</span>}
        </header>
      )}
      <div className="win-body">{children}</div>
      {status && status.length > 0 && (
        <div className="win-status">{status.map((field, i) => <span key={i}>{field}</span>)}</div>
      )}
      {grip && status && status.length > 0 && <span className="win-grip" aria-hidden="true" />}
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

const CELLS = 20

/** A level you can count. Cells beat a smooth bar here: in one bit there is no
 *  fill colour to judge a percentage by, but you can always count the squares. */
export function Meter({ label, value, max = 100 }: { label: string; value: number; max?: number }) {
  const pct = Math.max(0, Math.min(100, (value / max) * 100))
  const exact = (pct / 100) * CELLS
  const full = Math.floor(exact)
  const partial = exact - full >= 0.34 && full < CELLS
  return (
    <div className="meter">
      <div className="meter-head">
        <span>{label}</span>
        <span className="meter-num">{value}</span>
      </div>
      <div className="meter-track" role="meter" aria-valuenow={value} aria-valuemin={0}
        aria-valuemax={max} aria-label={label}>
        {Array.from({ length: CELLS }, (_, i) => (
          <span key={i} className={`meter-cell ${i < full ? 'on' : i === full && partial ? 'half' : ''}`} />
        ))}
      </div>
    </div>
  )
}

export function CacheBadge({ meta }: { meta?: Meta }) {
  if (!meta || meta.from_cache === undefined) return null
  return (
    <span className={`badge ${meta.stale ? 'badge-warn' : ''}`}>
      {meta.stale ? 'stale: provider unreachable' : meta.from_cache ? 'cached' : 'fresh'}
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

/** A one-bit checkbox that reports a fact rather than accepting input. */
export function StateBox({ on, label }: { on: boolean; label: string }) {
  return (
    <span className={`log-box ${on ? 'verified' : ''}`} role="img" aria-label={label}>
      {on && <PixelIcon name="check" size={12} />}
    </span>
  )
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
  canvas: 'Canvas',
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

/** Which drawn glyph stands for each evidence source. */
export const EVIDENCE_ICONS: Record<string, string> = {
  file_created: 'file', file_modified: 'file',
  document_content_changed: 'file', sheet_values_changed: 'insights',
  presentation_content_changed: 'easel', email_sent: 'envelope',
  calendar_event_completed: 'clock', github_commit_created: 'bolt',
  github_pull_request_opened: 'folder', github_pull_request_merged: 'check',
  github_checks_passed: 'check', meet_attended: 'megaphone',
  manual_confirmation: 'check',
}
