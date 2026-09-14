import { useEffect, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { searchProducts } from '../api/products';
import SearchBar from '../components/search/SearchBar';
import SearchControls from '../components/search/SearchControls';
import QueryInterpretation from '../components/search/QueryInterpretation';
import TierSection from '../components/search/TierSection';
import Spinner from '../components/ui/Spinner';
import { extractApiError } from '../utils/errors';
import { MATCH_TIERS } from '../utils/constants';
import { fillTemplate, useDocumentMeta } from '../hooks/useDocumentMeta';
import { useLocale } from '../hooks/useLocale';

export default function Results() {
  const { t } = useLocale();
  const [searchParams, setSearchParams] = useSearchParams();
  const query = searchParams.get('q') || '';
  const sort = searchParams.get('sort') || 'price_asc';
  const page = Number(searchParams.get('page') || 1);
  // 'exact' in the URL means the shopper rejected our correction. It
  // lives in the URL so the choice survives a reload and a shared link.
  const exact = searchParams.get('exact') === '1';

  // The query is whatever the link said, so it is filled in as text rather
  // than through t() -- see fillTemplate. Trimmed, or "?q=%20" titles the tab
  // with an empty pair of quotes.
  const typed = query.trim();
  // NEVER INDEXED. The query is whatever a link says, and it lands in the
  // title, the description and the heading -- so an indexable results page
  // lets anyone publish "call 079... for cheap iPhones" as a search result
  // under this domain by posting a link. Every q/sort/page combination would
  // also be its own URL, an endless crawl of near-duplicates. Products and
  // categories reach Google through the sitemap and their own pages; links
  // on this page are still followed. Not Disallowed in robots.txt either:
  // Google has to fetch the page to see the noindex on URLs it already knows.
  useDocumentMeta(
    typed
      ? {
          title: fillTemplate(t('meta.results.title'), { query: typed }),
          description: fillTemplate(t('meta.results.description'), { query: typed }),
          noindex: true,
        }
      : { title: t('search.button'), noindex: true },
  );

  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (!query) return undefined;

    // Abort the previous request when the query or options change, so a slow
    // earlier response cannot land after a newer one and overwrite it.
    const controller = new AbortController();

    const fetchResults = async () => {
      setLoading(true);
      setError(null);
      try {
        setData(
          await searchProducts(
            query,
            { sort, page, ...(exact ? { correct: false } : {}) },
            { signal: controller.signal },
          ),
        );
      } catch (err) {
        if (err.name === 'CanceledError' || err.code === 'ERR_CANCELED') return;
        setError(extractApiError(err, t('search.loadError')));
      } finally {
        if (!controller.signal.aborted) setLoading(false);
      }
    };

    fetchResults();
    return () => controller.abort();
  }, [query, sort, page, exact, t]);

  // Options live in the URL so a result page can be bookmarked and shared,
  // and the back button steps through them.
  const updateParams = (changes) => {
    const next = new URLSearchParams(searchParams);
    Object.entries(changes).forEach(([key, value]) => {
      if (value === null || value === undefined || value === '') next.delete(key);
      else next.set(key, String(value));
    });
    setSearchParams(next);
  };

  const isEmpty = data && data.total === 0 && page === 1;

  return (
    <div className="mx-auto max-w-4xl px-4 py-8">
      <div className="mb-6">
        {/* key={query} remounts the box when the URL changes, so it
            shows the query that produced this page (back button included). */}
        <SearchBar key={query} initialQuery={query} />
      </div>

      <h1 className="mb-1 text-xl font-semibold text-gray-900 dark:text-white">
        {t('search.resultsFor', { query })}
      </h1>

      {/* A spelling correction, stated rather than applied silently.
          Answering a different question from the one asked, without saying
          so, is how somebody ends up buying the wrong phone -- so the
          corrected wording is shown, and the original stays one click away. */}
      {!loading && !error && data?.interpretation?.corrected_query && (
        <p className="mb-3 text-sm text-gray-600 dark:text-gray-400">
          {t('search.showingFor', {
            corrected: data.interpretation.corrected_query,
          })}{' '}
          <button
            type="button"
            onClick={() => setSearchParams({ q: query, exact: '1' })}
            className="text-brand-600 hover:underline dark:text-brand-400"
          >
            {t('search.searchInstead', { original: query })}
          </button>
        </p>
      )}

      {!loading && !error && data?.total > 0 && (
        <SearchControls
          sort={sort}
          onSortChange={(value) => updateParams({ sort: value, page: 1 })}
          total={data.total}
          counts={data.counts}
        />
      )}

      {!loading && !error && <QueryInterpretation interpretation={data?.interpretation} />}

      {loading && <Spinner />}

      {error && (
        <div role="alert" className="rounded-lg bg-red-50 dark:bg-red-950/40 px-4 py-3 text-sm text-red-700 dark:text-red-300">
          {error}
        </div>
      )}

      {isEmpty && !loading && (
        <div className="rounded-lg border border-dashed border-gray-300 dark:border-gray-700 px-4 py-10 text-center">
          <p className="font-medium text-gray-700 dark:text-gray-300">{t('search.empty')}</p>
          <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
            {t('search.emptyHint')}
          </p>
        </div>
      )}

      {!loading &&
        !error &&
        data &&
        MATCH_TIERS.map(({ key, titleKey, blurbKey }) => (
          <TierSection
            key={key}
            title={t(titleKey)}
            blurb={t(blurbKey)}
            products={data[key]}
            total={data.counts?.[key]}
          />
        ))}

      {!loading && !error && data && (page > 1 || data.has_more) && (
        <div className="mt-6 flex items-center justify-between border-t border-gray-200 dark:border-gray-800 pt-4">
          <button
            onClick={() => updateParams({ page: page - 1 })}
            disabled={page <= 1}
            className="rounded-lg border border-gray-300 dark:border-gray-700 px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-300 hover:bg-gray-50 disabled:opacity-40"
          >
            {t('common.previous')}
          </button>
          <span className="text-sm text-gray-500 dark:text-gray-400">
            {t('common.page', { page })}
          </span>
          <button
            onClick={() => updateParams({ page: page + 1 })}
            disabled={!data.has_more}
            className="rounded-lg border border-gray-300 dark:border-gray-700 px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-300 hover:bg-gray-50 disabled:opacity-40"
          >
            {t('common.next')}
          </button>
        </div>
      )}
    </div>
  );
}
