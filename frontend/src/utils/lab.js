/**
 * The Matching Lab's arithmetic: examples, the two rankings, the one
 * disagreement worth leading with, and the 100-point bar.
 *
 * NOTHING HERE SCORES ANYTHING. Every number comes from POST
 * /products/explain, which runs the site's own matching code. This module
 * only arranges those numbers so a person can compare two orderings of the
 * same listings -- pure functions, so they are tested without a browser.
 */

/**
 * Worked examples, each one a claim this project makes, in listings a store
 * could plausibly publish. Titles marked (real) are copied from the live
 * feeds, as the backend tests are; the rest follow the same stores' patterns.
 *
 * `category` is the store's own product_type, read exactly as ingest reads
 * it. It is what turns the phone case away: "Mobile Case" is a case.
 */
export const EXAMPLES = [
  {
    id: 'storage',
    query: 'iPhone 11 Pro Black 128GB',
    // README.md's table and matching/scorer.py's measurement, verbatim.
    listings: [
      { title: 'Apple iPhone 11 Pro 128GB Black', category: 'Mobile' },
      { title: 'iPhone 11 Pro Black 128GB Smartphone 5G', category: 'Mobile' },
      { title: 'Apple iPhone 11 Pro 128GB Midnight Green', category: 'Mobile' },
      { title: 'Apple iPhone 11 Pro 256GB Black', category: 'Mobile' },
      { title: 'Apple iPhone 11 Pro Max 128GB Black', category: 'Mobile' },
      { title: 'Apple iPhone 12 Pro 128GB Black', category: 'Mobile' },
      { title: 'Samsung Galaxy S24 128GB Black', category: 'Mobile' },
    ],
  },
  {
    id: 'arabic',
    query: 'ايفون ١٥ ١٢٨ جيجا اسود',
    listings: [
      { title: 'Apple iPhone 15 128GB Black', category: 'iPhone 15' },
      { title: 'iPhone 15 128GB Midnight', category: 'Mobile' },
      { title: 'Apple iPhone 15 128GB Blue', category: 'iPhone 15' },
      { title: 'Apple iPhone 15 256GB Black', category: 'iPhone 15' },
      { title: 'Apple iPhone 16 128GB Black', category: 'iPhone 16' },
    ],
  },
  {
    id: 'case',
    query: 'iPhone 15 Pro',
    listings: [
      { title: 'IPHONE 15 PRO CASE', category: 'Mobile Case' },
      {
        title: 'iPhone 15 Pro Tempered Glass Screen Protector',
        category: 'Screen Protectors',
      },
      { title: 'Apple iPhone 15 Pro 256GB Natural Titanium', category: 'iPhone 15' },
      { title: 'Apple iPhone 15 Pro Max 256GB Natural Titanium', category: 'iPhone 15' },
    ],
  },
  {
    id: 'plus',
    query: 'Redmi Note 15 Pro+ 5G',
    listings: [
      // (real) AmmanCart: no brand at all.
      { title: 'Redmi Note 15 Pro+ 5G', category: 'Smart Phones' },
      {
        title: 'Xiaomi Redmi Note 15 Pro 5G, 8GB & 256GB, 6.67Inch, Black',
        category: 'Smart Phone',
      },
      {
        title: 'Xiaomi Redmi Note 15 Pro+ 5G, 12GB & 512GB, Midnight Black',
        category: 'Smart Phone',
      },
      { title: 'Xiaomi Redmi Note 15 5G, 8GB & 256GB', category: 'Smart Phone' },
    ],
  },
  {
    id: 'samsung',
    // A typo, and the spelling of "Samsung S24" the parser used to split
    // from "Galaxy S24" (tests/test_samsung_models.py).
    query: 'smasung s24 ultra 256gb',
    listings: [
      { title: 'Samsung Galaxy S24 Ultra 256GB Titanium Gray', category: 'Mobile' },
      { title: 'Samsung S24 Ultra 5G, 12GB & 256GB, Titanium Black', category: 'Smart Phone' },
      { title: 'Samsung Galaxy S23 Ultra 256GB Phantom Black', category: 'Mobile' },
      { title: 'Samsung Galaxy S24 256GB Onyx Black', category: 'Mobile' },
      { title: 'Samsung Galaxy S24 Ultra Silicone Case', category: 'Mobile Case' },
    ],
  },
  {
    id: 'laptop',
    query: 'MacBook Air M3 16GB 512GB',
    listings: [
      { title: 'Apple MacBook Air 13 M3 chip 16GB RAM 512GB SSD Midnight', category: 'Notebook' },
      { title: 'Apple MacBook Air 13 M2 16GB 512GB Midnight', category: 'Notebook' },
      { title: 'Apple MacBook Pro 14 M3 16GB 512GB Space Gray', category: 'Notebook' },
      { title: 'Apple MacBook Air 15 M3 16GB 256GB Starlight', category: 'Notebook' },
      { title: 'Apple MacBook Air M3 Laptop Sleeve 13 inch', category: 'Laptop Bags' },
    ],
  },
  {
    id: 'monitor',
    query: 'Samsung 27 inch 4K 144Hz monitor',
    listings: [
      { title: 'Samsung Odyssey G7 27" UHD 4K 144Hz IPS Gaming Monitor', category: 'Gaming Monitor' },
      { title: 'Samsung Odyssey G5 27" QHD 144Hz VA Gaming Monitor', category: 'Gaming Monitor' },
      { title: 'Samsung 32" UHD 4K 60Hz VA Monitor', category: 'Monitor' },
      { title: 'LG UltraGear 27" 4K 144Hz IPS Monitor', category: 'Gaming Monitor' },
    ],
  },
];

