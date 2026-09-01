#!/bin/bash
# ============================================================
#  CodeSandbox / Linux Runner: Captcha Solver API + Python Bot
# ============================================================

set -e

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$DIR"

echo "=================================================="
echo "🚀 KHỞI ĐỘNG HỆ THỐNG TRÊN CODESANDBOX / DEVBOX"
echo "=================================================="

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

# 2. Cài đặt dependencies nếu chưa có
echo "📦 1. Kiểm tra Dependencies..."
if [ ! -d "Api/node_modules" ]; then
    echo "   -> Cài đặt Node modules cho Solver API..."
    cd Api && npm install && cd ..
fi

if ! python3 -c "import requests, dotenv, colorama" 2>/dev/null; then
    echo "   -> Cài đặt Python requirements..."
    pip install -r requirements.txt
fi

# 3. Khởi động màn hình ảo Xvfb (nếu cần cho real browser)
export DISPLAY="${DISPLAY:-:99}"
if ! pgrep -f "Xvfb ${DISPLAY}" >/dev/null 2>&1; then
    echo "🖥️  2. Khởi động Xvfb (${DISPLAY})..."
    rm -f /tmp/.X99-lock 2>/dev/null || true
    if command -v Xvfb >/dev/null 2>&1; then
        Xvfb "${DISPLAY}" -screen 0 1366x768x24 -ac +extension RANDR >/tmp/xvfb.log 2>&1 &
        XVFB_PID=$!
        sleep 1
    else
        echo "   ⚠️  Xvfb chưa cài đặt trên hệ thống (bỏ qua nếu dùng headless mode)"
    fi
fi

# 4. Khởi động Captcha Solver API
echo "🤖 3. Khởi động Captcha Solver API (Port 8080)..."
cd Api
node Api.js > ../solver.log 2>&1 &
API_PID=$!
cd ..

# 5. Chờ Solver API sẵn sàng
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
    tail -n 20 solver.log
fi

# 6. Khởi động Python Bot
echo "🪙 5. Bắt đầu chạy Python Bot..."
echo "--------------------------------------------------"
python3 app.py
