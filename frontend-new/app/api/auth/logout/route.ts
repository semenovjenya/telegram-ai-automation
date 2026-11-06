import { NextRequest, NextResponse } from 'next/server'
import { backendRequest } from '@/lib/server/backend'
import {
  clearSessionCookie,
  isSameOriginRequest,
  SESSION_COOKIE_NAME,
} from '@/lib/server/security'

export const runtime = 'nodejs'

function json(body: object, status = 200): NextResponse {
  return NextResponse.json(body, {
    status,
    headers: { 'Cache-Control': 'no-store' },
  })
}

export async function POST(request: NextRequest): Promise<NextResponse> {
  if (!isSameOriginRequest(request)) {
    return json({ error: 'Cross-origin request rejected' }, 403)
  }

  const token = request.cookies.get(SESSION_COOKIE_NAME)?.value
  if (token) {
    try {
      await backendRequest('auth/logout', {
        method: 'POST',
        token,
        timeoutMs: 10_000,
      })
    } catch {
      // Local logout must still succeed when the upstream service is unavailable.
    }
  }

  const response = json({ authenticated: false })
  clearSessionCookie(response, request)
  return response
}
