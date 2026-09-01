import { useState } from 'react';

import { deleteListing, updateListing } from '../../api/merchant';
import ListingPhotoCell from './ListingPhotoCell';
import { useLocale } from '../../hooks/useLocale';
import { extractApiError } from '../../utils/errors';
import { formatAge, formatPrice, isPriceStale } from '../../utils/format';

export default function ListingRow({ listing, onChanged, onRemoved }) {
  const { t } = useLocale();
  const [price, setPrice] = useState(String(listing.price));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  const dirty = Number(price) !== listing.price;

  const save = async () => {
    setBusy(true);
    setError(null);
    try {
      onChanged(await updateListing(listing.id, { price: Number(price) }));
    } catch (err) {
      setError(extractApiError(err, t('merchant.saveError')));
    } finally {
      setBusy(false);
    }
  };

  const remove = async () => {
    // Removing takes the price history with it and cannot be undone, so it
    // is worth one confirmation rather than a single misplaced click -- the
    // same treatment user deletion gets in the admin screen.
    if (!window.confirm(t('merchant.confirmRemove', { name: listing.name }))) {
      return;
    }
    setBusy(true);
    try {
      await deleteListing(listing.id);
      onRemoved(listing.id);
    } catch (err) {
      setError(extractApiError(err, t('merchant.saveError')));
      setBusy(false);
    }
  };

  // Selling out is far more common than deleting a listing, and until now the
  // only way to express it was to remove the product and retype it later.
  const toggleStock = async () => {
    setBusy(true);
    setError(null);
    try {
      onChanged(
        await updateListing(listing.id, { availability: !listing.availability }),
      );
    } catch (err) {
      setError(extractApiError(err, t('merchant.saveError')));
    } finally {
      setBusy(false);
    }
  };

  // `t` is not optional here. Without it formatAge falls back to returning
  // the key itself, and the row rendered "Updated time.today" -- in both
  // languages, on the one screen a shop owner uses every day.
  const age = formatAge(listing.last_updated, t);
  const stale = isPriceStale(listing.last_updated);

  return (
    <tr className="align-top">
      <td className="px-4 py-3">
        <div className="flex items-start gap-3">
        <ListingPhotoCell listing={listing} onChanged={onChanged} />
        <div className="min-w-0 flex-1">
        <span className="font-medium text-gray-900 dark:text-white">{listing.name}</span>
        {listing.condition !== 'new' && (
          <span className="ml-2 rounded-full bg-amber-100 dark:bg-amber-900/40 px-2 py-0.5 text-xs font-medium text-amber-800 dark:text-amber-300">
            {/* The stored value is a database word ("used", "refurbished").
                Rendering it raw put English in the middle of the Arabic row;
                the add-product form above already translates the same three
                conditions, so reuse its wording rather than inventing a
                second vocabulary for the same thing. */}
            {t(
              listing.condition === 'refurbished'
                ? 'merchant.conditionRefurbished'
                : 'merchant.conditionUsed',
            )}
            {listing.battery_health != null && ` · ${listing.battery_health}%`}
            {listing.has_damage && ` · ${t('table.hasDamage')}`}
          </span>
        )}
        {!listing.is_searchable ? (
          <span className="mt-0.5 block text-xs text-amber-700 dark:text-amber-400">
            {t('merchant.notSearchable')}
          </span>
        ) : (
          listing.matched_product_name &&
          listing.matched_product_name !== listing.name && (
            <span className="mt-0.5 block text-xs text-gray-500 dark:text-gray-400">
              {t('merchant.matchedTo', { name: listing.matched_product_name })}
            </span>
          )
        )}
        {age && (
          <span
            className={`mt-0.5 block text-xs ${stale ? 'text-amber-700' : 'text-gray-400'}`}
          >
            {stale
              ? t('merchant.notUpdatedSince', { age })
              : t('table.updated', { age })}
          </span>
        )}
        {error && <span className="mt-0.5 block text-xs text-red-700 dark:text-red-300">{error}</span>}
        </div>
        </div>
      </td>
      <td className="px-4 py-3">
        <div className="flex items-center gap-2">
          <input
            type="number"
            min="0.001"
            step="0.001"
            value={price}
            onChange={(e) => setPrice(e.target.value)}
            aria-label={`Price for ${listing.name}`}
            className="w-28 rounded-lg border border-gray-300 dark:border-gray-700 px-2 py-1 text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
          />
          <button
            onClick={save}
            disabled={busy || !dirty}
            className="rounded-md bg-brand-600 px-2.5 py-1 text-xs font-medium text-white hover:bg-brand-700 disabled:opacity-40"
          >
            {t('merchant.save')}
          </button>
        </div>
      </td>
      <td className="px-4 py-3 text-sm text-gray-500 dark:text-gray-400">
        {formatPrice(listing.delivery_cost)}
      </td>
      <td className="px-4 py-3">
        <button
          onClick={toggleStock}
          disabled={busy}
          className={`rounded-md px-2.5 py-1 text-xs font-medium disabled:opacity-40 ${
            listing.availability
              ? 'bg-green-100 text-green-800 hover:bg-green-200'
              : 'bg-gray-200 text-gray-600 hover:bg-gray-300'
          }`}
          title={t('common.clickToChange')}
        >
          {listing.availability ? t('table.inStock') : t('table.outOfStock')}
        </button>
      </td>
      <td className="px-4 py-3 text-right">
        <button
          onClick={remove}
          disabled={busy}
          className="text-xs text-red-600 dark:text-red-400 hover:text-red-700 disabled:opacity-40"
        >
          {t('merchant.remove')}
        </button>
      </td>
    </tr>
  );
}
