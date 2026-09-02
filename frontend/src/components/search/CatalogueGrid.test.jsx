import { screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it } from 'vitest';
import { renderWithProviders as render } from '../../test/render';
import CatalogueGrid, { CategoryTiles } from './CatalogueGrid';

/**
 * The tile's DESTINATION is the whole test.
 *
 * These three tiles shipped pointing at `/results?q=Phones` — a text search
 * for the word "Phones". Nothing in the catalogue is called that, so a tile
 * advertising 151 products led to "Nothing matched that search", and the
 * Laptops tile returned exactly one product: a monitor whose title happens to
 * contain "for Laptops".
 *
 * Nothing caught it. The component rendered, the link worked, the count was
 * right, and the page it led to was a perfectly functioning search for a word
 * no product has. Only clicking it revealed the bug — so the assertion is on
 * where the tile GOES, not on whether it renders.
 */

const CATEGORIES = [
  { category: 'phones', count: 151 },
  { category: 'laptops', count: 97 },
  { category: 'monitors', count: 116 },
];

const show = (ui, options) => render(<MemoryRouter>{ui}</MemoryRouter>, options);

describe('CategoryTiles', () => {
  it('sends a category to the browse listing, never to a search', () => {
    show(<CategoryTiles categories={CATEGORIES} />);

    expect(screen.getByRole('link', { name: /Phones/ })).toHaveAttribute(
      'href',
      '/browse/phones',
    );
    expect(screen.getByRole('link', { name: /Laptops/ })).toHaveAttribute(
      'href',
      '/browse/laptops',
    );
  });

  it('never routes a tile through the search page', () => {
    // The specific regression, stated as the rule rather than as one URL: a
    // category is a lookup, and search is for words a shopper typed.
    const { container } = show(<CategoryTiles categories={CATEGORIES} />);
    for (const link of container.querySelectorAll('a')) {
      expect(link.getAttribute('href')).not.toMatch(/\/results/);
      expect(link.getAttribute('href')).not.toMatch(/[?&]q=/);
    }
  });

  it('shows the count it is promising', () => {
    show(<CategoryTiles categories={CATEGORIES} />);
    expect(screen.getByText('151 products')).toBeInTheDocument();
    expect(screen.getByText('97 products')).toBeInTheDocument();
  });

  it('names the categories in Arabic', () => {
    show(<CategoryTiles categories={CATEGORIES} />, { locale: 'ar' });
    expect(screen.getByText('هواتف')).toBeInTheDocument();
    expect(screen.getByText('لابتوبات')).toBeInTheDocument();
  });

  it('renders nothing when there are no categories', () => {
    const { container } = show(<CategoryTiles categories={[]} />);
    expect(container).toBeEmptyDOMElement();
  });
});

describe('CatalogueGrid', () => {
  const product = {
    id: 7,
    canonical_name: 'Honor X5c 4G, 4GB & 64GB',
    brand: 'honor',
    image_url: 'https://cdn.example/x.jpg',
    lowest_total_cost: 96,
    best_deal_store: 'SmartBuy',
    store_count: 1,
  };

  it('links each tile to its product', () => {
    show(<CatalogueGrid products={[product]} loading={false} />);
    expect(screen.getByRole('link')).toHaveAttribute('href', '/product/7');
  });

  it('shows skeletons while the first page loads', () => {
    const { container } = show(<CatalogueGrid products={[]} loading />);
    expect(container.querySelectorAll('.animate-pulse').length).toBeGreaterThan(0);
  });

  it('renders nothing rather than an empty box when there is nothing', () => {
    const { container } = show(<CatalogueGrid products={[]} loading={false} />);
    expect(container).toBeEmptyDOMElement();
  });
});
