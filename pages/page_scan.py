"""
page_scan.py — Trang Quét Món Ăn
==================================
[UPDATE v2.0] — 31/05/2026 — Tài · Tuấn · Vanh
  + Tích hợp Gemini Vision (scan_food_image từ gemini_service.py)
  + UI theo mock-up: Tên món (36px Black) | Mô tả | Lợi điểm 👍 | Lưu ý ⚠️
  + ScanWorker chạy trên QThread riêng — UI không bị đơ khi gọi API
  + Icons: foodscan-good-point.png + foodscan-warning-point.png
  + Cấu trúc content_stack giữ nguyên (index 0 = upload, index 1 = kết quả)

[UPDATE v2.1] — 31/05/2026 — Tài · Tuấn · Vanh
  + Nối log_scan() vào _update_result_ui() — tự động lưu kết quả xuống DB
  + _current_image_path lưu path ảnh để truyền vào log_scan
  + _DB_AVAILABLE fallback: lỗi DB không crash app, chỉ bỏ qua log
"""

import os
import sys

# ── SYS.PATH FIX: tìm fooder_database.py ở thư mục cha (root FooderAI/) ──
# page_scan.py nằm trong pages/ → phải thêm root vào sys.path
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

# ── Import DB — fallback an toàn nếu DB chưa kết nối ─────────────────────
# Lý do dùng try/except: DB lỗi không nên làm hỏng tính năng scan chính
# App vẫn quét bình thường, chỉ không lưu log xuống DB
try:
    from fooder_database import log_scan as _db_log_scan
    _DB_AVAILABLE = True
    print("[SCAN DB] fooder_database nạp thành công")
except Exception as _db_err:
    _DB_AVAILABLE = False
    print(f"[SCAN DB] Không nạp được fooder_database: {_db_err}")

from PySide6.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QLabel, QWidget,
    QGraphicsDropShadowEffect, QStackedWidget, QScrollArea, QPushButton
)
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QFont, QColor, QPixmap


# ══════════════════════════════════════════════════════════════════════
# WORKER THREAD — gọi Gemini Vision trên thread riêng, UI không đơ
# ══════════════════════════════════════════════════════════════════════
class ScanWorker(QThread):
    """
    Chạy scan_food_image() trên thread riêng.
    Khi xong → emit signal finished(dict) → UI nhận và cập nhật.

    Tại sao cần thread riêng?
    → Gọi API mạng có thể mất 2-5 giây
    → Nếu chạy trên main thread → UI bị đơ / freeze trong khi chờ
    → QThread = chạy song song, UI vẫn responsive
    """
    # Signal gửi kết quả dict về main thread khi AI xong
    finished = Signal(dict)
    # Signal gửi lỗi nếu có exception không mong muốn
    error    = Signal(str)

    def __init__(self, image_path: str, parent=None):
        super().__init__(parent)
        self.image_path = image_path

    def run(self):
        """Chạy trên thread riêng — KHÔNG được đụng vào UI ở đây."""
        try:
            # Import trong run() để tránh circular import khi load app
            from gemini_service import scan_food_image
            result = scan_food_image(self.image_path)
            self.finished.emit(result)
        except Exception as e:
            self.error.emit(str(e))
            self.finished.emit({
                "ten": "Lỗi kết nối",
                "mo_ta": f"⚠️ Không thể kết nối Gemini: {e}",
                "loi_diem": "",
                "luu_y": ""
            })


