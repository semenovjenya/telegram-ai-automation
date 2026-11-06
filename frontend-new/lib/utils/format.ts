export const formatNumber = (num: number | string): string => {
  const numValue = typeof num === 'string' ? parseFloat(num) : num
  if (isNaN(numValue)) return num.toString()
  
  if (numValue >= 1000000) {
    return `${(numValue / 1000000).toFixed(1)}M`
  }
  if (numValue >= 1000) {
    return `${(numValue / 1000).toFixed(1)}K`
  }
  return numValue.toString()
}

export const formatChange = (changePercent: number): string => {
  const sign = changePercent >= 0 ? '+' : ''
  return `${sign}${changePercent.toFixed(1)}%`
}

export const formatChannelNumber = (num: number): string => {
  if (num >= 1000000) return `${(num / 1000000).toFixed(1)}M`
  if (num >= 1000) return `${(num / 1000).toFixed(1)}K`
  return num.toString()
}

export const formatTime = (timestamp: string): string => {
  const date = new Date(timestamp)
  const now = new Date()
  const diff = now.getTime() - date.getTime()
  const minutes = Math.floor(diff / 60000)
  const hours = Math.floor(diff / 3600000)
  const days = Math.floor(diff / 86400000)

  if (minutes < 1) return 'только что'
  if (minutes < 60) return `${minutes} мин назад`
  if (hours < 24) return `${hours} ч назад`
  if (days < 7) return `${days} дн назад`
  return date.toLocaleDateString('ru-RU')
}

