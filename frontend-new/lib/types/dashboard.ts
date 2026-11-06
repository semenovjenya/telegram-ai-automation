export interface Metric {
  value: number | string
  change: number | null
  changePercent: number | null
}

export interface Publication {
  id: string
  title: string
  views: string
  timeAgo: string
}

export interface AISummaryItem {
  id: string
  text: string
}

export interface Notification {
  id: string
  icon: 'megaphone' | 'chart' | 'lightning'
  text: string
  timeAgo: string
}

export interface ActivityPoint {
  day: number
  views: number
  topPostViews: number | null
  posts: number
}

export interface DashboardData {
  data_source?: string
  profile: {
    username: string
    url: string
  }
  metrics: {
    subscribers: Metric
    engagement: Metric
    postsPerDay: Metric
    averageViews: Metric
  }
  aiRecommendation: string
  publications: Publication[]
  aiSummary: AISummaryItem[]
  notifications: Notification[]
  activity?: ActivityPoint[]
}

export interface Channel {
  id: number
  username: string
  title: string
  subscribers: number
  engagement_rate: number
  similarity_score: number
  common_topics_count: number
  common_audience_count: number
  final_score: number
}
