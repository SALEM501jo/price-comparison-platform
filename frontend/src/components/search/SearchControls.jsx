const SORT_OPTIONS = [
  { value: 'price_asc', label: 'Cheapest first' },
  { value: 'price_desc', label: 'Most expensive first' },
  { value: 'name', label: 'Name (A–Z)' },
];

/**
 * Sorting control for the results page.
 *
 * Sorting applies WITHIN each tier, never across them -- reordering the whole
 * list by price would let a cheaper near-miss outrank the exact match, which
 * is the behaviour the tiers exist to prevent.
 */
export default function SearchControls({ sort, onSortChange, total, counts }) {
  return (
    <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
      <p className="text-sm text-gray-500">
        {total} {total === 1 ? 'product' : 'products'}
        {counts && (
          <span className="ml-1 text-gray-400">
            ({counts.exact} exact · {counts.close} close · {counts.similar} similar)
          </span>
        )}
      </p>

      <label className="flex items-center gap-2 text-sm">
        <span className="text-gray-500">Sort within each group</span>
        <select
          value={sort}
          onChange={(e) => onSortChange(e.target.value)}
          className="rounded-lg border border-gray-300 px-2 py-1 focus:outline-none focus:ring-2 focus:ring-blue-500"
        >
          {SORT_OPTIONS.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
      </label>
    </div>
  );
}
