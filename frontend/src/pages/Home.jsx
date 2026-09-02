import { useEffect, useState } from 'react';
import SearchBar from '../components/search/SearchBar';
import DealsGrid from '../components/search/DealsGrid';
import CatalogueGrid, { CategoryTiles } from '../components/search/CatalogueGrid';
import { browseCatalogue, getDeals } from '../api/products';
import { useLocale } from '../hooks/useLocale';

/**
 * The landing page.
 *
 * IT USED TO BE ONE CARD. The page was a search box above the savings grid,
 * and the savings grid can only show a product carried by TWO OR MORE shops --
 * exactly one product in the real catalogue. So a site with 423 products and
 * 418 photographs rendered a single tile under a heading, which reads as
 * broken rather than as honest.
 *
 * The savings section stays exactly as strict as it was: loosening what counts
 * as a saving to fill a page would be the one genuinely dishonest thing this
 * project could do. What changed is that it is no longer asked to BE the page.
 * Underneath it now sits the catalogue itself -- real stock, real prices, real
 * photographs -- and above that, category doors for a visitor who does not yet
 * know what to type into a search box.
 *
 * The two sections are fetched independently and rendered independently: a
 * failure in either must not take the other down, and neither may stop
 * somebody searching, which is what the page is actually for.
 */
export default function Home() {
  const { t } = useLocale();
  const [deals, setDeals] = useState([]);
  const [dealsLoading, setDealsLoading] = useState(true);
  const [catalogue, setCatalogue] = useState({ categories: [], products: [] });
  const [browseLoading, setBrowseLoading] = useState(true);

  useEffect(() => {
    const controller = new AbortController();

    // Both requests are fired together and settled together. Promise.all
    // would let one failure discard the other's result, and these are two
    // independent things to show.
    const load = async () => {
      const [dealsResult, browseResult] = await Promise.allSettled([
        getDeals(8, { signal: controller.signal }),
        browseCatalogue({ limit: 12 }, { signal: controller.signal }),
      ]);

      if (controller.signal.aborted) return;

      // Both sections are decoration in the strict sense: a failure here must
      // never stop someone searching.
      setDeals(dealsResult.status === 'fulfilled' ? dealsResult.value : []);
      setCatalogue(
        browseResult.status === 'fulfilled'
          ? browseResult.value
          : { categories: [], products: [] },
      );
      setDealsLoading(false);
      setBrowseLoading(false);
    };

    load();
    return () => controller.abort();
  }, []);

  const hasDeals = dealsLoading || deals.length > 0;

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

      {/* The doors. Shown before the grids because a visitor who knows they
          want a laptop should not have to scroll past twelve phones. */}
      {catalogue.categories?.length > 0 && (
        <section className="mb-10">
          <CategoryTiles categories={catalogue.categories} />
        </section>
      )}

      {hasDeals && (
        <section className="mb-10">
          <div className="mb-4 flex flex-wrap items-baseline justify-between gap-3">
            <h2 className="text-lg font-bold text-gray-900 dark:text-white">
              {t('home.deals')}
            </h2>
            <p className="text-sm text-gray-500 dark:text-gray-400">
              {t('home.dealsHint')}
            </p>
          </div>
          <DealsGrid deals={deals} loading={dealsLoading} />
        </section>
      )}

      {(browseLoading || catalogue.products?.length > 0) && (
        <section>
          <div className="mb-4 flex flex-wrap items-baseline justify-between gap-3">
            <h2 className="text-lg font-bold text-gray-900 dark:text-white">
              {t('browse.title')}
            </h2>
            <p className="text-sm text-gray-500 dark:text-gray-400">
              {t('browse.hint')}
            </p>
          </div>
          <CatalogueGrid
            products={catalogue.products}
            loading={browseLoading}
          />
        </section>
      )}
    </div>
  );
}
