import ProductTile from './ProductTile';

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
 *
 * THIS SECTION IS STRUCTURALLY SMALL, and that is not a bug to design around.
 * Exactly one product in the real catalogue is carried by two shops, so this
 * grid renders one card. The home page answers that by ALSO showing the
 * catalogue underneath (see Home.jsx) rather than by loosening what counts as
 * a saving. The honest fix for a short savings list is more shops.
 */
export default function DealsGrid({ deals, loading }) {
  if (loading) {
    return (
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4">
        {Array.from({ length: 4 }).map((_, i) => (
          <div
            key={i}
            className="aspect-[3/4] animate-pulse rounded-xl border border-gray-200 bg-white dark:border-gray-800 dark:bg-gray-900"
          />
        ))}
      </div>
    );
  }

  // Nothing to show is a normal state: it means no product is stocked by two
  // shops at different prices yet. Better an absent section than an empty box.
  if (!deals?.length) return null;

  return (
    <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4">
      {deals.map((deal) => (
        <ProductTile
          key={deal.id}
          product={deal}
          saving={{
            amount: deal.saving,
            percent: deal.saving_percent,
            highest: deal.highest_total_cost,
          }}
        />
      ))}
    </div>
  );
}
