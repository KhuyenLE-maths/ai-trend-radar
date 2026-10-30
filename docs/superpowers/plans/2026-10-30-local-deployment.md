# AI Trend Radar chạy local: kế hoạch triển khai

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Chạy app hoàn toàn trên máy này từ repo `ai-trend-radar-local`, giữ lại toàn bộ dữ liệu thô và đã xử lý của mọi lần crawl trong `data/`, và báo đúng trạng thái crawl.

**Architecture:** Giữ Postgres, Redis và các dịch vụ Compose hiện có. Mỗi lần crawl có một `RawArchive` ghi phản hồi nguyên văn ra `data/raw/`, được các client lấy qua `contextvars`. Worker thay cron bằng một vòng kiểm tra 15 phút dùng chung cho crawl đúng giờ, chạy bù và thử lại. Một dịch vụ `backup` riêng chạy `pg_dump` bằng đúng phiên bản Postgres 16.

**Tech Stack:** Python 3.12, FastAPI, asyncpg, APScheduler, httpx, Postgres 16, Redis 7, Docker Compose, pytest, pytest-asyncio, bash.

**Spec:** `docs/superpowers/specs/2026-10-30-local-deployment-design.md`

## Global Constraints

- Toàn bộ công việc nằm trên nhánh `feat/local-deployment`. Không đưa vào `main` cho tới khi chủ dự án xác nhận đã tắt Render.
- Không có cơ chế tự xóa, xoay vòng hoặc nén bỏ dữ liệu cũ. File thô đã có không bao giờ bị ghi đè.
- `data/` và `.env` không vào git. Token không xuất hiện trong dữ liệu thô, log hay tài liệu.
- Không dùng `docker compose down -v`. Không xóa volume `ai-trend-radar_pgdata` và folder `~/Desktop/AI/ai-trend-radar`.
- Không đụng tới container `open-notebook-*`, folder `Guide/` và dịch vụ trên Render.
- Cổng: `127.0.0.1:3000` web, `127.0.0.1:8001` API (biến `API_PORT`), `127.0.0.1:5433` Postgres.
- Lịch crawl giữ `0 2 * * *` theo UTC. "Hôm nay" tính theo ngày UTC.
- Python trên máy là 3.9, không chạy được code. Mọi test chạy trong Docker.
- Theo ngôn ngữ của code: docstring và comment tiếng Việt ngắn gọn.

## Review Focus

- Ổ đầy hoặc `data/raw` không ghi được: lần crawl thành `failed`, không báo thành công. Test ở Task 2 và Task 5.
- Worker khởi động lại đúng lúc crawl do API kích hoạt đang chạy: lần chạy đó không bị đánh dấu `failed`. Test ở Task 6.
- Tiến trình bị kill giữa chừng: file `.jsonl.gz` dở vẫn đọc được tới dòng cuối đã ghi, lần chạy được dọn sau đó. Test ở Task 2 và Task 6.
- Token lọt vào dữ liệu thô: file thô không chứa token. Test ở Task 4.
- Một repo trả dữ liệu lạ: chỉ repo đó thất bại, bước `track` vẫn chạy tiếp. Test ở Task 3.

---

### Task 1: Môi trường test và schema mới

**Files:**
- Create: `backend/Dockerfile.test`, `backend/requirements-dev.txt`, `backend/pytest.ini`, `backend/tests/__init__.py`, `backend/tests/conftest.py`, `backend/tests/test_schema.py`, `docker-compose.test.yml`
- Modify: `backend/app/db/schema.sql`

**Interfaces:**
- Produces: fixture `pool` (asyncpg pool, đã `init_db`, bảng dữ liệu được dọn giữa các test); fixture `raw_dir` (`tmp_path / "raw"`, gán vào `settings.raw_data_dir`); bảng `repo_run_snapshots`, `raw_archives`; cột `crawl_runs.failure_kind TEXT`.

- [ ] **Step 1: Tạo nhánh và commit spec cùng plan**

```bash
git checkout -b feat/local-deployment
git add docs/superpowers
git commit -m "docs: add local deployment design and plan"
```

- [ ] **Step 2: Tạo môi trường test**

