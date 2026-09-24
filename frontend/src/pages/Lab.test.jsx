import { StrictMode } from 'react';
import { render as renderAtRoot, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { LocaleProvider } from '../context/LocaleContext';
import { renderWithProviders as render } from '../test/render';
import storage from '../test/fixtures/explain-storage.json';
import caseExample from '../test/fixtures/explain-case.json';
import Lab from './Lab';

/**
 * The Matching Lab page.
 *
 * THE FIXTURES ARE THE SERVER'S OWN ANSWERS: test/fixtures/explain-*.json
 * were written by running backend/app/services/explain.py on the requests
 * utils/lab.js sends for those examples. So these tests arrange real numbers
 * -- 67.9, 70, the refused phone case -- rather than numbers invented to
 * make a test pass.
 */

vi.mock('../api/lab', () => ({ explainSearch: vi.fn() }));

// Sentences wrap the names they quote in directional isolates (see
// utils/labText.js) which a reader never sees. Match what is visible: the
// element whose text, isolates removed, is the sentence -- and not every
// ancestor that also contains it.
const visible = (text) => text.replace(/[\u2068\u2069]/g, '');
const sentence = (expected) => (_, element) => {
  if (!element) return false;
  const matches = (node) =>
    typeof expected === 'string'
      ? visible(node.textContent) === expected
      : expected.test(visible(node.textContent));
  return matches(element) && ![...element.children].some(matches);
};
const { explainSearch } = await import('../api/lab');

let lastLocation = null;
function LocationProbe() {
  lastLocation = useLocation();
  return null;
}

function show(path = '/lab', options) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route
          path="/lab"
          element={
            <>
              <Lab />
              <LocationProbe />
            </>
          }
        />
      </Routes>
    </MemoryRouter>,
    options,
  );
}

function answerWith(...fixtures) {
  for (const fixture of fixtures) explainSearch.mockResolvedValueOnce(fixture.response);
}

afterEach(() => {
  // reset, not clear: the StrictMode test installs an implementation, and a
  // cleared mock would keep it for every test after.
  vi.resetAllMocks();
});

