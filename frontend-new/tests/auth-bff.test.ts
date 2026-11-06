import assert from 'node:assert/strict'
import { readdirSync, readFileSync, statSync } from 'node:fs'
import path from 'node:path'
import test, { afterEach } from 'node:test'
import { NextRequest } from 'next/server'
import { POST as login } from '@/app/api/auth/login/route'
import { GET as session } from '@/app/api/auth/session/route'
import { GET as barterChannels } from '@/app/api/barter/channels/route'
import { POST as proxyPost } from '@/app/api/backend/[...path]/route'
import { api } from '@/lib/api'
import { normalizeProxyPath } from '@/lib/server/backend'
import {
  isSameOriginRequest,
  SESSION_COOKIE_NAME,
} from '@/lib/server/security'
import {
  buildLoginClientClaimHeaders,
  LOGIN_CLIENT_COOKIE_NAME,
} from '@/lib/server/login-client'
import {
  readRequestBody,
  RequestBodyTooLargeError,
} from '@/lib/server/request-body'

const originalFetch = globalThis.fetch
const originalBackendUrl = process.env.AUTH_BACKEND_URL
const originalDashboardDataSource = process.env.DASHBOARD_DATA_SOURCE
const originalEnvironment = process.env.ENVIRONMENT
const originalLoginClientSigningKey = process.env.LOGIN_CLIENT_SIGNING_KEY
const originalPublicAppOrigin = process.env.PUBLIC_APP_ORIGIN

afterEach(() => {
  globalThis.fetch = originalFetch
  if (originalBackendUrl === undefined) {
    delete process.env.AUTH_BACKEND_URL
  } else {
    process.env.AUTH_BACKEND_URL = originalBackendUrl
  }
  if (originalDashboardDataSource === undefined) {
    delete process.env.DASHBOARD_DATA_SOURCE
  } else {
    process.env.DASHBOARD_DATA_SOURCE = originalDashboardDataSource
  }
  if (originalEnvironment === undefined) {
    delete process.env.ENVIRONMENT
  } else {
    process.env.ENVIRONMENT = originalEnvironment
  }
  if (originalLoginClientSigningKey === undefined) {
    delete process.env.LOGIN_CLIENT_SIGNING_KEY
  } else {
    process.env.LOGIN_CLIENT_SIGNING_KEY = originalLoginClientSigningKey
  }
  if (originalPublicAppOrigin === undefined) {
    delete process.env.PUBLIC_APP_ORIGIN
  } else {
    process.env.PUBLIC_APP_ORIGIN = originalPublicAppOrigin
  }
})

function setCookieValues(response: Response): string[] {
  const headers = response.headers as Headers & { getSetCookie?: () => string[] }
  return headers.getSetCookie?.() || [response.headers.get('set-cookie') || '']
}

function request(
  url: string,
  method: string,
  headers: Record<string, string> = {},
  body?: string
): NextRequest {
  return new NextRequest(url, { method, headers, body })
}

test('origin validation ignores spoofed forwarding headers', () => {
  process.env.ENVIRONMENT = 'development'
  delete process.env.PUBLIC_APP_ORIGIN
  assert.equal(isSameOriginRequest(request('http://app.test/api', 'POST')), false)
  assert.equal(isSameOriginRequest(request('http://app.test/api', 'GET')), true)
  assert.equal(isSameOriginRequest(request('http://app.test/api', 'POST', {
    origin: 'http://app.test',
    'sec-fetch-site': 'same-origin',
  })), true)
  assert.equal(isSameOriginRequest(request('http://app.test/api', 'POST', {
    origin: 'https://evil.test',
    'sec-fetch-site': 'cross-site',
  })), false)
  assert.equal(isSameOriginRequest(request('http://internal:7777/api', 'POST', {
    origin: 'https://analytics.example',
    'sec-fetch-site': 'same-origin',
    'x-forwarded-host': 'analytics.example',
    'x-forwarded-proto': 'https',
  })), false)
})

