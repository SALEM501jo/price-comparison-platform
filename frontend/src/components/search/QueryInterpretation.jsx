import { describeAttributes } from '../../utils/format';
import { useLocale } from '../../hooks/useLocale';

/**
 * Shows what the server understood the query to mean.
 *
 * WHY SURFACE THIS: when a search returns something unexpected, the shopper
 * has no way to tell whether the catalogue lacks the product or the query was
 * read differently than intended. Showing the parsed attributes turns a
 * confusing result into an obvious one -- "ah, it read 128GB, I meant 256".
 */
export default function QueryInterpretation({ interpretation }) {
  const { t } = useLocale();
  if (!interpretation) return null;

  const { structured, attributes } = interpretation;

  if (!structured) {
    return (
      <p className="mb-6 text-sm text-gray-500 dark:text-gray-400">
        {t('search.byName')}
      </p>
    );
  }

  const summary = describeAttributes(attributes);
  if (!summary) return null;

  return (
    <div className="mb-6 flex flex-wrap items-center gap-2 text-sm">
      <span className="text-gray-500 dark:text-gray-400">
        {t('search.lookingFor')}
      </span>
      {Object.entries(attributes)
        .filter(([key, value]) => key !== 'brand' && !(key === 'variant' && value === 'base'))
        .map(([key, value]) => (
          <span
            key={key}
            dir="ltr"
            className="rounded bg-brand-50 px-2 py-0.5 font-medium text-brand-800 dark:bg-brand-900/40 dark:text-brand-300"
            title={key}
          >
            {value}
          </span>
        ))}
    </div>
  );
}
