import { NextRequest, NextResponse } from 'next/server'
import { backendRequest } from '@/lib/server/backend'
import {
  clearSessionCookie,
  SESSION_COOKIE_NAME,
} from '@/lib/server/security'
import { SYNTHETIC_BARTER_CHANNELS } from './synthetic-fixture'

export const runtime = 'nodejs'

function json(body: object, status = 200): NextResponse {
  return NextResponse.json(body, {
    status,
    headers: { 'Cache-Control': 'private, no-store' },
  })
}

function isCrossSiteBrowserRequest(request: NextRequest): boolean {
  const fetchSite = request.headers.get('sec-fetch-site')
  return fetchSite !== null && fetchSite !== 'same-origin' && fetchSite !== 'none'
}

export async function GET(request: NextRequest): Promise<NextResponse> {
  if (isCrossSiteBrowserRequest(request)) {
    return json({ error: 'Cross-origin request rejected' }, 403)
  }

  const token = request.cookies.get(SESSION_COOKIE_NAME)?.value
  if (!token) {
    return json({ error: 'Authentication required' }, 401)
  }

  try {
    const session = await backendRequest('auth/me', {
      method: 'GET',
      token,
      headers: { Accept: 'application/json' },
      timeoutMs: 10_000,
    })

    if (session.status === 401 || session.status === 403) {
      const response = json({ error: 'Authentication required' }, 401)
      clearSessionCookie(response, request)
      return response
    }

    if (!session.ok) {
      return json({ error: 'Session service is unavailable' }, 502)
    }

    const dataSource = process.env.DASHBOARD_DATA_SOURCE?.trim().toLowerCase()
    if (dataSource !== 'synthetic-demo') {
      return json({
        channels: [],
        count: 0,
        error: 'Live recommendation source is not configured',
        source: {
          type: 'live_unconfigured',
          synthetic: false,
          provenance: 'none',
        },
      }, 503)
    }

    return json({
      channels: SYNTHETIC_BARTER_CHANNELS,
      count: SYNTHETIC_BARTER_CHANNELS.length,
      source: {
        type: 'synthetic_fixture',
        synthetic: true,
        provenance: 'bundled-public-demo',
      },
    })
  } catch {
    return json({ error: 'Session service is unavailable' }, 502)
  }
}
