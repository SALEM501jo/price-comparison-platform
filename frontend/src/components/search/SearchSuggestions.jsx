import { useEffect, useMemo, useRef, useState } from 'react';
import { getSuggestions } from '../../api/products';

/**
 * Type-ahead suggestions, drawn from the catalogue.
 *
 * WHY REAL PRODUCTS RATHER THAN GENERATED PHRASES: this platform's whole
 * argument is that a shopper should say which variant they mean -- "iPhone 15
 * 128GB Black" rather than "iPhone" -- because that is the only query the
 * matching engine can answer precisely. A list of real catalogue entries
 * teaches that by example, and every suggestion is guaranteed to lead
 * somewhere. A generated word list can promise neither.
 *
 * The request is debounced and abortable: a keystroke fires on every letter,
 * and without both, a fast typist queues eight requests whose answers arrive
 * out of order and fight over the dropdown.
 */
export default function SearchSuggestions({ query, onPick, onDismiss }) {
  const [items, setItems] = useState([]);
  const [highlighted, setHighlighted] = useState(-1);
  const listRef = useRef(null);

  const trimmed = query.trim();
  // DERIVED, not stored. Clearing the list by calling setItems([]) inside the
  // effect is a state write during render's commit phase, which React (and
  // the lint rule) rightly objects to -- and it is unnecessary: whether a
  // short query shows anything is a function of the query, not a fact worth
  // keeping in state.
  // Memoised so the array identity is stable: the keyboard effect below
  // depends on it, and a fresh [] every render would re-bind the window
  // listener on every keystroke.
  const visible = useMemo(
    () => (trimmed.length >= 2 ? items : []),
    [trimmed, items],
  );

  useEffect(() => {
    if (trimmed.length < 2) return undefined;

    const controller = new AbortController();
    // 180ms: long enough that a normal typing burst produces one request,
    // short enough that the list feels attached to the keyboard.
    const timer = setTimeout(() => {
      getSuggestions(trimmed, { signal: controller.signal })
        .then((results) => {
          setItems(results);
          setHighlighted(-1);
        })
        .catch(() => {
          // Suggestions are a convenience. A failure here must leave the
          // search box working exactly as it did before they existed.
          setItems([]);
        });
    }, 180);

    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [trimmed]);

  // Keyboard navigation is not optional for a control that intercepts Enter:
  // without it, a keyboard user who has typed a full query cannot submit.
  useEffect(() => {
    const onKey = (event) => {
      if (!visible.length) return;
      if (event.key === 'ArrowDown') {
        event.preventDefault();
        setHighlighted((i) => (i + 1) % visible.length);
      } else if (event.key === 'ArrowUp') {
        event.preventDefault();
        setHighlighted((i) => (i <= 0 ? visible.length - 1 : i - 1));
      } else if (event.key === 'Enter' && highlighted >= 0) {
        event.preventDefault();
        onPick(visible[highlighted]);
      } else if (event.key === 'Escape') {
        onDismiss();
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [visible, highlighted, onPick, onDismiss]);

  if (!visible.length) return null;

  return (
    <ul
      ref={listRef}
      role="listbox"
      className="absolute z-20 mt-1 w-full overflow-hidden rounded-xl border border-gray-200 bg-white shadow-lg dark:border-gray-700 dark:bg-gray-900"
    >
      {visible.map((item, index) => (
        <li key={item.product_id} role="option" aria-selected={index === highlighted}>
          <button
            type="button"
            // onMouseDown, not onClick: the input's blur fires first and
            // would unmount this list before a click ever landed.
            onMouseDown={(event) => {
              event.preventDefault();
              onPick(item);
            }}
            onMouseEnter={() => setHighlighted(index)}
            dir="auto"
            className={`block w-full px-4 py-2 text-start text-sm transition ${
              index === highlighted
                ? 'bg-gray-100 dark:bg-gray-800'
                : 'bg-transparent'
            } text-gray-800 dark:text-gray-200`}
          >
            <span className="block truncate">{item.label}</span>
            {item.brand && (
              <span className="block text-xs uppercase tracking-wide text-gray-400 dark:text-gray-500">
                {item.brand}
              </span>
            )}
          </button>
        </li>
      ))}
    </ul>
  );
}
