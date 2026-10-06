import json
import requests
import psutil
from flask import Flask, jsonify, render_template, request

app = Flask(__name__)

# Cấu hình kết nối aria2c JSON-RPC
ARIA2_RPC_URL = "http://127.0.0.1:6800/jsonrpc"
ARIA2_SECRET = ""  # Điền token nếu bạn có cấu hình rpc-secret trong aria2.conf
DOWNLOAD_DIR = "/mnt/phim/_MOVIES"

def call_aria2(method, params=None):
    if params is None: params = []
    if ARIA2_SECRET: params.insert(0, f"token:{ARIA2_SECRET}")
    payload = {"jsonrpc": "2.0", "id": "nucmonitor", "method": f"aria2.{method}", "params": params}
    try:
        res = requests.post(ARIA2_RPC_URL, json=payload, timeout=3)
        return res.json().get("result", {})
    except Exception as e:
        return {"error": str(e)}

@app.route("/")
def index():
    return render_template("index.html")

# ==========================================
# API LẤY THÔNG SỐ  CHAY CARD MAN HINH
# ==========================================
import subprocess

def get_gpu_percent():
    try:
        # Lấy thông số GPU Intel qua fdinfo
        cmd = "cat /sys/class/drm/card*/device/fdinfo/* 2>/dev/null | grep -i 'drm-engine-render' | awk '{print $2}'"
        output = subprocess.check_output(cmd, shell=True).decode().strip()
        if output:
            # Nếu đọc được dữ liệu render
            return min(100, int(output) // 1000000) # Chuẩn hóa về %
    except:
        pass
    return 0

# ==========================================
# API LẤY THÔNG SỐ HARDWARE
# ==========================================
@app.route("/api/hardware")
def get_hardware():
    ram = psutil.virtual_memory()
    
    # Lọc bỏ các phân vùng hệ thống ảo, chỉ giữ lại ổ cứng thực tế
    disks = []
    for p in psutil.disk_partitions(all=False):
        if p.fstype not in ['squashfs', 'tmpfs', 'devtmpfs', 'efivars', 'aufs', 'overlay'] and not p.mountpoint.startswith(('/sys', '/proc', '/dev', '/run')):
            try:
                usage = psutil.disk_usage(p.mountpoint)
                disks.append({
                    "mount": p.mountpoint,
                    "total": round(usage.total / (1024**3), 1),
                    "used": round(usage.used / (1024**3), 1),
                    "percent": usage.percent
                })
            except PermissionError:
                continue

    cpu_temp = 0
    try:
        temps = psutil.sensors_temperatures()
        if 'coretemp' in temps: cpu_temp = temps['coretemp'][0].current
        elif 'acpitz' in temps: cpu_temp = temps['acpitz'][0].current
        elif 'k10temp' in temps: cpu_temp = temps['k10temp'][0].current
    except: pass

    # Lấy thông số chi tiết RAM (GB)
    ram_total = round(ram.total / (1024**3), 2)
    ram_used = round(ram.used / (1024**3), 2)
    ram_cache = round((getattr(ram, 'cached', 0) + getattr(ram, 'buffers', 0)) / (1024**3), 2)
    ram_free = round(ram.available / (1024**3), 2)

    return jsonify({
        "cpu_temp": cpu_temp,
        "cpu_percent": psutil.cpu_percent(interval=0.1),
	"gpu_percent": get_gpu_percent(),
        "ram_total": ram_total,
        "ram_used": ram_used,
        "ram_cache": ram_cache,
        "ram_free": ram_free,
        "ram_percent": ram.percent,
        "disks": disks
    })

# ==========================================
# API QUẢN LÝ TORRENT
# ==========================================
@app.route("/api/torrent/list")
def get_torrents():
    keys = ["gid", "status", "totalLength", "completedLength", "downloadSpeed", "bittorrent", "files"]
    active = call_aria2("tellActive", [keys])
    waiting = call_aria2("tellWaiting", [0, 50, keys])
    stopped = call_aria2("tellStopped", [0, 50, keys])
    return jsonify({"active": active, "waiting": waiting, "stopped": stopped})

@app.route("/api/torrent/add", methods=["POST"])
def add_torrent():
    data = request.json
    uri = data.get("uri")
    if not uri: return jsonify({"success": False, "message": "Vui lòng nhập link Torrent/Magnet"})
    res = call_aria2("addUri", [[uri], {"dir": DOWNLOAD_DIR}])
    if "error" in res: return jsonify({"success": False, "message": str(res["error"])})
    return jsonify({"success": True, "gid": res})

@app.route("/api/torrent/control", methods=["POST"])
def control_torrent():
    data = request.json
    action = data.get("action")
    gid = data.get("gid")
    if action == "pause": res = call_aria2("pause", [gid])
    elif action == "unpause": res = call_aria2("unpause", [gid])
    elif action == "remove": res = call_aria2("remove", [gid])
    else: return jsonify({"success": False, "message": "Hành động không hợp lệ"})
    return jsonify({"success": True, "result": res})

# ==========================================
# API CHẠY LỆNH DỊCH PHỤ ĐỀ (TỰ ĐỘNG CẤP QUYỀN & BẮT LỖI MẠNH MẼ)
# ==========================================
@app.route("/api/torrent/translate", methods=["POST"])
def translate_subtitle():
    import os
    import subprocess

    python_bin = "/usr/bin/python3"
    script_path = "/home/huykhoi/scripts/auto_translate.py"
    work_dir = "/home/huykhoi/scripts"
    log_path = "/home/huykhoi/scripts/translate_debug.log"

    # Kiểm tra xem file script có tồn tại không
    if not os.path.exists(script_path):
        return jsonify({"success": False, "message": f"Không tìm thấy file: {script_path}"})

    try:
        # Mở file log dạng ghi đè/nối (a+)
        log_file = open(log_path, "a+", encoding="utf-8")
        
        # Chạy tiến trình ngầm
        proc = subprocess.Popen(
            [python_bin, script_path],
            cwd=work_dir,
            stdout=log_file,
            stderr=log_file,
            start_new_session=True # Đảm bảo tiến trình chạy độc lập không bị dính theo Flask
        )
        
        return jsonify({"success": True, "message": f"Đã kích hoạt dịch! (PID: {proc.pid})"})
    except Exception as e:
        return jsonify({"success": False, "message": f"Lỗi khởi chạy: {str(e)}"})

# ==========================================
# API LẤY DANH SÁCH SERVICES / TIẾN TRÌNH
# ==========================================
@app.route("/api/services")
def get_services():
    processes = []
    
    # 1. Lấy tổng % CPU và RAM toàn hệ thống
    total_cpu = psutil.cpu_percent(interval=None)
    total_ram = psutil.virtual_memory().percent

    # 2. Lấy số nhân CPU để quy đổi % chuẩn hóa
    cpu_cores = psutil.cpu_count() or 1

    # 3. Quét danh sách tiến trình
    for proc in psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_percent']):
        try:
            pinfo = proc.info
            
            # Chuẩn hóa % CPU của tiến trình theo tổng số nhân hệ thống
            normalized_cpu = round(pinfo['cpu_percent'] / cpu_cores, 1)
            
            if normalized_cpu > 0.1 or pinfo['memory_percent'] > 0.5:
                processes.append({
                    'pid': pinfo['pid'],
                    'name': pinfo['name'],
                    'cpu': normalized_cpu,
                    'ram': round(pinfo['memory_percent'], 1)
                })
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            pass
    
    # Sắp xếp giảm dần theo mức CPU đã chuẩn hóa
    processes = sorted(processes, key=lambda x: x['cpu'], reverse=True)[:15]

    return jsonify({
        'total_cpu': total_cpu,
        'total_ram': total_ram,
        'processes': processes
    })

# ==========================================
# API QUẢN TRỊ (MANAGE) - ĐĂNG NHẬP BẰNG TÀI KHOẢN SSH
# ==========================================
import re
import shlex
import secrets
import threading
import time
from functools import wraps

import paramiko

SSH_HOST = "127.0.0.1"
SSH_PORT = 22
SESSION_COOKIE = "nuc_manage"
SESSION_TTL = 30 * 60          # Tự đăng xuất sau 30 phút không thao tác
MAX_LOGIN_FAILURES = 5         # Sai quá 5 lần thì khóa IP...
LOCKOUT_SECONDS = 5 * 60       # ...trong 5 phút

# Phiên đăng nhập lưu trong RAM (mật khẩu không bao giờ gửi về trình duyệt)
_sessions = {}
_login_failures = {}
_lock = threading.Lock()

SYSTEMD_NAME_RE = re.compile(r'^[A-Za-z0-9@._:\\-]+\.service$')
DOCKER_NAME_RE = re.compile(r'^[A-Za-z0-9][A-Za-z0-9_.-]*$')

def ssh_connect(username, password):
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    # Tắt look_for_keys/allow_agent để bắt buộc xác thực bằng mật khẩu người dùng nhập
    client.connect(SSH_HOST, port=SSH_PORT, username=username, password=password,
                   timeout=5, auth_timeout=5, banner_timeout=5,
                   look_for_keys=False, allow_agent=False)
    return client

def ssh_run(client, cmd, sudo_password=None, timeout=30):
    if sudo_password is not None:
        cmd = "sudo -S -p '' " + cmd
    stdin, stdout, stderr = client.exec_command(cmd, timeout=timeout)
    if sudo_password is not None:
        stdin.write(sudo_password + "\n")
        stdin.flush()
    stdin.channel.shutdown_write()
    out = stdout.read().decode(errors="replace")
    err = stderr.read().decode(errors="replace")
    return stdout.channel.recv_exit_status(), out, err

def ssh_run_docker(client, cmd, password):
    # Chạy docker không sudo trước, nếu user không thuộc nhóm docker thì thử lại với sudo
    code, out, err = ssh_run(client, cmd)
    if code != 0 and "permission denied" in err.lower():
        code, out, err = ssh_run(client, cmd, sudo_password=password)
    return code, out, err

def get_session():
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        return None
    with _lock:
        sess = _sessions.get(token)
        if not sess:
            return None
        if time.time() - sess["last"] > SESSION_TTL:
            _sessions.pop(token, None)
            return None
        sess["last"] = time.time()
        return sess

def manage_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        sess = get_session()
        if not sess:
            return jsonify({"success": False, "auth": False, "message": "Phiên đăng nhập đã hết hạn"}), 401
        try:
            client = ssh_connect(sess["user"], sess["password"])
        except Exception as e:
            return jsonify({"success": False, "message": f"Lỗi kết nối SSH: {e}"}), 502
        try:
            return f(client, sess, *args, **kwargs)
        except Exception as e:
            return jsonify({"success": False, "message": f"Lỗi thực thi lệnh: {e}"}), 500
        finally:
            client.close()
    return wrapper

@app.route("/api/manage/status")
def manage_status():
    sess = get_session()
    return jsonify({"auth": bool(sess), "user": sess["user"] if sess else None})

@app.route("/api/manage/login", methods=["POST"])
def manage_login():
    ip = request.remote_addr
    now = time.time()
    with _lock:
        fail = _login_failures.get(ip)
        if fail and now - fail[1] >= LOCKOUT_SECONDS:
            _login_failures.pop(ip, None)
            fail = None
        if fail and fail[0] >= MAX_LOGIN_FAILURES:
            wait = int((LOCKOUT_SECONDS - (now - fail[1])) // 60) + 1
            return jsonify({"success": False, "message": f"Sai quá nhiều lần, thử lại sau {wait} phút"}), 429

    data = request.json or {}
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""
    if not username or not password:
        return jsonify({"success": False, "message": "Vui lòng nhập tài khoản và mật khẩu"}), 400

    try:
        ssh_connect(username, password).close()
    except paramiko.AuthenticationException:
        with _lock:
            fail = _login_failures.setdefault(ip, [0, now])
            fail[0] += 1
        return jsonify({"success": False, "message": "Sai tài khoản hoặc mật khẩu"}), 401
    except Exception as e:
        return jsonify({"success": False, "message": f"Không kết nối được SSH: {e}"}), 502

    token = secrets.token_urlsafe(32)
    with _lock:
        _login_failures.pop(ip, None)
        _sessions[token] = {"user": username, "password": password, "last": time.time()}
    resp = jsonify({"success": True, "user": username})
    resp.set_cookie(SESSION_COOKIE, token, httponly=True, samesite="Strict")
    return resp

@app.route("/api/manage/logout", methods=["POST"])
def manage_logout():
    token = request.cookies.get(SESSION_COOKIE)
    with _lock:
        _sessions.pop(token, None)
    resp = jsonify({"success": True})
    resp.delete_cookie(SESSION_COOKIE)
    return resp

@app.route("/api/manage/power", methods=["POST"])
@manage_required
def manage_power(client, sess):
    action = (request.json or {}).get("action")
    commands = {"reboot": "systemctl reboot", "shutdown": "systemctl poweroff"}
    if action not in commands:
        return jsonify({"success": False, "message": "Hành động không hợp lệ"}), 400
    try:
        code, out, err = ssh_run(client, commands[action], sudo_password=sess["password"], timeout=15)
    except Exception:
        # Máy tắt/khởi động lại có thể cắt kết nối SSH trước khi trả kết quả
        code, err = 0, ""
    if code != 0:
        return jsonify({"success": False, "message": err.strip() or f"Lỗi (mã {code})"})
    label = "Khởi động lại" if action == "reboot" else "Tắt máy"
    return jsonify({"success": True, "message": f"Đã gửi lệnh {label}"})

def list_systemd_services(client):
    services = {}
    _, out, _ = ssh_run(client, "systemctl list-unit-files --type=service --plain --no-legend --no-pager")
    for line in out.splitlines():
        parts = line.split()
        # Bỏ qua các unit mẫu (foo@.service), chúng chỉ chạy qua instance
        if len(parts) >= 2 and not parts[0].endswith("@.service"):
            services[parts[0]] = {"name": parts[0], "enabled": parts[1], "active": "inactive",
                                  "sub": "dead", "description": ""}

    _, out, _ = ssh_run(client, "systemctl list-units --type=service --all --plain --no-legend --no-pager")
    for line in out.splitlines():
        parts = line.lstrip("● ").split(None, 4)
        if len(parts) < 4 or parts[1] == "not-found":
            continue
        svc = services.setdefault(parts[0], {"name": parts[0], "enabled": "-"})
        svc.update({"active": parts[2], "sub": parts[3],
                    "description": parts[4] if len(parts) > 4 else ""})
    return sorted(services.values(), key=lambda s: s["name"])

def list_docker_containers(client, password):
    fmt = "{{.Names}}\t{{.Image}}\t{{.State}}\t{{.Status}}"
    code, out, err = ssh_run_docker(client, f"docker ps -a --format {shlex.quote(fmt)}", password)
    if code == 127:
        return [], "Docker chưa được cài đặt"
    if code != 0:
        return [], err.strip() or f"Lỗi docker (mã {code})"
    containers = []
    for line in out.splitlines():
        parts = line.split("\t")
        if len(parts) == 4:
            containers.append({"name": parts[0], "image": parts[1], "state": parts[2], "status": parts[3]})
    return sorted(containers, key=lambda c: c["name"]), None

@app.route("/api/manage/services")
@manage_required
def manage_services(client, sess):
    systemd = list_systemd_services(client)
    docker, docker_error = list_docker_containers(client, sess["password"])
    return jsonify({"success": True, "systemd": systemd, "docker": docker, "docker_error": docker_error})

@app.route("/api/manage/service", methods=["POST"])
@manage_required
def manage_service_action(client, sess):
    data = request.json or {}
    kind, name, action = data.get("type"), data.get("name") or "", data.get("action")
    if action not in ("start", "stop", "restart"):
        return jsonify({"success": False, "message": "Hành động không hợp lệ"}), 400

    if kind == "systemd" and SYSTEMD_NAME_RE.match(name):
        code, out, err = ssh_run(client, f"systemctl {action} {shlex.quote(name)}",
                                 sudo_password=sess["password"], timeout=60)
    elif kind == "docker" and DOCKER_NAME_RE.match(name):
        code, out, err = ssh_run_docker(client, f"docker {action} {shlex.quote(name)}", sess["password"])
    else:
        return jsonify({"success": False, "message": "Tên service không hợp lệ"}), 400

    if code != 0:
        return jsonify({"success": False, "message": err.strip() or f"Lỗi (mã {code})"})
    return jsonify({"success": True})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)