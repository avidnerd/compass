import { useId } from 'react'
import type { Character } from '../api/types'
import { PixelIcon } from './PixelIcon'

/** The companion, drawn as one-bit pixel art on a 24x24 grid.
 *
 *  Silhouettes are authored as masks; the one-pixel outline is computed from the
 *  mask at render time, so it is always exact and never drifts from the shape.
 *  The creature reads first: its body is paper-white inside a hard outline, and
 *  pattern is confined to the lower coat so the face never competes with texture.
 *
 *  There is no colour in this system, so the character's `palette` enum selects a
 *  COAT PATTERN and `aura` becomes the habitat's own material — the enums keep
 *  their job of telling companions apart, in the only vocabulary a one-bit world
 *  has. Everything is still enum-driven; nothing here is ever produced by a model
 *  beyond those enum choices. */

const W = 24

/** Coat patterns, replacing the old colour palettes one for one. */
export const COATS: Record<string, string> = {
  meadow: 'p25',
  ember: 'phatch',
  tide: 'phstripe',
  dusk: 'p50',
  citrus: 'pchecker',
  orchid: 'pvstripe',
}

/** The body a species shares below the head. */
const TORSO = [
  '...##################...', // 8
  '...##################...', // 9
  '..####################..', // 10
  '..####################..', // 11
  '..####################..', // 12
  '..####################..', // 13
  '..####################..', // 14
  '...##################...', // 15
  '...##################...', // 16
  '....################....', // 17
  '.....##############.....', // 18
  '......############......', // 19
  '.......##########.......', // 20
  '......###....###........', // 21
  '......###....###........', // 22
  '........................', // 23
]

const BODIES: Record<string, string[]> = {
  sproutling: [
    '........................', // 0
    '........................', // 1
    '......##......##........', // 2  leaves
    '.....####....####.......', // 3
    '......####..####........', // 4
    '........######..........', // 5  stem
    '.....##############.....', // 6
    '....################....', // 7
    ...TORSO,
  ],
  emberfox: [
    '........................', // 0
    '........................', // 1
    '....##..........##......', // 2  ears
    '....####......####......', // 3
    '.....#####..#####.......', // 4
    '......############......', // 5
    '.....##############.....', // 6
    '....################....', // 7
    '...##################...', // 8
    '...##################...', // 9
    '..####################..', // 10
    '..####################..', // 11
    '..####################..', // 12
    '..####################..', // 13
    '..####################..', // 14
    '...##################...', // 15
    '...###################..', // 16  tail
    '....###################.', // 17
    '.....##################.', // 18
    '......############......', // 19
    '.......##########.......', // 20
    '......###....###........', // 21
    '......###....###........', // 22
    '........................', // 23
  ],
  tidepup: [
    '........................', // 0
    '........................', // 1
    '........................', // 2
    '..........####..........', // 3  crest
    '..........####..........', // 4
    '........######..........', // 5
    '.....##############.....', // 6
    '....################....', // 7
    '...##################...', // 8
    '...##################...', // 9
    '..####################..', // 10
    '.######################.', // 11  fins
    '.######################.', // 12
    '..####################..', // 13
    '..####################..', // 14
    '...##################...', // 15
    '...##################...', // 16
    '....################....', // 17
    '.....##############.....', // 18
    '......############......', // 19
    '.......##########.......', // 20
    '......###....###........', // 21
    '......###....###........', // 22
    '........................', // 23
  ],
}

type Run = [x: number, y: number, w: number]

/** Pattern is confined to the lower coat so the face stays legible. */
const COAT_FROM = 16

const EYES: Record<string, { ink: Run[]; light?: Run[] }> = {
  round: { ink: [[8, 10, 2], [8, 11, 2], [14, 10, 2], [14, 11, 2]] },
  sparkle: {
    ink: [[8, 10, 2], [8, 11, 2], [14, 10, 2], [14, 11, 2]],
    light: [[8, 10, 1], [14, 10, 1]],
  },
  sleepy: { ink: [[7, 11, 4], [13, 11, 4]] },
  determined: { ink: [[7, 9, 4], [13, 9, 4], [8, 11, 2], [14, 11, 2]] },
}

