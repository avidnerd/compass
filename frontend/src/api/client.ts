export interface Meta {
  request_id: string
  generated_at: string
  from_cache?: boolean
  stale?: boolean
  cache_expires_at?: string
}

export interface Envelope<T> {
  data: T
  meta: Meta
}

export class ApiError extends Error {
  code: string
  status: number
  constructor(status: number, code: string, message: string) {
    super(message)
    this.status = status
    this.code = code
  }
}

interface Options {
  method?: string
  body?: unknown
  idempotencyKey?: string
  ifMatch?: number
}

export async function api<T>(path: string, opts: Options = {}): Promise<Envelope<T>> {
  const headers: Record<string, string> = {}
  if (opts.body !== undefined) headers['Content-Type'] = 'application/json'
  if (opts.idempotencyKey) headers['Idempotency-Key'] = opts.idempotencyKey
  if (opts.ifMatch !== undefined) headers['If-Match'] = String(opts.ifMatch)
  const resp = await fetch(`/api/v1${path}`, {
    method: opts.method ?? (opts.body !== undefined ? 'POST' : 'GET'),
    headers,
    credentials: 'same-origin',
    body: opts.body !== undefined ? JSON.stringify(opts.body) : undefined,
  })
  let payload: unknown = null
  try {
    payload = await resp.json()
  } catch {
    /* non-JSON error */
  }
  if (!resp.ok) {
    const err = (payload as { error?: { code?: string; message?: string } })?.error
    throw new ApiError(resp.status, err?.code ?? 'unknown_error', err?.message ?? `Request failed (${resp.status})`)
  }
  return payload as Envelope<T>
}

/**
 * POST a document as the raw request body. Used for planning a quest from a
 * brief the user already has — sending the text as-is avoids a multipart
 * parser on the server, and the metadata rides in headers.
 */
export async function postDocument<T>(
  path: string, text: string, headers: Record<string, string> = {},
): Promise<Envelope<T>> {
  const resp = await fetch(`/api/v1${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'text/plain; charset=utf-8', ...headers },
    credentials: 'same-origin',
    body: text,
  })
  let payload: unknown = null
  try {
    payload = await resp.json()
  } catch {
    /* non-JSON error */
  }
  if (!resp.ok) {
    const err = (payload as { error?: { code?: string; message?: string } })?.error
    throw new ApiError(resp.status, err?.code ?? 'unknown_error',
      err?.message ?? `Request failed (${resp.status})`)
  }
  return payload as Envelope<T>
}

/** Stable idempotency key that survives component re-renders and retries. */
const idemKeys = new Map<string, string>()
export function idempotencyKey(scope: string): string {
  let key = idemKeys.get(scope)
  if (!key) {
    key = `${scope}-${crypto.randomUUID()}`
    idemKeys.set(scope, key)
  }
  return key
}
export function resetIdempotencyKey(scope: string) {
  idemKeys.delete(scope)
}
