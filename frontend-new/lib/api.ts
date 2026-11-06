/** Same-origin client for the Next.js BFF. JWT values never enter browser JavaScript. */

import type { Channel, DashboardData } from '@/lib/types/dashboard'
import type { AiHistoryMessage } from '@/lib/ai-chat'

export interface SessionUser {
  id: number
  username: string
  saas_user_id: number
}

export interface SessionResponse {
  authenticated: boolean
  user?: SessionUser
}

export class ApiError extends Error {
  constructor(message: string, readonly status: number) {
    super(message)
    this.name = 'ApiError'
  }
}

interface ChannelsResponse {
  channels: Channel[]
  count?: number
}

async function getChannels(): Promise<ChannelsResponse> {
  const response = await fetch('/api/barter/channels')
  const payload = await response.json().catch(() => ({})) as Partial<ChannelsResponse> & {
    error?: string
  }

  if (!response.ok) {
    throw new Error(payload.error || 'Не удалось загрузить каналы')
  }

  return {
    channels: Array.isArray(payload.channels) ? payload.channels : [],
    count: payload.count,
  }
}

async function apiRequest<T>(
  endpoint: string,
  options: RequestInit = {}
): Promise<T> {
  const headers = new Headers(options.headers)
  if (options.body && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json')
  }

  const response = await fetch(endpoint, {
    ...options,
    headers,
    credentials: 'same-origin',
    cache: 'no-store',
  })

  if (!response.ok) {
    const error = await response.json().catch(() => ({})) as {
      detail?: string
      error?: string
      message?: string
    }
    throw new ApiError(
      error.detail || error.error || error.message || response.statusText || 'API request failed',
      response.status
    )
  }

  if (response.status === 204) {
    return undefined as T
  }

  return response.json()
}

function backendRequest<T>(endpoint: string, options: RequestInit = {}): Promise<T> {
  return apiRequest<T>(`/api/backend${endpoint}`, options)
}

export const api = {
  // Авторизация
  login: async (username: string, password: string) => {
    return apiRequest<SessionResponse>(
      '/api/auth/login',
      {
        method: 'POST',
        body: JSON.stringify({ username, password }),
      }
    )
  },

  getSession: async () => {
    return apiRequest<SessionResponse>('/api/auth/session')
  },

  logout: async () => {
    return apiRequest<SessionResponse>('/api/auth/logout', {
      method: 'POST',
    })
  },

  // Dashboard данные
  getDashboardData: async () => {
    return backendRequest<DashboardData>('/dashboard')
  },

  getDashboardMetrics: async () => {
    return backendRequest('/dashboard/metrics')
  },

  getDashboardPublications: async () => {
    return backendRequest('/dashboard/publications')
  },

  getDashboardProfile: async () => {
    return backendRequest('/dashboard/profile')
  },

  getDashboardAISummary: async () => {
    return backendRequest('/dashboard/ai-summary')
  },

  getDashboardAIRecommendation: async () => {
    return backendRequest<{ recommendation: string }>('/dashboard/ai-recommendation')
  },

  getDashboardNotifications: async () => {
    return backendRequest('/dashboard/notifications')
  },

  getChannels,
  
  // Прокси к AI Brain
  aiRequest: async <T = unknown>(path: string, options: RequestInit = {}) => {
    return backendRequest<T>(`/ai/${path.replace(/^\/+/, '')}`, options)
  },

  // Прокси к Telegram Chatbot
  chatbotRequest: async <T = unknown>(path: string, options: RequestInit = {}) => {
    return backendRequest<T>(`/chatbot/${path.replace(/^\/+/, '')}`, options)
  },

  // Получить историю чата из ai_brain
  getChatHistory: async (sessionId: string, limit: number = 100) => {
    const query = new URLSearchParams({ limit: String(limit) })
    return backendRequest<{
      session_id: string
      chat_id: string
      messages: AiHistoryMessage[]
      returned_count?: number
      total: number
    }>(`/ai/chat/history/${encodeURIComponent(sessionId)}?${query}`)
  },
  
  // Получить топ каналов для бартера
  getBarterChannels: getChannels,

  // Чаты и сообщения читаются через same-origin BFF polling; API keys остаются серверными.
  getChatbotChats: async (limit: number = 100) => {
    const query = new URLSearchParams({ limit: String(limit) })
    return backendRequest<{
      chats: unknown[]
      total?: number
      error?: string
    }>(`/chatbot/api/chats?${query}`)
  },

  // Получить сообщения чата из chatbot
  getChatbotMessages: async (chatId: string, limit: number = 50) => {
    const query = new URLSearchParams({ limit: String(limit) })
    return backendRequest<{
      messages: unknown[]
      total?: number
      error?: string
    }>(`/chatbot/api/chats/${encodeURIComponent(chatId)}/messages?${query}`)
  },

  // Отправить сообщение в чат через chatbot
  sendChatbotMessage: async (chatId: string, message: string) => {
    return backendRequest<{
      sent: boolean
      message?: unknown
      error?: string
    }>(`/chatbot/api/chats/${encodeURIComponent(chatId)}/messages`, {
      method: 'POST',
      body: JSON.stringify({ text: message }),
    })
  },
}
