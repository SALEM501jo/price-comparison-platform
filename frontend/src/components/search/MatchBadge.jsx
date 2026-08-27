import { useLocale } from '../../hooks/useLocale';

// Kept in an object rather than inline so the three tiers are legible side by
// side. The mechanical dark-mode pass only rewrites className attributes, so
// these carry their dark variants explicitly.
const TIER_STYLES = {
  exact:
    'bg-green-100 text-green-800 ring-green-600/20 dark:bg-green-900/40 dark:text-green-300 dark:ring-green-500/30',
  close:
    'bg-amber-100 text-amber-800 ring-amber-600/20 dark:bg-amber-900/40 dark:text-amber-300 dark:ring-amber-500/30',
  similar:
    'bg-gray-100 text-gray-700 ring-gray-500/20 dark:bg-gray-800 dark:text-gray-300 dark:ring-gray-600/40',
};

/**
 * The match score, colour-coded by tier.
 *
 * The number alone is not useful to a shopper -- "75%" means nothing without
 * knowing 75% of what. The colour carries the judgement (green = this is the
 * one), and the reason text next to it carries the detail.
 */
export default function MatchBadge({ tier, score }) {
  const { t } = useLocale();
  const style = TIER_STYLES[tier] ?? TIER_STYLES.similar;

  return (
    <span
      className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ring-1 ring-inset ${style}`}
      // The UNROUNDED score, deliberately. The label rounds because "89.5%
      // match" is noise to a shopper, but the tooltip is where someone who
      // wants the real number goes to find it.
      title={t('tier.scoreTitle', { score })}
    >
      {tier === 'exact'
        ? t('tier.exact')
        : t('tier.matchPercent', { score: Math.round(score) })}
    </span>
  );
}
