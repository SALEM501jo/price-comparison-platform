import { useEffect, useState } from 'react';
import { useLocation } from 'react-router-dom';
import SearchBar from '../components/search/SearchBar';
import DealsGrid from '../components/search/DealsGrid';
import CatalogueGrid, { CategoryTiles } from '../components/search/CatalogueGrid';
import { browseCatalogue, getDeals } from '../api/products';
import { useDocumentMeta } from '../hooks/useDocumentMeta';
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
  // No title of its own: the home page IS the site, so it wears the site
  // title. Called anyway, because in English that title is not the Arabic
  // one index.html was served with.
  useDocumentMeta();
  // Set by the account page on its way out. The confirmation cannot be shown
  // where the deletion happened: that page is behind RequireAuth and unmounts
  // with the session it just ended, and a user who is silently signed out
  // cannot tell a success from a crash.
  const { state } = useLocation();
  const [deals, setDeals] = useState([]);
  const [dealsLoading, setDealsLoading] = useState(true);
  const [catalogue, setCatalogue] = useState({ categories: [], products: [] });
  const [browseLoading, setBrowseLoading] = useState(true);
  // The browse strip pages in place rather than sending someone away: a
  // visitor who is still deciding what they want has not chosen a category
  // yet, so "show me more of everything" is the useful next step.
  const [browsePage, setBrowsePage] = useState(1);
  const [browseMore, setBrowseMore] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  // A per-visit seed for the catalogue strip, so it is a different sample of
  // the stock every time the page is opened or refreshed rather than the same
  // twelve cheapest products. Fixed for the life of THIS mount, so "show more"
  // pages through one consistent shuffle instead of re-rolling it. A fresh
  // visit remounts Home and draws a new seed.
  const [browseSeed] = useState(() => Math.floor(Math.random() * 2_000_000_000));

  useEffect(() => {
    const controller = new AbortController();

    // Both requests are fired together and settled together. Promise.all
    // would let one failure discard the other's result, and these are two
    // independent things to show.
    const load = async () => {
      const [dealsResult, browseResult] = await Promise.allSettled([
        getDeals(8, { signal: controller.signal }),
        browseCatalogue({ limit: 12, seed: browseSeed }, { signal: controller.signal }),
      ]);

      if (controller.signal.aborted) return;

      // Both sections are decoration in the strict sense: a failure here must
      // never stop someone searching.
      setDeals(dealsResult.status === 'fulfilled' ? dealsResult.value : []);
      const browsed =
        browseResult.status === 'fulfilled'
          ? browseResult.value
          : { categories: [], products: [] };
      setCatalogue(browsed);
      setBrowseMore(Boolean(browsed.has_more));
      setDealsLoading(false);
      setBrowseLoading(false);
    };

    load();
    return () => controller.abort();
    // browseSeed is drawn once per mount and never changes, so this still
    // runs exactly once -- it is listed only to satisfy the exhaustive-deps
    // rule.
  }, [browseSeed]);

  const showMore = async () => {
    const next = browsePage + 1;
    setLoadingMore(true);
    try {
      const more = await browseCatalogue({ limit: 12, page: next, seed: browseSeed });
      setCatalogue((current) => ({
        ...current,
        products: [...current.products, ...more.products],
      }));
      setBrowseMore(Boolean(more.has_more));
      setBrowsePage(next);
    } catch {
      // Same rule as the initial load: this section is decoration, and a
      // failure here must never break the page somebody came here to search
      // from. The button simply stops offering more.
      setBrowseMore(false);
    } finally {
      setLoadingMore(false);
    }
  };

  const hasDeals = dealsLoading || deals.length > 0;

  return (
    <div className="mx-auto max-w-6xl px-4 pb-16">
      {state?.accountDeleted && (
        <div
          role="status"
          className="mt-6 rounded-lg bg-brand-50 px-4 py-3 dark:bg-brand-900/30"
        >
          <p className="text-sm font-semibold text-brand-900 dark:text-brand-200">
            {t('account.deleted.title')}
          </p>
          <p className="mt-1 text-sm text-brand-900 dark:text-brand-200">
            {t('account.deleted.blurb')}
          </p>
        </div>
      )}

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

          {browseMore && (
            <div className="mt-8 flex justify-center">
              <button
                type="button"
                onClick={showMore}
                disabled={loadingMore}
                className="min-h-11 rounded-lg border border-gray-300 px-5 text-sm font-medium text-gray-700 transition hover:bg-gray-50 disabled:opacity-50 dark:border-gray-700 dark:text-gray-300 dark:hover:bg-gray-800"
              >
                {loadingMore ? t('common.loading') : t('browse.showMore')}
              </button>
            </div>
          )}
        </section>
      )}
    </div>
  );
}
