import type { Chat } from '@/lib/types/chat'
import type { ChatTransportStatus } from '@/hooks/useChatLogic'
import { ChatItem } from './ChatItem'

interface ChatListProps {
  chats: Chat[]
  selectedChat: string | null
  isLoading: boolean
  transportStatus: ChatTransportStatus
  error: string | null
  onSelectChat: (chatId: string) => void
  formatTime: (timestamp: string) => string
}

export const ChatList = ({ 
  chats, 
  selectedChat, 
  isLoading, 
  transportStatus,
  error,
  onSelectChat,
  formatTime 
}: ChatListProps) => {
  return (
    <div className="flex h-52 w-full flex-shrink-0 flex-col border-b border-gray-200 bg-white md:h-auto md:w-80 md:border-b-0 md:border-r">
      <div className="p-4 border-b border-gray-200">
        <h2 className="text-xl font-bold text-gray-900">Чаты</h2>
        <div className="mt-2 flex items-center gap-2">
          <div className={`w-2 h-2 rounded-full ${
            transportStatus === 'polling' ? 'bg-amber-500' : 'bg-red-500'
          }`}></div>
          <span className="text-sm text-gray-500">
            {transportStatus === 'polling' ? 'Безопасный polling' : 'Нет связи'}
          </span>
        </div>
        {error && <p className="mt-2 text-xs text-red-600" role="status">{error}</p>}
      </div>

      <div className="flex-1 overflow-y-auto">
        {isLoading && chats.length === 0 ? (
          <div className="p-4 text-center text-gray-500">Загрузка чатов...</div>
        ) : chats.length === 0 ? (
          <div className="p-4 text-center text-gray-500">Нет подключённых чатов</div>
        ) : (
          <div className="divide-y divide-gray-100">
            {chats.map((chat) => (
              <ChatItem
                key={chat.id}
                chat={chat}
                isSelected={String(selectedChat) === String(chat.id)}
                onClick={() => onSelectChat(chat.id)}
                formatTime={formatTime}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
