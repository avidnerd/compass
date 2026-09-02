import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useMutation, useQuery } from '@tanstack/react-query'
import { api } from '../api/client'
import type { ConnectorState, ProviderState } from '../api/types'
import { Card, CONNECTOR_LABELS, ErrorNote, Spinner } from '../components/ui'
import { ProviderSetup } from '../components/ProviderSetup'
import { CanvasSetup } from '../components/CanvasSetup'
import { OpenRouterSetup } from '../components/OpenRouterSetup'
import { PixelIcon } from '../components/PixelIcon'
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
              <span className={`badge ${c.status === 'connected' ? 'badge-verified'
                : c.status !== 'connected' ? 'badge-warn' : ''}`}>
                {c.status}
              </span>
            </span>
            <span className="small">
              {/* Canvas is its own feed, not a bridge capability — saying
                  "set up the bridge" here would send people the wrong way. */}
              {c.connector === 'canvas'
                ? (c.status === 'connected' ? 'via calendar feed' : 'paste your feed URL below')
                : !onBridge
                  ? 'set up the bridge below'
                  : c.connector === 'github' && c.status !== 'connected'
                    ? 'add a token below'
                    : c.status === 'unsupported' ? 'not on this path' : 'via bridge'}
            </span>
          </div>
        ))}
      </div>
      <div className="row" style={{ marginTop: 12 }}>
        <button onClick={() => recheck.mutate()} disabled={recheck.isPending}>
          <PixelIcon name="refresh" /> {recheck.isPending ? 'Rechecking…' : 'Recheck status'}
        </button>
      </div>
    </>
  )
}

/** Connecting accounts is the highest-friction step in Compass, and it is not
 *  required to get value. Students abandon tools that demand setup before they
 *  see anything work, so this step leads with the path that starts now and
 *  treats the bridge as an upgrade the user can take whenever they want. */
export function OnboardingConnect() {
  const navigate = useNavigate()
  const [showSetup, setShowSetup] = useState(false)

  const providers = useQuery({
    queryKey: ['providers'],
    queryFn: () => api<ProviderState>('/providers'),
    retry: false,
  })
  const connected = providers.data?.data.active === 'bridge'

  return (
    <>
      <Card
        title="Connect your accounts"
        status={[connected ? 'Bridge connected' : 'Nothing connected yet', 'Optional']}
      >
        <StepDots step={1} />

        <p><strong>You can skip this and start now.</strong> Compass works straight away:
          set a goal, break it into steps, and run focus sessions. You confirm each step
          yourself when it is done.</p>

        <p>Connecting your own Google and GitHub accounts changes one thing — Compass can
          then <em>check</em> that a step really happened, instead of taking your word for it.
          That is the whole point of the product, so it is worth doing, just not necessarily
          right now.</p>

        <p>There is one exception worth doing immediately: <strong>Canvas</strong> takes about
          thirty seconds and needs no token and no admin. It brings in your real assignment
          deadlines, so your quests start from work you actually owe.</p>

        <div className="grid-2" style={{ marginTop: 4 }}>
          <div>
            <h3>Without connecting</h3>
            {/* Capabilities, not evidence — so these carry no stamp. */}
            <div className="log">
              {['Quests and subgoals', 'Focus sessions and the timer',
                'Your companion and its growth', 'Focus rooms'].map((t) => (
                <div key={t} className="log-row">
                  <span className="log-box"><PixelIcon name="check" size={12} /></span>
                  <span className="log-what"><strong>{t}</strong></span>
                </div>
              ))}
              <div className="log-row">
                <span className="log-box" />
                <span className="log-what"><strong>Steps marked done</strong>
                  <small>on your word</small></span>
              </div>
            </div>
          </div>
          <div>
            <h3>After connecting</h3>
            <div className="log">
              {[['A file you actually edited', 'Drive · Docs · Sheets · Slides'],
                ['An email you actually sent', 'Gmail'],
                ['A commit or a merged PR', 'GitHub'],
                ['A calendar block you kept', 'Calendar']].map(([t, src]) => (
                <div key={t} className="log-row">
                  <span className="log-box verified"><PixelIcon name="check" size={12} /></span>
                  <span className="log-what"><strong>{t}</strong><small>{src}</small></span>
                </div>
              ))}
            </div>
            <p className="small" style={{ marginTop: 8 }}>
              A <span className="stamp-legend"><PixelIcon name="check" size={12} /></span>{' '}
              mark anywhere in Compass means a machine checked it. Nothing else is ever
              printed in that ink.
            </p>
            <p className="small">
              Read-only, and it runs in your own Google account — nothing is sent to us,
              because there is no us to send it to. Budget about 10 minutes.
            </p>
          </div>
        </div>
      </Card>

      <div className="row" style={{ marginTop: 4 }}>
        <button className="primary" onClick={() => navigate('/onboarding/companion')}>
          <PixelIcon name="right" /> Start now, connect later
        </button>
        <button onClick={() => setShowSetup((v) => !v)} aria-expanded={showSetup}>
          {showSetup ? 'Hide setup' : 'Set up the connection now'}
        </button>
        {connected && (
          <button onClick={() => navigate('/onboarding/scan')}>Continue to the scan</button>
        )}
      </div>

      <CanvasSetup />
      <OpenRouterSetup />

      {showSetup && (
        <>
          <Card title="Connection status">
            <ConnectorList />
          </Card>
          <ProviderSetup />
          <div className="row" style={{ marginTop: 4 }}>
            <button className="primary" onClick={() => navigate('/onboarding/scan')}>
              Done — continue
            </button>
          </div>
        </>
      )}
    </>
  )
}
