import { useState } from 'react';

import { updateMyStore } from '../../api/merchant';
import { useLocale } from '../../hooks/useLocale';
import { extractApiError } from '../../utils/errors';

export default function ContactPanel({ store, onSaved }) {
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
