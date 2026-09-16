import { useEffect } from 'react';
import { useLocation, useNavigationType } from 'react-router-dom';

/**
 * Start a new page at the top.
 *
 * A single-page app does not reload, so the browser keeps the scroll position
 * from the page you left. Tapping a product from halfway down a results page
 * opened the product page already scrolled halfway down -- on a phone that
 * looks like a page with no header, because the header is far above.
 *
 * ONLY ON A NEW NAVIGATION (PUSH/REPLACE). Going BACK keeps the browser's
 * restored position, which is what a visitor expects: they return to the row
 * they tapped, not to the top of a long list.
 *
 * The search page changes the query string as the shopper types and sorts;
 * that is the same page, so the scroll is left alone unless the path changed.
 */
export default function ScrollToTop() {
  const { pathname } = useLocation();
  const navigationType = useNavigationType();

  useEffect(() => {
    if (navigationType === 'POP') return;
    window.scrollTo({ top: 0, left: 0, behavior: 'instant' });
  }, [pathname, navigationType]);

  return null;
}
