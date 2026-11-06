'use client'

interface NavItem {
  path: string
  label: string
  icon: React.ReactNode
}

interface SidebarNavProps {
  currentPath: string
  onNavigate: (path: string) => void
  mobile?: boolean
}

const navItems: NavItem[] = [
  {
    path: '/dashboard',
    label: 'Dashboard',
    icon: (
      <svg className="w-6 h-6 flex-shrink-0" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" d="M4 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2V6zM14 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2V6zM4 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2v-2zM14 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2v-2z" />
      </svg>
    )
  },
  {
    path: '/documents',
    label: 'Документы',
    icon: (
      <svg className="w-6 h-6 flex-shrink-0" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
      </svg>
    )
  },
  {
    path: '/shop',
    label: 'Магазин',
    icon: (
      <svg className="w-6 h-6 flex-shrink-0" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" d="M16 11V7a4 4 0 00-8 0v4M5 9h14l1 12H4L5 9z" />
      </svg>
    )
  },
  {
    path: '/chat',
    label: 'AI-ассистент',
    icon: (
      <svg className="w-6 h-6 flex-shrink-0" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
      </svg>
    )
  }
]

export const SidebarNav = ({
  currentPath,
  onNavigate,
  mobile = false,
}: SidebarNavProps) => {
  const handleClick = (path: string) => {
    onNavigate(path)
  }

  const handleKeyDown = (e: React.KeyboardEvent, path: string) => {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault()
      handleClick(path)
    }
  }

  return (
    <nav
      aria-label={mobile ? 'Мобильная навигация' : 'Основная навигация'}
      className={mobile ? 'grid h-full grid-cols-4' : 'flex flex-1 flex-col gap-2 px-2'}
    >
      {navItems.map((item) => {
        const isActive = currentPath === item.path || currentPath.startsWith(item.path)
        
        return (
          <button
            key={item.path}
            onClick={() => handleClick(item.path)}
            onKeyDown={(e) => handleKeyDown(e, item.path)}
            className={`relative flex w-full items-center transition-colors ${
              mobile
                ? 'h-full min-w-0 flex-col justify-center gap-1 px-1 py-2'
                : 'h-12 justify-start gap-3 rounded-button px-3'
            } ${
              isActive
                ? mobile
                  ? 'bg-primary-light text-primary-dark'
                  : 'bg-gray-100 text-text-primary'
                : 'text-text-secondary hover:bg-gray-100'
            }`}
            aria-label={item.label}
            tabIndex={0}
          >
            {item.icon}
            <span className={`${mobile ? 'max-w-full truncate text-[11px]' : 'whitespace-nowrap text-sm'} font-medium`}>
              {item.label}
            </span>
            {isActive && (
              <div
                className={mobile
                  ? 'absolute inset-x-3 top-0 h-1 rounded-b bg-primary-DEFAULT'
                  : 'absolute bottom-0 left-0 top-0 w-1 rounded-r bg-primary-DEFAULT'}
              />
            )}
          </button>
        )
      })}
    </nav>
  )
}
