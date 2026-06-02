"""
PAGE VERSION INFO — FooderAI
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Tác giả     : Nhóm 25GAI — Nguyên Việt Anh (25AI002), Nguyễn Phú Tài (25AI045),
              Phan Thanh Tuấn (25AI064)
Mô tả       : Trang hiển thị thông tin phiên bản & bản quyền FooderAI.
              Bao gồm lớp InfoButton (nút ⓘ) với hiệu ứng hover/press
              và lớp PageVersionInfo (nội dung trang).

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
HƯỚNG DẪN TÍCH HỢP VÀO fooderMain.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

1. Import ở đầu file fooderMain.py:

        from pages.page_version_info import InfoButton, PageVersionInfo

2. Trong __init__ của FooderAI, thêm TRƯỚC self.connect_nav_buttons():

        self.page_version_info = PageVersionInfo()
        self.feature_stack.addWidget(self.page_version_info)  # Index 5

        self.btn_info = InfoButton(self.central_widget)
        self.btn_info.move(1432, 295)
        self.btn_info.raise_()

        self.connect_nav_buttons()   # ← GIỮ NGUYÊN

        # Kết nối nút ⓘ — KHÔNG dùng switch_feature_page vì modes[] chỉ có 5 phần tử (0-4)
        # Gọi thẳng feature_stack để tránh IndexError: list index out of range
        self.btn_info.clicked.connect(
            lambda: self.feature_stack.setCurrentIndex(5)
        )

        self.feature_stack.show()

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
GIẢI THÍCH 3 LỖI ĐÃ SỬA TRONG FILE NÀY
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

[FIX 1] IndexError: list index out of range
  Nguyên nhân: switch_feature_page(5) gọi nav_bar.modes[5]
               nhưng modes chỉ có 5 phần tử → index tối đa là 4.
  Cách sửa  : Không dùng switch_feature_page cho nút ⓘ.
               Gọi thẳng feature_stack.setCurrentIndex(5) — đủ rồi,
               không cần highlight gì trên thanh nav vì ⓘ không thuộc nav.

[FIX 2] Đường dẫn ảnh sai (pages\assets thay vì assets)
  Nguyên nhân: resource_path() dùng os.path.dirname(__file__).
               __file__ = E:\\FooderAI\\pages\\page_version_info.py
               → dirname  = E:\\FooderAI\\pages\\
               → nối assets = E:\\FooderAI\\pages\assets\\ ← SAI
  Cách sửa  : Leo lên 1 cấp bằng cách gọi dirname() thêm 1 lần nữa.
               dirname(dirname(__file__)) = E:\\FooderAI\\ ← ĐÚNG
               Kỹ thuật: os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

[FIX 3] Content bên phải bị hẹp hơn 22px
  Nguyên nhân: PageVersionInfo có border 3px (cả 2 bên = 6px)
               + right_scroll có border 2px (cả 2 bên = 4px)
               + margin trái/phải 15px mỗi bên (= 30px)
               + left_col 260px + spacing 20px
               = tổng mất: 6 + 4 + 30 + 260 + 20 = 320px
               → right_scroll thực tế chỉ còn 1240 - 320 = 920px
               Nhưng Qt còn tính thêm padding nội bộ → hẹp thêm ~22px.
  Cách sửa  : Bỏ border của right_scroll (dùng border của PageVersionInfo bao ngoài là đủ)
               + giảm margin main từ 15 xuống 10 mỗi bên.
"""

import os
import sys

from PySide6.QtWidgets import (
    QFrame, QLabel, QVBoxLayout, QHBoxLayout,
    QScrollArea, QWidget, QGraphicsDropShadowEffect, QSizePolicy
)
from PySide6.QtGui import (
    QPixmap, QColor, QFont, QPainter
)
from PySide6.QtCore import Qt, Signal


