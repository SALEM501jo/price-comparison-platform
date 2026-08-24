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

export default function Results() {
  const [searchParams, setSearchParams] = useSearchParams();
  const query = searchParams.get('q') || '';
  const sort = searchParams.get('sort') || 'price_asc';
  const page = Number(searchParams.get('page') || 1);

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
          await searchProducts(query, { sort, page }, { signal: controller.signal }),
        );
      } catch (err) {
        if (err.name === 'CanceledError' || err.code === 'ERR_CANCELED') return;
        setError(extractApiError(err, 'Could not load results.'));
      } finally {
        if (!controller.signal.aborted) setLoading(false);
      }
    };

    fetchResults();
    return () => controller.abort();
  }, [query, sort, page]);

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

      <h1 className="mb-1 text-xl font-semibold text-gray-900">
        Results for &ldquo;{query}&rdquo;
      </h1>

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
        <div role="alert" className="rounded-lg bg-red-50 px-4 py-3 text-sm text-red-700">
          {error}
        </div>
      )}

      {isEmpty && !loading && (
        <div className="rounded-lg border border-dashed border-gray-300 px-4 py-10 text-center">
          <p className="font-medium text-gray-700">No products matched.</p>
          <p className="mt-1 text-sm text-gray-500">
            Try fewer details &mdash; search &ldquo;iPhone 15&rdquo; instead of a
            full specification.
          </p>
        </div>
      )}

      {!loading &&
        !error &&
        data &&
        MATCH_TIERS.map(({ key, title, blurb }) => (
          <TierSection
            key={key}
            title={title}
            blurb={blurb}
            products={data[key]}
            total={data.counts?.[key]}
          />
        ))}

      {!loading && !error && data && (page > 1 || data.has_more) && (
        <div className="mt-6 flex items-center justify-between border-t border-gray-200 pt-4">
          <button
            onClick={() => updateParams({ page: page - 1 })}
            disabled={page <= 1}
            className="rounded-lg border border-gray-300 px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 disabled:opacity-40"
          >
            Previous
          </button>
          <span className="text-sm text-gray-500">Page {page}</span>
          <button
            onClick={() => updateParams({ page: page + 1 })}
            disabled={!data.has_more}
            className="rounded-lg border border-gray-300 px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 disabled:opacity-40"
          >
            Next
          </button>
        </div>
      )}
    </div>
  );
}
