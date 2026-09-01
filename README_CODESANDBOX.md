# 🚀 Hướng Dẫn Thiết Lập & Chạy Trên CodeSandbox (Devbox)

Tài liệu này hướng dẫn chi tiết cách đưa dự án **Captcha Solver API + Python Bot** lên **CodeSandbox** và thiết lập chạy tự động 24/7.

---

## 📂 1. Cấu Trúc Dự Án

```text
codesandbox/
├── .codesandbox/
│   └── tasks.json            # Cấu hình Tasks tự động cho CodeSandbox Devbox
├── python-scripts/
│   ├── Api/                  # Dịch vụ giải Captcha (Node.js + Puppeteer Real Browser)
│   │   ├── Api.js            # Express API server (Port 8080)
│   │   ├── Api/              # Module giải Turnstile, reCAPTCHA v2/v3, Interstitial
│   │   └── package.json
│   ├── app.py                # Python Bot (Kết nối Solver API, auto claim)
│   ├── start.sh              # Bash script tự động bật Xvfb + Solver API + Bot
│   ├── .env                  # Tệp cấu hình biến môi trường
│   ├── requirements.txt      # Thư viện Python cần thiết
│   └── README_CODESANDBOX.md # Tài liệu này
├── keep-alive.js             # Script giữ Devbox CodeSandbox online 24/7
├── cookies.txt               # Cookie phiên đăng nhập CodeSandbox
└── package.json              # Quản lý scripts tổng thể
```

---

## ⚙️ 2. Các Bước Triển Khai Lên CodeSandbox

### Bước 1: Tạo Devbox trên CodeSandbox
1. Truy cập [CodeSandbox Dashboard](https://codesandbox.io/dashboard).
2. Tạo mới một **Devbox** (chọn template **Node.js** hoặc **Python**).
3. Tải toàn bộ mã nguồn lên Devbox (thông qua **Import GitHub Repository** hoặc kéo thả thư mục vào trình duyệt).

### Bước 2: Cài Đặt Thư Viện (Dependencies)
Trên Terminal của CodeSandbox, chỉ cần chạy một lệnh:
```bash
npm run setup
```
Lệnh này sẽ tự động:
- Cài đặt các gói Node.js trong `python-scripts/Api` (`express`, `puppeteer-real-browser`...).
- Cài đặt các gói Python trong `python-scripts/` (`requests`, `python-dotenv`, `colorama`...).

### Bước 3: Cấu Hình Biến Môi Trường (`.env`)
Mở file `python-scripts/.env` và chỉnh sửa các thông số cần thiết:
```env
# Email ví nhận thưởng FaucetPay
EMAIL=Casminivana@gmail.com

# URL Solver (Mặc định local API là http://127.0.0.1:8080)
SOLVER_URL=http://127.0.0.1:8080
SOLVER_KEY=

# Giới hạn số lần claim
MAX_CLAIMS=100000

# Proxy (nếu cần đổi IP, bỏ trống nếu dùng IP mặc định của Devbox)
HTTP_PROXY=
HTTPS_PROXY=
```

---

## 🏃 3. Khởi Chạy Hệ Thống

### Cách 1: Sử dụng CodeSandbox Tasks UI (Khuyên Dùng)
Giao diện CodeSandbox Devbox sẽ tự động hiển thị các task trong tab **Tasks**:
- Click **`Run Full System (Solver API + Bot)`** để khởi chạy toàn bộ.

### Cách 2: Sử dụng Dòng Lệnh Terminal

**Chạy toàn bộ hệ thống (Xvfb + Solver API + Python Bot):**
```bash
npm run start:all
```
*Script `start.sh` sẽ tự động khởi động màn hình ảo Xvfb, bật Solver API trên cổng 8080, đợi API sẵn sàng và sau đó kích hoạt Python Bot.*

**Hoặc chạy từng thành phần riêng lẻ:**
- Chỉ chạy Solver API:
  ```bash
  npm run start:solver
  ```
- Chỉ chạy Python Bot:
  ```bash
  npm run start:bot
  ```

---

## 🔄 4. Giữ Devbox Hoạt Động 24/7 (Keep-Alive)

Mặc định, CodeSandbox Devbox sẽ tự động **Sleep (ngủ đông)** sau vài phút nếu không có người dùng tương tác trong trình duyệt.

Để giữ Devbox hoạt động liên tục:

1. **Lấy Devbox ID:**
   - Mở Devbox của bạn, nhìn lên thanh địa chỉ URL: `https://codesandbox.io/p/devbox/<DEVBOX_ID>` (ví dụ: `xtl54y`).
2. **Cập nhật `keep-alive.js`:**
   - Mở `keep-alive.js` ở thư mục gốc, cập nhật dòng:
     ```javascript
     DEVBOX_ID: "mã_devbox_của_bạn",
     ```
3. **Cập nhật `cookies.txt`:**
   - Đảm bảo file `cookies.txt` chứa cookie đăng nhập tài khoản CodeSandbox của bạn (được xuất từ extension như *Get cookies.txt LOCALLY* hoặc *Cookie-Editor*).
4. **Khởi chạy Keep-Alive trên máy tính cá nhân hoặc VPS:**
   ```bash
   npm run keep-alive
   ```
   Hoặc chạy ngầm bằng PM2:
   ```bash
   npm install -g pm2
   pm2 start keep-alive.js --name "csb-keepalive"
   pm2 save
   ```

---

## 🛠️ 5. Xử Lý Lỗi Thường Gặp (Troubleshooting)

| Vấn đề | Nguyên nhân | Cách khắc phục |
| :--- | :--- | :--- |
| `Không kết nối được Solver API` | Solver API chưa khởi động xong | Kiểm tra file `python-scripts/solver.log` hoặc chạy `npm run start:solver` trước |
| `Puppeteer / Chromium crash` | Thiếu Xvfb hoặc thư viện đồ họa | Script `start.sh` đã tích hợp sẵn Xvfb. Nếu cần, chạy `sudo apt-get install -y xvfb` trong Devbox terminal |
| `Captcha verification failed` | Proxy chậm hoặc Cloudflare bắt đổi IP | Thêm Proxy vào `.env` hoặc thử lại vài lượt để solver lấy token mới |
| `Devbox bị dừng đột ngột` | Hết session do Devbox sleep | Bật script `keep-alive.js` từ máy cá nhân hoặc VPS |
