import type { NextRequest, NextResponse } from 'next/server'

export const SESSION_COOKIE_NAME = 'taap_session'

const SESSION_MAX_AGE_SECONDS = 24 * 60 * 60
const SAFE_METHODS = new Set(['GET', 'HEAD', 'OPTIONS'])

function hardenedRuntime(): boolean {
  const environment = (process.env.ENVIRONMENT || process.env.APP_ENV || '')
    .trim()
    .toLowerCase()
  if (environment) {
    return !['development', 'test'].includes(environment)
  }
  return process.env.NODE_ENV === 'production'
}

function exactOrigin(value: string | undefined | null): string | null {
  const candidate = value?.trim()
  if (!candidate) {
    return null
  }
  try {
    const parsed = new URL(candidate)
    if (
      !['http:', 'https:'].includes(parsed.protocol) ||
      parsed.username ||
      parsed.password ||
      !parsed.hostname ||
      (parsed.pathname !== '' && parsed.pathname !== '/') ||
      parsed.search ||
      parsed.hash ||
      candidate.replace(/\/$/, '') !== parsed.origin
    ) {
      return null
    }
    return parsed.origin
  } catch {
    return null
  }
}

function publicAppOrigin(): string | null {
  const origin = exactOrigin(process.env.PUBLIC_APP_ORIGIN)
  if (hardenedRuntime() && (!origin || !origin.startsWith('https://'))) {
    return null
  }
  return origin
}

export function isSameOriginRequest(request: NextRequest): boolean {
  if (SAFE_METHODS.has(request.method.toUpperCase())) {
    return true
  }

  const fetchSite = request.headers.get('sec-fetch-site')
  if (fetchSite && fetchSite !== 'same-origin') {
    return false
  }

  const origin = request.headers.get('origin')
  if (!origin) {
    return false
  }

  const normalizedOrigin = exactOrigin(origin)
  if (!normalizedOrigin) {
    return false
  }

  const configuredOrigin = publicAppOrigin()
  if (hardenedRuntime()) {
    return configuredOrigin !== null && normalizedOrigin === configuredOrigin
  }

  const allowedOrigins = new Set([request.nextUrl.origin])
  if (configuredOrigin) allowedOrigins.add(configuredOrigin)
  return allowedOrigins.has(normalizedOrigin)
}

export function usesSecureCookies(request: NextRequest): boolean {
  const configuredOrigin = publicAppOrigin()
  return (
    configuredOrigin?.startsWith('https://') || request.nextUrl.protocol === 'https:'
  )
}

export function setSessionCookie(
  response: NextResponse,
  request: NextRequest,
  token: string
): void {
  response.cookies.set(SESSION_COOKIE_NAME, token, {
    httpOnly: true,
    secure: usesSecureCookies(request),
    sameSite: 'strict',
    path: '/',
    maxAge: SESSION_MAX_AGE_SECONDS,
    priority: 'high',
  })
}

export function clearSessionCookie(
  response: NextResponse,
  request: NextRequest
): void {
  response.cookies.set(SESSION_COOKIE_NAME, '', {
    httpOnly: true,
    secure: usesSecureCookies(request),
    sameSite: 'strict',
    path: '/',
    maxAge: 0,
    priority: 'high',
  })
}