test('hardened origin validation requires an exact HTTPS public origin', () => {
  process.env.ENVIRONMENT = 'production'
  delete process.env.PUBLIC_APP_ORIGIN
  const externalRequest = () => request('http://internal:7777/api', 'POST', {
    origin: 'https://analytics.example',
    'sec-fetch-site': 'same-origin',
    'x-forwarded-host': 'evil.example',
    'x-forwarded-proto': 'http',
  })

  assert.equal(isSameOriginRequest(externalRequest()), false)
  process.env.PUBLIC_APP_ORIGIN = 'http://analytics.example'
  assert.equal(isSameOriginRequest(externalRequest()), false)
  process.env.PUBLIC_APP_ORIGIN = 'https://analytics.example/path'
  assert.equal(isSameOriginRequest(externalRequest()), false)
  process.env.PUBLIC_APP_ORIGIN = 'https://analytics.example'
  assert.equal(isSameOriginRequest(externalRequest()), true)
})

test('login-client HMAC contract matches the backend fixed vector', () => {
  process.env.ENVIRONMENT = 'development'
  process.env.LOGIN_CLIENT_SIGNING_KEY = (
    'login-client-test-signing-key-0123456789-ABCDEF'
  )
  const headers = buildLoginClientClaimHeaders(
    'A'.repeat(43),
    'operator',
    1_800_000_000
  )
  assert.equal(
    headers['X-Login-Client-Signature'],
    'df89576cf5d06818bc0414b40b17afb392a497f4d1b36b6d1aebf85b7224a04c'
  )
})

test('backend proxy paths are allowlisted and traversal-safe', () => {
  assert.equal(normalizeProxyPath(['dashboard', 'metrics']), 'dashboard/metrics')
  assert.equal(normalizeProxyPath(['chatbot', 'messages', '42']), 'chatbot/messages/42')
  assert.throws(() => normalizeProxyPath(['admin', 'users']), /Unsupported/)
  assert.throws(() => normalizeProxyPath(['dashboard', '..']), /Invalid/)
  assert.throws(() => normalizeProxyPath(['ai', 'bad/path']), /Invalid/)
})

test('login stores the upstream JWT only in an HttpOnly strict cookie', async () => {
  process.env.AUTH_BACKEND_URL = 'http://backend.test/api'
  process.env.ENVIRONMENT = 'development'
  process.env.LOGIN_CLIENT_SIGNING_KEY = (
    'login-client-test-signing-key-0123456789-ABCDEF'
  )
  let forwardedClientId = ''
  globalThis.fetch = (async (input, init) => {
    assert.equal(String(input), 'http://backend.test/api/auth/login')
    assert.equal(init?.method, 'POST')
    const headers = new Headers(init?.headers)
    forwardedClientId = headers.get('x-login-client-id') || ''
    assert.match(forwardedClientId, /^[A-Za-z0-9_-]{43}$/)
    const timestamp = Number(headers.get('x-login-client-timestamp'))
    assert.ok(Number.isInteger(timestamp))
    const expected = buildLoginClientClaimHeaders(
      forwardedClientId,
      'demo',
      timestamp
    )
    for (const [name, value] of Object.entries(expected)) {
      assert.equal(headers.get(name), value)
    }
    return new Response(JSON.stringify({
      access_token: 'server-only.jwt.value',
      token_type: 'bearer',
      user: { id: 1, username: 'demo', saas_user_id: 1 },
    }), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    })
  }) as typeof fetch

  const response = await login(request('https://app.test/api/auth/login', 'POST', {
    origin: 'https://app.test',
    'sec-fetch-site': 'same-origin',
    'content-type': 'application/json',
  }, JSON.stringify({ username: 'demo', password: 'correct horse' })))

  assert.equal(response.status, 200)
  const payload = await response.json()
  assert.deepEqual(payload, {
    authenticated: true,
    user: { id: 1, username: 'demo', saas_user_id: 1 },
  })
  assert.equal(JSON.stringify(payload).includes('server-only.jwt.value'), false)

  const setCookie = response.headers.get('set-cookie') || ''
  assert.match(setCookie, new RegExp(`^${SESSION_COOKIE_NAME}=server-only\\.jwt\\.value`))
  assert.match(setCookie, /HttpOnly/i)
  assert.match(setCookie, /Secure/i)
  assert.match(setCookie, /SameSite=strict/i)
  assert.match(setCookie, /Path=\//i)

  const loginClientCookie = setCookieValues(response)
    .find((value) => value.startsWith(`${LOGIN_CLIENT_COOKIE_NAME}=`)) || ''
  assert.match(
    loginClientCookie,
    new RegExp(`^${LOGIN_CLIENT_COOKIE_NAME}=${forwardedClientId}`)
  )
  assert.match(loginClientCookie, /HttpOnly/i)
  assert.match(loginClientCookie, /Secure/i)
  assert.match(loginClientCookie, /SameSite=strict/i)
  assert.match(loginClientCookie, /Path=\/api\/auth\/login/i)
  assert.match(loginClientCookie, /Max-Age=2592000/i)
})

