import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { beforeEach, describe, expect, it } from 'vitest';
import translations from '../i18n/translations';
import { renderWithProviders as render } from '../test/render';
import { fillTemplate, useDocumentMeta } from './useDocumentMeta';

/**
 * What a browser tab and a search engine read on each page.
 *
 * WHAT THIS GUARDS: the quiet failures. A page that forgets to restore its
 * title leaves the next page wearing it; a noindex that outlives its page
 * takes the home page out of Google, and nothing on screen would ever show
 * it. And the title is built from strings this app did not write -- product
 * names from scrapers and shop owners, queries from whoever wrote the link --
 * so it has to stay text all the way to the tab.
 */

function Page(props) {
  useDocumentMeta(props);
  return null;
}

const robotsTags = () => document.head.querySelectorAll('meta[name="robots"]');
const description = () =>
  document.head.querySelector('meta[name="description"]')?.getAttribute('content');

describe('useDocumentMeta', () => {
  beforeEach(() => {
    // Rendering leaves a description tag in the shared jsdom head, and a test
    // about whether the hook duplicates one needs to start without it.
    document.head.querySelectorAll('meta[name="description"]').forEach((tag) => tag.remove());
    document.title = '';
  });

  it('titles the page and appends the site name', () => {
    render(<Page title="Wishlist" />);
    expect(document.title).toBe('Wishlist — Ahsan Se3r');
  });

  it('puts the Arabic site name on an Arabic page', () => {
    render(<Page title="المفضلة" />, { locale: 'ar' });
    expect(document.title).toBe('المفضلة — احسن سعر');
  });

  it('uses the site title and description when a page gives neither', () => {
    // The home page. In English it must still replace index.html's Arabic.
    render(<Page />);
    expect(document.title).toBe(translations.en['meta.siteTitle']);
    expect(description()).toBe(translations.en['meta.description']);
  });

  it('sets the description', () => {
    render(<Page title="Phones" description="Phones: compare prices." />);
    expect(description()).toBe('Phones: compare prices.');
  });

  it('restores the site defaults when the page goes away', () => {
    const { unmount } = render(<Page title="Phones" description="Phones: compare prices." />);
    unmount();
    expect(document.title).toBe(translations.en['meta.siteTitle']);
    expect(description()).toBe(translations.en['meta.description']);
  });

  it('follows a title that changes while the page is open', () => {
    // A product page opens titled by the site, then learns the product name.
    const { rerender } = render(<Page />);
    rerender(<Page title="iPhone 15" />);
    expect(document.title).toBe('iPhone 15 — Ahsan Se3r');
  });

  it('reuses the description tag index.html ships instead of adding another', () => {
    const shipped = document.createElement('meta');
    shipped.setAttribute('name', 'description');
    shipped.setAttribute('content', 'from the server');
    document.head.appendChild(shipped);

    render(<Page description="from the page" />);

    expect(document.head.querySelectorAll('meta[name="description"]')).toHaveLength(1);
    expect(shipped.getAttribute('content')).toBe('from the page');
  });

  it('adds no robots tag to a page meant to be found', () => {
    render(<Page title="Phones" />);
    expect(robotsTags()).toHaveLength(0);
  });

  it('adds noindex while mounted and removes it on unmount', () => {
    const { unmount } = render(<Page title="Account" noindex />);
    expect(robotsTags()).toHaveLength(1);
    expect(robotsTags()[0].getAttribute('content')).toBe('noindex');

    // The one that matters. A noindex left behind by a sign-in page would
    // ride along to the home page and take the whole site out of search.
    unmount();
    expect(robotsTags()).toHaveLength(0);
  });

  it('drops noindex when a page stops asking for it', () => {
    // A product page that was "not found" and then found on a retry.
    const { rerender } = render(<Page noindex />);
    rerender(<Page />);
    expect(robotsTags()).toHaveLength(0);
  });

  it('removes only its own robots tag', () => {
    const { rerender } = render(
      <>
        <Page noindex />
        <Page noindex />
      </>,
    );
    expect(robotsTags()).toHaveLength(2);

    rerender(<Page noindex />);
    expect(robotsTags()).toHaveLength(1);
  });

  it('keeps a product name that looks like HTML as text', () => {
    const name = '<img src=x onerror="window.__owned=1"></title><script>window.__owned=1</script>';
    render(<Page title={name} description={name} />);

    expect(document.title).toBe(`${name} — Ahsan Se3r`);
    expect(description()).toBe(name);
    // Stored as a string, never parsed: nothing was created from it.
    expect(document.querySelector('title').children).toHaveLength(0);
    expect(document.querySelector('img')).toBeNull();
    expect(document.head.querySelector('script')).toBeNull();
    expect(window.__owned).toBeUndefined();
  });
});

