import Image from 'next/image'

interface UserAvatarProps {
  name: string
  username: string
  avatarUrl?: string
}

export const UserAvatar = ({ name, username, avatarUrl }: UserAvatarProps) => {
  return (
    <div className="flex items-center justify-start gap-4 px-4">
      <div className="w-12 h-12 rounded-full bg-avatar-bg flex items-center justify-center overflow-hidden flex-shrink-0">
        {avatarUrl ? (
          <div className="relative w-full h-full">
            <Image
              src={avatarUrl}
              alt={name}
              fill
              sizes="48px"
              className="object-cover"
              unoptimized
            />
          </div>
        ) : (
          <div className="w-full h-full bg-gradient-to-br from-purple-400 to-pink-400"></div>
        )}
      </div>
      <div className="whitespace-nowrap">
        <p className="text-sm font-medium text-text-primary">{name}</p>
        <p className="text-xs text-text-secondary">{username}</p>
      </div>
    </div>
  )
}
