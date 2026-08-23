import { Link } from 'react-router-dom';
import MatchBadge from './MatchBadge';
import { formatPrice, formatStoreCount } from '../../utils/format';

/**
 * One product in the results list.
 *
 * Shows the cheapest TOTAL cost (price + delivery) rather than the headline
 * price, because that is what the shopper actually pays -- a store with a
 * lower sticker price and higher delivery is not the better deal.
 */
export default function ProductResultCard({ product }) {
  const inStock = product.store_count > 0;

  return (
    <Link
      to={`/product/${product.id}`}
      className="block rounded-lg border border-gray-200 bg-white p-4 transition hover:border-blue-400 hover:shadow-sm"
    >
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="font-medium text-gray-900">{product.canonical_name}</h3>
            <MatchBadge tier={product.match_tier} score={product.match_score} />
          </div>

          {product.brand && (
            <p className="mt-0.5 text-xs uppercase tracking-wide text-gray-400">
              {product.brand}
            </p>
          )}

          {/* The reason this is not an exact match. This is the whole point of
              the tiered results: the shopper can tell at a glance whether the
              difference matters to them. */}
          {product.differences?.length > 0 && (
            <ul className="mt-2 space-y-0.5">
              {product.differences.map((difference) => (
                <li key={difference} className="text-sm text-amber-700">
                  {difference}
                </li>
              ))}
            </ul>
          )}
        </div>

        <div className="shrink-0 text-left sm:text-right">
          {inStock ? (
            <>
              <p className="text-lg font-semibold text-gray-900">
                {formatPrice(product.lowest_total_cost)}
              </p>
              <p className="text-xs text-gray-500">
                incl. delivery
                {product.best_deal_store ? ` · ${product.best_deal_store}` : ''}
              </p>
              <p className="mt-1 text-xs text-gray-400">
                {formatStoreCount(product.store_count)}
              </p>
            </>
          ) : (
            <p className="text-sm text-gray-400">Not in stock</p>
          )}
        </div>
      </div>
    </Link>
  );
}
