/** @type {import('tailwindcss').Config} */

/**
 * Every colour that differs between the two themes is served through a CSS
 * custom property rather than a literal hex.
 *
 * WHY THE INDIRECTION IS NOT OPTIONAL. Dark-mode variants in this codebase are
 * inline `dark:` classes on the same elements -- `bg-white dark:bg-gray-900` --
 * and almost every rung of the gray scale is used by BOTH modes: gray-900 is
 * 56 light text uses against 38 `dark:bg-` uses, gray-400 is 36 against 86,
 * `dark:text-white` alone is 52. A literal override of `gray` would therefore
 * repaint dark mode too, which is exactly what this change must not do.
 *
 * Because `.dark` sits on <html>, redeclaring the same variables inside
 * `html.dark { }` (see index.css) restores today's byte-identical values for
 * every dark: utility. The variant does not need to know a swap happened.
 *
 * THE SYNTAX IS LOAD-BEARING: channel triplets ("248 250 252"), never hex.
 * Tailwind's <alpha-value> placeholder needs three numbers to build
 * rgb(r g b / a). Put a hex in the variable and every opacity utility in the
 * app -- bg-green-50/60, ring-gray-500/20, focus:ring-brand-500/30,
 * dark:bg-brand-900/40 -- silently renders transparent instead of erroring.
 */
const v = (name) => `rgb(var(--c-${name}) / <alpha-value>)`;

export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  // Class-based, not media-based: the toggle in the navbar has to be able to
  // override the operating system, and `media` gives the user no say.
  darkMode: 'class',
  theme: {
    extend: {
      fontFamily: {
        // Cairo carries BOTH scripts. A bilingual site that switches typeface
        // with language ends up looking like two different products, and
        // pairing an Arabic face with a Latin one well is a job in itself.
        // Cairo's Latin is good enough to carry the English side, so the
        // brand stays recognisably one thing in either language.
        sans: ['Cairo', 'system-ui', '-apple-system', 'Segoe UI', 'sans-serif'],
      },
      colors: {
        // The page plane. Its own token because `bg-gray-50` was doing three
        // different jobs -- page background, sunken fill inside a card, and
        // table-header fill -- which is what pinned the page to within 1.05:1
        // of the cards and made the whole screen one flat bright field.
        surface: v('surface'),

        // The letterbox behind product photography, pure white in both themes
        // ON PURPOSE. These are image backings, not UI surfaces: a shot
        // photographed on white against a slightly-off-white panel shows a
        // visible seam, which reads as a rendering bug rather than as depth.
        photo: '#FFFFFF',

        white: v('white'),

        gray: {
          50: v('gray-50'),
          100: v('gray-100'),
          200: v('gray-200'),
          300: v('gray-300'),
          400: v('gray-400'),
          500: v('gray-500'),
          600: v('gray-600'),
          700: v('gray-700'),
          800: v('gray-800'),
          900: v('gray-900'),
          // 950 is deliberately absent: it is the dark-mode page background
          // and has no light-mode use, so it keeps Tailwind's default.
        },

        // Deep teal rather than the default Tailwind blue: this is a site
        // about money and trust, and blue-600 is what every unstyled Tailwind
        // project looks like.
        //
        // In light mode the ramp shifts DOWN one step -- light-mode brand-600
        // is roughly the old brand-700 -- because white-on-brand-600 measured
        // 3.77:1 and failed AA on the primary button of every page. Same
        // hue, deeper end of it.
        brand: {
          50: '#ECFDF7',
          100: '#D1FAE9',
          200: '#A7F3D6',
          300: '#6EE7BC',
          400: v('brand-400'),
          500: v('brand-500'),
          600: v('brand-600'),
          700: v('brand-700'),
          800: v('brand-800'),
          900: '#064E3B',
        },

        // Status hues, only the shades this app actually paints on a light
        // surface. Spread-free because `extend` deep-merges per scale, so
        // every shade not named here keeps its Tailwind default.
        green: { 100: v('green-100'), 600: v('green-600'), 700: v('green-700') },
        red: { 50: v('red-50'), 600: v('red-600'), 700: v('red-700') },
        amber: { 50: v('amber-50'), 100: v('amber-100'), 700: v('amber-700') },

        // Chart series. A CATEGORICAL palette: these encode identity (which
        // shop), not magnitude, so the hues are assigned in a FIXED ORDER and
        // never cycled -- a shop must not change colour because a filter
        // removed the series above it.
        //
        // Selected per theme rather than flipped: the dark column is the same
        // five hues re-stepped for a dark ground, because a hue that clears
        // 3:1 on #F8FAFC does not on #111827 and vice versa.
        //
        // Validated, not eyeballed -- lightness band, chroma floor, adjacent
        // colour-vision-deficiency separation, and 3:1 against each surface.
        // The light column is the reference palette stepped DOWN until every
        // slot cleared 3:1 on our card; three of the five did not at their
        // published values.
        series: {
          1: v('series-1'),
          2: v('series-2'),
          3: v('series-3'),
          4: v('series-4'),
          5: v('series-5'),
        },
      },

      borderColor: {
        // Tailwind's preflight gives a bare `border` class gray-200 from its
        // OWN default, not from the scale above. Pointing DEFAULT at the token
        // is what makes the five bare `border` usages -- all of them form
        // fields -- track the palette instead of staying at #E5E7EB.
        DEFAULT: v('gray-200'),
      },
    },
  },
  plugins: [],
}
