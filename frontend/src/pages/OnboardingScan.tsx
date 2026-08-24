import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '../api/client'
import type { FreeModelStatus, InterestProfile, Job, Profile } from '../api/types'
import { Card, ErrorNote } from '../components/ui'
import { StepDots } from './OnboardingProfile'

export function OnboardingScan() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [jobId, setJobId] = useState<string | null>(null)

  const freeModels = useQuery({
    queryKey: ['free-models'],
    queryFn: () => api<FreeModelStatus>('/system/free-models'),
  })
  const job = useQuery({
    queryKey: ['jobs', jobId],
    queryFn: () => api<Job>(`/jobs/${jobId}`),
    enabled: !!jobId,
    refetchInterval: (q) =>
      q.state.data?.data.state === 'succeeded' || q.state.data?.data.state === 'failed' ? false : 1200,
  })
  const interest = useQuery({
    queryKey: ['interest'],
    queryFn: () => api<InterestProfile>('/interest-profile'),
    enabled: job.data?.data.state === 'succeeded',
    retry: false,
  })

  const consentAndScan = useMutation({
    mutationFn: async () => {
      await api<Profile>('/me', { method: 'PATCH', body: { scan_consented: true } })
      return api<Job>('/interest-scans', { body: {} })
    },
    onSuccess: (resp) => {
      setJobId(resp.data.id)
      queryClient.invalidateQueries({ queryKey: ['me'] })
    },
  })

  const jobState = job.data?.data
  const modelInfo = freeModels.data?.data

  return (
    <Card title="Personalize from your recent work (optional)">
      <StepDots step={2} />
      <p><strong>What happens:</strong> Compass samples up to 18 recent Google Docs, Sheets, and
        Slides (max 4,000 characters each, 32,000 total) through your own Apps Script bridge, and
        sends those bounded excerpts to a <strong>verified-free</strong> OpenRouter model to suggest
        interests and a companion style.</p>
      <ul className="small">
        <li>Excerpts stay in memory — Compass never stores your file contents.</li>
        <li>Nothing sensitive is inferred (health, politics, finances, etc.).</li>
        <li>You can edit or delete everything it suggests, or skip entirely.</li>
      </ul>
      <p className="small">
        Free AI status:{' '}
        {modelInfo?.available ? (
          <>
            <span className="badge">
              scan model: {modelInfo.scan_model?.status === 'verified_free'
                ? modelInfo.scan_model.id : modelInfo.selected_model}
            </span>{' '}
            <span className="small muted">
              (verified free in the catalog — if the request itself fails, Compass falls back to
              filename-based tags and says so in the result)
            </span>
          </>
        ) : (
          <span className="badge badge-warn">Free AI temporarily unavailable — Compass will use
            filename-based suggestions instead</span>
        )}
      </p>

      {!jobId && (
        <div className="row">
          <button className="primary" onClick={() => consentAndScan.mutate()}
            disabled={consentAndScan.isPending}>I consent — start the scan</button>
          <button onClick={() => navigate('/onboarding/companion')}>Skip the scan</button>
        </div>
      )}
      <ErrorNote error={consentAndScan.error} />

      {jobId && jobState && jobState.state !== 'succeeded' && jobState.state !== 'failed' && (
        <div>
          <p aria-busy="true">Scanning… {Math.round((jobState.progress ?? 0) * 100)}%</p>
          <div className="meter-track"><div className="meter-fill"
            style={{ width: `${(jobState.progress ?? 0) * 100}%` }} /></div>
        </div>
      )}
      {jobState?.state === 'failed' && (
        <ErrorNote error={new Error(`Scan failed (${jobState.error_code ?? 'unknown'}). You can skip or retry.`)} />
      )}
      {jobState?.state === 'succeeded' && interest.data && (
        <div>
          <h3>Suggested interests</h3>
          <div className="row">
            {interest.data.data.topics.map((t) => (
              <span key={t.label} className="badge">{t.label}</span>
            ))}
          </div>
          <p className="small muted">{interest.data.data.explanation}</p>
          <button className="primary" onClick={() => navigate('/onboarding/companion')}>
            Review & pick my companion
          </button>
        </div>
      )}
    </Card>
  )
}
