import type { FocusEvaluation } from '../api/types'
import { Card, StatTile } from './ui'
import { PixelIcon } from './PixelIcon'

const LABELS: Record<string, string> = {
  direct_work: 'Direct work', supporting_work: 'Supporting work',
  off_task: 'Off-task', unclear: 'Unclear', unmonitored: 'Unmonitored',
}

function minutes(seconds: number) {
  if (seconds < 60) return `${Math.round(seconds)} sec`
  return `${Math.round(seconds / 60)} min`
}

export function FocusAttentionCard({ evaluation }: { evaluation: FocusEvaluation }) {
  const analyzed = evaluation.status === 'analyzed'
  const confidence = evaluation.confidence.overall >= 0.75 ? 'High'
    : evaluation.confidence.overall >= 0.45 ? 'Moderate' : 'Limited'
  const present = new Set(evaluation.timeline.map((segment) =>
    segment.has_evidence ? segment.classification : 'unmonitored'))

  return (
    <Card title="Private attention view">
      <h3>{evaluation.summary.headline}</h3>
      <p>{evaluation.summary.strength}</p>
      <p className="small muted">{evaluation.summary.friction}</p>

      {analyzed && (
        <>
          <div className="focus-alignment">
            <span className="small">Focus alignment</span>
            <strong>{Math.round(evaluation.attention.focused_percentage)}%</strong>
            <span className="small muted">of clearly classifiable screen time</span>
          </div>
          <div className="grid-tiles">
            <StatTile label="Direct work" value={minutes(evaluation.attention.direct_work_seconds)} />
            <StatTile label="Supporting" value={minutes(evaluation.attention.supporting_work_seconds)} />
            <StatTile label="Longest streak" value={minutes(evaluation.continuity.longest_uninterrupted_seconds)}
              hint={`${evaluation.continuity.focus_streak_count} total`} />
            <StatTile label="Detours" value={evaluation.recovery.distraction_episodes}
              hint={`${evaluation.recovery.recovered_episodes} recovered`} />
            <StatTile label="Confidence" value={confidence}
              hint={`${Math.round(evaluation.confidence.screenshot_coverage * 100)}% coverage`} />
          </div>
          {evaluation.timeline.length > 0 && (
            <div className="focus-timeline-wrap">
              <div className="focus-timeline" aria-label="Attention timeline">
                {evaluation.timeline.map((segment, index) => {
                  const key = segment.has_evidence ? segment.classification : 'unmonitored'
                  const total = Math.max(1, evaluation.timing.total_session_seconds)
                  return <span key={index} className={`focus-segment ${key}`}
                    style={{ width: `${segment.duration_seconds / total * 100}%` }}
                    title={`${LABELS[key]}: ${segment.visible_activity}`} />
                })}
              </div>
              <div className="focus-legend">
                {[...present].map((key) => <span key={key}>
                  <i className={`focus-key ${key}`} />{LABELS[key]}
                </span>)}
              </div>
            </div>
          )}
        </>
      )}

      <p className="monitoring-recommendation">
        <PixelIcon name="idea" size={12} />
        <span>{evaluation.summary.next_session_recommendation}</span>
      </p>
      <p className="small muted">
        {evaluation.frames_analyzed} of {evaluation.frames_captured} sampled moments analyzed
        {evaluation.model_id ? <> by <code>{evaluation.model_id}</code></> : ''}.
        {' '}Raw screen images were deleted after analysis. This attention view never decides task completion.
      </p>
    </Card>
  )
}
