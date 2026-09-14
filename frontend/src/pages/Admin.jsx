import React, { useEffect, useState } from 'react';
import {
  adminDeleteListing,
  adminUpdateListing,
  deleteUser,
  getPriceAnomalies,
  getStats,
  getUsers,
} from '../api/admin';
import {
  declineStore,
  getStoreListings,
  getStores,
  unverifyStore,
  verifyStore,
} from '../api/merchant';
import SupportMessages from '../components/admin/SupportMessages';
import Spinner from '../components/ui/Spinner';
import { useAuth } from '../hooks/useAuth';
import { extractApiError } from '../utils/errors';
import { useDocumentMeta } from '../hooks/useDocumentMeta';
import { useLocale } from '../hooks/useLocale';

// Merchants can write prices that shoppers see, so they get their own colour
// rather than sharing the shopper grey.
const ROLE_STYLES = {
  admin: 'bg-purple-100 text-purple-800',
  merchant: 'bg-blue-100 text-blue-800',
  user: 'bg-gray-100 text-gray-600',
};

// Translation KEYS, not English. The labels are resolved where `t` is in
// scope; keeping the words here would have meant a second copy of them, and
// the pair would drift the first time one was edited.
const STAT_LABELS = {
  users: 'admin.stat.users',
  products: 'admin.stat.products',
  stores: 'admin.stat.stores',
  aliases: 'admin.stat.aliases',
  prices: 'admin.stat.prices',
  price_history_records: 'admin.stat.history',
};

function StatCard({ label, value }) {
  return (
    <div className="rounded-lg border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900 p-4">
      <p className="text-xs uppercase tracking-wide text-gray-400 dark:text-gray-500">{label}</p>
      <p className="mt-1 text-2xl font-semibold text-gray-900 dark:text-white">{value}</p>
    </div>
  );
}

/**
 * One merchant listing, editable by an admin.
 *
 * WHY AN ADMIN CAN EDIT A SHOP'S PRICE AT ALL: a wrong price is the single
 * thing a comparison site must never show, and "email the shop and wait" is
 * not a remedy. The backend route for this already existed and nothing in the
 * UI ever reached it, so in practice the only way to fix a bad price was a
 * query against the database.
 *
 * It calls /admin/listings/{id}, NOT the merchant route. That separation is
 * deliberate: the merchant route resolves the store from the signed-in user
 * and therefore cannot touch another shop's data, and an `if admin` branch
 * inside it would destroy exactly that guarantee. Every edit here is logged
 * with the admin's id, because an administrator quietly changing a shop's
 * advertised price is precisely the action that has to be answerable later.
 */
