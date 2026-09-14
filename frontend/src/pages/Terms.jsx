import LegalPage from '../components/layout/LegalPage';
import { useDocumentMeta } from '../hooks/useDocumentMeta';
import { useLocale } from '../hooks/useLocale';

/**
 * The terms of use, as an outline. LegalPage turns it into the page.
 *
 * WRITTEN FOR TWO AUDIENCES AT ONCE. A shopper needs one thing from this
 * page: that a price here is a guide and the shop's own price is what they
 * will pay. A shop owner -- who is about to be asked to open an account --
 * needs the merchant section, because that is what they are agreeing to when
 * they upload a photo of a phone and publish their mobile number.
 *
 * WHAT THIS PAGE MUST NOT IMPLY. No retailer has agreed to anything: the
 * scraper honours robots.txt out of courtesy, which is not permission, and
 * saying otherwise would invent a partnership that does not exist. And the
 * merchant taps we report are taps -- never calls, never customers, never
 * sales -- because the platform genuinely cannot tell one shopper from two.
 */
const SECTIONS = [
  {
    id: 'terms-what',
    title: 'terms.what.title',
    blocks: ['terms.what.p1', 'terms.what.p2', 'terms.what.p3'],
  },
  {
    id: 'terms-prices',
    title: 'terms.prices.title',
    blocks: [
      'terms.prices.sources',
      [
        'terms.prices.stale',
        'terms.prices.governs',
        'terms.prices.age',
        'terms.prices.matching',
      ],
      'terms.prices.report',
    ],
  },
  {
    id: 'terms-account',
    title: 'terms.account.title',
    blocks: [
      [
        'terms.account.email',
        'terms.account.password',
        'terms.account.breach',
        'terms.account.one',
      ],
    ],
  },
  {
    id: 'terms-merchant',
    title: 'terms.merchant.title',
    blocks: [
      'terms.merchant.intro',
      [
        'terms.merchant.accurate',
        'terms.merchant.condition',
        'terms.merchant.public',
        'terms.merchant.freeText',
        'terms.merchant.photos',
        'terms.merchant.licence',
        'terms.merchant.remove',
      ],
      'terms.merchant.review',
      'terms.merchant.taps',
    ],
  },
  {
    id: 'terms-retailers',
    title: 'terms.retailers.title',
    blocks: ['terms.retailers.p1', 'terms.retailers.p2', 'terms.retailers.p3'],
  },
  {
    id: 'terms-use',
    title: 'terms.use.title',
    blocks: [
      ['terms.use.harvest', 'terms.use.copy', 'terms.use.attack', 'terms.use.illegal'],
    ],
  },
  {
    id: 'terms-termination',
    title: 'terms.termination.title',
    blocks: [
      'terms.termination.you',
      { key: 'terms.termination.link', to: '/account' },
      'terms.termination.us',
      { key: 'terms.termination.privacyLink', to: '/privacy' },
    ],
  },
  {
    id: 'terms-warranty',
    title: 'terms.warranty.title',
    blocks: ['terms.warranty.p1', 'terms.warranty.p2', 'terms.warranty.p3'],
  },
  {
    id: 'terms-changes',
    title: 'terms.changes.title',
    blocks: ['terms.changes.p1'],
  },
  {
    id: 'terms-law',
    title: 'terms.law.title',
    blocks: ['terms.law.p1', 'terms.law.p2'],
  },
  {
    id: 'terms-contact',
    title: 'terms.contact.title',
    blocks: ['terms.contact.p1', { key: 'terms.contact.link', to: '/contact' }],
  },
];

// Who the agreement is with, and whose courts read it, are the two facts this
// page cannot know. They render as a panel at the top until filled.
const UNFILLED = ['legal.field.entity', 'legal.field.law'];

export default function Terms() {
  const { t } = useLocale();
  useDocumentMeta({ title: t('terms.title'), description: t('terms.blurb') });

  return (
    <LegalPage title="terms.title" blurb="terms.blurb" sections={SECTIONS} unfilled={UNFILLED} />
  );
}
