import { useLocale } from '../../hooks/useLocale';
import { barSegments, formatScore, letterFor } from '../../utils/lab';
import { attributeName, describeDifference, translateValue } from '../../utils/matchDifference';
import { outcomeMessage } from '../../utils/labText';
import LetterBadge from './LetterBadge';
import ScoreBar from './ScoreBar';
import TierLabel from './TierLabel';

/**
 * One listing: how it was read, what it scored and why, in words.
 *
 * This card is the chart's TABLE VIEW -- every number the bar and the
 * rankings show is also written here as text, so nothing on the page is
 * readable only by colour, only by hovering, or only by eye.
 */

export default function ListingCard({ listing, index, query, similarityRank, engineRank, total }) {
  const { t, locale } = useLocale();
  const scored = listing.outcome === 'scored';
  const segments = scored ? barSegments(query.weights, listing) : [];
  const lost = segments.filter((s) => s.state === 'lost');
  const unasked = segments.filter((s) => s.state === 'unasked');
  const attributes = Object.entries(listing.attributes ?? {});

  return (
    <article
      id={`lab-listing-${index}`}
      aria-labelledby={`lab-listing-${index}-title`}
      className="scroll-mt-24 rounded-lg border border-gray-200 bg-white p-4 dark:border-gray-800 dark:bg-gray-900"
    >
      <div className="flex items-start gap-3">
        <LetterBadge letter={letterFor(index, locale)} className="mt-0.5" />
        <div className="min-w-0 flex-1">
          <h3
            id={`lab-listing-${index}-title`}
            dir="auto"
            className="break-words font-medium text-gray-900 rtl:text-right dark:text-white"
          >
            {listing.title}
          </h3>
          {listing.store_category && (
            <p className="mt-0.5 text-xs text-gray-500 dark:text-gray-400">
              {t('lab.card.storeCategory')}{' '}
              <span dir="auto" className="font-medium text-gray-700 dark:text-gray-300">
                {listing.store_category}
              </span>
            </p>
          )}
        </div>
        <div className="flex shrink-0 flex-col items-end gap-1">
          {scored && (
            <span className="text-2xl font-semibold leading-none text-gray-900 dark:text-white">
              {formatScore(listing.score)}
            </span>
          )}
          <TierLabel tier={listing.tier} />
        </div>
      </div>

      {attributes.length > 0 && (
        <p className="mt-3 flex flex-wrap items-center gap-1.5 text-xs">
          <span className="text-gray-500 dark:text-gray-400">{t('lab.card.read')}</span>
          {attributes.map(([key, value]) => (
            <span
              key={key}
              dir="auto"
              title={attributeName(key, t)}
              className="rounded bg-gray-100 px-1.5 py-0.5 font-medium text-gray-700 dark:bg-gray-800 dark:text-gray-300"
            >
              {translateValue(value, t)}
            </span>
          ))}
        </p>
      )}

      {scored ? (
        <div className="mt-3">
          <ScoreBar
            segments={segments}
            label={t('lab.bar.label', { score: formatScore(listing.score) })}
          />
          <ul className="mt-2 space-y-0.5 text-sm">
            {lost.map((segment) => (
              <li key={segment.attribute} className="text-gray-800 dark:text-gray-200">
                <span className="me-1.5 font-semibold tabular-nums text-red-700 dark:text-red-400">
                  −{segment.weight}
                </span>
                {describeDifference(segment.comparison, t)}
              </li>
            ))}
            {lost.length === 0 && (
              <li className="text-gray-700 dark:text-gray-300">{t('lab.card.allKept')}</li>
            )}
            {unasked.length > 0 && (
              <li className="text-xs text-gray-500 dark:text-gray-400">
                {t('lab.card.unasked', {
                  attributes: unasked
                    .map((s) => attributeName(s.attribute, t, s.label))
                    .join(t('lab.listSeparator')),
                })}
              </li>
            )}
          </ul>
        </div>
      ) : (
        <p className="mt-3 text-sm leading-6 text-gray-700 dark:text-gray-300">
          {outcomeMessage(listing, query, t)}
        </p>
      )}

      <p className="mt-3 border-t border-gray-100 pt-2 text-xs text-gray-500 dark:border-gray-800 dark:text-gray-400">
        {t('lab.card.ranks', {
          similarity: formatScore(listing.string_similarity),
          similarityRank,
          engineRank,
          total,
        })}
      </p>
    </article>
  );
}
