from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Toàn bộ cấu hình đọc từ biến môi trường (12-factor). Xem .env.example."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Hạ tầng
    database_url: str = "postgresql://radar:radar@localhost:5432/radar"
    redis_url: str = "redis://localhost:6379/0"

    # Lưu trữ
    raw_data_dir: str = "/data/raw"        # dữ liệu thô từng lần crawl (bind mount ./data/raw)

    # Nguồn dữ liệu
    github_token: str = ""                 # BẮT BUỘC để crawl (5000 req/h)
    # LLM Gemini (tuỳ chọn — không có key thì pipeline bỏ qua bước AI Summary)
    gemini_api_key: str = ""
    summary_model: str = "gemini-3.8-flash"
    summary_daily_limit: int = 20          # số repo tóm tắt tối đa mỗi ngày

    # Bảo mật & vận hành
    admin_token: str = "changeme"
    slack_webhook_url: str = ""
    pipeline_cron: str = "0 2 * * *"       # 02:00 UTC = 09:00 VN

    # Tham số crawl / lọc
    discover_pages_per_query: int = 2      # số trang (100 repo/trang) mỗi truy vấn search
    discover_min_stars: int = 50           # sao tối thiểu khi discover
    ai_filter_threshold: float = 3.0       # ngưỡng điểm AI-relevance (tầng rule)
    cache_ttl_seconds: int = 900


settings = Settings()
