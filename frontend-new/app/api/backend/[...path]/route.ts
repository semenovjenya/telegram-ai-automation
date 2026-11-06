import { NextRequest, NextResponse } from 'next/server'
import { backendRequest, normalizeProxyPath } from '@/lib/server/backend'
import {
  clearSessionCookie,
  isSameOriginRequest,
  SESSION_COOKIE_NAME,
} from '@/lib/server/security'
import {
  readRequestBody,
  RequestBodyTooLargeError,
} from '@/lib/server/request-body'

export const runtime = 'nodejs'

const MAX_REQUEST_BODY_BYTES = 1024 * 1024
const BODY_METHODS = new Set(['POST', 'PUT', 'PATCH', 'DELETE'])

interface RouteContext {
  params: Promise<{ path: string[] }>
}

function json(body: object, status: number): NextResponse {
  return NextResponse.json(body, {
    status,
    headers: { 'Cache-Control': 'no-store' },
  })
}

async function proxy(request: NextRequest, context: RouteContext): Promise<NextResponse> {
  if (!isSameOriginRequest(request)) {
    return json({ error: 'Cross-origin request rejected' }, 403)
  }

  const token = request.cookies.get(SESSION_COOKIE_NAME)?.value
  if (!token) {
    return json({ error: 'Authentication required' }, 401)
  }

  let path: string
  try {
    path = normalizeProxyPath((await context.params).path)
  } catch {
    return json({ error: 'Unsupported backend route' }, 404)
  }

  const headers = new Headers()
  for (const name of ['accept', 'content-type']) {
    const value = request.headers.get(name)
    if (value) {
      headers.set(name, value)
    }
  }

  let body: ArrayBuffer | undefined
  if (BODY_METHODS.has(request.method)) {
    try {
      body = await readRequestBody(request, MAX_REQUEST_BODY_BYTES)
    } catch (error) {
      if (!(error instanceof RequestBodyTooLargeError)) {
        throw error
      }
      return json({ error: 'Request body is too large' }, 413)
    }
  }

  try {
    const upstream = await backendRequest(path, {
      method: request.method,
      token,
      search: request.nextUrl.search,
      headers,
      body,
    })

    if (upstream.status >= 300 && upstream.status < 400) {
      return json({ error: 'Backend returned an invalid redirect' }, 502)
    }

    const responseHeaders = new Headers({ 'Cache-Control': 'no-store' })
    for (const name of ['content-type', 'content-disposition']) {
      const value = upstream.headers.get(name)
      if (value) {
        responseHeaders.set(name, value)
      }
    }

    const response = new NextResponse(
      upstream.status === 204 ? null : await upstream.arrayBuffer(),
      { status: upstream.status, headers: responseHeaders }
    )
    if (upstream.status === 401 || upstream.status === 403) {
      clearSessionCookie(response, request)
    }
    return response
  } catch {
    return json({ error: 'Backend service is unavailable' }, 502)
  }
}

export const GET = proxy
export const POST = proxy
export const PUT = proxy
export const PATCH = proxy
export const DELETE = proxy
