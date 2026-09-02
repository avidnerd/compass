import { Link } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '../api/client'
import type { FreeModelStatus } from '../api/types'
import { ResetButton } from '../components/ResetButton'
import { Card, ErrorNote } from '../components/ui'
import { ProviderSetup } from '../components/ProviderSetup'
import { CanvasSetup } from '../components/CanvasSetup'
import { OpenRouterSetup } from '../components/OpenRouterSetup'
import { ConnectorList } from './OnboardingConnect'

export function SettingsConnections() {
  const queryClient = useQueryClient()
  const freeModels = useQuery({
    queryKey: ['free-models'],
    queryFn: () => api<FreeModelStatus>('/system/free-models'),
  })
  const invalidate = useMutation({
    mutationFn: (connector: string) =>
      api<{ invalidated_rows: number }>(`/cache/${connector}:invalidate`, { body: {} }),
    onSuccess: () => queryClient.invalidateQueries(),
  })

  const fm = freeModels.data?.data

  return (
    <>
      <div className="row spread">
        <h1>Settings — Connections</h1>
        <ResetButton className="danger" />
      </div>
      <p className="row small">
        <Link to="/settings/connections">Connections</Link> ·
        <Link to="/settings/privacy">Privacy</Link> ·
        <Link to="/settings/gameplay">Gameplay</Link>
      </p>
      <Card title="Connected apps">
        <ConnectorList />
      </Card>
      <ProviderSetup />
      <OpenRouterSetup />
      <CanvasSetup />
      <Card title="Connector caches">
        <p className="small muted">Clearing a connector's cache bumps its generation; analytics
          recompute lazily. Manual refresh is rate-limited to once per minute per connector.</p>
        <div className="row">
          {['google_calendar', 'google_drive', 'gmail', 'google_meet', 'github'].map((c) => (
            <button key={c} onClick={() => invalidate.mutate(c)} disabled={invalidate.isPending}>
              Clear {c.replace('google_', '')}
            </button>
          ))}
        </div>
        <ErrorNote error={invalidate.error} />
      </Card>
      <Card title="Free AI status">
        {fm && (
          <>
            <p>
              {fm.auth_state === 'failed'
                ? <span className="badge badge-warn">Your OpenRouter key was rejected by the
                    completions API — check OPENROUTER_API_KEY in .env. Compass runs on local
                    fallbacks meanwhile and will never switch to a paid model.</span>
                : fm.available
                  ? <>Active model: <code>{fm.selected_model}</code> <span className="badge">verified free</span></>
                  : <span className="badge badge-warn">Free AI temporarily unavailable — Compass
                      runs on transparent local fallbacks. It will never switch to a paid model.</span>}
            </p>
            <table className="simple">
              <thead><tr><th>Model</th><th>Status</th></tr></thead>
              <tbody>
                {fm.models.map((m) => (
                  <tr key={m.id}><td><code>{m.id}</code></td><td>{m.status}</td></tr>
                ))}
                {fm.scan_model && (
                  <tr><td><code>{fm.scan_model.id}</code> <span className="small muted">(interest scan)</span></td>
                    <td>{fm.scan_model.status}</td></tr>
                )}
              </tbody>
            </table>
            <p className="small muted">Every candidate must end in <code>:free</code>, report zero
              prompt and completion pricing, and support structured outputs. Anything else —
              including <code>openrouter/auto</code> — is rejected before a request is made.</p>
          </>
        )}
      </Card>
    </>
  )
}
