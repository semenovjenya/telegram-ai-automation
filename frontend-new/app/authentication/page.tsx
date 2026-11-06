'use client'

import { useEffect } from 'react'
import { useRouter } from 'next/navigation'
import { api } from '@/lib/api'
import { clearLegacyAuthStorage } from '@/lib/auth-client'

const AuthenticationPage = () => {
  const router = useRouter()

  useEffect(() => {
    clearLegacyAuthStorage()
    let active = true
    let timer: ReturnType<typeof setTimeout> | undefined

    api.getSession()
      .then((session) => {
        if (!active) return
        if (!session.authenticated) {
          router.replace('/')
          return
        }
        timer = setTimeout(() => {
          router.replace('/dashboard')
        }, 2000)
      })
      .catch(() => {
        if (active) {
          router.replace('/')
        }
      })

    return () => {
      active = false
      if (timer) clearTimeout(timer)
    }
  }, [router])

  const handleLogout = async () => {
    await api.logout().catch(() => undefined)
    clearLegacyAuthStorage()
    localStorage.removeItem('savedEmail')
    router.replace('/')
  }

  const handleGoToDashboard = () => {
    router.push('/dashboard')
  }

  return (
    <div className="min-h-screen bg-background-light p-8">
      <div className="max-w-7xl mx-auto">
        <div className="flex items-center justify-between mb-8">
          <h1 className="text-3xl font-bold text-text-primary">
            Authentication
          </h1>
          <button
            onClick={handleLogout}
            className="px-4 py-2 bg-red-500 hover:bg-red-600 text-white rounded-button transition-colors"
            aria-label="Выйти из системы"
          >
            Выйти
          </button>
        </div>
        <div className="bg-background-card rounded-card shadow-lg p-8">
          <div className="text-center mb-8">
            <div className="inline-flex items-center justify-center w-20 h-20 rounded-card bg-success-light mb-4">
              <svg className="w-10 h-10 text-success-DEFAULT" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
            </div>
            <h2 className="text-2xl font-bold text-text-primary mb-2">
              Авторизация успешна!
            </h2>
            <p className="text-text-secondary">
              Вы успешно вошли в систему
            </p>
          </div>
          
          <div className="flex justify-center">
            <button
              onClick={handleGoToDashboard}
              className="px-6 py-3 bg-primary-DEFAULT hover:bg-primary-dark text-white font-medium rounded-button transition-all duration-200 flex items-center gap-2"
              aria-label="Перейти на Dashboard"
            >
              <span>Перейти на Dashboard</span>
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 7l5 5m0 0l-5 5m5-5H6" />
              </svg>
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}

export default AuthenticationPage