function AdminListingRow({ listing, onChanged, onRemoved, onError }) {
  const { t } = useLocale();
  const [price, setPrice] = useState(
    listing.price != null ? String(listing.price) : '',
  );
  const [busy, setBusy] = useState(false);

  const dirty = price !== '' && Number(price) !== listing.price;

  const save = async () => {
    setBusy(true);
    try {
      onChanged(await adminUpdateListing(listing.id, { price: Number(price) }));
    } catch (err) {
      onError(extractApiError(err, t('admin.error.listing')));
    } finally {
      setBusy(false);
    }
  };

  const toggleStock = async () => {
    setBusy(true);
    try {
      onChanged(
        await adminUpdateListing(listing.id, {
          availability: !listing.availability,
        }),
      );
    } catch (err) {
      onError(extractApiError(err, t('admin.error.listing')));
    } finally {
      setBusy(false);
    }
  };

  const remove = async () => {
    if (
      !window.confirm(
        `Remove "${listing.name}" from this shop? Its price history goes with it and this cannot be undone.`,
      )
    ) {
      return;
    }
    setBusy(true);
    try {
      await adminDeleteListing(listing.id);
      onRemoved(listing.id);
    } catch (err) {
      onError(extractApiError(err, t('admin.error.removeListing')));
      setBusy(false);
    }
  };

  return (
    <li className="flex flex-wrap items-center gap-x-2 gap-y-1 text-sm">
      <span className="font-medium text-gray-900 dark:text-white">
        {listing.name}
      </span>
      {listing.condition !== 'new' && (
        <span className="rounded-full bg-amber-100 px-2 py-0.5 text-xs text-amber-800 dark:bg-amber-900/40 dark:text-amber-300">
          {listing.condition}
          {listing.battery_health != null && ` \u00b7 ${listing.battery_health}%`}
        </span>
      )}
      <span className="text-xs text-gray-400 dark:text-gray-500">
        matched to &ldquo;{listing.matched_product}&rdquo;
      </span>
      {listing.damage_notes && (
        <span className="text-xs text-amber-700 dark:text-amber-400">
          {listing.damage_notes}
        </span>
      )}

      <span className="ms-auto flex items-center gap-1.5">
        <input
          type="number"
          min="0.001"
          step="0.001"
          value={price}
          onChange={(e) => setPrice(e.target.value)}
          aria-label={`Price for ${listing.name}`}
          className="w-24 rounded-md border border-gray-300 px-2 py-1 text-xs dark:border-gray-700"
        />
        <button
          type="button"
          onClick={save}
          disabled={busy || !dirty}
          className="rounded-md bg-brand-600 px-2 py-1 text-xs font-medium text-white hover:bg-brand-700 disabled:opacity-40"
        >
          Save
        </button>
        <button
          type="button"
          onClick={toggleStock}
          disabled={busy}
          title={t('common.clickToChange')}
          className={`rounded-md px-2 py-1 text-xs font-medium disabled:opacity-40 ${
            listing.availability
              ? 'bg-green-100 text-green-800 dark:bg-green-900/40 dark:text-green-300'
              : 'bg-gray-200 text-gray-600 dark:bg-gray-700 dark:text-gray-300'
          }`}
        >
          {listing.availability ? 'In stock' : 'Out of stock'}
        </button>
        <button
          type="button"
          onClick={remove}
          disabled={busy}
          className="text-xs text-red-600 hover:text-red-700 disabled:opacity-40"
        >
          Remove
        </button>
      </span>
    </li>
  );
}

