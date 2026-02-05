import { HiUsers, HiServer, HiShieldExclamation, HiStatusOnline } from 'react-icons/hi'

// Stat card component
interface StatCardProps {
  title: string
  value: string | number
  icon: React.ElementType
  color: 'blue' | 'green' | 'yellow' | 'red'
  change?: string
}

function StatCard({ title, value, icon: Icon, color, change }: StatCardProps) {
  const colorClasses = {
    blue: 'bg-blue-500/10 text-blue-400',
    green: 'bg-green-500/10 text-green-400',
    yellow: 'bg-yellow-500/10 text-yellow-400',
    red: 'bg-red-500/10 text-red-400',
  }

  return (
    <div className="card">
      <div className="flex items-center justify-between">
        <div>
          <p className="text-sm text-gray-400">{title}</p>
          <p className="text-2xl font-bold text-white mt-1">{value}</p>
          {change && (
            <p className="text-xs text-gray-500 mt-1">{change}</p>
          )}
        </div>
        <div className={`p-3 rounded-lg ${colorClasses[color]}`}>
          <Icon className="w-6 h-6" />
        </div>
      </div>
    </div>
  )
}

export default function Dashboard() {
  // TODO: Fetch real data from API
  const stats = {
    totalUsers: 1234,
    onlineNow: 89,
    activeNodes: 12,
    violations: 5,
  }

  return (
    <div className="space-y-6">
      {/* Page header */}
      <div>
        <h1 className="text-2xl font-bold text-white">Dashboard</h1>
        <p className="text-gray-400 mt-1">Overview of your Remnawave panel</p>
      </div>

      {/* Stats grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard
          title="Total Users"
          value={stats.totalUsers.toLocaleString()}
          icon={HiUsers}
          color="blue"
          change="+12 today"
        />
        <StatCard
          title="Online Now"
          value={stats.onlineNow}
          icon={HiStatusOnline}
          color="green"
        />
        <StatCard
          title="Active Nodes"
          value={stats.activeNodes}
          icon={HiServer}
          color="yellow"
        />
        <StatCard
          title="Violations Today"
          value={stats.violations}
          icon={HiShieldExclamation}
          color="red"
        />
      </div>

      {/* Main content grid */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Recent activity */}
        <div className="card">
          <h2 className="text-lg font-semibold text-white mb-4">Recent Activity</h2>
          <div className="space-y-3">
            {[
              { type: 'connection', message: 'User @john connected from Moscow', time: '2 min ago' },
              { type: 'violation', message: 'Violation detected for @alice (score: 78)', time: '5 min ago' },
              { type: 'block', message: 'User @bob blocked (auto, 24h)', time: '12 min ago' },
              { type: 'node', message: 'Node DE-1 restarted by admin', time: '1 hour ago' },
            ].map((item, index) => (
              <div key={index} className="flex items-center gap-3 py-2 border-b border-dark-700 last:border-0">
                <span className={`w-2 h-2 rounded-full ${
                  item.type === 'connection' ? 'bg-green-500' :
                  item.type === 'violation' ? 'bg-yellow-500' :
                  item.type === 'block' ? 'bg-red-500' : 'bg-blue-500'
                }`}></span>
                <span className="flex-1 text-sm text-gray-300">{item.message}</span>
                <span className="text-xs text-gray-500">{item.time}</span>
              </div>
            ))}
          </div>
        </div>

        {/* Quick actions */}
        <div className="card">
          <h2 className="text-lg font-semibold text-white mb-4">Quick Actions</h2>
          <div className="grid grid-cols-2 gap-3">
            <button className="btn-secondary py-3">
              <HiUsers className="w-5 h-5 mr-2" />
              Add User
            </button>
            <button className="btn-secondary py-3">
              <HiServer className="w-5 h-5 mr-2" />
              Add Node
            </button>
            <button className="btn-secondary py-3">
              <HiShieldExclamation className="w-5 h-5 mr-2" />
              View Violations
            </button>
            <button className="btn-secondary py-3">
              <HiStatusOnline className="w-5 h-5 mr-2" />
              System Health
            </button>
          </div>
        </div>
      </div>

      {/* Placeholder for charts */}
      <div className="card">
        <h2 className="text-lg font-semibold text-white mb-4">Traffic Overview</h2>
        <div className="h-64 flex items-center justify-center border border-dashed border-dark-600 rounded-lg">
          <p className="text-gray-500">Chart will be displayed here</p>
        </div>
      </div>
    </div>
  )
}
