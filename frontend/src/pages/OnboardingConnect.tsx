import { useNavigate } from 'react-router-dom'
import { useMutation, useQuery } from '@tanstack/react-query'
import { api } from '../api/client'
import type { ConnectorState, ProviderState } from '../api/types'
import { Card, CONNECTOR_LABELS, ErrorNote, Spinner } from '../components/ui'
import { ProviderSetup } from '../components/ProviderSetup'
import { StepDots } from './OnboardingProfile'

export function ConnectorList() {
  const connections = useQuery({
    queryKey: ['connections'],
    queryFn: () => api<ConnectorState[]>('/connections'),
  })
  const providers = useQuery({
    queryKey: ['providers'],
    queryFn: () => api<ProviderState>('/providers'),
  })
  const recheck = useMutation({
    mutationFn: () => api<ConnectorState[]>('/connections?refresh=true'),
    onSuccess: () => connections.refetch(),
  })

  if (connections.isPending) return <Spinner label="Checking connections…" />
  if (connections.isError) return <ErrorNote error={connections.error} />

  // One Apps Script deployment covers every Google connector, so there is
  // nothing to link per connector — a connector is either served or it isn't.
  const onBridge = providers.data?.data.active === 'bridge'

  return (
    <>
      <div>
        {connections.data.data.map((c) => (
          <div key={c.connector} className="list-item">
            <span>
              {CONNECTOR_LABELS[c.connector] ?? c.connector}{' '}
              <span className={`badge ${c.status !== 'connected' ? 'badge-warn' : ''}`}>
                {c.status}
              </span>
            </span>
            <span className="small muted">
              {!onBridge
                ? 'set up the bridge below'
                : c.connector === 'github' && c.status !== 'connected'
                  ? 'add a token below'
                  : c.status === 'unsupported' ? 'not on this path' : 'via bridge'}
            </span>
          </div>
        ))}
      </div>
      <div className="row" style={{ marginTop: '0.8rem' }}>
        <button onClick={() => recheck.mutate()} disabled={recheck.isPending}>
          {recheck.isPending ? 'Rechecking…' : 'Recheck status'}
        </button>
      </div>
    </>
  )
}

export function OnboardingConnect() {
  const navigate = useNavigate()
  return (
    <>
      <Card title="Connect your work apps">
        <StepDots step={1} />
        <p>Compass reads — never writes — from your own accounts. Deploy the free Apps Script
          bridge in your Google account below; it covers every Google connector at once. You need
          Drive plus one of Docs/Sheets/Slides for the interest scan.</p>
        <ConnectorList />
      </Card>
      <ProviderSetup />
      <div className="row" style={{ marginTop: '1rem' }}>
        <button className="primary" onClick={() => navigate('/onboarding/scan')}>Continue</button>
        <button onClick={() => navigate('/onboarding/companion')}>Skip for now</button>
      </div>
    </>
  )
}
