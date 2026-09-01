import { Link } from 'react-router-dom';
import MatchBadge from './MatchBadge';
import { formatPrice, formatStoreCount } from '../../utils/format';
import { describeDifference } from '../../utils/matchDifference';
import ProductImage from '../ui/ProductImage';
import { useLocale } from '../../hooks/useLocale';

/**
 * One product in the results list.
 *
 * Shows the cheapest TOTAL cost (price + delivery) rather than the headline
 * price, because that is what the shopper actually pays -- a store with a
 * lower sticker price and higher delivery is not the better deal.
 */
export default function ProductResultCard({ product }) {
  const { t } = useLocale();
  const inStock = product.store_count > 0;
  const secondHand = (product.second_hand_store_count ?? 0) > 0;

  return (
    <Link
      to={`/product/${product.id}`}
      className="block rounded-lg border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900 p-4 transition hover:border-brand-400 hover:shadow-sm"
    >
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="flex min-w-0 flex-1 items-start gap-3">
          <ProductImage
            src={product.image_url}
            alt={product.canonical_name}
            size="card"
          />
          <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="font-medium text-gray-900 dark:text-white">{product.canonical_name}</h3>
            <MatchBadge tier={product.match_tier} score={product.match_score} />
          </div>

          {product.brand && (
            <p className="mt-0.5 text-xs uppercase tracking-wide text-gray-400 dark:text-gray-500">
              {product.brand}
            </p>
          )}

          {/* The reason this is not an exact match. This is the whole point of
              the tiered results: the shopper can tell at a glance whether the
              difference matters to them -- which means it has to be in the
              language they are reading. The server sends the attribute and the
              two values; the sentence is composed here. */}
          {product.differences?.length > 0 && (
            <ul className="mt-2 space-y-0.5">
              {product.differences.map((difference) => (
                <li
                  key={difference.attribute}
                  className="text-sm text-amber-700 dark:text-amber-400"
                >
                  {describeDifference(difference, t)}
                </li>
              ))}
            </ul>
          )}
          </div>
        </div>

        {/* The headline figure is the NEW price. Second-hand stock is quoted
            underneath rather than folded in, because a worn handset is not a
            cheaper version of the same offer -- and if it were the headline,
            every product with one used listing would look like a bargain. */}
        <div className="shrink-0 text-left sm:text-right">
          {inStock ? (
            <>
              <p className="text-lg font-semibold text-gray-900 dark:text-white">
                {formatPrice(product.lowest_total_cost)}
              </p>
              <p className="text-xs text-gray-500 dark:text-gray-400">
                {t('common.inclDelivery')}
                {product.best_deal_store ? ` · ${product.best_deal_store}` : ''}
              </p>
              <p className="mt-1 text-xs text-gray-400 dark:text-gray-500">
                {formatStoreCount(product.store_count, t)}
              </p>
            </>
          ) : (
            !secondHand && (
              <p className="text-sm text-gray-400 dark:text-gray-500">
                {t('common.notInStock')}
              </p>
            )
          )}

          {secondHand && (
            <p className={`text-xs ${inStock ? 'mt-1.5 text-gray-500' : 'text-gray-700'}`}>
              {inStock ? (
                t('common.orUsedFrom', {
                  price: formatPrice(product.second_hand_from),
                })
              ) : (
                <>
                  <span className="block text-lg font-semibold text-gray-900 dark:text-white">
                    {formatPrice(product.second_hand_from)}
                  </span>
                  {t('common.usedOnly')} ·{' '}
                  {formatStoreCount(product.second_hand_store_count, t)}
                </>
              )}
            </p>
          )}
        </div>
      </div>
    </Link>
  );
}