describe('fillTemplate', () => {
  it('fills placeholders', () => {
    expect(fillTemplate('{name} from {price}', { name: 'iPhone 15', price: '650.00 JOD' })).toBe(
      'iPhone 15 from 650.00 JOD',
    );
  });

  it('treats $ in a value as a dollar sign', () => {
    // replaceAll would read these as "the match" and "the text after it".
    expect(fillTemplate('{name} — site', { name: "Deal $& $' $$ phone" })).toBe(
      "Deal $& $' $$ phone — site",
    );
  });

  it('never fills a placeholder that arrived inside a value', () => {
    // A shop owner naming a product "{price}" gets that literal name back.
    expect(fillTemplate('{name} from {price}', { name: '{price}', price: '650.00 JOD' })).toBe(
      '{price} from 650.00 JOD',
    );
  });

  it('leaves a placeholder it was not given as written, inherited names included', () => {
    expect(fillTemplate('{constructor} {missing}', {})).toBe('{constructor} {missing}');
  });
});

describe('index.html', () => {
  // Read from disk, not from a build: this is the file the build copies, and
  // the one a reviewer edits. A path string rather than a URL object, because
  // under jsdom the global URL is jsdom's, and node:fs refuses it.
  const here = dirname(fileURLToPath(import.meta.url));
  const html = readFileSync(resolve(here, '../../index.html'), 'utf8');
  const head = new DOMParser().parseFromString(html, 'text/html').head;
  const attr = (selector, name = 'content') => head.querySelector(selector)?.getAttribute(name);

  it('opens with the title and description the Arabic page sets', () => {
    // A crawler has no stored locale, so it renders the Arabic page. If the
    // served head and the rendered head disagree, Google sees one URL
    // described two ways and chooses between them itself.
    expect(head.querySelector('title').textContent).toBe(translations.ar['meta.siteTitle']);
    expect(attr('meta[name="description"]')).toBe(translations.ar['meta.description']);
  });

  it('keeps the site title short enough to show whole in a result', () => {
    expect(translations.ar['meta.siteTitle'].length).toBeLessThanOrEqual(60);
    expect(translations.en['meta.siteTitle'].length).toBeLessThanOrEqual(60);
  });

  it('gives link previews the same title and description', () => {
    expect(attr('meta[property="og:title"]')).toBe(translations.ar['meta.siteTitle']);
    expect(attr('meta[property="og:description"]')).toBe(translations.ar['meta.description']);
    expect(attr('meta[property="og:site_name"]')).toBe(translations.ar['brand.name']);
  });

  it('declares no canonical and no robots rule, because it is the head of every route', () => {
    expect(head.querySelector('link[rel="canonical"]')).toBeNull();
    expect(head.querySelector('meta[name="robots"]')).toBeNull();
  });

  it('carries no inline script a browser would execute', () => {
    // Production CSP is script-src 'self'. An inline block of real code is
    // refused there while running fine in development, which is how the
    // theme script once shipped broken. A JSON-LD data block is never run.
    const inline = [...head.ownerDocument.querySelectorAll('script:not([src])')];
    expect(inline.length).toBeGreaterThan(0);
    for (const script of inline) {
      expect(script.getAttribute('type')).toBe('application/ld+json');
    }
  });

  it('names the site in structured data in every spelling people type', () => {
    const block = head.querySelector('script[type="application/ld+json"]');
    const graph = JSON.parse(block.textContent)['@graph'];
    const website = graph.find((node) => node['@type'] === 'WebSite');
    const organization = graph.find((node) => node['@type'] === 'Organization');

    for (const node of [website, organization]) {
      expect(node.name).toBe(translations.ar['brand.name']);
      expect(node.alternateName).toEqual(
        expect.arrayContaining(['أحسن سعر', translations.en['brand.name'], 'AhsanSe3r']),
      );
      expect(node.url).toBe('https://ahsanse3r.com/');
    }
    expect(website.inLanguage).toEqual(['ar', 'en']);
    expect(organization.logo).toBe('https://ahsanse3r.com/icon-512.png');
  });

  it('links every icon file and the manifest by its agreed name', () => {
    const hrefs = [...head.querySelectorAll('link[rel="icon"], link[rel="apple-touch-icon"], link[rel="manifest"]')].map(
      (link) => link.getAttribute('href'),
    );
    expect(hrefs).toEqual(
      expect.arrayContaining([
        '/favicon.ico',
        '/favicon.svg',
        '/apple-touch-icon.png',
        '/site.webmanifest',
      ]),
    );
    expect(attr('meta[property="og:image"]')).toBe('https://ahsanse3r.com/og-image.png');
  });

  it('never offers a full-bleed install icon as a tab icon', () => {
    // The 192/512 PNGs are maskable squares for the manifest. As rel=icon a
    // browser may pick one for the tab and show a hard green block.
    const tabIcons = [...head.querySelectorAll('link[rel="icon"]')].map((link) =>
      link.getAttribute('href'),
    );
    expect(tabIcons).not.toContain('/icon-192.png');
    expect(tabIcons).not.toContain('/icon-512.png');
  });
});
