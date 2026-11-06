import { formatNumber as defaultFormatNumber, formatChange } from '@/lib/utils/format'

interface MetricsCardProps {
  label: string
  value: number | string
  changePercent: number | null
  formatNumber?: (num: number | string) => string
  suffix?: string
}

export const MetricsCard = ({ 
  label, 
  value, 
  changePercent, 
  formatNumber = defaultFormatNumber,
  suffix = ''
}: MetricsCardProps) => {
  const isPositive = changePercent !== null && changePercent >= 0
  
  return (
    <div className="bg-background-card rounded-card shadow-lg p-6">
      <p className="text-sm text-text-secondary mb-2">{label}</p>
      <div className="flex items-center justify-between">
        <p className="text-2xl font-bold text-text-primary">
          {formatNumber(value)}{suffix}
        </p>
        {changePercent !== null && (
          <div className={`flex items-center gap-1 ${isPositive ? 'text-success-DEFAULT' : 'text-red-500'}`}>
            <span className="text-sm font-medium">
              {formatChange(changePercent)}
            </span>
            {isPositive ? (
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 10l7-7m0 0l7 7m-7-7v18" />
              </svg>
            ) : (
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 14l-7 7m0 0l-7-7m7 7V3" />
              </svg>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
