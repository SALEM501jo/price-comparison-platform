const TIER_STYLES = {
  exact: 'bg-green-100 text-green-800 ring-green-600/20',
  close: 'bg-amber-100 text-amber-800 ring-amber-600/20',
  similar: 'bg-gray-100 text-gray-700 ring-gray-500/20',
};

/**
 * The match score, colour-coded by tier.
 *
 * The number alone is not useful to a shopper -- "75%" means nothing without
 * knowing 75% of what. The colour carries the judgement (green = this is the
 * one), and the reason text next to it carries the detail.
 */
export default function MatchBadge({ tier, score }) {
  const style = TIER_STYLES[tier] ?? TIER_STYLES.similar;

  return (
    <span
      className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ring-1 ring-inset ${style}`}
      title={`Match score: ${score}%`}
    >
      {tier === 'exact' ? 'Exact match' : `${Math.round(score)}% match`}
    </span>
  );
}
