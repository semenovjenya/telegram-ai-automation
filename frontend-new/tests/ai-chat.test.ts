import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import path from 'node:path'
import test from 'node:test'
import {
  AI_SCENARIOS,
  buildAiRequestPayload,
  createAiSessionId,
  normalizeAiHistory,
  readAiSessionId,
} from '@/lib/ai-chat'

test('demo exposes deterministic prompts for all AI routes', () => {
  assert.deepEqual(
    AI_SCENARIOS.map((scenario) => scenario.route),
    ['GENERAL', 'SALES', 'BARTER']
  )
  for (const scenario of AI_SCENARIOS) {
    assert.ok(scenario.prompt.length > 20)
    assert.ok(scenario.description.length > 10)
  }
  assert.match(AI_SCENARIOS[1].prompt, /цену|рекламного/i)
  assert.match(AI_SCENARIOS[2].prompt, /бартер/i)
})

test('AI request payload is tenant-neutral and accepted by the brain contract', () => {
  const payload = buildAiRequestPayload('ui-session-123', 42, '  Сколько стоит размещение?  ')

  assert.deepEqual(payload, {
    session_id: 'ui-session-123',
    chat_id: 'ui-session-123',
    user_id: '42',
    message_text: 'Сколько стоит размещение?',
    channel_username: 'demo_analytics_channel',
    language: 'ru',
    metadata: {
      surface: 'frontend-demo',
      data_mode: 'synthetic',
    },
  })
  assert.equal('saas_user_id' in payload, false)
  assert.throws(
    () => buildAiRequestPayload('another-tenant-session', 42, 'hello'),
    /Invalid AI session/
  )
  assert.throws(
    () => buildAiRequestPayload('ui-session-123', 42, '   '),
    /cannot be empty/
  )
})

test('browser-scoped demo session IDs are bounded and validated', () => {
  const sessionId = createAiSessionId('123e4567-e89b-12d3-a456-426614174000')
  assert.equal(sessionId, 'ui-123e4567-e89b-12d3-a456-426614174000')
  assert.equal(readAiSessionId(sessionId), sessionId)
  assert.equal(readAiSessionId('shared-public-session'), null)
  assert.equal(readAiSessionId(`ui-${'x'.repeat(126)}`), null)
  assert.throws(() => createAiSessionId('///'), /random identifier/)
})

test('persisted history is normalized into chronological UI roles', () => {
  assert.deepEqual(normalizeAiHistory([
    {
      id: '10',
      content: 'Вопрос',
      is_own: true,
      timestamp: '2026-07-15T10:00:00Z',
      chat_id: 'ui-session-123',
    },
    {
      id: '11',
      content: 'Ответ',
      is_own: false,
      timestamp: '2026-07-15T10:00:01Z',
      chat_id: 'ui-session-123',
    },
  ]), [
    {
      id: '10',
      content: 'Вопрос',
      role: 'user',
      timestamp: '2026-07-15T10:00:00Z',
    },
    {
      id: '11',
      content: 'Ответ',
      role: 'assistant',
      timestamp: '2026-07-15T10:00:01Z',
    },
  ])
})

test('AI page uses the answer and persisted-history golden path', () => {
  const pageSource = readFileSync(
    path.join(process.cwd(), 'app/chat/page.tsx'),
    'utf8'
  )

  assert.match(pageSource, /api\.aiRequest<AiAnswer>\('brain\/answer'/)
  assert.match(pageSource, /api\.getChatHistory\(activeSessionId\)/)
  assert.match(pageSource, /Синтетический demo/)
  assert.match(pageSource, /RAG и live tools[^\n]+не запускаются/)
})
