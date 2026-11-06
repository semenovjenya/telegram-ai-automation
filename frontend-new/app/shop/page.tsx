'use client'

import { useCallback, useEffect, useState } from 'react'
import { usePathname, useRouter } from 'next/navigation'
import { Sidebar } from '@/components/layout/Sidebar'
import { ShopView } from '@/components/dashboard/ShopView'
import { api } from '@/lib/api'
import type { ChannelsPayload, RecommendationSource } from '@/lib/types/barter'
import type { Channel } from '@/lib/types/dashboard'

export default function ShopPage() {
  const router = useRouter()
  const pathname = usePathname()
  const [isAuthenticated, setIsAuthenticated] = useState(false)
  const [channels, setChannels] = useState<Channel[]>([])
  const [source, setSource] = useState<RecommendationSource | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const loadChannels = useCallback(async () => {
    setIsLoading(true)
    setError(null)

    try {
      const response = await fetch('/api/barter/channels', {
        credentials: 'same-origin',
        cache: 'no-store',
      })
      const payload = await response.json().catch(() => ({})) as Partial<ChannelsPayload>

      if (response.status === 401 || response.status === 403) {
        router.replace('/')
        return
      }

      setChannels(Array.isArray(payload.channels) ? payload.channels : [])
      setSource(payload.source ?? null)

      if (!response.ok) {
        setError(
          payload.source?.type === 'live_unconfigured'
            ? 'Для live-режима ещё не настроен аутентифицированный источник рекомендаций.'
            : 'Источник рекомендаций недоступен.'
        )
      }
    } catch {
      setChannels([])
      setSource(null)
      setError('Не удалось загрузить рекомендации')
    } finally {
      setIsLoading(false)
    }
  }, [router])

  useEffect(() => {
    let active = true
    api.getSession()
      .then((session) => {
        if (!active) return
        if (!session.authenticated) {
          router.replace('/')
          return
        }
        setIsAuthenticated(true)
        return loadChannels()
      })
      .catch(() => {
        if (active) router.replace('/')
      })

    return () => {
      active = false
    }
  }, [loadChannels, router])

  if (!isAuthenticated) return null

  return (
    <div className="min-h-screen bg-background-light">
      <Sidebar currentPath={pathname} />
      <div className="pb-16 pt-16 md:ml-64 md:pb-0 md:pt-0">
        <header className="bg-background-card px-4 py-5 shadow-sm sm:px-6 lg:px-8 lg:py-6">
          <h1 className="text-2xl font-bold text-text-primary">Рекомендации каналов</h1>
          <p className="mt-1 text-text-secondary">Подбор каналов для партнёрств и взаимного продвижения.</p>
        </header>
        <main className="p-4 sm:p-6 lg:p-8">
          <ShopView
            channels={channels}
            source={source}
            isLoading={isLoading}
            error={error}
            onRefresh={loadChannels}
          />
        </main>
      </div>
    </div>
  )
}






