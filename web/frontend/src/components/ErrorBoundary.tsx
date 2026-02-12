import { Component, type ReactNode } from 'react'
import i18n from '@/i18n'

interface Props {
  children: ReactNode
}

interface State {
  hasError: boolean
  error: Error | null
}

export class ErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false, error: null }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error }
  }

  componentDidCatch(error: Error, info: React.ErrorInfo) {
    console.error('ErrorBoundary caught:', error, info.componentStack)
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="flex items-center justify-center min-h-screen bg-dark-900">
          <div className="max-w-md p-6 text-center space-y-4">
            <h1 className="text-xl font-semibold text-white">{i18n.t('errorBoundary.title')}</h1>
            <p className="text-sm text-dark-300">
              {this.state.error?.message || i18n.t('errorBoundary.defaultError')}
            </p>
            <button
              onClick={() => window.location.reload()}
              className="px-4 py-2 text-sm font-medium text-white bg-primary-600 rounded-lg hover:bg-primary-700 transition-colors"
            >
              {i18n.t('errorBoundary.reload')}
            </button>
          </div>
        </div>
      )
    }
    return this.props.children
  }
}
