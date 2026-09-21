import { useState } from 'react';
import { Link, NavLink, useNavigate } from 'react-router-dom';
import { useAuth } from '../../hooks/useAuth';
import { useLocale } from '../../hooks/useLocale';
import { useTheme } from '../../hooks/useTheme';
import Logo from './Logo';

const linkClass = ({ isActive }) =>
  `inline-flex min-h-11 items-center text-sm transition ${
    isActive
      ? 'font-semibold text-brand-700 dark:text-brand-400'
      : 'text-gray-600 hover:text-gray-900 dark:text-gray-400 dark:hover:text-gray-100'
  }`;

// The same links, laid out for the mobile drawer: full-width rows big enough
// to tap, not the inline row the desktop bar uses.
const mobileLinkClass = ({ isActive }) =>
  `flex min-h-12 items-center rounded-lg px-3 text-base transition ${
    isActive
      ? 'bg-brand-50 font-semibold text-brand-700 dark:bg-gray-800 dark:text-brand-400'
      : 'text-gray-700 hover:bg-gray-50 dark:text-gray-300 dark:hover:bg-gray-800'
  }`;

const iconButton =
  'inline-flex h-11 items-center gap-1.5 rounded-lg border border-gray-200 px-3 text-sm ' +
  'text-gray-600 transition hover:bg-gray-50 hover:text-gray-900 ' +
  'focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-500 ' +
  'dark:border-gray-700 dark:text-gray-300 dark:hover:bg-gray-800 dark:hover:text-white';

function SunIcon() {
  return (
    <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
      <circle cx="12" cy="12" r="4" />
      <path strokeLinecap="round" d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" />
    </svg>
  );
}

function MoonIcon() {
  return (
    <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
      <path strokeLinecap="round" strokeLinejoin="round" d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8Z" />
    </svg>
  );
}

function MenuIcon() {
  return (
    <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
      <path strokeLinecap="round" d="M4 6h16M4 12h16M4 18h16" />
    </svg>
  );
}

function CloseIcon() {
  return (
    <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
      <path strokeLinecap="round" d="M6 6l12 12M18 6L6 18" />
    </svg>
  );
}

