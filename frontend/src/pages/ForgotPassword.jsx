import { useState } from 'react';
import { Link } from 'react-router-dom';
import { forgotPassword } from '../api/auth';
import { useDocumentMeta } from '../hooks/useDocumentMeta';
import { useLocale } from '../hooks/useLocale';

const field =
  'mt-1 w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-gray-900 ' +
  'focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-500 ' +
  'dark:border-gray-700 dark:bg-gray-900 dark:text-white';

/**
 * Ask for a reset link.
 *
 * The confirmation is deliberately the SAME whether or not the address has an
 * account. Saying "no account with that email" here would turn the page into a
 * membership check anyone could run, and the server already refuses to make
 * that distinction -- showing it in the UI would give away what the API
 * carefully does not.
 */
export default function ForgotPassword() {
  const { t } = useLocale();
  useDocumentMeta({ title: t('auth.forgotTitle'), noindex: true });
  const [email, setEmail] = useState('');
  const [sent, setSent] = useState(false);
  const [busy, setBusy] = useState(false);

  const submit = async (event) => {
    event.preventDefault();
    setBusy(true);
    try {
      await forgotPassword(email);
    } catch {
      // Even a failure shows the same confirmation: an error here would leak
      // timing and status differences the endpoint is built to hide.
    } finally {
      setBusy(false);
      setSent(true);
    }
  };

  return (
    <div className="mx-auto max-w-md px-4 py-12">
      <h1 className="text-2xl font-bold text-gray-900 dark:text-white">
        {t('auth.forgotTitle')}
      </h1>

      {sent ? (
        <>
          <p className="mt-4 rounded-lg bg-brand-50 px-4 py-3 text-sm text-brand-900 dark:bg-brand-900/30 dark:text-brand-200">
            {t('auth.resetSent')}
          </p>
          <Link
            to="/login"
            className="mt-4 inline-flex min-h-11 items-center text-sm text-brand-600 hover:underline dark:text-brand-400"
          >
            {t('auth.backToLogin')}
          </Link>
        </>
      ) : (
        <form onSubmit={submit} className="mt-6 space-y-4">
          <p className="text-sm text-gray-600 dark:text-gray-400">
            {t('auth.forgotBlurb')}
          </p>
          <div>
            <label htmlFor="email" className="block text-sm font-medium text-gray-700 dark:text-gray-300">
              {t('auth.email')}
            </label>
            <input
              id="email"
              type="email"
              required
              dir="ltr"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className={field}
            />
          </div>
          <button
            type="submit"
            disabled={busy}
            className="w-full min-h-11 rounded-lg bg-brand-600 px-4 py-2 font-semibold text-white hover:bg-brand-700 disabled:opacity-60"
          >
            {busy ? t('support.sending') : t('auth.sendResetLink')}
          </button>
          <Link
            to="/login"
            className="inline-flex min-h-11 w-full items-center justify-center text-sm text-brand-600 hover:underline dark:text-brand-400"
          >
            {t('auth.backToLogin')}
          </Link>
        </form>
      )}
    </div>
  );
}
