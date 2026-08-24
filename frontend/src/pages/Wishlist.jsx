import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { getWishlist, removeFromWishlist } from '../api/prices';
import Spinner from '../components/ui/Spinner';
import { extractApiError } from '../utils/errors';
import { formatPrice, formatStoreCount } from '../utils/format';

export default function Wishlist() {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [removing, setRemoving] = useState(null);

  useEffect(() => {
    const controller = new AbortController();

    // Defined inside the effect rather than as a useCallback: the lint rule
    // react-hooks/set-state-in-effect flags a callback that setStates being
    // invoked straight from an effect body.
    const load = async () => {
      try {
        setItems(await getWishlist({ signal: controller.signal }));
        setError(null);
      } catch (err) {
        if (err.code === 'ERR_CANCELED') return;
        setError(extractApiError(err, 'Could not load your wishlist.'));
      } finally {
        if (!controller.signal.aborted) setLoading(false);
      }
    };

    load();
    return () => controller.abort();
  }, []);

  const handleRemove = async (productId) => {
    setRemoving(productId);
    // Optimistic: the row disappears immediately and comes back if the
    // request fails, rather than the list sitting still until the round trip.
    const previous = items;
    setItems((current) => current.filter((i) => i.product_id !== productId));
    try {
      await removeFromWishlist(productId);
    } catch (err) {
      setItems(previous);
      setError(extractApiError(err, 'Could not remove that item.'));
    } finally {
      setRemoving(null);
    }
  };

  if (loading) {
    return (
      <div className="mx-auto max-w-4xl px-4 py-8">
        <Spinner />
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-4xl px-4 py-8">
      <h1 className="mb-1 text-xl font-semibold text-gray-900">Wishlist</h1>
      <p className="mb-6 text-sm text-gray-500">
        {items.length} {items.length === 1 ? 'product' : 'products'} saved
      </p>

      {error && (
        <div role="alert" className="mb-4 rounded bg-red-50 px-4 py-2 text-sm text-red-600">
          {error}
        </div>
      )}

      {items.length === 0 ? (
        <div className="rounded-lg border border-dashed border-gray-300 px-4 py-12 text-center">
          <p className="font-medium text-gray-700">Nothing saved yet.</p>
          <p className="mt-1 text-sm text-gray-500">
            Search for a product and use <span className="font-medium">Save</span> to
            track its price.
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
          {items.map((item) => (
            <li
              key={item.id}
              className="flex flex-col gap-3 rounded-lg border border-gray-200 bg-white p-4 sm:flex-row sm:items-center sm:justify-between"
            >
              <div className="min-w-0 flex-1">
                <Link
                  to={`/product/${item.product_id}`}
                  className="font-medium text-gray-900 hover:text-blue-600"
                >
                  {item.name}
                </Link>
                {item.brand && (
                  <p className="mt-0.5 text-xs uppercase tracking-wide text-gray-400">
                    {item.brand}
                  </p>
                )}
              </div>

              <div className="flex items-center gap-6">
                <div className="text-left sm:text-right">
                  {item.store_count > 0 ? (
                    <>
                      <p className="font-semibold text-gray-900">
                        {formatPrice(item.lowest_total_cost)}
                      </p>
                      <p className="text-xs text-gray-500">
                        {formatStoreCount(item.store_count)}
                        {item.best_deal_store ? ` · ${item.best_deal_store}` : ''}
                      </p>
                    </>
                  ) : (
                    <p className="text-sm text-gray-400">Not in stock</p>
                  )}
                </div>

                <button
                  onClick={() => handleRemove(item.product_id)}
                  disabled={removing === item.product_id}
                  className="text-sm text-red-600 hover:text-red-700 disabled:opacity-50"
                >
                  Remove
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
