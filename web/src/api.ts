import { clearToken, getToken } from './auth'

// Same-origin: the API is at /api on whatever host served this page (no CORS, no base URL config).
const API = '/api'

export class ApiError extends Error {
  status: number
  code: string
  constructor(status: number, code: string, message: string) {
    super(message)
    this.status = status
    this.code = code
  }
}

interface Opts {
  method?: 'GET' | 'POST' | 'PUT'
  body?: unknown
  auth?: boolean
}

export async function api<T>(path: string, { method = 'GET', body, auth = true }: Opts = {}): Promise<T> {
  const headers: Record<string, string> = {}
  if (body !== undefined) headers['Content-Type'] = 'application/json'
  const token = getToken()
  if (auth && token) headers.Authorization = `Bearer ${token}`

  let res: Response
  try {
    res = await fetch(API + path, { method, headers, body: body === undefined ? undefined : JSON.stringify(body) })
  } catch {
    throw new ApiError(0, 'network', "Can't reach the server")
  }
  let data: unknown = null
  try {
    data = await res.json()
  } catch {
    /* non-JSON error body */
  }
  if (!res.ok) {
    const err = (data as { error?: { code?: string; message?: string } } | null)?.error
    // A rejected token means this browser's account is gone (e.g. dev DB reset): sign out.
    if (res.status === 401 && auth && token) clearToken()
    throw new ApiError(res.status, err?.code ?? 'error', err?.message ?? `Request failed (${res.status})`)
  }
  return data as T
}

/** Minutes east of UTC for the viewer, matching the API's tzOffsetMin. */
export const tzOffsetMin = (): number => -new Date().getTimezoneOffset()
