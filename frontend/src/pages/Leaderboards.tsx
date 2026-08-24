import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { api } from '../api/client'
import type { Leaderboards as LeaderboardsData } from '../api/types'
import { ErrorNote, Spinner } from '../components/ui'

function formatValue(value: number, unit: string) {
  return `${value.toLocaleString()} ${unit}`
}

export function Leaderboards() {
  const boards = useQuery({
    queryKey: ['leaderboards'],
    queryFn: () => api<LeaderboardsData>('/leaderboards'),
  })
  const [selectedMetric, setSelectedMetric] = useState('focus_minutes')

  if (boards.isPending) return <Spinner label="Scouting the league…" />
  if (boards.isError) return <ErrorNote error={boards.error} />

  const data = boards.data.data
  const active = data.metrics.find((metric) => metric.id === selectedMetric) ?? data.metrics[0]
  const topThree = active.entries.slice(0, 3)
  const current = active.entries.find((entry) => entry.is_current_user)

  return (
    <div className="leaderboard-page">
      <header className="social-hero leaderboard-hero">
        <div>
          <p className="social-kicker">The clubhouse</p>
          <h1>League board</h1>
          <p>See who is finding their rhythm — from quiet streak-builders to boss-breaking regulars.</p>
        </div>
        <div className="season-stamp"><span>Current season</span><strong>{data.season}</strong></div>
      </header>

      <div className="leaderboard-tabs" role="tablist" aria-label="Leaderboard statistic">
        {data.metrics.map((metric) => (
          <button key={metric.id} role="tab" aria-selected={active.id === metric.id}
            className={active.id === metric.id ? 'active' : ''}
            onClick={() => setSelectedMetric(metric.id)}>
            <span aria-hidden="true">{metric.icon}</span>{metric.short_label}
          </button>
        ))}
      </div>

      <section className="league-podium" aria-label={`Top three for ${active.label}`}>
        {topThree.map((entry, index) => (
          <article key={entry.profile_id} className={`league-podium-card place-${index + 1}`}>
            <span className="league-place">#{entry.rank}</span>
            <div className="league-avatar" aria-hidden="true">{entry.avatar}</div>
            <h2>{entry.display_name}</h2>
            <p>{entry.title}</p>
            <strong>{formatValue(entry.value, active.unit)}</strong>
          </article>
        ))}
      </section>

      <section className="leaderboard-sheet">
        <header>
          <div><p className="social-kicker">This season</p><h2>{active.icon} {active.label}</h2></div>
          {current && <div className="your-rank"><span>Your rank</span><strong>#{current.rank}</strong></div>}
        </header>
        <div className="leaderboard-list" role="table" aria-label={`${active.label} standings`}>
          {active.entries.map((entry) => (
            <div key={entry.profile_id} className={`leaderboard-row ${entry.is_current_user ? 'is-you' : ''}`}
              role="row">
              <div className="rank-cell" role="cell">{entry.rank}</div>
              <div className="leaderboard-person" role="cell">
                <span className="mini-avatar" aria-hidden="true">{entry.avatar}</span>
                <span><strong>{entry.display_name}</strong>
                  <small>{entry.is_current_user ? 'You' : entry.title}</small></span>
              </div>
              <div className="trend-cell" role="cell" aria-label={entry.trend > 0 ? 'Up one place' : entry.trend < 0 ? 'Down one place' : 'No rank change'}>
                {entry.trend > 0 ? '↑ 1' : entry.trend < 0 ? '↓ 1' : '—'}
              </div>
              <div className="score-cell" role="cell">{formatValue(entry.value, active.unit)}</div>
            </div>
          ))}
        </div>
      </section>

      <p className="leaderboard-note">
        Demo rivals use simulated stats. Your row reflects your real Compass activity.{' '}
        <Link to="/battle">Challenge a rival</Link> or <Link to="/party">form a party</Link>.
      </p>
    </div>
  )
}
