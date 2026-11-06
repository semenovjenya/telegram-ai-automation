interface ProfileCardProps {
  username: string
  url: string
}

export const ProfileCard = ({ username, url }: ProfileCardProps) => {
  return (
    <div className="bg-background-card rounded-card shadow-lg p-6 relative">
      <div className="flex flex-col items-center">
        <div className="w-20 h-20 rounded-card bg-avatar-bg mb-4 relative flex items-center justify-center">
          <div className="absolute top-1 left-1 w-3 h-3 bg-success-DEFAULT rounded-full opacity-60"></div>
          <div className="absolute bottom-1 right-1 w-3 h-3 bg-success-DEFAULT rounded-full opacity-60"></div>
          <svg className="w-12 h-12 text-primary-DEFAULT" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 3v4M3 5h4M6 17v4m-2-2h4m5-16l2.286 6.857L21 12l-5.714 2.143L13 21l-2.286-6.857L5 12l5.714-2.143L13 3z" />
          </svg>
        </div>
        <h2 className="text-xl font-bold text-text-primary mb-1">
          {username}
        </h2>
        <p className="break-all text-center text-sm text-text-secondary">
          {url}
        </p>
      </div>
    </div>
  )
}
