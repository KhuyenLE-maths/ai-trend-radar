#!/usr/bin/env bash
# Lệnh vận hành AI Trend Radar trên máy này.
set -euo pipefail
cd "$(dirname "$0")/.."

env_value() { grep -E "^$1=" .env | tail -1 | cut -d= -f2-; }

cmd_up() {
  [ -f .env ] || { echo "Thiếu .env. Chạy: cp .env.example .env rồi điền GITHUB_TOKEN." >&2; exit 1; }
  mkdir -p data/postgres data/raw data/backups
  docker compose up -d --build
  echo "Web: http://localhost:3000"
}

cmd_down() { docker compose down; }

cmd_backup() { docker compose exec -T backup sh /scripts/backup-once.sh; }

cmd_update() {
  cmd_backup
  git pull --ff-only
  cmd_up
}

cmd_crawl() {
  local port
  port=$(env_value API_PORT || true)
  curl -fsS -X POST -H "X-Admin-Token: $(env_value ADMIN_TOKEN)" \
    "http://127.0.0.1:${port:-8001}/api/v1/admin/crawl"
  echo
}

cmd_status() {
  docker compose ps
  docker compose exec -T postgres psql -U radar -d radar -c \
    "SELECT id, trigger, status, started_at, finished_at FROM crawl_runs ORDER BY id DESC LIMIT 5"
  du -sh data/*
}

case "${1:-}" in
  up|down|update|crawl|status|backup) "cmd_$1" ;;
  *) echo "Cách dùng: $0 {up|down|update|crawl|status|backup}" >&2; exit 2 ;;
esac
