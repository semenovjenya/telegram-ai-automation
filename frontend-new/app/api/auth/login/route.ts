import { NextRequest, NextResponse } from 'next/server'
import {
  backendErrorMessage,
  backendRequest,
  readJson,
} from '@/lib/server/backend'
import { isSameOriginRequest, setSessionCookie } from '@/lib/server/security'
import {
  buildLoginClientClaimHeaders,
  canonicalLoginUsername,
  getOrCreateLoginClientId,
  setLoginClientCookie,
} from '@/lib/server/login-client'
import {
  readJsonRequestBody,
  RequestBodyTooLargeError,
} from '@/lib/server/request-body'

export const runtime = 'nodejs'

const MAX_LOGIN_BODY_BYTES = 8 * 1024
const MAX_TOKEN_LENGTH = 4_096

interface LoginBody {
  username: string
  password: string
}

function validLoginBody(value: unknown): value is LoginBody {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    return false
  }
  const body = value as Record<string, unknown>
  return (
    typeof body.username === 'string' &&
    body.username.trim().length > 0 &&
    [...body.username.trim()].length <= 128 &&
    Buffer.byteLength(body.username.trim(), 'utf8') <= 512 &&
    !/[\u0000-\u001f\u007f]/.test(body.username) &&
    typeof body.password === 'string' &&
    body.password.length > 0 &&
    body.password.length <= 1_024
  )
}

function json(
  body: object,
  status = 200,
  headers: Record<string, string> = {}
): NextResponse {
  return NextResponse.json(body, {
    status,
    headers: { ...headers, 'Cache-Control': 'no-store' },
  })
}

function retryAfterHeader(upstream: Response): Record<string, string> {
  const value = upstream.headers.get('retry-after') || ''
  return /^[1-9][0-9]{0,5}$/.test(value) ? { 'Retry-After': value } : {}
}

export async function POST(request: NextRequest): Promise<NextResponse> {
  if (!isSameOriginRequest(request)) {
    return json({ error: 'Cross-origin request rejected' }, 403)
  }

  if (!request.headers.get('content-type')?.toLowerCase().includes('application/json')) {
    return json({ error: 'Content-Type must be application/json' }, 415)
  }

  let body: unknown
  try {
    body = await readJsonRequestBody(request, MAX_LOGIN_BODY_BYTES)
  } catch (error) {
    if (error instanceof RequestBodyTooLargeError) {
      return json({ error: 'Request body is too large' }, 413)
    }
    return json({ error: 'Invalid JSON body' }, 400)
  }

  if (!validLoginBody(body)) {
    return json({ error: 'Username and password are required' }, 400)
  }

  let username: string
  let clientId: string
  try {
    username = canonicalLoginUsername(body.username)
    clientId = getOrCreateLoginClientId(request)
  } catch {
    return json({ error: 'Username and password are required' }, 400)
  }

  const loginResponse = (
    responseBody: object,
    responseStatus = 200,
    headers: Record<string, string> = {}
  ): NextResponse => {
    const response = json(responseBody, responseStatus, headers)
    setLoginClientCookie(response, request, clientId)
    return response
  }

  try {
    const claimHeaders = buildLoginClientClaimHeaders(clientId, username)
    const upstream = await backendRequest('auth/login', {
      method: 'POST',
      headers: {
        Accept: 'application/json',
        'Content-Type': 'application/json',
        ...claimHeaders,
      },
      body: JSON.stringify({ username, password: body.password }),
      timeoutMs: 10_000,
    })

    if (upstream.status >= 300 && upstream.status < 400) {
      return loginResponse({
        error: 'Authentication service returned an invalid redirect',
      }, 502)
    }

    const payload = await readJson(upstream)
    if (!upstream.ok) {
      const status = [400, 401, 429].includes(upstream.status) ? upstream.status : 502
      return loginResponse({
        error: backendErrorMessage(payload, 'Authentication failed'),
      }, status, upstream.status === 429 ? retryAfterHeader(upstream) : {})
    }

    const token = payload.access_token
    if (
      typeof token !== 'string' ||
      token.length === 0 ||
      token.length > MAX_TOKEN_LENGTH ||
      /[\u0000-\u001f\u007f]/.test(token)
    ) {
      return loginResponse({
        error: 'Authentication service returned an invalid session',
      }, 502)
    }

    const response = json({
      authenticated: true,
      user: payload.user || null,
    })
    setSessionCookie(response, request, token)
    setLoginClientCookie(response, request, clientId)
    return response
  } catch {
    return loginResponse({ error: 'Authentication service is unavailable' }, 502)
  }
}
