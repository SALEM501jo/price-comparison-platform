import { Link } from 'react-router-dom';
import ProductTile from './ProductTile';
import { useLocale } from '../../hooks/useLocale';

/**
 * What the shop actually stocks, for someone who has not searched yet.
 *
 * WHY THIS SECTION EXISTS: the home page used to be a search box above the
 * savings grid, and the savings grid can only ever show a product carried by
 * two or more shops -- one product in the real catalogue. So a site with 423
 * products and 418 photographs rendered a single card and read as broken or
 * empty. This is the rest of the answer: real stock, real prices, real
 * pictures, with nothing claimed about it that is not true.
 *
 * The category tiles above it are the other half. A visitor who does not know
 * what to type needs a door, and "Phones · 151" is a more useful door than a
 * blank search field.
 */

// Translation keys per category. A lookup rather than interpolation, so a new
// category fails loudly at the table instead of rendering "browse.cat.tvs".
const CATEGORY_LABEL = {
  phones: 'category.phones',
  laptops: 'category.laptops',
  monitors: 'category.monitors',
};

export function CategoryTiles({ categories }) {
  const { t } = useLocale();
  if (!categories?.length) return null;

  return (
    <div className="grid grid-cols-3 gap-3">
      {categories.map(({ category, count }) => (
        <Link
          key={category}
          // A CATEGORY IS NOT A QUERY. This used to link to
          // /results?q=Phones, which runs a text search for the word
          // "Phones" -- no product is called that, so a tile advertising 151
          // products led to "Nothing matched that search", and the Laptops
          // tile returned one monitor whose title contains "for Laptops".
          to={`/browse/${category}`}
          className="flex min-h-11 flex-col items-center justify-center rounded-xl border border-gray-200 bg-white px-3 py-4 text-center transition hover:border-brand-400 hover:shadow-sm dark:border-gray-800 dark:bg-gray-900 dark:hover:border-brand-600"
        >
          <span className="text-sm font-semibold text-gray-900 dark:text-gray-100">
            {t(CATEGORY_LABEL[category] ?? category)}
          </span>
          <span className="mt-0.5 text-xs text-gray-500 tnum dark:text-gray-400">
            {t('browse.count', { count })}
          </span>
        </Link>
      ))}
    </div>
  );
}

export default function CatalogueGrid({ products, loading }) {
  if (loading) {
    return (
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4">
        {Array.from({ length: 8 }).map((_, i) => (
          <div
            key={i}
            className="aspect-[3/4] animate-pulse rounded-xl border border-gray-200 bg-white dark:border-gray-800 dark:bg-gray-900"
          />
        ))}
      </div>
    );
  }

  if (!products?.length) return null;

  return (
    <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4">
      {products.map((product) => (
        <ProductTile key={product.id} product={product} />
      ))}
    </div>
  );
}
