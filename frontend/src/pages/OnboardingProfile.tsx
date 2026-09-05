import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '../api/client'
import type { Profile } from '../api/types'
import { Card, ErrorNote } from '../components/ui'

export function StepDots({ step }: { step: number }) {
  return (
    <div className="step-dots" aria-label={`Onboarding step ${step + 1} of 4`}>
      {[0, 1, 2, 3].map((i) => <span key={i} className={`step-dot ${i <= step ? 'done' : ''}`} />)}
    </div>
  )
}

export function OnboardingProfile() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [name, setName] = useState('')
  const [tz, setTz] = useState(Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC')
  const [workStart, setWorkStart] = useState(9)
  const [workEnd, setWorkEnd] = useState(18)
  const [recoveryCode, setRecoveryCode] = useState<string | null>(null)
  const [recoverMode, setRecoverMode] = useState(false)
  const [recoverInput, setRecoverInput] = useState('')

  const create = useMutation({
    mutationFn: () => api<{ profile: Profile; recovery_code: string }>('/profiles', {
      body: { display_name: name, timezone: tz, work_hours_start: workStart, work_hours_end: workEnd },
    }),
    onSuccess: (resp) => setRecoveryCode(resp.data.recovery_code),
  })

  const recover = useMutation({
    mutationFn: () => api<{ profile: Profile }>('/auth/recover', { body: { recovery_code: recoverInput } }),
    onSuccess: async () => {
      await queryClient.invalidateQueries()
      navigate('/home')
    },
  })

  if (recoveryCode) {
    return (
      <Card title="Save your recovery code">
        <StepDots step={0} />
        <p>This is the <strong>only</strong> way back into this profile if your browser data is
          cleared. Compass stores just a hash, so it can never show it again.</p>
        <code className="recovery">{recoveryCode}</code>
        <div className="row" style={{ marginTop: '1rem' }}>
          <button className="primary" onClick={async () => {
            await queryClient.invalidateQueries({ queryKey: ['me'] })
            navigate('/onboarding/connect')
          }}>I saved it, continue</button>
        </div>
      </Card>
    )
  }

  return (
    <Card title="Welcome to Compass">
      <StepDots step={0} />
      <p>Compass checks that you actually did the work, using evidence from your own accounts, locally, on your machine.
        Each browser gets its own profile.</p>
      {!recoverMode ? (
        <form onSubmit={(e) => { e.preventDefault(); create.mutate() }}>
          <label htmlFor="name">Display name</label>
          <input id="name" value={name} onChange={(e) => setName(e.target.value)} required
            maxLength={60} placeholder="e.g. Alex" />
          <label htmlFor="tz">Timezone</label>
          <input id="tz" value={tz} onChange={(e) => setTz(e.target.value)} />
          <div className="row">
            <div style={{ flex: 1 }}>
              <label htmlFor="ws">Work hours start</label>
              <input id="ws" type="number" min={0} max={23} value={workStart}
                onChange={(e) => setWorkStart(Number(e.target.value))} />
            </div>
            <div style={{ flex: 1 }}>
              <label htmlFor="we">Work hours end</label>
              <input id="we" type="number" min={1} max={24} value={workEnd}
                onChange={(e) => setWorkEnd(Number(e.target.value))} />
            </div>
          </div>
          <ErrorNote error={create.error} />
          <div className="row" style={{ marginTop: '1rem' }}>
            <button className="primary" type="submit" disabled={create.isPending || !name.trim()}>
              Create my profile
            </button>
            <button type="button" onClick={() => setRecoverMode(true)}>I have a recovery code</button>
          </div>
        </form>
      ) : (
        <form onSubmit={(e) => { e.preventDefault(); recover.mutate() }}>
          <label htmlFor="code">Recovery code</label>
          <input id="code" value={recoverInput} onChange={(e) => setRecoverInput(e.target.value)}
            placeholder="XXXX-XXXX-XXXX-XXXX" />
          <ErrorNote error={recover.error} />
          <div className="row" style={{ marginTop: '1rem' }}>
            <button className="primary" type="submit" disabled={recover.isPending}>Recover profile</button>
            <button type="button" onClick={() => setRecoverMode(false)}>Back</button>
          </div>
        </form>
      )}
    </Card>
  )
}
