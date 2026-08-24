import { useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { getPriceHistory, getProduct } from '../api/products';
import PriceHistoryChart from '../components/prices/PriceHistoryChart';
import ProductActions from '../components/prices/ProductActions';
import StorePriceTable from '../components/prices/StorePriceTable';
import Spinner from '../components/ui/Spinner';

export default function ProductDetail() {
  const { productId } = useParams();
  const [product, setProduct] = useState(null);
  const [history, setHistory] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    const controller = new AbortController();

    const fetchProduct = async () => {
      setLoading(true);
      setError(null);
      try {
        const [detail, priceHistory] = await Promise.all([
          getProduct(productId, { signal: controller.signal }),
          // History is supplementary: a failure here must not stop the
          // page rendering the prices, which are the point of the screen.
          getPriceHistory(productId, { signal: controller.signal }).catch(() => []),
        ]);
        setProduct(detail);
        setHistory(priceHistory);
      } catch (err) {
        if (err.name === 'CanceledError' || err.code === 'ERR_CANCELED') return;
        setError(
          err.response?.status === 404
            ? 'That product no longer exists.'
            : 'Could not load this product.',
        );
      } finally {
        if (!controller.signal.aborted) setLoading(false);
      }
    };

    fetchProduct();
    return () => controller.abort();
  }, [productId]);

  if (loading) {
    return (
      <div className="mx-auto max-w-4xl px-4 py-8">
        <Spinner />
      </div>
    );
  }

  if (error) {
    return (
      <div className="mx-auto max-w-4xl px-4 py-8">
        <div className="rounded-lg bg-red-50 px-4 py-3 text-sm text-red-700">
          {error}
        </div>
        <Link to="/" className="mt-4 inline-block text-sm text-blue-600 hover:underline">
          &larr; Back to search
        </Link>
      </div>
    );
  }

  // Prefer the structured matching attributes; `specs` is the legacy column
  // holding the old extractor's output and reads as junk ({"model_year": "15"}).
  const specs = product.attributes ?? {};

  return (
    <div className="mx-auto max-w-4xl px-4 py-8">
      <Link
        to="/"
        className="mb-4 inline-block text-sm text-blue-600 hover:underline"
      >
        &larr; Back to search
      </Link>

      <header className="mb-6">
        <h1 className="text-2xl font-semibold text-gray-900">
          {product.canonical_name}
        </h1>
        <div className="mt-1 flex flex-wrap gap-3 text-sm text-gray-500">
          {product.brand && <span className="uppercase tracking-wide">{product.brand}</span>}
          {product.category && <span>{product.category}</span>}
        </div>

        {Object.keys(specs).length > 0 && (
          <div className="mt-3 flex flex-wrap gap-2">
            {Object.entries(specs)
              .filter(([key, value]) => key !== 'brand' && !(key === 'variant' && value === 'base'))
              .map(([key, value]) => (
                <span
                  key={key}
                  className="rounded bg-gray-100 px-2 py-0.5 text-xs text-gray-700"
                  title={key}
                >
                  {value}
                </span>
              ))}
          </div>
        )}

        {product.description && (
          <p className="mt-3 text-sm text-gray-600">{product.description}</p>
        )}
      </header>

      <div className="mb-6">
        <ProductActions
          productId={product.id}
          lowestTotal={
            product.prices?.length
              ? Math.min(...product.prices.filter((p) => p.availability).map((p) => p.total_cost))
              : null
          }
        />
      </div>

      <h2 className="mb-3 text-lg font-semibold text-gray-900">
        Price comparison
      </h2>
      <StorePriceTable prices={product.prices} />

      <h2 className="mb-3 mt-8 text-lg font-semibold text-gray-900">
        Price history
      </h2>
      <PriceHistoryChart series={history} />
    </div>
  );
}
