export default function Sparkline({ values = [], width = 120, height = 32 }) {
  if (!values || values.length < 2) {
    return <span className="text-[10px] text-zinc-600">chưa đủ dữ liệu</span>;
  }
  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = max - min || 1;
  const pts = values
    .map((v, i) => {
      const x = (i / (values.length - 1)) * (width - 2) + 1;
      const y = height - 2 - ((v - min) / range) * (height - 4);
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(' ');
  return (
    <svg width={width} height={height} className="overflow-visible">
      <polyline points={pts} fill="none" stroke="#6d8dff" strokeWidth="1.5" strokeLinejoin="round" />
    </svg>
  );
}
