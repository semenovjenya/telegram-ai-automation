'use client'

import { useCallback, useEffect, useState } from 'react'
import { api } from '@/lib/api'
import type { Chat, Message } from '@/lib/types/chat'

const CHAT_POLL_INTERVAL_MS = 30_000
const MESSAGE_POLL_INTERVAL_MS = 15_000

export type ChatTransportStatus = 'polling' | 'offline'

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === 'object' && !Array.isArray(value)
    ? value as Record<string, unknown>
    : {}
}

function stringValue(value: unknown): string | undefined {
  return typeof value === 'string' && value ? value : undefined
}

function normalizeChat(value: unknown): Chat | null {
  const chat = asRecord(value)
  const rawId = chat.id ?? chat.chat_id
  if (typeof rawId !== 'string' && typeof rawId !== 'number') {
    return null
  }

  const id = String(rawId)
  const title = stringValue(chat.name) || stringValue(chat.title) ||
    stringValue(chat.username) || `Чат ${id}`
  const lastMessage = asRecord(chat.last_message)
  const lastContent = stringValue(lastMessage.content) || stringValue(lastMessage.text)
  const lastTimestamp = stringValue(lastMessage.timestamp) || stringValue(lastMessage.date)

  return {
    id,
    title,
    name: stringValue(chat.name),
    username: stringValue(chat.username),
    type: stringValue(chat.type),
    unread_count: typeof chat.unread_count === 'number' ? chat.unread_count : 0,
    last_message: lastContent && lastTimestamp
      ? { content: lastContent, timestamp: lastTimestamp }
      : undefined,
  }
}

function normalizeMessage(value: unknown, chatId: string, index: number): Message {
  const message = asRecord(value)
  const timestamp = stringValue(message.timestamp) || stringValue(message.date) ||
    new Date().toISOString()
  const rawId = message.id ?? message.message_id

  return {
    id: rawId === undefined ? `${chatId}-${timestamp}-${index}` : String(rawId),
    content: stringValue(message.content) || stringValue(message.text) ||
      stringValue(message.message) || '',
    timestamp,
    isOwn: typeof message.isOwn === 'boolean'
      ? message.isOwn
      : typeof message.out === 'boolean' ? message.out : false,
    chat_id: chatId,
  }
}

export const useChatLogic = (isAuthenticated: boolean) => {
  const [chats, setChats] = useState<Chat[]>([])
  const [selectedChat, setSelectedChat] = useState<string | null>(null)
  const [messages, setMessages] = useState<Message[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [isLoadingMessages, setIsLoadingMessages] = useState(false)
  const [transportStatus, setTransportStatus] = useState<ChatTransportStatus>('offline')
  const [error, setError] = useState<string | null>(null)

  const refreshChats = useCallback(async () => {
    if (!isAuthenticated) return

    try {
      const response = await api.getChatbotChats()
      const normalizedChats = response.chats
        .map(normalizeChat)
        .filter((chat): chat is Chat => chat !== null)
      setChats(normalizedChats)
      setSelectedChat((current) => {
        if (current && normalizedChats.some((chat) => chat.id === current)) {
          return current
        }
        return normalizedChats[0]?.id || null
      })
      setTransportStatus('polling')
      setError(null)
    } catch (requestError) {
      setTransportStatus('offline')
      setError(requestError instanceof Error ? requestError.message : 'Не удалось загрузить чаты')
    } finally {
      setIsLoading(false)
    }
  }, [isAuthenticated])

  const refreshMessages = useCallback(async () => {
    if (!isAuthenticated || !selectedChat) return

    setIsLoadingMessages(true)
    try {
      const response = await api.getChatbotMessages(selectedChat)
      const normalizedMessages = response.messages
        .map((message, index) => normalizeMessage(message, selectedChat, index))
        .reverse()
      setMessages(normalizedMessages)
      setTransportStatus('polling')
      setError(null)
    } catch (requestError) {
      setTransportStatus('offline')
      setError(requestError instanceof Error ? requestError.message : 'Не удалось загрузить сообщения')
    } finally {
      setIsLoadingMessages(false)
    }
  }, [isAuthenticated, selectedChat])

  useEffect(() => {
    if (!isAuthenticated) return

    void refreshChats()
    const interval = window.setInterval(() => {
      void refreshChats()
    }, CHAT_POLL_INTERVAL_MS)
    return () => window.clearInterval(interval)
  }, [isAuthenticated, refreshChats])

  useEffect(() => {
    setMessages([])
    if (!isAuthenticated || !selectedChat) return

    void refreshMessages()
    const interval = window.setInterval(() => {
      void refreshMessages()
    }, MESSAGE_POLL_INTERVAL_MS)
    return () => window.clearInterval(interval)
  }, [isAuthenticated, selectedChat, refreshMessages])

  const handleSelectChat = useCallback((chatId: string) => {
    setSelectedChat(chatId)
  }, [])

  return {
    chats,
    selectedChat,
    messages,
    isLoading,
    isLoadingMessages,
    transportStatus,
    error,
    handleSelectChat,
    refreshMessages,
  }
}
