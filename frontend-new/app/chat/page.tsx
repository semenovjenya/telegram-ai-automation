'use client'

import { FormEvent, KeyboardEvent, useCallback, useEffect, useRef, useState } from 'react'
import { usePathname, useRouter } from 'next/navigation'
import { Sidebar } from '@/components/layout/Sidebar'
import { clearLegacyAuthStorage } from '@/lib/auth-client'
import {
  AI_SCENARIOS,
  AI_SESSION_STORAGE_KEY,
  buildAiRequestPayload,
  createAiSessionId,
  getAiScenario,
  normalizeAiHistory,
  readAiSessionId,
  type AiAnswer,
  type AiRoute,
  type AiUiMessage,
} from '@/lib/ai-chat'
import { api, ApiError, type SessionUser } from '@/lib/api'

const ROUTE_STYLES: Record<AiRoute, string> = {
  GENERAL: 'border-sky-200 bg-sky-50 text-sky-800',
  SALES: 'border-violet-200 bg-violet-50 text-violet-800',
  BARTER: 'border-emerald-200 bg-emerald-50 text-emerald-800',
}

let fallbackSessionCounter = 0

function newSessionId(): string {
  const randomValue = globalThis.crypto?.randomUUID?.() || (
    `${Date.now()}-${fallbackSessionCounter++}`
  )
  return createAiSessionId(randomValue)
}

function formatMessageTime(value: string): string {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return ''
  return new Intl.DateTimeFormat('ru-RU', {
    hour: '2-digit',
    minute: '2-digit',
  }).format(date)
}

function messageError(error: unknown, fallback: string): string {
  if (error instanceof ApiError) {
    if (error.status === 503) return 'Сервис AI временно недоступен. Повторите запрос.'
    if (error.status === 429) return 'Слишком много запросов. Дайте сервису немного времени.'
    return `${fallback} (код ${error.status}).`
  }
  return error instanceof Error && error.message ? error.message : fallback
}

function RouteBadge({ route }: { route: AiRoute }) {
  return (
    <span className={`inline-flex rounded-full border px-2.5 py-1 text-[11px] font-bold tracking-wide ${ROUTE_STYLES[route]}`}>
      {route}
    </span>
  )
}

function MessageBubble({ message }: { message: AiUiMessage }) {
  const isUser = message.role === 'user'

  return (
    <div className={`flex gap-3 ${isUser ? 'justify-end' : 'justify-start'}`}>
      {!isUser && (
        <div className="mt-1 flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-xl bg-slate-950 text-white shadow-sm" aria-hidden="true">
          <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path strokeLinecap="round" strokeLinejoin="round" d="M12 3v3m0 12v3M3 12h3m12 0h3m-4.64-5.36-2.12 2.12M9.76 14.24l-2.12 2.12m0-9.72 2.12 2.12m4.48 5.48 2.12 2.12" />
          </svg>
        </div>
      )}
      <div className={`max-w-[88%] rounded-2xl px-4 py-3 shadow-sm sm:max-w-[75%] ${
        isUser
          ? 'rounded-br-md bg-primary-dark text-white'
          : 'rounded-bl-md border border-slate-200 bg-white text-slate-800'
      }`}>
        <p className="whitespace-pre-wrap text-sm leading-6">{message.content}</p>
        <p className={`mt-1 text-right text-[10px] ${isUser ? 'text-violet-100' : 'text-slate-400'}`}>
          {formatMessageTime(message.timestamp)}
        </p>
      </div>
    </div>
  )
}

