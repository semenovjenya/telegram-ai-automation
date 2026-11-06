import { ResponsiveContainer, ComposedChart, Area, Line, Bar, XAxis, YAxis, CartesianGrid, Tooltip } from 'recharts'
import type { ActivityPoint } from '@/lib/types/dashboard'

interface ActivityChartProps {
  data?: ActivityPoint[]
}

function formatCompactNumber(value: number): string {
  return new Intl.NumberFormat('ru-RU', {
    notation: 'compact',
    maximumFractionDigits: 1,
  }).format(value)
}

export const ActivityChart = ({ data }: ActivityChartProps) => {
  if (!data?.length) {
    return (
      <section className="mb-6 rounded-2xl border border-slate-200 bg-white p-4 shadow-sm sm:p-8">
        <h3 className="text-xl font-bold text-gray-900">Активность и частота публикаций</h3>
        <div className="mt-4 rounded-xl border border-dashed border-slate-300 bg-slate-50 p-4 sm:p-6" role="status">
          <p className="font-medium text-slate-700">Временной ряд пока недоступен</p>
          <p className="mt-1 text-sm text-slate-500">
            График появится, когда backend вернёт реальные данные об активности.
          </p>
        </div>
      </section>
    )
  }

  const averageViews = Math.round(
    data.reduce((total, point) => total + point.views, 0) / data.length
  )
  const averagePosts = data.reduce((total, point) => total + point.posts, 0) / data.length
  const topPostsCount = data.filter((point) => point.topPostViews !== null).length

  return (
    <div className="mb-6">
      <div className="inline-block w-full max-w-[900px] rounded-2xl border border-gray-200/50 bg-gradient-to-br from-white via-blue-50/30 to-purple-50/30 p-4 shadow-2xl backdrop-blur-sm transition-all duration-300 hover:shadow-3xl sm:p-8">
        <div className="mb-6">
          <div className="flex items-center gap-3 mb-2">
            <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-blue-500 to-purple-600 flex items-center justify-center shadow-lg">
              <svg className="w-6 h-6 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
              </svg>
            </div>
            <div>
              <h3 className="text-2xl font-bold bg-gradient-to-r from-gray-900 to-gray-700 bg-clip-text text-transparent">Активность и частота публикаций</h3>
              <p className="text-xs text-gray-500 mt-0.5">Анализ за последние 30 дней</p>
            </div>
          </div>
          <div className="flex items-center gap-3 mt-4 flex-wrap">
            <div className="flex items-center gap-2 px-3 py-1.5 bg-blue-50 rounded-lg border border-blue-100">
              <div className="w-2.5 h-2.5 rounded-full bg-gradient-to-r from-blue-500 to-cyan-400 shadow-sm"></div>
              <span className="text-xs font-medium text-blue-700">Просмотры</span>
            </div>
            <div className="flex items-center gap-2 px-3 py-1.5 bg-emerald-50 rounded-lg border border-emerald-100">
              <div className="w-2.5 h-2.5 rounded-full bg-gradient-to-r from-emerald-400 to-green-500 shadow-sm ring-2 ring-emerald-200"></div>
              <span className="text-xs font-medium text-emerald-700">Топ посты</span>
            </div>
            <div className="flex items-center gap-2 px-3 py-1.5 bg-purple-50 rounded-lg border border-purple-100">
              <div className="w-2.5 h-2.5 rounded-full bg-gradient-to-r from-purple-500 to-fuchsia-400 shadow-sm"></div>
              <span className="text-xs font-medium text-purple-700">Публикации</span>
            </div>
          </div>
        </div>
        <div className="bg-white/60 rounded-xl p-4 backdrop-blur-sm border border-gray-100">
          <ResponsiveContainer width="100%" height={340}>
            <ComposedChart data={data}>
              <defs>
                <linearGradient id="colorViews" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#3b82f6" stopOpacity={0.4}/>
                  <stop offset="50%" stopColor="#06b6d4" stopOpacity={0.3}/>
                  <stop offset="100%" stopColor="#3b82f6" stopOpacity={0}/>
                </linearGradient>
                <linearGradient id="barGradient" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#8b5cf6" stopOpacity={0.8}/>
                  <stop offset="50%" stopColor="#a78bfa" stopOpacity={0.7}/>
                  <stop offset="100%" stopColor="#c084fc" stopOpacity={0.5}/>
                </linearGradient>
                <linearGradient id="topPostGradient" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#10b981" stopOpacity={1}/>
                  <stop offset="50%" stopColor="#34d399" stopOpacity={1}/>
                  <stop offset="100%" stopColor="#059669" stopOpacity={1}/>
                </linearGradient>
                <filter id="glow">
                  <feGaussianBlur stdDeviation="3" result="coloredBlur"/>
                  <feMerge>
                    <feMergeNode in="coloredBlur"/>
                    <feMergeNode in="SourceGraphic"/>
                  </feMerge>
                </filter>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" opacity={0.5} />
              <XAxis 
                dataKey="day" 
                stroke="#94a3b8"
                tick={{ fill: '#64748b', fontSize: 11, fontWeight: 500 }}
                axisLine={{ stroke: '#e2e8f0' }}
                tickLine={{ stroke: '#e2e8f0' }}
                label={{ value: 'День', position: 'insideBottom', offset: -5, fill: '#64748b', style: { fontSize: 12 } }}
              />
              <YAxis 
                yAxisId="views"
                stroke="#3b82f6"
                tick={{ fill: '#3b82f6', fontSize: 11, fontWeight: 500 }}
                axisLine={{ stroke: '#3b82f6' }}
                tickLine={{ stroke: '#3b82f6' }}
                tickFormatter={(value) => `${(value / 1000).toFixed(1)}K`}
                label={{ value: 'Просмотры', angle: -90, position: 'insideLeft', fill: '#3b82f6', style: { fontSize: 12, fontWeight: 600 } }}
              />
              <YAxis 
                yAxisId="posts"
                orientation="right"
                stroke="#8b5cf6"
                tick={{ fill: '#8b5cf6', fontSize: 11, fontWeight: 500 }}
                axisLine={{ stroke: '#8b5cf6' }}
                tickLine={{ stroke: '#8b5cf6' }}
                label={{ value: 'Публикации', angle: 90, position: 'insideRight', fill: '#8b5cf6', style: { fontSize: 12, fontWeight: 600 } }}
              />
              <Tooltip 
                contentStyle={{ 
                  backgroundColor: '#ffffff', 
                  border: 'none', 
                  borderRadius: '12px',
                  boxShadow: '0 20px 25px -5px rgba(0, 0, 0, 0.1), 0 10px 10px -5px rgba(0, 0, 0, 0.04)',
                  padding: '14px 18px',
                  backdropFilter: 'blur(10px)'
                }}
                labelStyle={{ color: '#1e293b', fontWeight: 700, fontSize: 14, marginBottom: 10 }}
                itemStyle={{ color: '#475569', fontSize: 13, padding: '6px 0', fontWeight: 600 }}
                formatter={(value, name) => {
                  const seriesName = String(name ?? '')
                  const numericValue = typeof value === 'number' ? value : Number(value)
                  if (
                    Number.isFinite(numericValue) &&
                    ['views', 'Просмотры', 'topPostViews', 'Топ посты'].includes(seriesName)
                  ) {
                    return [`${numericValue.toLocaleString()} просмотров`, seriesName]
                  }
                  if (
                    Number.isFinite(numericValue) &&
                    ['posts', 'Публикации'].includes(seriesName)
                  ) {
                    const noun = numericValue === 1
                      ? 'публикация'
                      : numericValue < 5
                        ? 'публикации'
                        : 'публикаций'
                    return [`${numericValue} ${noun}`, 'Публикации']
                  }
                  return [String(value ?? ''), seriesName]
                }}
                labelFormatter={(label) => `День ${label}`}
                cursor={{ stroke: '#3b82f6', strokeWidth: 2, strokeDasharray: '5 5' }}
              />
              <Area 
                yAxisId="views"
                type="monotone" 
                dataKey="views" 
                stroke="url(#colorViews)"
                strokeWidth={4}
                fill="url(#colorViews)"
                dot={false}
                activeDot={{ r: 10, fill: '#3b82f6', stroke: '#fff', strokeWidth: 4, filter: 'url(#glow)', className: 'drop-shadow-2xl' }}
                name="Просмотры"
                animationDuration={1500}
              />
              <Line 
                yAxisId="views"
                type="monotone" 
                dataKey="topPostViews"
                stroke="none"
                dot={{ r: 14, fill: 'url(#topPostGradient)', stroke: '#fff', strokeWidth: 4, filter: 'url(#glow)', className: 'drop-shadow-2xl' }}
                connectNulls={false}
                name="Топ посты"
                animationDuration={1500}
              />
              <Bar 
                yAxisId="posts"
                dataKey="posts" 
                fill="url(#barGradient)"
                radius={[8, 8, 0, 0]}
                name="Публикации"
                opacity={0.9}
                animationDuration={1500}
              />
            </ComposedChart>
          </ResponsiveContainer>
        </div>
        <div className="mt-6 pt-6 border-t border-gradient-to-r from-transparent via-gray-200 to-transparent">
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
            <div className="bg-gradient-to-br from-blue-50 to-blue-100/50 rounded-xl p-4 border border-blue-100">
              <div className="flex items-center gap-2 mb-1">
                <svg className="w-4 h-4 text-blue-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
                </svg>
                <span className="text-xs font-medium text-blue-600 uppercase tracking-wide">Средние просмотры</span>
              </div>
              <p className="text-2xl font-bold text-blue-700">{formatCompactNumber(averageViews)}</p>
            </div>
            <div className="bg-gradient-to-br from-purple-50 to-purple-100/50 rounded-xl p-4 border border-purple-100">
              <div className="flex items-center gap-2 mb-1">
                <svg className="w-4 h-4 text-purple-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 6v6m0 0v6m0-6h6m-6 0H6" />
                </svg>
                <span className="text-xs font-medium text-purple-600 uppercase tracking-wide">Средние публикации</span>
              </div>
              <p className="text-2xl font-bold text-purple-700">
                {averagePosts.toFixed(1)}<span className="text-sm text-purple-500">/день</span>
              </p>
            </div>
            <div className="bg-gradient-to-br from-emerald-50 to-emerald-100/50 rounded-xl p-4 border border-emerald-100">
              <div className="flex items-center gap-2 mb-1">
                <svg className="w-4 h-4 text-emerald-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 3v4M3 5h4M6 17v4m-2-2h4m5-16l2.286 6.857L21 12l-5.714 2.143L13 21l-2.286-6.857L5 12l5.714-2.143L13 3z" />
                </svg>
                <span className="text-xs font-medium text-emerald-600 uppercase tracking-wide">Топ постов</span>
              </div>
              <p className="text-2xl font-bold text-emerald-700">{topPostsCount}</p>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
