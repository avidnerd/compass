import type { SimulatedPlayer } from '../api/types'
import { PixelIcon, iconFor } from './PixelIcon'

const STATUS_LABELS = {
  online: 'Online',
  in_focus: 'In focus',
  away: 'Away',
} as const

export function SimulatedPlayerCard({ player, actionLabel, onAction, active = false, disabled = false }:
  {
    player: SimulatedPlayer
    actionLabel: string
    onAction: () => void
    active?: boolean
    disabled?: boolean
  }) {
  return (
    <article className={`player-card ${active ? 'selected' : ''}`}>
      <div className="player-card-top">
        <div className={`player-avatar palette-${player.palette}`} aria-hidden="true"><PixelIcon name={iconFor(player.avatar)} size={24} /></div>
        <div className="player-identity">
          <div className="row player-name-row">
            <h3>{player.display_name}</h3>
            <span className={`presence presence-${player.status}`}>
              <span aria-hidden="true" />{STATUS_LABELS[player.status]}
            </span>
          </div>
          <div className="small muted">{player.handle} · Lv. {player.level}</div>
        </div>
      </div>
      <p className="player-title">{player.title}</p>
      <p className="small muted player-companion">
        {player.companion_name} the {player.companion_species} · {player.availability}
      </p>
      <dl className="player-stats">
        <div><dt>Streak</dt><dd>{player.stats.focus_streak}d</dd></div>
        
        <div><dt>Co-op</dt><dd>{player.stats.collaboration}</dd></div>
      </dl>
      <button className={active ? 'player-action selected' : 'player-action'} onClick={onAction}
        disabled={disabled} aria-pressed={active}>
        {active ? 'Selected' : actionLabel}
      </button>
    </article>
  )
}
