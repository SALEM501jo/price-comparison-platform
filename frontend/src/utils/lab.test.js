import { describe, expect, it } from 'vitest';
import {
  EXAMPLES,
  MAX_LISTINGS,
  MAX_QUERY,
  MAX_TITLE,
  barSegments,
  disagreements,
  formatScore,
  headlineDisagreement,
  letterFor,
  rankings,
  requestBody,
} from './lab';

/**
 * The fixtures are the server's real answers for the README example, copied
 * from POST /products/explain -- the numbers backend/tests/test_explain.py
 * pins -- so these tests arrange the numbers the page will actually get.
 */
const scored = (title, score, tier, similarity, comparisons = []) => ({
  title,
  outcome: 'scored',
  score,
  tier,
  string_similarity: similarity,
  comparisons,
});

const README = [
  scored('Apple iPhone 11 Pro 128GB Black', 100, 'exact', 67.9),
  scored('iPhone 11 Pro Black 128GB Smartphone 5G', 100, 'exact', 78.1),
  scored('Apple iPhone 11 Pro 128GB Midnight Green', 90, 'close', 58.5),
  scored('Apple iPhone 11 Pro 256GB Black', 76, 'similar', 67.9),
  scored('Apple iPhone 11 Pro Max 128GB Black', 72, 'similar', 70.0),
  scored('Apple iPhone 12 Pro 128GB Black', 67, 'excluded', 64.3),
  {
    title: 'Samsung Galaxy S24 128GB Black',
    outcome: 'gated',
    score: 0,
    tier: 'excluded',
    string_similarity: 36.4,
    comparisons: [],
  },
];

describe('rankings', () => {
  it('orders the same listings two ways', () => {
    const { engine, similarity } = rankings(README);
    expect(engine).toEqual([0, 1, 2, 3, 4, 5, 6]);
    expect(similarity).toEqual([1, 4, 0, 3, 5, 2, 6]);
  });

  it('keeps typed order within a tie, in both columns', () => {
    // 0 and 3 both score 67.9 by string similarity: 0 was typed first.
    const { similarity } = rankings(README);
    expect(similarity.indexOf(0)).toBeLessThan(similarity.indexOf(3));
  });

  it('puts every listing the engine did not score after every one it did', () => {
    const refused = { ...README[6], outcome: 'refused_by_store', string_similarity: 99 };
    const { engine } = rankings([refused, README[5]]);
    expect(engine).toEqual([1, 0]);
  });
});

describe('headlineDisagreement', () => {
  it('leads with the phone that was asked for being outranked', () => {
    // The Pro Max (72) scores 70.0, above the right phone (100) at 67.9 --
    // scorer.py's own example.
    expect(headlineDisagreement(README)).toEqual({ better: 0, worse: 4 });
  });

  it('prefers the widest gap when the better listing is exact in both', () => {
    const listings = [
      scored('right', 100, 'exact', 50),
      scored('a little wrong', 90, 'close', 60),
      scored('very wrong', 67, 'excluded', 55),
    ];
    expect(headlineDisagreement(listings)).toEqual({ better: 0, worse: 2 });
  });

  it('counts a tie against string similarity, since it cannot tell them apart', () => {
    const listings = [scored('128GB', 100, 'exact', 67.9), scored('256GB', 76, 'similar', 67.9)];
    expect(headlineDisagreement(listings)).toEqual({ better: 0, worse: 1 });
  });

  it('finds a case the store refused outranking the phone', () => {
    const listings = [
      { title: 'IPHONE 15 PRO CASE', outcome: 'refused_by_store', score: 0, tier: 'excluded', string_similarity: 83.9 },
      scored('Apple iPhone 15 Pro 256GB Natural Titanium', 100, 'exact', 47.3),
    ];
    expect(headlineDisagreement(listings)).toEqual({ better: 1, worse: 0 });
  });

  it('returns nothing when the two methods agree, rather than inventing a story', () => {
    const listings = [scored('a', 100, 'exact', 90), scored('b', 76, 'similar', 60)];
    expect(headlineDisagreement(listings)).toBeNull();
  });
});

