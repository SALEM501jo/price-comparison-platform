import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '../hooks/useAuth';
import { useDocumentMeta } from '../hooks/useDocumentMeta';
import { useLocale } from '../hooks/useLocale';
import { extractApiError } from '../utils/errors';

/**
 * What this account is, and the one place in the app it can be deleted.
 *
 * THE MEASURE IS THE POLICY PAGES' AND NOT A LIST PAGE'S. Most of what is
 * below the details card is prose somebody has to actually read before
 * pressing a button they cannot unpress, and max-w-4xl puts roughly 130
 * characters on a line here -- about twice what an eye tracks back reliably,
 * which is why long warnings go unread.
 *
 * THE CONSEQUENCES ARE REVEALED BEFORE THE FIELD, NOT AFTER IT. Pressing
 * "delete my account" opens the itemised list and the confirmation together,
 * so the list cannot be skipped on the way to the button. It is itemised
 * rather than summarised because "this cannot be undone" is the part everyone
 * already assumes; what nobody guesses is that a support message keeps its
 * text, that a shop is retired rather than deleted, and that its photographs
 * go while its prices stay.
 */

const ROLE_KEY = {
  buyer: 'account.role.buyer',
  merchant: 'account.role.merchant',
  admin: 'account.role.admin',
};

const GONE = [
  'account.delete.gone.account',
  'account.delete.gone.saved',
  'account.delete.gone.sessions',
  'account.delete.gone.social',
];

const MERCHANT = [
  'account.delete.merchant.retired',
  'account.delete.merchant.photos',
  'account.delete.merchant.listings',
];

/**
 * Does the typed confirmation name this account?
 *
 * The same normalisation the server applies -- surrounding space ignored,
 * compared case-insensitively -- and it has to be. A phone keyboard
 * capitalises the first letter of a field it reads as a sentence, so an exact
 * compare would leave the confirm button dead for a user typing an address
 * the server would have accepted, with nothing on screen to explain it.
 */
const sameAddress = (typed, actual) => {
  const candidate = typed.trim().toLowerCase();
  return candidate.length > 0 && candidate === (actual ?? '').trim().toLowerCase();
};

/**
 * The day the account was opened.
 *
 * Latin digits in both scripts, which is what `-u-nu-latn` buys: ar-JO
 * otherwise renders Arabic-Indic numerals, and this site already forces Latin
 * ones everywhere else (index.css sets font-feature-settings 'ss01' for RTL)
 * so that a date and a price do not use two different number systems on the
 * same screen.
 */
const formatOpened = (value, locale) => {
  if (!value) return null;
  const at = new Date(value);
  if (Number.isNaN(at.getTime())) return null;
  return at.toLocaleDateString(locale === 'ar' ? 'ar-JO-u-nu-latn' : 'en-GB', {
    year: 'numeric',
    month: 'long',
    day: 'numeric',
  });
};