`docker-compose.test.yml` có `name: ai-trend-radar-test`, dịch vụ `postgres` (`postgres:16-alpine`, dữ liệu trên `tmpfs`), `redis`, và `tests` build từ `backend/Dockerfile.test`, mount `./backend:/srv`, có `DATABASE_URL`, `REDIS_URL` trỏ vào hai dịch vụ này và `GITHUB_TOKEN=test-token`. Không publish cổng. `requirements-dev.txt` gồm `pytest` và `pytest-asyncio`. `pytest.ini` đặt `asyncio_mode = auto`.

- [ ] **Step 3: Viết test thất bại trong `backend/tests/test_schema.py`**

```python
async def test_new_tables_exist(pool):
    names = {r["table_name"] for r in await pool.fetch(
        "SELECT table_name FROM information_schema.tables WHERE table_schema='public'")}
    assert {"repo_run_snapshots", "raw_archives"} <= names

async def test_failure_kind_column(pool):
    assert await pool.fetchval(
        "SELECT 1 FROM information_schema.columns "
        "WHERE table_name='crawl_runs' AND column_name='failure_kind'") == 1

async def test_init_db_idempotent(pool):
    from app.core.db import init_db
    await init_db()
    await init_db()
```

- [ ] **Step 4: Chạy để thấy test thất bại**

Run: `docker compose -f docker-compose.test.yml run --rm --build tests pytest tests/test_schema.py -v`
Expected: FAIL ở `test_new_tables_exist`.

- [ ] **Step 5: Thêm vào `schema.sql`, idempotent**

`repo_run_snapshots`: `run_id BIGINT REFERENCES crawl_runs(id)`, `repo_id BIGINT REFERENCES repositories(id)`, `stars, forks, watchers, open_issues, contributors, star_growth_7d, star_growth_30d INT`, `hot_score REAL`, `trending_flag BOOLEAN`, khóa chính `(run_id, repo_id)`, không `ON DELETE CASCADE`.
`raw_archives`: `id BIGSERIAL PRIMARY KEY`, `run_id BIGINT NOT NULL REFERENCES crawl_runs(id)`, `source TEXT NOT NULL`, `path TEXT NOT NULL UNIQUE`, `line_count BIGINT NOT NULL`, `byte_size BIGINT NOT NULL`, `sha256 TEXT NOT NULL`, `created_at TIMESTAMPTZ DEFAULT now()`.
`ALTER TABLE crawl_runs ADD COLUMN IF NOT EXISTS failure_kind TEXT;`. Giữ nguyên bảng `raw_items`.

- [ ] **Step 6: Chạy lại, mong đợi PASS, rồi commit**

```bash
git add backend docker-compose.test.yml
git commit -m "test: add docker test harness and run history schema"
```

### Task 2: Bộ ghi dữ liệu thô

**Files:**
- Create: `backend/app/pipeline/raw_archive.py`, `backend/tests/test_raw_archive.py`
- Modify: `backend/app/core/config.py`

**Interfaces:**
- Consumes: fixture `raw_dir`.
- Produces:
  - `settings.raw_data_dir: str = "/data/raw"`
  - `class RawArchive(root: Path, run_id: int, day: date)`, có `error: str | None`
  - `RawArchive.record(source: str, request: dict, status: int | None, body: str) -> None`, không bao giờ raise; lỗi đầu tiên lưu vào `error`
  - `RawArchive.close() -> list[ArchiveFile]`, `ArchiveFile` là dataclass `source, path, line_count, byte_size, sha256`; `path` tương đối so với `root`
  - `use_archive(archive) -> ContextManager[None]` và `record_raw(source, request, status, body) -> None`, không làm gì khi chưa có archive

- [ ] **Step 1: Viết test thất bại**

