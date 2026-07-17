import Link from 'next/link';
import { fmt, timeAgo } from '@/lib/api';

export default function RepoCard({ repo }) {
  const href = `/repos/${repo.owner}/${repo.name}`;
  return (
    <div className="card flex flex-col gap-2 p-4 transition-colors hover:border-accent/40">
      <div className="flex items-center gap-2">
        {repo.logo_url ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={repo.logo_url} alt="" className="h-7 w-7 rounded-md" />
        ) : (
          <div className="h-7 w-7 rounded-md bg-zinc-800" />
        )}
        <Link href={href} className="truncate font-medium text-zinc-100 hover:text-accent">
          {repo.full_name}
        </Link>
        {repo.trending_flag && <span title="GitHub Trending hôm nay">📈</span>}
        <span className="ml-auto shrink-0 text-xs font-semibold text-orange-400">
          🔥 {repo.hot_score?.toFixed ? repo.hot_score.toFixed(0) : repo.hot_score}
        </span>
      </div>

      <p className="line-clamp-2 min-h-[2.5rem] text-sm text-zinc-400">{repo.description || '—'}</p>

      <div className="flex flex-wrap gap-1">
        {(repo.categories || []).slice(0, 3).map((c) => (
          <Link key={c.slug} href={`/repos?category=${c.slug}`} className="badge">
            {c.name}
          </Link>
        ))}
        {(repo.topics || []).slice(0, 3).map((t) => (
          <span key={t} className="chip">{t}</span>
        ))}
      </div>

      <div className="mt-auto flex items-center gap-3 pt-1 text-xs text-zinc-500">
        <span className="text-zinc-300">★ {fmt(repo.stars)}</span>
        {repo.star_growth_7d > 0 && (
          <span className="text-emerald-400">+{fmt(repo.star_growth_7d)}/7d</span>
        )}
        {repo.language && <span>{repo.language}</span>}
        {repo.license && <span>{repo.license}</span>}
        <span className="ml-auto">{timeAgo(repo.last_commit_at)}</span>
      </div>
    </div>
  );
}
