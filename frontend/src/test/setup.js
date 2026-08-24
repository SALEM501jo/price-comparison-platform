import '@testing-library/jest-dom/vitest';
import { cleanup } from '@testing-library/react';
import { afterEach } from 'vitest';

// Without this a component from one test is still mounted during the next,
// and queries match elements the current test never rendered.
afterEach(cleanup);
