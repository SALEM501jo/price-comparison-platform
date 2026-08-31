import { useLocale } from '../../hooks/useLocale';
const SORT_OPTIONS = [
  { value: 'price_asc', key: 'search.sort.priceAsc' },
  { value: 'price_desc', key: 'search.sort.priceDesc' },
  { value: 'name', key: 'search.sort.name' },
];

/**
 * Sorting control for the results page.
 *
 * Sorting applies WITHIN each tier, never across them -- reordering the whole
 * list by price would let a cheaper near-miss outrank the exact match, which
 * is the behaviour the tiers exist to prevent.
 */
export default function SearchControls({ sort, onSortChange, total, counts }) {
  const { t } = useLocale();

  return (
    <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
      <p className="text-sm text-gray-500 dark:text-gray-400">
        {total === 1 ? t('search.resultsOne') : t('search.results', { count: total })}
        {counts && (
          <span className="ml-1 text-gray-400 dark:text-gray-500">
            {t('search.counts', {
              exact: counts.exact,
              close: counts.close,
              similar: counts.similar,
            })}
          </span>
        )}
      </p>

      <label className="flex items-center gap-2 text-sm">
        <span className="text-gray-500 dark:text-gray-400">{t('search.sortLabel')}</span>
        <select
          value={sort}
          onChange={(e) => onSortChange(e.target.value)}
          className="min-h-11 rounded-lg border border-gray-300 px-2 focus:outline-none focus:ring-2 focus:ring-brand-500 dark:border-gray-700"
        >
          {SORT_OPTIONS.map((option) => (
            <option key={option.value} value={option.value}>
              {t(option.key)}
            </option>
          ))}
        </select>
      </label>
    </div>
  );
}
