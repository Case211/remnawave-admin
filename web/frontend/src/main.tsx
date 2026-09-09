import React from 'react'
import ReactDOM from 'react-dom/client'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { TooltipProvider } from '@/components/ui/tooltip'
import { Toaster } from '@/components/ui/sonner'
import { OfflineIndicator } from '@/components/OfflineIndicator'
import App from './App'
import { useAuthStore } from './store/authStore'
import { captureTelegramInitData, stripTelegramInitDataFromUrl } from './lib/telegramWebApp'
import { initTelegramViewport } from './lib/telegramViewport'
import './i18n'
import './index.css'

// Telegram кладёт подписанные initData в хеш URL при открытии мини-аппа.
// Снимаем их до того, как роутер перепишет адрес, иначе авто-вход
// потеряет данные ещё до первого рендера. Для уже вошедшего админа
// не снимаем вовсе: чужие initData в его вкладке не нужны, а без этой
// проверки открытая им ссылка молча сменила бы аккаунт при следующем
// истечении сессии.
if (useAuthStore.getState().isAuthenticated) {
  stripTelegramInitDataFromUrl()
} else {
  captureTelegramInitData()
}

// Внутри Telegram кнопки клиента лежат поверх страницы — подтягиваем его
// SDK, чтобы знать их размеры и не рисовать шапку под ними.
initTelegramViewport()

// A tab holding a pre-deploy build references chunk hashes that no longer
// exist on the server — lazy imports fail with "Failed to fetch dynamically
// imported module". One reload picks up the fresh index.html; the
// sessionStorage window guards against a reload loop if a chunk is missing
// for any other reason.
window.addEventListener('vite:preloadError', (event) => {
  const KEY = 'chunk-reload-at'
  const last = Number(sessionStorage.getItem(KEY) ?? 0)
  if (Date.now() - last > 30_000) {
    sessionStorage.setItem(KEY, String(Date.now()))
    event.preventDefault()
    window.location.reload()
  }
})

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 1000 * 60 * 3, // 3 minutes (WS events handle real-time updates)
      retry: 1,
      refetchOnWindowFocus: false,
    },
  },
})

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <TooltipProvider>
        <App />
        <Toaster />
        <OfflineIndicator />
      </TooltipProvider>
    </QueryClientProvider>
  </React.StrictMode>,
)
