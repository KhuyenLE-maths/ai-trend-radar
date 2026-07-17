# ◆ AI Trend Radar

Dashboard nội bộ tự động cập nhật **hàng ngày** các công cụ AI nổi bật trên GitHub: discover → lọc AI-relevance → phân loại → tính Hot Score → AI Summary → hiển thị.

Triển khai theo tài liệu *AI Trend Radar — System Design Document* (Phase 1 + Phase 2).

## Kiến trúc

```
GitHub Search/GraphQL/Trending + Hacker News
        │  (worker — APScheduler, 02:00 UTC hàng ngày)
        ▼
PostgreSQL 16 (data + full-text search) ◄── Redis 7 (cache + lock)
        ▼
FastAPI (REST /api/v1) ──► Next.js (dashboard) ──► Người dùng
```

| Service | Công nghệ | Port |
|---|---|---|
| `web` | Next.js 14 + Tailwind | 3000 |
| `api` | FastAPI (Python 3.12) | 8000 |
| `worker` | APScheduler + pipeline crawl | — |
| `postgres` | PostgreSQL 16 | nội bộ |
| `redis` | Redis 7 | nội bộ |

---

## 🚀 Chạy nhanh (Docker — khuyến nghị)

### Yêu cầu
- Docker + Docker Compose (Docker Desktop hoặc docker engine ≥ 24)
- **GitHub Personal Access Token** — tạo tại <https://github.com/settings/tokens> (loại *classic*, không cần chọn scope nào cho repo public). Không có token, GitHub chỉ cho 60 request/giờ → crawl sẽ fail.

### Các bước

```bash
# 1. Giải nén / clone project
cd ai-trend-radar

# 2. Tạo file cấu hình từ mẫu
cp .env.example .env
#    Mở .env và điền tối thiểu:
#    - GITHUB_TOKEN=ghp_xxx   (bắt buộc)
#    - ADMIN_TOKEN=...        (đổi mật khẩu admin)
#    - ANTHROPIC_API_KEY=...  (tuỳ chọn — muốn có AI Summary thì điền)

# 3. Build & chạy toàn bộ
docker compose up -d --build

# 4. Theo dõi crawl lần đầu (RUN_ON_START=true nên worker tự crawl ngay)
docker compose logs -f worker
```

Crawl lần đầu mất khoảng **10–25 phút** (tuỳ cấu hình). Sau đó mở:

- **Dashboard:** http://localhost:3000
- **API docs (Swagger):** http://localhost:8000/docs

### Chạy crawl thủ công bất kỳ lúc nào

```bash
curl -X POST http://localhost:8000/api/v1/admin/crawl \
     -H "X-Admin-Token: <ADMIN_TOKEN trong .env>"

# Xem lịch sử & trạng thái các lần chạy
curl http://localhost:8000/api/v1/admin/runs \
     -H "X-Admin-Token: <ADMIN_TOKEN>" | python3 -m json.tool
```

### Chạy thử nhanh (crawl nhỏ, ~3–5 phút)

Trong `.env`, giảm phạm vi rồi `docker compose restart worker`:

```env
DISCOVER_PAGES_PER_QUERY=1
MAX_TRACKED_REPOS=500
```

---

## 🧑‍💻 Chạy dev local (không Docker)

Yêu cầu: Python 3.12+, Node 20+, PostgreSQL 16, Redis 7 đang chạy local.

```bash
# Backend API
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export DATABASE_URL=postgresql://radar:radar@localhost:5432/radar
export REDIS_URL=redis://localhost:6379/0
export GITHUB_TOKEN=ghp_xxx
uvicorn app.main:app --reload            # http://localhost:8000/docs

# Worker (terminal khác, cùng env)
python -m app.pipeline.run_daily         # chạy pipeline 1 lần
python -m app.pipeline.scheduler         # hoặc chạy theo lịch cron

# Frontend (terminal khác)
cd frontend
npm install
npm run dev                              # http://localhost:3000
```

Tạo database local nếu chưa có: `createdb radar && psql -c "CREATE USER radar PASSWORD 'radar'; GRANT ALL ON DATABASE radar TO radar;"` — schema tự tạo khi API/worker khởi động.

---

## ⚙️ Cấu hình (.env)

| Biến | Bắt buộc | Mặc định | Ý nghĩa |
|---|---|---|---|
| `GITHUB_TOKEN` | ✅ | — | Token crawl GitHub (5.000 req/h) |
| `ADMIN_TOKEN` | ✅ | `changeme` | Bảo vệ endpoint `/admin/*` |
| `ANTHROPIC_API_KEY` | — | rỗng | Có key → bật AI Summary |
| `SUMMARY_MODEL` | — | `claude-haiku-4-5` | Model dùng tóm tắt |
| `SUMMARY_DAILY_LIMIT` | — | 20 | Số summary tối đa/ngày (kiểm soát chi phí) |
| `SLACK_WEBHOOK_URL` | — | rỗng | Thông báo kết quả pipeline vào Slack |
| `PIPELINE_CRON` | — | `0 2 * * *` | Lịch crawl (UTC). 02:00 UTC = 09:00 VN |
| `RUN_ON_START` | — | `true` | Worker crawl ngay khi khởi động |
| `MAX_TRACKED_REPOS` | — | 3000 | Trần số repo snapshot mỗi ngày |
| `DISCOVER_PAGES_PER_QUERY` | — | 2 | Số trang search (100 repo/trang)/truy vấn |
| `DISCOVER_MIN_STARS` | — | 50 | Sao tối thiểu khi discover repo active |
| `AI_FILTER_THRESHOLD` | — | 3.0 | Ngưỡng điểm lọc AI-relevance |

