'use client'

import { useState, useEffect } from 'react'
import { useRouter } from 'next/navigation'
import { api } from '@/lib/api'
import { clearLegacyAuthStorage } from '@/lib/auth-client'

const LoginPage = () => {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [rememberMe, setRememberMe] = useState(false)
  const [isCheckingSession, setIsCheckingSession] = useState(true)
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState('')
  const router = useRouter()

  // Загрузка сохраненного email при монтировании. Пароль никогда не сохраняется.
  useEffect(() => {
    clearLegacyAuthStorage()
    const savedEmail = localStorage.getItem('savedEmail')
    if (savedEmail) {
      setUsername(savedEmail)
      setRememberMe(true)
    }

    let active = true
    api.getSession()
      .then((session) => {
        if (active && session.authenticated) {
          router.replace('/dashboard')
        }
      })
      .catch(() => {
        // The login form remains available when the session service is offline.
      })
      .finally(() => {
        if (active) {
          setIsCheckingSession(false)
        }
      })

    return () => {
      active = false
    }
  }, [router])

  const handleSubmit = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault()
    setError('')
    setIsLoading(true)

    try {
      // Авторизация через API
      await api.login(username, password)
      
      // Сохраняем только email. Пароль остается исключительно в состоянии формы.
      if (rememberMe) {
        localStorage.setItem('savedEmail', username)
      } else {
        localStorage.removeItem('savedEmail')
      }
      // Редирект на dashboard
      router.replace('/dashboard')
    } catch (error) {
      setError(error instanceof Error ? error.message : 'Неверный email или пароль')
    } finally {
      setIsLoading(false)
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-background-light px-4">
      <div className="w-full max-w-md">
        <div className="bg-background-card rounded-card shadow-lg p-8">
          {/* Logo/Header */}
          <div className="text-center mb-8">
            <div className="inline-flex items-center justify-center w-20 h-20 rounded-card bg-avatar-bg mb-4 relative">
              {/* Декоративные элементы как в референсе */}
              <div className="absolute top-1 left-1 w-3 h-3 bg-success-DEFAULT rounded-full opacity-60"></div>
              <div className="absolute bottom-1 right-1 w-3 h-3 bg-success-DEFAULT rounded-full opacity-60"></div>
              <svg
                className="w-10 h-10 text-primary-DEFAULT relative z-10"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M13 10V3L4 14h7v7l9-11h-7z"
                />
              </svg>
            </div>
            <h1 className="text-3xl font-bold text-text-primary mb-2">
              Добро пожаловать
            </h1>
            <p className="text-text-secondary">
              Войдите в свой аккаунт
            </p>
          </div>

          {/* Login Form */}
          <form onSubmit={handleSubmit} className="space-y-6">
            {error && (
              <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-button text-sm">
                {error}
              </div>
            )}
            
            <div>
              <label
                htmlFor="username"
                className="block text-sm font-medium text-text-primary mb-2"
              >
                Логин
              </label>
              <input
                id="username"
                type="text"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                required
                className="w-full px-4 py-3 rounded-button border border-gray-200 focus:outline-none focus:ring-2 focus:ring-primary-DEFAULT focus:border-transparent transition-all"
                placeholder="Введите логин"
                aria-label="Логин"
              />
            </div>

            <div>
              <label
                htmlFor="password"
                className="block text-sm font-medium text-text-primary mb-2"
              >
                Пароль
              </label>
              <input
                id="password"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                className="w-full px-4 py-3 rounded-button border border-gray-200 focus:outline-none focus:ring-2 focus:ring-primary-DEFAULT focus:border-transparent transition-all"
                placeholder="••••••••"
                aria-label="Пароль"
              />
            </div>

            <div className="flex items-center">
              <label className="flex items-center cursor-pointer">
                <input
                  type="checkbox"
                  checked={rememberMe}
                  onChange={(e) => setRememberMe(e.target.checked)}
                  className="w-4 h-4 text-primary-DEFAULT border-gray-300 rounded focus:ring-primary-DEFAULT cursor-pointer"
                />
                <span className="ml-2 text-sm text-text-secondary">
                  Запомнить логин
                </span>
              </label>
            </div>

            <button
              type="submit"
              disabled={isLoading || isCheckingSession}
              className="w-full bg-primary-DEFAULT hover:bg-primary-dark text-white font-medium py-3 px-4 rounded-button transition-all duration-200 disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
              aria-label="Войти в систему"
            >
              {isLoading || isCheckingSession ? (
                <>
                  <svg
                    className="animate-spin h-5 w-5 text-white"
                    xmlns="http://www.w3.org/2000/svg"
                    fill="none"
                    viewBox="0 0 24 24"
                  >
                    <circle
                      className="opacity-25"
                      cx="12"
                      cy="12"
                      r="10"
                      stroke="currentColor"
                      strokeWidth="4"
                    ></circle>
                    <path
                      className="opacity-75"
                      fill="currentColor"
                      d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
                    ></path>
                  </svg>
                  {isCheckingSession ? 'Проверка сессии...' : 'Вход...'}
                </>
              ) : (
                <>
                  <svg
                    className="w-4 h-4"
                    fill="none"
                    stroke="currentColor"
                    viewBox="0 0 24 24"
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth={2}
                      d="M11 16l-4-4m0 0l4-4m-4 4h14m-5 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h7a3 3 0 013 3v1"
                    />
                  </svg>
                  Войти
                </>
              )}
            </button>
          </form>

          <p className="mt-6 text-center text-sm text-text-secondary">
            Данные локального demo-аккаунта указаны в README.
          </p>
        </div>
      </div>
    </div>
  )
}

export default LoginPage
