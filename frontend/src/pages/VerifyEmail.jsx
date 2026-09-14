import { useEffect, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { verifyEmail } from '../api/auth';
import Spinner from '../components/ui/Spinner';
import { useDocumentMeta } from '../hooks/useDocumentMeta';
import { useLocale } from '../hooks/useLocale';

/**
 * One attempt per token, shared across effect invocations.
 *
 * Redeeming a token is NOT idempotent -- it is single use by design -- and
 * React StrictMode runs effects twice in development. Without this the first
 * call succeeded, the second hit an already-consumed token, and the failure
 * overwrote the success: a correctly verified account showing "this link did
 * not work".
 *
 * Caching the promise rather than guarding with a boolean means both
 * invocations observe the SAME result instead of one of them racing to a
 * different conclusion.
 */
const attempts = new Map();

function verifyOnce(token) {
  if (!attempts.has(token)) {
    attempts.set(token, verifyEmail(token));
  }
  return attempts.get(token);
}

/**
 * Landing page for the link in the verification email.
 *
 * Deliberately does not require a session: the link is opened from an email
 * client, frequently in a different browser -- or on a different device --
 * from the one that signed up. Demanding a login here would strand exactly the
 * users the email is meant to onboard.
 */
export default function VerifyEmail() {
  const { t } = useLocale();
  // The URL carries a one-time token. It should never be linked from
  // anywhere public, but if it ever is, the page must not become a result.
  useDocumentMeta({ title: t('meta.verifyEmail.title'), noindex: true });
  const [searchParams] = useSearchParams();
  const token = searchParams.get('token');

  // Derived at first render rather than set inside the effect: a missing
  // token is knowable immediately, and setState in an effect body triggers
  // a cascading re-render (react-hooks/set-state-in-effect).
  const [status, setStatus] = useState(token ? 'checking' : 'missing');

  useEffect(() => {
    if (!token) return undefined;

    let cancelled = false;

    verifyOnce(token)
      .then(() => {
        if (!cancelled) setStatus('done');
      })
      .catch(() => {
        // The API gives one message for expired, already-used and unknown,
        // on purpose. The UI has nothing more specific to offer either.
        if (!cancelled) setStatus('failed');
      });

    return () => {
      cancelled = true;
    };
  }, [token]);

  return (
    <div className="mx-auto max-w-md px-4 py-16 text-center">
      {status === 'checking' && <Spinner />}

      {status === 'done' && (
        <>
          <h1 className="text-xl font-semibold text-gray-900 dark:text-white">
            {t('verify.confirmed')}
          </h1>
          <p className="mt-2 text-sm text-gray-600 dark:text-gray-400">
            {t('verify.confirmedBlurb')}
          </p>
          <Link
            to="/"
            className="mt-6 inline-block rounded-lg bg-brand-600 px-4 py-2 text-sm font-medium text-white hover:bg-brand-700"
          >
            {t('common.startSearching')}
          </Link>
        </>
      )}

      {(status === 'failed' || status === 'missing') && (
        <>
          <h1 className="text-xl font-semibold text-gray-900 dark:text-white">
            {t('verify.linkFailed')}
          </h1>
          <p className="mt-2 text-sm text-gray-600 dark:text-gray-400">
            {t('verify.linkFailedBlurb')}
          </p>
          <p className="mt-4 text-sm text-gray-500 dark:text-gray-400">
            {t('verify.signInAndResend')}
          </p>
          <Link
            to="/login"
            className="mt-6 inline-flex min-h-11 items-center rounded-lg border border-gray-300 px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 dark:border-gray-700 dark:text-gray-300 dark:hover:bg-gray-800"
          >
            Go to login
          </Link>
        </>
      )}
    </div>
  );
}
