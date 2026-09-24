import { useState } from 'react';
import { useLocale } from '../../hooks/useLocale';
import { formatScore, letterFor } from '../../utils/lab';
import LetterBadge from './LetterBadge';

/**
 * The same listings ranked twice, with a line joining each listing's two
 * places: a slope chart. Where the lines cross, the two methods disagree.
 *
 * EMPHASIS, NOT A HUE PER TIER. Colouring every line by its tier was tried
 * first and failed validation: exact-green and close-amber are 4.3 apart for
 * a deuteranopic reader, below the floor. So every line is neutral grey and
 * only the disagreement the page leads with is coloured -- the listing that
 * should have won in brand teal, the one that beat it in red -- and both are
 * named by letter in the sentence above, which is the second channel the
 * light-mode pair needs. Hovering or focusing a row lifts its line instead.
 *
 * ROWS ARE A FIXED HEIGHT so the SVG between the columns can place each end
 * at a known y without measuring anything. The SVG stretches horizontally
 * (non-scaling strokes keep lines 2px); end dots are HTML in the rows so
 * they stay round.
 */
const ROW = 48; // px, h-12 -- also the tap-target floor

const LINE_CLASSES = {
  better: 'stroke-brand-600 dark:stroke-brand-600',
  worse: 'stroke-red-600 dark:stroke-red-500',
  neutral: 'stroke-gray-300 dark:stroke-gray-500',
  // A hovered grey line darkens rather than borrowing a hue: teal and red
  // already mean something on this chart.
  lifted: 'stroke-gray-600 dark:stroke-gray-300',
};
const DOT_CLASSES = {
  better: 'bg-brand-600 dark:bg-brand-600',
  worse: 'bg-red-600 dark:bg-red-500',
  neutral: 'bg-gray-300 dark:bg-gray-500',
};

function Row({ index, rank, listing, value, locale, side, emphasis, active, onActivate }) {
  const dim = active !== null && active !== index;
  return (
    <li style={{ height: ROW }}>
      <a
        href={`#lab-listing-${index}`}
        onMouseEnter={() => onActivate(index)}
        onMouseLeave={() => onActivate(null)}
        onFocus={() => onActivate(index)}
        onBlur={() => onActivate(null)}
        className={`relative flex h-full items-center gap-2 rounded px-1.5 text-sm transition-opacity hover:bg-gray-50 focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-500 dark:hover:bg-gray-800 ${
          dim ? 'opacity-40' : ''
        } ${active === index ? 'bg-gray-50 dark:bg-gray-800' : ''}`}
      >
        <span className="w-4 shrink-0 text-xs tabular-nums text-gray-500 dark:text-gray-400">
          {rank}
        </span>
        <LetterBadge letter={letterFor(index, locale)} />
        {/* Below `sm` a column is about 130px, and a title cut to "Appl..."
            says nothing the letter does not -- so phones get the letter
            alone and the full title waits in the card it links to. */}
        <span
          dir="auto"
          className="hidden min-w-0 flex-1 truncate text-gray-800 rtl:text-right dark:text-gray-200 sm:block"
          title={listing.title}
        >
          {listing.title}
        </span>
        <span className="flex-1 sm:hidden" />
        <span className="shrink-0 text-xs font-semibold tabular-nums text-gray-900 dark:text-white">
          {value}
        </span>
        {/* The line's end: on the edge facing the other column. */}
        <span
          aria-hidden="true"
          className={`absolute top-1/2 h-2 w-2 -translate-y-1/2 rounded-full ring-2 ring-white dark:ring-gray-900 ${
            side === 'start' ? '-end-1' : '-start-1'
          } ${DOT_CLASSES[emphasis]}`}
        />
      </a>
    </li>
  );
}

