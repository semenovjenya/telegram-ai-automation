'use client'

import { useEffect, useState, useCallback } from 'react'
import { useRouter, usePathname } from 'next/navigation'
import { api, ApiError } from '@/lib/api'
import type { DashboardData } from '@/lib/types/dashboard'
import { Sidebar } from '@/components/layout/Sidebar'
import { DashboardHeader } from '@/components/dashboard/DashboardHeader'
import { ProfileCard } from '@/components/dashboard/ProfileCard'
import { MetricsGrid } from '@/components/dashboard/MetricsGrid'
import { AIRecommendationBar } from '@/components/dashboard/AIRecommendationBar'
import { ActivityChart } from '@/components/dashboard/ActivityChart'
import { PublicationsList } from '@/components/dashboard/PublicationsList'
import { AISummary } from '@/components/dashboard/AISummary'
import { NotificationsList } from '@/components/dashboard/NotificationsList'

const DashboardPage = () => {
  const router = useRouter()
  const pathname = usePathname()
  const [dashboardData, setDashboardData] = useState<DashboardData | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const loadDashboardData = useCallback(async () => {
    try {
      setIsLoading(true)
      setError(null)
      const data = await api.getDashboardData()
      setDashboardData(data)
    } catch (err) {
      setDashboardData(null)
      if (err instanceof ApiError && [401, 403].includes(err.status)) {
        router.replace('/')
        return
      }

      const status = err instanceof ApiError ? ` (код ${err.status})` : ''
      setError(`Сервис аналитики не вернул данные${status}. Демо-показатели не подставляются.`)
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
        return loadDashboardData()
      })
      .catch((sessionError) => {
        if (!active) return
        setError(sessionError instanceof Error ? sessionError.message : 'Не удалось проверить сессию')
        setIsLoading(false)
      })

    return () => {
      active = false
    }
  }, [router, loadDashboardData])

  return (
    <div className="min-h-screen bg-background-light relative">
      {/* Sidebar */}
      <Sidebar currentPath={pathname} />

      {/* Main Content */}
      <div className="pb-16 pt-16 md:ml-64 md:pb-0 md:pt-0">
        {/* Header */}
        <DashboardHeader />

        {/* Content */}
        <main className="p-4 sm:p-6 lg:p-8">
          {isLoading ? (
            <div className="flex items-center justify-center h-64">
              <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary-DEFAULT"></div>
            </div>
          ) : error ? (
            <div className="rounded-card border border-amber-300 bg-amber-50 p-6" role="alert">
              <h2 className="text-lg font-bold text-amber-950">Dashboard работает в ограниченном режиме</h2>
              <p className="mb-4 mt-2 text-amber-900">{error}</p>
              <button onClick={loadDashboardData} className="rounded-button bg-amber-700 px-4 py-2 text-white hover:bg-amber-800">
                Попробовать снова
              </button>
            </div>
          ) : dashboardData ? (
            <>
              {dashboardData.data_source === 'synthetic-demo' && (
                <div className="mb-6 rounded-card border-2 border-amber-400 bg-amber-100 p-4 text-amber-950" role="status">
                  <p className="font-bold">Демо-режим: показаны синтетические данные</p>
                  <p className="mt-1 text-sm">Эти показатели предназначены только для демонстрации интерфейса.</p>
                </div>
              )}

              {/* Top Section: Profile Card and Metrics */}
              <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 mb-6">
                <ProfileCard
                  username={dashboardData.profile.username}
                  url={dashboardData.profile.url}
                />
                <MetricsGrid metrics={dashboardData.metrics} />
              </div>

              {/* AI Recommendation Bar */}
              <AIRecommendationBar recommendation={dashboardData.aiRecommendation} />

              {/* Combined Chart Section */}
              <ActivityChart data={dashboardData.activity} />

              {/* Bottom Section: Three Columns */}
              <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                <PublicationsList publications={dashboardData.publications} />
                <AISummary items={dashboardData.aiSummary} />
                <NotificationsList notifications={dashboardData.notifications} />
              </div>
            </>
          ) : null}
        </main>
      </div>
    </div>
  )
}

export default DashboardPage
