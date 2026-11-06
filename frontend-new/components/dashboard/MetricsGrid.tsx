import { MetricsCard } from './MetricsCard'
import type { Metric } from '@/lib/types/dashboard'

interface MetricsGridProps {
  metrics: {
    subscribers: Metric
    engagement: Metric
    postsPerDay: Metric
    averageViews: Metric
  }
}

export const MetricsGrid = ({ metrics }: MetricsGridProps) => {
  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:col-span-2">
      <MetricsCard
        label="Подписчики"
        value={metrics.subscribers.value}
        changePercent={metrics.subscribers.changePercent}
      />

      <MetricsCard
        label="Вовлеченность"
        value={metrics.engagement.value}
        changePercent={metrics.engagement.changePercent}
        suffix="%"
      />

      <MetricsCard
        label="Постов в день"
        value={metrics.postsPerDay.value}
        changePercent={metrics.postsPerDay.changePercent}
      />

      <MetricsCard
        label="Средние просмотры"
        value={metrics.averageViews.value}
        changePercent={metrics.averageViews.changePercent}
      />
    </div>
  )
}
