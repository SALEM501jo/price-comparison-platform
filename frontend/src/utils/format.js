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

/** "4 stores" / "1 store" */
export function formatStoreCount(count) {
  if (!count) return 'Not in stock';
  return `${count} ${count === 1 ? 'store' : 'stores'}`;
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
