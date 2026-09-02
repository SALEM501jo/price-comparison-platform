import { useState } from 'react';
import { sendSupportMessage } from '../api/support';
import { useAuth } from '../hooks/useAuth';
import { useLocale } from '../hooks/useLocale';

const field =
  'mt-1 w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-gray-900 ' +
  'focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-500 ' +
  'dark:border-gray-700 dark:bg-gray-900 dark:text-white';

/**
 * The contact form.
 *
 * Open to anyone, signed in or not, because the people who most need it are
 * the ones who cannot get in. The email field is asked for even when signed
 * in: the address someone can actually receive mail on may not be the one on
 * the account they are locked out of.
 */
export default function Contact() {
  const { t } = useLocale();
  const { user } = useAuth();
  const [form, setForm] = useState({
    email: user?.email ?? '',
    subject: '',
    body: '',
  });
  const [sent, setSent] = useState(false);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  const set = (changes) => setForm((current) => ({ ...current, ...changes }));

  const submit = async (event) => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await sendSupportMessage(form);
      setSent(true);
    } catch {
      setError(t('support.error'));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="mx-auto max-w-lg px-4 py-12">
      <h1 className="text-2xl font-bold text-gray-900 dark:text-white">
        {t('support.title')}
      </h1>
      <p className="mt-2 text-sm text-gray-600 dark:text-gray-400">
        {t('support.blurb')}
      </p>

      {sent ? (
        <p className="mt-6 rounded-lg bg-brand-50 px-4 py-3 text-sm text-brand-900 dark:bg-brand-900/30 dark:text-brand-200">
          {t('support.sent')}
        </p>
      ) : (
        <form onSubmit={submit} className="mt-6 space-y-4">
          <div>
            <label
              htmlFor="email"
              className="block text-sm font-medium text-gray-700 dark:text-gray-300"
            >
              {t('support.yourEmail')}
            </label>
            <input
              id="email"
              type="email"
              required
              dir="ltr"
              value={form.email}
              onChange={(e) => set({ email: e.target.value })}
              className={field}
            />
            <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
              {t('support.emailHint')}
            </p>
          </div>

          <div>
            <label
              htmlFor="subject"
              className="block text-sm font-medium text-gray-700 dark:text-gray-300"
            >
              {t('support.subject')}{' '}
              <span className="text-gray-400">{t('merchant.optional')}</span>
            </label>
            <input
              id="subject"
              maxLength={150}
              value={form.subject}
              onChange={(e) => set({ subject: e.target.value })}
              className={field}
            />
          </div>

          <div>
            <label
              htmlFor="body"
              className="block text-sm font-medium text-gray-700 dark:text-gray-300"
            >
              {t('support.message')}
            </label>
            <textarea
              id="body"
              required
              rows={6}
              minLength={10}
              maxLength={4000}
              value={form.body}
              onChange={(e) => set({ body: e.target.value })}
              className={field}
            />
          </div>

          {error && (
            <p className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700 dark:bg-red-950/40 dark:text-red-300">
              {error}
            </p>
          )}

          <button
            type="submit"
            disabled={busy}
            className="w-full min-h-11 rounded-lg bg-brand-600 px-4 py-2 font-semibold text-white hover:bg-brand-700 disabled:opacity-60"
          >
            {busy ? t('support.sending') : t('support.send')}
          </button>
        </form>
      )}
    </div>
  );
}