# ══════════════════════════════════════════════════════════════════════
# HELPER — tạo section card (Lợi điểm / Lưu ý) trong vùng cam
# ══════════════════════════════════════════════════════════════════════
def _make_section_card(icon_path: str, title: str, body_text: str) -> QFrame:
    """
    Tạo 1 card section gồm: [icon tròn] + [tiêu đề 24px] + [nội dung 20px]
    Dùng cho Lợi điểm và Lưu ý theo mock-up.

    icon_path : đường dẫn đến icon (ví dụ assets/fooderai-scanfood/foodscan-good-point.png)
    title     : "Lợi điểm khi ăn món này" hoặc "Lưu ý khi ăn món này"
    body_text : nội dung bullet points từ Gemini
    """
    card = QFrame()
    card.setStyleSheet("QFrame { background: transparent; border: none; }")
    layout = QVBoxLayout(card)
    layout.setContentsMargins(0, 8, 0, 0)
    layout.setSpacing(6)

    # ── HEADER: icon + tiêu đề ───────────────────────────────────────
    header_row = QWidget()
    header_row.setStyleSheet("background: transparent;")
    header_layout = QHBoxLayout(header_row)
    header_layout.setContentsMargins(0, 0, 0, 0)
    header_layout.setSpacing(10)

    # Icon tròn
    lbl_icon = QLabel()
    lbl_icon.setStyleSheet("border: none; background: transparent;")
    if os.path.exists(icon_path):
        lbl_icon.setPixmap(
            QPixmap(icon_path).scaled(
                40, 40,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
        )
    lbl_icon.setFixedSize(40, 40)

    # Tiêu đề section
    lbl_title = QLabel(title)
    font_title = QFont("Roboto")
    font_title.setPixelSize(24)
    font_title.setWeight(QFont.Weight.Bold)
    lbl_title.setFont(font_title)
    lbl_title.setStyleSheet("color: #FFEBB3; border: none; background: transparent;")

    header_layout.addWidget(lbl_icon)
    header_layout.addWidget(lbl_title)
    header_layout.addStretch()

    # ── DIVIDER ──────────────────────────────────────────────────────
    divider = QFrame()
    divider.setFixedHeight(1)
    divider.setStyleSheet("background-color: rgba(255,235,179,0.5); border: none;")

    # ── NỘI DUNG body ────────────────────────────────────────────────
    lbl_body = QLabel(body_text if body_text else "—")
    font_body = QFont("Roboto")
    font_body.setPixelSize(20)
    lbl_body.setFont(font_body)
    lbl_body.setStyleSheet("color: #FFEBB3; border: none; background: transparent;")
    lbl_body.setWordWrap(True)
    lbl_body.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)

    layout.addWidget(header_row)
    layout.addWidget(divider)
    layout.addWidget(lbl_body)

    return card


