import Link from 'next/link';

export default function Nav() {
  return (
    <header className="sticky top-0 z-20 border-b border-edge bg-surface/80 backdrop-blur">
      <div className="mx-auto flex max-w-6xl items-center gap-6 px-4 py-3">
        <Link href="/" className="flex items-center gap-2 font-semibold text-zinc-100">
          <span className="text-accent">◆</span> AI Trend Radar
        </Link>
        <nav className="flex items-center gap-4 text-sm text-zinc-400">
          <Link href="/repos" className="hover:text-zinc-100">Projects</Link>
          <Link href="/categories" className="hover:text-zinc-100">Categories</Link>
          <Link href="/repos?sort=new" className="hover:text-zinc-100">Mới</Link>
        </nav>
        <form action="/repos" className="ml-auto">
          <input
            name="q"
            placeholder="Tìm repo, owner:..., tag:...  ↵"
            className="w-64"
            autoComplete="off"
          />
        </form>
      </div>
    </header>
  );
}
