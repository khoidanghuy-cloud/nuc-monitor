#!/bin/bash

# Kiểm tra quyền root
if [ "$EUID" -ne 0 ]; then
  echo "❌ Vui lòng chạy script với quyền sudo/root: sudo bash install.sh"
  exit 1
fi

echo "🚀 Đang bắt đầu cài đặt NUC Monitor..."

# 1. Cài đặt các gói phụ thuộc cần thiết
echo "📦 Đang cài đặt lm-sensors và python3..."
apt-get update -y && apt-get install -y lm-sensors python3

# 2. Tạo file Python ứng dụng
echo "📝 Đang khởi tạo ứng dụng /opt/nuc_monitor.py..."
cat << 'EOF' > /opt/nuc_monitor.py
import http.server
import socketserver
import json
import time
import threading
import subprocess
from collections import deque

history = deque(maxlen=60)

def get_sys_data():
    try:
        with open('/sys/class/thermal/thermal_zone0/temp', 'r') as f:
            temp = round(float(f.read().strip()) / 1000.0, 1)
    except: temp = 0.0

    try:
        out = subprocess.check_output("sensors 2>/dev/null | grep -i 'fan1' | awk '{print $2}'", shell=True).strip()
        fan = float(out) if out else 0.0
    except: fan = 0.0
    return temp, fan

def get_ram():
    try:
        with open('/proc/meminfo', 'r') as f:
            data = {k.strip(): int(v.split()[0]) for k, v in [line.split(':') for line in f if ':' in line]}
        total = round(data.get('MemTotal', 0) / 1048576, 2)
        free_pure = round(data.get('MemFree', 0) / 1048576, 2)
        cache = round((data.get('Buffers', 0) + data.get('Cached', 0) + data.get('SReclaimable', 0)) / 1048576, 2)
        avail = round(data.get('MemAvailable', free_pure + cache) / 1048576, 2)
        used = max(0, round(total - avail, 2))
        return {"total": total, "used": used, "cache": cache, "free": free_pure}
    except: return {"total":0, "used":0, "cache":0, "free":0}

def get_disks():
    try:
        out = subprocess.check_output("df -h --output=target,size,used,pcent -x tmpfs -x devtmpfs -x squashfs -x overlay -x efivarfs 2>/dev/null", shell=True, text=True)
        return [{"mount": c[0], "size": c[1], "used": c[2], "percent": int(c[3].replace('%', ''))} for c in [line.split() for line in out.strip().split('\n')[1:]] if len(c) >= 4]
    except: return []

def record_loop():
    while True:
        t, f = get_sys_data()
        history.append({"time_label": time.strftime("%H:%M:%S %d/%m/%Y"), "temp": t, "fan": f})
        time.sleep(60)

threading.Thread(target=record_loop, daemon=True).start()

