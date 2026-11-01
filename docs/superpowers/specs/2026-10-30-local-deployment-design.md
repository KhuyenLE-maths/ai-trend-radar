# AI Trend Radar chạy local: thiết kế

Ngày: 2026-10-30. Trạng thái: bản nháp chờ duyệt.

## Mục đích

Chủ dự án là người dùng duy nhất. Họ muốn tự chạy và tự cập nhật app trên máy mình, mở bằng browser, không phụ thuộc Render. Họ muốn lưu tất cả dữ liệu sau mỗi lần crawl, không mất và không bị ghi đè.

Yêu cầu của chủ dự án: một người dùng, chạy local qua browser; lưu toàn bộ dữ liệu crawl trong một folder local kèm database phù hợp; tự chủ động deploy.

## Hiện trạng đã kiểm tra

- Stack Docker Compose đang chạy, nhưng từ folder khác: `~/Desktop/AI/ai-trend-radar`, không phải repo này (`ai-trend-radar-local`). Cả hai cùng commit `dc78bdf`, code giống nhau, chỉ khác `.env`.
- Cổng API đang chạy là 8001 do một file override tạm trong thư mục tạm của phiên trước. `docker-compose.yml` ghi 8000, nhưng cổng này đã bị `open-notebook-surrealdb-1` chiếm. Web ở cổng 3000.
- `track` truyền chuỗi ngày ISO vào tham số `timestamptz` trong `github_graphql.py`. Chạy thử trong container cho thấy asyncpg từ chối (`DataError`), và lệnh upsert nằm ngoài `try`, nên repo đầu tiên làm hỏng cả bước. 16 trên 17 lần crawl có `track` lỗi hoặc không cập nhật được repo nào. Đây là lý do có thể khiến `repo_snapshots` trống ngay cả khi token còn hạn.
- `MAX_TRACKED_REPOS=3000`, nên khoảng 1.700 trên 4.677 repo không được cập nhật ở mỗi lần crawl.
- Database nằm trong volume `ai-trend-radar_pgdata`, 29 MB: 4.677 repo, 17 lần crawl, 49 AI summary, 5 mention.
- `repo_snapshots` và `raw_items` đều có 0 dòng. Không có code nào ghi `raw_items`.
- Lần crawl 17 (2026-10-30) báo `success` dù GitHub trả 401, `track` có `failed: 3063, updated: 0`, `discover` có `scanned: 0`.
- Lần crawl 16 kẹt ở `running` từ 2026-10-02.
- `repo_snapshots` có khóa `(repo_id, snapshot_date)` và upsert, nên lần crawl thứ hai trong ngày đè lên lần đầu.
- `RUN_ON_START=true`, nên mỗi lần worker khởi động đều crawl.
- Máy có Docker 27 và Postgres chỉ có trong container, 258 GB trống. Desktop không được iCloud đồng bộ.

## Mục tiêu

1. Mọi lần crawl đều giữ lại được dữ liệu thô và dữ liệu đã xử lý, tra cứu được theo lần crawl.
2. Toàn bộ dữ liệu nằm trong `data/` của repo, nhìn thấy được và sao lưu được.
3. Một lệnh để bật, cập nhật, crawl tay và xem trạng thái.
4. Crawl hỏng phải hiện ra là hỏng.
5. Máy tắt lúc đến giờ crawl thì chạy bù khi máy bật lại.

## Không làm

- Đăng nhập, phân quyền, truy cập từ máy khác, truy cập từ Internet.
- Giao diện mới để duyệt dữ liệu thô. Dữ liệu được lưu để dùng sau; web chỉ tự có thêm biểu đồ nhờ `repo_snapshots` có dữ liệu.
- Lấy lại lịch sử quá khứ. GitHub không cung cấp, nên lịch sử bắt đầu từ lần crawl thành công đầu tiên.
- Sao lưu ra ngoài máy (cloud, ổ ngoài).
- Thay Postgres hoặc Redis.

## Điều không được xảy ra

- Mất dữ liệu đang có trong `ai-trend-radar_pgdata` khi chuyển sang folder mới.
- Bất kỳ cơ chế tự xóa, xoay vòng hoặc nén bỏ dữ liệu cũ.
- Ghi đè file thô đã có.
- Crawl hỏng mà báo `success`.
- Đưa `data/` hoặc `.env` lên git.

## Quyết định của chủ dự án

