import { createHash, createHmac, randomBytes } from 'node:crypto'
import type { NextRequest, NextResponse } from 'next/server'
import { usesSecureCookies } from '@/lib/server/security'

export const LOGIN_CLIENT_COOKIE_NAME = 'taap_login_client'

const CLAIM_VERSION = 'v1'
const CLIENT_ID_PATTERN = /^[A-Za-z0-9_-]{43}$/
const LOGIN_CLIENT_MAX_AGE_SECONDS = 30 * 24 * 60 * 60
const MAX_USERNAME_CHARACTERS = 128
const MAX_USERNAME_BYTES = 512
const SECRET_PLACEHOLDERS = [
  'change-me',
  'changeme',
  'your-secret',
  'test-api-key',
  'example',
]

function requiresSignedClaim(): boolean {
  const environment = (process.env.ENVIRONMENT || process.env.APP_ENV || '')
    .trim()
    .toLowerCase()
  if (environment) {
    return !['development', 'test'].includes(environment)
  }
  return process.env.NODE_ENV === 'production'
}

function isPlaceholderSecret(value: string): boolean {
  const normalized = value.trim().toLowerCase()
  return (
    !normalized ||
    new Set(value).size < 8 ||
    SECRET_PLACEHOLDERS.some((marker) => normalized.includes(marker))
  )
}

function signingKey(): string | null {
  const key = process.env.LOGIN_CLIENT_SIGNING_KEY || ''
  if (requiresSignedClaim() && (key.length < 32 || isPlaceholderSecret(key))) {
    throw new Error('LOGIN_CLIENT_SIGNING_KEY is not securely configured')
  }
  return key || null
}

export function canonicalLoginUsername(username: string): string {
  const canonical = username.trim().normalize('NFKC')
  if (
    canonical.length === 0 ||
    [...canonical].length > MAX_USERNAME_CHARACTERS ||
    Buffer.byteLength(canonical, 'utf8') > MAX_USERNAME_BYTES ||
    /[\u0000-\u001f\u007f]/.test(canonical)
  ) {
    throw new Error('Invalid login username')
  }
  return canonical
}

export function getOrCreateLoginClientId(request: NextRequest): string {
  const existing = request.cookies.get(LOGIN_CLIENT_COOKIE_NAME)?.value || ''
  return CLIENT_ID_PATTERN.test(existing)
    ? existing
    : randomBytes(32).toString('base64url')
}

export function buildLoginClientClaimHeaders(
  clientId: string,
  username: string,
  timestamp = Math.floor(Date.now() / 1_000)
): Record<string, string> {
  if (!CLIENT_ID_PATTERN.test(clientId)) {
    throw new Error('Invalid login client identifier')
  }
  const key = signingKey()
  if (!key) {
    // A direct-peer fallback is deliberately limited to non-production auth.
    return {}
  }
  const canonicalUsername = canonicalLoginUsername(username)
  const usernameDigest = createHash('sha256')
    .update(canonicalUsername, 'utf8')
    .digest('hex')
  const payload = `${CLAIM_VERSION}\n${timestamp}\n${clientId}\n${usernameDigest}`
  const signature = createHmac('sha256', key)
    .update(payload, 'ascii')
    .digest('hex')
  return {
    'X-Login-Client-Version': CLAIM_VERSION,
    'X-Login-Client-Timestamp': String(timestamp),
    'X-Login-Client-ID': clientId,
    'X-Login-Client-Signature': signature,
  }
}

export function setLoginClientCookie(
  response: NextResponse,
  request: NextRequest,
  clientId: string
): void {
  response.cookies.set(LOGIN_CLIENT_COOKIE_NAME, clientId, {
    httpOnly: true,
    secure: usesSecureCookies(request),
    sameSite: 'strict',
    path: '/api/auth/login',
    maxAge: LOGIN_CLIENT_MAX_AGE_SECONDS,
    priority: 'high',
  })
}
