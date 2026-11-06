'use client'

import { useEffect, useState } from 'react'
import { useRouter, usePathname } from 'next/navigation'
import { SidebarNav } from './SidebarNav'
import { UserAvatar } from './UserAvatar'
import { api } from '@/lib/api'
import { clearLegacyAuthStorage } from '@/lib/auth-client'

interface SidebarProps {
  currentPath?: string
  onNavigate?: (path: string) => void
}

export const Sidebar = ({ currentPath: customPath, onNavigate }: SidebarProps) => {
  const router = useRouter()
  const pathname = usePathname()
  const [username, setUsername] = useState('Пользователь')
  
  const currentPath = customPath || pathname

  useEffect(() => {
    let active = true
    api.getSession()
      .then((session) => {
        if (active && session.authenticated && session.user?.username) {
          setUsername(session.user.username)
        }
      })
      .catch(() => undefined)

    return () => {
      active = false
    }
  }, [])

  const handleNavigate = (path: string) => {
    if (onNavigate) {
      onNavigate(path)
    } else {
      router.push(path)
    }
  }

  const handleLogout = async () => {
    await api.logout().catch(() => undefined)
    clearLegacyAuthStorage()
    localStorage.removeItem('savedEmail')
    router.replace('/')
  }

  return (
    <>
      <aside className="fixed left-0 top-0 z-30 hidden h-full w-64 flex-col overflow-hidden bg-background-card py-6 shadow-sm md:flex">
        <div className="mb-8 flex items-center justify-start gap-4 px-4">
          <div className="h-12 w-12 flex-shrink-0 rounded-full bg-gradient-to-br from-blue-500 to-green-500" />
          <span className="whitespace-nowrap text-lg font-bold text-text-primary">
            Telegram Analytics
          </span>
        </div>

        <SidebarNav currentPath={currentPath} onNavigate={handleNavigate} />

        <div className="border-t border-gray-100 pt-4">
          <UserAvatar name={username} username="Авторизованная сессия" />
          <button
            type="button"
            onClick={handleLogout}
            className="mx-4 mt-3 block rounded-button border border-gray-200 px-3 py-2 text-sm font-medium text-text-secondary hover:bg-gray-100 hover:text-text-primary"
          >
            Выйти
          </button>
        </div>
      </aside>

      <header className="fixed inset-x-0 top-0 z-40 flex h-16 items-center justify-between border-b border-gray-200 bg-background-card px-4 shadow-sm md:hidden">
        <div className="flex min-w-0 items-center gap-3">
          <div className="h-9 w-9 flex-shrink-0 rounded-full bg-gradient-to-br from-blue-500 to-green-500" />
          <div className="min-w-0">
            <p className="truncate text-sm font-bold text-text-primary">Telegram Analytics</p>
            <p className="truncate text-xs text-text-secondary">{username}</p>
          </div>
        </div>
        <button
          type="button"
          onClick={handleLogout}
          className="ml-3 flex-shrink-0 rounded-button border border-gray-200 px-3 py-2 text-xs font-medium text-text-secondary hover:bg-gray-100 hover:text-text-primary"
        >
          Выйти
        </button>
      </header>

      <div className="fixed inset-x-0 bottom-0 z-40 h-16 border-t border-gray-200 bg-background-card shadow-[0_-4px_16px_rgba(15,23,42,0.08)] md:hidden">
        <SidebarNav currentPath={currentPath} onNavigate={handleNavigate} mobile />
      </div>
    </>
  )
}
