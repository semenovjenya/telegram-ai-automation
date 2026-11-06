import type { Channel } from '@/lib/types/dashboard'

/**
 * Demo-only data packaged with the frontend image.
 * These records are synthetic and do not represent real Telegram channels.
 */
export const SYNTHETIC_BARTER_CHANNELS: readonly Channel[] = Object.freeze([
  {
    id: 1,
    username: 'demo_creator_lab',
    title: 'Демо: лаборатория авторов',
    subscribers: 48_200,
    engagement_rate: 8.4,
    similarity_score: 0.92,
    common_topics_count: 7,
    common_audience_count: 4,
    final_score: 0.894,
  },
  {
    id: 2,
    username: 'demo_media_notes',
    title: 'Демо: заметки о медиа',
    subscribers: 31_700,
    engagement_rate: 7.1,
    similarity_score: 0.86,
    common_topics_count: 6,
    common_audience_count: 3,
    final_score: 0.821,
  },
  {
    id: 3,
    username: 'demo_content_room',
    title: 'Демо: контент-комната',
    subscribers: 22_900,
    engagement_rate: 9.2,
    similarity_score: 0.79,
    common_topics_count: 5,
    common_audience_count: 2,
    final_score: 0.776,
  },
])