export default function ChatPage() {
  const router = useRouter()
  const pathname = usePathname()
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const [sessionUser, setSessionUser] = useState<SessionUser | null>(null)
  const [sessionId, setSessionId] = useState<string | null>(null)
  const [messages, setMessages] = useState<AiUiMessage[]>([])
  const [messageText, setMessageText] = useState('')
  const [pendingMessage, setPendingMessage] = useState<string | null>(null)
  const [selectedRoute, setSelectedRoute] = useState<AiRoute>('GENERAL')
  const [lastRoute, setLastRoute] = useState<AiRoute | null>(null)
  const [isCheckingSession, setIsCheckingSession] = useState(true)
  const [isLoadingHistory, setIsLoadingHistory] = useState(false)
  const [isSending, setIsSending] = useState(false)
  const [authError, setAuthError] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  const initializeSession = useCallback(async () => {
    setIsCheckingSession(true)
    setAuthError(null)
    clearLegacyAuthStorage()

    try {
      const session = await api.getSession()
      if (!session.authenticated || !session.user) {
        router.replace('/')
        return
      }

      const storedSessionId = readAiSessionId(
        localStorage.getItem(AI_SESSION_STORAGE_KEY)
      )
      const activeSessionId = storedSessionId || newSessionId()
      localStorage.setItem(AI_SESSION_STORAGE_KEY, activeSessionId)
      setSessionUser(session.user)
      setSessionId(activeSessionId)
    } catch (requestError) {
      if (requestError instanceof ApiError && [401, 403].includes(requestError.status)) {
        router.replace('/')
        return
      }
      setAuthError(messageError(requestError, 'Не удалось проверить сессию'))
    } finally {
      setIsCheckingSession(false)
    }
  }, [router])

  const loadHistory = useCallback(async (
    activeSessionId: string,
    showLoader = true
  ): Promise<AiUiMessage[] | null> => {
    if (showLoader) setIsLoadingHistory(true)

    try {
      const history = await api.getChatHistory(activeSessionId)
      const normalized = normalizeAiHistory(history.messages)
      setMessages(normalized)
      setError(null)
      return normalized
    } catch (requestError) {
      if (requestError instanceof ApiError && [401, 403].includes(requestError.status)) {
        router.replace('/')
        return null
      }
      setError(messageError(requestError, 'Не удалось загрузить историю'))
      return null
    } finally {
      if (showLoader) setIsLoadingHistory(false)
    }
  }, [router])

  useEffect(() => {
    void initializeSession()
  }, [initializeSession])

  useEffect(() => {
    if (sessionId) void loadHistory(sessionId)
  }, [loadHistory, sessionId])

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, pendingMessage])

  const sendMessage = useCallback(async (examplePrompt?: string) => {
    const text = (examplePrompt || messageText).trim()
    if (!text || !sessionId || !sessionUser || isSending) return

    setIsSending(true)
    setPendingMessage(text)
    setError(null)
    setMessageText('')

    try {
      const answer = await api.aiRequest<AiAnswer>('brain/answer', {
        method: 'POST',
        body: JSON.stringify(buildAiRequestPayload(sessionId, sessionUser.saas_user_id, text)),
      })
      setLastRoute(answer.route)
      setSelectedRoute(answer.route)

      const refreshedMessages = await loadHistory(sessionId, false)
      if (!refreshedMessages) {
        const now = new Date().toISOString()
        setMessages((current) => [
          ...current,
          { id: `local-user-${Date.now()}`, content: text, role: 'user', timestamp: now },
          { id: `local-ai-${Date.now()}`, content: answer.reply_text, role: 'assistant', timestamp: now },
        ])
        setError('Ответ получен, но историю не удалось обновить. Повторите загрузку.')
      }
    } catch (requestError) {
      setMessageText((current) => current || text)
      setError(messageError(requestError, 'Не удалось получить ответ AI'))
    } finally {
      setPendingMessage(null)
      setIsSending(false)
    }
  }, [isSending, loadHistory, messageText, sessionId, sessionUser])

  const startNewConversation = useCallback(() => {
    if (isSending) return
    const nextSessionId = newSessionId()
    localStorage.setItem(AI_SESSION_STORAGE_KEY, nextSessionId)
    setSessionId(nextSessionId)
    setMessages([])
    setMessageText('')
    setLastRoute(null)
    setError(null)
  }, [isSending])

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    void sendMessage()
  }

  const handleComposerKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault()
      void sendMessage()
    }
  }

  if (isCheckingSession) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-slate-50 px-4">
        <div className="text-center" role="status">
          <div className="mx-auto h-10 w-10 animate-spin rounded-full border-4 border-violet-200 border-t-primary-dark" />
          <p className="mt-4 text-sm font-medium text-slate-600">Подключаем AI workspace…</p>
        </div>
      </div>
    )
  }

  if (!sessionUser || !sessionId) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-slate-50 px-4">
        <div className="w-full max-w-md rounded-2xl border border-rose-200 bg-white p-6 text-center shadow-sm" role="alert">
          <h1 className="text-xl font-bold text-slate-900">Не удалось открыть AI workspace</h1>
          <p className="mt-2 text-sm text-slate-600">{authError || 'Авторизуйтесь и повторите попытку.'}</p>
          <button type="button" onClick={() => void initializeSession()} className="mt-5 rounded-xl bg-slate-950 px-4 py-2.5 text-sm font-semibold text-white hover:bg-slate-800">
            Повторить
          </button>
        </div>
      </div>
    )
  }

  const activeScenario = getAiScenario(selectedRoute)

  return (
    <div className="min-h-screen bg-slate-100">
      <Sidebar currentPath={pathname} />

      <div className="pb-20 pt-16 md:ml-64 md:pb-0 md:pt-0">
        <main className="mx-auto max-w-7xl p-3 sm:p-6 lg:p-8">
          <header className="relative overflow-hidden rounded-3xl bg-slate-950 px-5 py-6 text-white shadow-xl sm:px-7">
            <div className="absolute -right-16 -top-24 h-64 w-64 rounded-full bg-violet-500/30 blur-3xl" aria-hidden="true" />
            <div className="absolute -bottom-24 left-1/3 h-48 w-48 rounded-full bg-emerald-400/20 blur-3xl" aria-hidden="true" />
            <div className="relative flex flex-col gap-5 lg:flex-row lg:items-end lg:justify-between">
              <div className="max-w-2xl">
                <div className="mb-3 flex flex-wrap items-center gap-2">
                  <span className="rounded-full border border-violet-300/30 bg-violet-400/15 px-3 py-1 text-xs font-bold uppercase tracking-[0.16em] text-violet-100">
                    AI workspace
                  </span>
                  <span className="rounded-full border border-amber-300/40 bg-amber-300/10 px-3 py-1 text-xs font-semibold text-amber-100" role="status">
                    Синтетический demo
                  </span>
                </div>
                <h1 className="text-2xl font-bold tracking-tight sm:text-3xl">Проверьте AI-BRAIN прямо в интерфейсе</h1>
                <p className="mt-2 max-w-xl text-sm leading-6 text-slate-300">
                  Один запрос проходит маршрутизацию GENERAL, SALES или BARTER, а диалог сохраняется в PostgreSQL.
                </p>
              </div>
              <div className="grid grid-cols-2 gap-2 text-xs sm:flex">
                <div className="rounded-xl border border-white/10 bg-white/5 px-3 py-2">
                  <p className="text-slate-400">LLM</p>
                  <p className="mt-0.5 font-semibold text-white">deterministic mock</p>
                </div>
                <div className="rounded-xl border border-white/10 bg-white/5 px-3 py-2">
                  <p className="text-slate-400">Сессия</p>
                  <p className="mt-0.5 font-mono font-semibold text-white">…{sessionId.slice(-8)}</p>
                </div>
              </div>
            </div>
          </header>

          <div className="mt-5 grid gap-5 xl:grid-cols-[minmax(0,1fr)_18rem]">
            <div className="min-w-0 space-y-4">
              <section aria-labelledby="scenario-heading">
                <div className="mb-2 flex items-center justify-between gap-3">
                  <h2 id="scenario-heading" className="text-sm font-bold text-slate-900">Проверочный сценарий</h2>
                  <span className="text-xs text-slate-500">Нажмите, чтобы подставить пример</span>
                </div>
                <div className="grid gap-2 sm:grid-cols-3">
                  {AI_SCENARIOS.map((scenario) => {
                    const isSelected = selectedRoute === scenario.route
                    return (
                      <button
                        key={scenario.route}
                        type="button"
                        aria-pressed={isSelected}
                        onClick={() => {
                          setSelectedRoute(scenario.route)
                          setMessageText(scenario.prompt)
                        }}
                        className={`rounded-2xl border p-3 text-left transition-all hover:-translate-y-0.5 hover:shadow-sm ${
                          isSelected
                            ? 'border-slate-900 bg-white ring-2 ring-slate-900/10'
                            : 'border-slate-200 bg-white/70 hover:border-slate-300'
                        }`}
                      >
                        <div className="flex items-center justify-between gap-2">
                          <RouteBadge route={scenario.route} />
                          {isSelected && <span className="text-xs font-bold text-slate-900">Выбран</span>}
                        </div>
                        <p className="mt-2 text-sm font-semibold text-slate-900">{scenario.label}</p>
                        <p className="mt-0.5 text-xs leading-5 text-slate-500">{scenario.description}</p>
                      </button>
                    )
                  })}
                </div>
              </section>

              <section className="overflow-hidden rounded-3xl border border-slate-200 bg-white shadow-sm" aria-label="Диалог с AI">
                <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-200 px-4 py-3 sm:px-5">
                  <div>
                    <div className="flex items-center gap-2">
                      <h2 className="font-bold text-slate-900">AI-ассистент</h2>
                      {lastRoute ? <RouteBadge route={lastRoute} /> : (
                        <span className="rounded-full bg-slate-100 px-2.5 py-1 text-[11px] font-semibold text-slate-600">Готов к маршрутизации</span>
                      )}
                    </div>
                    <p className="mt-0.5 text-xs text-slate-500">Маршрут выбирает backend по тексту запроса.</p>
                  </div>
                  <button
                    type="button"
                    onClick={startNewConversation}
                    disabled={isSending}
                    className="rounded-xl border border-slate-200 px-3 py-2 text-xs font-semibold text-slate-700 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    Новый диалог
                  </button>
                </div>

                {error && (
                  <div className="mx-4 mt-4 flex items-start justify-between gap-3 rounded-xl border border-rose-200 bg-rose-50 px-3 py-2.5 text-sm text-rose-800" role="alert" aria-live="polite">
                    <p>{error}</p>
                    <button type="button" onClick={() => void loadHistory(sessionId)} className="flex-shrink-0 font-bold underline decoration-rose-300 underline-offset-2">
                      Повторить
                    </button>
                  </div>
                )}

                <div className="h-[430px] overflow-y-auto bg-slate-50/70 px-4 py-5 sm:h-[500px] sm:px-5">
                  {isLoadingHistory ? (
                    <div className="space-y-5" role="status" aria-label="Загрузка истории">
                      <div className="h-20 w-3/5 animate-pulse rounded-2xl bg-slate-200" />
                      <div className="ml-auto h-16 w-2/5 animate-pulse rounded-2xl bg-violet-200" />
                    </div>
                  ) : messages.length === 0 && !pendingMessage ? (
                    <div className="flex h-full items-center justify-center">
                      <div className="max-w-xl text-center">
                        <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-2xl bg-slate-950 text-white shadow-lg" aria-hidden="true">
                          <svg className="h-6 w-6" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                            <path strokeLinecap="round" strokeLinejoin="round" d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2h-5l-5 4v-4Z" />
                          </svg>
                        </div>
                        <h3 className="mt-4 text-lg font-bold text-slate-900">Задайте первый вопрос</h3>
                        <p className="mt-1 text-sm leading-6 text-slate-500">Напишите свой запрос или запустите детерминированный пример {selectedRoute}.</p>
                        <button
                          type="button"
                          onClick={() => void sendMessage(activeScenario.prompt)}
                          className="mt-4 rounded-xl bg-slate-950 px-4 py-2.5 text-sm font-semibold text-white shadow-sm hover:bg-slate-800"
                        >
                          Запустить пример {selectedRoute}
                        </button>
                      </div>
                    </div>
                  ) : (
                    <div className="space-y-5" aria-live="polite">
                      {messages.map((message) => <MessageBubble key={message.id} message={message} />)}
                      {pendingMessage && (
                        <>
                          <MessageBubble message={{
                            id: 'pending-user',
                            content: pendingMessage,
                            role: 'user',
                            timestamp: new Date().toISOString(),
                          }} />
                          <div className="flex items-center gap-3 text-sm text-slate-500" role="status">
                            <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-slate-950 text-white" aria-hidden="true">AI</div>
                            <div className="flex items-center gap-1 rounded-2xl border border-slate-200 bg-white px-4 py-3 shadow-sm">
                              {[0, 1, 2].map((index) => (
                                <span key={index} className="h-2 w-2 animate-bounce rounded-full bg-slate-400" style={{ animationDelay: `${index * 120}ms` }} />
                              ))}
                              <span className="ml-2">Анализирую запрос…</span>
                            </div>
                          </div>
                        </>
                      )}
                      <div ref={messagesEndRef} />
                    </div>
                  )}
                </div>

                <form onSubmit={handleSubmit} className="border-t border-slate-200 bg-white p-3 sm:p-4">
                  <label htmlFor="ai-message" className="sr-only">Сообщение AI-ассистенту</label>
                  <div className="flex items-end gap-2 rounded-2xl border border-slate-200 bg-slate-50 p-2 focus-within:border-violet-400 focus-within:ring-2 focus-within:ring-violet-100">
                    <textarea
                      id="ai-message"
                      value={messageText}
                      onChange={(event) => setMessageText(event.target.value)}
                      onKeyDown={handleComposerKeyDown}
                      disabled={isSending}
                      maxLength={12_000}
                      rows={2}
                      placeholder="Например: сколько стоит размещение?"
                      className="max-h-36 min-h-[48px] flex-1 resize-none bg-transparent px-2 py-2 text-sm leading-6 text-slate-900 outline-none placeholder:text-slate-400 disabled:cursor-not-allowed"
                    />
                    <button
                      type="submit"
                      disabled={!messageText.trim() || isSending}
                      className="flex h-11 w-11 flex-shrink-0 items-center justify-center rounded-xl bg-primary-dark text-white shadow-sm transition-colors hover:bg-violet-800 disabled:cursor-not-allowed disabled:bg-slate-300"
                      aria-label="Отправить сообщение"
                    >
                      <svg className="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                        <path strokeLinecap="round" strokeLinejoin="round" d="m22 2-7 20-4-9-9-4 20-7Z" />
                        <path strokeLinecap="round" strokeLinejoin="round" d="M22 2 11 13" />
                      </svg>
                    </button>
                  </div>
                  <div className="mt-2 flex items-center justify-between gap-3 px-1 text-[11px] text-slate-400">
                    <span>Enter — отправить, Shift+Enter — новая строка</span>
                    <span>{messageText.length}/12000</span>
                  </div>
                </form>
              </section>
            </div>

            <aside className="space-y-4" aria-label="О демо-контуре">
              <section className="rounded-2xl border border-amber-200 bg-amber-50 p-4">
                <div className="flex items-center gap-2 text-amber-900">
                  <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-amber-200 font-bold" aria-hidden="true">D</span>
                  <h2 className="font-bold">Честный demo-режим</h2>
                </div>
                <p className="mt-3 text-xs leading-5 text-amber-900">
                  Mock AI детерминированно выбирает агента и сохраняет историю. RAG и live tools в этом режиме не запускаются.
                </p>
              </section>

              <section className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
                <h2 className="text-sm font-bold text-slate-900">Что здесь проверяется</h2>
                <ol className="mt-3 space-y-3 text-xs leading-5 text-slate-600">
                  <li className="flex gap-2"><span className="font-bold text-slate-900">01</span><span>Same-origin BFF без JWT в browser JavaScript.</span></li>
                  <li className="flex gap-2"><span className="font-bold text-slate-900">02</span><span>LangGraph route GENERAL, SALES или BARTER.</span></li>
                  <li className="flex gap-2"><span className="font-bold text-slate-900">03</span><span>Tenant-scoped история после каждого ответа.</span></li>
                </ol>
              </section>

              <section className="rounded-2xl border border-slate-200 bg-slate-900 p-4 text-white shadow-sm">
                <p className="text-xs font-bold uppercase tracking-[0.14em] text-emerald-300">Telegram adapter</p>
                <h2 className="mt-2 text-sm font-bold">Synthetic, read-only</h2>
                <p className="mt-2 text-xs leading-5 text-slate-300">
                  Адаптер проверяется отдельным smoke-сценарием и не является RAG-вызовом mock AI.
                </p>
              </section>
            </aside>
          </div>
        </main>
      </div>
    </div>
  )
}
