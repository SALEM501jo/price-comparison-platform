// API base URL.
// Read from the environment so the same build can point at localhost in dev
// and a real domain in production. Vite only exposes variables prefixed with
// VITE_ to the browser, which is deliberate -- it stops server secrets being
// bundled into client-side JavaScript by accident.
export const API_BASE_URL =
  import.meta.env.VITE_API_URL ?? 'http://localhost:8000';

export const DEFAULT_CURRENCY = 'JOD';
export const ITEMS_PER_PAGE = 20;

// Match tiers returned by GET /products/search, in display order.
// Kept here so the labels live in one place rather than being retyped in
// every component that renders a tier.
// Translation KEYS, not English text. The wording lives in
// src/i18n/translations.js so the tiers read correctly in both languages;
// keeping copies here would guarantee the two drift apart.
export const MATCH_TIERS = [
  { key: 'exact', titleKey: 'tier.exact', blurbKey: 'tier.exact.blurb' },
  { key: 'close', titleKey: 'tier.close', blurbKey: 'tier.close.blurb' },
  { key: 'similar', titleKey: 'tier.similar', blurbKey: 'tier.similar.blurb' },
];
