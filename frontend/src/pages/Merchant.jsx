import { useEffect, useState } from 'react';
import { useLocale } from '../hooks/useLocale';
import {
  createListing,
  deleteListing,
  getMyListings,
  getMyStore,
  registerStore,
  updateListing,
  updateMyStore,
} from '../api/merchant';
import ContactStats from '../components/merchant/ContactStats';
import Spinner from '../components/ui/Spinner';
import { extractApiError } from '../utils/errors';
import { formatAge, formatPrice, isPriceStale } from '../utils/format';

/**
 * A shop manages its own store and prices.
 *
 * The page has two states rather than two routes: an account either has a
 * store or it does not, and asking the server is how we find out. A 404 from
 * GET /merchant/store is the normal "not a merchant yet" answer, not an error
 * to show the user.
 */

function StoreRegistration({ onCreated }) {
  const { t } = useLocale();
  const [form, setForm] = useState({
    name: '',
    phone: '',
    whatsapp: '',
    facebook_url: '',
    instagram_url: '',
  });
  const [error, setError] = useState(null);
  const [saving, setSaving] = useState(false);

  const submit = async (event) => {
    event.preventDefault();
    setSaving(true);
    setError(null);
    try {
      // Empty strings would fail the phone validator, which has no way to
      // tell "left blank" from "typed wrong". Null means "not provided".
      onCreated(
        await registerStore({
          name: form.name,
          phone: form.phone || null,
          whatsapp: form.whatsapp || null,
          facebook_url: form.facebook_url || null,
          instagram_url: form.instagram_url || null,
        }),
      );
    } catch (err) {
      setError(extractApiError(err, t('merchant.saveError')));
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="mx-auto max-w-xl px-4 py-10">
      <h1 className="text-2xl font-semibold text-gray-900 dark:text-white">{t('merchant.listYourShop')}</h1>
      <p className="mt-2 text-sm text-gray-600 dark:text-gray-400">
        {t('merchant.listYourShopBlurb')}
      </p>

      <form onSubmit={submit} className="mt-8 space-y-4">
        <div>
          <label htmlFor="name" className="block text-sm font-medium text-gray-700 dark:text-gray-300">
            {t('merchant.shopName')}
          </label>
          <input
            id="name"
            required
            minLength={2}
            maxLength={100}
            value={form.name}
            onChange={(e) => setForm({ ...form, name: e.target.value })}
            placeholder="Jado Mobile"
            className="mt-1 w-full rounded-lg border border-gray-300 dark:border-gray-700 px-3 py-2 focus:outline-none focus:ring-2 focus:ring-brand-500"
          />
          <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
            {t('merchant.shopNameHint')}
          </p>
        </div>

        <div className="grid gap-4 sm:grid-cols-2">
          <div>
            <label htmlFor="phone" className="block text-sm font-medium text-gray-700 dark:text-gray-300">
              {t('merchant.phone')}
            </label>
            <input
              id="phone"
              value={form.phone}
              onChange={(e) => setForm({ ...form, phone: e.target.value })}
              placeholder="0791234567"
              className="mt-1 w-full rounded-lg border border-gray-300 dark:border-gray-700 px-3 py-2 focus:outline-none focus:ring-2 focus:ring-brand-500"
            />
          </div>
          <div>
            <label htmlFor="whatsapp" className="block text-sm font-medium text-gray-700 dark:text-gray-300">
              {t('merchant.whatsapp')}
            </label>
            <input
              id="whatsapp"
              value={form.whatsapp}
              onChange={(e) => setForm({ ...form, whatsapp: e.target.value })}
              placeholder="0791234567"
              className="mt-1 w-full rounded-lg border border-gray-300 dark:border-gray-700 px-3 py-2 focus:outline-none focus:ring-2 focus:ring-brand-500"
            />
          </div>
        </div>

        <div>
          <label htmlFor="facebook" className="block text-sm font-medium text-gray-700 dark:text-gray-300">
            {t('merchant.facebook')}{' '}
            <span className="text-gray-400 dark:text-gray-500">{t('merchant.optional')}</span>
          </label>
          <input
            id="facebook"
            value={form.facebook_url}
            onChange={(e) => setForm({ ...form, facebook_url: e.target.value })}
            placeholder="https://facebook.com/yourshop"
            className="mt-1 w-full rounded-lg border border-gray-300 dark:border-gray-700 px-3 py-2 focus:outline-none focus:ring-2 focus:ring-brand-500"
          />
        </div>

        {/* Optional, like Facebook. Plenty of these shops have an Instagram
            and no Facebook page at all, so it is offered alongside rather
            than instead. */}
        <div>
          <label htmlFor="instagram" className="block text-sm font-medium text-gray-700 dark:text-gray-300">
            {t('merchant.instagram')}{' '}
            <span className="text-gray-400 dark:text-gray-500">{t('merchant.optional')}</span>
          </label>
          <input
            id="instagram"
            value={form.instagram_url}
            onChange={(e) => setForm({ ...form, instagram_url: e.target.value })}
            placeholder="https://instagram.com/yourshop"
            className="mt-1 w-full rounded-lg border border-gray-300 dark:border-gray-700 px-3 py-2 focus:outline-none focus:ring-2 focus:ring-brand-500"
          />
        </div>

        {error && (
          <p className="rounded-lg bg-red-50 dark:bg-red-950/40 px-3 py-2 text-sm text-red-700 dark:text-red-300">{error}</p>
        )}

        <button
          type="submit"
          disabled={saving}
          className="w-full rounded-lg bg-brand-600 px-4 py-2 font-medium text-white hover:bg-brand-700 disabled:opacity-60"
        >
          {saving ? t('merchant.registering') : t('merchant.registerShop')}
        </button>

        <p className="text-xs text-gray-500 dark:text-gray-400">
          {t('merchant.reviewNote')}
        </p>
      </form>
    </div>
  );
}

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
function AddListing({ onAdded }) {
  const { t } = useLocale();
  const [form, setForm] = useState(BLANK_LISTING);
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
      setForm(BLANK_LISTING);
      onAdded(created);
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
                placeholder="Hairline crack, bottom right of the screen"
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
            placeholder="Original box and charger included"
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

function ListingRow({ listing, onChanged, onRemoved }) {
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
          title="Click to change"
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

function ContactPanel({ store, onSaved }) {
  const { t } = useLocale();
  const [form, setForm] = useState({
    phone: store.phone ?? '',
    whatsapp: store.whatsapp ?? '',
    facebook_url: store.facebook_url ?? '',
    instagram_url: store.instagram_url ?? '',
  });
  const [error, setError] = useState(null);
  const [saved, setSaved] = useState(false);
  const [busy, setBusy] = useState(false);

  const submit = async (event) => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    setSaved(false);
    try {
      onSaved(
        await updateMyStore({
          phone: form.phone || null,
          whatsapp: form.whatsapp || null,
          facebook_url: form.facebook_url || null,
          instagram_url: form.instagram_url || null,
        }),
      );
      setSaved(true);
    } catch (err) {
      setError(extractApiError(err, t('merchant.saveError')));
    } finally {
      setBusy(false);
    }
  };

  return (
    <form onSubmit={submit} className="rounded-lg border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900 p-4">
      <h2 className="text-sm font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400">
        {t('merchant.contactHeading')}
      </h2>
      <div className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <input
          value={form.phone}
          onChange={(e) => setForm({ ...form, phone: e.target.value })}
          placeholder={t('merchant.phone')}
          aria-label={t('merchant.phone')}
          className="rounded-lg border border-gray-300 dark:border-gray-700 px-3 py-2 focus:outline-none focus:ring-2 focus:ring-brand-500"
        />
        <input
          value={form.whatsapp}
          onChange={(e) => setForm({ ...form, whatsapp: e.target.value })}
          placeholder={t('merchant.whatsapp')}
          aria-label={t('merchant.whatsapp')}
          className="rounded-lg border border-gray-300 dark:border-gray-700 px-3 py-2 focus:outline-none focus:ring-2 focus:ring-brand-500"
        />
        <input
          value={form.facebook_url}
          onChange={(e) => setForm({ ...form, facebook_url: e.target.value })}
          placeholder={t('merchant.facebook')}
          aria-label={t('merchant.facebook')}
          className="rounded-lg border border-gray-300 dark:border-gray-700 px-3 py-2 focus:outline-none focus:ring-2 focus:ring-brand-500"
        />
        <input
          value={form.instagram_url}
          onChange={(e) => setForm({ ...form, instagram_url: e.target.value })}
          placeholder={t('merchant.instagram')}
          aria-label={t('merchant.instagram')}
          className="rounded-lg border border-gray-300 dark:border-gray-700 px-3 py-2 focus:outline-none focus:ring-2 focus:ring-brand-500"
        />
      </div>
      <div className="mt-3 flex items-center gap-3">
        <button
          type="submit"
          disabled={busy}
          className="rounded-lg border border-gray-300 dark:border-gray-700 px-3 py-1.5 text-sm font-medium text-gray-700 dark:text-gray-300 hover:bg-gray-50 disabled:opacity-60"
        >
          {busy ? t('merchant.saving') : t('merchant.saveContact')}
        </button>
        {saved && <span className="text-sm text-green-700 dark:text-green-400">{t('merchant.saved')}</span>}
        {error && <span className="text-sm text-red-700 dark:text-red-300">{error}</span>}
      </div>
    </form>
  );
}

export default function Merchant() {
  const { t } = useLocale();
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
