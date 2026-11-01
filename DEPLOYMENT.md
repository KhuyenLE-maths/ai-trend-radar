# Vận hành AI Trend Radar trên máy local

App chạy bằng Docker Compose trên máy này và chỉ mở cho chính máy này (`127.0.0.1`).

## Yêu cầu

- Docker Desktop. Bật **Start Docker Desktop when you sign in** để app tự chạy khi mở máy.
- Nếu macOS hỏi quyền truy cập folder Desktop cho Docker, hãy cho phép, vì `data/` nằm trong repo.
- Một GitHub token tạo tại <https://github.com/settings/tokens>. Không cần chọn scope nào.

## Cài đặt

```bash
cp .env.example .env
```

Điền `GITHUB_TOKEN`, `ADMIN_TOKEN` và `POSTGRES_PASSWORD`. `GEMINI_API_KEY` là tùy chọn (tạo tại <https://aistudio.google.com/apikey>); để trống thì bỏ qua AI Summary.

## Các lệnh

| Lệnh | Tác dụng |
| --- | --- |
| `./scripts/radar.sh up` | Build và bật app |
| `./scripts/radar.sh down` | Tắt app, giữ nguyên dữ liệu |
| `./scripts/radar.sh update` | Backup, `git pull`, build lại và bật app |
| `./scripts/radar.sh crawl` | Crawl ngay |
| `./scripts/radar.sh status` | Xem dịch vụ, các lần crawl gần nhất, dung lượng dữ liệu |
| `./scripts/radar.sh backup` | Backup database ngay |

| Dịch vụ | Địa chỉ |
| --- | --- |
| Web | <http://localhost:3000> |
| API | <http://localhost:8001> (đổi bằng `API_PORT`) |
| Postgres | `127.0.0.1:5433`, user `radar`, database `radar` |

## Lịch crawl

App crawl vào 09:00 giờ Việt Nam (02:00 UTC, đổi bằng `PIPELINE_CRON`). Crawl chỉ chạy khi máy và Docker đang bật. Worker kiểm tra mỗi 15 phút, nên nếu máy tắt hoặc ngủ qua giờ crawl thì crawl sẽ chạy bù khi máy bật lại.

Nếu máy ngủ giữa lúc crawl, crawl tạm dừng và chạy tiếp khi máy thức, nên lần đó có thể kéo dài nhiều giờ. Muốn crawl xong nhanh, hãy giữ máy thức trong lúc crawl.

Crawl lỗi được thử lại sau ít nhất 1 giờ, tối đa 3 lần mỗi ngày. Lỗi token không được thử lại: hãy sửa `GITHUB_TOKEN`, chạy `./scripts/radar.sh up`, rồi `./scripts/radar.sh crawl`.

Trạng thái lần crawl:

- `success`: cập nhật được từ 95% repo trở lên và không có bước chính nào lỗi.
- `partial`: cập nhật được 50% đến dưới 95% repo, hoặc một bước chính lỗi toàn bộ.
- `failed`: token hỏng, cập nhật được dưới 50% repo, hoặc không ghi được dữ liệu thô.

## Dữ liệu

```text
data/
  postgres/                    dữ liệu Postgres
  raw/YYYY-MM-DD/run-<id>/     phản hồi nguyên văn từ từng nguồn
    <nguồn>.jsonl.gz
  backups/radar-YYYY-MM-DD.dump
```

Một lần crawl đầy đủ tạo khoảng 8 MB dữ liệu thô nén, tức khoảng 3 GB mỗi năm nếu crawl mỗi ngày (đo ngày 2026-10-30 với 6.288 repo).

Không có gì tự xóa. `data/` không nằm trong git, nên hãy tự sao chép folder này ra ổ khác nếu muốn phòng hỏng máy. Tắt app trước khi sao chép `data/postgres`; file trong `data/backups` thì sao chép lúc nào cũng được.

Các nguồn trong `data/raw`: `github_rest`, `github_graphql`, `github_readme`, `github_trending`, `hackernews`, `gemini`. Mỗi dòng là một JSON gồm `ts`, `source`, `request`, `status`, `body`, kể cả phản hồi lỗi.

```bash
gzip -dc data/raw/2026-10-30/run-20/hackernews.jsonl.gz | head -1
```

Trong database:

- `repo_run_snapshots`: số liệu từng repo theo từng lần crawl.
- `repo_snapshots`: số liệu theo ngày, dùng cho biểu đồ.
- `raw_archives`: danh sách file thô của từng lần crawl, kèm sha256.
- `crawl_runs`: lịch sử các lần crawl.

## Khôi phục từ backup

```bash
docker compose stop api worker backup
docker compose exec -T postgres dropdb -U radar radar
docker compose exec -T postgres createdb -U radar radar
docker compose exec -T postgres pg_restore -U radar -d radar --no-owner < data/backups/radar-YYYY-MM-DD.dump
./scripts/radar.sh up
```

Lệnh `dropdb` xóa database hiện tại, nên hãy chắc chắn file backup là bản bạn muốn dùng.

## Chạy test

```bash
docker compose -f docker-compose.test.yml run --rm --build tests pytest
```