```python
def test_writes_jsonl_gz_per_source(raw_dir):
    a = RawArchive(raw_dir, 7, date(2026, 10, 30))
    a.record("github_rest", {"url": "/x"}, 200, '{"a":1}')
    a.record("github_rest", {"url": "/y"}, 500, "boom")
    [f] = a.close()
    assert f.path == "2026-10-30/run-7/github_rest.jsonl.gz"
    lines = [json.loads(l) for l in gzip.open(raw_dir / f.path, "rt")]
    assert [l["status"] for l in lines] == [200, 500]
    assert lines[1]["body"] == "boom" and "ts" in lines[0]
    assert f.line_count == 2
    assert f.sha256 == hashlib.sha256((raw_dir / f.path).read_bytes()).hexdigest()

def test_never_overwrites_existing_file(raw_dir):
    p = raw_dir / "2026-10-30/run-7"
    p.mkdir(parents=True)
    (p / "hackernews.jsonl.gz").write_bytes(b"old")
    a = RawArchive(raw_dir, 7, date(2026, 10, 30))
    a.record("hackernews", {}, 200, "x")
    assert a.error is not None
    assert (p / "hackernews.jsonl.gz").read_bytes() == b"old"

def test_unwritable_root_sets_error(tmp_path):
    blocker = tmp_path / "file"
    blocker.write_text("x")
    a = RawArchive(blocker, 1, date(2026, 10, 30))
    a.record("github_rest", {}, 200, "x")
    assert a.error is not None

def test_truncated_file_readable_up_to_last_record(raw_dir):
    a = RawArchive(raw_dir, 8, date(2026, 10, 30))
    a.record("hackernews", {}, 200, "one")
    a.record("hackernews", {}, 200, "two")
    path = raw_dir / "2026-10-30/run-8/hackernews.jsonl.gz"  # không close: mô phỏng bị kill
    assert read_records_tolerant(path)[-1]["body"] == "two"

def test_record_raw_without_archive_is_noop():
    record_raw("hackernews", {}, 200, "x")
```

- [ ] **Step 2: Chạy, mong đợi FAIL do chưa có module**

Run: `docker compose -f docker-compose.test.yml run --rm tests pytest tests/test_raw_archive.py -v`

- [ ] **Step 3: Viết `raw_archive.py`**

Mỗi nguồn một `gzip.GzipFile` mở từ file `open(path, "xb")`, nên trùng file thì báo lỗi thay vì ghi đè. Sau mỗi dòng gọi `flush()` cả hai lớp, để file dở vẫn đọc được. Thêm `read_records_tolerant(path) -> list[dict]`, bỏ qua `EOFError` ở đuôi. `sha256` tính sau khi đóng file. Dòng JSON gồm `ts` (ISO UTC), `source`, `request`, `status`, `body`, và không có tham số nào cho header.

- [ ] **Step 4: Chạy, mong đợi PASS, rồi commit**

```bash
git add backend/app/pipeline/raw_archive.py backend/app/core/config.py backend/tests/test_raw_archive.py
git commit -m "feat: add append-only raw crawl archive"
```

### Task 3: Sửa `track` và bỏ trần repo

**Files:**
- Modify: `backend/app/pipeline/sources/github_graphql.py`, `backend/app/pipeline/sources/github_search.py`, `backend/app/core/config.py`, `.env.example`
- Create: `backend/app/core/dates.py`, `backend/tests/test_track.py`

**Interfaces:**
- Produces: `parse_iso_datetime(s: str | None) -> datetime | None` trong `core/dates.py`; `track(pool, extra_names=None) -> dict` trả thêm khóa `deleted`. `failed` đếm cả repo lỗi riêng lẻ.

- [ ] **Step 1: Viết test thất bại, giả lập `graphql` bằng `monkeypatch`**

Dựng node mẫu hợp lệ bằng helper `make_node(database_id, name, **overrides)` với đủ trường của `FRAGMENT`.

```python
async def test_track_writes_repo_and_snapshot(pool, monkeypatch): ...
    # mong đợi: updated == 1, snapshots == 1, repositories.repo_pushed_at là datetime
    # và repo_snapshots có 1 dòng

async def test_track_includes_archived_repos_without_cap(pool, monkeypatch): ...
    # chèn 60 repo, 1 repo is_archived: mong đợi mọi repo đều nằm trong query

async def test_bad_node_only_fails_that_repo(pool, monkeypatch): ...
    # node thứ nhất có createdAt="garbage", node thứ hai hợp lệ:
    # mong đợi updated == 1 và failed == 1

async def test_missing_repo_counts_as_deleted_not_failed(pool, monkeypatch): ...
    # graphql trả r0=None: mong đợi deleted == 1, failed == 0
```

- [ ] **Step 2: Chạy, mong đợi FAIL với `DataError`**

Run: `docker compose -f docker-compose.test.yml run --rm tests pytest tests/test_track.py -v`

- [ ] **Step 3: Sửa code**

