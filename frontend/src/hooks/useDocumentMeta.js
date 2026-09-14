import { useEffect } from 'react';
import { useLocale } from './useLocale';

/**
 * Fill {placeholders} in a template, treating every value as inert text.
 *
 * For a template that is already translated: t('meta.x') picks the string,
 * this fills it. The substitution is the same one-pass function replacer t()
 * uses -- a function replacer is never read for `$&`-style patterns, and a
 * single pass never revisits what it inserted, which matters because a page
 * title is built from product names and search queries nobody here wrote.
 * (t() used replaceAll per variable and got both wrong; it was fixed to match.)
 *
 * Object.hasOwn rather than `in`: a template naming {constructor} must stay
 * as written, not be filled from Object.prototype.
 */
export function fillTemplate(template, vars = {}) {
  return template.replace(/\{(\w+)\}/g, (placeholder, name) =>
    Object.hasOwn(vars, name) ? String(vars[name]) : placeholder,
  );
}

/**
 * The tab title, the search-result snippet and the robots rule for one page.
 *
 *   useDocumentMeta({ title: product.canonical_name, description, noindex })
 *
 * `title` is the PAGE's part only; the site name is appended here, so every
 * tab reads "<page> — احسن سعر" (or "— Ahsan Se3r") and no page can forget
 * it. Leave it out for the site title itself, and leave `description` out for
 * the site description.
 *
 * WHY EVERY PAGE NEEDS THIS. The server answers every route with the same
 * index.html, so without it every tab, every history entry and every result
 * Google renders is titled like the home page -- forty open products that
 * cannot be told apart, and a search listing that says nothing about the page
 * it links to. Google runs the JavaScript before it indexes, so what is set
 * here is what it reads.
 *
 * WHAT IT DOES NOT DO: Open Graph. WhatsApp, Facebook and X build a link
 * preview from the HTML the server sent and never run a script, so og:* tags
 * written from here would be read by nobody. They live, static, in index.html.
 *
 * RESTORED ON UNMOUNT to the site defaults, in the current language, rather
 * than to whatever was there before. A snapshot taken on mount is only right
 * if lifetimes never overlap: the moment two users of this hook are mounted
 * at once -- a page and a panel inside it -- one saves the other's title and
 * puts it back after its owner has gone. Defaults cannot go stale that way.
 * React runs every cleanup in a commit before any new effect, so the page
 * being opened still has the last word.
 *
 * NOINDEX IS ADDED, NEVER TAKEN AWAY. index.html carries no robots tag, and
 * pages that must stay out of search -- anything behind a sign-in, anything
 * holding a one-time link, a page that does not exist -- add one while they
 * are mounted. That direction is the one that works: Google documents that a
 * robots tag added by JavaScript is honoured, while a noindex in the served
 * HTML stops it before it ever renders, so no script could lift one again.
 * Each mount appends its own element and removes exactly that element, so
 * one page leaving cannot delete a tag another page still wants.
 *
 * TEXT ONLY. Everything goes through document.title and setAttribute, which
 * store a string and never parse it. A product called "<img onerror=...>" is
 * a strange title, not markup.
 */
export function useDocumentMeta({ title, description, noindex = false } = {}) {
  const { t } = useLocale();

  const siteTitle = t('meta.siteTitle');
  const siteDescription = t('meta.description');
  const fullTitle = title ? fillTemplate(t('meta.pageTitle'), { page: title }) : siteTitle;
  const fullDescription = description || siteDescription;

  useEffect(() => {
    document.title = fullTitle;
    descriptionTag().setAttribute('content', fullDescription);
    return () => {
      document.title = siteTitle;
      descriptionTag().setAttribute('content', siteDescription);
    };
  }, [fullTitle, fullDescription, siteTitle, siteDescription]);

  useEffect(() => {
    if (!noindex) return undefined;
    const tag = document.createElement('meta');
    tag.setAttribute('name', 'robots');
    tag.setAttribute('content', 'noindex');
    document.head.appendChild(tag);
    return () => tag.remove();
  }, [noindex]);
}

// index.html ships one, and it is reused rather than duplicated: two
// descriptions leave a crawler to choose. Created only when absent -- a test
// document, or a head some future change has trimmed.
function descriptionTag() {
  let tag = document.head.querySelector('meta[name="description"]');
  if (!tag) {
    tag = document.createElement('meta');
    tag.setAttribute('name', 'description');
    document.head.appendChild(tag);
  }
  return tag;
}
