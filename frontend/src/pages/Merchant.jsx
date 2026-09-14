import { useEffect, useState } from 'react';

import { getMyListings, getMyStore } from '../api/merchant';
import AddListing from '../components/merchant/AddListing';
import ContactPanel from '../components/merchant/ContactPanel';
import ContactStats from '../components/merchant/ContactStats';
import ListingRow from '../components/merchant/ListingRow';
import StoreRegistration from '../components/merchant/StoreRegistration';
import Spinner from '../components/ui/Spinner';
import { useDocumentMeta } from '../hooks/useDocumentMeta';
import { useLocale } from '../hooks/useLocale';
import { extractApiError } from '../utils/errors';

/**
 * A shop manages its own store and prices.
 *
 * The page has two states rather than two routes: an account either has a
 * store or it does not, and asking the server is how we find out. A 404 from
 * GET /merchant/store is the normal "not a merchant yet" answer, not an error
 * to show the user.
 *
 * WHAT LIVES WHERE: this file is composition only. The registration form, the
 * add-product form, one product row and the contact panel are each their own
 * component under components/merchant, because at 788 lines this page had
 * stopped being read and started being scrolled.
 */

export default function Merchant() {
  const { t } = useLocale();
  // Out of search although shops want to be found: this is the dashboard a
  // shop is run from, not what a shopper looks for. Shoppers reach a shop
  // through its products.
  useDocumentMeta({ title: t('nav.myShop'), noindex: true });
  const [store, setStore] = useState(null);
  const [listings, setListings] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  // `loading` starts true and is only cleared once the request settles. No
  // state is set synchronously in the effect body -- doing so triggers a
  // cascading render, and the other pages here follow the same shape.
  useEffect(() => {
    const controller = new AbortController();

    const load = async () => {
      try {
        const mine = await getMyStore({ signal: controller.signal });
        setStore(mine);
        setListings(await getMyListings({ signal: controller.signal }));
        setError(null);
      } catch (err) {
        if (err.code === 'ERR_CANCELED') return;
        // 404 is the normal answer for an account that has not registered a
        // shop, and 403 for one that never had the role. Neither is a failure.
        const status = err?.response?.status;
        if (status === 404 || status === 403) {
          setStore(null);
        } else {
          setError(extractApiError(err, t('merchant.loadError')));
        }
      } finally {
        if (!controller.signal.aborted) setLoading(false);
      }
    };

    load();
    return () => controller.abort();
  }, [t]);

  if (loading) return <Spinner />;

  if (error) {
    return (
      <div className="mx-auto max-w-3xl px-4 py-12">
        <p className="rounded-lg bg-red-50 dark:bg-red-950/40 px-4 py-3 text-sm text-red-700 dark:text-red-300">{error}</p>
      </div>
    );
  }

  if (!store) {
    return (
      <StoreRegistration
        onCreated={(created) => {
          setStore(created);
          setListings([]);
        }}
      />
    );
  }

  return (
    <div className="mx-auto max-w-4xl px-4 py-8">
      <header className="mb-6 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold text-gray-900 dark:text-white">{store.name}</h1>
          <p className="text-sm text-gray-500 dark:text-gray-400">
            {store.listing_count === 1
              ? t('merchant.productCountOne')
              : t('merchant.productCount', { count: store.listing_count })}
          </p>
        </div>
        {store.is_verified ? (
          <span className="rounded-full bg-green-100 dark:bg-green-900/40 px-3 py-1 text-xs font-medium text-green-800 dark:text-green-300">
            {t('merchant.verified')}
          </span>
        ) : (
          <span className="rounded-full bg-amber-100 dark:bg-amber-900/40 px-3 py-1 text-xs font-medium text-amber-800 dark:text-amber-300">
            {t('merchant.pending')}
          </span>
        )}
      </header>

      {!store.is_verified && (
        <p className="mb-6 rounded-lg border border-amber-200 dark:border-amber-900/50 bg-amber-50 dark:bg-amber-950/40 px-4 py-3 text-sm text-amber-900 dark:text-amber-200">
          {t('merchant.pendingNote')}
        </p>
      )}

      <div className="space-y-6">
        {/* First, because it answers the question a shop owner actually
            opens this page with: is any of this working? */}
        <ContactStats isVerified={store.is_verified} />

        <ContactPanel store={store} onSaved={setStore} />

        <AddListing
          onAdded={(created) => {
            setListings((current) => [
              created,
              ...current.filter((row) => row.id !== created.id),
            ]);
            setStore((current) => ({
              ...current,
              listing_count: current.listing_count + 1,
            }));
          }}
        />

        <div>
          <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400">
            {t('merchant.yourProducts')}
          </h2>
          {listings.length === 0 ? (
            <p className="rounded-lg border border-dashed border-gray-300 dark:border-gray-700 px-4 py-8 text-center text-sm text-gray-500 dark:text-gray-400">
              {t('merchant.noProducts')}
            </p>
          ) : (
            <div className="overflow-x-auto rounded-lg border border-gray-200 dark:border-gray-800">
              <table className="min-w-full bg-white dark:bg-gray-900 text-sm">
                <thead className="bg-gray-50 dark:bg-gray-900 text-left text-gray-600 dark:text-gray-400">
                  <tr>
                    <th className="px-4 py-3 font-medium">{t('merchant.productName')}</th>
                    <th className="px-4 py-3 font-medium">{t('table.price')}</th>
                    <th className="px-4 py-3 font-medium">{t('table.delivery')}</th>
                    <th className="px-4 py-3 font-medium">{t('table.availability')}</th>
                    <th className="px-4 py-3" />
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100 dark:divide-gray-800">
                  {listings.map((listing) => (
                    <ListingRow
                      key={listing.id}
                      listing={listing}
                      onChanged={(updated) =>
                        setListings((current) =>
                          current.map((row) =>
                            row.id === updated.id ? updated : row,
                          ),
                        )
                      }
                      onRemoved={(id) => {
                        setListings((current) =>
                          current.filter((row) => row.id !== id),
                        );
                        setStore((current) => ({
                          ...current,
                          listing_count: Math.max(0, current.listing_count - 1),
                        }));
                      }}
                    />
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
