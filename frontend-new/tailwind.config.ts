import type { Config } from 'tailwindcss'

const config: Config = {
  content: [
    './pages/**/*.{js,ts,jsx,tsx,mdx}',
    './components/**/*.{js,ts,jsx,tsx,mdx}',
    './app/**/*.{js,ts,jsx,tsx,mdx}',
  ],
  theme: {
    extend: {
      colors: {
        // Цвета из референса
        primary: {
          light: '#E8D5FF', // Светло-фиолетовый для кнопок
          DEFAULT: '#A855F7', // Фиолетовый основной
          dark: '#9333EA',
        },
        success: {
          light: '#D1FAE5',
          DEFAULT: '#10B981', // Зеленый для положительных значений
          dark: '#059669',
        },
        background: {
          light: '#F9FAFB',
          DEFAULT: '#FFFFFF',
          card: '#FEFEFE',
        },
        text: {
          primary: '#111827', // Темный текст
          secondary: '#6B7280', // Серый текст
          light: '#9CA3AF',
        },
        avatar: {
          bg: '#FCE7F3', // Светло-розовый фон для аватара
        },
      },
      borderRadius: {
        'card': '12px',
        'button': '8px',
      },
    },
  },
  plugins: [],
}
export default config






