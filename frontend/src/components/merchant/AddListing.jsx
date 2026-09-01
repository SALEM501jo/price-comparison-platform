import { useState } from 'react';

import { createListing, uploadListingPhoto } from '../../api/merchant';
import { useLocale } from '../../hooks/useLocale';
import { extractApiError, extractPhotoError } from '../../utils/errors';
import PhotoPicker from './PhotoPicker';

const BLANK_LISTING = {
  name: '',
  price: '',
  delivery_cost: '',
  condition: 'new',
  battery_health: '',
  has_damage: 'no',
  damage_notes: '',
  warranty_months: '',
  listing_notes: '',
};

/**
 * Add a product.
 *
 * The used fields appear only when they apply, and are required once they do.
 * A second-hand listing without battery health is not an offer a shopper can
 * act on, and the server rejects it either way -- asking here means the shop
 * owner finds out while they are still looking at the form.
 */
export default function AddListing({ onAdded }) {
  const { t } = useLocale();
  const [form, setForm] = useState(BLANK_LISTING);
  const [photo, setPhoto] = useState(null);
  const [error, setError] = useState(null);
  const [saving, setSaving] = useState(false);

  const isSecondHand = form.condition !== 'new';
  const set = (changes) => setForm((current) => ({ ...current, ...changes }));

  const submit = async (event) => {
    event.preventDefault();
    setSaving(true);
    setError(null);
    try {
      const payload = {
        name: form.name,
        price: Number(form.price),
        delivery_cost: form.delivery_cost ? Number(form.delivery_cost) : 0,
        condition: form.condition,
        listing_notes: form.listing_notes || null,
        warranty_months: form.warranty_months
          ? Number(form.warranty_months)
          : null,
      };

      if (isSecondHand) {
        payload.battery_health = Number(form.battery_health);
        payload.has_damage = form.has_damage === 'yes';
        payload.damage_notes = payload.has_damage ? form.damage_notes : null;
      }

      const created = await createListing(payload);

      // TWO REQUESTS, IN THIS ORDER. A photo attaches to a listing id, so
      // the listing has to exist first -- there is nothing to hang the image
      // on until the server has assigned one.
      //
      // A failed photo does NOT fail the listing. The price is the thing a
      // shopper needs and it is already saved; throwing here would leave a
      // live listing behind an error message that says the save did not
      // work. The merchant is told the photo specifically did not go up, and
      // can add it from the list.
      let photoError = null;
      if (photo) {
        try {
          await uploadListingPhoto(created.id, photo);
          created.has_photo = true;
        } catch (err) {
          photoError = extractPhotoError(err, t);
        }
      }

      setForm(BLANK_LISTING);
      setPhoto(null);
      onAdded(created);
      if (photoError) setError(photoError);
    } catch (err) {
      setError(extractApiError(err, t('merchant.saveError')));
    } finally {
      setSaving(false);
    }
  };

  return (
    <form onSubmit={submit} className="rounded-lg border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900 p-4">
      <h2 className="text-sm font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400">
        {t('merchant.addProduct')}
      </h2>
      <div className="mt-3 grid gap-3 sm:grid-cols-[1fr_9rem_9rem_auto]">
        <input
          required
          minLength={3}
          value={form.name}
          onChange={(e) => set({ name: e.target.value })}
          placeholder="iPhone 15 128GB Black"
          aria-label={t('merchant.productName')}
          className="rounded-lg border border-gray-300 dark:border-gray-700 px-3 py-2 focus:outline-none focus:ring-2 focus:ring-brand-500"
        />
        {/* step="any" so the arrows move in whole dinars instead of
            thousandths, while still accepting a typed 1045.500 -- JOD has
            three decimals and a fixed step would reject real prices. */}
        <input
          required
          type="number"
          min="0.001"
          step="any"
          value={form.price}
          onChange={(e) => set({ price: e.target.value })}
          placeholder={t('merchant.priceJod')}
          aria-label={t('merchant.priceJod')}
          className="rounded-lg border border-gray-300 dark:border-gray-700 px-3 py-2 focus:outline-none focus:ring-2 focus:ring-brand-500"
        />
        {/* Delivery is quoted in half-dinars here -- 0, 1, 1.5, 2.5 -- so
            the arrows step by 0.5 rather than a thousandth of a dinar. */}
        <input
          type="number"
          min="0"
          step="0.5"
          value={form.delivery_cost}
          onChange={(e) => set({ delivery_cost: e.target.value })}
          placeholder={t('table.delivery')}
          aria-label={t('table.delivery')}
          className="rounded-lg border border-gray-300 dark:border-gray-700 px-3 py-2 focus:outline-none focus:ring-2 focus:ring-brand-500"
        />
        <button
          type="submit"
          disabled={saving}
          className="rounded-lg bg-brand-600 px-4 py-2 font-medium text-white hover:bg-brand-700 disabled:opacity-60"
        >
          {saving ? t('merchant.saving') : t('merchant.add')}
        </button>
      </div>

      <div className="mt-4 border-t border-gray-100 pt-4 dark:border-gray-800">
        <PhotoPicker file={photo} onPick={setPhoto} disabled={saving} />
      </div>

      <div className="mt-3 flex flex-wrap items-center gap-2">
        <span className="text-sm text-gray-600 dark:text-gray-400">{t('merchant.condition')}</span>
        {[
          ['new', t('merchant.conditionNew')],
          ['used', t('merchant.conditionUsed')],
          ['refurbished', t('merchant.conditionRefurbished')],
        ].map(([value, label]) => (
          <label
            key={value}
            className={`cursor-pointer rounded-lg border px-3 py-1.5 text-sm ${
              form.condition === value
                ? 'border-brand-600 bg-brand-50 font-medium text-brand-700 dark:border-brand-500 dark:bg-brand-900/40 dark:text-brand-300'
                : 'border-gray-300 text-gray-700 hover:bg-gray-50 dark:border-gray-700 dark:text-gray-300 dark:hover:bg-gray-800'
            }`}
          >
            <input
              type="radio"
              name="condition"
              value={value}
              checked={form.condition === value}
              onChange={(e) => set({ condition: e.target.value })}
              className="sr-only"
            />
            {label}
          </label>
        ))}
      </div>

      {isSecondHand && (
        <div className="mt-3 rounded-lg border border-amber-200 dark:border-amber-900/50 bg-amber-50/60 dark:bg-amber-950/30 p-3">
          <p className="mb-3 text-xs text-amber-900 dark:text-amber-200">
            {t('merchant.usedNote')}
          </p>
          <div className="grid gap-3 sm:grid-cols-[10rem_1fr]">
            <label className="text-sm">
              <span className="mb-1 block text-gray-700 dark:text-gray-300">{t('merchant.batteryHealth')}</span>
              <input
                required
                type="number"
                min="1"
                max="100"
                value={form.battery_health}
                onChange={(e) => set({ battery_health: e.target.value })}
                placeholder="87"
                className="w-full rounded-lg border border-gray-300 dark:border-gray-700 px-3 py-2 focus:outline-none focus:ring-2 focus:ring-brand-500"
              />
            </label>
            <label className="text-sm">
              <span className="mb-1 block text-gray-700 dark:text-gray-300">{t('merchant.anyDamage')}</span>
              <select
                value={form.has_damage}
                onChange={(e) => set({ has_damage: e.target.value })}
                className="w-full rounded-lg border border-gray-300 dark:border-gray-700 px-3 py-2 focus:outline-none focus:ring-2 focus:ring-brand-500"
              >
                <option value="no">{t('merchant.noDamage')}</option>
                <option value="yes">{t('merchant.yesDamage')}</option>
              </select>
            </label>
          </div>

          {form.has_damage === 'yes' && (
            <label className="mt-3 block text-sm">
              <span className="mb-1 block text-gray-700 dark:text-gray-300">{t('merchant.describeDamage')}</span>
              <input
                required
                maxLength={500}
                value={form.damage_notes}
                onChange={(e) => set({ damage_notes: e.target.value })}
                placeholder={t('merchant.damageExample')}
                className="w-full rounded-lg border border-gray-300 dark:border-gray-700 px-3 py-2 focus:outline-none focus:ring-2 focus:ring-brand-500"
              />
            </label>
          )}
        </div>
      )}

      {/* Warranty is NOT a used-phone field. A sealed phone carries one too,
          and in this market the length of it is often the reason to pick one
          shop over another -- so it sits with the price, not behind a
          condition toggle. */}
      <div className="mt-3 grid gap-3 sm:grid-cols-[11rem_1fr]">
        <label className="text-sm">
          <span className="mb-1 block text-gray-700 dark:text-gray-300">{t('merchant.warrantyMonths')}</span>
          <input
            type="number"
            min="0"
            max="60"
            step="1"
            value={form.warranty_months}
            onChange={(e) => set({ warranty_months: e.target.value })}
            placeholder="12"
            className="w-full rounded-lg border border-gray-300 dark:border-gray-700 px-3 py-2 focus:outline-none focus:ring-2 focus:ring-brand-500"
          />
        </label>
        <label className="text-sm">
          <span className="mb-1 block text-gray-700 dark:text-gray-300">
            {t('merchant.anythingElse')}{' '}
            <span className="text-gray-400 dark:text-gray-500">{t('merchant.optional')}</span>
          </span>
          <input
            maxLength={1000}
            value={form.listing_notes}
            onChange={(e) => set({ listing_notes: e.target.value })}
            placeholder={t('merchant.notesExample')}
            className="w-full rounded-lg border border-gray-300 dark:border-gray-700 px-3 py-2 focus:outline-none focus:ring-2 focus:ring-brand-500"
          />
        </label>
      </div>

      <p className="mt-2 text-xs text-gray-500 dark:text-gray-400">
        {t('merchant.nameHint')}
      </p>
      {error && <p className="mt-2 text-sm text-red-700 dark:text-red-300">{error}</p>}
    </form>
  );
}
