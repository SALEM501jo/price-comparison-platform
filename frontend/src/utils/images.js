import { API_BASE_URL } from './constants';

/**
 * Resolve whatever the API gave us for a product image into a loadable src.
 *
 * Two sources reach this. A scraped listing carries an ABSOLUTE url on the
 * shop's own CDN. A merchant photo is served by our own API and arrives as a
 * PATH, because the API's origin differs between a laptop and production and
 * so cannot be baked into the response.
 *
 * Lives in utils rather than beside the component because it is a pure
 * function, and exporting one from a component file breaks React fast refresh
 * -- the same rule that keeps test/render.jsx from re-exporting the testing
 * library.
 */
export function imageSrc(value) {
  if (!value) return null;
  if (/^(https?:)?\/\//i.test(value) || value.startsWith('data:')) return value;
  return `${API_BASE_URL}${value.startsWith('/') ? '' : '/'}${value}`;
}