export default function Navbar() {
  const { user, isAuthenticated, isAdmin, isMerchant, logout, loading } = useAuth();
  const { t, locale, toggleLocale } = useLocale();
  const { isDark, toggleTheme } = useTheme();
  const navigate = useNavigate();
  // The mobile drawer. Below the `sm` breakpoint the links have no room in the
  // bar, so they live here behind a toggle instead of vanishing.
  const [menuOpen, setMenuOpen] = useState(false);
  const closeMenu = () => setMenuOpen(false);

  const handleLogout = async () => {
    closeMenu();
    await logout();
    // navigate() keeps this a single-page transition. window.location.href
    // reloads the whole app and throws away every bit of client state.
    navigate('/');
  };

  return (
    // STICKY, because on a phone this bar is the only way back. It used to
    // scroll away with the page: on a long results or product page the logo,
    // the language switch and the menu were hundreds of pixels above, and
    // getting back meant scrolling up through everything. z-40 keeps it over
    // the page content and under any dialog.
    <nav className="sticky top-0 z-40 border-b border-gray-200 bg-white shadow-sm dark:border-gray-800 dark:bg-gray-900">
      <div className="mx-auto flex max-w-6xl items-center justify-between gap-4 px-4 py-3">
        <div className="flex items-center gap-6">
          <Logo />

          {isAuthenticated && (
            <div className="hidden items-center gap-4 sm:flex">
              <NavLink to="/wishlist" className={linkClass}>
                {t('nav.wishlist')}
              </NavLink>
              <NavLink to="/alerts" className={linkClass}>
                {t('nav.alerts')}
              </NavLink>
              {/* Only merchants. A shopper has no shop, and offering them the
                  link made the site look like it was for sellers. */}
              {isMerchant && (
                <NavLink to="/merchant" className={linkClass}>
                  {t('nav.myShop')}
                </NavLink>
              )}
              {isAdmin && (
                <NavLink to="/admin" className={linkClass}>
                  {t('nav.admin')}
                </NavLink>
              )}
              {/* Last, because it is the settings drawer of this app rather
                  than somewhere to browse -- and it is the only route to
                  deleting an account, which the privacy policy promises. */}
              <NavLink to="/account" className={linkClass}>
                {t('nav.account')}
              </NavLink>
            </div>
          )}
        </div>

        <div className="flex items-center gap-2">
          {/* Outside the signed-in block on purpose: someone locked out of
              their account is exactly who needs to reach us. */}
          <NavLink to="/contact" className={`${linkClass({ isActive: false })} hidden sm:inline`}>
            {t('nav.contact')}
          </NavLink>
          {/* Each toggle shows the language it switches TO, not the one you
              are in -- a button labelled with the current state reads as a
              status display and people do not press it. */}
          <button
            onClick={toggleLocale}
            className={iconButton}
            aria-label={t('nav.toggleLanguage')}
            title={t('nav.toggleLanguage')}
          >
            <span className="font-semibold">
              {locale === 'ar' ? 'EN' : 'ع'}
            </span>
          </button>

          <button
            onClick={toggleTheme}
            className={iconButton}
            aria-label={isDark ? t('nav.toggleThemeLight') : t('nav.toggleTheme')}
            title={isDark ? t('nav.toggleThemeLight') : t('nav.toggleTheme')}
          >
            {isDark ? <SunIcon /> : <MoonIcon />}
          </button>

          {/* The hamburger — mobile only. It carries the links the bar hides
              below `sm`: the account, the shop, admin, alerts, favourites and
              contact. Without it those routes are unreachable on a phone. */}
          <button
            onClick={() => setMenuOpen((open) => !open)}
            className={`${iconButton} sm:hidden`}
            aria-label={menuOpen ? t('nav.closeMenu') : t('nav.menu')}
            aria-expanded={menuOpen}
            aria-controls="mobile-menu"
          >
            {menuOpen ? <CloseIcon /> : <MenuIcon />}
          </button>

          {/* While the refresh cookie is being exchanged, render neither
              state. Showing "Login" first makes the navbar flicker on every
              page load for users who are in fact signed in. */}
          {loading ? (
            <span className="h-5 w-20 animate-pulse rounded bg-gray-100 dark:bg-gray-800" />
          ) : isAuthenticated ? (
            <>
              <span className="hidden text-sm text-gray-600 dark:text-gray-400 lg:inline">
                {user?.email}
              </span>
              <button
                onClick={handleLogout}
                className="inline-flex min-h-11 items-center text-sm text-red-600 transition hover:text-red-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-red-500 dark:text-red-400 dark:hover:text-red-300"
              >
                {t('nav.logout')}
              </button>
            </>
          ) : (
            <Link
              to="/login"
              className="inline-flex min-h-11 items-center rounded-lg bg-brand-600 px-3.5 text-sm font-medium text-white transition hover:bg-brand-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-500"
            >
              {t('nav.login')}
            </Link>
          )}
        </div>
      </div>

      {/* The mobile drawer. `sm:hidden` so it never shows on desktop, where the
          same links already sit in the bar. Every row closes it, so a tap both
          navigates and dismisses. */}
      {menuOpen && (
        <div
          id="mobile-menu"
          className="space-y-1 border-t border-gray-200 px-3 py-2 sm:hidden dark:border-gray-800"
        >
          {isAuthenticated && (
            <>
              {/* The signed-in email, so it is clear whose account these
                  links belong to — it is hidden in the bar until `lg`. */}
              {user?.email && (
                <p className="px-3 py-1 text-xs text-gray-500 dark:text-gray-400">
                  {user.email}
                </p>
              )}
              <NavLink to="/wishlist" className={mobileLinkClass} onClick={closeMenu}>
                {t('nav.wishlist')}
              </NavLink>
              <NavLink to="/alerts" className={mobileLinkClass} onClick={closeMenu}>
                {t('nav.alerts')}
              </NavLink>
              {isMerchant && (
                <NavLink to="/merchant" className={mobileLinkClass} onClick={closeMenu}>
                  {t('nav.myShop')}
                </NavLink>
              )}
              {isAdmin && (
                <NavLink to="/admin" className={mobileLinkClass} onClick={closeMenu}>
                  {t('nav.admin')}
                </NavLink>
              )}
              <NavLink to="/account" className={mobileLinkClass} onClick={closeMenu}>
                {t('nav.account')}
              </NavLink>
            </>
          )}
          {/* Contact is here for everyone, signed in or not: on a phone the
              bar hides it too, and someone locked out needs to reach us. */}
          <NavLink to="/contact" className={mobileLinkClass} onClick={closeMenu}>
            {t('nav.contact')}
          </NavLink>
        </div>
      )}
    </nav>
  );
}