# ─────────────────────────────────────────────────────────────────────
# HÀM TIỆN ÍCH: resource_path — PHIÊN BẢN SỬA LỖI ĐƯỜNG DẪN
# ─────────────────────────────────────────────────────────────────────
def resource_path(relative_path: str) -> str:
    """
    Trả về đường dẫn tuyệt đối tới assets/, tương thích .py và .exe.

    [FIX 2 - GIẢI THÍCH CHI TIẾT]
    Vấn đề cũ:
        base = os.path.dirname(os.path.abspath(__file__))
        → __file__ = E:\\FooderAI\\pages\\page_version_info.py
        → dirname  = E:\\FooderAI\\pages\\          ← LEO LÊN 1 CẤP: đến thư mục chứa file
        → nối assets → E:\\FooderAI\\pages\\assets\\ ← SAI, assets không nằm trong pages/

    Cách sửa:
        Gọi dirname() thêm 1 lần nữa để leo lên thêm 1 cấp nữa:
        → dirname(dirname(__file__)) = E:\\FooderAI\\  ← thư mục gốc của project
        → nối assets → E:\\FooderAI\\assets\\          ← ĐÚNG

    [DEBUG] Để kiểm tra, uncomment 2 dòng print bên dưới khi cần:
    """
    if hasattr(sys, "_MEIPASS"):
        # [NOTE] Khi đóng gói .exe bằng PyInstaller, toàn bộ file được
        # giải nén vào sys._MEIPASS → không còn cấu trúc thư mục pages/
        # nên dùng _MEIPASS làm gốc là đúng trong cả 2 trường hợp.
        return os.path.join(sys._MEIPASS, relative_path)

    # [FIX] Leo lên 2 cấp: page_version_info.py → pages/ → FooderAI/
    base = os.path.dirname(          # Cấp 2: pages/  → FooderAI/
               os.path.dirname(      # Cấp 1: file.py → pages/
                   os.path.abspath(__file__)
               )
           )
    # print(f"[DEBUG resource_path] base = {base}")          # ← bật khi cần debug
    # print(f"[DEBUG resource_path] full = {os.path.join(base, relative_path)}")
    return os.path.join(base, relative_path)


# ─────────────────────────────────────────────────────────────────────
# HÀM TIỆN ÍCH: _make_brightness_variant
# ─────────────────────────────────────────────────────────────────────
def _make_brightness_variant(source_pix: QPixmap, factor: float) -> QPixmap:
    """
    Trả về bản sao QPixmap đã điều chỉnh độ sáng — KHÔNG bị viền đen.

    Tham số:
        source_pix : QPixmap gốc (PNG có alpha/transparency)
        factor     : hệ số độ sáng
                       > 1.0  → sáng hơn  (ví dụ 1.15 = +15%)
                       < 1.0  → tối hơn   (ví dụ 0.70 = -30%)

    [FIX - Giải thích tại sao cách cũ bị viền đen]
    ─────────────────────────────────────────────────────────────────
    Cách cũ dùng vòng lặp pixel-by-pixel:
        c = QColor(img.pixel(x, y))
        r = min(255, int(c.red() * factor))
        ...

    Vấn đề: Ảnh PNG có vùng "nửa trong suốt" (alpha = 10, 20, 30...)
    ở vùng rìa để tạo hiệu ứng anti-aliasing (làm mịn cạnh).
    Khi nhân RGB * 1.15 trên những pixel này, màu bị tính SAI vì Qt
    lưu ảnh dạng "premultiplied alpha" — tức là giá trị RGB đã được
    nhân sẵn với alpha rồi. Nhân thêm lần nữa → màu bị lệch → viền đen.

    [CÁCH MỚI - Dùng QPainter overlay]
    ─────────────────────────────────────────────────────────────────
    Thay vì can thiệp từng pixel, ta dùng kỹ thuật "vẽ đè lớp màu":
      - Tạo QPixmap mới trong suốt hoàn toàn
      - Vẽ ảnh gốc vào (giữ nguyên alpha gốc, không đụng pixel nào)
      - Vẽ đè 1 lớp màu trắng (sáng) hoặc đen (tối) với độ trong suốt
        nhất định lên trên, dùng CompositionMode_SourceAtop
        → chỉ tô màu lên vùng ảnh gốc CÓ alpha, vùng trong suốt bỏ qua
      - Kết quả: ảnh sáng/tối hơn mà alpha gốc hoàn toàn được giữ nguyên
                 → KHÔNG có viền đen
    """
    w, h = source_pix.width(), source_pix.height()

    # Bước 1: Tạo canvas trong suốt cùng kích thước ảnh gốc
    result = QPixmap(w, h)
    result.fill(Qt.GlobalColor.transparent)

    painter = QPainter(result)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

    # Bước 2: Vẽ ảnh gốc — alpha hoàn toàn nguyên vẹn
    painter.drawPixmap(0, 0, source_pix)

    if factor > 1.0:
        # Sáng hơn → vẽ đè lớp MÀU TRẮNG mờ lên trên
        # opacity = (factor - 1.0) → factor=1.15 thì opacity=0.15 (15% trắng)
        # SourceAtop: chỉ tô lên vùng có alpha của ảnh gốc, bỏ qua vùng trong suốt
        opacity = min(1.0, factor - 1.0)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceAtop)
        painter.setOpacity(opacity)
        painter.fillRect(0, 0, w, h, QColor(255, 255, 255))   # Trắng = sáng
    else:
        # Tối hơn → vẽ đè lớp MÀU ĐEN mờ lên trên
        # opacity = (1.0 - factor) → factor=0.70 thì opacity=0.30 (30% đen)
        opacity = min(1.0, 1.0 - factor)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceAtop)
        painter.setOpacity(opacity)
        painter.fillRect(0, 0, w, h, QColor(0, 0, 0))         # Đen = tối

    painter.end()
    return result


