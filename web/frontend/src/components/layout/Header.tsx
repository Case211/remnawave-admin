import { HiBell, HiSearch, HiMenuAlt2 } from 'react-icons/hi'

interface HeaderProps {
  onMenuToggle?: () => void
}

export default function Header({ onMenuToggle }: HeaderProps) {
  return (
    <header className="h-16 bg-dark-900 border-b border-dark-700 flex items-center justify-between px-4 md:px-6">
      {/* Left side: hamburger + search */}
      <div className="flex items-center gap-3 flex-1">
        {/* Mobile menu button */}
        <button
          onClick={onMenuToggle}
          className="p-2 text-gray-400 hover:text-white rounded-lg hover:bg-dark-800 transition-colors md:hidden"
        >
          <HiMenuAlt2 className="w-6 h-6" />
        </button>

        {/* Search */}
        <div className="flex-1 max-w-md hidden sm:block">
          <div className="relative">
            <HiSearch className="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-gray-500" />
            <input
              type="text"
              placeholder="Search users, nodes..."
              className="w-full pl-10 pr-4 py-2 bg-dark-800 border border-dark-700 rounded-lg text-sm text-gray-100 placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-transparent"
            />
          </div>
        </div>

        {/* Mobile search icon */}
        <button className="p-2 text-gray-400 hover:text-white rounded-lg hover:bg-dark-800 transition-colors sm:hidden">
          <HiSearch className="w-5 h-5" />
        </button>
      </div>

      {/* Right side */}
      <div className="flex items-center gap-2 md:gap-4">
        {/* Notifications */}
        <button className="relative p-2 text-gray-400 hover:text-white rounded-lg hover:bg-dark-800 transition-colors">
          <HiBell className="w-5 h-5" />
          <span className="absolute top-1.5 right-1.5 w-2 h-2 bg-red-500 rounded-full"></span>
        </button>

        {/* Status indicator */}
        <div className="flex items-center gap-2 px-3 py-1.5 bg-dark-800 rounded-lg">
          <span className="w-2 h-2 bg-green-500 rounded-full animate-pulse"></span>
          <span className="text-xs text-gray-400 hidden sm:inline">Online</span>
        </div>
      </div>
    </header>
  )
}
