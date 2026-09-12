import LegalPage from '../components/layout/LegalPage';

/**
 * The privacy policy, as an outline. LegalPage turns it into the page.
 *
 * EVERY LINE HERE IS A CLAIM ABOUT THIS CODEBASE, and the ones the code did
 * not support were cut rather than softened. Three that a policy would
 * normally reach for and this one cannot:
 *
 *   - "we delete data when it is no longer needed" -- nothing in the backend
 *     schedules a purge, so the retention section says so instead;
 *   - "we do not share your data with third parties" -- product photos are
 *     fetched by the shopper's own browser from the retailers' servers, so
 *     those retailers see an IP address on almost every page view;
 *   - "deleting your account removes everything" -- the text of a support
 *     message deliberately outlives the account that sent it, and a
 *     merchant's shop is retired rather than erased so the catalogue does
 *     not lose the prices a shopper is mid-comparison on.
 *
 * Anyone editing this page should check the claim against the file that
 * implements it before changing the wording. The deletion section in
 * particular is a description of backend/app/services/account.py, down to
 * which columns survive; if that changes, this changes with it.
 */
const SECTIONS = [
  {
    id: 'privacy-who',
    title: 'privacy.who.title',
    blocks: ['privacy.who.p1', 'privacy.who.p2', 'privacy.who.p3'],
  },
  {
    id: 'privacy-collect',
    title: 'privacy.collect.title',
    blocks: [
      'privacy.collect.intro',
      [
        'privacy.collect.account',
        'privacy.collect.noProfile',
        'privacy.collect.shop',
        'privacy.collect.listing',
        'privacy.collect.photos',
        'privacy.collect.wishlist',
        'privacy.collect.support',
        'privacy.collect.sessions',
        'privacy.collect.provider',
        'privacy.collect.linkPassword',
      ],
    ],
  },
  {
    id: 'privacy-why',
    title: 'privacy.why.title',
    blocks: [
      [
        'privacy.why.signin',
        'privacy.why.alerts',
        'privacy.why.shop',
        'privacy.why.support',
        'privacy.why.abuse',
      ],
      'privacy.why.noSale',
    ],
  },
  {
    id: 'privacy-not',
    title: 'privacy.not.title',
    blocks: [
      'privacy.not.intro',
      [
        'privacy.not.analytics',
        'privacy.not.search',
        'privacy.not.taps',
        'privacy.not.exif',
        'privacy.not.sensors',
      ],
      'privacy.not.tapsWhy',
    ],
  },
  {
    // The cookie-banner reasoning lives here rather than in a dismissible
    // strip across the top of the site. See Footer.jsx for why there is none.
    id: 'privacy-cookies',
    title: 'privacy.cookies.title',
    blocks: [
      'privacy.cookies.one',
      'privacy.cookies.oauth',
      'privacy.cookies.local',
      'privacy.cookies.noBanner1',
      'privacy.cookies.noBanner2',
      'privacy.cookies.noBanner3',
    ],
  },
  {
    id: 'privacy-others',
    title: 'privacy.others.title',
    blocks: [
      'privacy.others.intro',
      [
        'privacy.others.images',
        'privacy.others.referrer',
        'privacy.others.meta',
        'privacy.others.email',
        'privacy.others.hosting',
        'privacy.others.providers',
      ],
      'privacy.others.fonts',
      'privacy.others.retailers',
    ],
  },
  {
    id: 'privacy-keep',
    title: 'privacy.keep.title',
    blocks: [
      'privacy.keep.honest',
      [
        'privacy.keep.wishlist',
        'privacy.keep.links',
        'privacy.keep.sessions',
        'privacy.keep.support',
        'privacy.keep.prices',
      ],
      'privacy.keep.logs',
    ],
  },
  {
    id: 'privacy-rights',
    title: 'privacy.rights.title',
    blocks: [
      'privacy.rights.intro',
      [
        'privacy.rights.delete',
        'privacy.rights.providerLink',
        'privacy.rights.survives',
        'privacy.rights.export',
      ],
      { key: 'privacy.rights.accountLink', to: '/account' },
      'privacy.rights.how',
    ],
  },
  {
    id: 'privacy-security',
    title: 'privacy.security.title',
    blocks: [
      [
        'privacy.security.password',
        'privacy.security.cookie',
        'privacy.security.uploads',
        'privacy.security.rate',
        'privacy.security.https',
      ],
      'privacy.security.honest',
    ],
  },
  {
    id: 'privacy-changes',
    title: 'privacy.changes.title',
    blocks: ['privacy.changes.p1'],
  },
  {
    id: 'privacy-contact',
    title: 'privacy.contact.title',
    blocks: ['privacy.contact.p1', { key: 'privacy.contact.link', to: '/contact' }],
  },
];

// The operator, and the address a data request goes to, are the two facts
// this page cannot know. They render as a panel at the top until filled.
const UNFILLED = ['legal.field.entity', 'legal.field.dataContact'];

export default function Privacy() {
  return (
    <LegalPage
      title="privacy.title"
      blurb="privacy.blurb"
      sections={SECTIONS}
      unfilled={UNFILLED}
    />
  );
}