# =====================================================================
# LỚP 1: INFO BUTTON — NÚT ⓘ TÙY CHỈNH
# =====================================================================
class InfoButton(QLabel):
    """
    Nút ⓘ dạng QLabel (không dùng QPushButton để tránh frame mặc định).

    Kích thước: 60×60px — khớp với chiều cao ModeNavBar (60px).
    Ảnh nguồn : assets/fooderai-blockcomponent/fooderai-information.png

    Hiệu ứng chuột:
      • enterEvent  → pix_hover  (sáng +15%)
      • mousePressEvent   → pix_press  (tối  -30%)
      • mouseReleaseEvent → pix_normal (gốc 100%) + phát signal clicked()
      • leaveEvent  → pix_normal (gốc 100%)

    Signal:
      clicked() — phát ra khi người dùng nhấn và thả chuột trong vùng nút.
    """

    # [NOTE] Qt signal tùy chỉnh — QLabel không có sẵn signal clicked như QPushButton
    clicked = Signal()

    ICON_SIZE = 60    # px
    HOVER_F   = 1.15  # +15% độ sáng khi hover
    PRESS_F   = 0.70  # -30% độ sáng khi nhấn (= tối đi 30%)

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setFixedSize(self.ICON_SIZE, self.ICON_SIZE)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet("background: transparent; border: none;")

        # ── Nạp ảnh gốc ──────────────────────────────────────────────
        icon_path = resource_path(
            os.path.join("assets", "fooderai-blockcomponent", "fooderai-information.png")
        )

        # [DEBUG] Uncomment để kiểm tra đường dẫn khi gặp lỗi ảnh không hiện:
        # print(f"[DEBUG InfoButton] icon_path = {icon_path}")
        # print(f"[DEBUG InfoButton] exists    = {os.path.exists(icon_path)}")

        if os.path.exists(icon_path):
            # [OK] Ảnh tìm thấy → tạo 3 biến thể sáng/tối sẵn luôn khi khởi tạo
            # (tạo sẵn 1 lần tốt hơn tạo mỗi lần hover → không lag)
            src = QPixmap(icon_path).scaled(
                self.ICON_SIZE, self.ICON_SIZE,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
            self.pix_normal = src
            self.pix_hover  = _make_brightness_variant(src, self.HOVER_F)
            self.pix_press  = _make_brightness_variant(src, self.PRESS_F)
        else:
            # [ERROR] Không tìm thấy ảnh — dùng fallback vẽ tay
            # Nguyên nhân thường gặp:
            #   1. resource_path() trỏ sai thư mục (đã fix ở trên)
            #   2. Tên file sai chính tả (fooderai-information vs fooderai_information)
            #   3. File chưa được thêm vào thư mục assets
            print(f"[InfoButton][ERROR] Không tìm thấy ảnh tại: {icon_path}")
            print(f"[InfoButton][DEBUG] Kiểm tra lại tên file và đường dẫn thư mục assets/")
            self.pix_normal = self._make_fallback_pixmap(QColor("#7FD8E8"))
            self.pix_hover  = self._make_fallback_pixmap(QColor("#A8E8F5"))
            self.pix_press  = self._make_fallback_pixmap(QColor("#5ABFCE"))

        self.setPixmap(self.pix_normal)

    # ── Sự kiện chuột ────────────────────────────────────────────────

    def enterEvent(self, event):
        """Chuột trỏ vào vùng nút: làm sáng +15%."""
        self.setPixmap(self.pix_hover)
        super().enterEvent(event)

    def leaveEvent(self, event):
        """Chuột rời khỏi vùng nút: trả về màu gốc."""
        self.setPixmap(self.pix_normal)
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        """Nhấn giữ chuột trái: làm tối -30%."""
        if event.button() == Qt.MouseButton.LeftButton:
            self.setPixmap(self.pix_press)
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        """
        Thả chuột trái: trả về màu gốc, sau đó phát signal clicked().

        [NOTE] Kiểm tra self.rect().contains() trước khi emit:
        Nếu người dùng nhấn trong nút nhưng kéo chuột ra ngoài rồi mới thả
        → không tính là click → không phát signal.
        Hành vi này giống nút bấm vật lý thật.
        """
        if event.button() == Qt.MouseButton.LeftButton:
            self.setPixmap(self.pix_normal)
            if self.rect().contains(event.position().toPoint()):
                self.clicked.emit()
        super().mouseReleaseEvent(event)

    # ── Hàm hỗ trợ ───────────────────────────────────────────────────

    @staticmethod
    def _make_fallback_pixmap(color: QColor) -> QPixmap:
        """
        Tạo pixmap fallback: hình vuông bo góc + chữ 'i' trắng ở giữa.
        Chỉ dùng khi file ảnh gốc không tìm thấy.
        """
        SIZE = 60
        pix = QPixmap(SIZE, SIZE)
        pix.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pix)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(color)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(4, 4, SIZE - 8, SIZE - 8, 12, 12)
        painter.setPen(QColor("white"))
        f = QFont("Arial", 26, QFont.Weight.Bold)
        painter.setFont(f)
        painter.drawText(pix.rect(), Qt.AlignmentFlag.AlignCenter, "i")
        painter.end()
        return pix