test('login reuses an opaque cookie and binds the claim to canonical username', async () => {
  process.env.AUTH_BACKEND_URL = 'http://backend.test/api'
  process.env.ENVIRONMENT = 'development'
  process.env.LOGIN_CLIENT_SIGNING_KEY = (
    'login-client-test-signing-key-0123456789-ABCDEF'
  )
  const clientId = 'D'.repeat(43)

  globalThis.fetch = (async (_input, init) => {
    const headers = new Headers(init?.headers)
    assert.equal(headers.get('x-login-client-id'), clientId)
    const timestamp = Number(headers.get('x-login-client-timestamp'))
    const expected = buildLoginClientClaimHeaders(clientId, 'operator', timestamp)
    assert.equal(
      headers.get('x-login-client-signature'),
      expected['X-Login-Client-Signature']
    )
    assert.deepEqual(JSON.parse(String(init?.body)), {
      username: 'operator',
      password: 'secret',
    })
    return Response.json({
      access_token: 'private.jwt',
      user: { id: 1, username: 'operator', saas_user_id: 1 },
    })
  }) as typeof fetch

  const response = await login(request(
    'https://app.test/api/auth/login',
    'POST',
    {
      origin: 'https://app.test',
      'sec-fetch-site': 'same-origin',
      'content-type': 'application/json',
      cookie: `${LOGIN_CLIENT_COOKIE_NAME}=${clientId}`,
    },
    JSON.stringify({ username: 'ｏｐｅｒａｔｏｒ', password: 'secret' })
  ))

  assert.equal(response.status, 200)
  const loginClientCookie = setCookieValues(response)
    .find((value) => value.startsWith(`${LOGIN_CLIENT_COOKIE_NAME}=`)) || ''
  assert.match(loginClientCookie, new RegExp(`^${LOGIN_CLIENT_COOKIE_NAME}=${clientId}`))
})

test('login preserves bounded Retry-After without exposing client ID or logging it', async () => {
  process.env.AUTH_BACKEND_URL = 'http://backend.test/api'
  process.env.ENVIRONMENT = 'development'
  process.env.LOGIN_CLIENT_SIGNING_KEY = (
    'login-client-test-signing-key-0123456789-ABCDEF'
  )
  const clientId = 'E'.repeat(43)
  globalThis.fetch = (async () => Response.json(
    { detail: 'Too many login attempts' },
    { status: 429, headers: { 'Retry-After': '60' } }
  )) as typeof fetch

  const response = await login(request(
    'https://app.test/api/auth/login',
    'POST',
    {
      origin: 'https://app.test',
      'sec-fetch-site': 'same-origin',
      'content-type': 'application/json',
      cookie: `${LOGIN_CLIENT_COOKIE_NAME}=${clientId}`,
    },
    JSON.stringify({ username: 'operator', password: 'wrong' })
  ))
  const payload = await response.json()

  assert.equal(response.status, 429)
  assert.equal(response.headers.get('retry-after'), '60')
  assert.equal(JSON.stringify(payload).includes(clientId), false)
  const claimSource = readFileSync(
    path.join(process.cwd(), 'lib/server/login-client.ts'),
    'utf8'
  )
  const loginRouteSource = readFileSync(
    path.join(process.cwd(), 'app/api/auth/login/route.ts'),
    'utf8'
  )
  assert.doesNotMatch(`${claimSource}\n${loginRouteSource}`, /console\./)
})

