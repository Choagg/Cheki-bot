# Cheki Zaiko Bot — Check tồn kho phim Fujifilm instax

Bot theo dõi tồn kho phim instax (チェキ) trên nhiều trang bán hàng
(Amazon.co.jp, Rakuten, Yodobashi, Yahoo!ショッピング, Fujifilm Mall,
ビックカメラ.com, ソフマップ, ジョーシン) và gửi thông báo qua **Telegram**
(hoặc Discord/Slack webhook) khi hàng về.

⚠️ Bot chỉ theo dõi & báo tin — **không tự động mua/checkout**.

## 1. Cài đặt (nếu chạy local để test)

```bash
pip install requests beautifulsoup4 --break-system-packages
```

## 2. Tạo Telegram bot & lấy chat_id

1. Trên Telegram, chat với **@BotFather** → gõ `/newbot` → đặt tên →
   BotFather trả về **token** dạng `123456789:AAExxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx`.
2. Nhắn một tin bất kỳ (vd "hi") cho bot bạn vừa tạo (tìm theo username, ví dụ `@your_bot`).
3. Lấy `chat_id` của bạn bằng cách mở trong trình duyệt:
   `https://api.telegram.org/bot<TOKEN>/getUpdates`
   → tìm trường `"chat":{"id": ...}` trong kết quả JSON, đó là `chat_id`.
   (Nếu muốn gửi vào group, thêm bot vào group rồi lấy `chat_id` âm của group tương tự.)

## 3. Cấu hình `config.json`

- `notify_type`: `"telegram"` (mặc định), hoặc `"discord"` / `"slack"` nếu muốn dùng webhook thay thế
- `products`: danh sách sản phẩm cần theo dõi, mỗi mục gồm:
  - `name`: tên hiển thị
  - `site`: một trong `amazon`, `rakuten`, `yodobashi`, `yahoo`, `fujifilm_mall`,
    `bigcamera`, `sofmap`, `joshin`
  - `url`: link trực tiếp tới trang sản phẩm (thay các `XXXX` mẫu bằng link thật)

Token Telegram/webhook **không đặt trong file này** — xem mục 5, sẽ đặt làm
GitHub Secrets để không bị lộ khi repo public.

Ví dụ tìm link sản phẩm: vào trang chủ mỗi site, tìm "instax mini フィルム"
hoặc "チェキフィルム", copy URL trang chi tiết sản phẩm.

## 4. Chạy thử ở local (tùy chọn, để test trước khi deploy)

```bash
# chạy kiểm tra 1 lần (đọc token/chat_id từ biến môi trường)
export TELEGRAM_BOT_TOKEN="123456789:AAE..."
export TELEGRAM_CHAT_ID="123456789"
python3 checker.py

# chạy lặp lại liên tục theo interval trong config.json
python3 checker.py --loop
```

## 5. Chạy 24/7 MIỄN PHÍ bằng GitHub Actions (khuyên dùng)

Không cần thuê server, không cần thẻ tín dụng. GitHub Actions sẽ tự chạy
`checker.py` theo lịch (mặc định mỗi 5 phút) kể cả khi máy bạn tắt.

### Bước 1: Tạo repo GitHub
1. Tạo tài khoản GitHub (nếu chưa có) → tạo repo mới, đặt **Public**
   (repo public thì GitHub Actions chạy **không giới hạn số phút/tháng, miễn phí**;
   repo private chỉ có 2000 phút/tháng free).
2. Upload toàn bộ nội dung thư mục này (`checker.py`, `config.json`,
   `.github/workflows/check-zaiko.yml`, `state.json`) lên repo — kéo thả qua
   giao diện web GitHub cũng được, không cần biết dùng `git`.
   ⚠️ Nhớ điền URL sản phẩm thật vào `config.json` trước khi upload.

### Bước 2: Khai báo bí mật (Secrets)
Vào repo → **Settings → Secrets and variables → Actions → New repository secret**,
tạo các secret sau (chỉ điền cái bạn dùng):

| Tên secret | Giá trị |
|---|---|
| `TELEGRAM_BOT_TOKEN` | token bot Telegram (xem mục 2) |
| `TELEGRAM_CHAT_ID` | chat_id của bạn |
| `WEBHOOK_URL` | (nếu dùng Discord/Slack thay Telegram) |

### Bước 3: Kiểm tra hoạt động
- Vào tab **Actions** trên repo → chọn workflow "Check Cheki Zaiko" →
  bấm **Run workflow** để chạy thử ngay (không cần đợi lịch).
- Xem log để chắc chắn không có lỗi.
- Sau đó nó sẽ tự chạy mỗi 5 phút vĩnh viễn, kể cả khi bạn tắt máy tính.

### Lưu ý về GitHub Actions cron
- Lịch chạy có thể trễ vài phút vào giờ cao điểm (GitHub không đảm bảo đúng giây/phút),
  nhưng vẫn đủ tốt cho việc theo dõi tồn kho.
- Muốn chạy dày hơn (vd mỗi 2 phút) thì sửa `cron: "*/5 * * * *"` thành `"*/2 * * * *"`
  trong file `.github/workflows/check-zaiko.yml` — nhưng đừng quá dày kẻo bị site chặn IP.
- File `state.json` sẽ tự động được commit lại vào repo sau mỗi lần chạy để nhớ
  trạng thái tồn kho giữa các lần check.

### Phương án khác: Oracle Cloud Always Free VM
Nếu muốn 1 server Linux thật chạy `python3 checker.py --loop` liên tục 24/7
(không phải theo lịch rời rạc), Oracle Cloud có gói **Always Free** (VM ARM
4 core/24GB RAM miễn phí vĩnh viễn, cần xác minh thẻ nhưng không bị trừ tiền).
Nếu bạn muốn, mình có thể hướng dẫn setup chi tiết theo hướng này.

## 6. Cách hoạt động

- Bot tải HTML trang sản phẩm, tìm các từ khóa tiếng Nhật báo còn/hết hàng
  (在庫あり, カートに入れる, 売り切れ, SOLD OUT, v.v.), có parser riêng
  cho từng site để chính xác hơn.
- Trạng thái được lưu vào `state.json`; chỉ gửi thông báo khi sản phẩm
  **chuyển từ hết hàng/không rõ → còn hàng**, tránh spam thông báo lặp lại.
- Có delay 3 giây giữa các request để tránh gây tải nặng lên server / bị chặn IP.

## 7. Giới hạn cần biết

- Cấu trúc HTML các trang có thể thay đổi theo thời gian → có thể cần
  cập nhật lại `detect_stock_status()` trong `checker.py` nếu bot báo sai.
- Amazon/Yahoo có thể chặn request tự động (captcha, chặn IP) nếu check quá thường xuyên
  — không nên đặt `check_interval_seconds`/cron quá dày (khuyên ≥ 180–300 giây).
- Một số shop cấm rõ việc dùng công cụ tự động cho mục đích mua đi bán lại (転売);
  hãy chỉ dùng bot này để theo dõi cho nhu cầu mua cá nhân.
