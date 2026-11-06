import assert from 'node:assert/strict'
import test, { after } from 'node:test'
import nextConfig from '../next.config.js'

const mutableEnv = process.env as { [key: string]: string | undefined }
const originalNodeEnv = mutableEnv.NODE_ENV

after(() => {
  if (originalNodeEnv === undefined) {
    delete mutableEnv.NODE_ENV
  } else {
    mutableEnv.NODE_ENV = originalNodeEnv
  }
})

test('direct Next.js responses apply a production-safe global header policy', async () => {
  mutableEnv.NODE_ENV = 'production'
  const routes = await nextConfig.headers?.()
  assert.ok(routes)
  assert.equal(routes.length, 1)
  assert.equal(routes[0].source, '/:path*')
  const headers = new Map(
    routes[0].headers.map(({ key, value }) => [key.toLowerCase(), value])
  )

  assert.match(headers.get('content-security-policy') || '', /default-src 'self'/)
  assert.match(headers.get('content-security-policy') || '', /frame-ancestors 'none'/)
  assert.equal(headers.get('x-frame-options'), 'DENY')
  assert.equal(headers.get('x-content-type-options'), 'nosniff')
  assert.equal(headers.get('referrer-policy'), 'no-referrer')
  assert.equal(headers.get('cross-origin-opener-policy'), 'same-origin')
  assert.match(headers.get('permissions-policy') || '', /camera=\(\)/)
  assert.equal(headers.get('strict-transport-security'), 'max-age=31536000')
})

test('development header policy supports HMR without persisting HSTS', async () => {
  mutableEnv.NODE_ENV = 'development'
  const routes = await nextConfig.headers?.()
  assert.ok(routes)
  const headers = new Map(
    routes[0].headers.map(({ key, value }) => [key.toLowerCase(), value])
  )

  assert.equal(headers.has('strict-transport-security'), false)
  assert.match(
    headers.get('content-security-policy') || '',
    /connect-src 'self' ws: wss:/
  )
  assert.match(
    headers.get('content-security-policy') || '',
    /script-src 'self' 'unsafe-inline' 'unsafe-eval'/
  )
})
