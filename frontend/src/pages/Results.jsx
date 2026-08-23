import { useEffect, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { searchProducts } from '../api/products';
import SearchBar from '../components/search/SearchBar';
import QueryInterpretation from '../components/search/QueryInterpretation';
import TierSection from '../components/search/TierSection';
import Spinner from '../components/ui/Spinner';
import { MATCH_TIERS } from '../utils/constants';

export default function Results() {
  const [searchParams] = useSearchParams();
  const query = searchParams.get('q') || '';

  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (!query) return;

    // Abort the previous request when the query changes, so a slow earlier
    // response cannot land after a newer one and overwrite it.
    const controller = new AbortController();

    const fetchResults = async () => {
      setLoading(true);
      setError(null);
      try {
        setData(await searchProducts(query, { signal: controller.signal }));
      } catch (err) {
        if (err.name === 'CanceledError' || err.code === 'ERR_CANCELED') return;
        setError(
          err.response?.data?.detail ??
            'Could not load results. Check that the backend is running.',
        );
      } finally {
        if (!controller.signal.aborted) setLoading(false);
      }
    };

    fetchResults();
    return () => controller.abort();
  }, [query]);

  const isEmpty = data && data.total === 0;

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
      {data?.total > 0 && (
        <p className="mb-4 text-sm text-gray-500">
          {data.total} {data.total === 1 ? 'product' : 'products'} found
        </p>
      )}

      {!loading && !error && <QueryInterpretation interpretation={data?.interpretation} />}

      {loading && <Spinner />}

      {error && (
        <div className="rounded-lg bg-red-50 px-4 py-3 text-sm text-red-700">
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
          />
        ))}
    </div>
  );
}