for (const environment of ['staging', 'production', 'typo']) {
  test(`${environment} BFF fails closed without a strong signing key`, async () => {
    process.env.AUTH_BACKEND_URL = 'http://backend.test/api'
    process.env.ENVIRONMENT = environment
    process.env.PUBLIC_APP_ORIGIN = 'https://app.test'
    delete process.env.LOGIN_CLIENT_SIGNING_KEY
    let backendCalled = false
    globalThis.fetch = (async () => {
      backendCalled = true
      return new Response()
    }) as typeof fetch

    const response = await login(request(
      'https://app.test/api/auth/login',
      'POST',
      {
        origin: 'https://app.test',
        'sec-fetch-site': 'same-origin',
        'content-type': 'application/json',
      },
      JSON.stringify({ username: 'operator', password: 'secret' })
    ))

    assert.equal(response.status, 502)
    assert.equal(backendCalled, false)
    assert.deepEqual(await response.json(), {
      error: 'Authentication service is unavailable',
    })
  })
}

test('bounded request reader cancels an oversized stream without Content-Length', async () => {
  const chunks = [
    new TextEncoder().encode('1234'),
    new TextEncoder().encode('5678'),
  ]
  let index = 0
  let cancelled = false
  const body = new ReadableStream<Uint8Array>({
    pull(controller) {
      controller.enqueue(chunks[index]!)
      index += 1
    },
    cancel() {
      cancelled = true
    },
  })
  const streamedRequest = new Request('https://app.test/upload', {
    method: 'POST',
    body,
    duplex: 'half',
  } as RequestInit & { duplex: 'half' })

  assert.equal(streamedRequest.headers.has('content-length'), false)
  await assert.rejects(
    () => readRequestBody(streamedRequest, 6),
    RequestBodyTooLargeError
  )
  assert.equal(cancelled, true)
})

test('login rejects an oversized streamed body before calling the backend', async () => {
  let backendCalled = false
  globalThis.fetch = (async () => {
    backendCalled = true
    return new Response()
  }) as typeof fetch
  const oversizedRequest = request(
    'https://app.test/api/auth/login',
    'POST',
    {
      origin: 'https://app.test',
      'sec-fetch-site': 'same-origin',
      'content-type': 'application/json',
    },
    JSON.stringify({ username: 'demo', password: 'x'.repeat(9 * 1024) })
  )

  assert.equal(oversizedRequest.headers.has('content-length'), false)
  const response = await login(oversizedRequest)

  assert.equal(response.status, 413)
  assert.equal(backendCalled, false)
  assert.deepEqual(await response.json(), { error: 'Request body is too large' })
})

test('protected proxy rejects an oversized streamed body before upstream fetch', async () => {
  let backendCalled = false
  globalThis.fetch = (async () => {
    backendCalled = true
    return new Response()
  }) as typeof fetch
  const oversizedRequest = request(
    'http://app.test/api/backend/chatbot/send',
    'POST',
    {
      origin: 'http://app.test',
      'sec-fetch-site': 'same-origin',
      'content-type': 'application/octet-stream',
      cookie: `${SESSION_COOKIE_NAME}=cookie.jwt`,
    },
    'x'.repeat(1024 * 1024 + 1)
  )

  assert.equal(oversizedRequest.headers.has('content-length'), false)
  const response = await proxyPost(oversizedRequest, {
    params: Promise.resolve({ path: ['chatbot', 'send'] }),
  })

  assert.equal(response.status, 413)
  assert.equal(backendCalled, false)
  assert.deepEqual(await response.json(), { error: 'Request body is too large' })
})