---

## 📡 API chính

| Endpoint | Mô tả |
|---|---|
| `GET /api/v1/repos?category=rag&language=Python&min_stars=1000&sort=hot&page=1` | List + filter + sort |
| `GET /api/v1/repos/{owner}/{name}` | Chi tiết (kèm AI summary, sparkline, similar) |
| `GET /api/v1/search?q=vector+db` — hỗ trợ `owner:x`, `tag:y`, `category:z` | Full-text + fuzzy search |
| `GET /api/v1/trending?period=day\|week\|month` | Bảng xếp hạng |
| `GET /api/v1/categories` · `GET /api/v1/stats/dashboard` · `GET /api/v1/updates/daily` | Meta/dashboard |
| `POST /api/v1/admin/crawl` · `GET /api/v1/admin/runs` (header `X-Admin-Token`) | Vận hành |

Swagger đầy đủ tại `/docs`.

---

## 🗂 Cấu trúc code

```
backend/app/
├── main.py              # FastAPI app
├── core/                # config (env), db (asyncpg), cache (redis)
├── db/schema.sql        # schema + indexes (idempotent, tự chạy khi khởi động)
├── api/                 # repos, meta (trending/categories/stats), admin
└── pipeline/
    ├── scheduler.py     # worker process (APScheduler)
    ├── run_daily.py     # orchestrator: discover→track→categorize→rank→summarize
    ├── sources/         # github_search, github_graphql, github_trending, hackernews
    ├── steps/           # filter_ai, categorize, rank (Hot Score SQL), summarize
    └── rules/categories.yaml   # rule phân loại — sửa file này, không cần sửa code
frontend/
├── app/                 # Next.js App Router: dashboard, /repos, /repos/[o]/[n], /categories
├── components/          # Nav, RepoCard, FilterBar, Sparkline
└── lib/api.js           # gọi backend + format helpers
```

## 🔧 Vận hành & tuỳ biến

- **Thêm/chỉnh category:** sửa `backend/app/pipeline/rules/categories.yaml` (và seed thêm dòng vào `backend/app/db/seed.sql` nếu là category mới) → restart worker.
- **Chỉnh trọng số Hot Score:** sửa `HOT_SCORE_SQL` trong `backend/app/pipeline/steps/rank.py` (các trọng số 0.35/0.15/0.10/0.15/0.15/0.10 — mục 9 tài liệu thiết kế).
- **Gán nhãn tay (override):** `INSERT INTO repo_categories (repo_id, category_id, confidence, source) VALUES (..., 1.0, 'manual')` — pipeline không bao giờ ghi đè nhãn manual.
- **Backup:** `docker compose exec postgres pg_dump -U radar radar | gzip > backup_$(date +%F).sql.gz`
- **Public ra ngoài:** đặt sau reverse proxy (Caddy/Nginx) + basic auth/VPN; không expose port 8000/3000 trực tiếp.

## 🩺 Troubleshooting

| Triệu chứng | Nguyên nhân / cách xử lý |
|---|---|
| Dashboard trống, "chưa có dữ liệu" | Crawl chưa chạy xong — xem `docker compose logs -f worker`; hoặc trigger tay qua `/admin/crawl` |
| Worker log `rate limited` liên tục | Thiếu/sai `GITHUB_TOKEN`, hoặc giảm `MAX_TRACKED_REPOS`, `DISCOVER_PAGES_PER_QUERY` |
| `401 Invalid admin token` | Header `X-Admin-Token` không khớp `ADMIN_TOKEN` trong `.env` |
| Trending không có cờ 📈 | GitHub đổi HTML trang trending (rủi ro đã lường trước) — pipeline vẫn chạy bình thường, sửa selector trong `github_trending.py` |
| Không có AI Summary | Chưa điền `ANTHROPIC_API_KEY`, hoặc repo chưa lọt Top Hot — xem `SUMMARY_DAILY_LIMIT` |
| Muốn reset toàn bộ dữ liệu | `docker compose down -v && docker compose up -d --build` |

## 🗺 Roadmap tiếp theo (theo tài liệu thiết kế)

Phase 3: pgvector similar repos + semantic search · Phase 4: SSO + personalized feed · Phase 5: newsletter tuần. Cấu trúc module hiện tại đã chừa sẵn đường tách service khi cần scale.
