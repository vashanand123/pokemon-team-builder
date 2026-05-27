// Thin fetch wrapper. All calls go through the backend (same-origin via the Vite
// proxy in dev, nginx in the container), with credentials so the session cookie is sent.
//
// We surface the HTTP status code via `HttpError` so the auth flow (useMe / login
// guards) can tell a 401 ("show the login overlay") apart from a 500 ("something
// is on fire").

export class HttpError extends Error {
  readonly status: number
  readonly detail?: string
  constructor(status: number, message: string, detail?: string) {
    super(message)
    this.status = status
    this.detail = detail
  }
}

async function _toError(res: Response, method: string, url: string): Promise<never> {
  // Best-effort to read a JSON `detail` (FastAPI's convention); fall back to text.
  let detail: string | undefined
  try {
    const body = await res.json()
    detail = typeof body?.detail === 'string' ? body.detail : undefined
  } catch {
    // not JSON — leave detail undefined
  }
  throw new HttpError(res.status, `${method} ${url} -> ${res.status}`, detail)
}

export async function fetchJson<T>(path: string): Promise<T> {
  const res = await fetch(path, { credentials: 'include' })
  if (!res.ok) await _toError(res, 'GET', path)
  return res.json() as Promise<T>
}

// Mutations (POST/PUT/DELETE): same-origin + credentials, a JSON body when present,
// and a 204 No Content parses to undefined.
export async function mutateJson<T>(
  url: string,
  method: string,
  body?: unknown,
): Promise<T> {
  const res = await fetch(url, {
    method,
    credentials: 'include',
    headers: body ? { 'Content-Type': 'application/json' } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  })
  if (!res.ok) await _toError(res, method, url)
  return (res.status === 204 ? undefined : await res.json()) as T
}
