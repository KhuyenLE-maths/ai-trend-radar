# 🚀 Deployment Guide — AI Trend Radar

Hướng dẫn deploy AI Trend Radar lên production cho mọi người cùng truy cập.

---

## 📋 Yêu cầu

- GitHub account (để host code)
- API keys: GitHub PAT, Anthropic API
- Domain (tuỳ chọn, có thể dùng subdomain miễn phí)
- VPS hoặc PaaS account

---

## 🎯 Cách 1: Railway.app (Nhanh nhất — khuyến nghị)

### Lợi ích
✅ Tự động deploy từ GitHub  
✅ Tự động scale  
✅ Tự động SSL certificate  
✅ Postgres + Redis built-in  
✅ Không cần setup server  

### Bước 1: Push Code lên GitHub

```bash
cd ~/Desktop/AI/ai-trend-radar

# Tạo git repo (nếu chưa có)
git init
git add .
git commit -m "Initial: AI Trend Radar"

# Push lên GitHub
git remote add origin https://github.com/YOUR_USERNAME/ai-trend-radar.git
git branch -M main
git push -u origin main
```

### Bước 2: Deploy trên Railway

1. Truy cập: https://railway.app (đăng nhập bằng GitHub)
2. New Project → **Deploy from GitHub repo**
3. Chọn repo `ai-trend-radar`
4. Railway tự detect `docker-compose.yml` → Deploy tự động!
5. Chờ khoảng 5-10 phút

### Bước 3: Cấu hình Environment Variables

Trên Railway dashboard:
- Click project → Variables
- Add từ `.env`:
  ```
  GITHUB_TOKEN=github_pat_xxx
  ADMIN_TOKEN=your-secure-token
  ANTHROPIC_API_KEY=sk-ant-xxx
  POSTGRES_PASSWORD=your-secure-password
  ```

### Bước 4: Custom Domain (tuỳ chọn)

Railway → Settings → Domains → Add custom domain
- VD: `trends.example.com`
- Railway tự động cấp SSL!

**Chi phí:** $5-20/tháng (generous free tier)  
**Uptime:** 99.9%  
**Support:** Đa ngôn ngữ, community tốt

---

## 🖥️ Cách 2: Self-hosted trên VPS (Kiểm soát toàn bộ)

### Chọn VPS

| Provider | Giá | Suitability |
|----------|-----|------------|
| **DigitalOcean** | $6/tháng (1 CPU, 1GB RAM) | ⭐⭐⭐⭐⭐ Dễ dùng |
| **Hetzner** | €3/tháng | ⭐⭐⭐⭐ Rẻ, Europe |
| **Vultr** | $3.50/tháng | ⭐⭐⭐⭐ Flexible |
| **Linode** | $5/tháng | ⭐⭐⭐⭐ Hiệu năng cao |

**Recommend:** $6-10/tháng = Hoàn toàn đủ cho 1000 requests/ngày

### System Requirements

- **CPU:** 1-2 cores (1 core đủ khi traffic low)
- **RAM:** 2-4GB (2GB minimum)
- **Storage:** 20GB SSD (database + cache)
- **Bandwidth:** Unlimited (hầu hết providers)

### Bước 1: Setup VPS

```bash
# SSH vào VPS
ssh root@YOUR_VPS_IP

# Update system
apt update && apt upgrade -y

# Install Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sh get-docker.sh
usermod -aG docker root

# Install Docker Compose
curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
chmod +x /usr/local/bin/docker-compose

# Verify
docker --version
docker-compose --version
```

### Bước 2: Clone & Setup Repo

```bash
# Clone code
cd /opt
git clone https://github.com/YOUR_USERNAME/ai-trend-radar.git
cd ai-trend-radar

# Tạo .env từ example
cp .env.example .env

# Edit .env với production values
nano .env
# Thêm: GITHUB_TOKEN, ANTHROPIC_API_KEY, ADMIN_TOKEN, POSTGRES_PASSWORD
```

### Bước 3: Start Containers

```bash
# Build images
docker-compose build

# Start services
docker-compose up -d

# Verify
docker-compose ps
curl http://localhost:3000  # Frontend
curl http://localhost:8000/docs  # API Swagger
```

### Bước 4: Setup Reverse Proxy (Caddy)

Caddy tự động lấy SSL certificate từ Let's Encrypt!

```bash
# Install Caddy
apt install -y caddy

# Tạo Caddyfile
cat > /etc/caddy/Caddyfile << 'EOF'
trends.example.com {
  encode gzip
  reverse_proxy localhost:3000
}

api.trends.example.com {
  reverse_proxy localhost:8000
}
EOF

# Start Caddy
systemctl restart caddy
systemctl enable caddy

# Verify
curl https://trends.example.com  # HTTPS tự động!
```

**Bây giờ:** `https://trends.example.com` có thể truy cập từ khắp nơi! 🎉

### Bước 5: Auto-restart on Reboot

```bash
# Create systemd service
cat > /etc/systemd/system/ai-trend-radar.service << 'EOF'
[Unit]
Description=AI Trend Radar
Requires=docker.service
After=docker.service

[Service]
Type=oneshot
WorkingDirectory=/opt/ai-trend-radar
ExecStart=/usr/bin/docker-compose up -d
RemainAfterExit=yes
ExecStop=/usr/bin/docker-compose down
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable ai-trend-radar
```

