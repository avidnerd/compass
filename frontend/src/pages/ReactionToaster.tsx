import { useEffect, useState } from 'react'
import type { GameEvent } from '../api/types'
import { PixelIcon } from '../components/PixelIcon'

interface Toast {
  id: number
  lines: string[]
}

const EMOTE_ICON: Record<string, string> = {
  cheer: 'megaphone', heart: 'heart', spark: 'sparkle',
  flex: 'bolt', tea: 'kettle', confetti: 'sparkle',
}

/** Shows companion reactions and multiplayer moments as gentle toasts. */
export function ReactionToaster() {
  const [toasts, setToasts] = useState<Toast[]>([])
  const [emotes, setEmotes] = useState<{ id: number; emote: string }[]>([])

  useEffect(() => {
    const onEvent = (e: Event) => {
      const event = (e as CustomEvent<GameEvent>).detail
      if (event.type === 'reaction.created') {
        const p = event.payload as { reaction?: string; encouragement?: string }
        push([p.reaction, p.encouragement].filter(Boolean) as string[])
      } else if (event.type === 'party.emote') {
        const p = event.payload as { emote?: string; display_name?: string }
        const glyph = EMOTE_ICON[p.emote ?? ''] ?? 'sparkle'
        const id = Date.now() + Math.random()
        setEmotes((prev) => [...prev, { id, emote: glyph }])
        setTimeout(() => setEmotes((prev) => prev.filter((x) => x.id !== id)), 1700)
      }
    }
    window.addEventListener('compass-event', onEvent)
    return () => window.removeEventListener('compass-event', onEvent)
  }, [])

  const push = (lines: string[]) => {
    if (!lines.length) return
    const id = Date.now() + Math.random()
    setToasts((prev) => [...prev.slice(-2), { id, lines }])
    setTimeout(() => setToasts((prev) => prev.filter((t) => t.id !== id)), 7000)
  }

  return (
    <>
      <div className="toaster" role="status" aria-live="polite">
        {toasts.map((t) => (
          <div key={t.id} className="toast">
            {t.lines.map((line, i) => <p key={i} style={{ margin: i ? '0.3rem 0 0' : 0 }}>{line}</p>)}
          </div>
        ))}
      </div>
      {emotes.map((e, i) => (
        <span key={e.id} className="emote-burst"
          style={{ right: `${32 + (i % 3) * 38}px`, bottom: 96 }} aria-hidden="true">
          <PixelIcon name={e.emote} size={36} />
        </span>
      ))}
    </>
  )
}
