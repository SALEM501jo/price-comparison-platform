import { describe, expect, it } from 'vitest';
import translations, { DEFAULT_LOCALE } from '../i18n/translations';
import {
  attributeName,
  describeDifference,
  translateValue,
  valueKey,
} from './matchDifference';

/**
 * The same lookup LocaleContext provides, without React.
 *
 * Reimplemented rather than imported because the context's t() is bound to a
 * provider and a component tree, and these are assertions about sentence
 * composition, not about rendering. It must degrade the SAME way -- returning
 * the key when a string is missing -- because that behaviour is exactly what
 * describeDifference reads to decide whether to fall back.
 */
const translator = (locale) => (key, vars) => {
  const text = translations[locale][key] ?? translations[DEFAULT_LOCALE][key];
  if (text === undefined) return key;
  if (!vars) return text;
  return Object.entries(vars).reduce(
    (out, [name, value]) => out.replaceAll(`{${name}}`, String(value)),
    text,
  );
};

const en = translator('en');
const ar = translator('ar');

const colour = {
  attribute: 'color',
  label: 'colour',
  query_value: 'black',
  candidate_value: 'blue',
};

describe('describeDifference', () => {
  it('names the attribute and both values', () => {
    expect(describeDifference(colour, en)).toBe(
      'different colour (blue, not black)',
    );
  });

  it('writes the sentence in Arabic, values included', () => {
    // The bug this whole change exists to fix: the sentence used to be
    // composed on the server and arrived in English whatever the reader's
    // language. Both the frame AND the colour names have to turn over.
    const sentence = describeDifference(colour, ar);
    expect(sentence).not.toMatch(/[a-zA-Z]/);
    expect(sentence).toContain('أزرق');
    expect(sentence).toContain('أسود');
  });

  it('says "not listed" when the product states nothing, in both languages', () => {
    // Not the same fact as a different colour, and it must not be phrased as
    // one: nobody knows what colour this is.
    const missing = { ...colour, candidate_value: null };
    expect(describeDifference(missing, en)).toBe('colour not listed');
    expect(describeDifference(missing, ar)).not.toMatch(/[a-zA-Z]/);
  });

  it('treats an undefined value the same as a null one', () => {
    // Pydantic sends null; a hand-built fixture or an older cached response
    // may simply omit the key. Both mean "the listing does not say".
    const missing = { attribute: 'color', label: 'colour', query_value: 'black' };
    expect(describeDifference(missing, en)).toBe('colour not listed');
  });

  it('leaves values with no translation exactly as they are', () => {
    // A capacity and a model code are written in Latin on a Jordanian shelf.
    // Translating them would invent a spelling nobody uses -- and inventing
    // one per shopper is worse than leaving the one they already read.
    const storage = {
      attribute: 'storage',
      label: 'storage',
      query_value: '128gb',
      candidate_value: '256gb',
    };
    expect(describeDifference(storage, ar)).toContain('256gb');
    expect(describeDifference(storage, ar)).toContain('128gb');
  });

  it('falls back to a generic phrasing for an attribute it does not know', () => {
    // rules.py can gain an attribute before translations.js catches up. That
    // must read awkwardly, never as a raw key on the page.
    const unknown = {
      attribute: 'battery_health',
      label: 'battery health',
      query_value: '100%',
      candidate_value: '87%',
    };
    const sentence = describeDifference(unknown, en);
    expect(sentence).toBe('different battery health (87%, not 100%)');
    expect(sentence).not.toContain('match.diff');
    expect(describeDifference(unknown, ar)).not.toContain('match.diff');
  });

  it('falls back to the attribute name when the server sends no label', () => {
    const bare = { attribute: 'mystery', query_value: 'a', candidate_value: 'b' };
    expect(describeDifference(bare, en)).toContain('mystery');
  });

  it('returns null for a malformed entry rather than rendering a key', () => {
    expect(describeDifference(null, en)).toBeNull();
    expect(describeDifference({}, en)).toBeNull();
  });
});

describe('translateValue', () => {
  it('translates a two-word value', () => {
    expect(valueKey('pro max')).toBe('match.value.pro_max');
    expect(translateValue('pro max', ar)).toBe('برو ماكس');
  });

  it('passes an unknown value through untouched', () => {
    expect(translateValue('iphone 15', ar)).toBe('iphone 15');
  });

  it('has nothing to say about a value that is not there', () => {
    expect(translateValue(null, ar)).toBeNull();
    expect(translateValue(undefined, ar)).toBeNull();
  });
});

describe('attributeName', () => {
  it('names the attribute in the reader\'s language', () => {
    expect(attributeName('color', en)).toBe('colour');
    expect(attributeName('color', ar)).toBe('اللون');
  });

  it('prefers a caller fallback over the raw machine name', () => {
    expect(attributeName('battery_health', en, 'battery health')).toBe(
      'battery health',
    );
  });

  it('never returns a raw key', () => {
    expect(attributeName('battery_health', ar)).toBe('battery_health');
    expect(attributeName('battery_health', ar)).not.toContain('match.attr');
  });

  it('covers every attribute the engine defines', () => {
    // Copied from app/matching/rules.py -- see the note on the value table.
    const ENGINE_ATTRIBUTES = [
      'brand', 'model', 'variant', 'storage', 'ram', 'color',
      'cpu', 'size', 'resolution', 'refresh', 'panel',
    ];
    for (const attribute of ENGINE_ATTRIBUTES) {
      expect(
        translations.ar[`match.attr.${attribute}`],
        `no Arabic name for ${attribute}`,
      ).toBeDefined();
      // Both sentence shapes too: an attribute can differ, or go unstated.
      for (const kind of ['different', 'missing']) {
        expect(
          translations.ar[`match.diff.${attribute}.${kind}`],
          `no Arabic "${kind}" phrasing for ${attribute}`,
        ).toBeDefined();
      }
    }
  });
});

describe('the value table tracks the engine', () => {
  /**
   * Guards the one thing that can silently rot: rules.py owns the colour and
   * variant vocabulary, this table renders it, and nothing connects them. A
   * colour added there just quietly stays English here.
   *
   * The list is copied from app/matching/rules.py. Copied, not derived --
   * the frontend cannot read Python, and a test that fails when someone adds
   * a colour is the point, not a nuisance.
   */
  const ENGINE_COLOURS = [
    'midnight green', 'space gray', 'sierra blue', 'pacific blue',
    'phantom black', 'natural titanium', 'blue titanium', 'alpine green',
    'deep purple', 'rose gold', 'sky blue', 'starlight', 'graphite',
    'midnight', 'titanium', 'lavender', 'black', 'white', 'silver',
    'gold', 'blue', 'red', 'green', 'purple', 'pink', 'yellow',
    'orange', 'gray', 'cream', 'mint', 'beige',
  ];
  const ENGINE_VARIANTS = [
    'pro max', 'pro', 'plus', 'ultra', 'mini', 'fe', 'max', 'air', 'base',
  ];

  it('says every colour and variant the engine can produce in Arabic', () => {
    const untranslated = [...ENGINE_COLOURS, ...ENGINE_VARIANTS].filter(
      (value) => translations.ar[valueKey(value)] === undefined,
    );
    expect(untranslated, 'no Arabic for these engine values').toEqual([]);
  });
});
