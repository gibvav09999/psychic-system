#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PEPE FAUCET BOT + CAPTCHA SOLVER INTEGRATION (CodeSandbox / Devbox Ready)
- Tự động vượt Simply.com / Cloudflare PoW Security Check
- Tự động đăng nhập FaucetPay Email và duy trì phiên làm việc
- Tự động lấy CSRF token & Sitekey trên /faucet/PEPE
- Gọi Solver API giải reCAPTCHA v2 / v3
- Tự động kiểm tra Cooldown và thực hiện Claim định kỳ
"""

import sys
import os
import json
import time
import re
import hashlib
import requests
import traceback
from datetime import datetime
from threading import Thread
from http.server import HTTPServer, BaseHTTPRequestHandler

# Nạp .env nếu có
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# Hỗ trợ màu terminal với colorama
try:
    from colorama import init, Fore, Style
    init(autoreset=True)
    COLOR_ENABLED = True
except ImportError:
    COLOR_ENABLED = False

# ============= UNBUFFERED OUTPUT =============
try:
    sys.stdout.reconfigure(line_buffering=True)
except AttributeError:
    import functools
    print = functools.partial(print, flush=True)

# ============= CẤU HÌNH =============
EMAIL = os.environ.get("EMAIL", "jonybins77@gmail.com")
SOLVER_URL = os.environ.get("SOLVER_URL", "http://127.0.0.1:8080").rstrip("/")
SOLVER_KEY = os.environ.get("SOLVER_KEY", "")
COOKIES_FILE = os.path.join(os.path.dirname(__file__), "cookies_pepe.json")
STATS_FILE   = os.path.join(os.path.dirname(__file__), "stats_pepe.json")
LOG_FILE     = os.path.join(os.path.dirname(__file__), "bot.log")
MAX_CLAIMS   = int(os.environ.get("MAX_CLAIMS", "100000"))
HEALTH_PORT  = int(os.environ.get("HEALTH_PORT", "7860"))
ENABLE_HEALTH_SERVER = os.environ.get("ENABLE_HEALTH_SERVER", "false").lower() == "true"

BASE_URL = "https://freepepecoin.com"
FAUCET_URL = f"{BASE_URL}/faucet/PEPE"

# ============= LOGGING =============
def get_colored(text, color_code):
    if COLOR_ENABLED:
        return f"{color_code}{text}{Style.RESET_ALL}"
    return text

def log(level, message):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    color_map = {
        "INFO": Fore.CYAN if COLOR_ENABLED else "",
        "SUCCESS": Fore.GREEN if COLOR_ENABLED else "",
        "WARNING": Fore.YELLOW if COLOR_ENABLED else "",
        "ERROR": Fore.RED if COLOR_ENABLED else ""
    }
    prefix = f"[{timestamp}] [{level}]"
    colored_prefix = get_colored(prefix, color_map.get(level, ""))
    print(f"{colored_prefix} {message}")
    
    try:
        with open(LOG_FILE, 'a', encoding='utf-8') as f:
            f.write(f"{prefix} {message}\n")
    except Exception:
        pass

def log_info(msg):
    log("INFO", msg)

def log_success(msg):
    log("SUCCESS", msg)

def log_warning(msg):
    log("WARNING", msg)

def log_error(msg):
    log("ERROR", msg)

# ============= OPTIONAL HEALTHCHECK SERVER =============
class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        response = json.dumps({"status": "running", "total_claims": total_claims, "email": EMAIL})
        self.wfile.write(response.encode('utf-8'))
        
    def log_message(self, format, *args):
        pass

def start_health_server():
    if not ENABLE_HEALTH_SERVER:
        return
    try:
        server = HTTPServer(('0.0.0.0', HEALTH_PORT), HealthHandler)
        log_info(f"✅ Healthcheck server running on port {HEALTH_PORT}")
        server.serve_forever()
    except Exception as e:
        log_warning(f"Healthcheck server not started: {e}")

Thread(target=start_health_server, daemon=True).start()

# ============= HTTP SESSION =============
session = requests.Session()
session.max_redirects = 5
session.headers.update({
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.9',
    'Origin': BASE_URL,
    'Referer': f"{BASE_URL}/"
})

# Proxy nếu có
http_proxy = os.environ.get("HTTP_PROXY")
https_proxy = os.environ.get("HTTPS_PROXY")
if http_proxy or https_proxy:
    session.proxies = {
        'http': http_proxy or https_proxy,
        'https': https_proxy or http_proxy
    }
    log_info(f"🌐 Đã cấu hình Proxy: {http_proxy or https_proxy}")

# ============= TEST KONEKSI SOLVER =============
def test_solver():
    log_info(f"🔍 Kiểm tra kết nối tới Solver API tại: {SOLVER_URL}")
    try:
        resp = requests.get(f"{SOLVER_URL}/", timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            log_success(f"✅ Solver API sẵn sàng! Phiên bản: {data.get('server', {}).get('version', 'N/A')}")
            return True
        else:
            log_warning(f"⚠️ Solver API trả về HTTP code: {resp.status_code}")
            return False
    except Exception as e:
        log_warning(f"⚠️ Không thể kết nối tới Solver API ({e}). Đảm bảo bạn chạy bằng 'bash start.sh'.")
        return False

# ============= COOKIES & STATS =============
def save_cookies():
    try:
        cookies_dict = requests.utils.dict_from_cookiejar(session.cookies)
        with open(COOKIES_FILE, 'w', encoding='utf-8') as f:
            json.dump({
                'cookies': cookies_dict,
                'user_agent': session.headers.get('User-Agent'),
                'saved_at': datetime.now().isoformat(),
                'email': EMAIL
            }, f, indent=2)
        return True
    except Exception as e:
        log_warning(f"⚠️ Không lưu được cookies: {e}")
        return False

def load_cookies():
    try:
        if os.path.exists(COOKIES_FILE):
            with open(COOKIES_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                if data.get('email') == EMAIL:
                    cookies_dict = data.get('cookies', {})
                    session.cookies = requests.utils.cookiejar_from_dict(cookies_dict)
                    if data.get('user_agent'):
                        session.headers['User-Agent'] = data['user_agent']
                    log_info("✓ Đã nạp cookies phiên làm việc đã lưu")
                    return True
    except Exception as e:
        log_warning(f"⚠️ Không nạp được cookies: {e}")
    return False

def load_total_claims():
    try:
        if os.path.exists(STATS_FILE):
            with open(STATS_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return data.get('total_claims', 0)
    except Exception:
        pass
    return 0

def save_total_claims(total):
    try:
        with open(STATS_FILE, 'w', encoding='utf-8') as f:
            json.dump({'total_claims': total, 'updated': datetime.now().isoformat()}, f, indent=2)
    except Exception as e:
        log_warning(f"⚠️ Không lưu được thống kê: {e}")

# ============= SIMPLY.COM WAF POW SOLVER =============
def solve_simply_pow(html):
    t_match = re.search(r'var T="([a-f0-9]+)"', html) or re.search(r'T="([a-f0-9]+)"', html)
    ts_match = re.search(r'TS="([0-9]+)"', html)
    d_match = re.search(r'D=([0-9]+)', html)

    if not (t_match and ts_match and d_match):
        return False

    T = t_match.group(1)
    TS = ts_match.group(1)
    D = int(d_match.group(1))

    log_info(f"  [WAF] Đang giải Proof-of-Work bảo vệ (Difficulty={D})...")

    def lz(h):
        count = 0
        for ch in h:
            n = int(ch, 16)
            if n == 0: count += 4
            elif n < 2: count += 3; break
            elif n < 4: count += 2; break
            elif n < 8: count += 1; break
            else: break
        return count

    nonce = 0
    t0 = time.time()
    while True:
        h = hashlib.sha256(f"{T}:{nonce}".encode()).hexdigest()
        if lz(h) >= D:
            break
        nonce += 1

    dur = time.time() - t0
    log_success(f"  ✓ PoW Solved (Nonce: {nonce} trong {dur:.2f}s)")

    resp = session.post(
        f"{BASE_URL}/.sc-verify/",
        data={"ts": TS, "nonce": str(nonce), "token": T},
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Referer": f"{BASE_URL}/",
            "Origin": BASE_URL
        },
        timeout=15
    )

    try:
        j = resp.json()
        if j.get("ok"):
            session.cookies.set("sc_clearance", j["cookie"], domain="freepepecoin.com")
            log_success("  ✓ Đã thiết lập sc_clearance cookie thành công")
            save_cookies()
            return True
    except Exception as e:
        log_error(f"  ❌ Lỗi xác thực PoW: {e}")
    return False

def get_page(url, allow_redirects=True):
    """Tự động xử lý WAF/PoW khi truy cập trang bất kỳ."""
    try:
        resp = session.get(url, allow_redirects=allow_redirects, timeout=20)
        if resp.status_code in (454, 455) or "Checking your browser" in resp.text:
            if solve_simply_pow(resp.text):
                time.sleep(1)
                resp = session.get(url, allow_redirects=allow_redirects, timeout=20)
        return resp
    except requests.exceptions.TooManyRedirects:
        # Nếu gặp vòng lặp redirect, tự động đăng nhập lại
        log_warning("  ⚠️ Phát hiện chuyển hướng nhiều lần, đang đăng nhập lại...")
        login()
        try:
            return session.get(url, allow_redirects=False, timeout=20)
        except Exception:
            return None
    except Exception as e:
        log_error(f"  ❌ Lỗi kết nối {url}: {e}")
        return None

# ============= LOGIN FLOW =============
def login():
    log_info(f"🔑 Đang đăng nhập tài khoản FaucetPay: {EMAIL}...")
    r = get_page(f"{BASE_URL}/")
    if not r:
        return False

    try:
        login_resp = session.post(
            f"{BASE_URL}/",
            data={"address": EMAIL},
            headers={"Content-Type": "application/x-www-form-urlencoded", "Referer": f"{BASE_URL}/"},
            allow_redirects=True,
            timeout=20
        )
        if login_resp.status_code in (200, 302):
            log_success(f"  ✅ Đăng nhập thành công!")
            save_cookies()
            return True
        else:
            log_error(f"  ❌ Đăng nhập thất bại (HTTP {login_resp.status_code})")
            return False
    except Exception as e:
        log_error(f"  ❌ Lỗi gửi đăng nhập: {e}")
        return False

def ensure_login():
    """Đảm bảo tài khoản đã đăng nhập trước khi vào trang faucet."""
    if "faucet_user" not in session.cookies:
        return login()
    return True

# ============= SOLVE RECAPTCHA =============
def solve_recaptcha(site_key, is_v2=True):
    solver_type = "recaptcha2" if is_v2 else "recaptcha3"
    log_info(f"  [reCAPTCHA] Gửi yêu cầu giải {solver_type} (Sitekey: {site_key[:12]}...)...")
    
    headers = {"Content-Type": "application/json"}
    if SOLVER_KEY:
        headers["key"] = SOLVER_KEY

    data = {
        "type": solver_type,
        "domain": FAUCET_URL,
        "siteKey": site_key
    }

    try:
        resp = requests.post(f"{SOLVER_URL}/solve", headers=headers, json=data, timeout=30)
        result = resp.json()
        if "taskId" not in result:
            log_error(f"  ❌ Không nhận được Task ID: {result}")
            return None

        task_id = result["taskId"]
        log_info(f"  [reCAPTCHA] Task ID: {task_id} -> Đang giải...")

        for _ in range(45):
            time.sleep(2)
            poll = requests.post(f"{SOLVER_URL}/solve", headers=headers, json={"taskId": task_id}, timeout=30)
            poll_res = poll.json()
            if poll_res.get("status") == "done":
                token = poll_res.get("token") or poll_res.get("solution", {}).get("token")
                if token:
                    log_success(f"  ✓ reCAPTCHA solved thành công!")
                    return token
            elif poll_res.get("status") == "error":
                log_error(f"  ❌ Solver báo lỗi: {poll_res.get('message', 'Unknown')}")
                return None
        log_error("  ❌ Timeout chờ kết quả từ solver (90s)")
        return None
    except Exception as e:
        log_error(f"  ❌ Lỗi gọi solver API: {e}")
        return None

# ============= CLAIM FUNCTION =============
total_claims = load_total_claims()

def claim():
    global total_claims
    log_info("\n" + "="*55)
    log_info("🪙  BẮT ĐẦU QUY TRÌNH CLAIM PEPE")
    log_info("="*55)

    # 1. Đảm bảo đăng nhập
    ensure_login()

    # 2. Tải trang /faucet/PEPE
    log_info(f"  [1/4] Đang nạp trang vòi PEPE: {FAUCET_URL}")
    r = get_page(FAUCET_URL, allow_redirects=True)
    if not r:
        return "error", 30

    # Nếu bị chuyển về trang login
    if 'name="address"' in r.text or "Start Earning" in r.text:
        log_warning("  ⚠️ Phiên hết hạn. Đang đăng nhập lại...")
        if not login():
            return "error", 30
        r = get_page(FAUCET_URL, allow_redirects=True)
        if not r or 'name="address"' in r.text:
            log_error("  ❌ Không thể vào trang vòi sau khi đăng nhập")
            return "error", 30

    # 3. Kiểm tra Cooldown trên trang
    if "Please wait" in r.text or "disabled" in r.text:
        cd_match = re.search(r'Please wait (\d+)s', r.text) or re.search(r'(\d+)\s*(?:seconds|s|giây)', r.text)
        if cd_match:
            cd = int(cd_match.group(1))
            log_warning(f"⏳ Đang trong thời gian Cooldown: còn {cd} giây.")
            return "cooldown", cd

    # 4. Trích xuất CSRF Token & Captcha SiteKey
    csrf_match = re.search(r'name="csrf_token" value="([a-f0-9]{64})"', r.text)
    if not csrf_match:
        log_error("  ❌ Không tìm thấy csrf_token trong trang /faucet/PEPE")
        return "error", 30

    csrf_token = csrf_match.group(1)
    log_info(f"  ✓ CSRF Token: {csrf_token[:16]}...")

    # Sitekey
    sitekey_match = re.search(r'data-sitekey="([^"]+)"', r.text)
    sitekey = sitekey_match.group(1) if sitekey_match else "6LfNt2IsAAAAAPrj5FKMa9Wbn7I8SfkTsLTKLScQ"
    is_v2 = "g-recaptcha" in r.text or "6LfNt2Is" in sitekey

    # 5. Giải Captcha
    log_info("  [2/4] Bắt đầu giải Captcha...")
    captcha_token = solve_recaptcha(sitekey, is_v2=is_v2)
    if not captcha_token:
        return "captcha_failed", 5

    # 6. Gửi Claim POST
    log_info("  [3/4] Đang gửi yêu cầu nhận thưởng...")
    post_data = {
        "currency": "PEPE",
        "csrf_token": csrf_token,
        "g-recaptcha-response": captcha_token,
        "claim": ""
    }

    try:
        resp = session.post(
            FAUCET_URL,
            data=post_data,
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Origin": BASE_URL,
                "Referer": FAUCET_URL
            },
            timeout=30,
            allow_redirects=True
        )

        log_info(f"  Response Status: {resp.status_code}")

        if "Captcha verification failed" in resp.text:
            log_error("  ⚠️ Captcha verification failed – sẽ thử lại lượt mới.")
            return "captcha_failed", 5

        success_keywords = ['successfully', 'claimed', 'reward', 'thank you', 'you received', 'congratulation', 'satoshi', 'pepe']
        if any(kw in resp.text.lower() for kw in success_keywords) and "danger" not in resp.text.lower():
            total_claims += 1
            log_success(f"🎉 CLAIM THÀNH CÔNG! Tổng số claims: {total_claims}")

            reward_match = re.search(r'(\d+\.?\d*)\s*PEPE', resp.text)
            if reward_match:
                log_success(f"  💰 Phần thưởng nhận được: {reward_match.group(1)} PEPE")

            save_cookies()
            save_total_claims(total_claims)

            # Đọc cooldown mới
            cd_match = re.search(r'Please wait (\d+)s', resp.text) or re.search(r'(\d+)\s*(?:seconds|s|giây)', resp.text)
            cooldown = int(cd_match.group(1)) if cd_match else 240
            return "success", cooldown
        else:
            log_warning("  ⚠️ Phản hồi hoàn tất lượt claim.")
            cd_match = re.search(r'Please wait (\d+)s', resp.text)
            cooldown = int(cd_match.group(1)) if cd_match else 60
            return "success", cooldown

    except Exception as e:
        log_error(f"  ❌ Lỗi khi gửi POST Claim: {e}")
        return "error", 30

# ============= MAIN LOOP =============
def main():
    log_info("\n" + "#"*60)
    log_info("🚀 PEPE FAUCET BOT & CAPTCHA SOLVER - CODESANDBOX RUNNER")
    log_info(f"📧 Email cấu hình : {EMAIL}")
    log_info(f"🌐 Solver URL     : {SOLVER_URL}")
    log_info(f"📊 Số claims trước: {total_claims}")
    log_info("#"*60 + "\n")

    test_solver()
    load_cookies()

    while total_claims < MAX_CLAIMS:
        status, value = claim()

        if status == "cooldown":
            log_info(f"😴 Đang trong Cooldown, nghỉ {value} giây...")
            time.sleep(value)

        elif status == "captcha_failed":
            log_info("🔄 Thử lại sau 5 giây với token Captcha mới...")
            time.sleep(5)

        elif status == "success":
            cooldown = value if value else 240
            log_info(f"😴 Nghỉ {cooldown} giây trước lượt claim tiếp theo...")
            time.sleep(cooldown)

        else:
            log_info("⏳ Gặp lỗi tạm thời, thử lại sau 30 giây...")
            time.sleep(30)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log_info("\n👋 Bot đã được dừng bởi người dùng.")
    except Exception:
        log_error("\n💥 NGOẠI LỆ:")
        traceback.print_exc()
        sys.exit(1)
