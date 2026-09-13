/**
 * Where API requests go.
 *
 * AN EXPLICIT VITE_API_URL ALWAYS WINS. Vite only exposes VITE_-prefixed
 * variables to the browser, which is deliberate -- it stops server secrets
 * being bundled into client-side JavaScript by accident.
 *
 * WITHOUT ONE, THE DEFAULT DEPENDS ON THE KIND OF BUILD, and getting this wrong
 * is invisible everywhere except a real browser:
 *
 *   - development: the API is a separate process on localhost:8000, while Vite
 *     serves the app on :5173.
 *   - production: the API serves the built app from its OWN origin (see
 *     backend/app/frontend.py), so every request is same-origin and the base
 *     is empty -- "/products/browse", not a hostname.
 *
 * THIS USED TO FALL BACK TO localhost:8000 UNCONDITIONALLY. Nothing sets
 * VITE_API_URL in the production image, so every production build shipped
 * pointing at the developer's machine: in a visitor's browser there is nothing
 * listening there, and the CSP's connect-src 'self' blocks it regardless. The
 * page frame rendered, so the site looked up -- while no product, deal, session
 * refresh or merchant photo could load. curl against the API showed everything
 * healthy the whole time; only opening the page in a browser revealed it.
 *
 * `!= null` rather than `??`-on-a-truthy check so that an explicit empty string
 * is honoured as "same origin" instead of being treated as unset.
 */
export function resolveApiBaseUrl(env) {
  if (env.VITE_API_URL != null) return env.VITE_API_URL;
  return env.PROD ? '' : 'http://localhost:8000';
}

export const API_BASE_URL = resolveApiBaseUrl(import.meta.env);

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
