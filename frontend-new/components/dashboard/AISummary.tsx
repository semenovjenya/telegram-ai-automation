import type { AISummaryItem } from '@/lib/types/dashboard'

interface AISummaryProps {
  items: AISummaryItem[]
}

export const AISummary = ({ items }: AISummaryProps) => {
  return (
    <div className="bg-background-card rounded-card shadow-lg p-6">
      <div className="flex items-center gap-2 mb-4">
        <svg className="w-5 h-5 text-primary-DEFAULT" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 3v4M3 5h4M6 17v4m-2-2h4m5-16l2.286 6.857L21 12l-5.714 2.143L13 21l-2.286-6.857L5 12l5.714-2.143L13 3z" />
        </svg>
        <h3 className="text-lg font-bold text-text-primary">Сводка по данным</h3>
      </div>
      <ul className="space-y-3">
        {items.map((item) => (
          <li key={item.id} className="flex items-start gap-3">
            <svg className="w-5 h-5 text-success-DEFAULT flex-shrink-0 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
            </svg>
            <p className="text-sm text-text-primary">{item.text}</p>
          </li>
        ))}
      </ul>
    </div>
  )
}
