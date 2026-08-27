/** @type {import('tailwindcss').Config} */
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
        // The brand. Deep teal rather than the default Tailwind blue: this is
        // a site about money and trust, and blue-600 is what every unstyled
        // Tailwind project looks like.
        brand: {
          50: '#ECFDF7',
          100: '#D1FAE9',
          200: '#A7F3D6',
          300: '#6EE7BC',
          400: '#34D39E',
          500: '#10B77F',
          600: '#079669',
          700: '#047857',
          800: '#065F46',
          900: '#064E3B',
        },
      },
    },
  },
  plugins: [],
}
