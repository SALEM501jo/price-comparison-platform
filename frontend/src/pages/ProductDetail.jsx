import { useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { getPriceHistory, getProduct } from '../api/products';
import PriceHistoryChart from '../components/prices/PriceHistoryChart';
import ProductActions from '../components/prices/ProductActions';
import StorePriceTable from '../components/prices/StorePriceTable';
import { formatPrice } from '../utils/format';
import { attributeName, translateValue } from '../utils/matchDifference';
import ProductImage from '../components/ui/ProductImage';
import { fillTemplate, useDocumentMeta } from '../hooks/useDocumentMeta';
import { useLocale } from '../hooks/useLocale';
import Spinner from '../components/ui/Spinner';

export default function ProductDetail() {
  const { t } = useLocale();
  const { productId } = useParams();
  const [product, setProduct] = useState(null);
  const [history, setHistory] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  // A 404 is kept apart from the error MESSAGE because it changes what a
  // crawler should do, not just what the page says. See the meta below.
  const [missing, setMissing] = useState(false);

  useEffect(() => {
    const controller = new AbortController();

    const fetchProduct = async () => {
      setLoading(true);
      setError(null);
      setMissing(false);
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
        // 422 is as permanent as 404 here: it means the id in the URL is not
        // a number at all (/product/abc), and no retry will make that page
        // exist. Treating it as an outage left it indexable under the home
        // page's title.
        const gone = [404, 422].includes(err.response?.status);
        setMissing(gone);
        setError(gone ? t('product.notFound') : t('product.loadError'));
      } finally {
        if (!controller.signal.aborted) setLoading(false);
      }
    };

    fetchProduct();
    return () => controller.abort();
  }, [productId, t]);

  // Split by comparison group. The backend already labels every offer, so the
  // grouping is applied here rather than re-derived from `condition` strings.
  //
  // Worked out ABOVE the early returns, and from a product that may not be
  // here yet, because the page title needs the price and a hook cannot sit
  // below a return.
  const offers = product?.prices ?? [];
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

  // Titled by the product only once THIS product has loaded: while the next
  // one is on its way, `product` still holds the last, and its name in the
  // tab would be a claim about a page that is no longer showing.
  //
  // The price is the NEW one, for the reason ProductActions is seeded with
  // it: a used offer in the title would advertise a sealed phone at a
  // second-hand price. Filled with fillTemplate, not t(), because the name
  // comes from a scraper or a shop owner.
  //
  // A product that is gone answers with the app and a 200 like every route,
  // so it asks for noindex itself -- otherwise a deleted product lingers in
  // search as a page saying it does not exist. Any OTHER failure stays
  // indexable: an outage is temporary, and a noindex seen during one can
  // drop a real product from the index until Google happens to come back.
  const shown = !loading && !error ? product : null;
  const vars = { name: shown?.canonical_name, price: formatPrice(cheapestNew) };
  useDocumentMeta(
    shown
      ? {
          title:
            cheapestNew === null
              ? shown.canonical_name
              : fillTemplate(t('meta.product.titleFrom'), vars),
          description: fillTemplate(
            t(cheapestNew === null ? 'meta.product.description' : 'meta.product.descriptionFrom'),
            vars,
          ),
        }
      : { title: missing ? t('common.notFound') : undefined, noindex: missing },
  );

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

  return (
    <div className="mx-auto max-w-4xl px-4 py-8">
      <Link
        to="/"
        // min-h-11 rather than inline-block: a 20px-tall back link is the
        // second most-tapped thing on this page and was the smallest.
        className="mb-2 -ms-2 inline-flex min-h-11 items-center rounded-md px-2 text-sm text-brand-600 hover:bg-gray-50 hover:underline dark:text-brand-400 dark:hover:bg-gray-800"
      >
        &larr; {t('product.back')}
      </Link>

      <header className="mb-6 flex flex-col gap-5 sm:flex-row sm:items-start">
        <ProductImage
          src={product.image_url}
          alt={product.canonical_name}
          size="hero"
          className="sm:w-56 sm:shrink-0"
        />

        <div className="min-w-0 flex-1">
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
                  // Same vocabulary as the search chips and the match
                  // explanations. These read "black" and "color" in the
                  // Arabic UI until they used it.
                  dir="auto"
                  className="rounded bg-gray-100 dark:bg-gray-800 px-2 py-0.5 text-xs text-gray-700 dark:text-gray-300"
                  title={attributeName(key, t)}
                >
                  {translateValue(value, t)}
                </span>
              ))}
          </div>
        )}

        {product.description && (
          <p className="mt-3 text-sm text-gray-600 dark:text-gray-400">{product.description}</p>
        )}
        </div>
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
