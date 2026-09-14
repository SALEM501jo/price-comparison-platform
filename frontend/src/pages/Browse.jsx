import { useCallback, useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import CatalogueGrid from '../components/search/CatalogueGrid';
import Spinner from '../components/ui/Spinner';
import { browseCatalogue } from '../api/products';
import { fillTemplate, useDocumentMeta } from '../hooks/useDocumentMeta';
import { useLocale } from '../hooks/useLocale';

const PER_PAGE = 24;

const CATEGORY_LABEL = {
  phones: 'category.phones',
  laptops: 'category.laptops',
  monitors: 'category.monitors',
};

/**
 * Everything in one category.
 *
 * WHY THIS PAGE EXISTS AT ALL: the home page's category tiles used to link to
 * `/results?q=Phones`, which runs a TEXT SEARCH for the word "Phones". No
 * product is called that, so a tile advertising 151 products led to "Nothing
 * matched that search" -- and the Laptops tile was worse, returning a single
 * monitor whose title happens to contain "for Laptops".
 *
 * A category is not a query. Search answers "which products match these
 * words"; this answers "show me the ones you filed under this", which is a
 * lookup with no scoring, no tiers and nothing to interpret. Giving it its own
 * page rather than bending the results page around a query that means nothing
 * is the same split already made between search, deals and browse.
 *
 * Pages rather than loads-everything: 151 phones is 151 images.
 */
export default function Browse() {
  const { t } = useLocale();
  const { category } = useParams();

  const [products, setProducts] = useState([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [hasMore, setHasMore] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  // Reset when the category changes, or page 3 of Phones becomes page 3 of
  // Laptops and the shopper lands in the middle of a list they never scrolled.
  //
  // Adjusted DURING RENDER rather than in an effect. This is React's own
  // pattern for derived state: an effect would render the stale list first,
  // then re-render with it cleared, which is both a wasted pass and a visible
  // flash of the previous category's products.
  const [shownCategory, setShownCategory] = useState(category);
  if (shownCategory !== category) {
    setShownCategory(category);
    setPage(1);
    setProducts([]);
  }

  useEffect(() => {
    const controller = new AbortController();

    const load = async () => {
      setLoading(true);
      setError(null);
      try {
        const data = await browseCatalogue(
          { category, limit: PER_PAGE, page },
          { signal: controller.signal },
        );
        if (controller.signal.aborted) return;
        // Append rather than replace: this is a "show more" list, so the
        // shopper keeps what they have already scrolled past.
        setProducts((current) =>
          page === 1 ? data.products : [...current, ...data.products],
        );
        setTotal(data.total ?? 0);
        setHasMore(Boolean(data.has_more));
      } catch (err) {
        if (err.code === 'ERR_CANCELED' || err.name === 'CanceledError') return;
        setError(t('browse.loadError'));
      } finally {
        if (!controller.signal.aborted) setLoading(false);
      }
    };

    load();
    return () => controller.abort();
  }, [category, page, t]);

  const showMore = useCallback(() => setPage((p) => p + 1), []);

  const title = CATEGORY_LABEL[category]
    ? t(CATEGORY_LABEL[category])
    : category;

  // The heading may echo an unknown segment -- it is the visitor's own URL --
  // but the TAB AND SEARCH SNIPPET must not: /browse/<any text> answers 200,
  // so echoing it there would let a crafted link put its words in a Google
  // result under this domain. An unknown category, or a known one that turned
  // out empty, is a page with nothing on it: noindex, and the generic title.
  // The sitemap only lists categories that have products, so no real page is
  // affected. fillTemplate, not t(), for the same reason as before: the value
  // is data.
  const known = Boolean(CATEGORY_LABEL[category]);
  const empty = !loading && !error && total === 0;
  useDocumentMeta(
    known && !empty
      ? {
          title,
          description: fillTemplate(t('meta.browse.description'), { category: title }),
        }
      : { title: known ? title : t('common.notFound'), noindex: true },
  );

  return (
    <div className="mx-auto max-w-6xl px-4 pb-16 pt-8">
      <Link
        to="/"
        className="mb-2 -ms-2 inline-flex min-h-11 items-center rounded-md px-2 text-sm text-brand-600 hover:bg-gray-50 hover:underline dark:text-brand-400 dark:hover:bg-gray-800"
      >
        &larr; {t('product.back')}
      </Link>

      <div className="mb-6 flex flex-wrap items-baseline justify-between gap-3">
        <h1 className="text-2xl font-semibold text-gray-900 dark:text-white">
          {title}
        </h1>
        {total > 0 && (
          <p className="text-sm text-gray-500 tnum dark:text-gray-400">
            {t('browse.showingOf', { shown: products.length, total })}
          </p>
        )}
      </div>

      {error && (
        <div className="rounded-lg bg-red-50 px-4 py-3 text-sm text-red-700 dark:bg-red-950/40 dark:text-red-300">
          {error}
        </div>
      )}

      {/* The grid keeps its own skeletons for the FIRST page only. Paging in
          more must not blank out what is already on screen. */}
      <CatalogueGrid
        products={products}
        loading={loading && products.length === 0}
      />

      {!loading && !error && products.length === 0 && (
        <div className="rounded-lg border border-dashed border-gray-300 py-12 text-center text-sm text-gray-500 dark:border-gray-700 dark:text-gray-400">
          {t('browse.empty')}
        </div>
      )}

      {hasMore && (
        <div className="mt-8 flex justify-center">
          <button
            type="button"
            onClick={showMore}
            disabled={loading}
            className="min-h-11 rounded-lg border border-gray-300 px-5 text-sm font-medium text-gray-700 transition hover:bg-gray-50 disabled:opacity-50 dark:border-gray-700 dark:text-gray-300 dark:hover:bg-gray-800"
          >
            {loading ? <Spinner /> : t('browse.showMore')}
          </button>
        </div>
      )}
    </div>
  );
}
