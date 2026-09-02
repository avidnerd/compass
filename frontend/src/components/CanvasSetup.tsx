import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '../api/client'
import type { CanvasLink } from '../api/types'
import { Card, ErrorNote } from './ui'
import { PixelIcon } from './PixelIcon'

/** Deadlines are linked by pasting calendar-feed URLs.
 *
 *  Canvas is the anchor and is linked by its Calendar Feed — not a token and not
 *  OAuth, because Canvas is closing student access tokens off and OAuth needs a
 *  developer key an institution admin issues.
 *
 *  Canvas is not the whole picture, though. A course graded through Gradescope,
 *  Pearson or LabFlow can have deadlines that never reach Canvas at all, so any
 *  tool that publishes iCalendar can be added alongside it. */
export function CanvasSetup() {
  const queryClient = useQueryClient()
  const [url, setUrl] = useState('')
  const [label, setLabel] = useState('')
  const [kind, setKind] = useState<'canvas' | 'generic'>('canvas')

  const status = useQuery({
    queryKey: ['canvas-status'],
    queryFn: () => api<CanvasLink>('/canvas/status'),
    retry: false,
  })
  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ['canvas-status'] })
    queryClient.invalidateQueries({ queryKey: ['canvas'] })
    queryClient.invalidateQueries({ queryKey: ['canvas-due'] })
  }
  const link = useMutation({
    mutationFn: () => api<{ linked: boolean; assignment_count: number; feed: string }>(
      '/canvas/link', { body: { feed_url: url, label, kind } }),
    onSuccess: () => { setUrl(''); setLabel(''); invalidate() },
  })
  const removeFeed = useMutation({
    mutationFn: (id: string) => api(`/canvas/feeds/${id}`, { method: 'DELETE' }),
    onSuccess: invalidate,
  })

  const feeds = status.data?.data.feeds ?? []
  const hasCanvas = feeds.some((f) => f.kind === 'canvas')

  return (
    <Card
      title="Deadline feeds"
      status={[`${feeds.length} linked`, 'Due dates only']}
    >
      {feeds.length > 0 && (
        <div className="log" style={{ marginBottom: 12 }}>
          {feeds.map((f) => (
            <div key={f.id} className="log-row">
              <span className="log-box"><PixelIcon name="check" size={12} /></span>
              <span className="log-what">
                <strong>{f.label}</strong>
                <small>{f.kind === 'canvas' ? 'Canvas assignments' : 'All dated events'} · {f.feed}</small>
              </span>
              <button onClick={() => removeFeed.mutate(f.id!)} disabled={removeFeed.isPending}>
                Remove
              </button>
            </div>
          ))}
        </div>
      )}
      <ErrorNote error={removeFeed.error} />

      {!hasCanvas && (
        <p>Start with Canvas: open <strong>Calendar</strong>, click <strong>Calendar Feed</strong>,
          and copy the link. No token and no admin approval.</p>
      )}

      <p className="small">
        Canvas only carries deadlines your instructors entered <em>in Canvas</em>. If a course
        grades through Gradescope, Pearson or LabFlow, some deadlines may live only there —
        add any calendar those tools publish, or a personal calendar you sync them into.
      </p>

      <label htmlFor="feed-kind">Feed type</label>
      <select id="feed-kind" value={kind} onChange={(e) => setKind(e.target.value as 'canvas' | 'generic')}>
        <option value="canvas">Canvas — assignments only</option>
        <option value="generic">Another calendar — every dated event</option>
      </select>

      <label htmlFor="feed-label">Name it</label>
      <input id="feed-label" value={label} onChange={(e) => setLabel(e.target.value)}
        maxLength={60} placeholder={kind === 'canvas' ? 'Canvas' : 'Gradescope'} />

      <label htmlFor="canvas-feed">Calendar feed URL</label>
      <input id="canvas-feed" value={url} onChange={(e) => setUrl(e.target.value)}
        placeholder="https://…/feeds/calendars/user_….ics"
        autoComplete="off" spellCheck={false} />

      <p className="small">
        Treat this like a password: anyone holding the URL can read that calendar. Compass
        stores it encrypted and never shows it again in full.
      </p>
      <div className="row">
        <button className="primary" onClick={() => link.mutate()}
          disabled={link.isPending || !url.trim()}>
          <PixelIcon name="plug" /> {link.isPending ? 'Checking the feed…' : 'Add feed'}
        </button>
      </div>
      <ErrorNote error={link.error} />
    </Card>
  )
}
