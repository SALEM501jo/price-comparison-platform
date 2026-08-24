import { useMemo } from 'react';
import { formatPrice } from '../../utils/format';

// One colour per store series. Chosen to stay distinguishable in greyscale
// too, since screenshots and printed CVs lose colour.
const SERIES_COLORS = ['#2563eb', '#16a34a', '#ea580c', '#9333ea', '#0891b2'];

const WIDTH = 720;
const HEIGHT = 260;
const PADDING = { top: 16, right: 16, bottom: 28, left: 56 };

/**
 * Price history per store, as an inline SVG line chart.
 *
 * Deliberately not a charting library: this needs axes, a few polylines and a
 * legend, and every option weighs 50-150 kB gzipped. That is a large fraction
 * of the whole bundle for one screen.
 */
export default function PriceHistoryChart({ series }) {
  const chart = useMemo(() => {
    const withData = (series ?? []).filter((s) => s.history?.length > 0);
    if (withData.length === 0) return null;

    const points = withData.flatMap((s) =>
      s.history.map((h) => ({ t: new Date(h.recorded_at).getTime(), price: h.price })),
    );

    const times = points.map((p) => p.t);
    const prices = points.map((p) => p.price);

    const minT = Math.min(...times);
    const maxT = Math.max(...times);
    let minP = Math.min(...prices);
    let maxP = Math.max(...prices);

    // Pad the value axis so lines do not sit flat against the edges, and
    // guard the single-value case where min === max would divide by zero.
    const spread = maxP - minP || Math.max(maxP * 0.1, 1);
    minP -= spread * 0.1;
    maxP += spread * 0.1;

    const plotW = WIDTH - PADDING.left - PADDING.right;
    const plotH = HEIGHT - PADDING.top - PADDING.bottom;

    const x = (t) =>
      PADDING.left + (maxT === minT ? plotW / 2 : ((t - minT) / (maxT - minT)) * plotW);
    const y = (p) => PADDING.top + plotH - ((p - minP) / (maxP - minP)) * plotH;

    return {
      series: withData.map((s, i) => ({
        name: s.store_name,
        color: SERIES_COLORS[i % SERIES_COLORS.length],
        points: [...s.history]
          .sort((a, b) => new Date(a.recorded_at) - new Date(b.recorded_at))
          .map((h) => ({
            x: x(new Date(h.recorded_at).getTime()),
            y: y(h.price),
            price: h.price,
            at: h.recorded_at,
          })),
      })),
      yTicks: [minP, (minP + maxP) / 2, maxP].map((p) => ({ value: p, y: y(p) })),
      xLabels: [
        { label: new Date(minT).toLocaleDateString(), x: PADDING.left, anchor: 'start' },
        {
          label: new Date(maxT).toLocaleDateString(),
          x: WIDTH - PADDING.right,
          anchor: 'end',
        },
      ],
    };
  }, [series]);

  if (!chart) {
    return (
      <p className="rounded-lg border border-dashed border-gray-300 px-4 py-8 text-center text-sm text-gray-500">
        No price changes recorded yet. History builds up as stores change their
        prices between scrapes.
      </p>
    );
  }

  return (
    <div className="rounded-lg border border-gray-200 bg-white p-4">
      <div className="overflow-x-auto">
        <svg
          viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
          className="h-auto w-full min-w-[520px]"
          role="img"
          aria-label="Price history by store"
        >
          {chart.yTicks.map((tick) => (
            <g key={tick.value}>
              <line
                x1={PADDING.left}
                x2={WIDTH - PADDING.right}
                y1={tick.y}
                y2={tick.y}
                stroke="#e5e7eb"
                strokeWidth="1"
              />
              <text
                x={PADDING.left - 8}
                y={tick.y + 4}
                textAnchor="end"
                className="fill-gray-400"
                fontSize="11"
              >
                {tick.value.toFixed(0)}
              </text>
            </g>
          ))}

          {chart.xLabels.map((label) => (
            <text
              key={label.label + label.anchor}
              x={label.x}
              y={HEIGHT - 8}
              textAnchor={label.anchor}
              className="fill-gray-400"
              fontSize="11"
            >
              {label.label}
            </text>
          ))}

          {chart.series.map((s) => (
            <g key={s.name}>
              <polyline
                fill="none"
                stroke={s.color}
                strokeWidth="2"
                strokeLinejoin="round"
                strokeLinecap="round"
                points={s.points.map((p) => `${p.x},${p.y}`).join(' ')}
              />
              {s.points.map((p) => (
                <circle key={`${p.at}-${p.price}`} cx={p.x} cy={p.y} r="3" fill={s.color}>
                  <title>
                    {s.name}: {formatPrice(p.price)} on{' '}
                    {new Date(p.at).toLocaleDateString()}
                  </title>
                </circle>
              ))}
            </g>
          ))}
        </svg>
      </div>

      <ul className="mt-3 flex flex-wrap gap-4">
        {chart.series.map((s) => (
          <li key={s.name} className="flex items-center gap-2 text-sm text-gray-600">
            <span
              className="inline-block h-2.5 w-2.5 rounded-full"
              style={{ backgroundColor: s.color }}
            />
            {s.name}
          </li>
        ))}
      </ul>
    </div>
  );
}
