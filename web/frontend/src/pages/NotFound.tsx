import { useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { Home, ArrowLeft } from 'lucide-react'
import { Button } from '@/components/ui/button'

export default function NotFound() {
  const { t } = useTranslation()
  const navigate = useNavigate()

  return (
    <div className="min-h-[70vh] flex items-center justify-center p-4 relative">
      {/* Floating particles */}
      <div className="absolute inset-0 overflow-hidden pointer-events-none">
        {[...Array(6)].map((_, i) => (
          <div
            key={i}
            className="absolute rounded-full opacity-20"
            style={{
              width: `${4 + i * 2}px`,
              height: `${4 + i * 2}px`,
              background: `var(--accent-from)`,
              left: `${15 + i * 14}%`,
              top: `${20 + (i % 3) * 25}%`,
              animation: `notFoundFloat ${3 + i * 0.7}s ease-in-out infinite`,
              animationDelay: `${i * 0.5}s`,
            }}
          />
        ))}
      </div>

      <div className="text-center relative z-10 max-w-md">
        {/* Disconnected network SVG */}
        <div className="mb-8 flex justify-center">
          <svg width="200" height="120" viewBox="0 0 200 120" fill="none" className="opacity-60">
            {/* Nodes */}
            <circle cx="40" cy="60" r="8" stroke="var(--accent-from)" strokeWidth="1.5" fill="none" opacity="0.8" />
            <circle cx="100" cy="30" r="8" stroke="var(--accent-from)" strokeWidth="1.5" fill="none" opacity="0.5" />
            <circle cx="100" cy="90" r="8" stroke="var(--accent-from)" strokeWidth="1.5" fill="none" opacity="0.5" />
            <circle cx="160" cy="60" r="8" stroke="var(--accent-to)" strokeWidth="1.5" fill="none" opacity="0.8" />
            {/* Connected lines */}
            <line x1="48" y1="56" x2="92" y2="34" stroke="var(--accent-from)" strokeWidth="1" strokeDasharray="4 4" opacity="0.3" />
            <line x1="48" y1="64" x2="92" y2="86" stroke="var(--accent-from)" strokeWidth="1" strokeDasharray="4 4" opacity="0.3" />
            {/* Broken line with gap */}
            <line x1="108" y1="34" x2="125" y2="47" stroke="var(--accent-to)" strokeWidth="1" strokeDasharray="4 4" opacity="0.3" />
            <line x1="135" y1="53" x2="152" y2="56" stroke="var(--accent-to)" strokeWidth="1" strokeDasharray="4 4" opacity="0.3" />
            {/* X mark at break point */}
            <line x1="126" y1="46" x2="134" y2="54" stroke="var(--destructive)" strokeWidth="1.5" opacity="0.6" />
            <line x1="134" y1="46" x2="126" y2="54" stroke="var(--destructive)" strokeWidth="1.5" opacity="0.6" />
            {/* Node dots */}
            <circle cx="40" cy="60" r="3" fill="var(--accent-from)" opacity="0.6">
              <animate attributeName="opacity" values="0.6;1;0.6" dur="2s" repeatCount="indefinite" />
            </circle>
            <circle cx="160" cy="60" r="3" fill="var(--accent-to)" opacity="0.4">
              <animate attributeName="opacity" values="0.4;0.2;0.4" dur="3s" repeatCount="indefinite" />
            </circle>
          </svg>
        </div>

        {/* 404 Text */}
        <h1
          className="text-7xl md:text-8xl font-bold mb-4 tracking-tight"
          style={{
            background: 'linear-gradient(135deg, var(--accent-from) 0%, var(--accent-to) 100%)',
            WebkitBackgroundClip: 'text',
            WebkitTextFillColor: 'transparent',
            filter: 'drop-shadow(0 0 30px rgba(var(--glow-rgb), 0.2))',
          }}
        >
          404
        </h1>

        <h2 className="text-xl md:text-2xl font-semibold mb-2" style={{ color: 'var(--text-heading)' }}>
          {t('notFound.title')}
        </h2>
        <p className="text-sm text-muted-foreground mb-8 leading-relaxed">
          {t('notFound.description')}
        </p>

        <div className="flex items-center justify-center gap-3">
          <Button
            variant="outline"
            onClick={() => navigate(-1)}
          >
            <ArrowLeft className="w-4 h-4 mr-2" />
            {t('notFound.goBack')}
          </Button>
          <Button
            onClick={() => navigate('/')}
            className="bg-gradient-to-r from-[var(--accent-from)] to-[var(--accent-to)] text-white hover:opacity-90"
          >
            <Home className="w-4 h-4 mr-2" />
            {t('notFound.goHome')}
          </Button>
        </div>
      </div>

      <style>{`
        @keyframes notFoundFloat {
          0%, 100% { transform: translateY(0px); }
          50% { transform: translateY(-15px); }
        }
      `}</style>
    </div>
  )
}
