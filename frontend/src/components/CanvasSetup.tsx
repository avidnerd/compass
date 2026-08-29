import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '../api/client'
import type { CanvasLink } from '../api/types'
import { Card, ErrorNote } from './ui'
import { PixelIcon } from './PixelIcon'

/** Canvas is linked by pasting a personal calendar-feed URL.
 *
 *  Not a token and not OAuth: Canvas is closing student access tokens off, and
 *  OAuth needs a developer key the institution's admin has to issue. The
 *  calendar feed is the only door a student can open alone. */
export function CanvasSetup() {
  const queryClient = useQueryClient()
  const [url, setUrl] = useState('')

  const status = useQuery({
    queryKey: ['canvas-status'],
    queryFn: () => api<CanvasLink>('/canvas/status'),
    retry: false,
  })
  const link = useMutation({
    mutationFn: () => api<{ linked: boolean; assignment_count: number; feed: string }>(
      '/canvas/link', { body: { feed_url: url } }),
    onSuccess: () => {
      setUrl('')
      queryClient.invalidateQueries({ queryKey: ['canvas-status'] })
      queryClient.invalidateQueries({ queryKey: ['canvas'] })
    },
  })
  const unlink = useMutation({
    mutationFn: () => api('/canvas/link', { method: 'DELETE' }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['canvas-status'] })
      queryClient.invalidateQueries({ queryKey: ['canvas'] })
    },
  })

  const linked = status.data?.data.status === 'linked'

  return (
    <Card
      title="Canvas"
      status={[linked ? `Feed ${status.data?.data.feed}` : 'Not linked', 'Due dates only']}
    >
      {linked ? (
        <>
          <p>Linked. Compass reads your assignment due dates and can turn them into quests.</p>
          <p className="small">
            A Canvas feed carries deadlines, not proof — it has no submission status and no
            grades. An assignment can start a quest; finishing one is still verified from Drive,
            Gmail, Calendar or GitHub.
          </p>
          <div className="row">
            <button className="danger" onClick={() => unlink.mutate()} disabled={unlink.isPending}>
              Unlink Canvas
            </button>
          </div>
          <ErrorNote error={unlink.error} />
        </>
      ) : (
        <>
          <p>In Canvas, open <strong>Calendar</strong>, click <strong>Calendar Feed</strong>,
            and copy the link. No token and no admin approval — the feed is yours to share or
            revoke.</p>
          <label htmlFor="canvas-feed">Calendar feed URL</label>
          <input id="canvas-feed" value={url} onChange={(e) => setUrl(e.target.value)}
            placeholder="https://canvas.yourschool.edu/feeds/calendars/user_….ics"
            autoComplete="off" spellCheck={false} />
          <p className="small">
            Treat this like a password: anyone holding the URL can read your schedule. Compass
            stores it encrypted and never shows it again in full.
          </p>
          <div className="row">
            <button className="primary" onClick={() => link.mutate()}
              disabled={link.isPending || !url.trim()}>
              <PixelIcon name="plug" /> {link.isPending ? 'Checking the feed…' : 'Link Canvas'}
            </button>
          </div>
          <ErrorNote error={link.error} />
        </>
      )}
    </Card>
  )
}
