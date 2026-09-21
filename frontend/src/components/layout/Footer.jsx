import { Link } from 'react-router-dom';
import { useLocale } from '../../hooks/useLocale';

/**
 * The site footer.
 *
 * THERE IS NO COOKIE CONSENT BANNER, AND THAT IS A DECISION, NOT AN OVERSIGHT.
 * Please do not "fix" it. This site sets exactly one cookie -- the refresh
 * token, httpOnly, scoped to /auth, written only once someone signs in --
 * which is strictly necessary to keep a signed-in user signed in and needs no
 * consent. The only other browser storage is the locale and the theme the
 * visitor chose by clicking, neither of which carries an identifier or ever
 * leaves the device. There is no analytics service, no advertising pixel and
 * no session recording anywhere in this codebase. A banner would therefore
 * ask permission for tracking that does not happen -- claiming a practice we
 * do not have -- and would teach one more person to dismiss a consent dialog
 * without reading it. What we owe the reader instead is an explanation, and
 * that lives in the privacy policy under "Cookies and browser storage". If
 * anything that genuinely tracks a visitor is ever added, that is the change
 * that earns a consent prompt.
 *
 * QUIET ON PURPOSE. The navbar is where someone goes; this is where they look
 * when they want to know who is behind the site and whether it is selling
 * them something. Four links, one sentence, no calls to action. About comes
 * first because it answers the first of those questions.
 */
export default function Footer() {
  const { t } = useLocale();

  return (
    <footer className="mt-16 border-t border-gray-200 bg-white dark:border-gray-800 dark:bg-gray-900">
      <div className="mx-auto max-w-6xl px-4 py-8">
        <div className="flex flex-col gap-6 sm:flex-row sm:items-start sm:justify-between">
          <div className="max-w-sm">
            <p className="text-sm font-semibold text-gray-900 dark:text-white">
              {t('brand.name')}
            </p>
            {/* The one thing a first-time visitor most often gets wrong about
                this site: they think it is a shop and wait for a cart. */}
            <p className="mt-1 text-sm leading-6 text-gray-600 dark:text-gray-400">
              {t('footer.notAShop')}
            </p>
          </div>

          <nav
            aria-label={t('footer.nav')}
            className="flex flex-wrap items-center gap-x-6 gap-y-1"
          >
            <Link
              to="/about"
              className="inline-flex min-h-11 items-center text-sm text-gray-600 transition hover:text-gray-900 dark:text-gray-400 dark:hover:text-gray-100"
            >
              {t('footer.about')}
            </Link>
            <Link
              to="/privacy"
              className="inline-flex min-h-11 items-center text-sm text-gray-600 transition hover:text-gray-900 dark:text-gray-400 dark:hover:text-gray-100"
            >
              {t('footer.privacy')}
            </Link>
            <Link
              to="/terms"
              className="inline-flex min-h-11 items-center text-sm text-gray-600 transition hover:text-gray-900 dark:text-gray-400 dark:hover:text-gray-100"
            >
              {t('footer.terms')}
            </Link>
            <Link
              to="/contact"
              className="inline-flex min-h-11 items-center text-sm text-gray-600 transition hover:text-gray-900 dark:text-gray-400 dark:hover:text-gray-100"
            >
              {t('nav.contact')}
            </Link>
          </nav>
        </div>

        <p className="mt-6 text-xs text-gray-500 dark:text-gray-400">
          {t('footer.copyright', { year: new Date().getFullYear() })}
        </p>
      </div>
    </footer>
  );
}
