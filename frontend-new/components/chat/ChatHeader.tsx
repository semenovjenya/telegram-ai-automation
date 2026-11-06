interface ChatHeaderProps {
  chatTitle: string
}

export const ChatHeader = ({ chatTitle }: ChatHeaderProps) => {
  return (
    <div className="bg-white border-b border-gray-200 p-4">
      <h3 className="text-lg font-semibold text-gray-900">
        {chatTitle}
      </h3>
    </div>
  )
}

