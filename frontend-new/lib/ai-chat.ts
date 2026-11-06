export type AiRoute = 'GENERAL' | 'SALES' | 'BARTER'

export interface AiScenario {
  route: AiRoute
  label: string
  description: string
  prompt: string
}

export interface AiAnswer {
  reply_text: string
  used_agent: 'general' | 'sales' | 'barter'
  route: AiRoute
  metadata?: Record<string, unknown> | null
}

export interface AiHistoryMessage {
  id: string
  content: string
  is_own: boolean
  timestamp: string
  chat_id: string
}

export interface AiUiMessage {
  id: string
  content: string
  role: 'user' | 'assistant'
  timestamp: string
}

export interface AiRequestPayload {
  session_id: string
  chat_id: string
  user_id: string
  message_text: string
  channel_username: string
  language: 'ru'
  metadata: {
    surface: 'frontend-demo'
    data_mode: 'synthetic'
  }
}

export const AI_SESSION_STORAGE_KEY = 'telegram-ai-demo-session-v1'

export const AI_SCENARIOS: readonly AiScenario[] = Object.freeze([
  {
    route: 'GENERAL',
    label: 'Общий вопрос',
    description: 'Навигация по возможностям AI-платформы.',
    prompt: 'Привет! Чем ты можешь помочь владельцу Telegram-канала?',
  },
  {
    route: 'SALES',
    label: 'Продажи',
    description: 'Рекламные размещения, цена и медиакит.',
    prompt: 'Подскажи цену рекламного размещения и как подготовить медиакит.',
  },
  {
    route: 'BARTER',
    label: 'Бартер',
    description: 'Партнёрства и подбор похожих каналов.',
    prompt: 'Найди похожие каналы для бартера и предложи план партнёрства.',
  },
])

const SESSION_ID_PATTERN = /^ui-[A-Za-z0-9][A-Za-z0-9._:@-]{0,124}$/

export function createAiSessionId(randomValue: string): string {
  const normalized = randomValue
    .replace(/[^A-Za-z0-9._:@-]/g, '')
    .slice(0, 110)

  if (!normalized) {
    throw new Error('Cannot create an AI session without a random identifier')
  }

  return `ui-${normalized}`
}

export function readAiSessionId(value: string | null): string | null {
  return value && SESSION_ID_PATTERN.test(value) ? value : null
}

export function buildAiRequestPayload(
  sessionId: string,
  saasUserId: number,
  messageText: string
): AiRequestPayload {
  const normalizedMessage = messageText.trim()
  if (!readAiSessionId(sessionId)) {
    throw new Error('Invalid AI session identifier')
  }
  if (!normalizedMessage) {
    throw new Error('Message cannot be empty')
  }

  return {
    session_id: sessionId,
    chat_id: sessionId,
    user_id: String(saasUserId),
    message_text: normalizedMessage,
    channel_username: 'demo_analytics_channel',
    language: 'ru',
    metadata: {
      surface: 'frontend-demo',
      data_mode: 'synthetic',
    },
  }
}

export function normalizeAiHistory(messages: readonly AiHistoryMessage[]): AiUiMessage[] {
  return messages.map((message) => ({
    id: message.id,
    content: message.content,
    role: message.is_own ? 'user' : 'assistant',
    timestamp: message.timestamp,
  }))
}

export function getAiScenario(route: AiRoute): AiScenario {
  return AI_SCENARIOS.find((scenario) => scenario.route === route) || AI_SCENARIOS[0]
}
