import { useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { getPriceHistory, getProduct } from '../api/products';
import PriceHistoryChart from '../components/prices/PriceHistoryChart';
import ProductActions from '../components/prices/ProductActions';
import StorePriceTable from '../components/prices/StorePriceTable';
import { formatPrice } from '../utils/format';
import { useLocale } from '../hooks/useLocale';
import Spinner from '../components/ui/Spinner';

export default function ProductDetail() {
  const { t } = useLocale();
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
            ? t('product.notFound')
            : t('product.loadError'),
        );
      } finally {
        if (!controller.signal.aborted) setLoading(false);
      }
    };

    fetchProduct();
    return () => controller.abort();
  }, [productId, t]);

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
        <div className="rounded-lg bg-red-50 dark:bg-red-950/40 px-4 py-3 text-sm text-red-700 dark:text-red-300">
          {error}
        </div>
        <Link to="/" className="mt-4 inline-block text-sm text-brand-600 dark:text-brand-400 hover:underline">
          &larr; {t('product.back')}
        </Link>
      </div>
    );
  }

  // Prefer the structured matching attributes; `specs` is the legacy column
  // holding the old extractor's output and reads as junk ({"model_year": "15"}).
  const specs = product.attributes ?? {};

  // Split by comparison group. The backend already labels every offer, so the
  // grouping is applied here rather than re-derived from `condition` strings.
  const offers = product.prices ?? [];
  const newOffers = offers.filter((o) => o.comparison_group !== 'second_hand');
  const secondHandOffers = offers.filter((o) => o.comparison_group === 'second_hand');

  const cheapestOf = (rows) => {
    const inStock = rows.filter((row) => row.availability);
    return inStock.length
      ? Math.min(...inStock.map((row) => row.total_cost))
      : null;
  };
  const cheapestNew = cheapestOf(newOffers);
  const cheapestUsed = cheapestOf(secondHandOffers);

  return (
    <div className="mx-auto max-w-4xl px-4 py-8">
      <Link
        to="/"
        className="mb-4 inline-block text-sm text-brand-600 dark:text-brand-400 hover:underline"
      >
        &larr; {t('product.back')}
      </Link>

      <header className="mb-6">
        <h1 className="text-2xl font-semibold text-gray-900 dark:text-white">
          {product.canonical_name}
        </h1>
        <div className="mt-1 flex flex-wrap gap-3 text-sm text-gray-500 dark:text-gray-400">
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
                  className="rounded bg-gray-100 dark:bg-gray-800 px-2 py-0.5 text-xs text-gray-700 dark:text-gray-300"
                  title={key}
                >
                  {value}
                </span>
              ))}
          </div>
        )}

        {product.description && (
          <p className="mt-3 text-sm text-gray-600 dark:text-gray-400">{product.description}</p>
        )}
      </header>

      <div className="mb-6">
        <ProductActions
          productId={product.id}
          // The NEW price, deliberately. Price alerts track new stock, so
          // seeding the form from a used offer would suggest a target the
          // alert can never meet.
          lowestTotal={cheapestNew}
        />
      </div>

      {/* New and second-hand are compared separately, never in one list. A
          used handset at 620 sitting above a sealed one at 850 would take the
          "best deal" badge on every product that has one, which is not a
          cheaper offer -- it is a different thing. */}
      <h2 className="mb-3 text-lg font-semibold text-gray-900 dark:text-white">
        {newOffers.length > 0
          ? t('product.newFrom', { price: formatPrice(cheapestNew) })
          : t('product.new')}
      </h2>
      <StorePriceTable
        prices={newOffers}
        emptyMessage={t('product.noNewListings')}
        productId={product.id}
      />

      {secondHandOffers.length > 0 && (
        <>
          <h2 className="mb-3 mt-8 text-lg font-semibold text-gray-900 dark:text-white">
            {t('product.usedFrom', { price: formatPrice(cheapestUsed) })}
          </h2>
          <p className="mb-3 text-sm text-gray-500 dark:text-gray-400">
            {t('product.usedHint')}
          </p>
          <StorePriceTable prices={secondHandOffers} productId={product.id} />
        </>
      )}

      <h2 className="mb-3 mt-8 text-lg font-semibold text-gray-900 dark:text-white">
        {t('product.history')}
      </h2>
      <PriceHistoryChart series={history} />
    </div>
  );
}
