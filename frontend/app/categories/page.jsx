import Link from 'next/link';
import { api } from '@/lib/api';

export const dynamic = 'force-dynamic';

export default async function CategoriesPage() {
  const cats = await api('/api/v1/categories');
  return (
    <div>
      <h1 className="mb-4 text-xl font-semibold text-zinc-100">Categories</h1>
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {(cats?.data || []).map((c) => (
          <Link key={c.slug} href={`/repos?category=${c.slug}`} className="card p-4 transition-colors hover:border-accent/40">
            <div className="font-medium text-zinc-100">{c.name}</div>
            <div className="mt-1 text-sm text-zinc-500">{c.repo_count} projects</div>
          </Link>
        ))}
      </div>
    </div>
  );
}