test('cross-origin login is rejected before credentials reach the backend', async () => {
  let backendCalled = false
  globalThis.fetch = (async () => {
    backendCalled = true
    return new Response()
  }) as typeof fetch

  const response = await login(request('http://app.test/api/auth/login', 'POST', {
    origin: 'https://evil.test',
    'sec-fetch-site': 'cross-site',
    'content-type': 'application/json',
  }, JSON.stringify({ username: 'demo', password: 'secret' })))

  assert.equal(response.status, 403)
  assert.equal(backendCalled, false)
  assert.equal(response.headers.has('set-cookie'), false)
})

test('session validation adds bearer auth server-side without exposing it in JSON', async () => {
  process.env.AUTH_BACKEND_URL = 'http://backend.test/api'
  globalThis.fetch = (async (input, init) => {
    assert.equal(String(input), 'http://backend.test/api/auth/me')
    assert.equal(new Headers(init?.headers).get('authorization'), 'Bearer private.jwt')
    return new Response(JSON.stringify({ id: 1, username: 'demo', saas_user_id: 1 }), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    })
  }) as typeof fetch

  const response = await session(request('http://app.test/api/auth/session', 'GET', {
    cookie: `${SESSION_COOKIE_NAME}=private.jwt`,
  }))
  const payload = await response.json()

  assert.deepEqual(payload, {
    authenticated: true,
    user: { id: 1, username: 'demo', saas_user_id: 1 },
  })
  assert.equal(JSON.stringify(payload).includes('private.jwt'), false)
})

test('protected proxy ignores client auth headers and injects the cookie token', async () => {
  process.env.AUTH_BACKEND_URL = 'http://backend.test/api'
  globalThis.fetch = (async (input, init) => {
    assert.equal(String(input), 'http://backend.test/api/chatbot/send?source=ui')
    const headers = new Headers(init?.headers)
    assert.equal(headers.get('authorization'), 'Bearer cookie.jwt')
    assert.equal(headers.get('x-client-secret'), null)
    assert.equal(await new Response(init?.body).text(), '{"message":"hello"}')
    return Response.json({ success: true })
  }) as typeof fetch

  const response = await proxyPost(request(
    'http://app.test/api/backend/chatbot/send?source=ui',
    'POST',
    {
      origin: 'http://app.test',
      'sec-fetch-site': 'same-origin',
      'content-type': 'application/json',
      authorization: 'Bearer attacker-controlled',
      'x-client-secret': 'must-not-forward',
      cookie: `${SESSION_COOKIE_NAME}=cookie.jwt`,
    },
    '{"message":"hello"}'
  ), {
    params: Promise.resolve({ path: ['chatbot', 'send'] }),
  })

  assert.equal(response.status, 200)
  assert.deepEqual(await response.json(), { success: true })
})

test('chat message text is sent only in a JSON body, never in the URL', async () => {
  const sensitiveText = 'token=private-value&next=/billing?admin=true'
  globalThis.fetch = (async (input, init) => {
    const requestUrl = String(input)
    assert.equal(
      requestUrl,
      '/api/backend/chatbot/api/chats/chat-1/messages'
    )
    assert.equal(requestUrl.includes(sensitiveText), false)
    assert.equal(init?.method, 'POST')
    assert.equal(
      new Headers(init?.headers).get('content-type'),
      'application/json'
    )
    assert.deepEqual(
      JSON.parse(await new Response(init?.body).text()),
      { text: sensitiveText }
    )
    return Response.json({ sent: true })
  }) as typeof fetch

  assert.deepEqual(
    await api.sendChatbotMessage('chat-1', sensitiveText),
    { sent: true }
  )
})

