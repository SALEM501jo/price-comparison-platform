import { screen } from '@testing-library/react';
import { renderWithProviders as render } from '../../test/render';
import { describe, expect, it } from 'vitest';
import QueryInterpretation from './QueryInterpretation';

const interpretation = {
  query: 'iPhone 15 128GB Black',
  category: 'phones',
  structured: true,
  attributes: {
    brand: 'apple',
    model: 'iphone 15',
    storage: '128gb',
    color: 'black',
  },
};

const show = (overrides = {}, options = {}) =>
  render(
    <QueryInterpretation interpretation={{ ...interpretation, ...overrides }} />,
    options,
  );

describe('QueryInterpretation', () => {
  it('shows what the server understood the query to mean', () => {
    show();
    expect(screen.getByText('iphone 15')).toBeInTheDocument();
    expect(screen.getByText('128gb')).toBeInTheDocument();
  });

  it('leaves out the brand, which the model already implies', () => {
    show();
    expect(screen.queryByText('apple')).not.toBeInTheDocument();
  });

  it('leaves out a variant nobody typed', () => {
    // "base" is what the parser fills in for a listing, not something the
    // shopper asked for. Showing it claims they were more specific than they
    // were.
    show({ attributes: { ...interpretation.attributes, variant: 'base' } });
    expect(screen.queryByText('base')).not.toBeInTheDocument();
  });

  it('says the value in the reader\'s language', () => {
    // The chip used to read "black" underneath a card that said "أسود" for
    // the same value -- one screen disagreeing with itself. Same vocabulary
    // as the difference lines now, so it cannot drift again.
    show({}, { locale: 'ar' });
    expect(screen.getByText('أسود')).toBeInTheDocument();
    expect(screen.queryByText('black')).not.toBeInTheDocument();
  });

  it('leaves a capacity and a model code in Latin', () => {
    // Deliberate: that is how they are written on a Jordanian shelf.
    show({}, { locale: 'ar' });
    expect(screen.getByText('128gb')).toBeInTheDocument();
    expect(screen.getByText('iphone 15')).toBeInTheDocument();
  });

  it('names the attribute in the tooltip, translated', () => {
    // Was the raw machine name -- "color", not even the English label.
    expect(show().getByTitle('colour')).toBeInTheDocument();
    expect(show({}, { locale: 'ar' }).getByTitle('اللون')).toBeInTheDocument();
  });

  it('lets the browser decide each chip\'s direction', () => {
    // dir="auto" reads the direction off the first strong character, so a
    // Latin capacity still runs left-to-right inside the RTL page while a
    // translated colour runs the way it is written. A hard dir="ltr" was
    // right only while every value was Latin.
    const { container } = show({}, { locale: 'ar' });
    const chips = container.querySelectorAll('span[title]');
    expect(chips.length).toBeGreaterThan(0);
    for (const chip of chips) {
      expect(chip.getAttribute('dir')).toBe('auto');
    }
  });

  it('says so plainly when the query did not parse', () => {
    show({ structured: false });
    expect(screen.getByText(/Searching by name/)).toBeInTheDocument();
  });

  it('renders nothing at all without an interpretation', () => {
    const { container } = render(<QueryInterpretation interpretation={null} />);
    expect(container).toBeEmptyDOMElement();
  });
});
