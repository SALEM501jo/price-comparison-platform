import React, { useEffect, useState } from 'react';
import { deleteUser, getPriceAnomalies, getStats, getUsers } from '../api/admin';
import {
  getStoreListings,
  getStores,
  unverifyStore,
  verifyStore,
} from '../api/merchant';
import Spinner from '../components/ui/Spinner';
import { useAuth } from '../hooks/useAuth';
import { extractApiError } from '../utils/errors';

// Merchants can write prices that shoppers see, so they get their own colour
// rather than sharing the shopper grey.
const ROLE_STYLES = {
  admin: 'bg-purple-100 text-purple-800',
  merchant: 'bg-blue-100 text-blue-800',
  user: 'bg-gray-100 text-gray-600',
};

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
    <div className="rounded-lg border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900 p-4">
      <p className="text-xs uppercase tracking-wide text-gray-400 dark:text-gray-500">{label}</p>
      <p className="mt-1 text-2xl font-semibold text-gray-900 dark:text-white">{value}</p>
    </div>
  );
}

export default function Admin() {
  const { user } = useAuth();
  const [stats, setStats] = useState(null);
  const [users, setUsers] = useState([]);
  const [anomalies, setAnomalies] = useState([]);
  const [stores, setStores] = useState([]);
  const [openStoreId, setOpenStoreId] = useState(null);
  const [storeListings, setStoreListings] = useState({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    const controller = new AbortController();

    const load = async () => {
      try {
        // Four independent reads -- run them together rather than in series.
        const [statsData, usersData, anomalyData, storeData] = await Promise.all([
          getStats({ signal: controller.signal }),
          getUsers({ signal: controller.signal }),
          getPriceAnomalies({ signal: controller.signal }),
          getStores({}, { signal: controller.signal }),
        ]);
        setStats(statsData);
        setUsers(usersData);
        setAnomalies(anomalyData);
        setStores(storeData);
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

  // Scraped stores have no claim to check, so they are not listed here.
  const merchantStores = stores.filter((store) => store.is_merchant);

  // Approving a claim on a name and an email alone is guesswork. What a shop
  // actually sells is the evidence. Fetched on demand rather than for every
  // row, since most rows are never opened.
  const toggleStoreListings = async (storeId) => {
    if (openStoreId === storeId) {
      setOpenStoreId(null);
      return;
    }
    setOpenStoreId(storeId);
    if (storeListings[storeId]) return;
    try {
      const data = await getStoreListings(storeId);
      setStoreListings((current) => ({ ...current, [storeId]: data.listings }));
    } catch (err) {
      setError(extractApiError(err, 'Could not load the products for that shop.'));
    }
  };

  const handleVerify = async (store, approve) => {
    // A verification decision changes what shoppers see, so the row is not
    // updated optimistically -- the server's answer is the source of truth.
    try {
      const result = approve
        ? await verifyStore(store.id)
        : await unverifyStore(store.id);
      setStores((current) =>
        current.map((row) =>
          row.id === store.id ? { ...row, is_verified: result.is_verified } : row,
        ),
      );
    } catch (err) {
      setError(extractApiError(err, 'Could not update that store.'));
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
      <h1 className="mb-6 text-xl font-semibold text-gray-900 dark:text-white">Admin</h1>

      {error && (
        <div role="alert" className="mb-4 rounded bg-red-50 dark:bg-red-950/40 px-4 py-2 text-sm text-red-600 dark:text-red-400">
          {error}
        </div>
      )}

      {stats && (
        <section className="mb-8">
          <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400">
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
        <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400">
          Merchant stores
        </h2>
        <p className="mb-3 text-sm text-gray-500 dark:text-gray-400">
          A merchant&rsquo;s prices stay out of search until the claim is
          confirmed. Check that the account really belongs to the shop before
          approving &mdash; anyone can register under any name.
        </p>
        {merchantStores.length === 0 ? (
          <p className="rounded-lg border border-dashed border-gray-300 dark:border-gray-700 px-4 py-6 text-center text-sm text-gray-500 dark:text-gray-400">
            No shops have registered yet.
          </p>
        ) : (
          <div className="overflow-x-auto rounded-lg border border-gray-200 dark:border-gray-800">
            <table className="min-w-full bg-white dark:bg-gray-900 text-sm">
              <thead className="bg-gray-50 dark:bg-gray-900 text-left text-gray-600 dark:text-gray-400">
                <tr>
                  <th className="px-4 py-3 font-medium">Shop</th>
                  <th className="px-4 py-3 font-medium">Account</th>
                  <th className="px-4 py-3 font-medium">Contact</th>
                  <th className="px-4 py-3 font-medium">Listings</th>
                  {/* TAPS, not calls -- a shopper pressing Call or WhatsApp.
                      The header says so because this is the number a shop
                      would be billed against, and the admin deciding what to
                      charge needs to read it the same way the merchant does.
                      Both screens take it from one query in contact_stats. */}
                  <th className="px-4 py-3 font-medium" title="Shoppers who tapped Call, WhatsApp or Facebook. Not calls made, and not sales.">
                    Taps (30d)
                  </th>
                  <th className="px-4 py-3 font-medium">Status</th>
                  <th className="px-4 py-3" />
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100 dark:divide-gray-800">
                {merchantStores.map((store) => (
                  <React.Fragment key={store.id}>
                  <tr>
                    <td className="px-4 py-3">
                      <button
                        onClick={() => toggleStoreListings(store.id)}
                        className="font-medium text-brand-600 dark:text-brand-400 hover:underline"
                        title="Show what this shop lists"
                      >
                        {store.name}
                      </button>
                    </td>
                    <td className="px-4 py-3 text-gray-600 dark:text-gray-400">
                      {store.owner_email}
                      {store.owner_verified_email === false && (
                        <span
                          className="ml-2 rounded bg-amber-100 dark:bg-amber-900/40 px-1.5 py-0.5 text-xs text-amber-800 dark:text-amber-300"
                          title="This account has not confirmed its email address"
                        >
                          email unconfirmed
                        </span>
                      )}
                    </td>
                    <td className="px-4 py-3 text-gray-600 dark:text-gray-400">
                      {store.phone || store.whatsapp || '—'}
                      {store.facebook_url && (
                        <a
                          href={store.facebook_url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="ml-2 text-brand-600 dark:text-brand-400 hover:underline"
                        >
                          page
                        </a>
                      )}
                    </td>
                    <td className="px-4 py-3 text-gray-600 dark:text-gray-400">{store.listing_count}</td>
                    <td className="px-4 py-3 text-gray-600 dark:text-gray-400">
                      <span className="font-medium text-gray-900 dark:text-white">
                        {store.contact_taps ?? 0}
                      </span>
                      {store.contact_taps > 0 && (
                        <span className="ml-2 text-xs text-gray-400 dark:text-gray-500">
                          {['call', 'whatsapp', 'facebook']
                            .filter((c) => store.contact_taps_by_channel?.[c])
                            .map((c) => `${c} ${store.contact_taps_by_channel[c]}`)
                            .join(' · ')}
                        </span>
                      )}
                    </td>
                    <td className="px-4 py-3">
                      {store.is_verified ? (
                        <span className="text-green-700 dark:text-green-400">Verified</span>
                      ) : (
                        <span className="text-amber-700 dark:text-amber-400">Pending</span>
                      )}
                    </td>
                    <td className="px-4 py-3 text-right">
                      <button
                        onClick={() => handleVerify(store, !store.is_verified)}
                        className={
                          store.is_verified
                            ? 'text-xs text-red-600 hover:text-red-700'
                            : 'rounded-md bg-blue-600 px-2.5 py-1 text-xs font-medium text-white hover:bg-blue-700'
                        }
                      >
                        {store.is_verified ? 'Withdraw' : 'Approve'}
                      </button>
                    </td>
                  </tr>
                  {openStoreId === store.id && (
                    <tr>
                      <td colSpan={7} className="bg-gray-50 dark:bg-gray-900 px-4 py-3">
                        {!storeListings[store.id] ? (
                          <p className="text-sm text-gray-500 dark:text-gray-400">Loading...</p>
                        ) : storeListings[store.id].length === 0 ? (
                          <p className="text-sm text-gray-500 dark:text-gray-400">
                            This shop has not listed anything yet.
                          </p>
                        ) : (
                          <ul className="space-y-1.5">
                            {storeListings[store.id].map((listing) => (
                              <li key={listing.id} className="text-sm">
                                <span className="font-medium text-gray-900 dark:text-white">
                                  {listing.name}
                                </span>
                                {listing.condition !== 'new' && (
                                  <span className="ml-2 rounded-full bg-amber-100 dark:bg-amber-900/40 px-2 py-0.5 text-xs text-amber-800 dark:text-amber-300">
                                    {listing.condition}
                                    {listing.battery_health != null &&
                                      ` \u00b7 ${listing.battery_health}%`}
                                  </span>
                                )}
                                <span className="ml-2 text-gray-600 dark:text-gray-400">
                                  {listing.price != null
                                    ? `${listing.price} JOD`
                                    : 'no price'}
                                </span>
                                {!listing.availability && (
                                  <span className="ml-2 text-xs text-gray-400 dark:text-gray-500">
                                    out of stock
                                  </span>
                                )}
                                <span className="ml-2 text-xs text-gray-400 dark:text-gray-500">
                                  matched to &ldquo;{listing.matched_product}&rdquo;
                                </span>
                                {listing.damage_notes && (
                                  <span className="ml-2 text-xs text-amber-700 dark:text-amber-400">
                                    {listing.damage_notes}
                                  </span>
                                )}
                              </li>
                            ))}
                          </ul>
                        )}
                      </td>
                    </tr>
                  )}
                  </React.Fragment>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section className="mb-8">
        <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400">
          Price anomalies
        </h2>
        {anomalies.length === 0 ? (
          <p className="rounded-lg border border-dashed border-gray-300 dark:border-gray-700 px-4 py-6 text-center text-sm text-gray-500 dark:text-gray-400">
            No price moved more than 50% in the last 24 hours.
          </p>
        ) : (
          <div className="overflow-x-auto rounded-lg border border-gray-200 dark:border-gray-800">
            <table className="min-w-full bg-white dark:bg-gray-900 text-sm">
              <thead className="bg-gray-50 dark:bg-gray-900 text-left text-gray-600 dark:text-gray-400">
                <tr>
                  <th className="px-4 py-3 font-medium">Product</th>
                  <th className="px-4 py-3 font-medium">Was</th>
                  <th className="px-4 py-3 font-medium">Now</th>
                  <th className="px-4 py-3 font-medium">Change</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100 dark:divide-gray-800">
                {anomalies.map((a, i) => (
                  <tr key={`${a.product}-${i}`}>
                    <td className="px-4 py-3 text-gray-900 dark:text-white">{a.product}</td>
                    <td className="px-4 py-3 text-gray-500 dark:text-gray-400">{a.old_price}</td>
                    <td className="px-4 py-3 text-gray-900 dark:text-white">{a.new_price}</td>
                    <td className="px-4 py-3 font-medium text-amber-700 dark:text-amber-400">
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
        <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400">
          Users ({users.length})
        </h2>
        <div className="overflow-x-auto rounded-lg border border-gray-200 dark:border-gray-800">
          <table className="min-w-full bg-white dark:bg-gray-900 text-sm">
            <thead className="bg-gray-50 dark:bg-gray-900 text-left text-gray-600 dark:text-gray-400">
              <tr>
                <th className="px-4 py-3 font-medium">ID</th>
                <th className="px-4 py-3 font-medium">Email</th>
                <th className="px-4 py-3 font-medium">Role</th>
                <th className="px-4 py-3" />
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100 dark:divide-gray-800">
              {users.map((u) => (
                <tr key={u.id}>
                  <td className="px-4 py-3 text-gray-400 dark:text-gray-500">{u.id}</td>
                  <td className="px-4 py-3 text-gray-900 dark:text-white">{u.email}</td>
                  <td className="px-4 py-3">
                    {/* A distinct colour per role. Merchants sat in the same
                        grey as shoppers, so the one group with write access to
                        public prices was the hardest to pick out of the list,
                        which is backwards. */}
                    <span
                      className={`rounded-full px-2 py-0.5 text-xs font-medium ${
                        ROLE_STYLES[u.role] ?? ROLE_STYLES.user
                      }`}
                    >
                      {u.role}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-right">
                    {u.id === user?.id ? (
                      // The API rejects self-deletion; not offering the button
                      // is friendlier than letting them click it and get a 400.
                      <span className="text-xs text-gray-400 dark:text-gray-500">you</span>
                    ) : (
                      <button
                        onClick={() => handleDeleteUser(u.id, u.email)}
                        className="text-sm text-red-600 dark:text-red-400 hover:text-red-700"
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