export const DEFAULT_EXAMPLE = EXAMPLES[0].id;

/** Mirrors app/schemas/explain.py. The server enforces these; the form just stays inside them. */
export const MAX_LISTINGS = 8;
export const MAX_TITLE = 200;
export const MAX_QUERY = 100;
export const MIN_QUERY = 2;
export const MAX_STORE_CATEGORY = 60;

/**
 * One short mark per listing, shared by the rankings and the cards, so a
 * listing can be followed from one to the other without reading its title
 * twice. Arabic readers get the abjad order -- أ ب ج د -- which is how
 * Arabic has always lettered a list, rather than Latin capitals.
 */
const LETTERS = {
  en: ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H'],
  ar: ['أ', 'ب', 'ج', 'د', 'هـ', 'و', 'ز', 'ح'],
};

export function letterFor(index, locale) {
  const letters = LETTERS[locale] ?? LETTERS.en;
  return letters[index] ?? String(index + 1);
}

/** The engine's number for a listing: its score if it was scored, otherwise nothing. */
export function engineValue(listing) {
  return listing.outcome === 'scored' ? listing.score : 0;
}

/**
 * Both orderings of the same listings, as arrays of indexes into `listings`.
 *
 * Ties keep the order the listings were typed in, in both columns, so a tie
 * reads as a tie -- two rows with the same number -- rather than as one
 * method preferring one of them.
 */
export function rankings(listings) {
  const indexes = listings.map((_, i) => i);
  const engine = [...indexes].sort(
    (a, b) => engineValue(listings[b]) - engineValue(listings[a]) || a - b,
  );
  const similarity = [...indexes].sort(
    (a, b) => listings[b].string_similarity - listings[a].string_similarity || a - b,
  );
  return { engine, similarity };
}

/**
 * The disagreement to lead with: a listing string similarity scores at
 * least as high as one the engine rates better.
 *
 * Preference, in order: the better listing is an exact match (the phone the
 * shopper asked for is being outranked, which is the failure that costs
 * somebody money); the engine's gap is widest; string similarity's lead is
 * widest; typed first. Returns null when the two methods agree on every
 * pair -- which happens, and the page says so rather than inventing a story.
 */
export function headlineDisagreement(listings) {
  let best = null;
  listings.forEach((better, i) => {
    listings.forEach((worse, j) => {
      const gap = engineValue(better) - engineValue(worse);
      const lead = worse.string_similarity - better.string_similarity;
      if (gap <= 0 || lead < 0) return;

      const candidate = { better: i, worse: j, exact: better.tier === 'exact', gap, lead };
      if (
        !best ||
        candidate.exact > best.exact ||
        (candidate.exact === best.exact &&
          (candidate.gap > best.gap || (candidate.gap === best.gap && candidate.lead > best.lead)))
      ) {
        best = candidate;
      }
    });
  });
  return best && { better: best.better, worse: best.worse };
}

/**
 * How many pairs of listings the two methods put in opposite order.
 *
 * A pair counts only when the engine separates them (different values) and
 * string similarity orders them the other way or cannot separate them.
 */
export function disagreements(listings) {
  let total = 0;
  let against = 0;
  for (let i = 0; i < listings.length; i += 1) {
    for (let j = i + 1; j < listings.length; j += 1) {
      const engineGap = engineValue(listings[i]) - engineValue(listings[j]);
      if (engineGap === 0) continue;
      total += 1;
      const similarityGap = listings[i].string_similarity - listings[j].string_similarity;
      if (similarityGap === 0 || Math.sign(similarityGap) !== Math.sign(engineGap)) against += 1;
    }
  }
  return { total, against };
}

/**
 * The 100-point bar for one listing: one segment per scoring attribute of
 * the query's category, in rules.py order, each as wide as its weight.
 *
 *   kept    asked for and matched -- the points stay
 *   lost    asked for and differed -- the weight is deducted
 *   unasked not in the query -- costs nothing, which is the rule that lets
 *           "iPhone 15" match every colour of one
 *
 * rules.py order rather than sorted by state, so every listing's bar has
 * the same attribute in the same place and bars can be compared by eye.
 */
export function barSegments(weights, listing) {
  const asked = new Map((listing.comparisons ?? []).map((c) => [c.attribute, c]));
  return weights
    .filter((w) => !w.gate && w.weight > 0)
    .map((w) => {
      const comparison = asked.get(w.attribute) ?? null;
      let state = 'unasked';
      if (comparison) state = comparison.matched ? 'kept' : 'lost';
      return { attribute: w.attribute, label: w.label, weight: w.weight, state, comparison };
    });
}

/** Scores print as the engine computes them: 76, 67.9 -- never 76.0, never rounded away. */
export function formatScore(value) {
  if (value === null || value === undefined) return '—';
  return Number.isInteger(value) ? String(value) : value.toFixed(1);
}

/** The request body for an example or an edited form. Blank rows are dropped, not sent. */
export function requestBody(query, listings) {
  return {
    query: query.trim(),
    listings: listings
      .filter((row) => row.title.trim())
      .map((row) => ({
        title: row.title.trim(),
        store_category: row.category?.trim() || null,
      })),
  };
}
