import type { Message } from '@/lib/types/chat'
import { MessageItem } from './MessageItem'

interface MessageListProps {
  messages: Message[]
  isLoading: boolean
  messagesEndRef: React.RefObject<HTMLDivElement>
  formatTime: (timestamp: string) => string
}

export const MessageList = ({ messages, isLoading, messagesEndRef, formatTime }: MessageListProps) => {
  return (
    <div className="flex-1 overflow-y-auto p-4 space-y-4">
      {isLoading && messages.length === 0 ? (
        <div className="text-center text-gray-500">Загрузка сообщений...</div>
      ) : messages.length === 0 ? (
        <div className="text-center text-gray-500">Нет сообщений</div>
      ) : (
        messages.map((message) => (
          <MessageItem key={message.id} message={message} formatTime={formatTime} />
        ))
      )}
      <div ref={messagesEndRef} />
    </div>
  )
}

