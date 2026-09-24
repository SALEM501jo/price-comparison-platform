import { useLocale } from '../../hooks/useLocale';

// The search results' tier colours (MatchBadge), plus the one tier search
// never shows: below 70 a listing is left off the page, and the Lab has to
// be able to say so.
const STYLES = {
  exact:
    'bg-green-100 text-green-800 ring-green-600/20 dark:bg-green-900/40 dark:text-green-300 dark:ring-green-500/30',
  close:
    'bg-amber-100 text-amber-800 ring-amber-600/20 dark:bg-amber-900/40 dark:text-amber-300 dark:ring-amber-500/30',
  similar:
    'bg-gray-100 text-gray-700 ring-gray-500/20 dark:bg-gray-800 dark:text-gray-300 dark:ring-gray-600/40',
  excluded:
    'bg-red-50 text-red-700 ring-red-600/20 dark:bg-red-900/30 dark:text-red-300 dark:ring-red-500/30',
};

/** A tier in words, never colour alone. */
export default function TierLabel({ tier }) {
  const { t } = useLocale();
  return (
    <span
      className={`inline-flex items-center whitespace-nowrap rounded-full px-2 py-0.5 text-xs font-medium ring-1 ring-inset ${STYLES[tier] ?? STYLES.excluded}`}
    >
      {t(`lab.tier.${tier}`)}
    </span>
  );
}