Chuyển `_parse_iso_datetime` sang `core/dates.py`, `github_search.py` import lại. Trong `track`, parse ba trường ngày, bọc xử lý từng node bằng `try/except Exception` với log warning và `failed += 1`. `_select_tracked` bỏ `WHERE NOT is_archived` và `LIMIT`. Xóa `max_tracked_repos` và `run_on_start` khỏi `Settings` và `.env.example`. `scheduler.py` còn tham chiếu `run_on_start`, nên trong task này xóa luôn khối đó.

- [ ] **Step 4: Chạy, mong đợi PASS, rồi commit**

```bash
git add backend .env.example
git commit -m "fix: track all repos and parse GraphQL timestamps"
```

### Task 4: Ghi dữ liệu thô tại các nguồn

**Files:**
- Modify: `backend/app/pipeline/sources/github_client.py`, `github_search.py`, `github_trending.py`, `hackernews.py`, `backend/app/pipeline/steps/summarize.py`
- Create: `backend/tests/test_sources_raw.py`

**Interfaces:**
- Consumes: `record_raw`, `use_archive`, `RawArchive`, `read_records_tolerant`.
- Produces:
  - tên nguồn `github_rest`, `github_graphql`, `github_readme`, `github_trending`, `hackernews`, `anthropic`
  - `class GitHubAuthError(Exception)` và `async check_github_token() -> None` trong `github_client.py`: gọi `/rate_limit`; token rỗng hoặc phản hồi 401 thì raise `GitHubAuthError`
  - `discover` trả thêm `failed_queries: int`
  - `fetch_trending` raise `TrendingUnavailable` khi mọi `LANGS` đều lỗi
  - `fetch_mentions` raise lại lỗi thay vì trả `[]`

Thêm fixture `mock_http` vào `conftest.py`: dùng `monkeypatch` thay `httpx.AsyncClient` bằng client có `httpx.MockTransport`, để không test nào gọi mạng thật.

- [ ] **Step 1: Viết test thất bại**

```python
async def test_rest_get_records_error_responses(raw_dir, mock_http): ...
    # phản hồi 404: rest_get raise, nhưng file github_rest có status 404

async def test_token_never_in_raw_files(raw_dir, mock_http, monkeypatch):
    monkeypatch.setattr(settings, "github_token", "ghp_SECRET")
    # gọi rest_get, graphql, fetch_readme_raw trong use_archive
    assert "ghp_SECRET" not in all_raw_text(raw_dir)

async def test_trending_records_html_and_raises_when_all_fail(raw_dir, mock_http): ...
async def test_hackernews_failure_raises(raw_dir, mock_http): ...
async def test_summarize_records_model_response(pool, raw_dir, monkeypatch): ...
async def test_check_github_token_401_raises(mock_http): ...
async def test_discover_counts_failed_queries(pool, mock_http): ...
```

- [ ] **Step 2: Chạy, mong đợi FAIL**

Run: `docker compose -f docker-compose.test.yml run --rm tests pytest tests/test_sources_raw.py -v`

- [ ] **Step 3: Thêm `record_raw` ngay sau mỗi phản hồi, trước mọi kiểm tra trạng thái**

`request` chỉ gồm `method`, `url`, `params` hoặc `query`, không có header. Với lỗi kết nối, ghi `status=None`, `body=str(e)`. Trong `summarize`, ghi `msg.model_dump_json()` với `source="anthropic"`. Retry của tenacity tạo một dòng cho mỗi lần thử.

- [ ] **Step 4: Chạy toàn bộ test, mong đợi PASS, rồi commit**

Run: `docker compose -f docker-compose.test.yml run --rm tests pytest -v`

```bash
git add backend
git commit -m "feat: record every external response to the raw archive"
```

### Task 5: Điều phối lần crawl và trạng thái đúng

**Files:**
- Modify: `backend/app/pipeline/run_daily.py`
- Create: `backend/app/pipeline/run_status.py`, `backend/tests/test_run_status.py`, `backend/tests/test_run_daily.py`

**Interfaces:**
- Consumes: `RawArchive`, `use_archive`, `check_github_token`, `GitHubAuthError`, `TrendingUnavailable`, `track`'s `updated`/`failed`/`deleted`.
- Produces:
  - `classify_run(stats: dict, failed_steps: set[str], raw_error: str | None) -> str`, trả `success`, `partial` hoặc `failed`
  - `run_daily(trigger="cron") -> dict`; `crawl_runs.failure_kind` là `auth` khi lỗi token
  - `save_run_snapshots(pool, run_id, started_at) -> int`

