import { useLocale } from '../../hooks/useLocale';
import { API_BASE_URL } from '../../utils/constants';

/**
 * "Continue with Google" / "Sign in with Apple", plus the divider that
 * separates them from the email form.
 *
 * THESE ARE LINKS, NOT BUTTONS THAT FETCH. Sign-in is a server-side redirect
 * chain that ends on accounts.google.com: XHR cannot follow it, and a popup
 * would have to be reopened by hand every time a browser's blocker ate it. A
 * plain <a> to the API's start endpoint is the whole mechanism -- which is
 * also why no Google or Apple JavaScript is loaded here, and why the
 * production CSP can stay at script-src 'self'.
 *
 * Presentational on purpose: it is handed the provider list rather than
 * fetching it, so the render can be tested without a network. SocialSignIn is
 * the wrapper that does the asking.
 */

// One entry per provider the API can return. An id with no entry is dropped
// rather than rendered: a button with no mark and no label would be a blank
// 44px rectangle that still navigates somewhere.
const PROVIDERS = {
  google: { labelKey: 'auth.continueWithGoogle', Mark: GoogleMark },
  apple: { labelKey: 'auth.continueWithApple', Mark: AppleMark },
};

// Matched to the submit button below it -- same width, same min-h-11, same
// py-2 and font-medium -- because three sign-in controls of three different
// heights is the first thing the eye lands on in a stack this short.
const socialButton =
  'flex w-full min-h-11 items-center justify-center gap-3 rounded-lg border ' +
  'border-gray-300 px-4 py-2 font-medium text-gray-900 transition ' +
  'hover:bg-gray-50 focus:outline-none focus-visible:ring-2 ' +
  'focus-visible:ring-brand-500 dark:border-gray-700 dark:text-white ' +
  'dark:hover:bg-gray-800';

export default function SocialButtons({ providers }) {
  const { t } = useLocale();

  // null means the list is still in flight; an array means the answer is in.
  const known = providers?.filter((provider) => PROVIDERS[provider.id]) ?? null;

  // Nothing configured, or the list could not be fetched. Render nothing at
  // all -- no divider, no empty gap -- and leave the email form as the only
  // way in, which it always was.
  if (known?.length === 0) return null;

  return (
    <>
      <div className="space-y-3">
        {/* The placeholder is one button tall so the email form below does
            not jump when the answer lands: Google alone is the shipping
            configuration, which makes the swap a replacement rather than a
            reflow under whatever the pointer was already over. */}
        {known === null ? (
          <div
            className="min-h-11 animate-pulse rounded-lg bg-gray-100 dark:bg-gray-800"
            aria-hidden="true"
          />
        ) : (
          known.map((provider) => {
            const { labelKey, Mark } = PROVIDERS[provider.id];
            return (
              <a
                key={provider.id}
                // The start endpoint lives on the API, which is a different
                // origin in development (:8000 vs :5173) and the same one in
                // production. Either way this is a top-level navigation.
                href={`${API_BASE_URL}${provider.start_url}`}
                className={socialButton}
              >
                {/* The mark leads the label. In an RTL page that means the
                    right-hand side, which is what both brands' guidelines
                    ask for -- flex + gap gets it for free, and a physical
                    margin here would pin it to the left in Arabic. */}
                <Mark />
                {t(labelKey)}
              </a>
            );
          })
        )}
      </div>

      {/* Decorative, and hidden from assistive tech deliberately: a screen
          reader that announces a lone "or" between two groups it cannot see
          has been told nothing. The buttons and the form each name
          themselves. */}
      <div className="my-6 flex items-center gap-3" aria-hidden="true">
        <span className="h-px flex-1 bg-gray-200 dark:bg-gray-800" />
        <span className="text-xs text-gray-500 dark:text-gray-400">{t('auth.or')}</span>
        <span className="h-px flex-1 bg-gray-200 dark:bg-gray-800" />
      </div>
    </>
  );
}

/**
 * The Google "G", in Google's four brand colours.
 *
 * Inline rather than an <img>: an external mark would be a request to a third
 * party on the login page -- the one page where an outage or a blocked domain
 * is least acceptable -- and img-src would have to be widened to allow it.
 * The colours are fixed hex values, not theme tokens: the G is Google's, and
 * it is the same G in both themes.
 */
function GoogleMark() {
  return (
    <svg viewBox="0 0 48 48" className="h-5 w-5 shrink-0" aria-hidden="true">
      <path
        fill="#EA4335"
        d="M24 9.5c3.54 0 6.71 1.22 9.21 3.6l6.85-6.85C35.9 2.38 30.47 0 24 0 14.62 0 6.51 5.38 2.56 13.22l7.98 6.19C12.43 13.72 17.74 9.5 24 9.5z"
      />
      <path
        fill="#4285F4"
        d="M46.98 24.55c0-1.57-.15-3.09-.38-4.55H24v9.02h12.94c-.58 2.96-2.26 5.48-4.78 7.18l7.73 6c4.51-4.18 7.09-10.36 7.09-17.65z"
      />
      <path
        fill="#FBBC05"
        d="M10.53 28.59c-.48-1.45-.76-2.99-.76-4.59s.27-3.14.76-4.59l-7.98-6.19C.92 16.46 0 20.12 0 24c0 3.88.92 7.54 2.56 10.78l7.97-6.19z"
      />
      <path
        fill="#34A853"
        d="M24 48c6.48 0 11.93-2.13 15.89-5.81l-7.73-6c-2.15 1.45-4.92 2.3-8.16 2.3-6.26 0-11.57-4.22-13.47-9.91l-7.98 6.19C6.51 42.62 14.62 48 24 48z"
      />
    </svg>
  );
}

/**
 * The Apple mark, monochrome.
 *
 * fill="currentColor" rather than a hex: Apple's guidelines allow a black mark
 * on a light button and a white one on a dark button, and inheriting the
 * button's text colour is what makes the same element satisfy both without a
 * dark: variant to keep in sync.
 */
function AppleMark() {
  return (
    <svg
      viewBox="0 0 24 24"
      className="h-5 w-5 shrink-0"
      fill="currentColor"
      aria-hidden="true"
    >
      <path d="M17.05 20.28c-.98.95-2.05.8-3.08.35-1.09-.46-2.09-.48-3.24 0-1.44.62-2.2.44-3.06-.35C2.79 15.25 3.51 7.59 9.05 7.31c1.35.07 2.29.74 3.08.8 1.18-.24 2.31-.93 3.57-.84 1.51.12 2.65.72 3.4 1.8-3.12 1.87-2.38 5.98.48 7.13-.57 1.5-1.31 2.99-2.54 4.09zM12.03 7.25c-.15-2.23 1.66-4.07 3.74-4.25.29 2.58-2.34 4.5-3.74 4.25z" />
    </svg>
  );
}
