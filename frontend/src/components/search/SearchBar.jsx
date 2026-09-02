import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useLocale } from '../../hooks/useLocale';
import SearchSuggestions from './SearchSuggestions';

// Example searches offered on the home page.
//
// These are the first thing a visitor clicks, so each MUST return results
// against the seeded catalogue -- "MacBook Air M3" sat here returning nothing,
// because the store stocks M2 and M4 and never had an M3. The smoke test
// checks all three, so a catalogue change turns that into a failed check
// rather than a dead first impression.
//
// NOT translated: they are product names, and a shopper types "iPhone 15"
// into the box in either language. Rendering them in Arabic script would
// produce a chip that does not match anything in the catalogue.
const EXAMPLES = [
  'iPhone 15 128GB Black',
  'MacBook Air M2 256GB',
  'Galaxy S24 128GB',
];

export default function SearchBar({ initialQuery = '', showExamples = false }) {
  const [query, setQuery] = useState(initialQuery);
  // Suggestions are hidden until the box is focused AND the shopper has typed
  // since the last submit, so arriving on /results does not immediately drop
  // a list over the results they just asked for.
  const [showSuggestions, setShowSuggestions] = useState(false);
  const { t } = useLocale();
  const navigate = useNavigate();

  // NOTE: this box does not sync itself to `initialQuery` with an effect.
  // Syncing state to a prop that way causes a cascading re-render; React's
  // recommended approach is to remount instead, so Results passes key={query}.

  const submit = (value) => {
    const trimmed = value.trim();
    setShowSuggestions(false);
    if (trimmed) navigate(`/results?q=${encodeURIComponent(trimmed)}`);
  };

  // A suggestion IS a product, so it goes straight to that product rather
  // than running a search that would only have to find it again.
  const pickSuggestion = (item) => {
    setQuery(item.label);
    setShowSuggestions(false);
    navigate(`/product/${item.product_id}`);
  };

  const handleSubmit = (e) => {
    e.preventDefault();
    submit(query);
  };

  return (
    <div className="w-full max-w-2xl">
      <form onSubmit={handleSubmit}>
        <div className="relative flex gap-2">
          <input
            type="text"
            value={query}
            onChange={(e) => {
              setQuery(e.target.value);
              setShowSuggestions(true);
            }}
            onFocus={() => setShowSuggestions(true)}
            onBlur={() => setShowSuggestions(false)}
            autoComplete="off"
            role="combobox"
            aria-expanded={showSuggestions}
            aria-autocomplete="list"
            placeholder={t('search.placeholder')}
            aria-label={t('search.placeholder')}
            // dir="auto" so a query typed in Arabic aligns right and one
            // typed in Latin aligns left, whichever language the UI is in --
            // product names are almost always Latin even on the Arabic site.
            dir="auto"
            className="flex-1 rounded-xl border border-gray-300 bg-white px-4 py-3 text-gray-900 shadow-sm transition placeholder:text-gray-400 focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-500 dark:border-gray-700 dark:bg-gray-900 dark:text-white dark:placeholder:text-gray-500"
          />
          <button
            type="submit"
            className="rounded-xl bg-brand-600 px-6 py-3 font-semibold text-white shadow-sm transition hover:bg-brand-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-500"
          >
            {t('search.button')}
          </button>

          {showSuggestions && (
            <div className="absolute inset-x-0 top-full">
              <SearchSuggestions
                query={query}
                onPick={pickSuggestion}
                onDismiss={() => setShowSuggestions(false)}
              />
            </div>
          )}
        </div>
      </form>

      {showExamples && (
        <div className="mt-3 flex flex-wrap items-center gap-2 text-sm">
          <span className="text-gray-400 dark:text-gray-500">
            {t('search.try')}
          </span>
          {EXAMPLES.map((example) => (
            <button
              key={example}
              type="button"
              dir="ltr"
              onClick={() => submit(example)}
              className="inline-flex min-h-11 items-center rounded-full bg-gray-100 px-4 text-gray-600 transition hover:bg-gray-200 focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-500 dark:bg-gray-800 dark:text-gray-300 dark:hover:bg-gray-700"
            >
              {example}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
