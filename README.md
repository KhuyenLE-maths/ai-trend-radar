# AI Trend Radar

Radar theo dõi các repo AI trên GitHub, chạy trên máy cá nhân và mở qua browser. Mỗi lần crawl đều được lưu lại trong folder `data/`.

```bash
cp .env.example .env      # điền GITHUB_TOKEN và ADMIN_TOKEN
./scripts/radar.sh up     # mở http://localhost:3000
```

Xem [DEPLOYMENT.md](DEPLOYMENT.md) để biết cách vận hành, cấu trúc dữ liệu và cách khôi phục.