# ══════════════════════════════════════════════════════════════════════
# PAGE CHÍNH
# ══════════════════════════════════════════════════════════════════════
class PageFoodScanner(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(1240, 640)
        self._scan_worker        = None   # giữ ref để tránh garbage collect
        self._current_image_path = None   # lưu path ảnh hiện tại → dùng khi log_scan()

        self.setStyleSheet("""
            PageFoodScanner {
                background-color: white;
                border: 3px solid rgba(0, 77, 77, 0.5);
                border-radius: 24px;
            }
        """)

        box_shadow = QGraphicsDropShadowEffect()
        box_shadow.setBlurRadius(5)
        box_shadow.setOffset(0, 3)
        box_shadow.setColor(QColor(150, 150, 150, 180))
        self.setGraphicsEffect(box_shadow)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(15, 10, 15, 15)
        main_layout.setSpacing(8)

        # ──────────────────────────────────────────────────────────────
        # PHẦN 1: BANNER TIÊU ĐỀ
        # ──────────────────────────────────────────────────────────────
        self.banner = QFrame()
        self.banner.setFixedSize(1210, 60)

        color_hex = "#F4960C"
        base_color = QColor(color_hex)
        color_80  = base_color.darker(109).name()
        color_100 = base_color.darker(131).name()

        self.banner.setStyleSheet(f"""
            QFrame {{
                background-color: qlineargradient(
                    x1:0, y1:0.2, x2:1, y2:1,
                    stop:0 {color_hex}, stop:0.8 {color_80}, stop:1.0 {color_100}
                );
                border-radius: 15px;
                border: none;
            }}
        """)

        banner_shadow = QGraphicsDropShadowEffect()
        banner_shadow.setBlurRadius(6)
        banner_shadow.setOffset(0, 0)
        banner_shadow.setColor(QColor(0, 0, 0, 204))
        self.banner.setGraphicsEffect(banner_shadow)

        banner_layout = QHBoxLayout(self.banner)
        banner_layout.setContentsMargins(3, 0, 12, 0)
        banner_layout.setSpacing(0)

        title_group = QWidget()
        title_group.setStyleSheet("background: transparent;")
        title_layout = QHBoxLayout(title_group)
        title_layout.setContentsMargins(7, 0, 3, 0)
        title_layout.setSpacing(5)

        title_icon = QLabel()
        tab_icon_path = os.path.join("assets", "fooderai-scanfood", "fooderai-scanfood-logo.png")
        if os.path.exists(tab_icon_path):
            title_icon.setPixmap(
                QPixmap(tab_icon_path).scaledToHeight(45, Qt.TransformationMode.SmoothTransformation)
            )
        title_icon.setStyleSheet("border: none; background: transparent;")

        title_text = QLabel("Quét món ăn")
        title_text.setStyleSheet("""
            color: white; border: none;
            font-family: 'Roboto'; font-size: 25px; font-weight: 800;
        """)

        title_layout.addWidget(title_icon)
        title_layout.addWidget(title_text)
        banner_layout.addWidget(title_group, alignment=Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        banner_layout.addStretch()

        main_layout.addWidget(self.banner, alignment=Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)

        # ──────────────────────────────────────────────────────────────
        # PHẦN 2: CONTENT STACK
        # index 0 = Upload box | index 1 = Kết quả AI
        # ──────────────────────────────────────────────────────────────
        self.content_stack = QStackedWidget()
        self.content_stack.setFixedSize(1210, 550)

        # ── TRANG 0: UPLOAD BOX ───────────────────────────────────────
        self.upload_box = QFrame()
        self.upload_box.setFixedSize(1210, 550)
        self.upload_box.setStyleSheet(
            "QFrame { background-color: white; border: 2px solid #F9C070; border-radius: 8px; }"
        )
        self.upload_box.setCursor(Qt.CursorShape.PointingHandCursor)
        self.upload_box.mousePressEvent = lambda event: self._flash_and_open()

        upload_layout = QVBoxLayout(self.upload_box)
        upload_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        upload_layout.setSpacing(10)

        self.lbl_upload_icon = QLabel()
        self.lbl_upload_icon.setStyleSheet("border: none; background: transparent;")
        self.lbl_upload_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_attach_path = os.path.join("assets", "fooderai-scanfood", "fdai-foodscan-photoattach.png")
        if os.path.exists(icon_attach_path):
            self.lbl_upload_icon.setPixmap(
                QPixmap(icon_attach_path).scaledToHeight(72, Qt.TransformationMode.SmoothTransformation)
            )

        self.lbl_upload_text = QLabel("Nhấn để tải ảnh hoặc chụp ảnh")
        font_upload = QFont("Roboto")
        font_upload.setPixelSize(20)
        font_upload.setWeight(QFont.Weight.Medium)
        font_upload.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 1.1)
        self.lbl_upload_text.setFont(font_upload)
        self.lbl_upload_text.setStyleSheet("color: #888888; border: none;")
        self.lbl_upload_text.setAlignment(Qt.AlignmentFlag.AlignCenter)

        upload_layout.addWidget(self.lbl_upload_icon)
        upload_layout.addWidget(self.lbl_upload_text)

        # ── TRANG 1: KẾT QUẢ AI ──────────────────────────────────────
        self.result_box = QFrame()
        self.result_box.setFixedSize(1210, 550)
        self.result_box.setStyleSheet(
            "QFrame { background-color: white; border: 2px solid #F9C070; border-radius: 8px; }"
        )

        result_layout = QHBoxLayout(self.result_box)
        result_layout.setContentsMargins(12, 12, 0, 12)
        result_layout.setSpacing(12)

        # [LEFT] nút back + ảnh 500x500
        left_col = QVBoxLayout()
        left_col.setSpacing(8)
        left_col.setContentsMargins(0, 0, 0, 0)

        self.btn_back = QPushButton("◄")
        self.btn_back.setFixedSize(44, 44)
        self.btn_back.setStyleSheet("""
            QPushButton {
                background-color: #FDD58D; border: 2px solid #F4960C;
                border-radius: 8px; font-size: 18px; color: #7A4000;
            }
            QPushButton:hover { background-color: #F4960C; color: white; }
        """)
        self.btn_back.clicked.connect(self._on_back_clicked)

        self.lbl_food_img = QLabel()
        self.lbl_food_img.setFixedSize(500, 500)
        self.lbl_food_img.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_food_img.setStyleSheet("""
            QLabel {
                border: 3px solid #FDD58D;
                border-radius: 12px;
                background-color: #FFF8EE;
            }
        """)
        img_shadow = QGraphicsDropShadowEffect()
        img_shadow.setBlurRadius(20)
        img_shadow.setOffset(0, 0)
        img_shadow.setColor(QColor(0, 0, 0, 120))
        self.lbl_food_img.setGraphicsEffect(img_shadow)

        left_col.addWidget(self.btn_back, alignment=Qt.AlignmentFlag.AlignLeft)
        left_col.addWidget(self.lbl_food_img)
        left_col.addStretch()

        # [RIGHT] scroll area màu cam — chứa toàn bộ thông tin AI
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setStyleSheet("""
            QScrollArea { background-color: #EF8511; border: none; border-radius: 0px; }
            QScrollBar:vertical {
                background: #C96800; width: 12px; border-radius: 6px;
            }
            QScrollBar::handle:vertical {
                background: #FDD58D; border-radius: 6px; min-height: 30px;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }
        """)

        # Widget chứa nội dung bên trong scroll
        self.result_content = QWidget()
        self.result_content.setStyleSheet("background-color: #EF8511;")
        self._content_inner_layout = QVBoxLayout(self.result_content)
        self._content_inner_layout.setContentsMargins(20, 20, 20, 20)
        self._content_inner_layout.setSpacing(10)

        # ── Label TÊN MÓN ĂN (Roboto Black 36px) ────────────────────
        self.lbl_food_name = QLabel("TÊN MÓN ĂN")
        font_name = QFont("Roboto")
        font_name.setPixelSize(36)
        font_name.setWeight(QFont.Weight.Black)
        self.lbl_food_name.setFont(font_name)
        self.lbl_food_name.setStyleSheet("color: #FFEBB3; border: none; background: transparent;")
        self.lbl_food_name.setWordWrap(True)

        # ── Divider ───────────────────────────────────────────────────
        divider_main = QFrame()
        divider_main.setFixedHeight(2)
        divider_main.setStyleSheet("background-color: #FFEBB3; border: none;")

        # ── MÔ TẢ món ăn (24px) ──────────────────────────────────────
        self.lbl_food_desc = QLabel("Đang phân tích món ăn...")
        font_desc = QFont("Roboto")
        font_desc.setPixelSize(20)
        self.lbl_food_desc.setFont(font_desc)
        self.lbl_food_desc.setStyleSheet("color: #FFEBB3; border: none; background: transparent;")
        self.lbl_food_desc.setWordWrap(True)
        self.lbl_food_desc.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)

        # ── Placeholder cho section Lợi điểm + Lưu ý ─────────────────
        # Sẽ được tạo lại trong _update_result_ui() sau khi AI trả về
        self._section_loi_diem = None
        self._section_luu_y    = None

        self._content_inner_layout.addWidget(self.lbl_food_name)
        self._content_inner_layout.addWidget(divider_main)
        self._content_inner_layout.addWidget(self.lbl_food_desc)
        self._content_inner_layout.addStretch()

        self.scroll_area.setWidget(self.result_content)
        result_layout.addLayout(left_col)
        result_layout.addWidget(self.scroll_area, 1)

        # Nạp 2 trang vào stack
        self.content_stack.addWidget(self.upload_box)
        self.content_stack.addWidget(self.result_box)
        self.content_stack.setCurrentIndex(0)

        main_layout.addWidget(
            self.content_stack,
            alignment=Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter
        )

    # ══════════════════════════════════════════════════════════════════
    # PRIVATE — XỬ LÝ CLICK UPLOAD
    # ══════════════════════════════════════════════════════════════════
    def _on_upload_clicked(self):
        """Mở file dialog → user chọn ảnh → hiển thị ảnh + gọi Gemini Vision."""
        from PySide6.QtWidgets import QFileDialog

        file_path, _ = QFileDialog.getOpenFileName(
            self, "Chọn ảnh món ăn", "",
            "Ảnh (*.png *.jpg *.jpeg *.webp)"
        )
        if not file_path:
            print("[SCAN] Người dùng hủy chọn ảnh.")
            return

        print(f"[SCAN] Đã nhận ảnh: {file_path}")

        # Lưu lại path ảnh để _update_result_ui dùng khi gọi log_scan()
        self._current_image_path = file_path

        # Hiển thị ảnh vào lbl_food_img, scale vừa 500x500 giữ tỉ lệ
        pixmap = QPixmap(file_path).scaled(
            500, 500,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation
        )
        self.lbl_food_img.setPixmap(pixmap)

        # Reset UI về trạng thái "đang chờ AI"
        self._reset_result_ui()
        self.lbl_food_name.setText("Đang nhận diện...")
        self.lbl_food_desc.setText("⏳ AI đang phân tích ảnh, vui lòng chờ...")

        # Chuyển sang trang kết quả ngay để user thấy ảnh + spinner text
        self.content_stack.setCurrentIndex(1)

        # Khởi động ScanWorker trên thread riêng
        self._scan_worker = ScanWorker(file_path)
        self._scan_worker.finished.connect(self._update_result_ui)
        self._scan_worker.error.connect(lambda e: print(f"[SCAN WORKER ERROR] {e}"))
        self._scan_worker.start()
        print("[SCAN] ScanWorker đã khởi động.")

    def _on_back_clicked(self):
        """Nút ◄ — quay về trang upload, hủy worker nếu đang chạy."""
        if self._scan_worker and self._scan_worker.isRunning():
            self._scan_worker.quit()
            self._scan_worker.wait(500)
            print("[SCAN] Worker bị hủy do user bấm Back.")
        self.content_stack.setCurrentIndex(0)

    # ══════════════════════════════════════════════════════════════════
    # PRIVATE — CẬP NHẬT UI SAU KHI AI TRẢ VỀ
    # ══════════════════════════════════════════════════════════════════
    def _reset_result_ui(self):
        """Xóa các section Lợi điểm / Lưu ý cũ (nếu có) trước khi nạp kết quả mới."""
        if self._section_loi_diem:
            self._content_inner_layout.removeWidget(self._section_loi_diem)
            self._section_loi_diem.deleteLater()
            self._section_loi_diem = None

        if self._section_luu_y:
            self._content_inner_layout.removeWidget(self._section_luu_y)
            self._section_luu_y.deleteLater()
            self._section_luu_y    = None

    def _update_result_ui(self, result: dict):
        """
        Callback khi ScanWorker.finished(dict) — chạy trên main thread.
        Cập nhật toàn bộ vùng cam bên phải theo mock-up.
        """
        print(f"[SCAN] Cập nhật UI: {result.get('ten', '?')}")

        # 1. Xóa section cũ (nếu bấm ảnh mới)
        self._reset_result_ui()

        # 2. Cập nhật tên món + mô tả
        self.lbl_food_name.setText(result.get("ten", "Không xác định"))
        self.lbl_food_desc.setText(result.get("mo_ta", ""))

        # 3. Thêm section Lợi điểm (icon xanh lá thumbs up)
        icon_good = os.path.join("assets", "fooderai-scanfood", "foodscan-good-point.png")
        loi_diem_text = result.get("loi_diem", "")
        if loi_diem_text:
            self._section_loi_diem = _make_section_card(
                icon_path  = icon_good,
                title      = "Lợi điểm khi ăn món này",
                body_text  = loi_diem_text
            )
            # Chèn trước stretch (item cuối cùng)
            stretch_idx = self._content_inner_layout.count() - 1
            self._content_inner_layout.insertWidget(stretch_idx, self._section_loi_diem)

        # 4. Thêm section Lưu ý (icon vàng warning)
        icon_warn = os.path.join("assets", "fooderai-scanfood", "foodscan-warning-point.png")
        luu_y_text = result.get("luu_y", "")
        if luu_y_text:
            self._section_luu_y = _make_section_card(
                icon_path  = icon_warn,
                title      = "Lưu ý khi ăn món này",
                body_text  = luu_y_text
            )
            stretch_idx = self._content_inner_layout.count() - 1
            self._content_inner_layout.insertWidget(stretch_idx, self._section_luu_y)

        # 5. Cuộn lên đầu để user thấy tên món trước
        self.scroll_area.verticalScrollBar().setValue(0)

        # 6. Lưu kết quả quét xuống DB (chạy trên main thread — nhanh, không block UI)
        # ─────────────────────────────────────────────────────────────────────────────
        # Tại sao KHÔNG cần thread riêng?
        # → log_scan() chỉ INSERT 1 dòng vào DB → rất nhanh (~5-20ms)
        # → Khác với scan_food_image() gọi API mạng (2-5 giây) → mới cần QThread
        # → Bọc trong if _DB_AVAILABLE + try/except → lỗi DB không ảnh hưởng UI
        if _DB_AVAILABLE:
            try:
                # Lấy token đã dùng từ worker nếu có (sau này worker có thể emit thêm)
                tokens = result.get("tokens_used", 0) or 0

                scan_id = _db_log_scan(
                    food_name   = result.get("ten"),
                    description = result.get("mo_ta"),
                    benefits    = result.get("loi_diem"),
                    warnings    = result.get("luu_y"),
                    image_path  = self._current_image_path,
                    tokens_used = tokens,
                    user_id     = None,  # sau này truyền user_id thật khi đã login
                )
                print(f"[SCAN DB] Lưu thành công — scan_id={scan_id}")
            except Exception as e:
                # Không crash app — chỉ log lỗi
                print(f"[SCAN DB] Lỗi khi log_scan: {e}")

    # ══════════════════════════════════════════════════════════════════
    # PRIVATE — FLASH + MỞ DIALOG (giữ nguyên từ v1)
    # ══════════════════════════════════════════════════════════════════
    def _flash_and_open(self):
        """Flash background vàng nhạt 30ms rồi mở file dialog — feedback tức thì."""
        self.upload_box.setStyleSheet("""
            QFrame { background-color: #FBF4BD; border: 2px solid #F9C070; border-radius: 8px; }
        """)

        from PySide6.QtCore import QTimer
        QTimer.singleShot(30, lambda: (
            self.upload_box.setStyleSheet("""
                QFrame { background-color: white; border: 2px solid #F9C070; border-radius: 8px; }
            """),
            self._on_upload_clicked()
        ))