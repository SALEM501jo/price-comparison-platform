import { describeDifference } from './matchDifference';

/**
 * Wrap text that goes INSIDE a sentence in Unicode directional isolates.
 *
 * A Latin product name in an Arabic sentence is laid out by the bidi
 * algorithm together with whatever neutral characters surround it, so
 * "«Apple iPhone 15 Pro 256GB Natural Titanium»: 83.9" came out with the
 * closing guillemet after the number -- measured in the browser at 375px.
 * FSI...PDI makes the inserted text one unit whose direction is decided by
 * its own first strong character, which is exactly the "dir=auto" the rest
 * of the site uses on elements, applied to a run of text instead.
 */
export const isolate = (text) => `\u2068${text}\u2069`;

/**
 * The Lab's sentences about a listing, composed in the reader's language
 * from the facts the server sends -- the same division of labour as
 * matchDifference.js: the engine reports which attribute and which values,
 * the client writes the words.
 */

/** The gate comparison in the shape describeDifference reads. */
function gateDifference(listing) {
  const { gate } = listing;
  return (
    gate && {
      attribute: gate.attribute,
      label: gate.label,
      query_value: gate.query_value,
      candidate_value: gate.candidate_value,
    }
  );
}

/** The full sentence for a listing the engine did not score. */
export function outcomeMessage(listing, query, t) {
  switch (listing.outcome) {
    case 'gated':
      return t('lab.outcome.gated', { reason: describeDifference(gateDifference(listing), t) });
    case 'refused_by_store':
      return t('lab.outcome.refused_by_store', { category: isolate(listing.store_category) });
    case 'other_category':
      return t('lab.outcome.other_category', {
        found: t(`category.${listing.category}`),
        wanted: t(`category.${query.category}`),
      });
    default:
      return t(`lab.outcome.${listing.outcome}`);
  }
}

/** Why a listing lost points or was not scored, short enough for one clause. */
export function shortReason(listing, t) {
  if (listing.outcome === 'scored') {
    return listing.comparisons
      .filter((c) => !c.matched)
      .map((c) => describeDifference(c, t))
      .join(t('lab.listSeparator'));
  }
  if (listing.outcome === 'gated') return describeDifference(gateDifference(listing), t);
  if (listing.outcome === 'refused_by_store') {
    return t('lab.reason.refused_by_store', { category: isolate(listing.store_category) });
  }
  return t(`lab.reason.${listing.outcome}`);
}