test('barter fixture requires an authenticated session cookie', async () => {
  let backendCalled = false
  globalThis.fetch = (async () => {
    backendCalled = true
    return new Response()
  }) as typeof fetch

  const response = await barterChannels(request(
    'http://app.test/api/barter/channels',
    'GET',
    { 'sec-fetch-site': 'same-origin' }
  ))

  assert.equal(response.status, 401)
  assert.deepEqual(await response.json(), { error: 'Authentication required' })
  assert.equal(backendCalled, false)
})

test('barter fixture validates the session server-side and is explicitly synthetic', async () => {
  process.env.AUTH_BACKEND_URL = 'http://backend.test/api'
  process.env.DASHBOARD_DATA_SOURCE = 'synthetic-demo'
  globalThis.fetch = (async (input, init) => {
    assert.equal(String(input), 'http://backend.test/api/auth/me')
    assert.equal(init?.method, 'GET')
    assert.equal(new Headers(init?.headers).get('authorization'), 'Bearer private.jwt')
    return Response.json({ id: 1, username: 'demo', saas_user_id: 1 })
  }) as typeof fetch

  const response = await barterChannels(request(
    'http://app.test/api/barter/channels',
    'GET',
    {
      cookie: `${SESSION_COOKIE_NAME}=private.jwt`,
      'sec-fetch-site': 'same-origin',
    }
  ))
  const payload = await response.json() as {
    channels: Array<Record<string, unknown>>
    count: number
    source: { type: string; synthetic: boolean; provenance: string }
  }

  assert.equal(response.status, 200)
  assert.equal(payload.count, payload.channels.length)
  assert.ok(payload.channels.length > 0)
  assert.deepEqual(payload.source, {
    type: 'synthetic_fixture',
    synthetic: true,
    provenance: 'bundled-public-demo',
  })
})

test('barter fixture fails closed outside explicit synthetic demo mode', async () => {
  process.env.AUTH_BACKEND_URL = 'http://backend.test/api'
  process.env.DASHBOARD_DATA_SOURCE = 'live'
  globalThis.fetch = (async () => Response.json({
    id: 1,
    username: 'operator',
    saas_user_id: 1,
  })) as typeof fetch

  const response = await barterChannels(request(
    'http://app.test/api/barter/channels',
    'GET',
    {
      cookie: `${SESSION_COOKIE_NAME}=private.jwt`,
      'sec-fetch-site': 'same-origin',
    }
  ))
  const payload = await response.json()

  assert.equal(response.status, 503)
  assert.deepEqual(payload, {
    channels: [],
    count: 0,
    error: 'Live recommendation source is not configured',
    source: {
      type: 'live_unconfigured',
      synthetic: false,
      provenance: 'none',
    },
  })
})

test('barter fixture cannot leak filesystem paths or debug details', async () => {
  process.env.AUTH_BACKEND_URL = 'http://backend.test/api'
  process.env.DASHBOARD_DATA_SOURCE = 'synthetic-demo'
  globalThis.fetch = (async () => Response.json({ id: 1 })) as typeof fetch

  const response = await barterChannels(request(
    'http://app.test/api/barter/channels',
    'GET',
    { cookie: `${SESSION_COOKIE_NAME}=private.jwt` }
  ))
  const serializedPayload = JSON.stringify(await response.json())

  for (const forbidden of ['process.cwd', 'vector_search', 'parser_local', 'triedPaths', 'debug']) {
    assert.equal(serializedPayload.includes(forbidden), false, forbidden)
  }

  const routeSource = readFileSync(
    path.join(process.cwd(), 'app/api/barter/channels/route.ts'),
    'utf8'
  )
  assert.doesNotMatch(routeSource, /(?:node:)?fs|readFile|process\.cwd|console\./)
})

