import ProductResultCard from './ProductResultCard';
import { useLocale } from '../../hooks/useLocale';

/**
 * One tier of results with its heading.
 * Renders nothing when the tier is empty, so the page does not show three
 * headings with two of them blank.
 */
export default function TierSection({ title, blurb, products, total }) {
  const { t } = useLocale();
  if (!products?.length) return null;

  return (
    <section className="mb-8">
      <div className="mb-3 flex flex-wrap items-baseline gap-2 border-b border-gray-200 pb-2 dark:border-gray-800">
        <h2 className="text-lg font-bold text-gray-900 dark:text-white">{title}</h2>
        <span className="text-sm text-gray-400 dark:text-gray-500">
          {blurb} ·{' '}
          {/* "3 of 40" when the tier is paginated, plain "3" when it is not. */}
          {total && total > products.length
            ? t('search.ofTotal', { shown: products.length, total })
            : products.length}
        </span>
      </div>

      <div className="space-y-3">
        {products.map((product) => (
          <ProductResultCard key={product.id} product={product} />
        ))}
      </div>
    </section>
  );
}
