from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Toàn bộ cấu hình đọc từ biến môi trường (12-factor). Xem .env.example."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Hạ tầng
    database_url: str = "postgresql://radar:radar@localhost:5432/radar"
    redis_url: str = "redis://localhost:6379/0"

    # Nguồn dữ liệu
    github_token: str = ""                 # BẮT BUỘC để crawl (5000 req/h)
    # LLM (tuỳ chọn — không có key thì pipeline bỏ qua bước AI Summary)
    anthropic_api_key: str = ""
    summary_model: str = "claude-haiku-4-5"
    summary_daily_limit: int = 20          # số repo tóm tắt tối đa mỗi ngày

    # Bảo mật & vận hành
    admin_token: str = "changeme"
    slack_webhook_url: str = ""
    pipeline_cron: str = "0 2 * * *"       # 02:00 UTC = 09:00 VN
    run_on_start: bool = False             # worker chạy pipeline ngay khi khởi động (tiện demo)

    # Tham số crawl / lọc
    max_tracked_repos: int = 3000          # trần số repo track mỗi ngày (rate-limit safety)
    discover_pages_per_query: int = 2      # số trang (100 repo/trang) mỗi truy vấn search
    discover_min_stars: int = 50           # sao tối thiểu khi discover
    ai_filter_threshold: float = 3.0       # ngưỡng điểm AI-relevance (tầng rule)
    cache_ttl_seconds: int = 900


settings = Settings()
