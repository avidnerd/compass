import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '../api/client'
import type { ProviderState } from '../api/types'
import { Card, ErrorNote, Spinner } from './ui'

/**
 * Setup for the data plane: a read-only Apps Script Web App the user deploys in
 * their own Google account, plus a GitHub token.
 */
export function ProviderSetup({ compact = false }: { compact?: boolean }) {
  const queryClient = useQueryClient()
  const [url, setUrl] = useState('')
  const [token, setToken] = useState('')
  const [ghToken, setGhToken] = useState('')
  const [saved, setSaved] = useState<string | null>(null)

  const state = useQuery({
    queryKey: ['providers'],
    queryFn: () => api<ProviderState>('/providers'),
  })

  const invalidateAll = () => {
    queryClient.invalidateQueries({ queryKey: ['providers'] })
    queryClient.invalidateQueries({ queryKey: ['connections'] })
    queryClient.invalidateQueries({ queryKey: ['college'] })
    queryClient.invalidateQueries({ queryKey: ['college-status'] })
  }

  const saveBridge = useMutation({
    mutationFn: () => api<ProviderState>('/providers/bridge', { method: 'PUT', body: { url, token } }),
    onSuccess: (resp) => {
      setSaved(`Bridge connected — ${resp.data.handshake?.capabilities.length ?? 0} capabilities available.`)
      setUrl('')
      setToken('')
      invalidateAll()
    },
  })

  const clearBridge = useMutation({
    mutationFn: () => api<ProviderState>('/providers/bridge', { method: 'DELETE' }),
    onSuccess: () => { setSaved(null); invalidateAll() },
  })

  const saveGithub = useMutation({
    mutationFn: () => api<ProviderState>('/providers/github', { method: 'PUT', body: { token: ghToken } }),
    onSuccess: () => { setSaved('GitHub token accepted.'); setGhToken(''); invalidateAll() },
  })

  const clearGithub = useMutation({
    mutationFn: () => api<ProviderState>('/providers/github', { method: 'DELETE' }),
    onSuccess: () => invalidateAll(),
  })

  if (state.isPending) return <Spinner label="Checking your data provider…" />
  if (state.isError) return <ErrorNote error={state.error} />

  const data = state.data.data
  const onBridge = data.active === 'bridge'

  return (
    <Card title={compact ? undefined : 'Where Compass reads your data'}>
      <p className="row" style={{ marginTop: 0 }}>
        <span className={`badge ${onBridge ? '' : 'badge-warn'}`}>
          {onBridge ? 'Apps Script bridge (free)' : 'no provider configured'}
        </span>
      </p>

      {data.bridge.configured ? (
        <div className="list-item">
          <span>
            <strong>Apps Script bridge</strong> — connected
            {data.bridge.from_env && <span className="small muted"> (from .env)</span>}
            <br />
            <span className="small muted">
              token {data.bridge.token_hint}
              {data.bridge.status === 'error' && ` · last check failed: ${data.bridge.error_code}`}
            </span>
          </span>
          <button className="danger" onClick={() => clearBridge.mutate()} disabled={clearBridge.isPending}>
            Disconnect
          </button>
        </div>
      ) : (
        <>
          <p className="muted">
            Deploy <code>college-os/bridge/api.gs</code> as a Web App in your own Google account and
            paste its details here. It runs under your own read-only OAuth grant — no connector
            platform, no Google Cloud project, no cost.
          </p>
          <ol className="small">
            <li>New Apps Script project → paste <code>bridge/api.gs</code> and its manifest.</li>
            <li>Run <code>setUpBridge</code> and copy the token it logs.</li>
            <li>Deploy → New deployment → <strong>Web app</strong>, Execute as <strong>Me</strong>,
              Who has access <strong>Anyone</strong>. Copy the <code>/exec</code> URL.</li>
          </ol>
          <label htmlFor="bridge-url">Web App URL</label>
          <input id="bridge-url" value={url} onChange={(e) => setUrl(e.target.value)}
            placeholder="https://script.google.com/macros/s/…/exec" style={{ width: '100%' }} />
          <label htmlFor="bridge-token">Bridge token</label>
          <input id="bridge-token" type="password" value={token} autoComplete="off"
            onChange={(e) => setToken(e.target.value)} style={{ width: '100%' }} />
          <div className="row" style={{ marginTop: '0.6rem' }}>
            <button className="primary" disabled={!url.trim() || !token.trim() || saveBridge.isPending}
              onClick={() => saveBridge.mutate()}>
              {saveBridge.isPending ? 'Verifying…' : 'Connect bridge'}
            </button>
          </div>
          <p className="small muted">
            Compass verifies the deployment before saving anything, and never sends the URL or token
            back to the browser afterwards.
          </p>
        </>
      )}
      <ErrorNote error={saveBridge.error || clearBridge.error} />

      <h3 style={{ marginTop: '1rem' }}>GitHub</h3>
      {data.github.configured ? (
        <div className="list-item">
          <span>
            Token {data.github.token_hint} accepted
            {data.github.from_env && <span className="small muted"> (from .env)</span>}
          </span>
          <button className="danger" onClick={() => clearGithub.mutate()} disabled={clearGithub.isPending}>
            Remove
          </button>
        </div>
      ) : (
        <>
          <p className="small muted">
            Optional. A fine-grained personal access token with read-only repository access lets
            Compass verify commits and merged PRs. GitHub charges nothing for it.
          </p>
          <input aria-label="GitHub token" type="password" value={ghToken} autoComplete="off"
            onChange={(e) => setGhToken(e.target.value)} placeholder="github_pat_… or ghp_…"
            style={{ width: '100%' }} />
          <div className="row" style={{ marginTop: '0.5rem' }}>
            <button disabled={!ghToken.trim() || saveGithub.isPending} onClick={() => saveGithub.mutate()}>
              {saveGithub.isPending ? 'Verifying…' : 'Save GitHub token'}
            </button>
          </div>
        </>
      )}
      <ErrorNote error={saveGithub.error || clearGithub.error} />
      {saved && <p className="small" role="status">{saved}</p>}

      {onBridge && (
        <p className="small muted" style={{ marginBottom: 0 }}>
          Google Meet is unavailable on this path — its API needs a Google Cloud project, which is
          the cost the bridge avoids. Compass reports it as unsupported rather than pretending.
        </p>
      )}
    </Card>
  )
}