- Chỉ một người dùng trên máy này.
- Lưu tất cả, không chọn lọc.
- Dữ liệu ở folder local, kèm database phù hợp. Không phụ thuộc Render.

## Quyết định của người viết (chủ dự án có thể bác)

### Lưu trữ

Giữ Postgres 16 vì code đã viết cho Postgres (`pg_trgm`, `TSVECTOR`, `JSONB`, `TEXT[]`).

```text
data/                       (gitignore)
  postgres/                 dữ liệu Postgres, bind mount
  raw/YYYY-MM-DD/run-<id>/  dữ liệu thô từng lần crawl
    <source>.jsonl.gz
  backups/radar-YYYY-MM-DD.dump
```

Dữ liệu thô để trong file gzip thay vì Postgres. Ước tính khoảng 35 đến 40 MB thô mỗi ngày, tức khoảng 5 MB nén hoặc 2 GB mỗi năm; để trong JSONB sẽ nặng hơn nhiều và làm backup phình to. Con số này là ước tính, cần đo lại sau lần crawl thật đầu tiên.

Database lưu chỉ mục các file đó, không giữ nội dung.

### Phạm vi crawl

- Bỏ trần `MAX_TRACKED_REPOS`: mọi repo đã biết đều được cập nhật ở mỗi lần crawl, kể cả repo đã archive. Với 50 repo một batch, 4.677 repo cần khoảng 94 lệnh GraphQL, thấp hơn nhiều so với hạn mức GitHub.
- `DISCOVER_PAGES_PER_QUERY` và `DISCOVER_MIN_STARS` giữ nguyên. "Tất cả" nghĩa là tất cả những gì app crawl về, không phải mọi repo AI trên GitHub.
- Sửa lỗi kiểu ngày trong `track` bằng cách parse sang `datetime`, như `discover` đang làm. Lỗi của một repo không được làm hỏng cả bước.

### Thu thập dữ liệu thô

Ghi nguyên văn mọi phản hồi từ nguồn bên ngoài, trước khi lọc:

- GitHub Search, GraphQL, README, GitHub Trending (HTML), Hacker News.
- Phản hồi từ model tạo AI summary.
- Cả phản hồi lỗi, kèm mã HTTP. Trường hợp này vẫn là một dòng trong file.

Mỗi dòng JSONL gồm thời điểm, nguồn, request (URL hoặc query, không chứa token), mã trạng thái và body. Nên gắn việc ghi ở lớp client dùng chung (`github_client.py`) cùng các điểm gọi của Trending, HN và summary, để bước mới sau này không bị bỏ sót.

Ghi file thất bại phải làm lần crawl thành `partial` hoặc `failed`, không được bỏ qua trong im lặng.

### Dữ liệu đã xử lý

- Bảng mới `repo_run_snapshots`, khóa `(run_id, repo_id)`: stars, forks, watchers, open_issues, contributors, hot_score, star_growth_7d, star_growth_30d, trending_flag. Ghi sau bước rank.
- Bảng mới `raw_archives`: `run_id`, `source`, đường dẫn tương đối, số dòng, số byte, sha256.
- Giữ `repo_snapshots` theo ngày cho biểu đồ và công thức tăng trưởng hiện có.
- Thay đổi schema phải idempotent, theo kiểu `schema.sql` hiện tại.
- `raw_items` bỏ không dùng nhưng không xóa bảng.

### Báo đúng trạng thái crawl

- Kiểm tra token GitHub trước khi crawl. Token hỏng thì lần crawl là `failed`, ghi rõ nguyên nhân, không chạy tiếp.
- `failed` khi `track` cập nhật được dưới 50% số repo cần cập nhật, hoặc khi không ghi được dữ liệu thô. Khi `track` đã `failed` thì dừng lại: không chạy rank, trending flags, summary, để không tốn tiền và không làm bẩn dữ liệu.
- `partial` khi `track` đạt từ 50% đến dưới 95%, hoặc một trong các bước discover, Trending, HN, categorize, rank thất bại toàn bộ.
- `success` trong các trường hợp còn lại.
- Không tính là lỗi: repo đã xóa hoặc chuyển private, README 404, không có Anthropic key, HN không có kết quả, một vài summary lỗi. Các số này vẫn ghi trong `stats`.
- Sửa `run_daily` để đọc số `failed` mà các bước trả về, không chỉ dựa vào exception.
- Khi worker khởi động, các lần chạy kẹt ở `running` (gồm lần 16) chuyển thành `failed`.
- Sửa lịch sử khi chuyển dữ liệu: lần 17 thành `failed`; các lần `success` có `track` lỗi hoặc `updated: 0` (lần 1, 2, 3, 15) thành `partial`. Giữ nguyên `stats` và ghi lý do vào `error`.

