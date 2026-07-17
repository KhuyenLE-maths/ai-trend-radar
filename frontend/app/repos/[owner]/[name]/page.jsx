import Link from 'next/link';
import RepoCard from '@/components/RepoCard';
import Sparkline from '@/components/Sparkline';
import { api, fmt, timeAgo } from '@/lib/api';

export const dynamic = 'force-dynamic';

function ListBlock({ title, items, tone = 'zinc' }) {
  if (!items || items.length === 0) return null;
  return (
    <div>
      <h4 className={`mb-1 text-xs font-semibold uppercase tracking-wide text-${tone}-400`}>{title}</h4>
      <ul className="list-disc space-y-0.5 pl-5 text-sm text-zinc-300">
        {items.map((x, i) => <li key={i}>{x}</li>)}
      </ul>
    </div>
  );
}

export default async function RepoDetail({ params }) {
  const repo = await api(`/api/v1/repos/${params.owner}/${params.name}`);
  if (!repo) {
    return <div className="card p-8 text-center text-zinc-400">Không tìm thấy repository này.</div>;
  }
  const s = repo.ai_summary?.content;

  return (
    <div className="flex flex-col gap-6">
      <header className="card p-5">
        <div className="flex flex-wrap items-center gap-3">
          {repo.logo_url && (
            // eslint-disable-next-line @next/next/no-img-element
            <img src={repo.logo_url} alt="" className="h-10 w-10 rounded-lg" />
          )}
          <h1 className="text-xl font-semibold text-zinc-100">{repo.full_name}</h1>
          {repo.trending_flag && <span className="badge">📈 Trending</span>}
          <span className="text-sm font-semibold text-orange-400">🔥 Hot {repo.hot_score}</span>
          <div className="ml-auto flex gap-2 text-sm">
            <a href={repo.url} target="_blank" rel="noreferrer" className="chip hover:text-zinc-100">★ GitHub</a>
            {repo.homepage && (
              <a href={repo.homepage} target="_blank" rel="noreferrer" className="chip hover:text-zinc-100">🌐 Website</a>
            )}
          </div>
        </div>
        <p className="mt-2 text-zinc-400">{repo.description}</p>
        <div className="mt-3 flex flex-wrap gap-1">
          {(repo.categories || []).map((c) => (
            <Link key={c.slug} href={`/repos?category=${c.slug}`} className="badge">{c.name}</Link>
          ))}
          {(repo.topics || []).slice(0, 8).map((t) => <span key={t} className="chip">{t}</span>)}
        </div>
      </header>

      <div className="grid gap-6 lg:grid-cols-5">
        <section className="card p-5 lg:col-span-3">
          <div className="mb-3 flex items-center gap-2">
            <h2 className="font-semibold text-zinc-100">✨ AI Summary</h2>
            {repo.ai_summary && (
              <span className="text-xs text-zinc-500">
                {repo.ai_summary.model} · {timeAgo(repo.ai_summary.created_at)}
              </span>
            )}
          </div>
          {!s ? (
            <p className="text-sm text-zinc-500">
              Chưa có AI summary cho repo này. Summary được sinh tự động hàng ngày cho các repo thuộc Top Hot
              (cần cấu hình ANTHROPIC_API_KEY).
            </p>
          ) : (
            <div className="flex flex-col gap-4">
              <p className="rounded-lg bg-accent/5 p-3 text-sm text-zinc-200">{s.tldr}</p>
              {s.purpose && <p className="text-sm text-zinc-300">{s.purpose}</p>}
              <div className="flex flex-wrap gap-2 text-xs">
                {s.difficulty && <span className="chip">Độ khó: {s.difficulty}</span>}
                {s.maturity && <span className="chip">Maturity: {s.maturity}</span>}
                {(s.target_users || []).map((u) => <span key={u} className="chip">{u}</span>)}
              </div>
              <div className="grid gap-4 sm:grid-cols-2">
                <ListBlock title="✅ Nên dùng khi" items={s.when_to_use} tone="emerald" />
                <ListBlock title="🚫 Không nên khi" items={s.when_not_to_use} tone="rose" />
                <ListBlock title="Tính năng chính" items={s.key_features} />
                <ListBlock title="Công nghệ liên quan" items={s.related_tech} />
                <ListBlock title="Ưu điểm" items={s.pros} tone="emerald" />
                <ListBlock title="Nhược điểm" items={s.cons} tone="rose" />
              </div>
              {s.architecture_notes && (
                <p className="text-sm text-zinc-400"><b className="text-zinc-300">Kiến trúc:</b> {s.architecture_notes}</p>
              )}
              {(s.alternatives || []).length > 0 && (
                <div className="text-sm text-zinc-300">
                  <b>So sánh:</b>{' '}
                  {s.alternatives.map((a, i) => (
                    <span key={i}>
                      <Link className="text-accent hover:underline" href={`/repos/${a.repo}`}>{a.repo}</Link>
                      {a.note ? ` — ${a.note}` : ''}{i < s.alternatives.length - 1 ? ' · ' : ''}
                    </span>
                  ))}
                </div>
              )}
              <p className="text-[11px] text-zinc-600">
                ✨ Nội dung do AI sinh tự động từ README — hãy kiểm chứng trước khi ra quyết định quan trọng.
              </p>
            </div>
          )}
        </section>

        <section className="flex flex-col gap-4 lg:col-span-2">
          <div className="card p-5">
            <h3 className="mb-2 font-semibold text-zinc-100">📈 Stars 30 ngày</h3>
            <Sparkline values={repo.sparkline_30d} width={260} height={56} />
            <dl className="mt-3 grid grid-cols-2 gap-x-4 gap-y-1.5 text-sm">
              <dt className="text-zinc-500">Stars</dt><dd className="text-right text-zinc-200">★ {fmt(repo.stars)}</dd>
              <dt className="text-zinc-500">Growth 7d / 30d</dt>
              <dd className="text-right text-emerald-400">+{fmt(repo.star_growth_7d)} / +{fmt(repo.star_growth_30d)}</dd>
              <dt className="text-zinc-500">Forks</dt><dd className="text-right text-zinc-200">{fmt(repo.forks)}</dd>
              <dt className="text-zinc-500">Contributors</dt><dd className="text-right text-zinc-200">{fmt(repo.contributors)}</dd>
              <dt className="text-zinc-500">Open issues</dt><dd className="text-right text-zinc-200">{fmt(repo.open_issues)}</dd>
              <dt className="text-zinc-500">Ngôn ngữ</dt><dd className="text-right text-zinc-200">{repo.language || '–'}</dd>
              <dt className="text-zinc-500">License</dt><dd className="text-right text-zinc-200">{repo.license || '–'}</dd>
              <dt className="text-zinc-500">Commit cuối</dt><dd className="text-right text-zinc-200">{timeAgo(repo.last_commit_at)}</dd>
              <dt className="text-zinc-500">Tạo lúc</dt><dd className="text-right text-zinc-200">{timeAgo(repo.repo_created_at)}</dd>
            </dl>
          </div>

          {(repo.mentions || []).length > 0 && (
            <div className="card p-5">
              <h3 className="mb-2 font-semibold text-zinc-100">💬 Cộng đồng nhắc tới</h3>
              <ul className="space-y-2 text-sm">
                {repo.mentions.map((m, i) => (
                  <li key={i}>
                    <a href={m.url} target="_blank" rel="noreferrer" className="text-zinc-300 hover:text-accent">
                      [{m.source}] {m.title}
                    </a>
                    <span className="ml-1 text-xs text-zinc-600">▲{m.score}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </section>
      </div>

      {(repo.similar || []).length > 0 && (
        <section>
          <h2 className="mb-3 text-lg font-semibold text-zinc-100">⚖ Công cụ tương tự</h2>
          <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-3">
            {repo.similar.map((r) => <RepoCard key={r.full_name} repo={r} />)}
          </div>
        </section>
      )}
    </div>
  );
}
