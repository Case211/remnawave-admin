/// <reference types="vite/client" />

interface RuntimeEnv {
  API_URL?: string
  TELEGRAM_BOT_USERNAME?: string
}

declare global {
  interface Window {
    __ENV?: RuntimeEnv
  }
}