### Vận hành

- Cổng chỉ mở trên máy: `127.0.0.1:3000` (web), `127.0.0.1:8001` (API, đặt được qua biến môi trường), `127.0.0.1:5433` (Postgres, để mở bằng công cụ khác). Hiện web và API mở ra cả mạng. Không đụng tới open-notebook.
- Thêm `scripts/radar.sh` với các lệnh `up`, `down`, `update`, `crawl`, `status`, `backup`.
  - `update`: `git pull`, build lại, khởi động lại. Backup trước khi chạy.
  - `status`: trạng thái dịch vụ, lần crawl gần nhất, dung lượng `data/`.
- Lịch crawl giữ 02:00 UTC (09:00 VN).
- Bỏ crawl mỗi lần khởi động. Thay bằng chạy bù: worker kiểm tra khi khởi động và sau đó mỗi 15 phút, để cả trường hợp máy ngủ qua giờ crawl cũng được xử lý. Nếu đã qua giờ crawl và hôm nay chưa có lần `success` hoặc `partial` thì chạy một lần. "Hôm nay" tính theo ngày UTC, cùng mốc với lịch crawl.
- Lần crawl `failed` được thử lại sau ít nhất 1 giờ, tối đa 3 lần trong ngày. Lần lỗi do token không thử lại.
- Sau mỗi lần crawl, tạo `pg_dump` vào `data/backups/`, ghi đè trong cùng ngày, không xóa file của ngày khác.
- Docker Desktop cần bật tự khởi động theo máy để app tự chạy. Ghi trong README.

### Chuyển dữ liệu

1. Dump `ai-trend-radar_pgdata` trước khi dừng stack cũ, và kiểm tra file dump.
2. Dừng stack ở `~/Desktop/AI/ai-trend-radar`. Không chạy `down -v`.
3. Bật stack từ repo này với `data/postgres`, restore dump.
4. So số dòng từng bảng với số trước khi chuyển.
5. Giữ nguyên volume cũ và folder cũ. Việc xóa do chủ dự án tự quyết sau.

Chạy trên repo này tạo Compose project mới tên `ai-trend-radar-local`, nên volume cũ không tự được dùng lại.

### Bỏ phụ thuộc Render

- Xóa `render.yaml`, `uptime.py`, `.github/workflows/daily-crawl.yml`.
- Viết lại `DEPLOYMENT.md` thành hướng dẫn local, cập nhật `README.md`.
- Không đụng tới `Guide/` và không đụng vào dịch vụ trên Render. Tắt dịch vụ đó là việc chủ dự án làm trên dashboard của Render.
- Làm trên nhánh riêng. Chỉ đưa vào `main` sau khi chủ dự án đã tắt Render, vì Render có thể tự deploy từ `main` và lỗi ở đó.

## Việc chủ dự án phải tự làm

- Tạo GitHub token mới và cập nhật `.env`. Cần kiểm tra token trong `.env` của folder cũ trước, vì hai file khác nhau.

## Tiêu chí hoàn thành

- `./scripts/radar.sh up` từ repo này mở được `http://localhost:3000` với đủ 4.677 repo và số dòng các bảng khớp trước khi chuyển.
- Hai lần crawl trong cùng ngày tạo hai thư mục `run-<id>` và hai bộ dòng trong `repo_run_snapshots`, cộng với bản ghi tương ứng trong `raw_archives`.
- Với token sai, lần crawl có trạng thái `failed` và lỗi nêu rõ nguyên nhân token.
- Với token đúng, `repo_snapshots` có dòng cho mọi repo cập nhật được, và `repo_run_snapshots` có số dòng tương ứng.
- Khởi động lại worker sau giờ crawl mà chưa crawl trong ngày thì có đúng một lần chạy bù; khởi động lại lần nữa thì không chạy thêm.
- Lần crawl `failed` không do token được thử lại không quá 3 lần trong ngày.
- Xóa toàn bộ container rồi `up` lại, dữ liệu vẫn còn.
- `git status` không hiện `data/`.

## Để người xây dựng tự quyết

- Tên biến môi trường và cấu trúc code của phần ghi file thô.
- Cách viết test cụ thể.
- Thứ tự commit.
