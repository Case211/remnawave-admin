import { HiBell, HiSearch, HiMenuAlt2 } from 'react-icons/hi'

interface HeaderProps {
  onMenuToggle?: () => void
}

export default function Header({ onMenuToggle }: HeaderProps) {
  return (
    <header
      className="h-16 border-b border-dark-400/10 flex items-center justify-between px-4 md:px-6 animate-fade-in"
      style={{
        background: 'rgba(22, 27, 34, 0.95)',
        backdropFilter: 'blur(12px)',
      }}
    >
      {/* Left side: hamburger + search */}
      <div className="flex items-center gap-3 flex-1">
        {/* Mobile menu button */}
        <button
          onClick={onMenuToggle}
          className="p-2 text-dark-200 hover:text-white rounded-lg hover:bg-dark-600 transition-all duration-200 md:hidden"
        >
          <HiMenuAlt2 className="w-6 h-6" />
        </button>

        {/* Search */}
        <div className="flex-1 max-w-md hidden sm:block">
          <div className="relative">
            <HiSearch className="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-dark-200" />
            <input
              type="text"
              placeholder="Search users, nodes..."
              className="w-full pl-10 pr-4 py-2 bg-dark-800 border border-dark-400/20 rounded-lg text-sm text-dark-50 placeholder-dark-200 focus:outline-none focus:ring-2 focus:ring-primary-500/50 focus:border-primary-500/50 transition-all duration-200"
            />
          </div>
        </div>

        {/* Mobile search icon */}
        <button className="p-2 text-dark-200 hover:text-white rounded-lg hover:bg-dark-600 transition-all duration-200 sm:hidden">
          <HiSearch className="w-5 h-5" />
        </button>
      </div>

      {/* Right side */}
      <div className="flex items-center gap-2 md:gap-4">
        {/* Notifications */}
        <button className="relative p-2 text-dark-200 hover:text-white rounded-lg hover:bg-dark-600 transition-all duration-200">
          <HiBell className="w-5 h-5" />
          <span className="absolute top-1.5 right-1.5 w-2 h-2 bg-red-500 rounded-full"></span>
        </button>

        {/* Status indicator */}
        <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg border border-dark-400/20" style={{ background: 'rgba(13, 17, 23, 0.5)' }}>
          <span
            className="w-2 h-2 rounded-full animate-pulse"
            style={{ background: '#0d9488', boxShadow: '0 0 8px rgba(13, 148, 136, 0.5)' }}
          ></span>
          <span className="text-xs text-dark-100 hidden sm:inline">Online</span>
        </div>
      </div>
    </header>
  )
}
