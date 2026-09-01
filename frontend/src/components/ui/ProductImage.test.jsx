import { fireEvent, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { renderWithProviders as render } from '../../test/render';
import ProductImage from './ProductImage';
import { imageSrc } from '../../utils/images';

/**
 * The placeholder is the part worth testing.
 *
 * A missing or broken photo is not a rare edge here: five of the catalogue's
 * products have no image at all, and every other one is hotlinked from a shop's
 * own CDN that can 404 or block us at any time. A shop owner being shown this
 * site will judge it on whichever card is broken, so "no photo" has to render
 * as something deliberate rather than as a torn-page icon.
 */

describe('imageSrc', () => {
  it('leaves an absolute url alone', () => {
    expect(imageSrc('https://cdn.shopify.com/x.jpg')).toBe(
      'https://cdn.shopify.com/x.jpg',
    );
  });

  it('resolves an API path against the API origin, not the app origin', () => {
    // The merchant photo route is served by the API on another port in dev
    // and another host in production, so a bare path would resolve against
    // the app and 404.
    expect(imageSrc('/products/1/photo')).toBe(
      'http://localhost:8000/products/1/photo',
    );
  });

  it('has nothing to resolve when there is no image', () => {
    expect(imageSrc(null)).toBeNull();
    expect(imageSrc('')).toBeNull();
  });
});

describe('ProductImage', () => {
  it('shows the photo when there is one', () => {
    render(<ProductImage src="https://cdn.example/x.jpg" alt="iPhone 15" />);
    expect(screen.getByAltText('iPhone 15')).toHaveAttribute(
      'src',
      'https://cdn.example/x.jpg',
    );
  });

  it('draws a labelled placeholder when there is none', () => {
    render(<ProductImage src={null} alt="iPhone 15" />);
    expect(screen.queryByRole('img', { name: 'No photo' })).toBeInTheDocument();
  });

  it('falls back to the placeholder when the image fails to load', () => {
    // Those urls are on somebody else's server. One disappearing must not
    // leave a broken-image glyph on the card.
    render(<ProductImage src="https://cdn.example/gone.jpg" alt="iPhone 15" />);
    fireEvent.error(screen.getByAltText('iPhone 15'));
    expect(screen.getByRole('img', { name: 'No photo' })).toBeInTheDocument();
  });

  it('recovers when the src changes after a failure', () => {
    // React reuses a card for whatever product scrolls into that slot. A
    // plain "did it fail" flag would keep the placeholder on the next
    // product's photo too.
    const { rerender } = render(
      <ProductImage src="https://cdn.example/gone.jpg" alt="First" />,
    );
    fireEvent.error(screen.getByAltText('First'));
    expect(screen.getByRole('img', { name: 'No photo' })).toBeInTheDocument();

    rerender(<ProductImage src="https://cdn.example/good.jpg" alt="Second" />);
    expect(screen.getByAltText('Second')).toBeInTheDocument();
    expect(screen.queryByRole('img', { name: 'No photo' })).not.toBeInTheDocument();
  });

  it('does not leak the shopper\'s browsing to the shops\' CDNs', () => {
    // Most of these images live on the retailers' servers. Sending a referer
    // would tell each of them exactly which products get looked at here.
    render(<ProductImage src="https://cdn.example/x.jpg" alt="iPhone" />);
    expect(screen.getByAltText('iPhone')).toHaveAttribute(
      'referrerpolicy',
      'no-referrer',
    );
  });

  it('loads lazily, because a results page is a grid of these', () => {
    render(<ProductImage src="https://cdn.example/x.jpg" alt="iPhone" />);
    expect(screen.getByAltText('iPhone')).toHaveAttribute('loading', 'lazy');
  });
});
