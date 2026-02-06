import { HiSave, HiRefresh } from 'react-icons/hi'

export default function Settings() {
  return (
    <div className="space-y-6">
      {/* Page header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">Settings</h1>
          <p className="text-gray-400 mt-1">Configure your admin panel</p>
        </div>
        <div className="flex gap-2">
          <button className="btn-secondary">
            <HiRefresh className="w-5 h-5 mr-2" />
            Reset
          </button>
          <button className="btn-primary">
            <HiSave className="w-5 h-5 mr-2" />
            Save Changes
          </button>
        </div>
      </div>

      {/* Settings sections */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Anti-Abuse Settings */}
        <div className="card">
          <h2 className="text-lg font-semibold text-white mb-4">Anti-Abuse Settings</h2>
          <div className="space-y-4">
            <div>
              <label className="block text-sm text-gray-400 mb-2">Monitor Threshold</label>
              <input type="number" className="input" defaultValue={30} />
              <p className="text-xs text-gray-500 mt-1">Score above which users are monitored</p>
            </div>
            <div>
              <label className="block text-sm text-gray-400 mb-2">Warning Threshold</label>
              <input type="number" className="input" defaultValue={50} />
            </div>
            <div>
              <label className="block text-sm text-gray-400 mb-2">Block Threshold</label>
              <input type="number" className="input" defaultValue={80} />
            </div>
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-white">Auto-block enabled</p>
                <p className="text-xs text-gray-500">Automatically block high-score violations</p>
              </div>
              <button className="w-12 h-6 bg-primary-600 rounded-full relative">
                <span className="absolute right-1 top-1 w-4 h-4 bg-white rounded-full"></span>
              </button>
            </div>
          </div>
        </div>

        {/* Notification Settings */}
        <div className="card">
          <h2 className="text-lg font-semibold text-white mb-4">Notifications</h2>
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-white">Violation alerts</p>
                <p className="text-xs text-gray-500">Get notified about new violations</p>
              </div>
              <button className="w-12 h-6 bg-primary-600 rounded-full relative">
                <span className="absolute right-1 top-1 w-4 h-4 bg-white rounded-full"></span>
              </button>
            </div>
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-white">Node status alerts</p>
                <p className="text-xs text-gray-500">Get notified when nodes go offline</p>
              </div>
              <button className="w-12 h-6 bg-primary-600 rounded-full relative">
                <span className="absolute right-1 top-1 w-4 h-4 bg-white rounded-full"></span>
              </button>
            </div>
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-white">Daily reports</p>
                <p className="text-xs text-gray-500">Receive daily summary reports</p>
              </div>
              <button className="w-12 h-6 bg-dark-600 rounded-full relative">
                <span className="absolute left-1 top-1 w-4 h-4 bg-gray-400 rounded-full"></span>
              </button>
            </div>
          </div>
        </div>

        {/* API Settings */}
        <div className="card">
          <h2 className="text-lg font-semibold text-white mb-4">API Configuration</h2>
          <div className="space-y-4">
            <div>
              <label className="block text-sm text-gray-400 mb-2">Remnawave API URL</label>
              <input type="text" className="input" placeholder="https://api.example.com" />
            </div>
            <div>
              <label className="block text-sm text-gray-400 mb-2">API Token</label>
              <input type="password" className="input" placeholder="••••••••••••••••" />
            </div>
            <button className="btn-secondary w-full">Test Connection</button>
          </div>
        </div>

        {/* Sync Settings */}
        <div className="card">
          <h2 className="text-lg font-semibold text-white mb-4">Synchronization</h2>
          <div className="space-y-4">
            <div>
              <label className="block text-sm text-gray-400 mb-2">Sync Interval (seconds)</label>
              <input type="number" className="input" defaultValue={300} />
            </div>
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-white">Auto-sync enabled</p>
                <p className="text-xs text-gray-500">Automatically sync data from Remnawave</p>
              </div>
              <button className="w-12 h-6 bg-primary-600 rounded-full relative">
                <span className="absolute right-1 top-1 w-4 h-4 bg-white rounded-full"></span>
              </button>
            </div>
            <button className="btn-secondary w-full">Sync Now</button>
          </div>
        </div>
      </div>
    </div>
  )
}
