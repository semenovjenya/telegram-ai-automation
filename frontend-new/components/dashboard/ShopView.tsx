import type { Channel } from '@/lib/types/dashboard'
import type { RecommendationSource } from '@/lib/types/barter'
import { formatChannelNumber } from '@/lib/utils/format'

interface ShopViewProps {
  channels: Channel[]
  source: RecommendationSource | null
  isLoading: boolean
  error: string | null
  onRefresh: () => void
}

export const ShopView = ({ channels, source, isLoading, error, onRefresh }: ShopViewProps) => {
  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary-DEFAULT"></div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="rounded-card border border-amber-300 bg-amber-50 p-6" role="alert">
        <h2 className="font-bold text-amber-950">
          {source?.type === 'live_unconfigured'
            ? 'Живой источник не подключён'
            : 'Рекомендации недоступны'}
        </h2>
        <p className="mb-4 mt-2 text-amber-900">{error}</p>
        <p className="mb-4 text-sm text-amber-800">Синтетические каналы не подставляются в live-режиме.</p>
        <button onClick={onRefresh} className="rounded-button bg-amber-700 px-4 py-2 text-white hover:bg-amber-800">
          Попробовать снова
        </button>
      </div>
    )
  }

  if (channels.length === 0) {
    return <p className="text-text-secondary">Каналы не найдены</p>
  }

  return (
    <div className="space-y-4">
      <div className="mb-6 rounded-card border-2 border-amber-400 bg-amber-100 p-4 text-amber-950">
        <p className="text-sm font-bold">
          {source?.synthetic ? 'Демо: синтетические рекомендации' : 'Источник рекомендаций'}
        </p>
        <p className="mt-1 text-xs">
          {source?.synthetic
            ? `Источник: ${source.provenance}. Записи входят в публичную демо-сборку и не описывают реальные Telegram-каналы.`
            : `Provenance: ${source?.provenance ?? 'не указан'}`}
        </p>
      </div>
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        {channels.map((channel, index) => (
          <div key={channel.id} className="bg-background-card rounded-card shadow-lg p-6 hover:shadow-xl transition-shadow">
            <div className="flex items-center gap-2 mb-4">
              <span className="w-8 h-8 rounded-full bg-primary-DEFAULT text-white flex items-center justify-center text-sm font-bold">
                {index + 1}
              </span>
              <span className="text-sm font-bold text-primary-DEFAULT">
                {(channel.final_score * 100).toFixed(1)}%
              </span>
              {channel.similarity_score > 0.9 && (
                <span className="px-2 py-1 bg-green-100 text-green-700 text-xs font-medium rounded-button ml-auto">
                  Высокая схожесть
                </span>
              )}
            </div>
            <h3 className="text-lg font-bold text-text-primary mb-1 line-clamp-2">{channel.title}</h3>
            <p className="text-sm text-text-secondary mb-3">@{channel.username}</p>
            <div className="grid grid-cols-2 gap-3 mb-4">
              <div className="bg-gray-50 rounded-button p-3">
                <p className="text-xs text-text-secondary mb-1">Подписчики</p>
                <p className="text-lg font-bold text-text-primary">{formatChannelNumber(channel.subscribers)}</p>
              </div>
              <div className="bg-gray-50 rounded-button p-3">
                <p className="text-xs text-text-secondary mb-1">ER</p>
                <p className="text-lg font-bold text-text-primary">{channel.engagement_rate.toFixed(1)}%</p>
              </div>
            </div>
            {(channel.common_topics_count > 0 || channel.common_audience_count > 0) && (
              <div className="flex flex-wrap gap-2 mb-4">
                {channel.common_topics_count > 0 && (
                  <span className="px-2 py-1 bg-blue-100 text-blue-700 text-xs font-medium rounded-button">
                    {channel.common_topics_count} общих тем
                  </span>
                )}
                {channel.common_audience_count > 0 && (
                  <span className="px-2 py-1 bg-purple-100 text-purple-700 text-xs font-medium rounded-button">
                    {channel.common_audience_count} общих аудиторий
                  </span>
                )}
              </div>
            )}
            <div className="mb-4">
              <div className="flex items-center justify-between mb-1">
                <span className="text-xs text-text-secondary">Семантическая схожесть</span>
                <span className="text-xs font-medium text-text-primary">
                  {(channel.similarity_score * 100).toFixed(1)}%
                </span>
              </div>
              <div className="w-full bg-gray-200 rounded-full h-2">
                <div 
                  className="bg-primary-DEFAULT h-2 rounded-full transition-all" 
                  style={{ width: `${channel.similarity_score * 100}%` }}
                ></div>
              </div>
            </div>
            {source?.synthetic ? (
              <p className="rounded-button bg-gray-100 px-4 py-2 text-center text-xs text-text-secondary">
                Ссылка отсутствует: это синтетический пример
              </p>
            ) : (
              <a
                href={`https://t.me/${channel.username}`}
                target="_blank"
                rel="noopener noreferrer"
                className="block rounded-button bg-primary-DEFAULT px-4 py-2 text-center text-sm font-medium text-white hover:bg-primary-dark"
              >
                Открыть канал
              </a>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}
