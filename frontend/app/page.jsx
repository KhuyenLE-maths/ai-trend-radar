import Link from 'next/link';
import RepoCard from '@/components/RepoCard';
import { api, fmt } from '@/lib/api';

export const dynamic = 'force-dynamic';

function StatTile({ label, value, sub }) {
  return (
    <div className="card p-4">
      <div className="text-2xl font-semibold text-zinc-100">{value ?? '–'}</div>
      <div className="text-sm text-zinc-400">{label}</div>
      {sub && <div className="mt-1 truncate text-xs text-zinc-500">{sub}</div>}
    </div>
  );
}

export default async function Dashboard() {
  const [stats, day, updates, cats] = await Promise.all([
    api('/api/v1/stats/dashboard'),
    api('/api/v1/trending?period=day&limit=9'),
    api('/api/v1/updates/daily?limit=6'),
    api('/api/v1/categories'),
  ]);

  if (!stats) {
    return (
      <div className="card p-8 text-center text-zinc-400">
        <p className="mb-2 text-lg">⏳ Chưa kết nối được API hoặc chưa có dữ liệu.</p>
        <p className="text-sm">
          Chạy crawl lần đầu: <code className="rounded bg-zinc-800 px-1">POST /api/v1/admin/crawl</code> (xem README).
        </p>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-8">
      <section className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <StatTile label="Projects đang theo dõi" value={fmt(stats.total_repos)} />
        <StatTile
          label="Mới hôm nay"
          value={`+${stats.new_today ?? 0}`}
          sub={stats.new_yesterday ? `hôm qua: +${stats.new_yesterday}` : null}
        />
        <StatTile
          label="Top tuần"
          value={stats.top_weekly ? `+${fmt(stats.top_weekly.star_growth_7d)}★` : '–'}
          sub={stats.top_weekly?.full_name}
        />
        <StatTile
          label="Top tháng"
          value={stats.top_monthly ? `+${fmt(stats.top_monthly.star_growth_30d)}★` : '–'}
          sub={stats.top_monthly?.full_name}
        />
      </section>

      <section>
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-lg font-semibold text-zinc-100">🔥 Trending hôm nay</h2>
          <div className="flex gap-2 text-xs">
            <Link href="/repos?sort=hot" className="chip hover:text-zinc-200">Ngày</Link>
            <Link href="/repos?sort=growth_7d" className="chip hover:text-zinc-200">Tuần</Link>
            <Link href="/repos?sort=growth_30d" className="chip hover:text-zinc-200">Tháng</Link>
          </div>
        </div>
        <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-3">
          {(day?.data || []).map((r) => <RepoCard key={r.full_name} repo={r} />)}
        </div>
      </section>

      <div className="grid gap-6 md:grid-cols-2">
        <section>
          <h2 className="mb-3 text-lg font-semibold text-zinc-100">📂 Top categories</h2>
          <div className="card divide-y divide-edge">
            {(stats.top_categories || []).map((c) => (
              <Link
                key={c.slug}
                href={`/repos?category=${c.slug}`}
                className="flex items-center justify-between px-4 py-2.5 text-sm hover:bg-zinc-800/40"
              >
                <span className="text-zinc-300">{c.name}</span>
                <span className="text-zinc-500">{c.repo_count}</span>
              </Link>
            ))}
          </div>
        </section>

        <section>
          <h2 className="mb-3 text-lg font-semibold text-zinc-100">🆕 Mới phát hiện hôm nay</h2>
          <div className="card divide-y divide-edge">
            {(updates?.new_repos || []).length === 0 && (
              <div className="px-4 py-3 text-sm text-zinc-500">Chưa có repo mới hôm nay.</div>
            )}
            {(updates?.new_repos || []).map((r) => (
              <Link
                key={r.full_name}
                href={`/repos/${r.owner}/${r.name}`}
                className="flex items-center gap-2 px-4 py-2.5 text-sm hover:bg-zinc-800/40"
              >
                <span className="truncate text-zinc-300">{r.full_name}</span>
                <span className="ml-auto shrink-0 text-zinc-500">★ {fmt(r.stars)}</span>
              </Link>
            ))}
          </div>
        </section>
      </div>
    </div>
  );
}
