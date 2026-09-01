import { useState } from 'react';

import { registerStore } from '../../api/merchant';
import { useLocale } from '../../hooks/useLocale';
import { extractApiError } from '../../utils/errors';

/**
 * A shop manages its own store and prices.
 *
 * The page has two states rather than two routes: an account either has a
 * store or it does not, and asking the server is how we find out. A 404 from
 * GET /merchant/store is the normal "not a merchant yet" answer, not an error
 * to show the user.
 */

export default function StoreRegistration({ onCreated }) {
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
          className="w-full min-h-11 rounded-lg bg-brand-600 px-4 py-2 font-medium text-white hover:bg-brand-700 disabled:opacity-60"
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
