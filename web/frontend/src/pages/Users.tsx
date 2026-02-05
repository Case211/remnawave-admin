import { HiSearch, HiPlus, HiRefresh } from 'react-icons/hi'

export default function Users() {
  // TODO: Fetch real data from API
  const users = [
    { uuid: '1', username: 'john_doe', email: 'john@example.com', status: 'active', traffic: '12.5 GB', expire: '2026-03-15' },
    { uuid: '2', username: 'jane_smith', email: 'jane@example.com', status: 'active', traffic: '8.2 GB', expire: '2026-04-20' },
    { uuid: '3', username: 'bob_wilson', email: 'bob@example.com', status: 'disabled', traffic: '25.1 GB', expire: '2026-02-10' },
    { uuid: '4', username: 'alice_brown', email: 'alice@example.com', status: 'limited', traffic: '50.0 GB', expire: '2026-05-01' },
  ]

  const getStatusBadge = (status: string) => {
    switch (status) {
      case 'active':
        return <span className="badge-success">Active</span>
      case 'disabled':
        return <span className="badge-danger">Disabled</span>
      case 'limited':
        return <span className="badge-warning">Limited</span>
      default:
        return <span className="badge-gray">{status}</span>
    }
  }

  return (
    <div className="space-y-6">
      {/* Page header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">Users</h1>
          <p className="text-gray-400 mt-1">Manage your users and subscriptions</p>
        </div>
        <button className="btn-primary">
          <HiPlus className="w-5 h-5 mr-2" />
          Add User
        </button>
      </div>

      {/* Filters */}
      <div className="card">
        <div className="flex flex-col sm:flex-row gap-4">
          <div className="flex-1 relative">
            <HiSearch className="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-gray-500" />
            <input
              type="text"
              placeholder="Search by username, email, UUID..."
              className="input pl-10"
            />
          </div>
          <select className="input w-full sm:w-48">
            <option value="">All Statuses</option>
            <option value="active">Active</option>
            <option value="disabled">Disabled</option>
            <option value="limited">Limited</option>
            <option value="expired">Expired</option>
          </select>
          <button className="btn-secondary">
            <HiRefresh className="w-5 h-5" />
          </button>
        </div>
      </div>

      {/* Users table */}
      <div className="card p-0 overflow-hidden">
        <table className="table">
          <thead>
            <tr>
              <th>Username</th>
              <th>Email</th>
              <th>Status</th>
              <th>Traffic Used</th>
              <th>Expires</th>
              <th className="text-right">Actions</th>
            </tr>
          </thead>
          <tbody>
            {users.map((user) => (
              <tr key={user.uuid}>
                <td className="font-medium text-white">{user.username}</td>
                <td className="text-gray-400">{user.email}</td>
                <td>{getStatusBadge(user.status)}</td>
                <td className="text-gray-300">{user.traffic}</td>
                <td className="text-gray-400">{user.expire}</td>
                <td className="text-right">
                  <button className="btn-ghost text-xs py-1 px-2">View</button>
                  <button className="btn-ghost text-xs py-1 px-2">Edit</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Pagination */}
      <div className="flex items-center justify-between">
        <p className="text-sm text-gray-400">Showing 1-4 of 1,234 users</p>
        <div className="flex gap-2">
          <button className="btn-secondary" disabled>Previous</button>
          <button className="btn-secondary">Next</button>
        </div>
      </div>
    </div>
  )
}
