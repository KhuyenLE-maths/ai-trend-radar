import './globals.css';
import Nav from '@/components/Nav';

export const metadata = {
  title: 'AI Trend Radar',
  description: 'Theo dõi công cụ AI nổi bật trên GitHub, cập nhật hàng ngày',
};

export default function RootLayout({ children }) {
  return (
    <html lang="vi">
      <body>
        <Nav />
        <main className="mx-auto max-w-6xl px-4 py-6">{children}</main>
        <footer className="mx-auto max-w-6xl px-4 py-8 text-xs text-zinc-600">
          AI Trend Radar — dữ liệu GitHub cập nhật hàng ngày · nội bộ
        </footer>
      </body>
    </html>
  );
}
