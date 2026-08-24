import type { Character } from '../api/types'

/** Layered local SVG companion. All layers are enum-driven; nothing here is
 * ever produced by an LLM beyond enum choices. */

export const PALETTES: Record<string, { body: string; belly: string; accent: string; habitat: string }> = {
  meadow: { body: '#7cbf6b', belly: '#dff0d0', accent: '#4c8a3f', habitat: '#eaf6df' },
  ember: { body: '#e8875a', belly: '#ffe3c8', accent: '#c05b2e', habitat: '#fdeee2' },
  tide: { body: '#5fa8d3', belly: '#dceefb', accent: '#33698f', habitat: '#e5f2fb' },
  dusk: { body: '#8d7bb8', belly: '#e8e1f5', accent: '#5d4a8a', habitat: '#efeaf9' },
  citrus: { body: '#e3b23c', belly: '#fbeecb', accent: '#b08215', habitat: '#fbf4dd' },
  orchid: { body: '#d377a8', belly: '#f9dfec', accent: '#a34a78', habitat: '#fceaf3' },
}

function Eyes({ kind, cx1, cx2, cy }: { kind: string; cx1: number; cx2: number; cy: number }) {
  if (kind === 'sleepy') {
    return (
      <g stroke="#2f2a36" strokeWidth="2.4" strokeLinecap="round" fill="none">
        <path d={`M ${cx1 - 5} ${cy} q 5 4 10 0`} />
        <path d={`M ${cx2 - 5} ${cy} q 5 4 10 0`} />
      </g>
    )
  }
  if (kind === 'determined') {
    return (
      <g fill="#2f2a36">
        <path d={`M ${cx1 - 6} ${cy - 5} l 12 3 l -1 3 l -11 -1 z`} />
        <path d={`M ${cx2 + 6} ${cy - 5} l -12 3 l 1 3 l 11 -1 z`} />
      </g>
    )
  }
  return (
    <g fill="#2f2a36">
      <circle cx={cx1} cy={cy} r={4.4} />
      <circle cx={cx2} cy={cy} r={4.4} />
      {kind === 'sparkle' && (
        <g fill="#ffffff">
          <circle cx={cx1 + 1.6} cy={cy - 1.6} r={1.5} />
          <circle cx={cx2 + 1.6} cy={cy - 1.6} r={1.5} />
        </g>
      )}
    </g>
  )
}

function Markings({ kind, color }: { kind: string; color: string }) {
  if (kind === 'stripes')
    return (
      <g stroke={color} strokeWidth="3" strokeLinecap="round" opacity="0.55" fill="none">
        <path d="M 38 78 q 8 -4 16 0" />
        <path d="M 66 78 q 8 -4 16 0" />
      </g>
    )
  if (kind === 'spots')
    return (
      <g fill={color} opacity="0.5">
        <circle cx="42" cy="76" r="3.4" />
        <circle cx="76" cy="72" r="2.8" />
        <circle cx="62" cy="84" r="2.2" />
      </g>
    )
  if (kind === 'patches')
    return <ellipse cx="72" cy="66" rx="9" ry="7" fill={color} opacity="0.4" />
  if (kind === 'swirl')
    return (
      <path d="M 58 80 q 8 -8 2 -12 q -5 -3 -7 3" stroke={color} strokeWidth="2.6" fill="none"
        opacity="0.6" strokeLinecap="round" />
    )
  return null
}

function Accessory({ kind, accent }: { kind: string; accent: string }) {
  switch (kind) {
    case 'scarf':
      return (
        <g>
          <path d="M 40 92 q 20 10 40 0 l -2 8 q -18 8 -36 0 z" fill={accent} />
          <rect x="52" y="94" width="7" height="16" rx="3" fill={accent} />
        </g>
      )
    case 'glasses':
      return (
        <g stroke="#2f2a36" strokeWidth="2.2" fill="rgba(255,255,255,0.35)">
          <circle cx="48" cy="58" r="8" />
          <circle cx="72" cy="58" r="8" />
          <path d="M 56 58 h 8" fill="none" />
        </g>
      )
    case 'flower':
      return (
        <g transform="translate(78,34)">
          {[0, 72, 144, 216, 288].map((a) => (
            <ellipse key={a} rx="4" ry="6.5" fill="#f6a7c1" transform={`rotate(${a})`} />
          ))}
          <circle r="3" fill="#f3d258" />
        </g>
      )
    case 'headphones':
      return (
        <g fill="#2f2a36">
          <path d="M 36 50 q 24 -26 48 0 l -5 4 q -19 -22 -38 0 z" />
          <rect x="32" y="50" width="9" height="14" rx="4" />
          <rect x="79" y="50" width="9" height="14" rx="4" />
        </g>
      )
    case 'satchel':
      return (
        <g>
          <path d="M 42 66 L 82 96" stroke="#8a6b47" strokeWidth="3.4" />
          <rect x="74" y="90" width="18" height="13" rx="3" fill="#a5824f" />
        </g>
      )
    case 'bowtie':
      return (
        <g fill={accent}>
          <path d="M 60 92 l -12 -6 v 12 z" />
          <path d="M 60 92 l 12 -6 v 12 z" />
          <circle cx="60" cy="92" r="2.6" />
        </g>
      )
    case 'crown':
      return (
        <g fill="#f3c94f" stroke="#c9a02e" strokeWidth="1">
          <path d="M 46 34 l 4 -10 l 6 7 l 4 -11 l 4 11 l 6 -7 l 4 10 z" />
        </g>
      )
    default:
      return null
  }
}

