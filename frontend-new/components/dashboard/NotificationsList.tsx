import type { Notification } from '@/lib/types/dashboard'

interface NotificationsListProps {
  notifications: Notification[]
}

const NotificationIcon = ({ icon }: { icon: Notification['icon'] }) => {
  const iconMap = {
    megaphone: (
      <svg className="w-5 h-5 text-primary-DEFAULT" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M11 5.882V19.24a1.76 1.76 0 01-3.417.592l-2.147-6.15M18 13a3 3 0 100-6M5.436 13.683A4.001 4.001 0 017 6h1.832c4.1 0 7.625-1.234 9.168-3v14c-1.543-1.766-5.067-3-9.168-3H7a3.988 3.988 0 01-1.564-.317z" />
      </svg>
    ),
    chart: (
      <svg className="w-5 h-5 text-success-DEFAULT" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
      </svg>
    ),
    lightning: (
      <svg className="w-5 h-5 text-yellow-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
      </svg>
    )
  }

  const bgColorMap = {
    megaphone: 'bg-primary-light',
    chart: 'bg-success-light',
    lightning: 'bg-yellow-100'
  }

  return (
    <div className={`w-8 h-8 rounded-button flex items-center justify-center flex-shrink-0 ${bgColorMap[icon]}`}>
      {iconMap[icon]}
    </div>
  )
}

export const NotificationsList = ({ notifications }: NotificationsListProps) => {
  return (
    <div className="bg-background-card rounded-card shadow-lg p-6">
      <h3 className="text-lg font-bold text-text-primary mb-4">Последние уведомления</h3>
      <div className="space-y-4">
        {notifications.map((notification, index) => (
          <div 
            key={notification.id} 
            className={`flex items-start gap-3 ${index < notifications.length - 1 ? 'pb-4 border-b border-gray-100' : ''}`}
          >
            <NotificationIcon icon={notification.icon} />
            <div className="flex-1 min-w-0">
              <p className="text-sm text-text-primary mb-1">{notification.text}</p>
              <p className="text-xs text-text-secondary">{notification.timeAgo}</p>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
