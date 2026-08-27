import { DEFAULT_CURRENCY } from './constants';

/**
 * Format a price for display.
 * Returns a dash for null/undefined rather than throwing or printing "NaN" --
 * a product with nothing in stock has no price, and that is a normal state.
 */
export function formatPrice(value, currency = DEFAULT_CURRENCY) {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return '—';
  }
  return `${Number(value).toFixed(2)} ${currency}`;
}

/**
 * How long ago a price was last confirmed: "today", "3 days ago".
 *
 * Matters most for merchant prices. A scraped price is refreshed every six
 * hours by a machine; a merchant price is only as fresh as the last time a
 * shop owner typed it, and a stale price on a comparison site is a lie. The
 * age is shown so a shopper can judge it rather than assume.
 */
export function formatAge(timestamp, t) {
  if (!timestamp) return null;
  const then = new Date(timestamp);
  if (Number.isNaN(then.getTime())) return null;

  // Takes the translator rather than importing it: this is a pure function in
  // a utils module, and reaching into React context from here would make it
  // untestable and unusable outside a component.
  const say = t ?? ((key, vars) => (vars ? `${vars.count} ${key}` : key));

  const days = Math.floor((Date.now() - then.getTime()) / 86_400_000);
  if (days <= 0) return say('time.today'); // clock skew: "in -1 days" helps nobody
  if (days === 1) return say('time.yesterday');
  if (days < 30) return say('time.daysAgo', { count: days });
  const months = Math.floor(days / 30);
  return months === 1
    ? say('time.monthAgo')
    : say('time.monthsAgo', { count: months });
}

/** True when a price is old enough that a shopper should be warned. */
export function isPriceStale(timestamp, thresholdDays = 30) {
  if (!timestamp) return true;
  const then = new Date(timestamp);
  if (Number.isNaN(then.getTime())) return true;
  return (Date.now() - then.getTime()) / 86_400_000 > thresholdDays;
}

/** "4 stores" / "1 store", in the caller's language. */
export function formatStoreCount(count, t) {
  const say = t ?? ((key, vars) => (vars ? `${vars.count} ${key}` : key));
  if (!count) return say('common.notInStock');
  return count === 1 ? say('common.storeOne') : say('common.stores', { count });
}

/**
 * Turn the parsed query attributes into a readable summary.
 * { model: "iphone 15", storage: "128gb", color: "black" }
 *   -> "iphone 15 · 128gb · black"
 *
 * `brand` is dropped because it is already implied by the model, and
 * `variant: base` is an internal default meaning "no Pro/Max suffix" -- both
 * would be noise to a shopper.
 */
export function describeAttributes(attributes) {
  if (!attributes) return '';
  return Object.entries(attributes)
    .filter(([key, value]) => key !== 'brand' && !(key === 'variant' && value === 'base'))
    .map(([, value]) => value)
    .join(' · ');
}