- [ ] **Step 1: Viết test thất bại cho `classify_run`**

```python
@pytest.mark.parametrize("updated,failed,expected", [
    (0, 3063, "failed"), (0, 0, "failed"), (49, 51, "failed"),
    (50, 50, "partial"), (94, 6, "partial"), (95, 5, "success"), (100, 0, "success"),
])
def test_track_thresholds(updated, failed, expected):
    assert classify_run({"track": {"updated": updated, "failed": failed}}, set(), None) == expected

def test_deleted_repos_do_not_count():
    assert classify_run({"track": {"updated": 95, "failed": 0, "deleted": 40}}, set(), None) == "success"

@pytest.mark.parametrize("step", ["discover", "trending", "hn", "categorize", "rank"])
def test_step_failure_is_partial(step):
    assert classify_run({"track": {"updated": 10, "failed": 0}}, {step}, None) == "partial"

def test_summary_failure_is_not_a_failure():
    stats = {"track": {"updated": 10, "failed": 0}, "summarize": {"failed": 3}}
    assert classify_run(stats, set(), None) == "success"

def test_raw_error_is_failed():
    assert classify_run({"track": {"updated": 10, "failed": 0}}, set(), "disk full") == "failed"

def test_track_exception_is_failed():
    assert classify_run({"track": {"error": "x"}}, {"track"}, None) == "failed"
```

- [ ] **Step 2: Viết test thất bại cho `run_daily`, giả lập các nguồn**

```python
async def test_bad_token_stops_run(pool, raw_dir, monkeypatch): ...
    # check_github_token raise GitHubAuthError: status 'failed', failure_kind 'auth',
    # error nhắc tới GITHUB_TOKEN, discover không được gọi, lock được nhả

async def test_failed_track_skips_later_steps(pool, raw_dir, monkeypatch): ...
    # track updated=0: rank, apply_trending_flags, summarize không được gọi, status 'failed'

async def test_two_runs_same_day_keep_separate_history(pool, raw_dir, monkeypatch): ...
    # hai lần run_daily: 2 thư mục run-<id>, 2 bộ dòng repo_run_snapshots, bản ghi raw_archives cho cả hai

async def test_raw_write_failure_marks_run_failed(pool, tmp_path, monkeypatch): ...
    # settings.raw_data_dir trỏ vào một file: status 'failed', error nêu dữ liệu thô

async def test_locked_run_creates_no_row(pool, raw_dir): ...
    # lock đang giữ: trả {"skipped": "locked"} và không thêm dòng crawl_runs

async def test_init_failure_releases_lock(pool, raw_dir, monkeypatch): ...
    # init_db raise: pipeline:lock không còn
```

- [ ] **Step 3: Chạy, mong đợi FAIL**

Run: `docker compose -f docker-compose.test.yml run --rm tests pytest tests/test_run_status.py tests/test_run_daily.py -v`

- [ ] **Step 4: Viết `run_status.py` và sửa `run_daily.py`**

Tỷ lệ là `updated / (updated + failed)`, không tính `deleted`. 0/0 là `failed`.
Thứ tự mới: lấy lock, vào `try`, `init_db`, tạo `crawl_runs`, tạo `RawArchive`, `use_archive`, `check_github_token`, discover, fetch trending và HN, track. Sau track, nếu `classify_run` trả `failed` thì kết thúc luôn. Ngược lại tiếp tục apply trending (bỏ qua khi `TrendingUnavailable`), save mentions, categorize, rank, `save_run_snapshots`, summarize, invalidate cache.
Sau mỗi bước, nếu `archive.error` có giá trị thì dừng. Mọi đường kết thúc đều đóng archive, ghi `raw_archives`, cập nhật `finished_at`, `status`, `failure_kind`, `error`, nhả lock.
`save_run_snapshots` dùng `INSERT ... SELECT` từ `repositories WHERE last_crawled_at >= started_at`, nên chỉ ghi repo thực sự được cập nhật trong lần này.

- [ ] **Step 5: Chạy toàn bộ test, mong đợi PASS, rồi commit**

```bash
git add backend
git commit -m "feat: report crawl status truthfully and keep per-run history"
```

### Task 6: Lịch crawl, chạy bù và dọn lần chạy kẹt

**Files:**
- Modify: `backend/app/pipeline/scheduler.py`
- Create: `backend/tests/test_scheduler.py`

