const DEFAULT_DEVELOPMENT_BACKEND = 'http://localhost:8001/api'
const DEFAULT_PRODUCTION_BACKEND = 'http://auth-backend:8000/api'
const ALLOWED_PROXY_ROOTS = new Set(['dashboard', 'ai', 'chatbot'])

export function getBackendBaseUrl(): URL {
  const configured = process.env.AUTH_BACKEND_URL || (
    process.env.NODE_ENV === 'production'
      ? DEFAULT_PRODUCTION_BACKEND
      : DEFAULT_DEVELOPMENT_BACKEND
  )
  const url = new URL(configured)

  if (!['http:', 'https:'].includes(url.protocol) || url.username || url.password) {
    throw new Error('AUTH_BACKEND_URL must be an HTTP(S) URL without credentials')
  }

  url.hash = ''
  url.search = ''
  url.pathname = `${url.pathname.replace(/\/+$/, '')}/`
  return url
}

export function normalizeProxyPath(segments: string[]): string {
  if (segments.length === 0 || !ALLOWED_PROXY_ROOTS.has(segments[0])) {
    throw new Error('Unsupported backend route')
  }

  return segments.map((segment) => {
    if (
      !segment ||
      segment === '.' ||
      segment === '..' ||
      /[\\/\0]/.test(segment)
    ) {
      throw new Error('Invalid backend route')
    }
    return encodeURIComponent(segment)
  }).join('/')
}

export function createBackendUrl(path: string, search = ''): URL {
  const baseUrl = getBackendBaseUrl()
  const normalizedPath = path.replace(/^\/+/, '')
  const url = new URL(normalizedPath, baseUrl)

  if (url.origin !== baseUrl.origin || !url.pathname.startsWith(baseUrl.pathname)) {
    throw new Error('Backend URL escaped its configured base path')
  }

  url.search = search
  return url
}

interface BackendRequestOptions extends RequestInit {
  token?: string
  search?: string
  timeoutMs?: number
}

export async function backendRequest(
  path: string,
  options: BackendRequestOptions = {}
): Promise<Response> {
  const {
    token,
    search,
    timeoutMs = 30_000,
    headers: inputHeaders,
    ...requestOptions
  } = options
  const headers = new Headers(inputHeaders)

  if (token) {
    headers.set('Authorization', `Bearer ${token}`)
  }

  return fetch(createBackendUrl(path, search), {
    ...requestOptions,
    headers,
    cache: 'no-store',
    redirect: 'manual',
    signal: AbortSignal.timeout(timeoutMs),
  })
}

export async function readJson(response: Response): Promise<Record<string, unknown>> {
  const payload: unknown = await response.json().catch(() => ({}))
  return payload && typeof payload === 'object' && !Array.isArray(payload)
    ? payload as Record<string, unknown>
    : {}
}

export function backendErrorMessage(
  payload: Record<string, unknown>,
  fallback: string
): string {
  for (const key of ['detail', 'error', 'message']) {
    if (typeof payload[key] === 'string' && payload[key]) {
      return payload[key]
    }
  }
  return fallback
}
