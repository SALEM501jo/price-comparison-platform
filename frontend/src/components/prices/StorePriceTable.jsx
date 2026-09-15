import { formatPrice, formatAge, isPriceStale } from '../../utils/format';
import { useLocale } from '../../hooks/useLocale';
import { recordContactTap } from '../../api/products';

/**
 * A thumb-sized hit area for the contact links.
 *
 * WHY THIS EXISTS AS A CONSTANT: these are the only buttons on the site that
 * complete a purchase. There is no checkout -- a shopper compares, taps Call
 * or WhatsApp, and the rest happens on the phone -- so if these are hard to
 * hit, nothing else on the page matters.
 *
 * Measured at 375px before this: 24px and 26px tall. That clears the WCAG 2.2
 * AA floor of 24px by a hair and falls well short of both platform
 * guidelines, which are what actually govern whether a thumb lands on it --
 * Apple's HIG says 44pt and Material says 48dp.
 *
 * min-h-11 is 44px. inline-flex + items-center keeps the label centred as the
 * box grows, so the button gets bigger without the text moving.
 */
const TAP_TARGET =
  'inline-flex min-h-11 items-center justify-center rounded-md px-3 ' +
  'text-xs font-medium transition';

/**
 * Every store's price for one product, cheapest total first.
 *
 * The backend already sorts by total cost, but the sort is repeated here so
 * the component is correct on its own rather than depending on the caller.
 *
 * TWO KINDS OF ROW. A scraped store links to its own product page. A merchant
 * store has no website at all -- its shopfront is a Facebook page and its
 * checkout is a phone call -- so it gets Call and WhatsApp instead. Offering a
 * "Visit" link we cannot honour would be worse than offering a number that
 * actually rings.
 */

function ContactLinks({ row, productId }) {
  const { t } = useLocale();
  const links = [];

  // Count the tap, then get out of the way.
  //
  // There is no checkout here, so this is the LAST thing the platform can
  // observe before the conversation moves to a phone. It is what lets a shop
  // be told "47 people asked for your number last month" instead of being
  // asked to take the platform's word for its value.
  //
  // Deliberately NOT awaited and never allowed to throw: the visitor is
  // leaving for their dialler and must not wait on an analytics write, and a
  // lost row is worth far less than an interrupted purchase.
  const tap = (channel) => {
    recordContactTap(row.store_id, productId, channel);
  };

  if (row.whatsapp) {
    // wa.me wants the international form without a plus or leading zero.
    const international = `962${row.whatsapp.replace(/^0/, '')}`;
    links.push(
      <a
        key="whatsapp"
        href={`https://wa.me/${international}`}
        onClick={() => tap('whatsapp')}
        target="_blank"
        rel="noopener noreferrer"
        className={`${TAP_TARGET} bg-green-600 text-white hover:bg-green-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-green-500`}
      >
        WhatsApp
      </a>,
    );
  }

  if (row.phone) {
    links.push(
      <a
        key="phone"
        href={`tel:${row.phone}`}
        onClick={() => tap('call')}
        className={`${TAP_TARGET} border border-gray-300 text-gray-700 hover:bg-gray-50 focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-500 dark:border-gray-700 dark:text-gray-300 dark:hover:bg-gray-800`}
      >
        {row.phone}
      </a>,
    );
  }

  // Instagram sits alongside Facebook, not instead of it: a shop may have
  // either or both, and for many of these shops Instagram IS the shopfront.
  // Both are last-resort links -- a number that rings beats a profile to
  // browse, so they only appear when there is no phone or WhatsApp.
  if (!links.length && row.instagram_url) {
    links.push(
      <a
        key="instagram"
        href={row.instagram_url}
        onClick={() => tap('instagram')}
        target="_blank"
        rel="noopener noreferrer"
        className={`${TAP_TARGET} border border-gray-300 text-brand-600 hover:bg-gray-50 dark:border-gray-700 dark:text-brand-400 dark:hover:bg-gray-800`}
      >
        Instagram
      </a>,
    );
  }

  if (!links.length && row.facebook_url) {
    links.push(
      <a
        key="facebook"
        href={row.facebook_url}
        onClick={() => tap('facebook')}
        target="_blank"
        rel="noopener noreferrer"
        className={`${TAP_TARGET} border border-gray-300 text-brand-600 hover:bg-gray-50 dark:border-gray-700 dark:text-brand-400 dark:hover:bg-gray-800`}
      >
        {t('common.facebookPage')}
      </a>,
    );
  }

  if (!links.length) return <span className="text-gray-400 dark:text-gray-500">—</span>;
  return <div className="flex flex-wrap justify-end gap-1.5">{links}</div>;
}

/**
 * What a buyer would ask about a second-hand unit, before the price matters.
 *
 * Shown as facts rather than a badge: "84% battery" and "no damage reported"
 * are the two questions every used-phone conversation in Jordan starts with,
 * and burying them behind a tooltip would make the listing look like a new
 * phone that happens to be cheap.
 */
function ConditionDetails({ row }) {
  const { t } = useLocale();
  if (row.comparison_group !== 'second_hand') return null;

  return (
    <div className="mt-1 space-y-0.5 text-xs">
      <div className="flex flex-wrap items-center gap-x-2 gap-y-0.5 text-gray-600 dark:text-gray-400">
        {row.battery_health != null && (
          <span
            className={
              row.battery_health < 80 ? 'font-medium text-amber-700' : undefined
            }
          >
            {t('table.battery', { percent: row.battery_health })}
          </span>
        )}
      </div>
      {row.has_damage ? (
        <p className="text-amber-700 dark:text-amber-400">{row.damage_notes || t('table.hasDamage')}</p>
      ) : (
        row.has_damage === false && <p className="text-gray-500 dark:text-gray-400">{t('table.noDamage')}</p>
      )}
      {row.listing_notes && <p className="text-gray-500 dark:text-gray-400">{row.listing_notes}</p>}
    </div>
  );
}