HTML_PAGE = """<!DOCTYPE html>
<html lang="vi">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"><title>NUC Monitor</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
<style>
body{font-family:system-ui,sans-serif;background:#0f172a;color:white;padding:20px;display:flex;justify-content:center}
.container{width:100%;max-width:950px;background:#1e293b;padding:24px;border-radius:16px;display:flex;flex-direction:column;gap:24px}
.header{display:flex;justify-content:space-between;align-items:center;border-bottom:1px solid #334155;padding-bottom:16px}
.title{font-size:1.25rem;font-weight:bold;color:#38bdf8}
.badge{font-weight:bold;padding:6px 12px;border-radius:12px;background:#0284c7}
.badge-fan{background:#0d9488}
.section-title{font-weight:bold;color:#cbd5e1;margin-bottom:12px}
.chart-box{height:320px;position:relative} .ram-chart-box{height:180px;position:relative}
.disk-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:15px}
.disk-item{background:#0f172a;padding:14px;border-radius:12px;border:1px solid #334155}
.progress-bar{background:#334155;height:8px;border-radius:4px;margin-top:4px}
.progress-fill{background:#38bdf8;height:100%}
</style></head><body>
<div class="container">
  <div class="header">
    <div class="title">🖥️ Linux Hardware Monitor</div>
    <div style="display:flex;gap:10px">
      <div class="badge" id="liveTemp">🌡️ --°C</div><div class="badge badge-fan" id="liveFan">🌀 -- RPM</div>
    </div>
  </div>
  <div><div class="section-title">📈 Nhiệt độ & Quạt</div><div class="chart-box"><canvas id="hwChart"></canvas></div></div>
  <div><div class="section-title">🧠 RAM (GB)</div><div class="ram-chart-box"><canvas id="ramChart"></canvas></div></div>
  <div><div class="section-title">💾 Ổ cứng</div><div class="disk-grid" id="diskContainer"></div></div>
</div>
<script>
let hwChart, rChart;
async function loadData() {
    try {
        const res = await (await fetch('/api/data')).json();
        const data = res.chart || [];
        if(data.length > 0) {
            document.getElementById('liveTemp').innerText = '🌡️ ' + data[data.length-1].temp + '°C';
            document.getElementById('liveFan').innerText = '🌀 ' + data[data.length-1].fan + ' RPM';
        }
        const labels = data.map(d=>d.time_label), temps = data.map(d=>d.temp), fans = data.map(d=>d.fan);
        if(hwChart) { hwChart.data.labels=labels; hwChart.data.datasets[0].data=temps; hwChart.data.datasets[1].data=fans; hwChart.update('none'); }
        else {
            hwChart = new Chart(document.getElementById('hwChart'), { type:'line', data:{ labels, datasets:[ {label:'°C',data:temps,borderColor:'#38bdf8',backgroundColor:'rgba(56,189,248,0.1)',fill:true,yAxisID:'y'}, {label:'RPM',data:fans,borderColor:'#2dd4bf',yAxisID:'y1'} ] }, options:{responsive:true,maintainAspectRatio:false,scales:{y:{position:'left',grid:{color:'#334155'}},y1:{position:'right',grid:{drawOnChartArea:false}},x:{grid:{color:'#334155'}}}} });
        }
        const ram = res.ram;
        if(ram && ram.total>0) {
            const rVals = [ram.used, ram.cache, ram.free];
            const rLabels = ['Dùng (' + ram.used + 'G)', 'Cache (' + ram.cache + 'G)', 'Trống (' + ram.free + 'G)'];
            if(rChart) { 
                rChart.data.labels = rLabels; 
                rChart.data.datasets[0].data = rVals; 
                rChart.options.scales.x.title.text = 'GB (Tổng: ' + ram.total + ' GB)'; 
                rChart.update('none'); 
            } else { 
                rChart = new Chart(document.getElementById('ramChart'), { 
                    type: 'bar', 
                    data: { 
                        labels: rLabels, 
                        datasets: [{
                            data: rVals, 
                            backgroundColor: ['#f43f5e', '#fbbf24', '#10b981'], 
                            borderRadius: 6
                        }] 
                    }, 
                    options: {
                        responsive: true, 
                        maintainAspectRatio: false, 
                        indexAxis: 'y', 
                        scales: {
                            x: {
                                grid: {color: '#334155'}, 
                                title: {display: true, text: 'GB (Tổng: ' + ram.total + ' GB)', color: '#94a3b8'}, 
                                ticks: {color: '#cbd5e1'}
                            }, 
                            y: {
                                grid: {display: false}, 
                                ticks: {color: '#ffffff', font: {weight: 'bold'}}
                            }
                        }, 
                        plugins: {legend: {display: false}} 
                    } 
                }); 
            }
        }
        document.getElementById('diskContainer').innerHTML = (res.disk||[]).map(d=>`<div class='disk-item'><b>📂 ${d.mount}</b><br>Dùng: ${d.used}/${d.size} (${d.percent}%)<div class='progress-bar'><div class='progress-fill' style='width:${d.percent}%'></div></div></div>`).join('');
    } catch(e){}
}
loadData(); setInterval(loadData, 15000);
</script></body></html>"""

class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/api/data':
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({"chart": list(history), "ram": get_ram(), "disk": get_disks()}).encode('utf-8'))
        else:
            self.send_response(200)
            self.send_header('Content-type', 'text/html; charset=utf-8')
            self.end_headers()
            self.wfile.write(HTML_PAGE.encode('utf-8'))
            
    def log_message(self, format, *args): 
        pass

if __name__ == '__main__':
    PORT = 8080
    with socketserver.TCPServer(("", PORT), Handler) as httpd:
        httpd.serve_forever()
EOF

# 3. Tạo Service khởi động cùng hệ thống (Systemd)
echo "⚙️ Đang cấu hình Systemd Service..."
cat << 'EOF' > /etc/systemd/system/nuc-monitor.service
[Unit]
Description=NUC Monitor Standalone Service
After=network.target

[Service]
ExecStart=/usr/bin/python3 /opt/nuc_monitor.py
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
