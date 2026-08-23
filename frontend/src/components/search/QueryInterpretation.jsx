import { describeAttributes } from '../../utils/format';

/**
 * Shows what the server understood the query to mean.
 *
 * WHY SURFACE THIS: when a search returns something unexpected, the shopper
 * has no way to tell whether the catalogue lacks the product or the query was
 * read differently than intended. Showing the parsed attributes turns a
 * confusing result into an obvious one -- "ah, it read 128GB, I meant 256".
 */
export default function QueryInterpretation({ interpretation }) {
  if (!interpretation) return null;

  const { structured, attributes } = interpretation;

  if (!structured) {
    return (
      <p className="mb-6 text-sm text-gray-500">
        Searching by name. Add details like storage or colour
        {' '}&mdash; for example{' '}
        <span className="font-medium text-gray-700">iPhone 15 128GB Black</span>
        {' '}&mdash; to get exact matches.
      </p>
    );
  }

  const summary = describeAttributes(attributes);
  if (!summary) return null;

  return (
    <div className="mb-6 flex flex-wrap items-center gap-2 text-sm">
      <span className="text-gray-500">Looking for:</span>
      {Object.entries(attributes)
        .filter(([key, value]) => key !== 'brand' && !(key === 'variant' && value === 'base'))
        .map(([key, value]) => (
          <span
            key={key}
            className="rounded bg-blue-50 px-2 py-0.5 font-medium text-blue-800"
            title={key}
          >
            {value}
          </span>
        ))}
    </div>
  );
}
