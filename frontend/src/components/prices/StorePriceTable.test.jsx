import { render, screen, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import StorePriceTable from './StorePriceTable';

const prices = [
  {
    store_name: 'DNA Jordan',
    price: 899,
    delivery_cost: 0,
    total_cost: 899,
    availability: true,
    store_product_url: 'https://www.dna.jo/x',
  },
  {
    store_name: 'SmartBuy',
    price: 875,
    delivery_cost: 2.5,
    total_cost: 877.5,
    availability: true,
    store_product_url: 'https://smartbuy-me.com/x',
  },
  {
    store_name: 'Carrefour Jordan',
    price: 889,
    delivery_cost: 0,
    total_cost: 889,
    availability: true,
  },
];

const rowsOf = (container) =>
  [...container.querySelectorAll('tbody tr')].map((r) => r.textContent);

describe('StorePriceTable', () => {
  it('orders stores by total cost, not sticker price', () => {
    // SmartBuy has the HIGHER delivery and still wins, because 875 + 2.50
    // beats Carrefour's 889 with free delivery. Sorting on price alone would
    // put Carrefour second and mislead the shopper.
    const { container } = render(<StorePriceTable prices={prices} />);
    const rows = rowsOf(container);
    expect(rows[0]).toMatch(/SmartBuy/);
    expect(rows[1]).toMatch(/Carrefour Jordan/);
    expect(rows[2]).toMatch(/DNA Jordan/);
  });

  it('marks the cheapest total as the best deal', () => {
    const { container } = render(<StorePriceTable prices={prices} />);
    const first = container.querySelector('tbody tr');
    expect(within(first).getByText('Best deal')).toBeInTheDocument();
  });

  it('shows free delivery as free rather than 0.00', () => {
    render(<StorePriceTable prices={prices} />);
    expect(screen.getAllByText('Free').length).toBeGreaterThan(0);
  });

  it('does not depend on the caller having sorted the list', () => {
    const reversed = [...prices].reverse();
    const { container } = render(<StorePriceTable prices={reversed} />);
    expect(rowsOf(container)[0]).toMatch(/SmartBuy/);
  });

  it('marks the cheapest IN-STOCK store, not merely the cheapest row', () => {
    const withCheapOutOfStock = [
      { store_name: 'Sold Out', price: 1, delivery_cost: 0, total_cost: 1, availability: false },
      ...prices,
    ];
    const { container } = render(<StorePriceTable prices={withCheapOutOfStock} />);
    const soldOutRow = [...container.querySelectorAll('tbody tr')].find((r) =>
      r.textContent.includes('Sold Out'),
    );
    expect(within(soldOutRow).queryByText('Best deal')).toBeNull();
  });

  it('opens store links safely', () => {
    // noopener/noreferrer stops the opened store page reaching back into this
    // tab through window.opener.
    render(<StorePriceTable prices={prices} />);
    const link = screen.getAllByRole('link', { name: 'Visit' })[0];
    expect(link).toHaveAttribute('target', '_blank');
    expect(link).toHaveAttribute('rel', expect.stringContaining('noopener'));
    expect(link).toHaveAttribute('rel', expect.stringContaining('noreferrer'));
  });

  it('says so when no store carries the product', () => {
    render(<StorePriceTable prices={[]} />);
    expect(screen.getByText(/No stores are currently listing/)).toBeInTheDocument();
  });
});