describe('<Lab>', () => {
  it('explains its first example on arrival, sending exactly that example', async () => {
    answerWith(storage);
    show();

    await waitFor(() => expect(explainSearch).toHaveBeenCalledTimes(1));
    expect(explainSearch.mock.calls[0][0]).toEqual(storage.request);
    expect(await screen.findByRole('heading', { name: 'How the search was read' })).toBeInTheDocument();
  });

  it('still explains its first example under StrictMode, as `npm run dev` renders it', async () => {
    // Found by running the page in the Vite dev server, not by a test: in
    // development StrictMode mounts, rehearses an unmount, and mounts again.
    // The rehearsal aborted the opening request and a "run once" guard kept
    // the second mount from sending it again -- a blank page in development
    // only. The mock honours the abort signal, as axios does, or this test
    // could not see that.
    explainSearch.mockImplementation(
      (body, { signal } = {}) =>
        new Promise((resolve, reject) => {
          const abort = () => reject(Object.assign(new Error('canceled'), { code: 'ERR_CANCELED' }));
          if (signal?.aborted) return abort();
          signal?.addEventListener('abort', abort);
          setTimeout(() => resolve(storage.response), 0);
        }),
    );
    // StrictMode AT THE ROOT, as main.jsx has it. Nested inside the
    // providers renderWithProviders adds, React does not rehearse the
    // unmount at all, and this test passed against the broken page.
    window.localStorage.setItem('locale', 'en');
    renderAtRoot(
      <StrictMode>
        <LocaleProvider>
          <MemoryRouter initialEntries={['/lab']}>
            <Routes>
              <Route path="/lab" element={<Lab />} />
            </Routes>
          </MemoryRouter>
        </LocaleProvider>
      </StrictMode>,
    );

    expect(await screen.findByRole('heading', { name: 'How the search was read' })).toBeInTheDocument();
  });

  it('leads with the disagreement scorer.py documents', async () => {
    answerWith(storage);
    show();

    // The Pro Max (E) beats the right phone (A) by string similarity, 70 to
    // 67.9, and the engine scores them 72 and 100.
    expect(
      await screen.findByText(
        sentence(
          'String similarity ranks E “Apple iPhone 11 Pro Max 128GB Black” above A “Apple iPhone 11 Pro 128GB Black”, 70 to 67.9. This site scores them 72 and 100: different variant (Pro Max, not Pro).',
        ),
      ),
    ).toBeInTheDocument();
    expect(
      screen.getByText('6 of 20 pairs in the opposite order, or tied where this site sees a difference.'),
    ).toBeInTheDocument();
  });

  it('ranks the same listings twice', async () => {
    answerWith(storage);
    show();

    const similarity = await screen.findByRole('list', { name: 'String similarity' });
    const engine = screen.getByRole('list', { name: 'This site' });
    const firstTitle = (list) => within(list).getAllByRole('link')[0].textContent;

    expect(firstTitle(similarity)).toContain('iPhone 11 Pro Black 128GB Smartphone 5G');
    expect(firstTitle(engine)).toContain('Apple iPhone 11 Pro 128GB Black');
    // Every row links to its listing's card.
    expect(within(engine).getAllByRole('link')[0]).toHaveAttribute('href', '#lab-listing-0');
  });

  it('writes out every lost point, so the bar is never the only place it lives', async () => {
    answerWith(storage);
    show();

    const card = await screen.findByRole('article', { name: 'Apple iPhone 11 Pro 256GB Black' });
    expect(within(card).getByText('76')).toBeInTheDocument();
    // Once in the bar, once in words beside the reason.
    const lostLine = within(card).getByText('different storage (256gb, not 128gb)');
    expect(lostLine).toHaveTextContent('−24');
    expect(within(card).getAllByText('−24')).toHaveLength(2);
    expect(within(card).getByText('Not in the search, so free: memory')).toBeInTheDocument();
    expect(within(card).getByRole('img', { name: 'Score 76 out of 100' })).toBeInTheDocument();
  });

  it('says the brand gate excluded the Samsung, rather than showing a score of 0', async () => {
    answerWith(storage);
    show();

    const card = await screen.findByRole('article', { name: 'Samsung Galaxy S24 128GB Black' });
    expect(
      within(card).getByText(
        'Brand is a gate: different brand (samsung, not apple). Excluded, however much else agrees.',
      ),
    ).toBeInTheDocument();
    expect(within(card).queryByRole('img')).not.toBeInTheDocument();
  });

  it('opens the example the address names, and says why the case was turned away', async () => {
    answerWith(caseExample);
    show('/lab?example=case');

    await waitFor(() => expect(explainSearch).toHaveBeenCalledTimes(1));
    expect(explainSearch.mock.calls[0][0]).toEqual(caseExample.request);
    expect(screen.getByRole('button', { name: 'A case names its phone' })).toHaveAttribute('aria-pressed', 'true');

    const card = await screen.findByRole('article', { name: 'IPHONE 15 PRO CASE' });
    expect(within(card).getByText(sentence(/^The store files this under “Mobile Case”/))).toBeInTheDocument();
    expect(
      screen.getByText(
        sentence(
          'String similarity ranks A “IPHONE 15 PRO CASE” above C “Apple iPhone 15 Pro 256GB Natural Titanium”, 83.9 to 47.3. This site gives C 100 and does not score A at all: the store files it under “Mobile Case”, which this site does not carry.',
        ),
      ),
    ).toBeInTheDocument();
  });

  it('switches example on a click, and puts it in the address', async () => {
    answerWith(storage, caseExample);
    show();
    await screen.findByRole('heading', { name: 'How the search was read' });

    await userEvent.click(screen.getByRole('button', { name: 'A case names its phone' }));

    await waitFor(() => expect(explainSearch).toHaveBeenCalledTimes(2));
    expect(explainSearch.mock.calls[1][0]).toEqual(caseExample.request);
    expect(lastLocation.search).toBe('?example=case');
    expect(screen.getByLabelText('Search')).toHaveValue('iPhone 15 Pro');
  });

  it('sends an edited search, trimmed, without blank rows', async () => {
    answerWith(storage, storage);
    show();
    await screen.findByRole('heading', { name: 'How the search was read' });

    const search = screen.getByLabelText('Search');
    await userEvent.clear(search);
    await userEvent.type(search, 'Galaxy A57 256GB');
    await userEvent.click(screen.getByRole('button', { name: 'Add a listing' }));
    expect(screen.getByText('Edited — press Explain to update.')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Explain' }));

    await waitFor(() => expect(explainSearch).toHaveBeenCalledTimes(2));
    const sent = explainSearch.mock.calls[1][0];
    expect(sent.query).toBe('Galaxy A57 256GB');
    expect(sent.listings).toHaveLength(storage.request.listings.length);
    expect(screen.queryByRole('button', { name: /One character/, pressed: true })).not.toBeInTheDocument();
  });

  it('refuses a search too short for the server before sending it', async () => {
    answerWith(storage);
    show();
    await screen.findByRole('heading', { name: 'How the search was read' });

    await userEvent.clear(screen.getByLabelText('Search'));
    await userEvent.type(screen.getByLabelText('Search'), 'x');
    await userEvent.click(screen.getByRole('button', { name: 'Explain' }));

    expect(screen.getByRole('alert')).toHaveTextContent('Type at least 2 characters to search.');
    expect(explainSearch).toHaveBeenCalledTimes(1);
  });

  it('keeps a listing row at the minimum of one and stops adding at eight', async () => {
    answerWith(storage);
    show();
    await screen.findByRole('heading', { name: 'How the search was read' });

    // The first example has seven listings; one more reaches the server's cap.
    await userEvent.click(screen.getByRole('button', { name: 'Add a listing' }));
    expect(screen.getByRole('button', { name: 'Up to 8 listings' })).toBeDisabled();
  });

  it('says so when the server cannot answer', async () => {
    explainSearch.mockRejectedValueOnce({ response: { status: 500 } });
    show();

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Could not explain this search. Try again in a moment.',
    );
  });

  it('is an indexable page with its own title', async () => {
    answerWith(storage);
    show();
    await screen.findByRole('heading', { name: 'How the search was read' });

    expect(document.title).toBe('Matching Lab — Ahsan Se3r');
    expect(document.head.querySelector('meta[name="robots"]')).toBeNull();
  });

  it('letters listings in Arabic order for an Arabic reader, and prints no raw keys', async () => {
    answerWith(storage);
    const { container } = show('/lab', { locale: 'ar' });
    await screen.findByRole('heading', { name: 'كيف قُرئ البحث' });

    const rows = within(screen.getByRole('list', { name: 'هذا الموقع' })).getAllByRole('link');
    expect(rows[0].textContent).toContain('أ');
    expect(container.textContent).not.toMatch(/lab\.[a-z]/);
  });

  it('isolates the Latin names an Arabic sentence quotes, so the numbers stay put', async () => {
    // Without the isolates, "«...Natural Titanium»: 83.9" rendered with the
    // closing guillemet after the number at 375px.
    answerWith(caseExample);
    show('/lab?example=case', { locale: 'ar' });

    const headline = await screen.findByText(sentence(/^يضع تشابه النصوص/));
    expect(headline.textContent).toContain('«\u2068IPHONE 15 PRO CASE\u2069»');
    expect(headline.textContent).toContain('«\u2068Apple iPhone 15 Pro 256GB Natural Titanium\u2069»');
  });

  it('prints no raw keys in English either', async () => {
    answerWith(caseExample);
    const { container } = show('/lab?example=case');
    await screen.findByRole('article', { name: 'IPHONE 15 PRO CASE' });

    expect(container.textContent).not.toMatch(/\b(lab|match|category|tier)\.[a-z]/);
  });
});
