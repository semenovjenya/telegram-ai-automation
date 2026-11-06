import type { Chat } from '@/lib/types/chat'

interface ChatItemProps {
  chat: Chat
  isSelected: boolean
  onClick: () => void
  formatTime: (timestamp: string) => string
}

export const ChatItem = ({ chat, isSelected, onClick, formatTime }: ChatItemProps) => {
  return (
    <button
      onClick={onClick}
      className={`w-full p-4 text-left hover:bg-gray-50 transition-colors ${
        isSelected ? 'bg-blue-50 border-l-4 border-blue-500' : ''
      }`}
    >
      <div className="flex items-start justify-between">
        <div className="flex-1 min-w-0">
          <h3 className="font-semibold text-gray-900 truncate">
            {chat.title || chat.username || `Чат ${chat.id}`}
          </h3>
          {chat.last_message && (
            <p className="text-sm text-gray-500 truncate mt-1">
              {chat.last_message.content}
            </p>
          )}
        </div>
        {chat.unread_count && chat.unread_count > 0 && (
          <span className="ml-2 flex-shrink-0 bg-blue-500 text-white text-xs font-bold rounded-full w-5 h-5 flex items-center justify-center">
            {chat.unread_count}
          </span>
        )}
      </div>
      {chat.last_message && (
        <p className="text-xs text-gray-400 mt-1">
          {formatTime(chat.last_message.timestamp)}
        </p>
      )}
    </button>
  )
}

