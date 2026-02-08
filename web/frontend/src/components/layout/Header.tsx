import { Bell, Search, Menu } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Badge } from '@/components/ui/badge'

interface HeaderProps {
  onMenuToggle?: () => void
}

export default function Header({ onMenuToggle }: HeaderProps) {
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

        {/* Search */}
        <div className="flex-1 max-w-md hidden sm:block">
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-dark-200" />
            <Input
              type="text"
              placeholder="Search users, nodes..."
              className="pl-10"
            />
          </div>
        </div>

        {/* Mobile search icon */}
        <Button
          variant="ghost"
          size="icon"
          className="sm:hidden"
        >
          <Search className="w-5 h-5" />
        </Button>
      </div>

      {/* Right side */}
      <div className="flex items-center gap-2 md:gap-4">
        {/* Notifications */}
        <Button variant="ghost" size="icon" className="relative">
          <Bell className="w-5 h-5" />
          <span className="absolute top-1.5 right-1.5 w-2 h-2 bg-red-500 rounded-full" />
        </Button>

        {/* Status indicator */}
        <Badge variant="default" className="gap-2 px-3 py-1.5">
          <span
            className="w-2 h-2 rounded-full animate-pulse bg-accent-teal"
            style={{ boxShadow: '0 0 8px rgba(13, 148, 136, 0.5)' }}
          />
          <span className="hidden sm:inline text-xs">Online</span>
        </Badge>
      </div>
    </header>
  )
}
