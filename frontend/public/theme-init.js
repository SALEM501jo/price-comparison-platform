/*
 * Applied before React mounts. Reading the stored choice in a component means
 * the first paint uses the wrong theme and direction, and the page visibly
 * flips a moment later -- most noticeably for an English reader, whose whole
 * layout mirrors from right-to-left on screen.
 *
 * WHY THIS IS A FILE AND NOT AN INLINE <script>. The production CSP is
 * script-src 'self', with no 'unsafe-inline', so an inline block is refused
 * outright and this code simply never ran. Development allows inline scripts,
 * which is why it worked locally and failed only once deployed. A file served
 * from our own origin satisfies 'self' with no exception to the policy.
 *
 * A hash in the CSP would also have worked and was rejected: it breaks
 * silently the first time anyone edits a comment in this script, and the
 * symptom -- a brief theme flash -- is exactly the kind nobody files a bug for.
 *
 * Loaded as a classic, non-deferred script in <head>, so it still runs before
 * the body is parsed: the same timing guarantee the inline version had.
 */
(function () {
  try {
    var locale = localStorage.getItem('locale') || 'ar';
    document.documentElement.lang = locale;
    document.documentElement.dir = locale === 'ar' ? 'rtl' : 'ltr';

    var theme = localStorage.getItem('theme');
    var prefersDark =
      window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches;
    if (theme === 'dark' || (!theme && prefersDark)) {
      document.documentElement.classList.add('dark');
    }
  } catch {
    /* private mode: fall through to the markup defaults */
  }
})();
