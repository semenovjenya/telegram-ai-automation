import type { Channel } from '@/lib/types/dashboard'

export interface RecommendationSource {
  type: 'synthetic_fixture' | 'live_unconfigured' | string
  synthetic: boolean
  provenance: string
}

export interface ChannelsPayload {
  channels: Channel[]
  count: number
  source: RecommendationSource
  error?: string
}
