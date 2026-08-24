import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { deleteAlert, getAlerts } from '../api/prices';
import Spinner from '../components/ui/Spinner';
import { extractApiError } from '../utils/errors';
import { formatPrice } from '../utils/format';

/** How close the current price is to the target, as a percentage over it. */
function gapToTarget(alert) {
  if (!alert.lowest_total_cost || !alert.target_price) return null;
  const over = alert.lowest_total_cost - alert.target_price;
  if (over <= 0) return 0;
  return Math.round((over / alert.target_price) * 100);
}

export default function Alerts() {
  const [alerts, setAlerts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    const controller = new AbortController();

    const load = async () => {
      try {
        setAlerts(await getAlerts({ signal: controller.signal }));
        setError(null);
      } catch (err) {
        if (err.code === 'ERR_CANCELED') return;
        setError(extractApiError(err, 'Could not load your alerts.'));
      } finally {
        if (!controller.signal.aborted) setLoading(false);
      }
    };

    load();
    return () => controller.abort();
  }, []);

  const handleDelete = async (alertId) => {
    const previous = alerts;
    setAlerts((current) => current.filter((a) => a.id !== alertId));
    try {
      await deleteAlert(alertId);
    } catch (err) {
      setAlerts(previous);
      setError(extractApiError(err, 'Could not delete that alert.'));
    }
  };

  if (loading) {
    return (
      <div className="mx-auto max-w-4xl px-4 py-8">
        <Spinner />
      </div>
    );
  }

  const met = alerts.filter((a) => a.is_met);

  return (
    <div className="mx-auto max-w-4xl px-4 py-8">
      <h1 className="mb-1 text-xl font-semibold text-gray-900">Price alerts</h1>
      <p className="mb-6 text-sm text-gray-500">
        {alerts.length} active
        {met.length > 0 && (
          <span className="ml-2 rounded-full bg-green-100 px-2 py-0.5 text-xs font-medium text-green-800">
            {met.length} target{met.length === 1 ? '' : 's'} reached
          </span>
        )}
      </p>

      {error && (
        <div role="alert" className="mb-4 rounded bg-red-50 px-4 py-2 text-sm text-red-600">
          {error}
        </div>
      )}

      {alerts.length === 0 ? (
        <div className="rounded-lg border border-dashed border-gray-300 px-4 py-12 text-center">
          <p className="font-medium text-gray-700">No alerts yet.</p>
          <p className="mt-1 text-sm text-gray-500">
            Open a product and set a target price to be told when it drops.
          </p>
          <Link
            to="/"
            className="mt-4 inline-block rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700"
          >
            Start searching
          </Link>
        </div>
      ) : (
        <ul className="space-y-3">
          {alerts.map((alert) => {
            const gap = gapToTarget(alert);
            return (
              <li
                key={alert.id}
                className={`rounded-lg border bg-white p-4 ${
                  alert.is_met ? 'border-green-300 bg-green-50/50' : 'border-gray-200'
                }`}
              >
                <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                  <div className="min-w-0 flex-1">
                    <Link
                      to={`/product/${alert.product_id}`}
                      className="font-medium text-gray-900 hover:text-blue-600"
                    >
                      {alert.product_name}
                    </Link>

                    <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-sm">
                      <span className="text-gray-500">
                        Target{' '}
                        <span className="font-medium text-gray-900">
                          {formatPrice(alert.target_price)}
                        </span>
                      </span>
                      <span className="text-gray-500">
                        Now{' '}
                        <span className="font-medium text-gray-900">
                          {formatPrice(alert.lowest_total_cost)}
                        </span>
                        {alert.best_deal_store ? ` · ${alert.best_deal_store}` : ''}
                      </span>
                    </div>

                    {alert.is_met ? (
                      <p className="mt-2 text-sm font-medium text-green-700">
                        Target reached — buy now
                      </p>
                    ) : (
                      gap !== null && (
                        <p className="mt-2 text-sm text-gray-500">
                          {gap}% above your target
                        </p>
                      )
                    )}
                  </div>

                  <button
                    onClick={() => handleDelete(alert.id)}
                    className="shrink-0 text-sm text-red-600 hover:text-red-700"
                  >
                    Delete
                  </button>
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
