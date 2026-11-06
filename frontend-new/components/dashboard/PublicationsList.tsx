import type { Publication } from '@/lib/types/dashboard'

interface PublicationsListProps {
  publications: Publication[]
}

export const PublicationsList = ({ publications }: PublicationsListProps) => {
  return (
    <div className="bg-background-card rounded-card shadow-lg p-6">
      <h3 className="text-lg font-bold text-text-primary mb-4">Лучшие публикации</h3>
      <div className="space-y-4">
        {publications.map((item) => (
          <div key={item.id} className="flex items-start gap-3 pb-4 border-b border-gray-100 last:border-0 last:pb-0">
            <div className="w-12 h-12 rounded-button bg-gray-200 flex items-center justify-center flex-shrink-0">
              <svg className="w-6 h-6 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" />
              </svg>
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-sm font-medium text-text-primary mb-1 truncate">{item.title}</p>
              <p className="text-xs text-text-secondary">{item.views} • {item.timeAgo}</p>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
