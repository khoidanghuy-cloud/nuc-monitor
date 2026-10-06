#!/bin/bash
set -e

# Kiểm tra quyền root
if [ "$EUID" -ne 0 ]; then
  echo "❌ Vui lòng chạy script với quyền sudo/root: sudo bash install.sh"
  exit 1
fi

REPO_RAW="https://raw.githubusercontent.com/khoidanghuy-cloud/nuc-monitor/main"
APP_DIR="/opt/nuc-monitor"

echo "🚀 Đang bắt đầu cài đặt NUC Monitor..."

# 1. Cài đặt các gói phụ thuộc cần thiết
echo "📦 Đang cài đặt python3 và các thư viện (flask, psutil, requests, paramiko)..."
apt-get update -y
apt-get install -y curl lm-sensors python3 python3-flask python3-psutil python3-requests python3-paramiko

# 2. Tải mã nguồn ứng dụng từ GitHub
echo "📝 Đang tải ứng dụng về $APP_DIR..."
mkdir -p "$APP_DIR/templates"
curl -fsSL "$REPO_RAW/app.py" -o "$APP_DIR/app.py"
curl -fsSL "$REPO_RAW/templates/index.html" -o "$APP_DIR/templates/index.html"

# Xóa bản cũ (standalone) nếu có
rm -f /opt/nuc_monitor.py

# 3. Tạo Service khởi động cùng hệ thống (Systemd)
echo "⚙️ Đang cấu hình Systemd Service..."
cat << EOF > /etc/systemd/system/nuc-monitor.service
[Unit]
Description=NUC Monitor & Torrent Manager
After=network-online.target
Wants=network-online.target

[Service]
WorkingDirectory=$APP_DIR
ExecStart=/usr/bin/python3 $APP_DIR/app.py
Restart=always
RestartSec=5
User=root

[Install]
WantedBy=multi-user.target
EOF

# 4. Kích hoạt dịch vụ
systemctl daemon-reload
systemctl enable nuc-monitor
systemctl restart nuc-monitor

echo "✅ CÀI ĐẶT HOÀN TẤT!"
echo "🌐 Bạn có thể truy cập ngay tại địa chỉ: http://<IP_MAY_LINUX>:8080"
