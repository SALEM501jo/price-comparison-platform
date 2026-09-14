import { screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { renderWithProviders as render } from '../test/render';
import { AuthContext } from '../context/auth-context';
import Browse from './Browse';
import ProductDetail from './ProductDetail';
import Results from './Results';

/**
 * Which public pages a search engine may index, decided per page.
 *
 * WHAT THIS GUARDS. Every route answers 200 with the app, and three pages put
 * text straight from the URL into the tab title and the search snippet. A
 * crafted link to any of them used to be an indexable page on this domain
 * carrying the link's own words -- "call 079..." as a Google result under
 * ahsanse3r.com. Found by an adversarial review of the page metadata:
 *
 *  1. /results?q=<anything>: internal search is never indexed.
 *  2. /browse/<unknown>: noindex, and the tab does not echo the segment.
 *  3. /product/<not a number>: the API answers 422, which is as permanent as
 *     a 404 and must not be treated as a temporary outage.
 */

vi.mock('../api/products', () => ({
  searchProducts: vi.fn(),
  browseCatalogue: vi.fn(),
  getProduct: vi.fn(),
  getPriceHistory: vi.fn(),
  getDeals: vi.fn(),
  getSuggestions: vi.fn(),
  recordContactTap: vi.fn(),
}));

// Imported after vi.mock so these are the mocks.
const api = await import('../api/products');

const ANONYMOUS = {
  loading: false,
  user: null,
  isAuthenticated: false,
  isAdmin: false,
  isMerchant: false,
};

function renderAt(path, pattern, element) {
  return render(
    <AuthContext.Provider value={ANONYMOUS}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path={pattern} element={element} />
        </Routes>
      </MemoryRouter>
    </AuthContext.Provider>,
  );
}

const robots = () =>
  [...document.head.querySelectorAll('meta[name="robots"]')].map((m) => m.getAttribute('content'));

beforeEach(() => {
  api.getSuggestions.mockResolvedValue([]);
  api.getPriceHistory.mockResolvedValue([]);
});

afterEach(() => {
  vi.clearAllMocks();
});

describe('search results', () => {
  it('is never indexed, whatever the link says', async () => {
    api.searchProducts.mockResolvedValue({ exact: [], close: [], similar: [], total: 0 });
    renderAt('/results?q=call%200790000000%20for%20cheap%20iPhones', '/results', <Results />);

    await waitFor(() => expect(robots()).toContain('noindex'));
  });
});

describe('browse', () => {
  it('does not put an unknown category from the URL in the tab, and is not indexed', async () => {
    api.browseCatalogue.mockResolvedValue({ products: [], total: 0, categories: [] });
    renderAt('/browse/Official%20refunds%20call%200790000000', '/browse/:category', <Browse />);

    await waitFor(() => expect(robots()).toContain('noindex'));
    expect(document.title).not.toContain('0790000000');
  });

  it('indexes a real category that has products', async () => {
    api.browseCatalogue.mockResolvedValue({
      products: [{ id: 1, canonical_name: 'Galaxy S24 128GB', category: 'phones', prices: [] }],
      total: 1,
      categories: [{ category: 'phones', count: 1 }],
    });
    renderAt('/browse/phones', '/browse/:category', <Browse />);

    await waitFor(() => expect(api.browseCatalogue).toHaveBeenCalled());
    await waitFor(() => expect(document.title).toContain('Phones'));
    expect(robots()).not.toContain('noindex');
  });

  it('is not indexed when a real category turns out empty', async () => {
    api.browseCatalogue.mockResolvedValue({ products: [], total: 0, categories: [] });
    renderAt('/browse/phones', '/browse/:category', <Browse />);

    await waitFor(() => expect(robots()).toContain('noindex'));
  });
});

describe('product page', () => {
  it('treats an id that is not a number as missing, not as an outage', async () => {
    api.getProduct.mockRejectedValue({ response: { status: 422 } });
    renderAt('/product/not-a-number', '/product/:productId', <ProductDetail />);

    await waitFor(() => expect(robots()).toContain('noindex'));
  });

  it('stays indexable through a server error, which is temporary', async () => {
    api.getProduct.mockRejectedValue({ response: { status: 503 } });
    renderAt('/product/42', '/product/:productId', <ProductDetail />);

    await screen.findByText(/could not load|couldn't load|failed/i);
    expect(robots()).not.toContain('noindex');
  });
});