**Interfaces:**
- Consumes: `run_daily`, `release_pipeline_lock`, redis key `pipeline:lock`, `settings.pipeline_cron`.
- Produces:
  - `RETRY_MINUTES = 60`, `MAX_FAILED_PER_DAY = 3`, `TICK_MINUTES = 15`
  - `@dataclass RunInfo(status: str, started_at: datetime, finished_at: datetime | None, failure_kind: str | None)`
  - `should_run(now: datetime, due_at: datetime, today_runs: list[RunInfo]) -> bool`
  - `due_time(now: datetime) -> datetime`: lần kích hoạt đầu tiên của cron trong ngày UTC, dùng `CronTrigger.get_next_fire_time`
  - `async reap_stale_runs(pool) -> int`
  - `async tick() -> None`

- [ ] **Step 1: Viết test thất bại**

```python
D = datetime(2026, 10, 30, 2, 0, tzinfo=timezone.utc)
def at(h, m=0): return D.replace(hour=h, minute=m)
def run(status, h, kind=None): return RunInfo(status, at(h), at(h), kind)

def test_before_due_no_run(): assert not should_run(at(1), D, [])
def test_after_due_runs(): assert should_run(at(5), D, [])
def test_success_done(): assert not should_run(at(5), D, [run("success", 3)])
def test_partial_done(): assert not should_run(at(5), D, [run("partial", 3)])
def test_running_blocks(): assert not should_run(at(5), D, [RunInfo("running", at(4), None, None)])
def test_failed_retries_after_hour():
    assert not should_run(at(3, 30), D, [run("failed", 3)])
    assert should_run(at(4), D, [run("failed", 3)])
def test_three_failures_stop():
    assert not should_run(at(9), D, [run("failed", 3), run("failed", 5), run("failed", 7)])
def test_auth_failure_not_retried():
    assert not should_run(at(9), D, [run("failed", 3, "auth")])

async def test_reap_marks_stale_run_failed(pool): ...
    # lock trống + run 'running': mong đợi 'failed', finished_at có giá trị, error nêu rõ bị dọn
async def test_reap_keeps_run_when_lock_held(pool): ...
    # lock đang giữ (crawl do API chạy): run vẫn 'running'
async def test_tick_twice_runs_once(pool, monkeypatch): ...
    # run_daily giả ghi một dòng success: gọi tick() hai lần, run_daily được gọi 1 lần
```

- [ ] **Step 2: Chạy, mong đợi FAIL**

Run: `docker compose -f docker-compose.test.yml run --rm tests pytest tests/test_scheduler.py -v`

- [ ] **Step 3: Viết lại `scheduler.py`**

Bỏ job cron. `main()` dùng `AsyncIOScheduler(timezone="UTC")` với `IntervalTrigger(minutes=TICK_MINUTES)`, `max_instances=1`, `next_run_time=now` để kiểm tra ngay khi khởi động. `tick()` chạy `reap_stale_runs`, lấy các lần chạy có `started_at` từ 00:00 UTC hôm nay, rồi gọi `run_daily(trigger="schedule")` nếu `should_run` đúng. Lần chạy `failed` có `finished_at` rỗng thì tính từ `started_at`. Với lần chạy cũ bị dọn thì không tính vào `today_runs`, vì đã khác ngày. Thêm `'schedule'` không cần đổi schema, vì `trigger` là `TEXT`.

- [ ] **Step 4: Chạy toàn bộ test, mong đợi PASS, rồi commit**

```bash
git add backend
git commit -m "feat: replace cron with catch-up scheduler and reap stale runs"
```

### Task 7: Compose, folder dữ liệu, backup và lệnh vận hành

**Files:**
- Modify: `docker-compose.yml`, `.gitignore`, `.env.example`
- Create: `scripts/radar.sh`, `scripts/backup-loop.sh`, `scripts/backup-once.sh`

**Interfaces:**
- Consumes: `settings.raw_data_dir`, bảng `crawl_runs`.
- Produces: dịch vụ `backup`; lệnh `./scripts/radar.sh up|down|update|crawl|status|backup`.

- [ ] **Step 1: Sửa `docker-compose.yml`**

