import { useEffect, useState } from 'react';
import { getMyStats } from '../../api/merchant';
import { useLocale } from '../../hooks/useLocale';
import Spinner from '../ui/Spinner';

/**
 * What the platform actually did for this shop.
 *
 * There is no checkout here -- the sale happens on the phone -- so a shop has
 * no way of its own to tell whether this site is worth anything to it. This
 * panel is the answer to "how many customers did you send me?", which is the
 * first question any merchant asks before paying for a listing.
 *
 * THE WORDING IS THE FEATURE. These are TAPS: someone pressing Call or
 * WhatsApp. Whether the phone rang, was answered, or led to a sale is not
 * observable from a web page. Calling them "calls" would inflate the one
 * number a shop is being billed against, and the first time a merchant
 * compared it against their own call log the platform would lose the argument
 * and the customer. So the explainer sits under the figure permanently, not
 * behind a tooltip.
 */
export default function ContactStats({ isVerified }) {
  const { t } = useLocale();
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const controller = new AbortController();
    getMyStats({ signal: controller.signal })
      .then(setStats)
      .catch(() => {
        // A dashboard panel that cannot load must not take the page with it:
        // the merchant's prices are what they came here to manage.
        setStats(null);
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, []);

  if (loading) return <Spinner />;
  if (!stats) return null;

  const channels = [
    ['call', 'stats.call'],
    ['whatsapp', 'stats.whatsapp'],
    ['facebook', 'stats.facebook'],
    ['instagram', 'stats.instagram'],
  ];

  const describe = (count) => {
    if (!count) return t('stats.tapsNone');
    return count === 1 ? t('stats.tapsOne') : t('stats.taps', { count });
  };

  return (
    <div className="rounded-lg border border-gray-200 bg-white p-4 dark:border-gray-800 dark:bg-gray-900">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400">
          {t('stats.heading')}
        </h2>
        <span className="text-xs text-gray-400 dark:text-gray-500">
          {t('stats.window', { days: stats.window_days })}
        </span>
      </div>

      <p className="mt-2 text-3xl font-semibold text-gray-900 dark:text-white">
        {describe(stats.total)}
      </p>

      {/* Every channel, including the ones at zero. "Nobody used WhatsApp"
          and "WhatsApp is not set up" need different actions from the shop
          owner, and hiding empty rows makes the two look identical. */}
      <div className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-4">
        {channels.map(([key, label]) => (
          <div
            key={key}
            className="rounded-lg bg-gray-50 px-3 py-2 dark:bg-gray-800"
          >
            <p className="text-xs text-gray-500 dark:text-gray-400">{t(label)}</p>
            <p className="text-lg font-semibold text-gray-900 dark:text-white">
              {stats.by_channel?.[key] ?? 0}
            </p>
          </div>
        ))}
      </div>

      {stats.top_products?.length > 0 && (
        <div className="mt-4">
          <h3 className="text-xs font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400">
            {t('stats.topProducts')}
          </h3>
          <ul className="mt-1.5 space-y-1">
            {stats.top_products.map((row) => (
              <li
                key={row.product_id}
                className="flex items-baseline justify-between gap-3 text-sm"
              >
                <span className="min-w-0 truncate text-gray-700 dark:text-gray-300">
                  {row.product_name}
                </span>
                <span className="shrink-0 font-medium text-gray-900 dark:text-white">
                  {row.taps}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {!isVerified && (
        <p className="mt-3 rounded-md bg-amber-50 px-3 py-2 text-xs text-amber-800 dark:bg-amber-900/30 dark:text-amber-300">
          {t('stats.unverifiedHint')}
        </p>
      )}

      {/* Permanent, not a tooltip. See the component docstring. */}
      <p className="mt-3 text-xs text-gray-500 dark:text-gray-400">
        {t('stats.explainer')}
      </p>
    </div>
  );
}
