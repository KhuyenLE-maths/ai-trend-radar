#!/usr/bin/env python3
"""Keep-alive script: ping app mỗi 10 phút để tránh sleep"""
import requests
import time
from datetime import datetime

API_URL = "https://ai-trend-radar-api.render.com/docs"  # Thay bằng URL thực
CHECK_INTERVAL = 10 * 60  # 10 phút

def keep_alive():
    while True:
        try:
            response = requests.get(API_URL, timeout=10)
            status = "✅" if response.status_code == 200 else "⚠️"
            print(f"{datetime.now()} {status} Pinged {API_URL}")
        except Exception as e:
            print(f"{datetime.now()} ❌ Ping failed: {e}")

        time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    print("🚀 Keep-alive script started")
    keep_alive()
