import { HiShieldExclamation, HiFilter } from 'react-icons/hi'

export default function Violations() {
  // TODO: Fetch real data from API
  const violations = [
    { id: 1, user: '@alice', score: 85, severity: 'high', reason: 'Multiple countries simultaneously', time: '2 hours ago', status: 'pending' },
    { id: 2, user: '@bob', score: 72, severity: 'medium', reason: 'Unusual IP pattern', time: '5 hours ago', status: 'resolved' },
    { id: 3, user: '@charlie', score: 91, severity: 'critical', reason: '5 simultaneous connections', time: '1 day ago', status: 'blocked' },
    { id: 4, user: '@dave', score: 45, severity: 'low', reason: 'New country detected', time: '2 days ago', status: 'dismissed' },
  ]

  const getSeverityBadge = (severity: string) => {
    switch (severity) {
      case 'critical':
        return <span className="badge-danger">Critical</span>
      case 'high':
        return <span className="badge-warning">High</span>
      case 'medium':
        return <span className="badge-info">Medium</span>
      case 'low':
        return <span className="badge-gray">Low</span>
      default:
        return <span className="badge-gray">{severity}</span>
    }
  }

  const getStatusBadge = (status: string) => {
    switch (status) {
      case 'pending':
        return <span className="badge-warning">Pending</span>
      case 'resolved':
        return <span className="badge-success">Resolved</span>
      case 'blocked':
        return <span className="badge-danger">Blocked</span>
      case 'dismissed':
        return <span className="badge-gray">Dismissed</span>
      default:
        return <span className="badge-gray">{status}</span>
    }
  }

  return (
    <div className="space-y-6">
      {/* Page header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">Violations</h1>
          <p className="text-gray-400 mt-1">Anti-abuse detection and management</p>
        </div>
        <button className="btn-secondary">
          <HiFilter className="w-5 h-5 mr-2" />
          Filters
        </button>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <div className="card">
          <p className="text-sm text-gray-400">Total Today</p>
          <p className="text-2xl font-bold text-white mt-1">12</p>
        </div>
        <div className="card">
          <p className="text-sm text-gray-400">Pending Review</p>
          <p className="text-2xl font-bold text-yellow-400 mt-1">3</p>
        </div>
        <div className="card">
          <p className="text-sm text-gray-400">Auto-blocked</p>
          <p className="text-2xl font-bold text-red-400 mt-1">2</p>
        </div>
        <div className="card">
          <p className="text-sm text-gray-400">False Positives</p>
          <p className="text-2xl font-bold text-green-400 mt-1">1</p>
        </div>
      </div>

      {/* Violations list */}
      <div className="space-y-4">
        {violations.map((violation) => (
          <div key={violation.id} className="card">
            <div className="flex items-start justify-between">
              <div className="flex items-start gap-4">
                <div className="p-2 bg-red-500/10 rounded-lg">
                  <HiShieldExclamation className="w-6 h-6 text-red-400" />
                </div>
                <div>
                  <div className="flex items-center gap-2">
                    <h3 className="font-semibold text-white">{violation.user}</h3>
                    {getSeverityBadge(violation.severity)}
                    {getStatusBadge(violation.status)}
                  </div>
                  <p className="text-sm text-gray-400 mt-1">{violation.reason}</p>
                  <p className="text-xs text-gray-500 mt-2">{violation.time}</p>
                </div>
              </div>
              <div className="text-right">
                <p className="text-2xl font-bold text-white">{violation.score}</p>
                <p className="text-xs text-gray-500">Score</p>
              </div>
            </div>

            {violation.status === 'pending' && (
              <div className="mt-4 pt-4 border-t border-dark-700 flex gap-2">
                <button className="btn-danger text-sm">Block User</button>
                <button className="btn-secondary text-sm">Dismiss</button>
                <button className="btn-ghost text-sm">View Details</button>
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}
