import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '../api/client'
import type { ProviderState } from '../api/types'
import { Card, ErrorNote } from './ui'
import { PixelIcon } from './PixelIcon'

/** Bring your own key.
 *
 *  An installed copy of Compass has no .env to edit, so the OpenRouter key is
 *  entered here and encrypted at rest like every other credential. A source
 *  checkout can still set OPENROUTER_API_KEY instead, and this panel says which
 *  of the two is in force rather than leaving it ambiguous. */
export function OpenRouterSetup() {
  const queryClient = useQueryClient()
  const [key, setKey] = useState('')

  const state = useQuery({
    queryKey: ['providers'],
    queryFn: () => api<ProviderState>('/providers'),
  })
  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ['providers'] })
    queryClient.invalidateQueries({ queryKey: ['free-models'] })
  }
  const save = useMutation({
    mutationFn: () => api('/providers/openrouter', { method: 'PUT', body: { api_key: key } }),
    onSuccess: () => { setKey(''); invalidate() },
  })
  const clear = useMutation({
    mutationFn: () => api('/providers/openrouter', { method: 'DELETE' }),
    onSuccess: invalidate,
  })

  const or = state.data?.data.openrouter
  const configured = !!or?.configured
  const fromEnv = !!or?.from_env

  return (
    <Card
      title="AI key"
      status={[configured ? (fromEnv ? 'From environment' : 'Your key') : 'Not set',
        'Free models only']}
    >
      <p>Compass only ever calls models that are verified free at the moment of the call, so a
        key costs nothing to use here. Get one at{' '}
        <a href="https://openrouter.ai/keys" target="_blank" rel="noreferrer">openrouter.ai/keys</a>.</p>

      {configured && fromEnv && (
        <p className="small">A key is set in this deployment&apos;s environment and is being used.
          Saving your own below overrides it for this profile only.</p>
      )}
      {configured && !fromEnv && (
        <div className="row" style={{ marginBottom: 12 }}>
          <span className="badge badge-verified">Key saved · {or?.token_hint}</span>
          <button className="danger" onClick={() => clear.mutate()} disabled={clear.isPending}>
            Remove key
          </button>
        </div>
      )}
      {!configured && (
        <p className="small">Without a key Compass still runs: goals get a local plan instead of
          a model-written one, and steps close on your own confirmation. Nothing is ever sent to
          a paid model.</p>
      )}

      <label htmlFor="or-key">OpenRouter API key</label>
      <input id="or-key" type="password" value={key} onChange={(e) => setKey(e.target.value)}
        placeholder="sk-or-v1-…" autoComplete="off" spellCheck={false} />
      <p className="small">Checked against OpenRouter before it is saved, then encrypted at rest.
        It is never shown again in full and never leaves this machine except to OpenRouter.</p>
      <div className="row">
        <button className="primary" onClick={() => save.mutate()}
          disabled={save.isPending || !key.trim()}>
          <PixelIcon name="plug" /> {save.isPending ? 'Checking the key…' : 'Save key'}
        </button>
      </div>
      <ErrorNote error={save.error || clear.error} />
    </Card>
  )
}