const MOUTH: Run[] = [[10, 14, 1], [11, 15, 2], [13, 14, 1]]

const MARKINGS: Record<string, Run[]> = {
  stripes: [[4, 12, 2], [18, 12, 2], [4, 13, 2], [18, 13, 2]],
  spots: [[5, 13, 2], [17, 12, 2]],
  patches: [[15, 7, 4], [15, 8, 4]],
  swirl: [[10, 18, 4], [10, 19, 1], [13, 19, 1]],
}

const ACCESSORIES: Record<string, { ink: Run[]; light?: Run[] }> = {
  scarf: { ink: [[5, 16, 14], [5, 17, 14], [10, 18, 2], [10, 19, 2]] },
  glasses: {
    ink: [
      [6, 9, 5], [6, 10, 1], [10, 10, 1], [6, 11, 1], [10, 11, 1], [6, 12, 5],
      [13, 9, 5], [13, 10, 1], [17, 10, 1], [13, 11, 1], [17, 11, 1], [13, 12, 5],
      [11, 10, 2],
    ],
  },
  flower: { ink: [[17, 3, 3], [17, 4, 3], [18, 5, 1]], light: [[18, 4, 1]] },
  headphones: {
    ink: [[7, 4, 10], [6, 5, 1], [17, 5, 1], [4, 6, 3], [4, 7, 3], [17, 6, 3], [17, 7, 3]],
  },
  /* Slung on the flank: a strap over the face would read as a scar, not a bag. */
  satchel: {
    ink: [[12, 16, 1], [13, 17, 1], [13, 18, 5], [13, 19, 4]],
    light: [[14, 18, 3]],
  },
  bowtie: { ink: [[8, 16, 3], [7, 17, 4], [8, 18, 3], [13, 16, 3], [13, 17, 4], [13, 18, 3], [11, 17, 2]] },
  crown: { ink: [[6, 1, 2], [11, 1, 2], [16, 1, 2], [6, 2, 12], [6, 3, 12]], light: [[9, 3, 1], [14, 3, 1]] },
}

const HABITAT_PROPS: Record<string, string> = {
  bookstack: 'bookstack', terrarium: 'terrarium', lantern: 'lantern', easel: 'easel',
  telescope: 'telescope', kettle: 'kettle', banner: 'banner', trophy: 'ranks',
}

function grid(rows: string[]) {
  return (x: number, y: number) => y >= 0 && y < W && x >= 0 && x < W && rows[y][x] === '#'
}

/** Merge horizontal spans so a 24x24 field ships as ~60 rects, not 576. */
function merge(hit: (x: number, y: number) => boolean): Run[] {
  const out: Run[] = []
  for (let y = 0; y < W; y += 1) {
    let x = 0
    while (x < W) {
      if (hit(x, y)) {
        let w = 1
        while (x + w < W && hit(x + w, y)) w += 1
        out.push([x, y, w])
        x += w
      } else x += 1
    }
  }
  return out
}

function Rects({ runs, fill }: { runs: Run[]; fill: string }) {
  return (
    <>
      {runs.map(([x, y, w]) => (
        <rect key={`${x}-${y}-${w}`} x={x} y={y} width={w} height={1} fill={fill} />
      ))}
    </>
  )
}

const PATTERN_TILES: Record<string, [number, number, number, number][]> = {
  p25: [[0, 0, 1, 1]],
  p50: [[0, 0, 1, 1], [1, 1, 1, 1]],
  phatch: [[0, 0, 1, 1], [1, 1, 1, 1], [2, 2, 1, 1], [3, 3, 1, 1]],
  phstripe: [[0, 0, 2, 1]],
  pvstripe: [[0, 0, 1, 2]],
  pchecker: [[0, 0, 2, 2], [2, 2, 2, 2]],
}
const TILE_SIZE: Record<string, number> = {
  p25: 2, p50: 2, phatch: 4, phstripe: 2, pvstripe: 2, pchecker: 4,
}