export default function Account() {
  const { t, locale } = useLocale();
  useDocumentMeta({ title: t('account.title'), noindex: true });
  const { user, isMerchant, deleteAccount } = useAuth();
  const navigate = useNavigate();

  const [confirming, setConfirming] = useState(false);
  const [typed, setTyped] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  const email = user?.email ?? '';
  const verified = Boolean(user?.email_verified_at);
  const opened = formatOpened(user?.created_at, locale);
  const matches = sameAddress(typed, email);

  const cancel = () => {
    setConfirming(false);
    setTyped('');
    setError(null);
  };

  const handleDelete = async (event) => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      // Handed in rather than run after the await: this has to leave the
      // protected route in the same commit that forgets the session, or
      // RequireAuth sees a signed-out user still standing on /account and
      // sends somebody who has just deleted their account to a login form.
      // `replace`, because Back must not return to a page for an account that
      // no longer exists. The confirmation travels with the navigation --
      // this page cannot show it, having unmounted with the session.
      await deleteAccount(typed.trim(), () =>
        navigate('/', { replace: true, state: { accountDeleted: true } }),
      );
    } catch (err) {
      // The server answers a mismatch in English because it cannot know what
      // language the reader is in. It is the only 400 this endpoint returns,
      // and the rule is one the page already enforces, so it is said here in
      // the reader's language instead of relayed.
      setError(
        err?.response?.status === 400
          ? t('account.delete.mismatch')
          : extractApiError(err, t('account.delete.error')),
      );
      // Only on failure: a success unmounts this page with the navigation.
      setBusy(false);
    }
  };

  return (
    <div className="mx-auto max-w-2xl px-4 py-8">
      <h1 className="mb-1 text-xl font-semibold text-gray-900 dark:text-white">
        {t('account.title')}
      </h1>
      <p className="mb-6 text-sm text-gray-500 dark:text-gray-400">{t('account.blurb')}</p>

      <dl className="divide-y divide-gray-200 rounded-lg border border-gray-200 bg-white px-4 dark:divide-gray-800 dark:border-gray-800 dark:bg-gray-900">
        <Detail label={t('auth.email')}>
          {/* An account address is never Arabic, and left to the page's own
              direction an RTL run would move the domain in front of the
              local part. */}
          <span dir="ltr">{email}</span>
        </Detail>

        <Detail label={t('account.emailStatus')}>
          <span
            className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${
              verified
                ? 'bg-green-100 text-green-800 dark:bg-green-900/40 dark:text-green-300'
                : 'bg-amber-50 text-amber-900 dark:bg-amber-950/40 dark:text-amber-200'
            }`}
          >
            {verified ? t('account.verified') : t('account.unverified')}
          </span>
        </Detail>

        {/* A div and not a p: a <dl> may only contain dt, dd and div, and a
            stray paragraph inside one is silently reparented out of it. */}
        {!verified && (
          <div className="py-3 text-sm text-gray-600 dark:text-gray-400">
            {t('account.unverifiedHint')}
          </div>
        )}

        <Detail label={t('account.role')}>
          {ROLE_KEY[user?.role] ? t(ROLE_KEY[user.role]) : user?.role}
        </Detail>

        {/* Hidden rather than dashed when the API answers without it: a row
            reading "Opened —" says nothing anyone needed. */}
        {opened && (
          <Detail label={t('account.created')}>
            <span className="tnum">{opened}</span>
          </Detail>
        )}
      </dl>

      {/* Said on the page itself rather than left to be discovered: the two
          things this screen looks like it should do and does not. */}
      <p className="mt-3 text-sm leading-7 text-gray-600 dark:text-gray-400">
        {t('account.limits')}{' '}
        <Link to="/contact" className="font-medium text-brand-600 hover:underline dark:text-brand-400">
          {t('account.limitsLink')}
        </Link>
      </p>

      <section
        aria-labelledby="delete-account"
        className="mt-8 rounded-lg border border-red-200 bg-white p-4 dark:border-red-900/50 dark:bg-gray-900"
      >
        <h2
          id="delete-account"
          className="text-lg font-semibold text-gray-900 dark:text-white"
        >
          {t('account.delete.title')}
        </h2>
        <p className="mt-2 text-sm leading-7 text-gray-700 dark:text-gray-300">
          {t('account.delete.blurb')}
        </p>

        {!confirming ? (
          <button
            type="button"
            onClick={() => setConfirming(true)}
            className="mt-4 inline-flex min-h-11 items-center rounded-lg border border-red-200 px-4 text-sm font-medium text-red-600 transition hover:bg-red-50 focus:outline-none focus-visible:ring-2 focus-visible:ring-red-500 dark:border-red-900/50 dark:text-red-400 dark:hover:bg-red-950/40"
          >
            {t('account.delete.start')}
          </button>
        ) : (
          <>
            {/* No uppercase and no tracking on a heading that is translated:
                Arabic has no case, and letter-spacing pulls apart letters
                that are supposed to join. */}
            <h3 className="mt-6 text-base font-semibold text-gray-900 dark:text-white">
              {t('account.delete.whatTitle')}
            </h3>

            <Group title={t('account.delete.goneTitle')} items={GONE} />
            <Group
              title={t('account.delete.keptTitle')}
              items={['account.delete.kept.support']}
            />
            <Group
              title={t('account.delete.untouchedTitle')}
              items={['account.delete.untouched.taps']}
            />

            {/* A shop owner must not find out afterwards that their photos
                are gone and their shop name has been released. */}
            {isMerchant && (
              <>
                <Group title={t('account.delete.merchantTitle')} items={MERCHANT} />
                <p className="mt-2">
                  <Link
                    to="/merchant"
                    className="inline-flex min-h-11 items-center text-sm font-medium text-brand-600 hover:underline dark:text-brand-400"
                  >
                    {t('account.delete.merchantLink')}
                  </Link>
                </p>
              </>
            )}

            <form onSubmit={handleDelete} className="mt-6">
              <h3 className="text-base font-semibold text-gray-900 dark:text-white">
                {t('account.delete.confirmTitle')}
              </h3>
              <p
                id="confirm-why"
                className="mt-2 text-sm leading-7 text-gray-700 dark:text-gray-300"
              >
                {t('account.delete.confirmWhy')}
              </p>

              <label
                htmlFor="confirm-email"
                className="mt-4 block text-sm font-medium text-gray-700 dark:text-gray-300"
              >
                {t('account.delete.confirmLabel')}
              </label>
              <input
                id="confirm-email"
                type="email"
                dir="ltr"
                value={typed}
                onChange={(event) => setTyped(event.target.value)}
                aria-describedby="confirm-why"
                // Autofill would type the address for them, which is the whole
                // of what this field is for. autoCapitalize stops a phone
                // keyboard capitalising it in the first place -- the compare
                // forgives that, but a field that visibly disagrees with the
                // address above it looks broken.
                autoComplete="off"
                autoCapitalize="none"
                autoCorrect="off"
                spellCheck="false"
                className="mt-1 w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-gray-900 focus:border-red-500 focus:outline-none focus:ring-2 focus:ring-red-500 dark:border-gray-700 dark:bg-gray-900 dark:text-white"
              />

              {error && (
                <div
                  role="alert"
                  className="mt-4 rounded bg-red-50 px-4 py-2 text-sm text-red-600 dark:bg-red-950/40 dark:text-red-400"
                >
                  {error}
                </div>
              )}

              <div className="mt-4 flex flex-wrap items-center gap-3">
                <button
                  type="submit"
                  disabled={!matches || busy}
                  className="inline-flex min-h-11 items-center rounded-lg bg-red-600 px-4 text-sm font-semibold text-white transition hover:bg-red-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-red-500 disabled:opacity-50"
                >
                  {busy ? t('account.delete.deleting') : t('account.delete.confirm')}
                </button>
                <button
                  type="button"
                  onClick={cancel}
                  disabled={busy}
                  className="inline-flex min-h-11 items-center rounded-lg border border-gray-300 px-5 text-sm font-medium text-gray-700 transition hover:bg-gray-50 disabled:opacity-50 dark:border-gray-700 dark:text-gray-300 dark:hover:bg-gray-800"
                >
                  {t('actions.cancel')}
                </button>
              </div>
            </form>
          </>
        )}
      </section>
    </div>
  );
}

function Detail({ label, children }) {
  return (
    <div className="flex flex-wrap items-baseline justify-between gap-3 py-3">
      <dt className="text-sm text-gray-600 dark:text-gray-400">{label}</dt>
      <dd className="text-sm font-medium text-gray-900 dark:text-white">{children}</dd>
    </div>
  );
}

function Group({ title, items }) {
  const { t } = useLocale();

  return (
    <>
      <h4 className="mt-4 text-sm font-semibold text-gray-900 dark:text-white">{title}</h4>
      <ul className="mt-1 space-y-2">
        {items.map((key) => (
          <li
            key={key}
            className="flex gap-2.5 text-sm leading-7 text-gray-700 dark:text-gray-300"
          >
            {/* A drawn dot rather than list-disc: a real marker needs padding
                on one side, and every one-sided utility here is a bug waiting
                for an Arabic reader. A flex row has no side. */}
            <span
              aria-hidden="true"
              className="mt-3 h-1.5 w-1.5 shrink-0 rounded-full bg-gray-400 dark:bg-gray-500"
            />
            <span>{t(key)}</span>
          </li>
        ))}
      </ul>
    </>
  );
}
