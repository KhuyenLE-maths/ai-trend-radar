#!/bin/sh
# Dump database vào /backups. Ghi ra file tạm trước để dump dở không đè bản tốt.
set -eu
target="/backups/radar-$(date -u +%F).dump"
pg_dump -Fc -f "$target.tmp"
mv "$target.tmp" "$target"
echo "Đã backup: $target"
