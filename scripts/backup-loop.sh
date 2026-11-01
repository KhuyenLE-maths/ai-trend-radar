#!/bin/sh
# Backup sau mỗi lần crawl kết thúc. Không bao giờ xoá file .dump.
marker=/backups/.last_run_id
while true; do
  latest=$(psql -Atc "SELECT coalesce(max(id), 0) FROM crawl_runs WHERE finished_at IS NOT NULL" 2>/dev/null)
  done_id=$(cat "$marker" 2>/dev/null || echo 0)
  if [ -n "$latest" ] && [ "$latest" -gt "$done_id" ]; then
    sh /scripts/backup-once.sh && echo "$latest" > "$marker"
  fi
  sleep 300
done
