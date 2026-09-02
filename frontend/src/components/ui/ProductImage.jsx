import { useState } from 'react';
import { imageSrc } from '../../utils/images';
import { useLocale } from '../../hooks/useLocale';

/**
 * A product picture, wherever it came from.
 *
 * Two sources, one component. A scraped listing carries an ABSOLUTE url on
 * the shop's own CDN; a merchant photo is served by our API and arrives as a
 * PATH. The server already decided which of the two a product should show, so
 * this only has to notice which kind it is holding.
 *
 * THE PLACEHOLDER IS THE POINT. 418 of 423 products have a scraped image and
 * five do not, and a shop owner being shown this site will judge it on the
 * broken one. A missing photo has to look deliberate -- a neutral tile that
 * belongs to the design -- rather than like a page that failed to load.
 *
 * The same applies to an image that 404s or is blocked after the page has
 * rendered, which is a live risk here: those CDN urls belong to somebody
 * else's server, and nothing stops one of them disappearing.
 */

const SIZES = {
  // Merchant dashboard rows and compact lists.
  thumb: 'h-14 w-14 rounded-md',
  // Search results and the deals grid.
  card: 'h-20 w-20 rounded-lg sm:h-24 sm:w-24',
  // The product page.
  hero: 'aspect-square w-full rounded-xl',
  // A grid tile. Square and full-bleed: the card rounds its own corners and
  // clips this, so the image must not round them again or the two radii
  // disagree by a pixel along every edge.
  tile: 'aspect-square w-full',
};

function Placeholder({ className, label }) {
  return (
    <div
      className={`${className} flex shrink-0 items-center justify-center border border-gray-200 bg-gray-50 text-gray-300 dark:border-gray-800 dark:bg-gray-800/60 dark:text-gray-600`}
      role="img"
      aria-label={label}
    >
      {/* Inline rather than an icon dependency, and stroke-only so it reads
          the same on both themes without a second asset. */}
      <svg
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.5"
        className="h-1/2 w-1/2"
        aria-hidden="true"
      >
        <rect x="3" y="3" width="18" height="18" rx="2" />
        <circle cx="8.5" cy="8.5" r="1.5" />
        <path d="m21 15-4.5-4.5L3 21" />
      </svg>
    </div>
  );
}

export default function ProductImage({ src, alt, size = 'card', className = '' }) {
  const { t } = useLocale();
  const resolved = imageSrc(src);

  // WHICH src failed, not whether one did. React reuses a card for whatever
  // product lands in that slot as a list re-renders, so a boolean would keep
  // showing the placeholder for the next product too. Comparing against the
  // current src resets itself with no effect and no key juggling.
  const [failedSrc, setFailedSrc] = useState(null);
  const failed = failedSrc !== null && failedSrc === resolved;

  const box = `${SIZES[size] ?? SIZES.card} ${className}`;

  if (!resolved || failed) {
    return <Placeholder className={box} label={t('product.noPhoto')} />;
  }

  return (
    <img
      src={resolved}
      alt={alt || ''}
      loading="lazy"
      decoding="async"
      // These images are mostly on shops' own CDNs. Sending our users'
      // browsing along with each request would tell every one of those shops
      // exactly which products are being looked at here, which is not ours to
      // share -- the same instinct that keeps personal data out of the tap
      // counts.
      referrerPolicy="no-referrer"
      onError={() => setFailedSrc(resolved)}
      className={`${box} shrink-0 border border-gray-200 bg-white object-contain dark:border-gray-800 dark:bg-gray-900`}
    />
  );
}
