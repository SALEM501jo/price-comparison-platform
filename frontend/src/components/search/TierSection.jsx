import ProductResultCard from './ProductResultCard';

/**
 * One tier of results with its heading.
 * Renders nothing when the tier is empty, so the page does not show three
 * headings with two of them blank.
 */
export default function TierSection({ title, blurb, products }) {
  if (!products?.length) return null;

  return (
    <section className="mb-8">
      <div className="mb-3 flex items-baseline gap-2 border-b border-gray-200 pb-2">
        <h2 className="text-lg font-semibold text-gray-900">{title}</h2>
        <span className="text-sm text-gray-400">
          {blurb} · {products.length}
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
