import { HiPlus, HiRefresh, HiStatusOnline, HiStatusOffline } from 'react-icons/hi'

export default function Nodes() {
  // TODO: Fetch real data from API
  const nodes = [
    { uuid: '1', name: 'DE-Frankfurt-1', address: '185.x.x.1', status: 'online', users: 45, traffic: '1.2 TB' },
    { uuid: '2', name: 'NL-Amsterdam-1', address: '185.x.x.2', status: 'online', users: 38, traffic: '890 GB' },
    { uuid: '3', name: 'US-NewYork-1', address: '185.x.x.3', status: 'offline', users: 0, traffic: '2.1 TB' },
    { uuid: '4', name: 'SG-Singapore-1', address: '185.x.x.4', status: 'online', users: 22, traffic: '450 GB' },
  ]

  return (
    <div className="space-y-6">
      {/* Page header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">Nodes</h1>
          <p className="text-gray-400 mt-1">Manage your server nodes</p>
        </div>
        <button className="btn-primary">
          <HiPlus className="w-5 h-5 mr-2" />
          Add Node
        </button>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="card">
          <p className="text-sm text-gray-400">Total Nodes</p>
          <p className="text-2xl font-bold text-white mt-1">4</p>
        </div>
        <div className="card">
          <p className="text-sm text-gray-400">Online</p>
          <p className="text-2xl font-bold text-green-400 mt-1">3</p>
        </div>
        <div className="card">
          <p className="text-sm text-gray-400">Offline</p>
          <p className="text-2xl font-bold text-red-400 mt-1">1</p>
        </div>
      </div>

      {/* Nodes grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {nodes.map((node) => (
          <div key={node.uuid} className="card">
            <div className="flex items-start justify-between">
              <div className="flex items-center gap-3">
                {node.status === 'online' ? (
                  <div className="p-2 bg-green-500/10 rounded-lg">
                    <HiStatusOnline className="w-6 h-6 text-green-400" />
                  </div>
                ) : (
                  <div className="p-2 bg-red-500/10 rounded-lg">
                    <HiStatusOffline className="w-6 h-6 text-red-400" />
                  </div>
                )}
                <div>
                  <h3 className="font-semibold text-white">{node.name}</h3>
                  <p className="text-sm text-gray-500">{node.address}</p>
                </div>
              </div>
              <span className={node.status === 'online' ? 'badge-success' : 'badge-danger'}>
                {node.status}
              </span>
            </div>

            <div className="mt-4 grid grid-cols-2 gap-4">
              <div>
                <p className="text-xs text-gray-500">Active Users</p>
                <p className="text-lg font-semibold text-white">{node.users}</p>
              </div>
              <div>
                <p className="text-xs text-gray-500">Traffic Used</p>
                <p className="text-lg font-semibold text-white">{node.traffic}</p>
              </div>
            </div>

            <div className="mt-4 flex gap-2">
              <button className="btn-secondary flex-1 text-sm">View Details</button>
              <button className="btn-ghost">
                <HiRefresh className="w-4 h-4" />
              </button>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