- `postgres`: bind `./data/postgres:/var/lib/postgresql/data`, publish `127.0.0.1:5433:5432`.
- `api`: publish `127.0.0.1:${API_PORT:-8001}:8000`. `api` và `worker` mount `./data/raw:/data/raw`.
- `web`: publish `127.0.0.1:3000:3000`.
- Thêm `backup`: `postgres:16-alpine`, mount `./data/backups:/backups` và `./scripts:/scripts:ro`, chạy `/scripts/backup-loop.sh`, có `PGPASSWORD`, `depends_on` postgres healthy, `restart: unless-stopped`.
- Xóa khai báo volume `pgdata`.
- `.gitignore` thêm `data/`.

- [ ] **Step 2: Viết script backup**

`backup-once.sh` chạy `pg_dump -Fc` vào `/backups/radar-YYYY-MM-DD.dump.tmp`, rồi `mv` sang tên cuối, nên dump dở không đè bản tốt. `backup-loop.sh` mỗi 5 phút đọc `max(id)` của `crawl_runs` đã có `finished_at`; khi lớn hơn giá trị trong `/backups/.last_run_id` thì gọi `backup-once.sh` và cập nhật file đó. Không có lệnh `rm` trên file `.dump`.

- [ ] **Step 3: Viết `scripts/radar.sh`**

- `up`: tạo `data/{postgres,raw,backups}`, báo lỗi rõ nếu thiếu `.env`, `docker compose up -d --build`, in địa chỉ web.
- `down`: `docker compose down`, tuyệt đối không có `-v`.
- `update`: `backup`, `git pull --ff-only`, `up`. Dừng ngay khi backup lỗi.
- `crawl`: gọi `POST http://127.0.0.1:${API_PORT:-8001}/api/v1/admin/crawl` với `ADMIN_TOKEN` đọc từ `.env`.
- `status`: `docker compose ps`, lần crawl gần nhất từ `crawl_runs`, `du -sh data/*`.
- `backup`: `docker compose exec -T backup /scripts/backup-once.sh`.
- Dùng `set -euo pipefail`, `cd` về thư mục repo.

- [ ] **Step 4: Kiểm tra cú pháp**

Run: `bash -n scripts/radar.sh scripts/backup-loop.sh scripts/backup-once.sh && docker compose config --quiet`
Expected: không có lỗi.

Kiểm tra chạy thật thuộc Task 9, vì stack cũ đang giữ cổng 3000.

- [ ] **Step 5: Commit**

```bash
git add docker-compose.yml .gitignore .env.example scripts
git commit -m "feat: store data in local folder and add radar commands"
```

### Task 8: Bỏ Render và viết lại tài liệu

**Files:**
- Delete: `render.yaml`, `uptime.py`, `.github/workflows/daily-crawl.yml`
- Modify: `DEPLOYMENT.md`, `README.md`, `backend/Dockerfile:8` (comment về Render), `backend/app/pipeline/run_daily.py` nếu còn nhắc Render

- [ ] **Step 1: Xóa file và tìm phần còn sót**

Run: `git rm render.yaml uptime.py && rm -r .github && grep -rniE 'render|onrender' --exclude-dir=node_modules --exclude-dir=.git --exclude-dir=docs --exclude-dir=Guide --exclude-dir=data --exclude-dir=.next .`
Expected: chỉ còn các từ không liên quan tới dịch vụ Render, ví dụ hàm render của frontend.

- [ ] **Step 2: Viết lại `DEPLOYMENT.md` và `README.md`**

Gồm: yêu cầu (Docker Desktop, bật tự khởi động theo máy, cấp quyền truy cập folder Desktop nếu macOS hỏi), tạo `.env`, các lệnh `radar.sh`, cấu trúc `data/`, cách đọc file thô, cách restore từ `data/backups`, cổng 8001, và cách sao lưu folder `data/`. Nêu rõ lịch crawl chỉ chạy khi máy và Docker đang bật. `README.md` ngắn, trỏ sang `DEPLOYMENT.md`.

- [ ] **Step 3: Commit**

```bash
git add -A -- render.yaml uptime.py DEPLOYMENT.md README.md backend/Dockerfile backend/app/pipeline/run_daily.py
git commit -m "chore: remove Render deployment and document local setup"
```

### Task 9: Chuyển dữ liệu và nghiệm thu

Task này tác động lên app đang chạy. Làm tuần tự, dừng lại nếu số liệu không khớp.

