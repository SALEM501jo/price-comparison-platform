import { Link } from 'react-router-dom';
import { useLocale } from '../../hooks/useLocale';

/**
 * The wordmark.
 *
 * WHY THE NAME STAYS ARABIC IN BOTH LANGUAGES: a brand name is not a string to
 * translate. "احسن سعر" is what someone will say to a friend and type into a
 * search box, and swapping it for a Latin rendering in English mode would give
 * the site two identities and neither would stick. English readers get a small
 * transliteration alongside instead.
 *
 * The mark is a price tag drawn inline rather than an image file: it is two
 * paths, it inherits the current colour so it works in both themes without a
 * second asset, and it cannot arrive late and shift the layout.
 */
export default function Logo({ compact = false }) {
  const { t, locale } = useLocale();

  return (
    <Link
      to="/"
      className="group flex min-h-11 items-center gap-2.5"
      aria-label={t('brand.name')}
    >
      <svg
        viewBox="0 0 32 32"
        className="h-8 w-8 shrink-0 text-brand-600 dark:text-brand-400"
        aria-hidden="true"
      >
        {/* The tag body, corner cut where the string threads through. */}
        <path
          d="M17.4 3.2 28.8 14.6a3 3 0 0 1 0 4.24l-9.96 9.96a3 3 0 0 1-4.24 0L3.2 17.4A3 3 0 0 1 2.32 15.28V5.32A3 3 0 0 1 5.32 2.32h9.96a3 3 0 0 1 2.12.88Z"
          fill="currentColor"
          opacity="0.16"
        />
        <path
          d="M17.4 3.2 28.8 14.6a3 3 0 0 1 0 4.24l-9.96 9.96a3 3 0 0 1-4.24 0L3.2 17.4A3 3 0 0 1 2.32 15.28V5.32A3 3 0 0 1 5.32 2.32h9.96a3 3 0 0 1 2.12.88Z"
          fill="none"
          stroke="currentColor"
          strokeWidth="2.1"
          strokeLinejoin="round"
        />
        {/* The eyelet. */}
        <circle cx="9.4" cy="9.4" r="2.5" fill="currentColor" />
      </svg>

      <span className="flex flex-col leading-none">
        <span className="text-xl font-extrabold tracking-tight text-gray-900 dark:text-white">
          {/* Two-tone so the mark reads as a designed thing rather than a
              heading that happens to sit in the corner. */}
          <span>احسن</span>{' '}
          <span className="text-brand-600 dark:text-brand-400">سعر</span>
        </span>
        {!compact && locale === 'en' && (
          <span className="mt-0.5 text-[10px] font-medium uppercase tracking-[0.18em] text-gray-400 dark:text-gray-500">
            Ahsan Se3r
          </span>
        )}
      </span>
    </Link>
  );
}
