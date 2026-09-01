import '@testing-library/jest-dom/vitest';
import { cleanup } from '@testing-library/react';
import { afterEach } from 'vitest';

// Without this a component from one test is still mounted during the next,
// and queries match elements the current test never rendered.
afterEach(cleanup);

// jsdom implements no object-URL store, so any component that previews a
// picked file -- the merchant photo picker, the listing thumbnails -- throws
// on sight rather than failing an assertion.
//
// Counted rather than stubbed blind: forgetting to revoke an object URL leaks
// the whole file for the life of the tab, and that is invisible in a browser
// until a shop owner has re-picked a dozen photos. Tests can assert the books
// balance.
let objectUrlCount = 0;

if (!URL.createObjectURL) {
  URL.createObjectURL = () => `blob:test/${(objectUrlCount += 1)}`;
  URL.revokeObjectURL = () => {
    objectUrlCount -= 1;
  };
}

export const liveObjectUrls = () => objectUrlCount;
