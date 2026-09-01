#!/bin/bash
# ============================================================
#  CodeSandbox / Linux Self-Healing Runner: Captcha Solver API + Bot
# ============================================================

set -e

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$DIR"

echo "=================================================="
echo "🚀 KHỞI ĐỘNG HỆ THỐNG TRÊN CODESANDBOX / DEVBOX"
echo "=================================================="

# Helper function để chạy lệnh với sudo nếu có
run_root() {
    if command -v sudo >/dev/null 2>&1; then
        sudo "$@"
    else
        "$@"
    fi
}

# 1. Quản lý dọn dẹp tiến trình khi tắt
cleanup() {
    echo ""
    echo "🛑 Đang dừng hệ thống..."
    if [ ! -z "$API_PID" ]; then
        kill "$API_PID" 2>/dev/null || true
    fi
    if [ ! -z "$XVFB_PID" ]; then
        kill "$XVFB_PID" 2>/dev/null || true
    fi
    pkill -f "node Api.js" 2>/dev/null || true
    echo "👋 Đã dừng thành công."
    exit 0
}
trap cleanup SIGINT SIGTERM EXIT

# 2. Tự động kiểm tra và cài đặt Node.js & npm nếu thiếu
if ! command -v node >/dev/null 2>&1 || ! command -v npm >/dev/null 2>&1; then
    echo "📦 0. Phát hiện thiếu Node.js/npm. Đang tự động cài đặt Node.js 20..."
    if command -v apt-get >/dev/null 2>&1; then
        run_root apt-get update -y
        run_root apt-get install -y curl ca-certificates gnupg
        curl -fsSL https://deb.nodesource.com/setup_20.x | run_root bash -
        run_root apt-get install -y nodejs
    elif command -v apk >/dev/null 2>&1; then
        run_root apk add --no-cache nodejs npm
    fi
fi

# 3. Tự động kiểm tra và cài đặt Python3 & pip nếu thiếu
if ! command -v python3 >/dev/null 2>&1; then
    echo "📦 0. Đang cài đặt Python3..."
    if command -v apt-get >/dev/null 2>&1; then
        run_root apt-get install -y python3 python3-pip python3-venv
    fi
fi

# Kiểm tra lệnh pip / python3 -m pip
PIP_CMD=""
if command -v pip3 >/dev/null 2>&1; then
    PIP_CMD="pip3"
elif command -v pip >/dev/null 2>&1; then
    PIP_CMD="pip"
elif python3 -m pip --version >/dev/null 2>&1; then
    PIP_CMD="python3 -m pip"
else
    echo "📦 0. Đang cài đặt pip cho Python3..."
    if command -v apt-get >/dev/null 2>&1; then
        run_root apt-get install -y python3-pip
        PIP_CMD="pip3"
    fi
fi

# 4. Tự động kiểm tra và cài đặt Xvfb + Thư viện Chrome nếu thiếu
if ! command -v Xvfb >/dev/null 2>&1; then
    echo "🖥️  0. Đang cài đặt Xvfb và thư viện đồ họa..."
    if command -v apt-get >/dev/null 2>&1; then
        run_root apt-get install -y --no-install-recommends \
            xvfb \
            ca-certificates \
            fonts-liberation \
            libasound2 \
            libatk-bridge2.0-0 \
            libatk1.0-0 \
            libcups2 \
            libdrm2 \
            libgbm1 \
            libglib2.0-0 \
            libgtk-3-0 \
            libnspr4 \
            libnss3 \
            libx11-6 \
            libx11-xcb1 \
            libxcb1 \
            libxcomposite1 \
            libxdamage1 \
            libxext6 \
            libxfixes3 \
            libxrandr2 \
            libxrender1 \
            libxshmfence1 || true
    fi
fi

# 5. Cài đặt dependencies dự án
echo "📦 1. Kiểm tra Dependencies của dự án..."
if [ ! -d "Api/node_modules" ]; then
    echo "   -> Cài đặt Node modules cho Solver API..."
    cd Api && npm install && cd ..
fi

if ! python3 -c "import requests, dotenv, colorama" 2>/dev/null; then
    echo "   -> Cài đặt Python requirements..."
    if [ -n "$PIP_CMD" ]; then
        $PIP_CMD install -r requirements.txt --break-system-packages 2>/dev/null || $PIP_CMD install -r requirements.txt
    fi
fi

# 6. Khởi động màn hình ảo Xvfb
export DISPLAY="${DISPLAY:-:99}"
if ! pgrep -f "Xvfb ${DISPLAY}" >/dev/null 2>&1; then
    echo "🖥️  2. Khởi động Xvfb (${DISPLAY})..."
    rm -f /tmp/.X99-lock 2>/dev/null || true
    if command -v Xvfb >/dev/null 2>&1; then
        Xvfb "${DISPLAY}" -screen 0 1366x768x24 -ac +extension RANDR >/tmp/xvfb.log 2>&1 &
        XVFB_PID=$!
        sleep 1
    else
        echo "   ⚠️  Xvfb chưa sẵn sàng (tiếp tục chạy chế độ fallback)"
    fi
fi

# 7. Khởi động Captcha Solver API
echo "🤖 3. Khởi động Captcha Solver API (Port 8080)..."
cd Api
node Api.js > ../solver.log 2>&1 &
API_PID=$!
cd ..

# 8. Chờ Solver API sẵn sàng
echo "⏳ 4. Chờ Solver API sẵn sàng..."
MAX_RETRY=30
RETRY=0
while [ $RETRY -lt $MAX_RETRY ]; do
    if curl -s http://127.0.0.1:8080/ >/dev/null 2>&1; then
        echo "   ✅ Solver API đã sẵn sàng!"
        break
    fi
    sleep 1
    RETRY=$((RETRY+1))
done

if [ $RETRY -eq $MAX_RETRY ]; then
    echo "   ⚠️  Không thể kết nối Solver API sau 30s. Xem log tại solver.log:"
    tail -n 20 solver.log 2>/dev/null || true
fi

# 9. Khởi động Python Bot
echo "🪙 5. Bắt đầu chạy Python Bot..."
echo "--------------------------------------------------"
python3 app.py
