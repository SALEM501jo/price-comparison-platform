import { useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { resetPassword } from '../api/auth';
import { useLocale } from '../hooks/useLocale';
import { passwordProblems } from '../utils/errors';

const field =
  'mt-1 w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-gray-900 ' +
  'focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-500/30 ' +
  'dark:border-gray-700 dark:bg-gray-900 dark:text-white';

/**
 * Spend a reset link and choose a new password.
 *
 * The token travels in the URL because it arrives from an email client, which
 * can only hand over a link. It is single use and short lived, so a copy left
 * in browser history is already spent by the time anyone finds it.
 *
 * Success does NOT sign the user in -- the API deliberately returns no token.
 * Someone who has just proved control of a mailbox should still type the
 * password they chose, and a link opened on a shared machine must not leave a
 * live session behind it.
 */
export default function ResetPassword() {
  const { t } = useLocale();
  const [params] = useSearchParams();
  const token = params.get('token') || '';

  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [error, setError] = useState(null);
  const [done, setDone] = useState(false);
  const [busy, setBusy] = useState(false);

  const problems = password ? passwordProblems(password) : [];

  const submit = async (event) => {
    event.preventDefault();
    setError(null);

    if (password !== confirm) {
      setError(t('auth.passwordsDoNotMatch'));
      return;
    }

    setBusy(true);
    try {
      await resetPassword(token, password);
      setDone(true);
    } catch (err) {
      // 401 is the expired / spent / unknown case, which the API deliberately
      // does not distinguish between. Anything else is a validation failure.
      setError(
        err?.response?.status === 401 ? t('auth.resetInvalid') : t('common.error'),
      );
    } finally {
      setBusy(false);
    }
  };

  if (!token) {
    return (
      <div className="mx-auto max-w-md px-4 py-12">
        <p className="rounded-lg bg-red-50 px-4 py-3 text-sm text-red-700 dark:bg-red-950/40 dark:text-red-300">
          {t('auth.resetInvalid')}
        </p>
        <Link
          to="/forgot-password"
          className="mt-4 inline-block text-sm text-brand-600 hover:underline dark:text-brand-400"
        >
          {t('auth.forgotTitle')}
        </Link>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-md px-4 py-12">
      <h1 className="text-2xl font-bold text-gray-900 dark:text-white">
        {t('auth.resetTitle')}
      </h1>

      {done ? (
        <>
          <p className="mt-4 rounded-lg bg-brand-50 px-4 py-3 text-sm text-brand-900 dark:bg-brand-900/30 dark:text-brand-200">
            {t('auth.resetDone')}
          </p>
          <Link
            to="/login"
            className="mt-4 inline-block rounded-lg bg-brand-600 px-4 py-2 font-semibold text-white hover:bg-brand-700"
          >
            {t('auth.login')}
          </Link>
        </>
      ) : (
        <form onSubmit={submit} className="mt-6 space-y-4">
          <div>
            <label
              htmlFor="password"
              className="block text-sm font-medium text-gray-700 dark:text-gray-300"
            >
              {t('auth.newPassword')}
            </label>
            <input
              id="password"
              type="password"
              required
              dir="ltr"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className={field}
            />
            {problems.length > 0 && (
              <ul className="mt-1 space-y-0.5 text-xs text-gray-500 dark:text-gray-400">
                {problems.map((problem) => (
                  <li key={problem}>&bull; {problem}</li>
                ))}
              </ul>
            )}
          </div>

          <div>
            <label
              htmlFor="confirm"
              className="block text-sm font-medium text-gray-700 dark:text-gray-300"
            >
              {t('auth.confirmPassword')}
            </label>
            <input
              id="confirm"
              type="password"
              required
              dir="ltr"
              value={confirm}
              onChange={(e) => setConfirm(e.target.value)}
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
            disabled={busy || problems.length > 0}
            className="w-full rounded-lg bg-brand-600 px-4 py-2 font-semibold text-white hover:bg-brand-700 disabled:opacity-60"
          >
            {busy ? t('support.sending') : t('auth.setPassword')}
          </button>
        </form>
      )}
    </div>
  );
}