export default function RankComparison({ listings, order, headline, sentence, pairs }) {
  const { t, locale, isRtl } = useLocale();
  const [active, setActive] = useState(null);

  const emphasisOf = (index) => {
    if (headline?.better === index) return 'better';
    if (headline?.worse === index) return 'worse';
    return 'neutral';
  };

  const engineLabel = (listing) =>
    listing.outcome === 'scored' ? formatScore(listing.score) : t(`lab.short.${listing.outcome}`);

  const height = listings.length * ROW;
  // The similarity column comes first in reading order, so its edge is the
  // left in English and the right in Arabic.
  const from = isRtl ? 100 : 0;
  const to = 100 - from;

  const lines = listings.map((_, index) => {
    const y1 = order.similarity.indexOf(index) * ROW + ROW / 2;
    const y2 = order.engine.indexOf(index) * ROW + ROW / 2;
    return { index, d: `M ${from} ${y1} C 50 ${y1}, 50 ${y2}, ${to} ${y2}` };
  });
  // Emphasised lines last, so they are drawn over the grey ones.
  const drawOrder = [...lines].sort(
    (a, b) =>
      (emphasisOf(a.index) !== 'neutral') - (emphasisOf(b.index) !== 'neutral') ||
      (a.index === active) - (b.index === active),
  );

  const column = (key, indexes, valueOf, side) => (
    <ol aria-label={t(`lab.rank.${key}`)}>
      {indexes.map((index, position) => (
        <Row
          key={index}
          index={index}
          rank={position + 1}
          listing={listings[index]}
          value={valueOf(listings[index])}
          locale={locale}
          side={side}
          emphasis={emphasisOf(index)}
          active={active}
          onActivate={setActive}
        />
      ))}
    </ol>
  );

  return (
    <section aria-labelledby="lab-rankings" className="mt-10">
      <h2 id="lab-rankings" className="text-lg font-bold text-gray-900 dark:text-white">
        {t('lab.rank.title')}
      </h2>
      <p className="mt-2 max-w-3xl text-sm leading-6 text-gray-700 dark:text-gray-300">{sentence}</p>
      {pairs.total > 0 && (
        <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
          {t('lab.rank.pairs', { against: pairs.against, total: pairs.total })}
        </p>
      )}

      <div className="mt-4 rounded-lg border border-gray-200 bg-white p-3 dark:border-gray-800 dark:bg-gray-900 sm:p-4">
        <div className="grid grid-cols-[minmax(0,1fr)_2.5rem_minmax(0,1fr)] sm:grid-cols-[minmax(0,1fr)_5rem_minmax(0,1fr)]">
          <div className="pb-2 pe-1">
            <p className="text-sm font-semibold text-gray-900 dark:text-white">{t('lab.rank.similarity')}</p>
            <p className="text-xs text-gray-500 dark:text-gray-400">{t('lab.rank.similarityHint')}</p>
          </div>
          <div />
          <div className="pb-2 ps-1">
            <p className="text-sm font-semibold text-gray-900 dark:text-white">{t('lab.rank.engine')}</p>
            <p className="text-xs text-gray-500 dark:text-gray-400">{t('lab.rank.engineHint')}</p>
          </div>

          {column('similarity', order.similarity, (l) => formatScore(l.string_similarity), 'start')}

          <svg
            aria-hidden="true"
            viewBox={`0 0 100 ${height}`}
            preserveAspectRatio="none"
            className="w-full overflow-visible"
            style={{ height }}
          >
            {drawOrder.map(({ index, d }) => {
              const emphasis = emphasisOf(index);
              const lifted = active === index;
              const faded = active !== null && !lifted;
              return (
                <path
                  key={index}
                  d={d}
                  fill="none"
                  vectorEffect="non-scaling-stroke"
                  strokeLinecap="round"
                  strokeWidth={lifted ? 3 : 2}
                  className={`${LINE_CLASSES[lifted && emphasis === 'neutral' ? 'lifted' : emphasis]} transition-opacity ${
                    faded ? 'opacity-20' : ''
                  }`}
                />
              );
            })}
          </svg>

          {column('engine', order.engine, engineLabel, 'end')}
        </div>
      </div>
    </section>
  );
}

