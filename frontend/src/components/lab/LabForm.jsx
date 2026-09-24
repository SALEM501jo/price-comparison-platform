import { useLocale } from '../../hooks/useLocale';
import {
  MAX_LISTINGS,
  MAX_QUERY,
  MAX_STORE_CATEGORY,
  MAX_TITLE,
  letterFor,
} from '../../utils/lab';
import LetterBadge from './LetterBadge';

/**
 * The query and the listings, editable. Controlled by the page, which owns
 * the rows because an example replaces them all at once.
 *
 * The limits are the server's (app/schemas/explain.py) so a visitor cannot
 * type something the API would refuse, and the server enforces them anyway.
 */
function RemoveIcon() {
  return (
    <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
      <path strokeLinecap="round" strokeLinejoin="round" d="M6 6l12 12M18 6L6 18" />
    </svg>
  );
}

export default function LabForm({
  query,
  rows,
  onQueryChange,
  onRowChange,
  onAddRow,
  onRemoveRow,
  onSubmit,
  busy,
  error,
  dirty,
}) {
  const { t, locale } = useLocale();

  return (
    <form
      onSubmit={(event) => {
        event.preventDefault();
        onSubmit();
      }}
      noValidate
      className="mt-6 rounded-lg border border-gray-200 bg-white p-4 dark:border-gray-800 dark:bg-gray-900 sm:p-5"
    >
      <label htmlFor="lab-query" className="block text-sm font-semibold text-gray-900 dark:text-white">
        {t('lab.form.query')}
      </label>
      <input
        id="lab-query"
        type="search"
        dir="auto"
        value={query}
        maxLength={MAX_QUERY}
        onChange={(event) => onQueryChange(event.target.value)}
        className="mt-1.5 w-full rounded-lg border border-gray-300 px-3 py-2 text-base focus:outline-none focus:ring-2 focus:ring-brand-500 dark:border-gray-700"
      />

      <fieldset className="mt-5">
        <legend className="text-sm font-semibold text-gray-900 dark:text-white">
          {t('lab.form.listings')}
        </legend>
        <p className="mt-0.5 text-xs text-gray-500 dark:text-gray-400">{t('lab.form.categoryHint')}</p>

        <ul className="mt-3 space-y-3 sm:space-y-2">
          {rows.map((row, i) => {
            const letter = letterFor(i, locale);
            return (
              <li key={row.id} className="flex items-start gap-2">
                <LetterBadge letter={letter} className="mt-2.5" />
                <div className="flex min-w-0 flex-1 flex-col gap-2 sm:flex-row">
                  <input
                    type="text"
                    dir="auto"
                    value={row.title}
                    maxLength={MAX_TITLE}
                    aria-label={t('lab.form.title', { letter })}
                    onChange={(event) => onRowChange(row.id, { title: event.target.value })}
                    className="min-w-0 flex-1 rounded-lg border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-500 dark:border-gray-700"
                  />
                  <input
                    type="text"
                    dir="auto"
                    value={row.category}
                    maxLength={MAX_STORE_CATEGORY}
                    placeholder={t('lab.form.category')}
                    aria-label={t('lab.form.categoryLabel', { letter })}
                    onChange={(event) => onRowChange(row.id, { category: event.target.value })}
                    className="rounded-lg border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-500 dark:border-gray-700 sm:w-44"
                  />
                </div>
                <button
                  type="button"
                  onClick={() => onRemoveRow(row.id)}
                  disabled={rows.length === 1}
                  aria-label={t('lab.form.remove', { letter })}
                  className="inline-flex h-11 w-11 shrink-0 items-center justify-center rounded-lg text-gray-500 transition hover:bg-gray-50 hover:text-gray-900 disabled:opacity-30 dark:text-gray-400 dark:hover:bg-gray-800 dark:hover:text-gray-100"
                >
                  <RemoveIcon />
                </button>
              </li>
            );
          })}
        </ul>

        <button
          type="button"
          onClick={onAddRow}
          disabled={rows.length >= MAX_LISTINGS}
          className="mt-3 inline-flex min-h-11 items-center rounded-lg border border-gray-300 px-4 text-sm font-medium text-gray-700 transition hover:bg-gray-50 disabled:opacity-50 dark:border-gray-700 dark:text-gray-300 dark:hover:bg-gray-800"
        >
          {rows.length >= MAX_LISTINGS
            ? t('lab.form.full', { max: MAX_LISTINGS })
            : t('lab.form.add')}
        </button>
      </fieldset>

      <div className="mt-5 flex flex-wrap items-center gap-3">
        <button
          type="submit"
          disabled={busy}
          className="min-h-11 rounded-lg bg-brand-600 px-6 font-semibold text-white transition hover:bg-brand-700 disabled:opacity-60"
        >
          {busy ? t('lab.loading') : t('lab.form.submit')}
        </button>
        {dirty && !busy && !error && (
          <span className="text-sm text-gray-500 dark:text-gray-400">{t('lab.form.dirty')}</span>
        )}
        {error && (
          <p role="alert" className="text-sm text-red-700 dark:text-red-400">
            {error}
          </p>
        )}
      </div>
    </form>
  );
}
