import { useEffect, useState } from 'react';
import { deleteUser, getPriceAnomalies, getStats, getUsers } from '../api/admin';
import Spinner from '../components/ui/Spinner';
import { useAuth } from '../hooks/useAuth';
import { extractApiError } from '../utils/errors';

const STAT_LABELS = {
  users: 'Users',
  products: 'Products',
  stores: 'Stores',
  aliases: 'Store listings',
  prices: 'Current prices',
  price_history_records: 'History records',
};

function StatCard({ label, value }) {
  return (
    <div className="rounded-lg border border-gray-200 bg-white p-4">
      <p className="text-xs uppercase tracking-wide text-gray-400">{label}</p>
      <p className="mt-1 text-2xl font-semibold text-gray-900">{value}</p>
    </div>
  );
}

export default function Admin() {
  const { user } = useAuth();
  const [stats, setStats] = useState(null);
  const [users, setUsers] = useState([]);
  const [anomalies, setAnomalies] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    const controller = new AbortController();

    const load = async () => {
      try {
        // Three independent reads -- run them together rather than in series.
        const [statsData, usersData, anomalyData] = await Promise.all([
          getStats({ signal: controller.signal }),
          getUsers({ signal: controller.signal }),
          getPriceAnomalies({ signal: controller.signal }),
        ]);
        setStats(statsData);
        setUsers(usersData);
        setAnomalies(anomalyData);
        setError(null);
      } catch (err) {
        if (err.code === 'ERR_CANCELED') return;
        setError(extractApiError(err, 'Could not load the dashboard.'));
      } finally {
        if (!controller.signal.aborted) setLoading(false);
      }
    };

    load();
    return () => controller.abort();
  }, []);

  const handleDeleteUser = async (id, email) => {
    // Deleting a user cascades to their wishlist, alerts and sessions, so it
    // is worth one confirmation rather than a single misplaced click.
    if (!window.confirm(`Delete ${email}? This cannot be undone.`)) return;

    const previous = users;
    setUsers((current) => current.filter((u) => u.id !== id));
    try {
      await deleteUser(id);
    } catch (err) {
      setUsers(previous);
      setError(extractApiError(err, 'Could not delete that user.'));
    }
  };

  if (loading) {
    return (
      <div className="mx-auto max-w-5xl px-4 py-8">
        <Spinner />
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-5xl px-4 py-8">
      <h1 className="mb-6 text-xl font-semibold text-gray-900">Admin</h1>

      {error && (
        <div role="alert" className="mb-4 rounded bg-red-50 px-4 py-2 text-sm text-red-600">
          {error}
        </div>
      )}

      {stats && (
        <section className="mb-8">
          <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-gray-500">
            Platform
          </h2>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
            {Object.entries(stats).map(([key, value]) => (
              <StatCard key={key} label={STAT_LABELS[key] ?? key} value={value} />
            ))}
          </div>
        </section>
      )}

      <section className="mb-8">
        <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-gray-500">
          Price anomalies
        </h2>
        {anomalies.length === 0 ? (
          <p className="rounded-lg border border-dashed border-gray-300 px-4 py-6 text-center text-sm text-gray-500">
            No price moved more than 50% in the last 24 hours.
          </p>
        ) : (
          <div className="overflow-x-auto rounded-lg border border-gray-200">
            <table className="min-w-full bg-white text-sm">
              <thead className="bg-gray-50 text-left text-gray-600">
                <tr>
                  <th className="px-4 py-3 font-medium">Product</th>
                  <th className="px-4 py-3 font-medium">Was</th>
                  <th className="px-4 py-3 font-medium">Now</th>
                  <th className="px-4 py-3 font-medium">Change</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {anomalies.map((a, i) => (
                  <tr key={`${a.product}-${i}`}>
                    <td className="px-4 py-3 text-gray-900">{a.product}</td>
                    <td className="px-4 py-3 text-gray-500">{a.old_price}</td>
                    <td className="px-4 py-3 text-gray-900">{a.new_price}</td>
                    <td className="px-4 py-3 font-medium text-amber-700">
                      {a.change_percent}%
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section>
        <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-gray-500">
          Users ({users.length})
        </h2>
        <div className="overflow-x-auto rounded-lg border border-gray-200">
          <table className="min-w-full bg-white text-sm">
            <thead className="bg-gray-50 text-left text-gray-600">
              <tr>
                <th className="px-4 py-3 font-medium">ID</th>
                <th className="px-4 py-3 font-medium">Email</th>
                <th className="px-4 py-3 font-medium">Role</th>
                <th className="px-4 py-3" />
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {users.map((u) => (
                <tr key={u.id}>
                  <td className="px-4 py-3 text-gray-400">{u.id}</td>
                  <td className="px-4 py-3 text-gray-900">{u.email}</td>
                  <td className="px-4 py-3">
                    <span
                      className={`rounded-full px-2 py-0.5 text-xs font-medium ${
                        u.role === 'admin'
                          ? 'bg-purple-100 text-purple-800'
                          : 'bg-gray-100 text-gray-600'
                      }`}
                    >
                      {u.role}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-right">
                    {u.id === user?.id ? (
                      // The API rejects self-deletion; not offering the button
                      // is friendlier than letting them click it and get a 400.
                      <span className="text-xs text-gray-400">you</span>
                    ) : (
                      <button
                        onClick={() => handleDeleteUser(u.id, u.email)}
                        className="text-sm text-red-600 hover:text-red-700"
                      >
                        Delete
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
