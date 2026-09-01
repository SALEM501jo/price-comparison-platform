import { Link } from 'react-router-dom';
import { formatPrice } from '../../utils/format';
import ProductImage from '../ui/ProductImage';
import { useLocale } from '../../hooks/useLocale';

/**
 * "Biggest savings" for the home page.
 *
 * WHAT A DEAL MEANS HERE: not a discount off a list price -- this platform has
 * no list price, and inventing one to strike through would be exactly the
 * fake-urgency pattern a comparison site exists to see past. The number shown
 * is the gap between the cheapest and the dearest shop stocking the same
 * product right now, which is the one saving we can actually stand behind.
 *
 * New stock only, and only products carried by two or more shops -- a single
 * price is not a comparison.
 */
export default function DealsGrid({ deals, loading }) {
  const { t } = useLocale();

  if (loading) {
    return (
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {Array.from({ length: 4 }).map((_, i) => (
          <div
            key={i}
            className="h-36 animate-pulse rounded-xl border border-gray-200 bg-white dark:border-gray-800 dark:bg-gray-900"
          />
        ))}
      </div>
    );
  }

  // Nothing to show is a normal state: it means no product is stocked by two
  // shops at different prices yet. Better an absent section than an empty box.
  if (!deals?.length) return null;

  return (
    <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
      {deals.map((deal) => (
        <Link
          key={deal.id}
          to={`/product/${deal.id}`}
          className="flex flex-col rounded-xl border border-gray-200 bg-white p-4 transition hover:border-brand-400 hover:shadow-md dark:border-gray-800 dark:bg-gray-900 dark:hover:border-brand-600"
        >
          <div className="mb-2 flex items-start justify-between gap-2">
            <span className="rounded-full bg-brand-100 px-2.5 py-0.5 text-xs font-bold text-brand-800 dark:bg-brand-900/50 dark:text-brand-300">
              {t('home.save')} {formatPrice(deal.saving)}
            </span>
            <span className="text-xs font-medium text-gray-400 tnum dark:text-gray-500">
              {deal.saving_percent}%
            </span>
          </div>

          <div className="flex flex-1 items-start gap-3">
            <ProductImage
              src={deal.image_url}
              alt={deal.canonical_name}
              size="thumb"
            />
            <p className="line-clamp-3 flex-1 text-sm font-medium text-gray-900 dark:text-gray-100">
              {deal.canonical_name}
            </p>
          </div>

          <div className="mt-3">
            <p className="text-lg font-bold text-gray-900 tnum dark:text-white">
              {formatPrice(deal.lowest_total_cost)}
            </p>
            <p className="text-xs text-gray-500 dark:text-gray-400">
              {t('home.at')} {deal.best_deal_store}
              {/* The dearest price is context, not a struck-through "was":
                  it is a real price at a real shop. */}
              <span className="text-gray-400 dark:text-gray-500">
                {' · '}
                {t('home.upTo')} {formatPrice(deal.highest_total_cost)}{' '}
                {t('home.elsewhere')}
              </span>
            </p>
            <p className="mt-1 text-xs text-gray-400 dark:text-gray-500">
              {t('home.comparedAcross', { count: deal.store_count })}
            </p>
          </div>
        </Link>
      ))}
    </div>
  );
}