test('dashboard never fabricates unlabeled fallback analytics', () => {
  const dashboardSource = readFileSync(
    path.join(process.cwd(), 'app/dashboard/page.tsx'),
    'utf8'
  )
  const chartSource = readFileSync(
    path.join(process.cwd(), 'components/dashboard/ActivityChart.tsx'),
    'utf8'
  )

  assert.equal(dashboardSource.includes("data_source === 'synthetic-demo'"), true)
  assert.equal(dashboardSource.includes('Демо-показатели не подставляются'), true)
  assert.equal(dashboardSource.includes('Попробовать снова'), true)
  assert.doesNotMatch(dashboardSource, /console\.|Трендовые тени|12500/)
  assert.doesNotMatch(chartSource, /Math\.random|generateDefaultData/)
  assert.equal(chartSource.includes('Временной ряд пока недоступен'), true)
})

test('authenticated product views avoid dead navigation and hardcoded live identities', () => {
  const shopSource = readFileSync(path.join(process.cwd(), 'app/shop/page.tsx'), 'utf8')
  const documentsSource = readFileSync(path.join(process.cwd(), 'app/documents/page.tsx'), 'utf8')
  const sidebarSource = readFileSync(path.join(process.cwd(), 'components/layout/Sidebar.tsx'), 'utf8')
  const navigationSource = readFileSync(path.join(process.cwd(), 'components/layout/SidebarNav.tsx'), 'utf8')
  const metricTypes = readFileSync(path.join(process.cwd(), 'lib/types/dashboard.ts'), 'utf8')
  const loginSource = readFileSync(path.join(process.cwd(), 'app/page.tsx'), 'utf8')
  const productSources = [shopSource, documentsSource, sidebarSource, navigationSource, loginSource].join('\n')

  assert.match(shopSource, /getSession\(\)/)
  assert.match(shopSource, /<Sidebar/)
  assert.match(documentsSource, /<Sidebar/)
  assert.match(sidebarSource, /api\.logout\(\)/)
  assert.doesNotMatch(navigationSource, /\/(?:calendar|ideas|flags)/)
  assert.doesNotMatch(productSources, /href=["']#["']/)
  assert.doesNotMatch(productSources, /Принцесса Игорь|princessigorrr|gori_yasno/i)
  assert.match(metricTypes, /postsPerDay: Metric/)
  assert.match(metricTypes, /averageViews: Metric/)
  assert.doesNotMatch(metricTypes, /averagePromos|growth: Metric/)
})

function filesUnder(directory: string): string[] {
  return readdirSync(directory).flatMap((entry) => {
    const fullPath = path.join(directory, entry)
    return statSync(fullPath).isDirectory() ? filesUnder(fullPath) : [fullPath]
  })
}

test('client code cannot read or persist a bearer token', () => {
  const clientRoots = ['app', 'components', 'hooks', 'lib']
    .map((directory) => path.join(process.cwd(), directory))
  const files = clientRoots
    .flatMap(filesUnder)
    .filter((file) => /\.(ts|tsx)$/.test(file))
    .filter((file) => !file.includes(`${path.sep}app${path.sep}api${path.sep}`))
    .filter((file) => !file.includes(`${path.sep}lib${path.sep}server${path.sep}`))
  const forbiddenStorage = /(?:localStorage|sessionStorage)\s*\.\s*(?:getItem|setItem)\s*\(\s*['"](?:token|access_token|authToken)['"]/i

  for (const file of files) {
    const source = readFileSync(file, 'utf8')
    assert.doesNotMatch(source, forbiddenStorage, file)
    assert.equal(source.includes('new WebSocket('), false, file)
    assert.equal(source.includes('NEXT_PUBLIC_WS_URL'), false, file)
  }

  const clientApi = readFileSync(path.join(process.cwd(), 'lib/api.ts'), 'utf8')
  assert.equal(clientApi.includes('NEXT_PUBLIC_API_URL'), false)
  assert.equal(clientApi.includes("headers.set('Authorization'"), false)
})
