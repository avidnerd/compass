import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '../api/client'
import type { Character, Profile } from '../api/types'
import { Card, ErrorNote } from '../components/ui'

export function SettingsGameplay() {
  const queryClient = useQueryClient()
  const me = useQuery({ queryKey: ['me'], queryFn: () => api<Profile>('/me') })
  const character = useQuery({
    queryKey: ['character'], queryFn: () => api<Character>('/character'), retry: false,
  })
  const [motionOff, setMotionOff] = useState(
    () => document.documentElement.dataset.motion === 'off')

  useEffect(() => {
    document.documentElement.dataset.motion = motionOff ? 'off' : 'on'
  }, [motionOff])

  const patchMe = useMutation({
    mutationFn: (body: Record<string, number | string>) =>
      api<Profile>('/me', { method: 'PATCH', body }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['me'] }),
  })
  const patchCharacter = useMutation({
    mutationFn: (body: Record<string, string>) => api<Character>('/character', {
      method: 'PATCH', body, ifMatch: character.data?.data.version,
    }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['character'] }),
  })

  const profile = me.data?.data

  return (
    <>
      <h1>Settings — Gameplay</h1>
      <p className="row small">
        <Link to="/settings/connections">Connections</Link> ·
        <Link to="/settings/privacy">Privacy</Link> ·
        <Link to="/settings/gameplay">Gameplay</Link>
      </p>
      <Card title="Work hours">
        <p className="small muted">Used only for your own calendar analytics — Compass never
          rewards after-hours work for its own sake.</p>
        {profile && (
          <div className="row">
            <div style={{ flex: 1 }}>
              <label htmlFor="ws">Start</label>
              <input id="ws" type="number" min={0} max={23} defaultValue={profile.work_hours_start}
                onBlur={(e) => patchMe.mutate({ work_hours_start: Number(e.target.value) })} />
            </div>
            <div style={{ flex: 1 }}>
              <label htmlFor="we">End</label>
              <input id="we" type="number" min={1} max={24} defaultValue={profile.work_hours_end}
                onBlur={(e) => patchMe.mutate({ work_hours_end: Number(e.target.value) })} />
            </div>
            <div style={{ flex: 1 }}>
              <label htmlFor="tz">Timezone</label>
              <input id="tz" defaultValue={profile.timezone}
                onBlur={(e) => patchMe.mutate({ timezone: e.target.value })} />
            </div>
          </div>
        )}
      </Card>
      <Card title="Motion">
        <label className="row" style={{ fontWeight: 400 }}>
          <input type="checkbox" style={{ width: 'auto' }} checked={motionOff}
            onChange={(e) => setMotionOff(e.target.checked)} />
          Reduce companion animation (system reduced-motion preference is always respected too).
        </label>
      </Card>
      {character.data && (
        <Card title="Companion voice">
          <label htmlFor="tone">Tone</label>
          <select id="tone" value={character.data.data.voice_tone}
            onChange={(e) => patchCharacter.mutate({ voice_tone: e.target.value })}>
            {['warm', 'playful', 'calm', 'spirited'].map((t) => <option key={t}>{t}</option>)}
          </select>
          <label htmlFor="pers">Personality</label>
          <select id="pers" value={character.data.data.personality}
            onChange={(e) => patchCharacter.mutate({ personality: e.target.value })}>
            {['cheerful', 'thoughtful', 'adventurous', 'gentle', 'curious', 'steadfast']
              .map((t) => <option key={t}>{t}</option>)}
          </select>
        </Card>
      )}
      <ErrorNote error={patchMe.error || patchCharacter.error} />
    </>
  )
}
