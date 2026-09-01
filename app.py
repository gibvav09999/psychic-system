#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PEPE FAUCET BOT + CAPTCHA SOLVER INTEGRATION (CodeSandbox / Devbox Ready)
- Hỗ trợ giải Cloudflare Interstitial (cf_clearance) tự động
- Hỗ trợ giải reCAPTCHA v3 / Turnstile qua local Solver API
- Tự động kiểm tra Cooldown trước khi gửi claim
- Lưu trữ session cookies & thống kê claims
- Tự động load cấu hình từ .env
"""

import sys
import os
import json
import time
import re
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

# Hỗ trợ màu terminal với colorama nếu có
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
EMAIL = os.environ.get("EMAIL", "Casminivana@gmail.com")
SOLVER_URL = os.environ.get("SOLVER_URL", "http://127.0.0.1:8080").rstrip("/")
SOLVER_KEY = os.environ.get("SOLVER_KEY", "")
COOKIES_FILE = os.path.join(os.path.dirname(__file__), "cookies_pepe.json")
STATS_FILE   = os.path.join(os.path.dirname(__file__), "stats_pepe.json")
LOG_FILE     = os.path.join(os.path.dirname(__file__), "bot.log")
MAX_CLAIMS   = int(os.environ.get("MAX_CLAIMS", "100000"))
HEALTH_PORT  = int(os.environ.get("HEALTH_PORT", "7860"))
ENABLE_HEALTH_SERVER = os.environ.get("ENABLE_HEALTH_SERVER", "false").lower() == "true"

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
session.headers.update({
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.9',
    'Sec-Ch-Ua': '"Chromium";v="128", "Not;A=Brand";v="24", "Google Chrome";v="128"',
    'Sec-Ch-Ua-Mobile': '?0',
    'Sec-Ch-Ua-Platform': '"Windows"',
    'Sec-Fetch-Dest': 'document',
    'Sec-Fetch-Mode': 'navigate',
    'Sec-Fetch-Site': 'same-origin',
    'Sec-Fetch-User': '?1',
    'Upgrade-Insecure-Requests': '1',
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
        log_warning(f"⚠️ Không thể kết nối tới Solver API ({e}). Đảm bảo Solver API đã được khởi động.")
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
                cookies_dict = data.get('cookies', {})
                session.cookies = requests.utils.cookiejar_from_dict(cookies_dict)
                if data.get('user_agent'):
                    session.headers['User-Agent'] = data['user_agent']
                log_info(f"✓ Đã nạp cookies và User-Agent đã lưu")
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

# ============= CLOUDFLARE BYPASS =============
def bypass_cloudflare():
    log_info("  [Cloudflare] Phát hiện thử thách bảo vệ. Đang yêu cầu Solver giải quyết...")
    headers = {"Content-Type": "application/json"}
    if SOLVER_KEY:
        headers["key"] = SOLVER_KEY

    data = {
        "type": "interstitial",
        "domain": "https://freepepecoin.com"
    }

    try:
        resp = requests.post(f"{SOLVER_URL}/solve", headers=headers, json=data, timeout=35)
        result = resp.json()
        if "taskId" not in result:
            log_error(f"  ❌ Không nhận được Task ID giải Cloudflare: {result}")
            return False

        task_id = result["taskId"]
        log_info(f"  [Cloudflare] Task ID: {task_id} -> Đang chờ Solver vượt qua...")

        for attempt in range(40):
            time.sleep(2)
            poll = requests.post(f"{SOLVER_URL}/solve", headers=headers, json={"taskId": task_id}, timeout=30)
            poll_res = poll.json()
            if poll_res.get("status") == "done":
                cf_clearance = poll_res.get("cf_clearance")
                ua = poll_res.get("user_agent")
                cookies_str = poll_res.get("cookies")
                
                if cf_clearance:
                    session.cookies.set("cf_clearance", cf_clearance, domain="freepepecoin.com")
                    log_success(f"  ✓ Đã nhận cf_clearance: {cf_clearance[:20]}...")
                
                if ua:
                    session.headers["User-Agent"] = ua
                    log_info(f"  ✓ Đã đồng bộ User-Agent từ Solver")
                    
                if cookies_str and isinstance(cookies_str, str):
                    for c in cookies_str.split(";"):
                        if "=" in c:
                            k, v = c.strip().split("=", 1)
                            session.cookies.set(k, v, domain="freepepecoin.com")
                            
                save_cookies()
                log_success("  ✅ Đã vượt qua Cloudflare thành công!")
                return True
            elif poll_res.get("status") == "error":
                log_error(f"  ❌ Solver báo lỗi Cloudflare: {poll_res.get('message')}")
                return False
                
        log_error("  ❌ Timeout khi giải Cloudflare (80s)")
        return False
    except Exception as e:
        log_error(f"  ❌ Lỗi khi gửi yêu cầu giải Cloudflare: {e}")
        return False

# ============= KIỂM TRA COOLDOWN =============
def check_cooldown():
    try:
        resp = session.get("https://freepepecoin.com/", timeout=15)
        if resp.status_code in (403, 454, 503) or "Checking your browser" in resp.text or "Just a moment" in resp.text:
            return 0, "Cloudflare Challenge"
        if resp.status_code != 200:
            return 0, f"HTTP {resp.status_code}"
        match = re.search(r'Please wait (\d+)s', resp.text)
        if match:
            cd = int(match.group(1))
            return cd, f"Cooldown còn {cd} giây"
        if 'Claim Pepe' in resp.text and 'Please wait' not in resp.text:
            return 0, "Sẵn sàng Claim"
        return 0, "Sẵn sàng Claim"
    except Exception as e:
        return 0, f"Lỗi kết nối: {e}"

# ============= SOLVE RECAPTCHA =============
def solve_recaptcha():
    log_info("  [reCAPTCHA] Đang gửi yêu cầu giải captcha tới Solver API...")
    headers = {"Content-Type": "application/json"}
    if SOLVER_KEY:
        headers["key"] = SOLVER_KEY

    data = {
        "type": "recaptcha3",
        "domain": "https://freepepecoin.com",
        "siteKey": "6LcbMB0sAAAAAAxsy76NqLNBhHfzZO8E4jLJ8XNl"
    }

    try:
        resp = requests.post(f"{SOLVER_URL}/solve", headers=headers, json=data, timeout=30)
        result = resp.json()
        if "taskId" not in result:
            log_error(f"  ❌ Không lấy được Task ID: {result}")
            return None
        task_id = result["taskId"]
        log_info(f"  [reCAPTCHA] Task ID: {task_id} -> Đang chờ giải...")

        for attempt in range(45):
            time.sleep(2)
            poll = requests.post(f"{SOLVER_URL}/solve", headers=headers, json={"taskId": task_id}, timeout=30)
            poll_res = poll.json()
            if poll_res.get("status") == "done":
                token = poll_res.get("token") or poll_res.get("solution", {}).get("token")
                if token:
                    log_success("  ✓ reCAPTCHA solved thành công!")
                    return token
            elif poll_res.get("status") == "error":
                log_error(f"  ❌ Solver trả về lỗi: {poll_res.get('message', 'Unknown error')}")
                return None
        log_error("  ❌ Timeout khi chờ kết quả từ solver (90s)")
        return None
    except Exception as e:
        log_error(f"  ❌ Lỗi khi gọi solver: {e}")
        return None

# ============= LẤY CSRF TOKEN =============
def get_csrf_token(retry_bypass=True):
    log_info("  [CSRF] Đang lấy CSRF Token từ trang chủ...")
    try:
        resp = session.get("https://freepepecoin.com/", timeout=30)
        
        # Kiểm tra xem có bị Cloudflare chặn không
        if resp.status_code in (403, 454, 503) or "Checking your browser" in resp.text or "Just a moment" in resp.text:
            log_warning(f"  ⚠️ Trang web yêu cầu xác minh Cloudflare (HTTP {resp.status_code})")
            if retry_bypass:
                if bypass_cloudflare():
                    time.sleep(2)
                    return get_csrf_token(retry_bypass=False)
            log_error("  ❌ Không vượt được Cloudflare để lấy CSRF token")
            return None

        if resp.status_code != 200:
            log_error(f"  ❌ Truy cập trang chủ thất bại: HTTP {resp.status_code}")
            return None

        match = re.search(r'name="csrf_token" value="([a-f0-9]{64})"', resp.text)
        if match:
            token = match.group(1)
            log_info(f"  ✓ CSRF token: {token[:16]}...")
            return token
        else:
            if "cf-" in resp.text or "cloudflare" in resp.text.lower():
                log_warning("  ⚠️ Bị Cloudflare chặn nội dung, đang kích hoạt giải Cloudflare...")
                if retry_bypass and bypass_cloudflare():
                    time.sleep(2)
                    return get_csrf_token(retry_bypass=False)
            log_error("  ❌ Không tìm thấy csrf_token trong HTML")
            return None
    except Exception as e:
        log_error(f"  ❌ Lỗi khi lấy CSRF: {e}")
        return None

# ============= CLAIM FUNCTION =============
total_claims = load_total_claims()

def claim():
    global total_claims
    log_info("\n" + "="*50)
    log_info("🪙  BẮT ĐẦU QUY TRÌNH CLAIM PEPE")
    log_info("="*50)

    # 1. Kiểm tra Cooldown
    cd, msg = check_cooldown()
    if cd > 0:
        log_warning(f"⏳ {msg} – Chờ hết cooldown...")
        return "cooldown", cd

    log_success(f"✅ {msg} – Tiến hành gửi claim ngay.")

    # 2. Lấy CSRF token (tự động bypass Cloudflare nếu cần)
    csrf = get_csrf_token()
    if not csrf:
        return "error", None

    # 3. Giải reCAPTCHA
    captcha = solve_recaptcha()
    if not captcha:
        return "error", None

    # 4. Gửi request Claim
    log_info("  [POST] Đang gửi yêu cầu claim...")
    headers = {
        'Content-Type': 'application/x-www-form-urlencoded',
        'Origin': 'https://freepepecoin.com',
        'Referer': 'https://freepepecoin.com/',
    }
    data = {
        'csrf_token': csrf,
        'g-recaptcha-response': captcha,
        'email': EMAIL,
        'claim': ''
    }
    try:
        resp = session.post("https://freepepecoin.com/", headers=headers, data=data, timeout=30, allow_redirects=True)
        log_info(f"  Response Status: {resp.status_code}")

        if 'Captcha verification failed.' in resp.text:
            log_error("  ⚠️  Captcha verification failed – sẽ thử lại với token mới.")
            return "captcha_failed", None

        success_keywords = ['successfully', 'claimed', 'reward', 'thank you', 'you received', 'congratulation']
        if any(kw in resp.text.lower() for kw in success_keywords):
            total_claims += 1
            success_msg = f"🎉 CLAIM THÀNH CÔNG! Tổng số claims: {total_claims}"
            log_success(success_msg)

            reward_match = re.search(r'(\d+\.?\d*)\s*PEPE', resp.text)
            if reward_match:
                reward = float(reward_match.group(1))
                log_success(f"  💰 Nhận thưởng: {reward} PEPE")

            save_cookies()
            save_total_claims(total_claims)

            cd_new, _ = check_cooldown()
            if cd_new > 0:
                return "success", cd_new
            else:
                return "success", 240
        else:
            log_error("  ❌ Claim không thành công (không phát hiện dấu hiệu thành công)")
            return "error", None

    except Exception as e:
        log_error(f"  ❌ Lỗi khi gửi claim: {e}")
        return "error", None

# ============= MAIN LOOP =============
def main():
    log_info("\n" + "#"*60)
    log_info("🚀 PEPE BOT & CAPTCHA SOLVER - CODESANDBOX RUNNER")
    log_info(f"📧 Email cấu hình : {EMAIL}")
    log_info(f"🌐 Solver URL     : {SOLVER_URL}")
    log_info(f"📊 Số claims trước: {total_claims}")
    log_info("#"*60 + "\n")

    test_solver()
    load_cookies()

    while total_claims < MAX_CLAIMS:
        status, value = claim()

        if status == "cooldown":
            log_info(f"😴 Tạm dừng {value} giây (đang trong thời gian cooldown)...")
            time.sleep(value)

        elif status == "captcha_failed":
            log_info("🔄 Thử lại sau 5 giây với captcha mới...")
            time.sleep(5)

        elif status == "success":
            cooldown = value if value else 240
            log_info(f"😴 Nghỉ {cooldown} giây trước lượt claim tiếp theo...")
            time.sleep(cooldown)

        else:
            log_info("⏳ Gặp lỗi, thử lại sau 30 giây...")
            time.sleep(30)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log_info("\n👋 Bot đã được dừng bởi người dùng.")
    except Exception:
        log_error("\n💥 NGOẠI LỆ KHÔNG XỬ LÝ ĐƯỢC:")
        traceback.print_exc()
        sys.exit(1)
