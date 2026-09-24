import { useEffect, useMemo, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { explainSearch } from '../api/lab';
import LabForm from '../components/lab/LabForm';
import ListingCard from '../components/lab/ListingCard';
import QueryReading from '../components/lab/QueryReading';
import RankComparison from '../components/lab/RankComparison';
import WeightsLegend from '../components/lab/WeightsLegend';
import { useDocumentMeta } from '../hooks/useDocumentMeta';
import { useLocale } from '../hooks/useLocale';
import {
  DEFAULT_EXAMPLE,
  EXAMPLES,
  MAX_LISTINGS,
  MIN_QUERY,
  disagreements,
  formatScore,
  headlineDisagreement,
  letterFor,
  rankings,
  requestBody,
} from '../utils/lab';
import { isolate, shortReason } from '../utils/labText';

/**
 * The Matching Lab: type a search and the names stores give things, and see
 * how this site reads and ranks them beside how string similarity would.
 *
 * WHY A PAGE FOR THIS. The site's one claim to being more than a list of
 * prices is that it knows "iPhone 11 Pro 128GB" and "iPhone 11 Pro 256GB"
 * are different phones while "Apple iPhone 11 Pro 128GB Black" and "iPhone
 * 11 Pro Black 128GB" are the same one. That was argued in a README. Here a
 * shopper, a shop owner or anyone reviewing the code can test it with their
 * own words and watch it hold -- or find where it does not, which is how the
 * "Samsung A57" / "Galaxy A57" split was found on this page's first run.
 *
 * NOTHING IS SIMULATED. Every number comes from POST /products/explain, which
 * runs the search's own code. This page only arranges the answer.
 *
 * INDEXED, unlike search results: it is one fixed page whose content is the
 * same for every visitor on arrival (the first example), with nothing from
 * the URL reaching the title or description. ?example= only picks which of
 * the fixed examples opens.
 */

let nextRowId = 0;
const toRows = (listings) =>
  listings.map((listing) => ({ id: (nextRowId += 1), title: listing.title, category: listing.category ?? '' }));

function exampleById(id) {
  return EXAMPLES.find((example) => example.id === id) ?? null;
}

export default function Lab() {
  const { t, locale } = useLocale();
  const [searchParams, setSearchParams] = useSearchParams();
  const opening = exampleById(searchParams.get('example')) ?? exampleById(DEFAULT_EXAMPLE);

  const [activeExample, setActiveExample] = useState(opening.id);
  const [query, setQuery] = useState(opening.query);
  const [rows, setRows] = useState(() => toRows(opening.listings));
  const [dirty, setDirty] = useState(false);
  const [result, setResult] = useState(null);
  // True from the start: the opening example is sent the moment the page mounts.
  const [busy, setBusy] = useState(true);
  // A translation key and its values, not a sentence: the sentence is
  // written at render time, so an error re-reads in the other language when
  // the visitor switches.
  const [error, setError] = useState(null);
  // WHAT TO EXPLAIN IS STATE, AND ONE EFFECT FETCHES IT. The opening example
  // explains itself on arrival -- a lab that opens on an empty form asks for
  // work before showing anything -- and an example or the Explain button just
  // replaces this. Each change aborts the request before it in the effect's
  // cleanup, so a slow answer can never land on top of a newer one.
  //
  // This replaced a "send once" ref guard plus a separate abort-on-unmount
  // effect, which showed a BLANK PAGE in development: StrictMode mounts,
  // rehearses an unmount (the abort fired) and mounts again (the guard said
  // "already sent"). Found by running `npm run dev`, not by a test -- see
  // the StrictMode test in Lab.test.jsx, which renders it as main.jsx does.
  const [requested, setRequested] = useState(() => requestBody(opening.query, opening.listings));

  useDocumentMeta({ title: t('lab.metaTitle'), description: t('lab.lead') });

  useEffect(() => {
    const controller = new AbortController();
    const load = async () => {
      try {
        const data = await explainSearch(requested, { signal: controller.signal });
        setResult(data);
        setDirty(false);
        setError(null);
      } catch (err) {
        if (controller.signal.aborted) return;
        setError({ key: err?.code === 'ERR_NETWORK' ? 'common.networkError' : 'lab.error' });
      } finally {
        // A request replaced by a newer one leaves the page busy for it.
        if (!controller.signal.aborted) setBusy(false);
      }
    };
    load();
    return () => controller.abort();
  }, [requested]);

  const start = (body) => {
    setBusy(true);
    setError(null);
    setRequested(body);
  };

  const chooseExample = (example) => {
    setActiveExample(example.id);
    setQuery(example.query);
    setRows(toRows(example.listings));
    setSearchParams(example.id === DEFAULT_EXAMPLE ? {} : { example: example.id }, { replace: true });
    start(requestBody(example.query, toRows(example.listings)));
  };

  const edited = () => {
    setDirty(true);
    setActiveExample(null);
  };

  const submit = () => {
    const body = requestBody(query, rows);
    if (body.query.length < MIN_QUERY) {
      setError({ key: 'lab.form.tooShort', vars: { min: MIN_QUERY } });
      return;
    }
    if (body.listings.length === 0) {
      setError({ key: 'lab.form.noListings' });
      return;
    }
    if (activeExample === null) setSearchParams({}, { replace: true });
    start(body);
  };

  const view = useMemo(() => {
    if (!result) return null;
    const { listings } = result;
    const order = rankings(listings);
    const headline = headlineDisagreement(listings);
    const pairs = disagreements(listings);

    let sentence = t('lab.rank.agree');
    if (headline) {
      const better = listings[headline.better];
      const worse = listings[headline.worse];
      // Four wordings, because two facts change the sentence: a tie is not
      // "above" (string similarity simply cannot separate the two), and a
      // listing the engine never scored has no score to quote.
      const tie = worse.string_similarity === better.string_similarity;
      const unscored = worse.outcome !== 'scored';
      const key = `lab.rank.headline${tie ? 'Tie' : ''}${unscored ? 'Unscored' : ''}`;
      sentence = t(key, {
        worseLetter: letterFor(headline.worse, locale),
        worse: isolate(worse.title),
        betterLetter: letterFor(headline.better, locale),
        better: isolate(better.title),
        worseSimilarity: formatScore(worse.string_similarity),
        betterSimilarity: formatScore(better.string_similarity),
        worseScore: formatScore(worse.score),
        betterScore: formatScore(better.score),
        reason: shortReason(worse, t),
      });
    }
    return { listings, order, headline, pairs, sentence };
  }, [result, t, locale]);

  const example = exampleById(activeExample);

  return (
    <div className="mx-auto max-w-5xl px-4 py-10">
      <h1 className="text-3xl font-extrabold tracking-tight text-gray-900 dark:text-white">
        {t('lab.title')}
      </h1>
      <p className="mt-3 max-w-3xl text-base leading-7 text-gray-700 dark:text-gray-300">{t('lab.lead')}</p>

      <section aria-labelledby="lab-examples" className="mt-8">
        <h2 id="lab-examples" className="text-sm font-semibold text-gray-900 dark:text-white">
          {t('lab.examples')}
        </h2>
        <div className="mt-2 flex flex-wrap gap-2">
          {EXAMPLES.map((item) => (
            <button
              key={item.id}
              type="button"
              aria-pressed={activeExample === item.id}
              onClick={() => chooseExample(item)}
              className={`min-h-11 rounded-full border px-4 text-sm font-medium transition ${
                activeExample === item.id
                  ? 'border-brand-600 bg-brand-600 text-white dark:border-brand-600 dark:bg-brand-600 dark:text-gray-950'
                  : 'border-gray-300 text-gray-700 hover:bg-gray-50 dark:border-gray-700 dark:text-gray-300 dark:hover:bg-gray-800'
              }`}
            >
              {t(`lab.example.${item.id}`)}
            </button>
          ))}
        </div>
        <p className="mt-3 min-h-12 max-w-3xl text-sm leading-6 text-gray-600 dark:text-gray-400">
          {example ? t(`lab.exampleNote.${example.id}`) : t('lab.exampleNote.custom')}
        </p>
      </section>

      <LabForm
        query={query}
        rows={rows}
        busy={busy}
        error={error && t(error.key, error.vars)}
        dirty={dirty}
        onQueryChange={(value) => {
          setQuery(value);
          edited();
        }}
        onRowChange={(id, change) => {
          setRows((current) => current.map((row) => (row.id === id ? { ...row, ...change } : row)));
          edited();
        }}
        onAddRow={() => {
          setRows((current) =>
            current.length >= MAX_LISTINGS ? current : [...current, ...toRows([{ title: '', category: '' }])],
          );
          edited();
        }}
        onRemoveRow={(id) => {
          setRows((current) => (current.length === 1 ? current : current.filter((row) => row.id !== id)));
          edited();
        }}
        onSubmit={submit}
      />

      {/* The previous answer stays on screen, dimmed, while the next one is
          fetched: swapping it for a spinner would jump the page on every
          example. */}
      {view && (
        <div aria-live="polite" aria-busy={busy} className={`transition-opacity ${busy ? 'opacity-50' : ''}`}>
          <QueryReading reading={result.query} />

          {result.query.category && (
            <RankComparison
              listings={view.listings}
              order={view.order}
              headline={view.headline}
              sentence={view.sentence}
              pairs={view.pairs}
            />
          )}

          <section aria-labelledby="lab-cards" className="mt-10">
            <h2 id="lab-cards" className="text-lg font-bold text-gray-900 dark:text-white">
              {t('lab.cards.title')}
            </h2>
            {result.query.category && (
              <WeightsLegend weights={result.query.weights} category={result.query.category} />
            )}
            <div className="mt-4 grid gap-3 lg:grid-cols-2">
              {view.listings.map((listing, index) => (
                <ListingCard
                  key={`${index}-${listing.title}`}
                  listing={listing}
                  index={index}
                  query={result.query}
                  total={view.listings.length}
                  similarityRank={view.order.similarity.indexOf(index) + 1}
                  engineRank={view.order.engine.indexOf(index) + 1}
                />
              ))}
            </div>
          </section>
        </div>
      )}

      <section className="mt-12 max-w-3xl space-y-3 border-t border-gray-200 pt-6 text-sm leading-6 text-gray-600 dark:border-gray-800 dark:text-gray-400">
        <p>{t('lab.honest')}</p>
        <p>{t('lab.similarityExplained')}</p>
        <p>
          <Link
            to="/about"
            className="inline-flex min-h-11 items-center font-medium text-brand-600 hover:underline dark:text-brand-400"
          >
            {t('lab.aboutLink')}
          </Link>
        </p>
      </section>
    </div>
  );
}
