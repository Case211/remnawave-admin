import { Link, useLocation } from 'react-router-dom'
import {
  HiHome,
  HiUsers,
  HiServer,
  HiShieldExclamation,
  HiCog,
  HiLogout,
  HiX,
} from 'react-icons/hi'
import { useAuthStore } from '../../store/authStore'

const navigation = [
  { name: 'Dashboard', href: '/', icon: HiHome },
  { name: 'Users', href: '/users', icon: HiUsers },
  { name: 'Nodes', href: '/nodes', icon: HiServer },
  { name: 'Violations', href: '/violations', icon: HiShieldExclamation },
  { name: 'Settings', href: '/settings', icon: HiCog },
]

interface SidebarProps {
  mobileOpen?: boolean
  onClose?: () => void
}

export default function Sidebar({ mobileOpen, onClose }: SidebarProps) {
  const location = useLocation()
  const { logout, user } = useAuthStore()

  const handleNavClick = () => {
    if (onClose) onClose()
  }

  return (
    <>
      {/* Mobile overlay backdrop */}
      {mobileOpen && (
        <div
          className="fixed inset-0 z-40 bg-black/60 backdrop-blur-sm md:hidden"
          onClick={onClose}
        />
      )}

      {/* Sidebar */}
      <div
        className={`
          fixed inset-y-0 left-0 z-50 flex flex-col w-64 bg-dark-900 border-r border-dark-700
          transform transition-transform duration-300 ease-in-out
          md:relative md:translate-x-0 md:transition-none
          ${mobileOpen ? 'translate-x-0' : '-translate-x-full'}
        `}
      >
        {/* Logo */}
        <div className="flex items-center justify-between h-16 px-6 border-b border-dark-700">
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 bg-primary-600 rounded-lg flex items-center justify-center">
              <span className="text-white font-bold text-sm">R</span>
            </div>
            <span className="text-lg font-bold text-white">Remnawave</span>
          </div>
          {/* Mobile close button */}
          <button
            onClick={onClose}
            className="p-1.5 text-gray-400 hover:text-white rounded-lg hover:bg-dark-800 transition-colors md:hidden"
          >
            <HiX className="w-5 h-5" />
          </button>
        </div>

        {/* Navigation */}
        <nav className="flex-1 px-3 py-4 space-y-1 overflow-y-auto">
          {navigation.map((item) => {
            const isActive = location.pathname === item.href
            return (
              <Link
                key={item.name}
                to={item.href}
                onClick={handleNavClick}
                className={`flex items-center px-3 py-2.5 text-sm font-medium rounded-lg transition-colors ${
                  isActive
                    ? 'bg-primary-600 text-white'
                    : 'text-gray-400 hover:text-white hover:bg-dark-800'
                }`}
              >
                <item.icon className="w-5 h-5 mr-3 flex-shrink-0" />
                {item.name}
              </Link>
            )
          })}
        </nav>

        {/* User info */}
        <div className="p-4 border-t border-dark-700">
          <div className="flex items-center">
            <div className="w-9 h-9 bg-dark-700 rounded-full flex items-center justify-center">
              <span className="text-sm font-medium text-gray-300">
                {user?.username?.charAt(0).toUpperCase() || 'A'}
              </span>
            </div>
            <div className="ml-3 flex-1 min-w-0">
              <p className="text-sm font-medium text-white truncate">
                {user?.username || 'Admin'}
              </p>
              <p className="text-xs text-gray-500">Administrator</p>
            </div>
            <button
              onClick={logout}
              className="p-2 text-gray-400 hover:text-white rounded-lg hover:bg-dark-800 transition-colors"
              title="Logout"
            >
              <HiLogout className="w-5 h-5" />
            </button>
          </div>
        </div>
      </div>
    </>
  )
}
