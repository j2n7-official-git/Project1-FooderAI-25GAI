"""
fooder_logger.py — Module ghi log dùng chung toàn app FooderAI
==============================================================
Nhiệm vụ:
  - In log ra black console (stdout)
  - Ghi đồng thời ra file .txt trong thư mục logs/
  - Tự tạo thư mục nếu chưa có
  - Tự sinh file mới nếu file cũ bị xóa (không crash)

Format log:
  [HH:MM:SS - YYYY/MM/DD]: [TAG] nội dung
  Ví dụ:
  [14:32:05 - 2026/06/02]: [RESET] ✅ Xóa lịch sử session 1 thành công
  [14:32:06 - 2026/06/02]: [DB] ❌ Lỗi kết nối: timeout

Cách dùng:
  from fooder_logger import flog

  flog("RESET", "Bắt đầu reset chat")
  flog("DB",    "Kết nối thành công")
  flog("ERROR", f"Lỗi: {e}", level="ERROR")

[UPDATE v1.0] — 02/06/2026 — Tài · Tuấn · Vanh
  + Tạo module từ đầu
  + Hỗ trợ console + file đồng thời
  + Cơ chế tự sinh file mới nếu bị dọn
"""

import os
import sys
from datetime import datetime

# ── CẤU HÌNH ────────────────────────────────────────────────────────────────
# Thư mục logs/ nằm cạnh file này (root dự án)
# os.path.dirname(__file__) = thư mục chứa fooder_logger.py
_LOG_DIR  = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
_LOG_FILE = os.path.join(_LOG_DIR, "fooderai_app.log")

# ── NỘI BỘ ──────────────────────────────────────────────────────────────────
def _ensure_log_file() -> str:
    """
    Đảm bảo thư mục logs/ và file .log luôn tồn tại.
    Nếu bị xóa thì tạo lại — không crash.
    Trả về đường dẫn file log hiện tại.
    """
    # Tạo thư mục nếu chưa có (exist_ok=True: không lỗi nếu đã có)
    os.makedirs(_LOG_DIR, exist_ok=True)

    # Nếu file bị xóa → tạo lại với header
    if not os.path.exists(_LOG_FILE):
        with open(_LOG_FILE, "w", encoding="utf-8") as f:
            f.write("=" * 60 + "\n")
            f.write(f"FooderAI — App Log\n")
            f.write(f"Tạo lúc: {datetime.now().strftime('%H:%M:%S - %Y/%m/%d')}\n")
            f.write("=" * 60 + "\n\n")

    return _LOG_FILE


def flog(tag: str, message: str, level: str = "INFO"):
    """
    Ghi 1 dòng log ra cả console lẫn file .txt.

    Tham số:
        tag     : nhãn phân loại, ví dụ "RESET", "DB", "AUTH", "SCAN"
        message : nội dung cần log
        level   : "INFO" (mặc định) | "WARN" | "ERROR"
                  Chỉ ảnh hưởng prefix màu trên console, không đổi format file

    Ví dụ:
        flog("RESET", "Bắt đầu reset chat")
        flog("DB",    "Kết nối SQL Server thành công")
        flog("AUTH",  f"Đăng nhập thất bại: {e}", level="ERROR")
    """
    now       = datetime.now()
    timestamp = now.strftime("%H:%M:%S - %Y/%m/%d")   # HH:MM:SS - YYYY/MM/DD
    line      = f"[{timestamp}]: [{tag}] {message}"   # format chuẩn

    # ── In ra console ────────────────────────────────────────────────────────
    # Thêm màu ANSI nếu terminal hỗ trợ (Windows Terminal, PyCharm, VS Code)
    # Fallback bình thường nếu không hỗ trợ (IDLE, cmd cũ)
    _COLOR = {
        "INFO":  "\033[0m",    # trắng bình thường
        "WARN":  "\033[33m",   # vàng
        "ERROR": "\033[31m",   # đỏ
    }
    _RESET_COLOR = "\033[0m"
    color = _COLOR.get(level, _COLOR["INFO"])

    try:
        print(f"{color}{line}{_RESET_COLOR}", flush=True)
    except Exception:
        print(line, flush=True)   # fallback nếu terminal không hỗ trợ ANSI

    # ── Ghi ra file ──────────────────────────────────────────────────────────
    # _ensure_log_file() tự tạo lại file nếu bị xóa → không bao giờ crash
    try:
        log_path = _ensure_log_file()
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception as write_err:
        # Không để lỗi ghi file crash app — chỉ báo lên console
        print(f"[fooder_logger] ⚠️ Không ghi được log: {write_err}", file=sys.stderr)


def flog_separator(label: str = ""):
    """
    Ghi 1 dòng phân cách vào log — dùng để đánh dấu sự kiện lớn.
    Ví dụ: flog_separator("APP KHỞI ĐỘNG")
    Output:
    ══════════════ APP KHỞI ĐỘNG ══════════════
    """
    now       = datetime.now()
    timestamp = now.strftime("%H:%M:%S - %Y/%m/%d")
    sep       = "═" * 20
    line      = f"\n[{timestamp}]: {sep} {label} {sep}\n" if label else f"\n{sep * 2}\n"

    try:
        print(f"\033[36m{line.strip()}\033[0m", flush=True)   # cyan trên console
    except Exception:
        print(line.strip(), flush=True)

    try:
        log_path = _ensure_log_file()
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(line)
    except Exception:
        pass


# ── Tự chạy khi import lần đầu: đảm bảo thư mục logs/ luôn sẵn sàng ────────
_ensure_log_file()