function Aura({ kind }: { kind: string }) {
  if (kind === 'soft-glow') return <circle cx="60" cy="72" r="46" fill="#ffe9a8" opacity="0.35" />
  if (kind === 'sparkles')
    return (
      <g fill="#f3c94f" className="sparkle-layer">
        <circle cx="24" cy="40" r="2" />
        <circle cx="98" cy="52" r="2.4" />
        <circle cx="88" cy="24" r="1.8" />
        <circle cx="30" cy="90" r="1.8" />
      </g>
    )
  if (kind === 'bubbles')
    return (
      <g stroke="#9fcbe8" fill="none" strokeWidth="1.4" opacity="0.8">
        <circle cx="26" cy="46" r="4" />
        <circle cx="96" cy="38" r="5.5" />
        <circle cx="92" cy="86" r="3" />
      </g>
    )
  if (kind === 'embers')
    return (
      <g fill="#e8875a" opacity="0.8">
        <circle cx="28" cy="44" r="2.2" />
        <circle cx="94" cy="60" r="1.8" />
        <circle cx="86" cy="30" r="2.6" />
      </g>
    )
  return null
}

function Body({ species, palette }: { species: string; palette: { body: string; belly: string; accent: string } }) {
  if (species === 'emberfox') {
    return (
      <g>
        <path d="M 38 44 l -6 -18 l 16 8 z" fill={palette.body} />
        <path d="M 82 44 l 6 -18 l -16 8 z" fill={palette.body} />
        <ellipse cx="60" cy="74" rx="30" ry="32" fill={palette.body} />
        <ellipse cx="60" cy="86" rx="18" ry="16" fill={palette.belly} />
        <path d="M 86 92 q 16 4 12 18 q -10 -2 -14 -10" fill={palette.accent} opacity="0.9" />
      </g>
    )
  }
  if (species === 'tidepup') {
    return (
      <g>
        <ellipse cx="60" cy="76" rx="31" ry="30" fill={palette.body} />
        <ellipse cx="60" cy="88" rx="19" ry="14" fill={palette.belly} />
        <path d="M 30 62 q -10 6 -6 16 q 8 0 12 -8" fill={palette.body} />
        <path d="M 90 62 q 10 6 6 16 q -8 0 -12 -8" fill={palette.body} />
        <path d="M 48 40 q 12 -14 24 0 q -12 -6 -24 0" fill={palette.accent} />
      </g>
    )
  }
  // sproutling
  return (
    <g>
      <path d="M 60 26 q -2 -12 -12 -14 q 2 12 8 15 z" fill={palette.accent} />
      <path d="M 60 26 q 2 -12 12 -14 q -2 12 -8 15 z" fill={palette.accent} />
      <ellipse cx="60" cy="76" rx="30" ry="31" fill={palette.body} />
      <ellipse cx="60" cy="87" rx="18" ry="15" fill={palette.belly} />
    </g>
  )
}

const HABITAT_PROPS: Record<string, string> = {
  bookstack: '📚', terrarium: '🪴', lantern: '🏮', easel: '🎨',
  telescope: '🔭', kettle: '🫖', banner: '🚩', trophy: '🏆',
}

export function Companion({ character, size = 220, showHabitat = true }: {
  character: Pick<Character, 'species' | 'palette' | 'eyes' | 'markings' | 'accessory' | 'aura' | 'habitat' | 'animation' | 'expression'> & { props?: string[] }
  size?: number
  showHabitat?: boolean
}) {
  const palette = PALETTES[character.palette] ?? PALETTES.meadow
  const anim = character.animation || 'idle'
  return (
    <div className={`companion-wrap anim-${anim}`} style={{ width: size, height: size }}
      role="img" aria-label={`Your companion, a ${character.species}`}>
      {showHabitat && (
        <div className="habitat" style={{ background: palette.habitat }} aria-hidden="true">
          {(character.props ?? []).slice(0, 4).map((p) => (
            <span key={p} className="habitat-prop" title={p}>{HABITAT_PROPS[p] ?? '✨'}</span>
          ))}
        </div>
      )}
      <svg viewBox="0 0 120 120" width="100%" height="100%" className="companion-svg">
        <Aura kind={character.aura} />
        <ellipse cx="60" cy="108" rx="26" ry="5" fill="rgba(0,0,0,0.12)" />
        <g className="companion-body">
          <Body species={character.species} palette={palette} />
          <Markings kind={character.markings} color={palette.accent} />
          <Eyes kind={character.eyes} cx1={49} cx2={71} cy={60} />
          <path d="M 55 70 q 5 5 10 0" stroke="#2f2a36" strokeWidth="2.2" fill="none" strokeLinecap="round" />
          {character.expression === 'joyful' && (
            <g fill="#f6a7c1" opacity="0.7">
              <circle cx="42" cy="68" r="3.6" />
              <circle cx="78" cy="68" r="3.6" />
            </g>
          )}
          <Accessory kind={character.accessory} accent={palette.accent} />
        </g>
      </svg>
    </div>
  )
}
