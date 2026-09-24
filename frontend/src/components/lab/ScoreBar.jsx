import { useLocale } from '../../hooks/useLocale';
import { attributeName, translateValue } from '../../utils/matchDifference';

/**
 * The 100 points, one segment per attribute, each as wide as its weight.
 *
 * THREE STATES THAT DO NOT DEPEND ON COLOUR. Kept points are a solid fill,
 * lost points an outline, attributes the search never asked about a faint
 * track -- so the bar reads in greyscale and for a reader who cannot tell
 * the brand teal from the red (validated: they sit in the CVD floor band in
 * light mode, which is legal only with this second channel).
 *
 * Labels only where they fit. The weight goes inside any segment of 8 points
 * or more; the attribute's name joins it from the `sm` breakpoint and only on
 * segments of 20 or more. Everything the bar shows is also written out in
 * the card beneath it, so a label that does not fit is never the only place a
 * value lives.
 */
const STATE_CLASSES = {
  kept: 'bg-brand-600 text-white dark:bg-brand-600 dark:text-gray-950',
  lost: 'bg-red-600/10 text-gray-900 ring-2 ring-inset ring-red-600 dark:bg-red-500/15 dark:text-white dark:ring-red-500',
  unasked: 'bg-gray-100 text-gray-500 dark:bg-gray-800 dark:text-gray-400',
  reference: 'bg-gray-100 text-gray-700 dark:bg-gray-800 dark:text-gray-200',
};

function segmentTitle(segment, t) {
  const name = attributeName(segment.attribute, t, segment.label);
  const { comparison } = segment;
  if (segment.state === 'reference') return `${name}: ${segment.weight}`;
  if (segment.state === 'unasked') return t('lab.bar.unaskedTitle', { name });
  if (segment.state === 'kept') {
    return t('lab.bar.keptTitle', {
      name,
      value: translateValue(comparison.query_value, t),
      weight: segment.weight,
    });
  }
  return t('lab.bar.lostTitle', {
    name,
    wanted: translateValue(comparison.query_value, t),
    found: translateValue(comparison.candidate_value, t) ?? t('lab.bar.notStated'),
    weight: segment.weight,
  });
}

export default function ScoreBar({ segments, label }) {
  const { t } = useLocale();
  const last = segments.length - 1;

  return (
    <div className="flex h-7 w-full gap-0.5" role="img" aria-label={label}>
      {segments.map((segment, i) => (
        <div
          key={segment.attribute}
          data-state={segment.state}
          title={segmentTitle(segment, t)}
          style={{ flex: `${segment.weight} ${segment.weight} 0%` }}
          className={`flex min-w-0 items-center justify-center gap-1 whitespace-nowrap text-[11px] font-semibold tabular-nums ${
            STATE_CLASSES[segment.state]
          } ${i === 0 ? 'rounded-s' : ''} ${i === last ? 'rounded-e' : ''}`}
        >
          {segment.weight >= 20 && (
            <span className="hidden font-medium sm:inline">
              {attributeName(segment.attribute, t, segment.label)}
            </span>
          )}
          {segment.weight >= 8 && (
            <span>{segment.state === 'lost' ? `−${segment.weight}` : segment.weight}</span>
          )}
        </div>
      ))}
    </div>
  );
}