# =====================================================================
# LỚP 2: PAGE VERSION INFO — TRANG NỘI DUNG
# =====================================================================
class PageVersionInfo(QFrame):
    """
    Trang hiển thị thông tin phiên bản và bản quyền FooderAI.

    Kích thước: 1240×640px — khớp với feature_stack trong fooderMain.py.

    Bố cục (KHÔNG có banner trên đầu):
        ┌──────────┬───────────────────────────────────────────────┐
        │  Logo    │  THÔNG TIN PHẦN MỀM (Bold 26px)               │
        │  160px   │  Đồ án cơ sở 1 – FooderAI (20px)              │
        │          │  Phiên bản ...                                │
        │  Fooder  │  ───────────────────────────────              │
        │   AI     │  [mô tả]                                      │
        │          │  ───────────────────────────────              │
        │          │  Bản quyền...                                 │
        │          │  • Nguyễn Việt Anh – MSV: 25AI002             │
        └──────────┴───────────────────────────────────────────────┘

    [NOTE - Tại sao KHÔNG dùng banner?]
    Theo thiết kế mới (hình 2), trang này có tiêu đề lớn ngay trong
    content, không cần banner riêng. Banner làm mất ~70px chiều cao
    → content bị thu hẹp không cần thiết.
    """

    C_ACCENT  = "#2ECC71"
    C_ACCENT2 = "#27AE60"
    C_BORDER  = "rgba(0, 77, 77, 0.5)"
    C_TEXT    = "#1A1A2E"

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(1240, 640)
        self.setFocusPolicy(Qt.FocusPolicy.ClickFocus)

        self.setStyleSheet(f"""
            PageVersionInfo {{
                background-color: white;
                border: 3px solid {self.C_BORDER};
                border-radius: 24px;
            }}
        """)

        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(5)
        shadow.setOffset(0, 3)
        shadow.setColor(QColor(150, 150, 150, 180))
        self.setGraphicsEffect(shadow)

        # ── Layout tổng: margin 10px đều 4 cạnh ──────────────────────
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(12)

        # ══════════════════════════════════════════════════════════════
        # CỘT TRÁI: Logo + "Fooder AI"
        # Kích thước cố định, viền xanh lá nhạt
        # ══════════════════════════════════════════════════════════════
        left_col = QFrame()
        left_col.setFixedWidth(220)
        left_col.setStyleSheet(f"""
            QFrame {{
                background-color: rgba(46, 204, 113, 0.08);
                border-radius: 16px;
                border: 2px solid rgba(46, 204, 113, 0.3);
            }}
            QLabel {{ border: none; background: transparent; }}
        """)

        # spacing=6 → logo cách chữ "Fooder AI" đúng 6px
        left_v = QVBoxLayout(left_col)
        left_v.setAlignment(Qt.AlignmentFlag.AlignCenter)
        left_v.setSpacing(6)   # [SPEC] Logo cách chữ 6px

        # ── Logo ──────────────────────────────────────────────────────
        self.lbl_logo = QLabel()
        self.lbl_logo.setFixedSize(160, 160)
        self.lbl_logo.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # [NOTE] Logo path mới: assets/fooderai-logo/fooderai_logo_removebg.jpg
        # Folder fooderai-logo là folder mới, khác fooderai-blockcomponent cũ
        logo_path = resource_path(
            os.path.join("assets", "fooderai-logo", "fooderai_logo_removebg.jpg")
        )
        # [DEBUG] Bật 2 dòng dưới nếu logo không hiện:
        # print(f"[DEBUG PageVersionInfo] logo_path  = {logo_path}")
        # print(f"[DEBUG PageVersionInfo] logo exists = {os.path.exists(logo_path)}")

        if os.path.exists(logo_path):
            # [OK] Load logo thật
            self.lbl_logo.setPixmap(
                QPixmap(logo_path).scaled(
                    160, 160,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation
                )
            )
        else:
            # [ERROR] File chưa có → hiện emoji táo giữ chỗ
            # Kiểm tra: đúng tên file fooderai_logo_removebg.jpg chưa?
            #           đúng folder assets/fooderai-logo/ chưa?
            print(f"[PageVersionInfo][ERROR] Không tìm thấy logo tại: {logo_path}")
            self.lbl_logo.setText("🍏")
            self.lbl_logo.setStyleSheet(
                "font-size: 80px; background: transparent; border: none;"
            )

        logo_shadow = QGraphicsDropShadowEffect()
        logo_shadow.setBlurRadius(20)
        logo_shadow.setOffset(0, 4)
        logo_shadow.setColor(QColor(46, 204, 113, 120))
        self.lbl_logo.setGraphicsEffect(logo_shadow)

        # ── Chữ "Fooder AI" ───────────────────────────────────────────
        lbl_app_name = QLabel("Fooder AI")
        name_font = QFont("Roboto")
        name_font.setPixelSize(25)
        name_font.setWeight(QFont.Weight.Bold)
        lbl_app_name.setFont(name_font)
        lbl_app_name.setStyleSheet(f"color: {self.C_ACCENT2};")
        lbl_app_name.setAlignment(Qt.AlignmentFlag.AlignCenter)

        left_v.addStretch()
        left_v.addWidget(self.lbl_logo, alignment=Qt.AlignmentFlag.AlignHCenter)
        left_v.addWidget(lbl_app_name, alignment=Qt.AlignmentFlag.AlignHCenter)
        left_v.addStretch()

        # ══════════════════════════════════════════════════════════════
        # CỘT PHẢI: ScrollArea chứa toàn bộ nội dung văn bản
        # ══════════════════════════════════════════════════════════════
        right_scroll = QScrollArea()
        right_scroll.setWidgetResizable(True)
        right_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        right_scroll.setStyleSheet(f"""
            QScrollArea {{
                background: transparent;
                border: none;
            }}
            QScrollBar:vertical {{
                background: rgba(46, 204, 113, 0.10);
                width: 8px;
                border-radius: 4px;
            }}
            QScrollBar::handle:vertical {{
                background: {self.C_ACCENT};
                border-radius: 4px;
                min-height: 24px;
            }}
            QScrollBar::add-line:vertical,
            QScrollBar::sub-line:vertical {{ height: 0px; }}
        """)

        self.content_widget = QWidget()
        self.content_widget.setStyleSheet("background: transparent;")
        content_layout = QVBoxLayout(self.content_widget)
        content_layout.setContentsMargins(10, 10, 10, 10)
        content_layout.setSpacing(10)
        content_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        # ── Tiêu đề lớn: THÔNG TIN PHẦN MỀM ─────────────────────────
        # [SPEC] Roboto Bold 26px — theo hình mockup thứ 2
        lbl_header = QLabel("THÔNG TIN PHẦN MỀM")
        header_font = QFont("Roboto")
        header_font.setPixelSize(32)
        header_font.setWeight(QFont.Weight.Bold)
        lbl_header.setFont(header_font)
        lbl_header.setStyleSheet(f"color: {self.C_TEXT};")

        # ── Tên đồ án (Roboto 20px) ───────────────────────────────────
        self.lbl_title = QLabel("Đồ án cơ sở 1 – FooderAI")
        title_font = QFont("Roboto")
        title_font.setPixelSize(20)
        self.lbl_title.setFont(title_font)
        self.lbl_title.setStyleSheet(f"color: {self.C_TEXT};")

        # ── Phiên bản ─────────────────────────────────────────────────
        self.lbl_version = QLabel("Phiên bản v1.05_5510sf.final260601_lab25gai")
        ver_font = QFont("Roboto")
        ver_font.setPixelSize(20)
        self.lbl_version.setFont(ver_font)
        self.lbl_version.setStyleSheet("color: #555;")

        # ── Đường kẻ phân cách 1 ─────────────────────────────────────
        divider1 = QFrame()
        divider1.setFixedHeight(2)
        divider1.setStyleSheet(
            f"background: {self.C_ACCENT}; border: none; border-radius: 1px;"
        )

        # ── Mô tả ứng dụng (điền sau qua set_content()) ───────────────
        self.lbl_description = QLabel()
        self.lbl_description.setWordWrap(True)
        self.lbl_description.setAlignment(
            Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft
        )
        desc_font = QFont("Roboto")
        desc_font.setPixelSize(20)
        self.lbl_description.setFont(desc_font)
        self.lbl_description.setStyleSheet(f"color: {self.C_TEXT};")
        self.lbl_description.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum
        )

        # ── Đường kẻ phân cách 2 ─────────────────────────────────────
        divider2 = QFrame()
        divider2.setFixedHeight(2)
        divider2.setStyleSheet(
            "background: rgba(46,204,113,0.4); border: none; border-radius: 1px;"
        )

        # ── Dòng bản quyền ────────────────────────────────────────────
        ct_font = QFont("Roboto")
        ct_font.setPixelSize(20)
        ct_font.setWeight(QFont.Weight.Medium)

        # ── Dòng bảo hộ bản quyền VKU ─────────────────────────────────
        # [NOTE] © ghi đầy đủ tên trường theo chuẩn văn bản học thuật
        lbl_vku_copyright = QLabel(
            "© 2026 Trường Đại học Công nghệ Thông tin và Truyền thông Việt - Hàn (VKU). "
            "Mọi quyền được bảo lưu. Sản phẩm được phát triển cho mục đích học thuật."
        )
        lbl_vku_copyright.setWordWrap(True)
        lbl_vku_copyright.setFont(ct_font)
        lbl_vku_copyright.setStyleSheet("color: #555;")

        lbl_copyright_title = QLabel(
            "Bản quyền thuộc về các thành viên trong nhóm của lớp 25GAI:"
        )
        lbl_copyright_title.setFont(ct_font)
        lbl_copyright_title.setStyleSheet(f"color: {self.C_TEXT};")

        # ── Thêm vào layout theo đúng thứ tự ─────────────────────────
        content_layout.addWidget(lbl_header)
        content_layout.addWidget(self.lbl_title)
        content_layout.addWidget(self.lbl_version)
        content_layout.addWidget(divider1)
        content_layout.addWidget(self.lbl_description)
        content_layout.addWidget(divider2)
        content_layout.addWidget(lbl_vku_copyright)  # ← UPGRADE: THÊM dòng này
        content_layout.addWidget(lbl_copyright_title)

        # ── Danh sách thành viên (dấu gạch đầu dòng "-") ─────────────
        # [NOTE] Dùng "-" thay "•" để khớp với mockup hình 2
        members = [
            ("Nguyễn Việt Anh",  "MSV: 25AI002"),
            ("Nguyễn Phú Tài",   "MSV: 25AI045"),
            ("Phan Thanh Tuấn",  "MSV: 25AI064"),
        ]
        for name, msv in members:
            row_widget = QWidget()
            row_widget.setStyleSheet("background: transparent;")
            row = QHBoxLayout(row_widget)
            row.setContentsMargins(8, 0, 0, 0)   # thụt vào 8px từ lề
            row.setSpacing(6)

            lbl_dash = QLabel("-")
            lbl_dash.setFixedWidth(10)
            lbl_dash.setFont(ct_font)
            lbl_dash.setStyleSheet(f"color: {self.C_TEXT};")

            lbl_name = QLabel(name)
            lbl_name.setFont(ct_font)
            lbl_name.setStyleSheet(f"color: {self.C_TEXT};")

            lbl_msv = QLabel(f"– {msv}")
            lbl_msv.setFont(ct_font)
            lbl_msv.setStyleSheet("color: #555;")

            row.addWidget(lbl_dash)
            row.addWidget(lbl_name)
            row.addWidget(lbl_msv)
            row.addStretch()

            content_layout.addWidget(row_widget)

        right_scroll.setWidget(self.content_widget)

        main_layout.addWidget(left_col)
        main_layout.addWidget(right_scroll, 1)   # stretch=1 → chiếm toàn bộ phần còn lại

        self.set_content()

    # ─────────────────────────────────────────────────────────────────
    # API CÔNG KHAI
    # ─────────────────────────────────────────────────────────────────

    def set_content(
        self,
        version: str = "v1.05_5510sf.final260601_lab25gai",
        description: str = (
            "FooderAI là trợ lý dinh dưỡng thông minh hỗ trợ tư vấn chế độ ăn uống, "
            "tính toán chỉ số sức khỏe (BMI, BMR, TDEE), nhận diện món ăn qua hình ảnh "
            "và gợi ý bài tập phù hợp với từng cá nhân. Được xây dựng bởi nhóm sinh viên "
            "lớp 25GAI, Khoa Khoa học Máy tính, Trường Đại học Công nghệ Thông tin và "
            "Truyền thông Việt - Hàn (VKU), Đà Nẵng, Việt Nam."
        ),
        title: str = "Đồ án cơ sở 1 – FooderAI",
    ):
        """
        Cập nhật tiêu đề, phiên bản và mô tả.

        Gọi hàm này sau khi khởi tạo để điền nội dung:
            self.page_version_info.set_content(
                version     = "v1.01_...",
                description = "Mô tả dài...",
                title       = "Đồ án cơ sở 1 – FooderAI"
            )
        """
        self.lbl_title.setText(title)
        self.lbl_version.setText(f"Phiên bản {version}")
        self.lbl_description.setText(description)

    def set_logo(self, logo_path: str):
        """Thay thế logo cột trái bằng ảnh từ đường dẫn cho trước."""
        if os.path.exists(logo_path):
            self.lbl_logo.setPixmap(
                QPixmap(logo_path).scaled(
                    160, 160,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation
                )
            )
        else:
            print(f"[PageVersionInfo][ERROR] set_logo() không tìm thấy file: {logo_path}")