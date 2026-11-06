export interface Message {
  id: string
  content: string
  timestamp: string
  isOwn: boolean
  chat_id: string
}

export interface Chat {
  id: string
  title?: string
  name?: string
  username?: string
  type?: string
  unread_count?: number
  last_message?: {
    content: string
    timestamp: string
  }
}