describe('disagreements', () => {
  it('counts the pairs the engine separates and string similarity does not', () => {
    // 21 pairs, one tied by the engine (the two exacts): 20 separated.
    // Against, counted by hand: the right phone ties the 256GB and sits below
    // the Pro Max; Midnight Green (a close match) sits below the 256GB, the
    // Pro Max and the iPhone 12; and the Pro Max sits above the 256GB.
    const { total, against } = disagreements(README);
    expect(total).toBe(20);
    expect(against).toBe(6);
  });
});

describe('barSegments', () => {
  const PHONE_WEIGHTS = [
    { attribute: 'brand', label: 'brand', weight: 0, gate: true },
    { attribute: 'model', label: 'model', weight: 33, gate: false },
    { attribute: 'variant', label: 'variant', weight: 28, gate: false },
    { attribute: 'storage', label: 'storage', weight: 24, gate: false },
    { attribute: 'ram', label: 'memory', weight: 5, gate: false },
    { attribute: 'color', label: 'colour', weight: 10, gate: false },
  ];

  it('keeps, loses or never asks for each attribute, in rules order', () => {
    const listing = scored('Apple iPhone 11 Pro 256GB Black', 76, 'similar', 67.9, [
      { attribute: 'model', matched: true },
      { attribute: 'variant', matched: true },
      { attribute: 'storage', matched: false, query_value: '128gb', candidate_value: '256gb' },
      { attribute: 'color', matched: true },
    ]);
    expect(barSegments(PHONE_WEIGHTS, listing).map((s) => [s.attribute, s.weight, s.state])).toEqual([
      ['model', 33, 'kept'],
      ['variant', 28, 'kept'],
      ['storage', 24, 'lost'],
      ['ram', 5, 'unasked'],
      ['color', 10, 'kept'],
    ]);
  });

  it('leaves the gate out: brand decides, it does not score', () => {
    expect(barSegments(PHONE_WEIGHTS, README[0]).map((s) => s.attribute)).not.toContain('brand');
  });

  it('adds up to the whole score', () => {
    const segments = barSegments(PHONE_WEIGHTS, README[0]);
    expect(segments.reduce((sum, s) => sum + s.weight, 0)).toBe(100);
  });
});

describe('letterFor', () => {
  it('letters in the reader’s alphabet', () => {
    expect([0, 1, 2, 3].map((i) => letterFor(i, 'en'))).toEqual(['A', 'B', 'C', 'D']);
    expect([0, 1, 2, 3].map((i) => letterFor(i, 'ar'))).toEqual(['أ', 'ب', 'ج', 'د']);
  });

  it('has a letter for every listing the server accepts', () => {
    for (const locale of ['en', 'ar']) {
      const letters = Array.from({ length: MAX_LISTINGS }, (_, i) => letterFor(i, locale));
      expect(new Set(letters).size).toBe(MAX_LISTINGS);
    }
  });
});

describe('formatScore', () => {
  it('prints what the engine computed', () => {
    expect(formatScore(76)).toBe('76');
    expect(formatScore(67.9)).toBe('67.9');
    expect(formatScore(70)).toBe('70');
  });
});

describe('requestBody', () => {
  it('trims, drops blank rows, and sends a blank category as none', () => {
    expect(
      requestBody('  iPhone 15 ', [
        { title: ' iPhone 15 128GB ', category: ' Mobile ' },
        { title: '   ', category: 'Mobile' },
        { title: 'iPhone 15 Case', category: '' },
      ]),
    ).toEqual({
      query: 'iPhone 15',
      listings: [
        { title: 'iPhone 15 128GB', store_category: 'Mobile' },
        { title: 'iPhone 15 Case', store_category: null },
      ],
    });
  });
});

describe('EXAMPLES', () => {
  it('stay inside what the server accepts', () => {
    for (const example of EXAMPLES) {
      expect(example.query.length).toBeLessThanOrEqual(MAX_QUERY);
      expect(example.listings.length).toBeLessThanOrEqual(MAX_LISTINGS);
      for (const listing of example.listings) {
        expect(listing.title.length).toBeLessThanOrEqual(MAX_TITLE);
      }
    }
  });

  it('have unique ids, which the address bar uses', () => {
    const ids = EXAMPLES.map((e) => e.id);
    expect(new Set(ids).size).toBe(ids.length);
  });
});
