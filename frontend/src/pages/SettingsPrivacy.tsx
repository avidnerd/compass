import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '../api/client'
import type { Job, Profile } from '../api/types'
import { Card, ErrorNote } from '../components/ui'
import { useFocusMonitoring } from '../components/FocusMonitoringProvider'
import { PixelIcon } from '../components/PixelIcon'

export function SettingsPrivacy() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [confirmDelete, setConfirmDelete] = useState('')
  const monitoring = useFocusMonitoring()

  const me = useQuery({ queryKey: ['me'], queryFn: () => api<Profile>('/me') })
  const patchMe = useMutation({
    mutationFn: (body: Record<string, boolean>) => api<Profile>('/me', { method: 'PATCH', body }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['me'] }),
  })
  const rescan = useMutation({
    mutationFn: () => api<Job>('/interest-profile:rescan', { body: {} }),
  })
  const exportData = useMutation({
    mutationFn: () => api<Record<string, unknown>>('/me/export'),
    onSuccess: (resp) => {
      const blob = new Blob([JSON.stringify(resp.data, null, 2)], { type: 'application/json' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = 'compass-export.json'
      a.click()
      URL.revokeObjectURL(url)
    },
  })
  const deleteProfile = useMutation({
    mutationFn: () => api('/me', { method: 'DELETE' }),
    onSuccess: () => {
      monitoring.abandonCapture()
      queryClient.clear()
      navigate('/onboarding/profile')
    },
  })

  const profile = me.data?.data

  return (
    <>
      <div className="page-head">
        <h1>Settings: Privacy</h1>
        <p className="row small">
          <Link to="/settings/connections">Connections</Link> ·
          <Link to="/settings/privacy">Privacy</Link> ·
          <Link to="/settings/gameplay">Gameplay</Link>
        </p>
      </div>
      <Card title="Interest scanning">
        <label className="row" style={{ fontWeight: 400 }}>
          <input type="checkbox" style={{ width: 'auto' }} checked={profile?.scan_consented ?? false}
            onChange={(e) => patchMe.mutate({ scan_consented: e.target.checked })} />
          Allow bounded workspace scanning (excerpts pass through your own Apps Script bridge
          and a verified-free OpenRouter model; nothing raw is stored).
        </label>
        <div className="row" style={{ marginTop: '0.6rem' }}>
          <button onClick={() => rescan.mutate()}
            disabled={rescan.isPending || !profile?.scan_consented}>Rescan interests now</button>
          {rescan.isSuccess && <span className="badge">rescan queued</span>}
        </div>
        <ErrorNote error={rescan.error} />
      </Card>
      <Card title="Multiplayer sharing">
        <label className="row" style={{ fontWeight: 400 }}>
          <input type="checkbox" style={{ width: 'auto' }}
            checked={profile?.share_activity_category ?? false}
            onChange={(e) => patchMe.mutate({ share_activity_category: e.target.checked })} />
          Allow a generic activity category (like “writing”) in focus rooms. Goals,
          filenames, repos, messages, and evidence are never shared regardless.
        </label>
      </Card>
      <Card title="Focus screen monitoring">
        <p className="small">Screen access is requested only when you start or resume a focus task.
          By default, Compass samples a JPEG still about every 20 seconds from the screen, window,
          or tab you choose.</p>
        <ul className="small muted">
          <li>No audio, camera, keystrokes, or clipboard access.</li>
          <li>Raw images stay in a local temporary folder and are deleted after analysis or cancellation.</li>
          <li>Only derived attention categories and metrics remain in your local SQLite database.</li>
          <li>Attention analysis is separate from task-completion evidence and is never shared in multiplayer.</li>
        </ul>
      </Card>
      <Card title="Your data">
        <div className="row">
          <button onClick={() => exportData.mutate()} disabled={exportData.isPending}>
            <PixelIcon name="down" /> Export everything as JSON
          </button>
        </div>
        <p className="small muted">Memories can be edited or deleted in the
          {' '}<Link to="/character/journal">journal</Link>; connector caches in
          {' '}<Link to="/settings/connections">connections</Link>.</p>
      </Card>
      <Card title="Delete this profile">
        <p className="small muted">Removes your profile, companion, quests, sessions, evidence,
          memories, and caches from this machine. This cannot be undone.</p>
        <label htmlFor="confirm">Type <strong>delete</strong> to confirm</label>
        <input id="confirm" value={confirmDelete} onChange={(e) => setConfirmDelete(e.target.value)} />
        <button className="danger" style={{ marginTop: '0.6rem' }}
          disabled={confirmDelete !== 'delete' || deleteProfile.isPending}
          onClick={() => deleteProfile.mutate()}>
          Permanently delete my profile
        </button>
        <ErrorNote error={deleteProfile.error} />
      </Card>
    </>
  )
}
