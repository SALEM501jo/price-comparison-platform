/**
 * Turn a structured match difference into a sentence in the reader's language.
 *
 * The server used to send this sentence ready-made: "different colour (blue,
 * not black)". That was the last English-only text in the product, and it was
 * the worst possible one to leave behind -- the explanation of WHY a result is
 * not exact is the whole reason the tiered search exists, and it was reaching
 * an Arabic-first site in English with no way for the client to intervene.
 *
 * The server now reports which attribute differed and what the two values
 * were. The sentence is composed here, where the locale is known.
 */

/**
 * Look up a string, returning null when it is genuinely absent.
 *
 * t() answers a missing key with the key itself -- deliberately, so an
 * untranslated string shows up as "match.diff.color.missing" on the page
 * instead of a blank that nobody reports. That is right for a component and
 * wrong for a lookup that wants to fall back, so this turns it back into an
 * absence. A key missing from the Arabic table alone cannot reach here: t()
 * falls back to the default locale first, and the parity test forbids it.
 */
function lookup(t, key, vars) {
  const text = t(key, vars);
  return text === key ? null : text;
}

/**
 * The translation key for an attribute value.
 *
 * The engine's values are lowercase English tokens, some of them two words
 * ("space gray", "pro max"), so the space becomes an underscore to keep keys
 * readable in the table.
 */
export function valueKey(value) {
  return `match.value.${String(value).toLowerCase().replace(/\s+/g, '_')}`;
}

/**
 * Say an attribute value in the reader's language, or leave it alone.
 *
 * Only colours and variants are translated. A model code, a brand and a
 * capacity are written in Latin on a Jordanian shelf and in the Arabic
 * listings we scrape -- "iPhone 15", "128GB" -- so translating them would be
 * inventing a spelling nobody uses. Anything with no entry falls through
 * unchanged, which is why adding a colour to rules.py cannot blank a word on
 * the page before this table catches up.
 */
export function translateValue(value, t) {
  if (value === null || value === undefined) return null;
  return lookup(t, valueKey(value)) ?? String(value);
}

/**
 * The name of an attribute on its own, for labelling a value.
 *
 * Falls back to whatever the caller has -- the server's English label, or the
 * machine name -- so an attribute new to rules.py is named clumsily rather
 * than shown as "match.attr.battery_health".
 */
export function attributeName(attribute, t, fallback) {
  if (!attribute) return fallback ?? null;
  return lookup(t, `match.attr.${attribute}`) ?? fallback ?? attribute;
}

/**
 * The full sentence for one difference.
 *
 * Two shapes, and they are different facts: a listing that states a colour we
 * did not ask for, and a listing that states no colour at all. Collapsing
 * them would tell a shopper the phone is the wrong colour when nobody knows
 * what colour it is.
 *
 * Falls back to a generic, ungendered phrasing built on the server's English
 * label if an attribute is added to rules.py before translations.js catches
 * up -- awkward rather than wrong, and never a raw key.
 */
export function describeDifference(difference, t) {
  if (!difference?.attribute) return null;

  const found = difference.candidate_value;
  const kind = found === null || found === undefined ? 'missing' : 'different';
  const vars = {
    label: difference.label ?? difference.attribute,
    wanted: translateValue(difference.query_value, t),
    found: translateValue(found, t),
  };

  return (
    lookup(t, `match.diff.${difference.attribute}.${kind}`, vars) ??
    t(`match.diff.${kind}`, vars)
  );
}
