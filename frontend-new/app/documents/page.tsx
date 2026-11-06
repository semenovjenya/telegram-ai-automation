'use client'

import { useEffect, useState } from 'react'
import { usePathname, useRouter } from 'next/navigation'
import { Sidebar } from '@/components/layout/Sidebar'
import { api } from '@/lib/api'

export default function DocumentsPage() {
  const router = useRouter()
  const pathname = usePathname()
  const [isAuthenticated, setIsAuthenticated] = useState(false)

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
      })
      .catch(() => {
        if (active) router.replace('/')
      })

    return () => {
      active = false
    }
  }, [router])

  if (!isAuthenticated) return null

  return (
    <div className="min-h-screen bg-background-light">
      <Sidebar currentPath={pathname} />
      <div className="pb-16 pt-16 md:ml-64 md:pb-0 md:pt-0">
        <header className="bg-background-card px-4 py-5 shadow-sm sm:px-6 lg:px-8 lg:py-6">
          <h1 className="text-2xl font-bold text-text-primary">Документы</h1>
          <p className="mt-1 text-text-secondary">Сохранённые отчёты и экспорты аналитики.</p>
        </header>
        <main className="p-4 sm:p-6 lg:p-8">
          <section className="rounded-card border border-gray-200 bg-background-card p-6 text-center shadow-sm sm:p-8">
            <svg className="mx-auto h-12 w-12 text-text-secondary" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
            </svg>
            <h2 className="mt-4 text-lg font-bold text-text-primary">Документов пока нет</h2>
            <p className="mx-auto mt-2 max-w-xl text-sm text-text-secondary">
              Здесь появятся сформированные отчёты, когда backend экспорта будет подключён. Интерфейс не подставляет демо-документы.
            </p>
          </section>
        </main>
      </div>
    </div>
  )
}
