-- Sửa các lần crawl đã báo success sai trước khi có classify_run. Chạy một lần.
UPDATE crawl_runs SET status = 'failed',
  error = concat_ws(E'\n', error, 'Sửa 2026-10-30: báo success sai, track updated=0 (GitHub 401).')
WHERE id = 17 AND status = 'success';

UPDATE crawl_runs SET status = 'partial',
  error = concat_ws(E'\n', error, 'Sửa 2026-10-30: báo success sai, track lỗi hoặc updated=0.')
WHERE id IN (1, 2, 3, 15) AND status = 'success';
