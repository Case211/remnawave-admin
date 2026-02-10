import { Bell, Search, Menu } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { AppearancePanel } from '../AppearancePanel'

interface HeaderProps {
  onMenuToggle?: () => void
  onSearchClick?: () => void
}

export default function Header({ onMenuToggle, onSearchClick }: HeaderProps) {
  return (
    <header
      className="h-16 border-b border-dark-400/10 flex items-center justify-between px-4 md:px-6 animate-fade-in bg-dark-700/95 backdrop-blur-xl"
    >
      {/* Left side: hamburger + search */}
      <div className="flex items-center gap-3 flex-1">
        {/* Mobile menu button */}
        <Button
          variant="ghost"
          size="icon"
          onClick={onMenuToggle}
          className="md:hidden"
        >
          <Menu className="w-6 h-6" />
        </Button>

        {/* Search trigger — opens Command Palette */}
        <button
          onClick={onSearchClick}
          className="header-search-bar flex-1 max-w-md hidden sm:flex items-center gap-2 h-10 rounded-md border border-dark-400/20 bg-dark-800 px-3 text-sm text-dark-300 hover:border-dark-400/40 hover:text-dark-200 transition-colors cursor-pointer"
        >
          <Search className="w-4 h-4 flex-shrink-0" />
          <span className="flex-1 text-left">Поиск...</span>
          <kbd className="hidden lg:inline-flex h-5 select-none items-center gap-1 rounded border border-dark-400/30 bg-dark-700 px-1.5 font-mono text-[10px] font-medium text-dark-300">
            <span className="text-xs">&#x2318;</span>K
          </kbd>
        </button>

        {/* Mobile search icon */}
        <Button
          variant="ghost"
          size="icon"
          className="sm:hidden"
          onClick={onSearchClick}
        >
          <Search className="w-5 h-5" />
        </Button>
      </div>

      {/* Right side */}
      <div className="flex items-center gap-2 md:gap-4">
        {/* Appearance settings */}
        <AppearancePanel />

        {/* Notifications */}
        <Button variant="ghost" size="icon" className="relative">
          <Bell className="w-5 h-5" />
          <span className="absolute top-1.5 right-1.5 w-2 h-2 bg-red-500 rounded-full" />
        </Button>

        {/* Status indicator */}
        <Badge variant="default" className="gap-2 px-3 py-1.5">
          <span
            className="w-2 h-2 rounded-full animate-pulse"
            style={{ backgroundColor: 'var(--accent-from)', boxShadow: '0 0 8px rgba(var(--glow-rgb), 0.5)' }}
          />
          <span className="hidden sm:inline text-xs">Online</span>
        </Badge>
      </div>
    </header>
  )
}
