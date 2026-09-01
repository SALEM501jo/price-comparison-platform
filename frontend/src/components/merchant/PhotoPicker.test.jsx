import { fireEvent, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { renderWithProviders as render } from '../../test/render';
import { liveObjectUrls } from '../../test/setup';
import PhotoPicker from './PhotoPicker';

/**
 * The client-side checks here are a courtesy, not a control -- the server
 * re-decodes every upload and enforces the same limits. What these tests
 * protect is the courtesy: a shop owner on a phone finding out their photo is
 * wrong while looking at the form, instead of after waiting for an upload.
 */

const file = (name, type, size = 1024) => {
  const made = new File(['x'], name, { type });
  // File size is read-only, and a real 9MB fixture would be silly to build.
  Object.defineProperty(made, 'size', { value: size });
  return made;
};

const pick = (input, picked) =>
  fireEvent.change(input, { target: { files: [picked] } });

describe('PhotoPicker', () => {
  it('invites a photo when there is none', () => {
    render(<PhotoPicker file={null} onPick={vi.fn()} />);
    expect(screen.getByLabelText('Add photo')).toBeInTheDocument();
  });

  it('hands a good file straight to the caller', () => {
    const onPick = vi.fn();
    const { container } = render(<PhotoPicker file={null} onPick={onPick} />);

    const chosen = file('shop.jpg', 'image/jpeg');
    pick(container.querySelector('input[type="file"]'), chosen);

    expect(onPick).toHaveBeenCalledWith(chosen);
  });

  it('refuses a file that is not one of the accepted formats', () => {
    const onPick = vi.fn();
    const { container } = render(<PhotoPicker file={null} onPick={onPick} />);

    pick(container.querySelector('input[type="file"]'), file('scan.pdf', 'application/pdf'));

    expect(onPick).not.toHaveBeenCalled();
    expect(screen.getByRole('alert')).toHaveTextContent(/JPG, PNG or WebP/);
  });

  it('refuses an oversized file before uploading it', () => {
    const onPick = vi.fn();
    const { container } = render(<PhotoPicker file={null} onPick={onPick} />);

    pick(
      container.querySelector('input[type="file"]'),
      file('huge.jpg', 'image/jpeg', 9 * 1024 * 1024),
    );

    expect(onPick).not.toHaveBeenCalled();
    expect(screen.getByRole('alert')).toHaveTextContent(/larger than 8MB/);
  });

  it('says the size limit in the hint, not as a raw placeholder', () => {
    // The hint carries a {mb} placeholder; forgetting to pass it renders
    // "up to {mb}MB" to a shop owner.
    render(<PhotoPicker file={null} onPick={vi.fn()} />);
    expect(screen.getByText(/up to 8MB/)).toBeInTheDocument();
    expect(screen.queryByText(/\{mb\}/)).not.toBeInTheDocument();
  });

  it('offers change and remove once a photo is chosen', () => {
    render(<PhotoPicker file={file('shop.jpg', 'image/jpeg')} onPick={vi.fn()} />);
    expect(screen.getByText('Change photo')).toBeInTheDocument();
    expect(screen.getByText('Remove photo')).toBeInTheDocument();
  });

  it('clears the chosen photo when asked', () => {
    const onPick = vi.fn();
    render(<PhotoPicker file={file('shop.jpg', 'image/jpeg')} onPick={onPick} />);

    fireEvent.click(screen.getByText('Remove photo'));
    expect(onPick).toHaveBeenCalledWith(null);
  });

  it('does not leak the preview when it goes away', () => {
    // An object URL pins the whole file in memory until it is revoked or the
    // tab closes. A shop owner trying four photos for one listing would hold
    // all four -- invisible in a browser, and exactly the kind of thing that
    // only shows up on a cheap phone.
    const before = liveObjectUrls();
    const { unmount } = render(
      <PhotoPicker file={file('shop.jpg', 'image/jpeg')} onPick={vi.fn()} />,
    );
    expect(liveObjectUrls()).toBe(before + 1);

    unmount();
    expect(liveObjectUrls()).toBe(before);
  });

  it('reads the whole picker in Arabic', () => {
    // The people this form is for read Arabic first. A form that is half
    // translated is worse than one that is not, because it looks unfinished.
    const { container } = render(<PhotoPicker file={null} onPick={vi.fn()} />, {
      locale: 'ar',
    });
    const text = container.textContent;
    expect(text).toMatch(/[؀-ۿ]/);
    // The format names are legitimately Latin; nothing else should be.
    expect(text.replace(/JPG|PNG|WebP/g, '')).not.toMatch(/[a-zA-Z]{4,}/);
  });
});
