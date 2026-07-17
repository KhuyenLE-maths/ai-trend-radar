'use client';

import { useRouter, useSearchParams } from 'next/navigation';

const LANGS = ['Python', 'TypeScript', 'JavaScript', 'Rust', 'Go', 'C++', 'Jupyter Notebook'];
const SORTS = [
  ['hot', '🔥 Hot'],
  ['new', '🆕 Mới phát hiện'],
  ['stars', '★ Stars'],
  ['growth_7d', '▲ Growth 7d'],
  ['growth_30d', '▲ Growth 30d'],
];

export default function FilterBar({ categories = [] }) {
  const router = useRouter();
  const sp = useSearchParams();

  const set = (key, value) => {
    const next = new URLSearchParams(sp.toString());
    if (value) next.set(key, value);
    else next.delete(key);
    next.delete('page');
    router.push(`/repos?${next.toString()}`);
  };

  return (
    <div className="card mb-5 flex flex-wrap items-center gap-2 p-3 text-sm">
      <select value={sp.get('sort') || 'hot'} onChange={(e) => set('sort', e.target.value)}>
        {SORTS.map(([v, label]) => (
          <option key={v} value={v}>{label}</option>
        ))}
      </select>

      <select value={sp.get('category') || ''} onChange={(e) => set('category', e.target.value)}>
        <option value="">Mọi category</option>
        {categories.map((c) => (
          <option key={c.slug} value={c.slug}>
            {c.name} ({c.repo_count})
          </option>
        ))}
      </select>

      <select value={sp.get('language') || ''} onChange={(e) => set('language', e.target.value)}>
        <option value="">Mọi ngôn ngữ</option>
        {LANGS.map((l) => (
          <option key={l} value={l}>{l}</option>
        ))}
      </select>

      <select value={sp.get('min_stars') || ''} onChange={(e) => set('min_stars', e.target.value)}>
        <option value="">★ bất kỳ</option>
        <option value="100">★ ≥ 100</option>
        <option value="1000">★ ≥ 1k</option>
        <option value="10000">★ ≥ 10k</option>
      </select>

      <select value={sp.get('updated_within') || ''} onChange={(e) => set('updated_within', e.target.value)}>
        <option value="">Cập nhật bất kỳ</option>
        <option value="7">Trong 7 ngày</option>
        <option value="30">Trong 30 ngày</option>
        <option value="90">Trong 90 ngày</option>
      </select>

      {sp.toString() && (
        <button onClick={() => router.push('/repos')} className="ml-auto text-xs text-zinc-500 hover:text-zinc-200">
          ✕ Xoá bộ lọc
        </button>
      )}
    </div>
  );
}