**Files:**
- Create: `scripts/sql/2026-10-30-fix-run-history.sql`, `docs/superpowers/specs/2026-10-30-migration-baseline.txt`

- [ ] **Step 1: Xác định token dùng được**

Với từng `.env` (folder cũ và repo này), đọc `GITHUB_TOKEN` và gọi `curl -s -o /dev/null -w '%{http_code}' -H "Authorization: token $T" https://api.github.com/rate_limit`. Không in token. Nếu một file trả 200, dùng token đó cho `.env` của repo này. Nếu không có file nào trả 200, chủ dự án phải tạo token mới; phần còn lại vẫn làm được, nhưng các tiêu chí cần crawl thật sẽ chờ tới lúc có token.

- [ ] **Step 2: Ghi số liệu gốc và dump**

Ghi số dòng của tất cả bảng từ `ai-trend-radar-postgres-1` vào file baseline, rồi:

```bash
mkdir -p data/backups data/postgres data/raw
docker exec ai-trend-radar-postgres-1 pg_dump -U radar -d radar -Fc > data/backups/pre-migration-2026-10-30.dump
docker run --rm -v "$PWD/data/backups:/b:ro" postgres:16-alpine pg_restore -l /b/pre-migration-2026-10-30.dump | grep -c 'TABLE DATA'
```

Expected: file khác rỗng, số `TABLE DATA` bằng số bảng.

- [ ] **Step 3: Dừng stack cũ, không xóa gì**

```bash
docker update --restart=no ai-trend-radar-web-1 ai-trend-radar-api-1 ai-trend-radar-worker-1 ai-trend-radar-postgres-1 ai-trend-radar-redis-1
docker stop ai-trend-radar-web-1 ai-trend-radar-api-1 ai-trend-radar-worker-1 ai-trend-radar-postgres-1 ai-trend-radar-redis-1
```

- [ ] **Step 4: Bật Postgres mới và restore**

Chỉ bật `postgres` trước (`docker compose up -d postgres`), để `init_db` chưa tạo bảng. Restore bằng `pg_restore --no-owner -d radar` từ file dump. So số dòng với baseline; khác là dừng lại, chạy lại stack cũ bằng `docker start` và báo cho chủ dự án.

- [ ] **Step 5: Sửa lịch sử crawl**

SQL trong `2026-10-30-fix-run-history.sql`, chạy sau khi `init_db` đã thêm cột, tức sau Step 6 lần đầu của API; nên chạy với worker chưa bật.

```sql
UPDATE crawl_runs SET status='failed',
  error=coalesce(error||E'\n','')||'Sửa 2026-10-30: báo success sai, track updated=0 (GitHub 401).'
WHERE id=17 AND status='success';
UPDATE crawl_runs SET status='partial',
  error=coalesce(error||E'\n','')||'Sửa 2026-10-30: báo success sai, track lỗi hoặc updated=0.'
WHERE id IN (1,2,3,15) AND status='success';
```

- [ ] **Step 6: Bật toàn bộ**

Thứ tự: `docker compose up -d --build api`, chạy SQL ở Step 5, rồi `./scripts/radar.sh up`.

- [ ] **Step 7: Nghiệm thu theo tiêu chí trong spec**

- `curl -s -o /dev/null -w '%{http_code}' localhost:3000` trả 200, API `/readyz` ở cổng 8001 trả `ready`, số repo là 4.677 trở lên.
- Lần 16 thành `failed`.
- Khi có token đúng: crawl tự chạy bù, `repo_snapshots` có dòng, có `data/raw/<ngày>/run-<id>/` và `raw_archives`.
- `./scripts/radar.sh crawl` lần hai tạo thêm thư mục `run-<id>` và thêm bộ dòng `repo_run_snapshots`.
- Với token sai tạm thời trong `.env`: lần crawl `failed`, lỗi nêu `GITHUB_TOKEN`. Khôi phục token sau đó.
- `docker compose down && ./scripts/radar.sh up`: dữ liệu còn nguyên.
- Có file `data/backups/radar-*.dump` sau crawl.
- `git status` không hiện `data/`.
- Đo dung lượng thô thực tế và ghi vào `DEPLOYMENT.md`.

- [ ] **Step 8: Commit**

```bash
git add scripts/sql docs/superpowers/specs/2026-10-30-migration-baseline.txt DEPLOYMENT.md
git commit -m "chore: migrate data to local folder and record baseline"
```
