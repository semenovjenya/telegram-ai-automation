import { NextRequest, NextResponse } from 'next/server'
import { backendRequest, readJson } from '@/lib/server/backend'
import {
  clearSessionCookie,
  SESSION_COOKIE_NAME,
} from '@/lib/server/security'

export const runtime = 'nodejs'

function json(body: object, status = 200): NextResponse {
  return NextResponse.json(body, {
    status,
    headers: { 'Cache-Control': 'no-store' },
  })
}

export async function GET(request: NextRequest): Promise<NextResponse> {
  const token = request.cookies.get(SESSION_COOKIE_NAME)?.value
  if (!token) {
    return json({ authenticated: false })
  }

  try {
    const upstream = await backendRequest('auth/me', {
      method: 'GET',
      token,
      headers: { Accept: 'application/json' },
      timeoutMs: 10_000,
    })

    if (upstream.ok) {
      return json({ authenticated: true, user: await readJson(upstream) })
    }

    if (upstream.status === 401 || upstream.status === 403) {
      const response = json({ authenticated: false })
      clearSessionCookie(response, request)
      return response
    }

    return json({ error: 'Session service is unavailable' }, 502)
  } catch {
    return json({ error: 'Session service is unavailable' }, 502)
  }
}
