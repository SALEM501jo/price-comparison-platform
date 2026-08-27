import { useEffect, useState } from 'react';
import SearchBar from '../components/search/SearchBar';
import DealsGrid from '../components/search/DealsGrid';
import { getDeals } from '../api/products';
import { useLocale } from '../hooks/useLocale';

/**
 * The landing page.
 *
 * The search box used to sit alone above an empty screen, which asked the
 * visitor to already know what they wanted. The savings below give the page
 * something to say to someone just looking, and they demonstrate the product
 * rather than describing it: every card is a real gap between two real shops.
 */
export default function Home() {
  const { t } = useLocale();
  const [deals, setDeals] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const controller = new AbortController();

    const load = async () => {
      try {
        setDeals(await getDeals(8, { signal: controller.signal }));
      } catch (err) {
        if (err.code === 'ERR_CANCELED') return;
        // Deals are decoration. A failure here must never stop someone
        // searching, which is what the page is actually for.
        setDeals([]);
      } finally {
        if (!controller.signal.aborted) setLoading(false);
      }
    };

    load();
    return () => controller.abort();
  }, []);

  return (
    <div className="mx-auto max-w-6xl px-4 pb-16">
      <div className="flex flex-col items-center pt-14 pb-10">
        <h1 className="mb-3 text-center text-4xl font-extrabold tracking-tight text-gray-900 dark:text-white sm:text-5xl">
          {t('home.title')}
        </h1>
        <p className="mb-8 max-w-md text-center text-gray-500 dark:text-gray-400">
          {t('home.subtitle')}
        </p>
        <SearchBar showExamples />
      </div>

      {(loading || deals.length > 0) && (
        <section>
          <div className="mb-4 flex flex-wrap items-baseline justify-between gap-3">
            <h2 className="text-lg font-bold text-gray-900 dark:text-white">
              {t('home.deals')}
            </h2>
            <p className="text-sm text-gray-500 dark:text-gray-400">
              {t('home.dealsHint')}
            </p>
          </div>
          <DealsGrid deals={deals} loading={loading} />
        </section>
      )}
    </div>
  );
}