export default function StorePriceTable({ prices, emptyMessage, productId }) {
  const { t } = useLocale();

  if (!prices?.length) {
    return (
      <p className="rounded-lg border border-dashed border-gray-300 dark:border-gray-700 px-4 py-8 text-center text-sm text-gray-500 dark:text-gray-400">
        {emptyMessage ?? t('product.noListings')}
      </p>
    );
  }

  const rows = [...prices].sort((a, b) => a.total_cost - b.total_cost);
  const cheapest = rows.find((row) => row.availability);

  return (
    <div className="overflow-x-auto rounded-lg border border-gray-200 dark:border-gray-800">
      <table className="min-w-full bg-white dark:bg-gray-900 text-sm">
        <thead className="bg-gray-50 dark:bg-gray-900 text-left text-gray-600 dark:text-gray-400">
          <tr>
            <th className="px-4 py-3 font-medium">{t('table.store')}</th>
            <th className="px-4 py-3 font-medium">{t('table.price')}</th>
            <th className="px-4 py-3 font-medium">{t('table.delivery')}</th>
            <th className="px-4 py-3 font-medium">{t('table.total')}</th>
            {/* Warranty is a purchase factor in its own right here -- two
                shops at the same price and different cover are not the same
                offer -- so it earns a column rather than a footnote. */}
            <th className="px-4 py-3 font-medium">{t('table.warranty')}</th>
            <th className="px-4 py-3 font-medium">{t('table.availability')}</th>
            <th className="px-4 py-3 text-end font-medium">{t('table.buy')}</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-100 dark:divide-gray-800">
          {rows.map((row) => {
            const isBest = row === cheapest;
            // A scraped price is as fresh as the last time the scraper READ
            // it, changed or not. last_updated only moves when the figure
            // changes, so a price confirmed every six hours used to read
            // "updated 19 days ago". A merchant's price is as fresh as the
            // last time the shop typed it, which is last_updated.
            const seen = row.is_merchant
              ? row.last_updated
              : (row.checked_at ?? row.last_updated);
            const age = formatAge(seen, t);
            const stale = row.is_merchant && isPriceStale(row.last_updated);

            return (
              <tr
                key={`${row.store_name}-${row.price}`}
                className={isBest ? 'bg-green-50/60 dark:bg-green-950/30' : undefined}
              >
                <td className="px-4 py-3">
                  <span className="font-medium text-gray-900 dark:text-white">{row.store_name}</span>
                  {isBest && (
                    <span className="ml-2 rounded-full bg-green-100 dark:bg-green-900/40 px-2 py-0.5 text-xs font-medium text-green-800 dark:text-green-300">
                      {t('table.bestDeal')}
                    </span>
                  )}
                  {row.is_merchant && (
                    <span
                      className="ml-2 rounded-full bg-blue-50 dark:bg-brand-900/40 px-2 py-0.5 text-xs font-medium text-blue-700 dark:text-brand-400"
                      title={t('common.priceFromShop')}
                    >
                      {t('table.localShop')}
                    </span>
                  )}
                  {age && (
                    <span
                      className={`mt-0.5 block text-xs ${
                        stale ? 'text-amber-700' : 'text-gray-400'
                      }`}
                    >
                      {stale
                        ? t('table.stalePrice', { age })
                        : t('table.updated', { age })}
                    </span>
                  )}
                  <ConditionDetails row={row} />
                </td>
                <td className="px-4 py-3 text-gray-700 dark:text-gray-300">{formatPrice(row.price)}</td>
                <td className="px-4 py-3 text-gray-500 dark:text-gray-400">
                  {row.delivery_cost > 0 ? formatPrice(row.delivery_cost) : t('table.free')}
                </td>
                <td className="px-4 py-3 font-semibold text-gray-900 dark:text-white">
                  {formatPrice(row.total_cost)}
                </td>
                <td className="px-4 py-3 text-gray-700 dark:text-gray-300">
                  {row.warranty_months > 0 ? (
                    t('table.months', { count: row.warranty_months })
                  ) : (
                    <span className="text-gray-400 dark:text-gray-500">—</span>
                  )}
                </td>
                <td className="px-4 py-3">
                  {row.availability ? (
                    <span className="text-green-700 dark:text-green-400">{t('table.inStock')}</span>
                  ) : (
                    <span className="text-gray-400 dark:text-gray-500">{t('table.outOfStock')}</span>
                  )}
                </td>
                <td className="px-4 py-3 text-right">
                  {row.is_merchant ? (
                    <ContactLinks row={row} productId={productId} />
                  ) : (
                    row.store_product_url && (
                      <a
                        href={row.store_product_url}
                        target="_blank"
                        // noreferrer/noopener stops the opened store page from
                        // reaching back into this tab via window.opener.
                        rel="noopener noreferrer"
                        className="inline-flex min-h-11 items-center justify-center rounded-md px-3 text-brand-600 hover:bg-gray-50 hover:underline dark:text-brand-400 dark:hover:bg-gray-800"
                      >
                        {t('table.visit')}
                      </a>
                    )
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