export default function Admin() {
  const { t } = useLocale();
  useDocumentMeta({ title: t('admin.title'), noindex: true });
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
        setError(extractApiError(err, t('admin.error.dashboard')));
      } finally {
        if (!controller.signal.aborted) setLoading(false);
      }
    };

    load();
    return () => controller.abort();
    // `t` is a dependency because the error path renders a translated string:
    // switching language while the dashboard is open should not leave the
    // previous language's message on screen. The other pages here do the same.
  }, [t]);

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
      setError(extractApiError(err, t('admin.error.user')));
    }
  };

  // Scraped stores have no claim to check, so they are not listed here.
  const merchantStores = stores.filter((store) => store.is_merchant);

  // Approving a claim on a name and an email alone is guesswork. What a shop
  // actually sells is the evidence. Fetched on demand rather than for every
  // row, since most rows are never opened.
  const handleDecline = async (store) => {
    // Worth one confirmation: it is a judgement about somebody's business,
    // and although it is reversible the shop sees the effect immediately.
    if (
      !window.confirm(
        `Decline "${store.name}"? Their prices stay hidden from shoppers. ` +
          'You can approve them later if they send proof.',
      )
    ) {
      return;
    }
    try {
      const result = await declineStore(store.id);
      setStores((current) =>
        current.map((row) =>
          row.id === store.id
            ? {
                ...row,
                is_verified: false,
                review_status: result.review_status,
                rejected_at: new Date().toISOString(),
              }
            : row,
        ),
      );
    } catch (err) {
      setError(extractApiError(err, t('admin.error.decline')));
    }
  };

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
      setError(extractApiError(err, t('admin.error.shopListings')));
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
          row.id === store.id
            ? {
                ...row,
                is_verified: result.is_verified,
                review_status: result.is_verified ? 'verified' : 'pending',
                // Approving clears a decline, so the row must stop showing
                // one -- the server has already cleared the column.
                rejected_at: null,
              }
            : row,
        ),
      );
    } catch (err) {
      setError(extractApiError(err, t('admin.error.store')));
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
      <h1 className="mb-6 text-xl font-semibold text-gray-900 dark:text-white">
        {t('admin.title')}
      </h1>

      {error && (
        <div role="alert" className="mb-4 rounded bg-red-50 dark:bg-red-950/40 px-4 py-2 text-sm text-red-600 dark:text-red-400">
          {error}
        </div>
      )}

      {stats && (
        <section className="mb-8">
          <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400">
            {t('admin.platform')}
          </h2>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
            {Object.entries(stats).map(([key, value]) => (
              <StatCard key={key} label={t(STAT_LABELS[key] ?? key)} value={value} />
            ))}
          </div>
        </section>
      )}

      <section className="mb-8">
        <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400">
          {t('admin.merchantStores')}
        </h2>
        <p className="mb-3 text-sm text-gray-500 dark:text-gray-400">
          {t('admin.merchantStoresBlurb')}
        </p>
        {merchantStores.length === 0 ? (
          <p className="rounded-lg border border-dashed border-gray-300 dark:border-gray-700 px-4 py-6 text-center text-sm text-gray-500 dark:text-gray-400">
            {t('admin.noShops')}
          </p>
        ) : (
          <div className="overflow-x-auto rounded-lg border border-gray-200 dark:border-gray-800">
            <table className="min-w-full bg-white dark:bg-gray-900 text-sm">
              <thead className="bg-gray-50 dark:bg-gray-900 text-left text-gray-600 dark:text-gray-400">
                <tr>
                  <th className="px-4 py-3 font-medium">{t('admin.shop')}</th>
                  <th className="px-4 py-3 font-medium">{t('admin.account')}</th>
                  <th className="px-4 py-3 font-medium">{t('admin.contact')}</th>
                  <th className="px-4 py-3 font-medium">{t('admin.listings')}</th>
                  {/* TAPS, not calls -- a shopper pressing Call or WhatsApp.
                      The header says so because this is the number a shop
                      would be billed against, and the admin deciding what to
                      charge needs to read it the same way the merchant does.
                      Both screens take it from one query in contact_stats. */}
                  <th className="px-4 py-3 font-medium" title={t('admin.tapsHint')}>
                    {t('admin.taps')}
                  </th>
                  <th className="px-4 py-3 font-medium">{t('admin.status')}</th>
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
                        title={t('admin.showListings')}
                      >
                        {store.name}
                      </button>
                    </td>
                    <td className="px-4 py-3 text-gray-600 dark:text-gray-400">
                      {store.owner_email}
                      {store.owner_verified_email === false && (
                        <span
                          className="ml-2 rounded bg-amber-100 dark:bg-amber-900/40 px-1.5 py-0.5 text-xs text-amber-800 dark:text-amber-300"
                          title={t('admin.emailUnconfirmedHint')}
                        >
                          {t('admin.emailUnconfirmed')}
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
                          {['call', 'whatsapp', 'facebook', 'instagram']
                            .filter((c) => store.contact_taps_by_channel?.[c])
                            .map((c) => `${c} ${store.contact_taps_by_channel[c]}`)
                            .join(' · ')}
                        </span>
                      )}
                    </td>
                    <td className="px-4 py-3">
                      {/* Three states. "Declined" is the one that was missing:
                          without it a rejected claim looked identical to one
                          nobody had reviewed, and the queue never emptied. */}
                      {store.review_status === 'verified' ? (
                        <span className="text-green-700 dark:text-green-400">{t('admin.verified')}</span>
                      ) : store.review_status === 'declined' ? (
                        <span
                          className="text-red-600 dark:text-red-400"
                          title={
                            store.rejected_at
                              ? `Declined ${new Date(store.rejected_at).toLocaleDateString()}`
                              : 'Declined'
                          }
                        >
                          {t('admin.declined')}
                        </span>
                      ) : (
                        <span className="text-amber-700 dark:text-amber-400">{t('admin.pending')}</span>
                      )}
                    </td>
                    <td className="px-4 py-3 text-right">
                      <div className="flex items-center justify-end gap-2">
                        <button
                          onClick={() => handleVerify(store, !store.is_verified)}
                          className={
                            store.is_verified
                              ? 'text-xs text-red-600 hover:text-red-700'
                              : 'rounded-md bg-brand-600 px-2.5 py-1 text-xs font-medium text-white hover:bg-brand-700'
                          }
                        >
                          {store.is_verified
                            ? t('admin.withdraw')
                            : store.review_status === 'declined'
                              ? t('admin.approveAnyway')
                              : t('admin.approve')}
                        </button>
                        {/* Only offered while the claim is still open. A
                            verified shop is withdrawn, not declined, and a
                            claim already declined has nothing to decline. */}
                        {store.review_status === 'pending' && (
                          <button
                            onClick={() => handleDecline(store)}
                            className="rounded-md border border-gray-300 px-2.5 py-1 text-xs font-medium text-gray-700 hover:bg-gray-50 dark:border-gray-700 dark:text-gray-300 dark:hover:bg-gray-800"
                          >
                            {t('admin.decline')}
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                  {openStoreId === store.id && (
                    <tr>
                      <td colSpan={7} className="bg-gray-50 dark:bg-gray-900 px-4 py-3">
                        {!storeListings[store.id] ? (
                          <p className="text-sm text-gray-500 dark:text-gray-400">{t('admin.loading')}</p>
                        ) : storeListings[store.id].length === 0 ? (
                          <p className="text-sm text-gray-500 dark:text-gray-400">
                            {t('admin.shopHasNothing')}
                          </p>
                        ) : (
                          <ul className="space-y-1.5">
                            {storeListings[store.id].map((listing) => (
                              <AdminListingRow
                                key={listing.id}
                                listing={listing}
                                onChanged={(updated) =>
                                  setStoreListings((current) => ({
                                    ...current,
                                    [store.id]: current[store.id].map((row) =>
                                      row.id === updated.id
                                        ? { ...row, ...updated }
                                        : row,
                                    ),
                                  }))
                                }
                                onRemoved={(id) =>
                                  setStoreListings((current) => ({
                                    ...current,
                                    [store.id]: current[store.id].filter(
                                      (row) => row.id !== id,
                                    ),
                                  }))
                                }
                                onError={setError}
                              />
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

      {/* Above price anomalies: a person waiting for a reply outranks a
          number that moved. */}
      <SupportMessages />

      <section className="mb-8">
        <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400">
          {t('admin.priceAnomalies')}
        </h2>
        {anomalies.length === 0 ? (
          <p className="rounded-lg border border-dashed border-gray-300 dark:border-gray-700 px-4 py-6 text-center text-sm text-gray-500 dark:text-gray-400">
            {t('admin.noAnomalies')}
          </p>
        ) : (
          <div className="overflow-x-auto rounded-lg border border-gray-200 dark:border-gray-800">
            <table className="min-w-full bg-white dark:bg-gray-900 text-sm">
              <thead className="bg-gray-50 dark:bg-gray-900 text-left text-gray-600 dark:text-gray-400">
                <tr>
                  <th className="px-4 py-3 font-medium">{t('admin.product')}</th>
                  <th className="px-4 py-3 font-medium">{t('admin.was')}</th>
                  <th className="px-4 py-3 font-medium">{t('admin.now')}</th>
                  <th className="px-4 py-3 font-medium">{t('admin.change')}</th>
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
          {t('admin.users', { count: users.length })}
        </h2>
        <div className="overflow-x-auto rounded-lg border border-gray-200 dark:border-gray-800">
          <table className="min-w-full bg-white dark:bg-gray-900 text-sm">
            <thead className="bg-gray-50 dark:bg-gray-900 text-left text-gray-600 dark:text-gray-400">
              <tr>
                <th className="px-4 py-3 font-medium">{t('admin.id')}</th>
                <th className="px-4 py-3 font-medium">{t('admin.email')}</th>
                <th className="px-4 py-3 font-medium">{t('admin.role')}</th>
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
                        className="inline-flex min-h-11 items-center text-sm text-red-600 hover:text-red-700 dark:text-red-400"
                      >
                        {t('admin.delete')}
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
