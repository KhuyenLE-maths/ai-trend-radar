import Link from 'next/link';
import FilterBar from '@/components/FilterBar';
import RepoCard from '@/components/RepoCard';
import { api } from '@/lib/api';

export const dynamic = 'force-dynamic';

export default async function ReposPage({ searchParams }) {
  const sp = searchParams || {};
  const qs = new URLSearchParams();
  for (const k of ['category', 'language', 'license', 'min_stars', 'updated_within', 'sort', 'page']) {
    if (sp[k]) qs.set(k, sp[k]);
  }

  let result;
  if (sp.q) {
    const sqs = new URLSearchParams({ q: sp.q });
    if (sp.page) sqs.set('page', sp.page);
    result = await api(`/api/v1/search?${sqs.toString()}`);
  } else {
    result = await api(`/api/v1/repos?${qs.toString()}`);
  }
  const cats = await api('/api/v1/categories');

  const data = result?.data || [];
  const pg = result?.pagination || { page: 1, per_page: 24, total: 0 };
  const lastPage = Math.max(1, Math.ceil(pg.total / pg.per_page));

  const pageLink = (p) => {
    const next = new URLSearchParams();
    if (sp.q) next.set('q', sp.q);
    for (const [k, v] of qs.entries()) if (k !== 'page') next.set(k, v);
    next.set('page', String(p));
    return `/repos?${next.toString()}`;
  };

  return (
    <div>
      <div className="mb-4 flex items-baseline gap-3">
        <h1 className="text-xl font-semibold text-zinc-100">
          {sp.q ? `Kết quả cho “${sp.q}”` : 'AI Projects'}
        </h1>
        <span className="text-sm text-zinc-500">{pg.total} repo</span>
      </div>

      {!sp.q && <FilterBar categories={cats?.data || []} />}

      {data.length === 0 ? (
        <div className="card p-8 text-center text-sm text-zinc-500">
          Không có kết quả. {sp.q ? 'Thử từ khoá khác hoặc operator owner:/tag:/category:.' : 'Nới lỏng bộ lọc hoặc chạy crawl lần đầu (xem README).'}
        </div>
      ) : (
        <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-3">
          {data.map((r) => <RepoCard key={r.full_name} repo={r} />)}
        </div>
      )}

      {lastPage > 1 && (
        <div className="mt-6 flex items-center justify-center gap-3 text-sm">
          {pg.page > 1 && <Link href={pageLink(pg.page - 1)} className="chip hover:text-zinc-100">← Trước</Link>}
          <span className="text-zinc-500">Trang {pg.page}/{lastPage}</span>
          {pg.page < lastPage && <Link href={pageLink(pg.page + 1)} className="chip hover:text-zinc-100">Sau →</Link>}
        </div>
      )}
    </div>
  );
}
