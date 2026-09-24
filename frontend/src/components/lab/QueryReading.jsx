import { useLocale } from '../../hooks/useLocale';
import { attributeName, translateValue } from '../../utils/matchDifference';
import { isolate } from '../../utils/labText';

/**
 * The query, stage by stage, then what the engine took from it.
 *
 * Only stages that changed something are listed -- the server sends no
 * "spelling" step for a query with no typo and no "arabic" step for a Latin
 * one -- so the list is a record of what happened, not a diagram of a
 * pipeline that did nothing.
 */
function Arrow() {
  // Points along the reading direction: down on a phone, across (and
  // mirrored for Arabic) from `sm` up.
  return (
    <svg
      viewBox="0 0 24 24"
      className="h-4 w-4 shrink-0 rotate-90 text-gray-400 sm:rotate-0 rtl:sm:rotate-180 dark:text-gray-500"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      aria-hidden="true"
    >
      <path strokeLinecap="round" strokeLinejoin="round" d="M5 12h14M13 6l6 6-6 6" />
    </svg>
  );
}

export default function QueryReading({ reading }) {
  const { t } = useLocale();
  const attributes = Object.entries(reading.attributes ?? {});

  return (
    <section aria-labelledby="lab-reading" className="mt-10">
      <h2 id="lab-reading" className="text-lg font-bold text-gray-900 dark:text-white">
        {t('lab.reading.title')}
      </h2>

      <div className="mt-4 rounded-lg border border-gray-200 bg-white p-4 dark:border-gray-800 dark:bg-gray-900">
        <ol className="flex flex-col gap-2 sm:flex-row sm:flex-wrap sm:items-center">
          {reading.steps.map((step, i) => (
            <li key={step.stage} className="flex flex-col gap-2 sm:flex-row sm:items-center">
              {i > 0 && <Arrow />}
              <div className="min-w-0">
                <p className="text-xs font-medium text-gray-500 dark:text-gray-400">
                  {t(`lab.reading.stage.${step.stage}`)}
                </p>
                <p
                  dir="auto"
                  className="mt-0.5 break-words rounded bg-gray-50 px-2 py-1 font-mono text-sm text-gray-900 dark:bg-gray-800 dark:text-gray-100"
                >
                  {step.text}
                </p>
              </div>
            </li>
          ))}
        </ol>

        {Object.entries(reading.corrections ?? {}).map(([typed, corrected]) => (
          <p key={typed} className="mt-3 text-sm text-amber-700 dark:text-amber-400">
            {t('lab.reading.correction', { typed: isolate(typed), corrected: isolate(corrected) })}
          </p>
        ))}

        <div className="mt-4 border-t border-gray-200 pt-4 dark:border-gray-800">
          {reading.category ? (
            <>
              <p className="text-xs font-medium text-gray-500 dark:text-gray-400">
                {t('lab.reading.understood')}
              </p>
              <ul className="mt-2 flex flex-wrap gap-2">
                <li className="rounded bg-gray-100 px-2 py-1 text-sm font-medium text-gray-800 dark:bg-gray-800 dark:text-gray-200">
                  {t(`category.${reading.category}`)}
                </li>
                {attributes.map(([key, value]) => (
                  <li
                    key={key}
                    className="flex items-baseline gap-1.5 rounded bg-brand-50 px-2 py-1 text-sm dark:bg-brand-900/40"
                  >
                    <span className="text-xs text-brand-800 dark:text-brand-300">
                      {attributeName(key, t)}
                    </span>
                    <span dir="auto" className="font-semibold text-brand-900 dark:text-brand-200">
                      {translateValue(value, t)}
                    </span>
                  </li>
                ))}
              </ul>
            </>
          ) : (
            <p className="text-sm text-gray-700 dark:text-gray-300">{t('lab.reading.unread')}</p>
          )}
        </div>
      </div>
    </section>
  );
}