export function Companion({ character, size = 240, showHabitat = true }: {
  character: Pick<Character, 'species' | 'palette' | 'eyes' | 'markings' | 'accessory' | 'aura' | 'habitat' | 'animation' | 'expression'> & { props?: string[] }
  size?: number
  showHabitat?: boolean
}) {
  const uid = useId().replace(/:/g, '')
  /** Snap to a whole multiple of the grid so every drawn pixel stays square. */
  const frame = Math.max(W, Math.round(size / W) * W)
  /** The creature sits inside the habitat, clear of its corner props. */
  const art = showHabitat ? Math.max(W, Math.round((frame * 0.74) / W) * W) : frame

  const rows = BODIES[character.species] ?? BODIES.sproutling
  const solid = grid(rows)
  const edge = (x: number, y: number) =>
    solid(x, y) && !(solid(x - 1, y) && solid(x + 1, y) && solid(x, y - 1) && solid(x, y + 1))

  const outline = merge(edge)
  const body = merge((x, y) => solid(x, y) && !edge(x, y) && y < COAT_FROM)
  const coat = merge((x, y) => solid(x, y) && !edge(x, y) && y >= COAT_FROM)

  const coatKey = COATS[character.palette] ?? 'p25'
  const coatId = `${uid}-coat`
  const shadeId = `${uid}-shade`

  const eyes = EYES[character.eyes] ?? EYES.round
  const marks = MARKINGS[character.markings] ?? []
  const worn = ACCESSORIES[character.accessory]
  const anim = character.animation || 'idle'
  const props = (character.props ?? []).slice(0, 4)

  return (
    <div className={`companion-wrap anim-${anim}`} style={{ width: frame, height: frame }}
      role="img" aria-label={`Your companion, a ${character.species}`}>
      {showHabitat && (
        <>
          <div className={`habitat aura-${character.aura || 'none'}`} aria-hidden="true" />
          {props.map((p) => (
            <span key={p} className="habitat-prop" title={p}>
              <PixelIcon name={HABITAT_PROPS[p] ?? 'sparkle'} size={24} />
            </span>
          ))}
        </>
      )}
      <svg viewBox={`0 0 ${W} ${W}`} width={art} height={art} className="companion-svg"
        shapeRendering="crispEdges" aria-hidden="true">
        <defs>
          <pattern id={coatId} patternUnits="userSpaceOnUse"
            width={TILE_SIZE[coatKey]} height={TILE_SIZE[coatKey]}>
            {PATTERN_TILES[coatKey].map(([x, y, w, h]) => (
              <rect key={`${x}-${y}`} x={x} y={y} width={w} height={h} fill="#000" />
            ))}
          </pattern>
          <pattern id={shadeId} patternUnits="userSpaceOnUse" width="2" height="2">
            <rect x="0" y="0" width="1" height="1" fill="#000" />
            <rect x="1" y="1" width="1" height="1" fill="#000" />
          </pattern>
        </defs>

        {/* The creature casts a dithered shadow, not a soft one. */}
        <rect x="7" y="23" width="10" height="1" fill={`url(#${shadeId})`} />

        <g className="companion-body">
          <Rects runs={body} fill="#fff" />
          <Rects runs={coat} fill={`url(#${coatId})`} />
          <Rects runs={outline} fill="#000" />
          {marks.length > 0 && <Rects runs={marks} fill="#000" />}
          <Rects runs={eyes.ink} fill="#000" />
          {eyes.light && <Rects runs={eyes.light} fill="#fff" />}
          <Rects runs={MOUTH} fill="#000" />
          {character.expression === 'joyful' && (
            <Rects runs={[[5, 12, 2], [17, 12, 2]]} fill="#000" />
          )}
          {worn && (
            <>
              <Rects runs={worn.ink} fill="#000" />
              {worn.light && <Rects runs={worn.light} fill="#fff" />}
            </>
          )}
        </g>
      </svg>
    </div>
  )
}
