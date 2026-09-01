import { screen } from '@testing-library/react';
import { renderWithProviders as render } from '../../test/render';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it } from 'vitest';
import ProductResultCard from './ProductResultCard';
import MatchBadge from './MatchBadge';

const product = {
  id: 1,
  canonical_name: 'Apple iPhone 15 128GB 5G Smartphone - Black',
  brand: 'apple',
  match_score: 100,
  match_tier: 'exact',
  differences: [],
  lowest_total_cost: 877.5,
  best_deal_store: 'SmartBuy',
  store_count: 4,
};

// One entry of the structured `differences` list the API now returns.
const COLOUR_DIFFERS = {
  attribute: 'color',
  label: 'colour',
  query_value: 'black',
  candidate_value: 'blue',
};

const show = (overrides = {}, options = {}) =>
  render(
    <MemoryRouter>
      <ProductResultCard product={{ ...product, ...overrides }} />
    </MemoryRouter>,
    options,
  );

describe('ProductResultCard', () => {
  it('shows the product and its cheapest total', () => {
    show();
    expect(screen.getByText(product.canonical_name)).toBeInTheDocument();
    expect(screen.getByText('877.50 JOD')).toBeInTheDocument();
  });

  it('shows the total INCLUDING delivery, which is what a buyer pays', () => {
    show();
    expect(screen.getByText(/incl\. delivery/)).toBeInTheDocument();
    expect(screen.getByText(/SmartBuy/)).toBeInTheDocument();
  });

  it('reports how many stores carry it', () => {
    show();
    expect(screen.getByText('4 stores')).toBeInTheDocument();
  });

  it('explains why a result is not exact', () => {
    // The whole point of the tiers: the shopper can see at a glance whether
    // the difference matters to them.
    show({
      match_tier: 'close',
      match_score: 90,
      differences: [COLOUR_DIFFERS],
    });
    expect(
      screen.getByText('different colour (blue, not black)'),
    ).toBeInTheDocument();
  });

  it('explains it in the language the shopper is reading', () => {
    // THE REASON THIS FEATURE WAS REBUILT. The server used to send the
    // sentence ready-made in English, so the one piece of text the tiered
    // results exist to produce arrived untranslated on an Arabic-first site.
    //
    // Asserted as "no Latin letters" rather than against a pinned Arabic
    // string, on purpose: the point is that the sentence FOLLOWS THE LOCALE,
    // and pinning the wording would make an improvement to the phrasing look
    // like a regression. (Only safe for colours and variants -- a capacity is
    // deliberately still written "128GB" in Arabic.)
    show(
      { match_tier: 'close', match_score: 90, differences: [COLOUR_DIFFERS] },
      { locale: 'ar' },
    );
    // By role, not by text: in Arabic the whole card matches an Arabic-script
    // pattern, so a text query finds the delivery line and the store count too.
    const [explanation] = screen.getAllByRole('listitem');
    expect(explanation.textContent).toMatch(/[\u0600-\u06FF]/);
    expect(explanation.textContent).not.toMatch(/[a-zA-Z]/);
  });

  it('distinguishes a different value from one the listing never states', () => {
    // "The wrong colour" and "nobody said what colour" are different facts.
    show({
      match_tier: 'close',
      match_score: 90,
      differences: [{ ...COLOUR_DIFFERS, candidate_value: null }],
    });
    expect(screen.getByText('colour not listed')).toBeInTheDocument();
  });

  it('lists every difference, not just the first', () => {
    show({
      match_tier: 'similar',
      match_score: 70,
      differences: [
        {
          attribute: 'storage',
          label: 'storage',
          query_value: '128gb',
          candidate_value: '256gb',
        },
        COLOUR_DIFFERS,
      ],
    });
    expect(screen.getByText(/different storage/)).toBeInTheDocument();
    expect(screen.getByText(/different colour/)).toBeInTheDocument();
  });

  it('says "not in stock" instead of showing a price of nothing', () => {
    show({ store_count: 0, lowest_total_cost: null });
    expect(screen.getByText('Not in stock')).toBeInTheDocument();
  });

  it('links to the product detail page', () => {
    show();
    expect(screen.getByRole('link')).toHaveAttribute('href', '/product/1');
  });
});

describe('MatchBadge', () => {
  it('names an exact match rather than showing 100%', () => {
    render(<MatchBadge tier="exact" score={100} />);
    expect(screen.getByText('Exact match')).toBeInTheDocument();
  });

  it('rounds the percentage for other tiers', () => {
    render(<MatchBadge tier="similar" score={74.7} />);
    expect(screen.getByText('75% match')).toBeInTheDocument();
  });

  it('exposes the precise score for anyone who wants it', () => {
    render(<MatchBadge tier="close" score={89.5} />);
    expect(screen.getByTitle('Match score: 89.5%')).toBeInTheDocument();
  });
});