### Bước 6: Setup Auto-backup

```bash
# Backup database hàng ngày
cat > /usr/local/bin/backup-radar.sh << 'EOF'
#!/bin/bash
cd /opt/ai-trend-radar
BACKUP_DIR="./backups"
mkdir -p $BACKUP_DIR
docker-compose exec -T postgres pg_dump -U radar radar | \
  gzip > $BACKUP_DIR/db_$(date +%Y%m%d_%H%M%S).sql.gz
# Giữ 30 ngày backup gần nhất
find $BACKUP_DIR -name "db_*.sql.gz" -mtime +30 -delete
EOF

chmod +x /usr/local/bin/backup-radar.sh

# Cron: backup hàng ngày lúc 2 sáng
(crontab -l 2>/dev/null; echo "0 2 * * * /usr/local/bin/backup-radar.sh") | crontab -
```

### Bước 7: Monitoring & Logs

```bash
# Xem logs real-time
docker-compose logs -f

# Xem logs worker
docker-compose logs -f worker

# Xem logs API
docker-compose logs -f api

# Container stats
docker stats
```

---

## 🔐 Security Best Practices

### 1. Firewall Rules

```bash
# UFW (Ubuntu)
ufw default deny incoming
ufw default allow outgoing
ufw allow 22/tcp     # SSH
ufw allow 80/tcp     # HTTP
ufw allow 443/tcp    # HTTPS
ufw enable
```

### 2. Cấu hình SSH

```bash
# Disable root login
sed -i 's/#PermitRootLogin yes/PermitRootLogin no/' /etc/ssh/sshd_config

# Change SSH port (tuỳ chọn)
sed -i 's/#Port 22/Port 2222/' /etc/ssh/sshd_config

# Restart SSH
systemctl restart sshd
```

### 3. API Token Protection

`.env`:
```
ADMIN_TOKEN=generate-a-long-random-token-here
```

Chỉ `/admin/*` endpoints có quyền sử dụng token này.

### 4. Rate Limiting

Caddy config (tự động có):
```
trends.example.com {
  rate_limit * 100 100
  reverse_proxy localhost:3000
}
```

---

## 📊 Monitoring & Maintenance

### Logs & Alerts

```bash
# Cài sentry.io cho error tracking (tuỳ chọn)
# Hoặc dùng ELK stack (Elasticsearch, Logstash, Kibana)
```

### Database Optimization

```bash
# Vacuum database (cleanup)
docker-compose exec postgres psql -U radar -d radar -c "VACUUM ANALYZE;"

# Check indexes
docker-compose exec postgres psql -U radar -d radar -c "SELECT * FROM pg_stat_user_indexes;"
```

### Cache Invalidation

```bash
# Invalidate cache khi cần
docker-compose exec redis redis-cli FLUSHALL

# Hoặc selective
docker-compose exec redis redis-cli DEL "repos:*"
```

---

## 💡 Performance Tips

1. **CDN cho Frontend Assets**
   - Dùng Cloudflare (miễn phí)
   - Cache static files 1 năm

2. **Database Connection Pool**
   - `min_size=5, max_size=20` (đã config)

3. **Redis Cache TTL**
   - Repos list: 1 giờ
   - Categories: 24 giờ
   - Dashboard: 6 giờ

4. **Image Optimization**
   - Logo URLs từ GitHub (không store local)

5. **Crawler Schedule**
   - Chạy lúc 02:00 UTC (off-peak)
   - Tránh crawl khi traffic cao

---

## 🆘 Troubleshooting

| Issue | Giải pháp |
|-------|----------|
| **Port 8000/3000 đã được dùng** | `docker-compose down` trước, hoặc `lsof -i :8000` để kill process |
| **Database connection fail** | Kiểm tra `DATABASE_URL` trong `.env` |
| **GitHub API 401** | `GITHUB_TOKEN` không hợp lệ hoặc hết hạn |
| **Anthropic API fail** | `ANTHROPIC_API_KEY` chưa được set hoặc hết credit |
| **SSL certificate fail** | Kiểm tra domain DNS pointing đúng VPS IP |
| **Memory leak** | Restart containers: `docker-compose restart` |

---

## 📞 Support & Updates

- **Bugs/Features:** Create issue trên GitHub
- **Documentation:** CLAUDE.md (trong repo)
- **API Docs:** `http://your-domain/docs` (Swagger)

---

## 📝 Checklist Pre-launch

- [ ] ✅ GitHub PAT token (5000 requests/hour)
- [ ] ✅ Anthropic API key (optional, cho AI Summary)
- [ ] ✅ Custom domain (hoặc dùng Railway default)
- [ ] ✅ SSL certificate (tự động qua Caddy/Railway)
- [ ] ✅ `.env` variables toàn bộ
- [ ] ✅ Database backup strategy
- [ ] ✅ Firewall rules
- [ ] ✅ Monitoring/logs setup
- [ ] ✅ Test từ external IP/domain
- [ ] ✅ Share URL với team! 🎉

---

**Happy deploying! 🚀**
