import os
import math
import threading
import webbrowser
import http.server
import urllib.parse
from PySide6.QtWidgets import (QFrame, QVBoxLayout, QHBoxLayout, QLabel,
                               QWidget, QGraphicsDropShadowEffect, QPushButton,
                               QLineEdit, QSizePolicy, QButtonGroup, QMessageBox)
from PySide6.QtCore import Qt, QSize, Signal, QObject
from PySide6.QtGui import (QFont, QColor, QPixmap, QPainter, QPainterPath,
                           QBrush, QPen, QLinearGradient, QIcon)
from fooder_widgetBack import NutritionLogic

# ─── Thư viện OAuth mới — chỉ cần requests ───────────────────────────────────
try:
    import requests as _requests
    _REQUESTS_OK = True
except ImportError:
    _REQUESTS_OK = False

# ─── DB layer ────────────────────────────────────────────────────────────────
try:
    from fooder_database import upsert_user, update_user_profile, get_user_by_uid
    _DB_OK = True
except Exception:
    _DB_OK = False

# ─── Config Google OAuth — đọc từ .env, không cần client_secrets.json ────────
from dotenv import load_dotenv as _load_dotenv
_load_dotenv()
_GOOGLE_CLIENT_ID     = os.getenv("GOOGLE_CLIENT_ID", "")
_GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "")
_GAUTH_OK      = bool(_GOOGLE_CLIENT_ID and _GOOGLE_CLIENT_SECRET and _REQUESTS_OK)
_REDIRECT_URI  = "http://localhost:8765/oauth2callback"
_REDIRECT_PORT = 8765

# ─── Signal bridge: OAuth chạy trong thread → Qt main thread ─────────────────
class _OAuthSignals(QObject):
    login_success = Signal(str, str, str, str)  # uid, email, display_name, photo_url
    login_failed  = Signal(str)                 # error message


# ─── Callback HTTP server bắt code từ Google ─────────────────────────────────
class _OAuthCallbackHandler(http.server.BaseHTTPRequestHandler):
    """Bắt request redirect từ Google, parse code, gọi exchange."""
    auth_code: str = None
    flow: object  = None

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)
        if "code" in params:
            _OAuthCallbackHandler.auth_code = params["code"][0]
        self.send_response(200)
        self.end_headers()
        html = (
            "<html><body style='font-family:sans-serif;text-align:center;padding-top:80px'>"
            "<h2 style='color:#3EE28C'>&#10003; &nbsp;Dang nhap thanh cong!</h2>"
            "<p>Ban co the dong tab nay va quay lai FooderAI.</p>"
            "</body></html>"
        )
        self.wfile.write(html.encode("utf-8"))

    def log_message(self, fmt, *args):  # tắt log console
        pass

# =====================================================================
# HẰNG SỐ MÀU — PALETTE TRANG HỒ SƠ
# =====================================================================
COLOR_BANNER = "#3EE28C"
COLOR_TEAL   = "#266066"
COLOR_TEXT   = "#1A2A3A"
COLOR_MUTED  = "#8A9BAC"
COLOR_BORDER = "rgba(0, 77, 77, 0.18)"
COLOR_CARD_BG = "#F7FAFA"

_AVT_DEFAULT = os.path.join("assets", "fooderai-userpage", "fdai-userpage-unsignedin.png")


# =====================================================================
# HÀM TIỆN ÍCH
# =====================================================================
def _gradient_style(base_hex: str, radius: int = 12) -> str:
    dark = QColor(base_hex).darker(116).name()
    return f"""
        QPushButton {{
            background: qlineargradient(x1:0,y1:0,x2:1,y2:1,
                stop:0 {base_hex}, stop:1 {dark});
            border-radius: {radius}px;
            border: none;
            color: white;
        }}
        QPushButton:hover   {{ background: {QColor(base_hex).lighter(108).name()}; }}
        QPushButton:pressed {{ background: {dark}; }}
        QPushButton:disabled {{
            background: #C8D0D8;
            color: rgba(255,255,255,0.5);
        }}
    """


# =====================================================================
# LỚP 1: AVATARBOX
# =====================================================================
class AvatarBox(QLabel):
    def __init__(self, size: int = 180, parent=None):
        super().__init__(parent)
        self._size = size
        self._radius = size // 3
        self.setFixedSize(size, size)
        self._pix = None
        self.reset_default()

    def reset_default(self):
        if os.path.exists(_AVT_DEFAULT):
            pix = QPixmap(_AVT_DEFAULT).scaled(
                self._size, self._size,
                Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation
            )
            self._pix = pix
        else:
            self._pix = None
        self.update()

    def set_pixmap(self, pixmap: QPixmap):
        self._pix = pixmap.scaled(
            self._size, self._size,
            Qt.AspectRatioMode.KeepAspectRatioByExpanding,
            Qt.TransformationMode.SmoothTransformation
        )
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        path = QPainterPath()
        path.addRoundedRect(2, 2, self._size - 4, self._size - 4,
                            self._radius, self._radius)
        painter.setClipPath(path)

        if self._pix:
            painter.drawPixmap(0, 0, self._pix)
        else:
            grad = QLinearGradient(0, 0, self._size, self._size)
            grad.setColorAt(0.0, QColor("#3EE28C"))
            grad.setColorAt(1.0, QColor("#2ABF73"))
            painter.fillPath(path, QBrush(grad))

        painter.setClipping(False)
        painter.setPen(QPen(QColor(COLOR_BANNER), 2.5))
        painter.drawRoundedRect(2, 2, self._size - 4, self._size - 4,
                                self._radius, self._radius)


# =====================================================================
# LỚP 2: GENDERBUTTON
# =====================================================================
class GenderButton(QPushButton):
    COLORS = {
        "male":   ("#42A5F5", "#1E88E5"),
        "female": ("#F48FB1", "#E91E8C"),
    }

    def __init__(self, gender: str, label: str, parent=None):
        super().__init__(label, parent)
        self._gender = gender
        self.setFixedSize(92, 44)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setCheckable(True)
        self._shadow = QGraphicsDropShadowEffect()
        self._shadow.setBlurRadius(10)
        self._shadow.setOffset(0, 3)
        self.setGraphicsEffect(self._shadow)
        self._apply_style(selected=False)

    def _apply_style(self, selected: bool):
        base, dark = self.COLORS[self._gender]
        if selected:
            self._shadow.setColor(QColor(base).darker(120))
            self._shadow.setBlurRadius(12)
            self.setStyleSheet(f"""
                QPushButton {{
                    background: qlineargradient(x1:0,y1:0,x2:1,y2:1,
                        stop:0 {base}, stop:1 {dark});
                    border-radius: 22px;
                    border: 2px solid {QColor(base).lighter(120).name()};
                    color: white;
                    font-family: 'Roboto';
                    font-size: 16px;
                    font-weight: 700;
                }}
            """)
        else:
            self._shadow.setColor(QColor(0, 0, 0, 40))
            self._shadow.setBlurRadius(4)
            self.setStyleSheet("""
                QPushButton {
                    background-color: #E8ECF0;
                    border-radius: 22px;
                    border: 1.5px solid #C8D0D8;
                    color: #5E6E7E;
                    font-family: 'Roboto';
                    font-size: 15px;
                    font-weight: 600;
                }
                QPushButton:hover { background-color: #D8E0E8; }
            """)

    def setChecked(self, checked: bool):
        super().setChecked(checked)
        self._apply_style(selected=checked)


# =====================================================================
# LỚP 3: ACTIVITYBUTTON
# =====================================================================
class ActivityButton(QPushButton):
    BASE_COLOR = "#3EE28C"

    def __init__(self, main_text: str, sub_text: str, parent=None):
        super().__init__(parent)
        self.setFixedHeight(50)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setCheckable(True)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 5, 16, 5)
        lay.setSpacing(1)

        self._lbl_main = QLabel(main_text)
        f_main = QFont("Roboto")
        f_main.setPixelSize(16)
        f_main.setWeight(QFont.Weight.Medium)
        self._lbl_main.setFont(f_main)

        self._lbl_sub = QLabel(sub_text)
        f_sub = QFont("Roboto")
        f_sub.setPixelSize(13)
        self._lbl_sub.setFont(f_sub)

        lay.addWidget(self._lbl_main)
        lay.addWidget(self._lbl_sub)

        self._apply_style(False)

    def _apply_style(self, selected: bool):
        dark = QColor(self.BASE_COLOR).darker(116).name()
        if selected:
            style = f"""
                QPushButton {{
                    background: qlineargradient(x1:0,y1:0,x2:1,y2:1,
                        stop:0 {self.BASE_COLOR}, stop:1 {dark});
                    border-radius: 12px; border: none;
                }}
            """
            self._lbl_main.setStyleSheet("color: white; background: transparent;")
            self._lbl_sub.setStyleSheet("color: rgba(255,255,255,0.75); background: transparent;")
        else:
            style = """
                QPushButton {
                    background-color: white;
                    border-radius: 12px;
                    border: 1.5px solid rgba(0,77,77,0.15);
                }
                QPushButton:hover { background-color: #F0FFF8; }
            """
            self._lbl_main.setStyleSheet(f"color: {COLOR_TEXT}; background: transparent;")
            self._lbl_sub.setStyleSheet(f"color: {COLOR_MUTED}; background: transparent;")
        self.setStyleSheet(style)

    def setChecked(self, checked: bool):
        super().setChecked(checked)
        self._apply_style(selected=checked)


# =====================================================================
# LỚP 4: GOALBUTTON
# =====================================================================
class GoalButton(QPushButton):
    COLORS = {
        "lose":     ("#FF7043", "#E64A19"),
        "maintain": ("#78909C", "#546E7A"),
        "gain":     ("#66BB6A", "#388E3C"),
    }

    def __init__(self, goal_key: str, label: str, parent=None):
        super().__init__(label, parent)
        self._key = goal_key
        self.setFixedHeight(46)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setCheckable(True)
        self._apply_style(False)

    def _apply_style(self, selected: bool):
        base, dark = self.COLORS[self._key]
        font = QFont("Roboto")
        font.setPixelSize(22)
        font.setWeight(QFont.Weight.Bold)
        self.setFont(font)
        if selected:
            self.setStyleSheet(f"""
                QPushButton {{
                    background: qlineargradient(x1:0,y1:0,x2:1,y2:1,
                        stop:0 {base}, stop:1 {dark});
                    border-radius: 22px; border: none; color: white;
                }}
            """)
        else:
            self.setStyleSheet("""
                QPushButton {
                    background-color: #E8ECF0;
                    border-radius: 22px;
                    border: 1.5px solid #C8D0D8;
                    color: #708090;
                    font-weight: 700;
                }
                QPushButton:hover { background-color: #D8E0E8; }
            """)

    def setChecked(self, checked: bool):
        super().setChecked(checked)
        self._apply_style(selected=checked)


# =====================================================================
# LỚP CHÍNH: PAGEUSERPROFILE
# =====================================================================
class PageUserProfile(QFrame):
    # --- ĐỊNH NGHĨA 2 SIGNALS CHÍ HẠNG MẠNG ĐỂ CỨU LỖI ATTRIBUTEERROR ---
    stats_saved = Signal(float, int, int, int)  # bmi, bmr, tdee, goal_kcal
    username_changed = Signal(str)  # Truyền username mới lên dashboard


    def __init__(self, parent=None):
        super().__init__(parent)
        # ── State đăng nhập ────────────────────────────────────────────
        self._user_id: int | None = None   # user_id nội bộ trong DB (sau khi login)
        self._uid:     str | None = None   # Firebase/Google uid
        self._oauth_signals = _OAuthSignals()
        self._oauth_signals.login_success.connect(self._apply_login)
        self._oauth_signals.login_failed.connect(self._on_login_error)
        # ──────────────────────────────────────────────────────────────
        self.setFixedSize(1240, 640)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet("""
            PageUserProfile {
                background-color: white;
                border: 2px solid rgba(0, 77, 77, 0.25);
                border-radius: 24px;
            }
        """)

        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(5)
        shadow.setOffset(0, 3)
        shadow.setColor(QColor(150, 150, 150, 180))
        self.setGraphicsEffect(shadow)

        main = QVBoxLayout(self)
        main.setContentsMargins(6, 6, 6, 6)
        main.setSpacing(0)

        self._build_banner(main)

        body = QWidget()
        body.setStyleSheet("background: transparent;")
        body_lay = QHBoxLayout(body)
        body_lay.setContentsMargins(2 , 2 , 2 , 2)
        body_lay.setSpacing(10)

        self._build_left(body_lay)
        self._build_right(body_lay)

        main.addWidget(body, 1)

    # ================================================================
    # BANNER
    # ================================================================
    def _build_banner(self, parent_lay):
        banner = QFrame()
        banner.setFixedHeight(64)
        banner.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        c0   = COLOR_BANNER
        c80  = QColor(c0).darker(109).name()
        c100 = QColor(c0).darker(131).name()

        banner.setStyleSheet(f"""
            QFrame {{
                background-color: qlineargradient(
                    x1:0,y1:0.2,x2:1,y2:1,
                    stop:0 {c0}, stop:0.8 {c80}, stop:1.0 {c100}
                );
                border-radius: 18px; border: none;
            }}
        """)

        sh = QGraphicsDropShadowEffect()
        sh.setBlurRadius(6)
        sh.setOffset(0, 2)
        sh.setColor(QColor(0, 0, 0, 160))
        banner.setGraphicsEffect(sh)

        b_lay = QHBoxLayout(banner)
        b_lay.setContentsMargins(16, 0, 20, 0)
        b_lay.setSpacing(12)

        # ── Icon 50x50 ──
        icon_box = AvatarBox(size=50)
        b_lay.addWidget(icon_box, alignment=Qt.AlignmentFlag.AlignVCenter)

        # ── Chữ "Hồ sơ người dùng" — ShadowLabel 25px Bold, canh giữa dọc icon ──
        class ShadowLabel(QLabel):
            def paintEvent(self, event):
                p = QPainter(self)
                p.setRenderHint(QPainter.RenderHint.Antialiasing)
                p.setFont(self.font())
                p.setPen(QColor(0, 0, 0, 130))
                p.drawText(self.rect().translated(0, 2),
                           Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                           self.text())
                p.setPen(QColor("white"))
                p.drawText(self.rect(),
                           Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                           self.text())

        lbl_t = ShadowLabel("Hồ sơ người dùng")
        ft = QFont("Roboto")
        ft.setPixelSize(25)
        ft.setWeight(QFont.Weight.Bold)
        lbl_t.setFont(ft)
        lbl_t.setStyleSheet("border: none; background: transparent;")

        b_lay.addWidget(lbl_t, alignment=Qt.AlignmentFlag.AlignVCenter)
        b_lay.addStretch()

        parent_lay.addWidget(banner)
        parent_lay.addSpacing(6)

    # ================================================================
    # CỘT TRÁI
    # ================================================================
    def _build_left(self, parent_lay):
        left = QFrame()
        left.setFixedWidth(240)
        left.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        left.setStyleSheet(f"""
            QFrame {{
                background-color: {COLOR_CARD_BG};
                border-radius: 18px;
                border: 1.5px solid {COLOR_BORDER};
            }}
            QLabel {{ border: none; background: transparent; }}
        """)

        lay = QVBoxLayout(left)
        lay.setContentsMargins(20, 20, 20, 20)
        lay.setSpacing(8)
        lay.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)

        self.avatar = AvatarBox(size=180)
        lay.addWidget(self.avatar, alignment=Qt.AlignmentFlag.AlignHCenter)
        lay.addSpacing(8)

        self.lbl_name = QLabel("Chưa đăng nhập")
        fn = QFont("Roboto")
        fn.setPixelSize(18)
        fn.setWeight(QFont.Weight.Bold)
        self.lbl_name.setFont(fn)
        self.lbl_name.setStyleSheet(f"color: {COLOR_TEAL};")
        self.lbl_name.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_name.setWordWrap(True)
        lay.addWidget(self.lbl_name)

        self.lbl_email = QLabel("–")
        fe = QFont("Roboto")
        fe.setPixelSize(11)
        self.lbl_email.setFont(fe)
        self.lbl_email.setStyleSheet(f"color: {COLOR_MUTED};")
        self.lbl_email.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(self.lbl_email)

        lay.addSpacing(10)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("background: rgba(0,77,77,0.12); border: none;")
        sep.setFixedHeight(1)
        lay.addWidget(sep)
        lay.addSpacing(10)

        self.btn_google = QPushButton("  Đăng nhập với Google")
        self.btn_google.setFixedHeight(45)
        fg = QFont("Roboto")
        fg.setPixelSize(14)
        self.btn_google.setFont(fg)
        self.btn_google.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_google.setStyleSheet("""
            QPushButton {
                background-color: white;
                color: #3C4043;
                border: 1.5px solid #DADCE0;
                border-radius: 20px;
                padding: 0 12px;
            }
            QPushButton:hover  { background-color: #F8F9FA; border-color: #3EE28C; }
            QPushButton:pressed{ background-color: #E8F5E9; }
        """)
        self.btn_google.clicked.connect(self._on_google_login)
        lay.addWidget(self.btn_google)

        lbl_note = QLabel("Dữ liệu của bạn được bảo mật\nvà không chia sẻ với bên thứ ba")
        fnote = QFont("Roboto")
        fnote.setPixelSize(10)
        lbl_note.setFont(fnote)
        lbl_note.setStyleSheet(f"color: {COLOR_MUTED};")
        lbl_note.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_note.setWordWrap(True)
        lay.addWidget(lbl_note)

        lay.addStretch()

        self.btn_logout = QPushButton("Đăng xuất")
        self.btn_logout.setFixedHeight(34)
        self.btn_logout.setFont(QFont("Roboto", 10))
        self.btn_logout.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_logout.setStyleSheet("""
            QPushButton {
                background: transparent; color: #E57373;
                border: 1px solid #E57373; border-radius: 17px;
            }
            QPushButton:hover { background: #FFEBEE; }
        """)
        self.btn_logout.setVisible(False)
        self.btn_logout.clicked.connect(self._on_logout)
        lay.addWidget(self.btn_logout)

        parent_lay.addWidget(left)

    # ================================================================
    # CỘT PHẢI — đã xây lại
    # ================================================================
    def _build_right(self, parent_lay):
        right = QFrame()
        right.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        right.setFixedSize(950, 550)
        right.setStyleSheet("""
            QFrame {
                background: transparent;
                border: 2px solid rgba(0, 77, 77, 0.15);
                border-radius: 18px;
            }
        """)
        # Cho phép QFrame nhận focus khi click vào vùng trống
        # → kéo focus ra khỏi QLineEdit → border xanh tự tắt
        right.setFocusPolicy(Qt.FocusPolicy.ClickFocus)


        # ── [BOX 1] HỌ VÀ TÊN — tọa độ tự do ──
        lbl_hoten = QLabel("HỌ VÀ TÊN CỦA BẠN", right)
        #NEW UPDATE FONT
        f_lbl = QFont("Roboto")
        f_lbl.setPixelSize(13)
        f_lbl.setWeight(QFont.Weight.Bold)
        f_lbl.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 2)
        lbl_hoten.setFont(f_lbl)

        lbl_hoten.setStyleSheet("color: #3A4A5A; background: transparent; border: none;")
        lbl_hoten.move(18, 16)
        lbl_hoten.adjustSize()

        self.input_name = QLineEdit(right)
        self.input_name.setPlaceholderText("Đăng nhập Google để đặt tên...")
        self.input_name.setGeometry(16, 40, 918, 44)  # x, y, w, h
        self.input_name.setEnabled(False)
        self.input_name.setFont(QFont("Roboto", 16))
        self.input_name.setStyleSheet("""
            QLineEdit {
                background-color: #F0F4F8;
                color: #8A9BAC;
                border-radius: 22px;
                border: 1.5px solid #C8D0D8;
                padding: 0 18px;
            }
            QLineEdit:enabled {
                background-color: white;
                color: #1A2A3A;
                border: 1.5px solid rgba(0,77,77,0.25);
            }
            QLineEdit:enabled:focus {
                border: 1.5px solid #3EE28C;
            }
        """)

        # -- [ROW 2.1] TUỔI -----------------------------------------------------------------------
        # QLabel đặt tọa độ tuyệt đối bằng .move(x, y) — không dùng layout
        # y=94: bắt đầu từ input_name kết thúc tại y=84 (40+44), cách 10px → 94
        lbl_age = QLabel("⌚ TUỔI", right)
        f_lbl2 = QFont("Roboto")
        f_lbl2.setPixelSize(13)
        f_lbl2.setWeight(QFont.Weight.Bold)
        lbl_age.setFont(f_lbl2)
        lbl_age.setStyleSheet("color: #3A4A5A; background: transparent; border: none;")
        lbl_age.move(16, 94)
        lbl_age.adjustSize()  # tự co giãn theo nội dung chữ, tránh bị cắt

        # Label GIỚI TÍNH — cùng hàng y=94 với TUỔI, đặt sau input_age (x=16+160+24=200)
        lbl_gender = QLabel("GIỚI TÍNH", right)
        lbl_gender.setFont(f_lbl2)  # dùng chung font với TUỔI cho đồng bộ
        lbl_gender.setStyleSheet("color: #3A4A5A; background: transparent; border: none;")
        lbl_gender.move(200, 94)
        lbl_gender.adjustSize()

        # QLineEdit: ô nhập tuổi — setGeometry(x, y, w, h) đặt vị trí + kích thước 1 lần
        self.input_age = QLineEdit(right)
        self.input_age.setPlaceholderText("VD: 22")
        self.input_age.setGeometry(16, 114, 160, 44)  # cùng hàng y với nút giới tính
        f_age = QFont("Roboto")
        f_age.setPixelSize(15)
        self.input_age.setFont(f_age)
        self.input_age.setStyleSheet("""
            QLineEdit {
                background-color: white;
                color: #1A2A3A;
                border-radius: 12px;
                border: 1.5px solid rgba(0,77,77,0.25);
                padding: 0 14px;
            }
            QLineEdit:focus    { border: 1.5px solid #3EE28C; }
            QLineEdit:!focus   { border: 1.5px solid rgba(0,77,77,0.25); }
        """)

        # -- [ROW 2.2] GIỚI TÍNH ------------------------------------------------------------------
        # Cơ chế: 2 QPushButton checkable — khi 1 ON thì hàm _update ép cái kia OFF
        # Dùng setIcon(QPixmap.scaled()) thay vì QIcon trực tiếp để ép đúng kích thước
        # dù PNG gốc lệch pixel do bevel/shadow từ PPTX export

        _ASSET = os.path.join("assets", "fooderai-userpage")

        BTN_W = 92
        BTN_H = int(BTN_W / 1.77)# CHỈNH TẠI ĐÂY nếu bất ổn — tỉ lệ 658:372 = 1.77:1
        # Hàm scale ảnh về đúng BTN_W x BTN_H — tránh lệch do PNG gốc khác pixel

        def _make_icon(filename):
            pix = QPixmap(os.path.join(_ASSET, filename)).scaled(
                BTN_W, BTN_H,
                Qt.AspectRatioMode.KeepAspectRatio,  # ép đúng kích thước, bỏ qua tỉ lệ
                Qt.TransformationMode.SmoothTransformation  # scale mượt, không bị răng cưa
            )
            return QIcon(pix)

        # Nút Nam — x=200 (sau input_age x=16+160+24=200), y=114 (cùng hàng input)
        # new change: nút nam và nữ có thể giảm xuống là x=196, y=110
        self.btn_male = QPushButton(right)
        self.btn_male.setGeometry(196, 110, BTN_W, BTN_H)
        self.btn_male.setCheckable(True)  # giữ trạng thái ON/OFF sau khi click
        self.btn_male.setStyleSheet("border: none; background: transparent;")
        self.btn_male.setCursor(Qt.CursorShape.PointingHandCursor)

        # Nút Nữ — x = 200 + BTN_W = cách nút Nam 0px (cũ)
        # new change: nút nam và nữ có thể giảm xuống là 196, 110
        self.btn_female = QPushButton(right)
        self.btn_female.setGeometry(196 + BTN_W, 110, BTN_W, BTN_H)
        self.btn_female.setCheckable(True)
        self.btn_female.setStyleSheet("border: none; background: transparent;")
        self.btn_female.setCursor(Qt.CursorShape.PointingHandCursor)

        # iconSize phải khớp BTN_W x BTN_H để Qt không thêm padding trắng
        self.btn_male.setIconSize(QSize(BTN_W, BTN_H))
        self.btn_female.setIconSize(QSize(BTN_W, BTN_H))

        def _update_gender():
            if self.btn_male.isChecked():
                # Nam ON → ảnh sáng, ép Nữ tắt → ảnh tối
                self.btn_male.setIcon(_make_icon("fdai-male-on.png"))
                self.btn_female.setIcon(_make_icon("fdai-female-off.png"))
                self.btn_female.setChecked(False)
            else:
                # Bấm Nam lần 2 (bỏ chọn) → trả về ảnh off
                self.btn_male.setIcon(_make_icon("fdai-male-off.png"))

        def _update_female():
            if self.btn_female.isChecked():
                # Nữ ON → ảnh sáng, ép Nam tắt → ảnh tối
                self.btn_female.setIcon(_make_icon("fdai-female-on.png"))
                self.btn_male.setIcon(_make_icon("fdai-male-off.png"))
                self.btn_male.setChecked(False)
            else:
                # Bấm Nữ lần 2 (bỏ chọn) → trả về ảnh off
                self.btn_female.setIcon(_make_icon("fdai-female-off.png"))

        # Mặc định khi mở app: Nam ON, Nữ OFF
        self.btn_male.setChecked(True)
        self.btn_male.setIcon(_make_icon("fdai-male-on.png"))
        self.btn_female.setIcon(_make_icon("fdai-female-off.png"))

        # clicked.connect: Qt tự gọi hàm mỗi khi nút được bấm
        self.btn_male.clicked.connect(_update_gender)
        self.btn_female.clicked.connect(_update_female)

        # -- [ROW 3] CHIỀU CAO + CÂN NẶNG --------------------------------------------------------
        # Cùng cấu trúc ROW 2.1: label trên, input dưới, tọa độ tuyệt đối
        # y=214: ROW 2 kết thúc tại y=114+90=204, cách 10px → 214
        # -- Chiều cao --
        lbl_height = QLabel("📏 CHIỀU CAO (CM)", right)
        lbl_height.setFont(f_lbl2)  # dùng chung font Bold 13px
        lbl_height.setStyleSheet("color: #3A4A5A; background: transparent; border: none;")
        lbl_height.move(16, 180) #<=== CHỈNH TẠI ĐÂY
        lbl_height.adjustSize()

        self.input_height = QLineEdit(right)
        self.input_height.setPlaceholderText("VD: 170")
        self.input_height.setGeometry(16, 200, 160, 44) #<=== CHỈNH TẠI ĐÂY
        self.input_height.setFont(f_age)  # dùng chung font 15px với ô tuổi
        self.input_height.setStyleSheet("""
                    QLineEdit {
                        background-color: white;
                        color: #1A2A3A;
                        border-radius: 12px;
                        border: 1.5px solid rgba(0,77,77,0.25);
                        padding: 0 14px;
                    }
                    QLineEdit:focus  { border: 1.5px solid #3EE28C; }
                    QLineEdit:!focus { border: 1.5px solid rgba(0,77,77,0.25); }
                """)

        # -- Cân nặng -- cách chiều cao 16px (x = 16+160+16 = 192)
        lbl_weight = QLabel("⚖ CÂN NẶNG (KG)", right)
        lbl_weight.setFont(f_lbl2)
        lbl_weight.setStyleSheet("color: #3A4A5A; background: transparent; border: none;")
        lbl_weight.move(200, 180) #<=== CHỈNH TẠI ĐÂY
        lbl_weight.adjustSize()

        self.input_weight = QLineEdit(right)
        self.input_weight.setPlaceholderText("VD: 60")
        self.input_weight.setGeometry(200, 200, 177, 44) #<=== CHỈNH TẠI ĐÂY
        self.input_weight.setFont(f_age)
        self.input_weight.setStyleSheet(self.input_height.styleSheet())  # dùng chung style

        # -- [ROW 4] MỤC TIÊU SỨC KHỎE ----------------------------------------------------------
        # 3 nút exclusive: chọn 1 thì 2 cái kia OFF — cơ chế giống giới tính
        # y=288: input_height/weight kết thúc y=234+44=278, cách 10px → 288

        lbl_goal = QLabel("🎯 MỤC TIÊU SỨC KHỎE", right)
        lbl_goal.setFont(f_lbl2)
        lbl_goal.setStyleSheet("color: #3A4A5A; background: transparent; border: none;")
        lbl_goal.move(16, 260)
        lbl_goal.adjustSize()

        # Hàm tạo style cho nút mục tiêu — selected: màu riêng, unselected: xám (và tăng đậm phông)
        #CHỖ CHỈNH SỬA SẼ NẰM Ở ĐÂY
        def _goal_style(color: str, selected: bool) -> str:
            if selected:
                return f"""QPushButton {{
                           background-color: {color};
                           border-radius: 18px; border: none;
                           color: white; font-weight: 750; font-size: 18px;
                       }}"""
            return """QPushButton {
                       background-color: #E8ECF0;
                       border-radius: 18px;
                       border: 1.5px solid #C8D0D8;
                       color: #708090; font-weight: 700; font-size: 16px;
                   }
                   QPushButton:hover { background-color: #D8E0E8; }"""

        # 3 nút: GIẢM CÂN / DUY TRÌ / TĂNG CÂN — đều dùng màu cam khi selected
        # Rộng mỗi nút: 120px, cao 40px, cách nhau 8px
        # Tổng chiều ngang: 16 + (110+8)×3 - 8 = 362px (nằm trong giới hạn cột trái 360px)
        # GOAL_Y=280: input_height/weight kết thúc y=200+44=244, cách 36px → 280
        GOAL_W, GOAL_H = 117, 40
        GOAL_Y = 280

        self.btn_lose = QPushButton("GIẢM CÂN", right)
        self.btn_maintain = QPushButton("DUY TRÌ", right)
        self.btn_gain = QPushButton("TĂNG CÂN", right)

        goals = [
            (self.btn_lose, "#FF7043", 16),
            (self.btn_maintain, "#FF7043", 16 + GOAL_W + 7),
            (self.btn_gain, "#FF7043", 16 + (GOAL_W + 7) * 2),
        ]

        for btn, color, x in goals:
            btn.setGeometry(x, GOAL_Y, GOAL_W, GOAL_H)
            btn.setCheckable(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setFont(f_lbl2)

        # Mặc định: GIẢM CÂN được chọn
        self.btn_lose.setChecked(True)

        def _update_goal(selected_btn, color):
            for btn, c, _ in goals:
                btn.setStyleSheet(_goal_style(c, btn is selected_btn))
                btn.setChecked(btn is selected_btn)

        # Khởi tạo style ban đầu
        _update_goal(self.btn_lose, "#FF7043")

        self.btn_lose.clicked.connect(lambda: _update_goal(self.btn_lose, "#FF7043"))
        self.btn_maintain.clicked.connect(lambda: _update_goal(self.btn_maintain, "#78909C"))
        self.btn_gain.clicked.connect(lambda: _update_goal(self.btn_gain, "#66BB6A"))

        # -- [ROW 5] MỨC ĐỘ VẬN ĐỘNG + NÚT LƯU ------------------------------------------------
        # TƯ DUY: Cột phải chia 2 vùng theo trục X:
        # - x=0→459: cột form (tuổi, giới tính, chiều cao, cân nặng, mục tiêu)
        # - x=460→934: cột vận động (5 nút xếp dọc liên tục)
        # Nút lưu nằm dưới cùng, full width — là điểm kết thúc hành trình nhập liệu

        ACT_X     = 430  # x bắt đầu cột vận động — ranh giới chia đôi khung right  # CHỈNH TẠI ĐÂY
        ACT_Y     = 114  # y bắt đầu — cùng hàng ROW 2 (tuổi/giới tính)             # CHỈNH TẠI ĐÂY (KHÔNG ĐỘNG)
        ACT_W     = 504  # rộng = 950(frame) - 430(ACT_X) - 16(margin phải)          # CHỈNH TẠI ĐÂY (KHÔNG ĐỘNG)
        BTN_ACT_H = 50   # cao mỗi nút — đủ chứa 2 dòng chữ (18px + 11px + padding) # CHỈNH TẠI ĐÂY
        GAP       = 6    # khoảng cách giữa các nút theo trục Y                      # CHỈNH TẠI ĐÂY

        # Label tiêu đề cột vận động — y=94 cùng hàng label TUỔI và GIỚI TÍNH
        # Dùng f_lbl2 (Bold 13px) đồng bộ toàn bộ label nhãn trong trang
        lbl_act = QLabel("🏃 MỨC ĐỘ VẬN ĐỘNG HÀNG TUẦN", right)
        lbl_act.setFont(f_lbl2)
        lbl_act.setStyleSheet("color: #3A4A5A; background: transparent; border: none;")
        lbl_act.move(ACT_X, 94)  # CHỈNH TẠI ĐÂY
        lbl_act.adjustSize()     # tự co theo chữ, không bị cắt

        # Dữ liệu 5 mức vận động dạng tuple (tên, mô tả, hệ_số_TDEE)
        # Hệ số TDEE (Total Daily Energy Expenditure) là nhân tố khoa học dinh dưỡng:
        # TDEE = BMR × hệ_số — càng vận động nhiều, cơ thể đốt calo càng cao
        acts = [
            ("Ít vận động", "Làm việc văn phòng", 1.2),
            ("Nhẹ nhàng",   "1-2 ngày/tuần",      1.375),
            ("Vừa phải",    "3-5 ngày/tuần",       1.55),
            ("Năng động",   "6-7 ngày/tuần",       1.725),
            ("Rất cao",     "Vận động viên",        1.9),
        ]
        self._activity_factors = {}  # dict {index → hệ_số} — _on_save dùng để tính TDEE
        self._act_buttons      = []  # list (btn, lbl_main, lbl_sub) — loop update style

        def _act_style(selected: bool) -> str:
            # TƯ DUY: stylesheet trả về dạng string → gán qua setStyleSheet()
            # selected=True : nền xanh lá #00C950, viền mint #00DD58 2px solid
            # selected=False: nền trắng thuần, viền xanh rêu nhạt rgba
            if selected:
                return """QPushButton {
                    background-color: #00C950;
                    border-radius: 12px;
                    border: 2px solid #00DD58;
                }"""
            return """QPushButton {
                background-color: white;
                border-radius: 12px;
                border: 1.5px solid rgba(0,77,77,0.15);
            }
            QPushButton:hover { background-color: #F0FFF8; }"""

        for i, (name, desc, factor) in enumerate(acts):
            # TƯ DUY: enumerate() cho index i → tính y tuyệt đối = ACT_Y + i*(H+GAP)
            # Mỗi vòng lặp tạo 1 nút + 2 QLabel con bên trong nút (parent=btn)
            # QLabel con dùng .move() tọa độ relative so với nút cha — không phải frame right

            btn   = QPushButton(right)
            btn_y = ACT_Y + i * (BTN_ACT_H + GAP)  # y tăng đều mỗi nút  # CHỈNH GAP TẠI ĐÂY
            btn.setGeometry(ACT_X, btn_y, ACT_W, BTN_ACT_H)
            btn.setCheckable(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet(_act_style(False))

            # Label chính — Roboto Bold 18px, đặt trong nút (parent=btn), tọa độ relative
            lbl_main = QLabel(name, btn)
            f_act_main = QFont("Roboto")
            f_act_main.setPixelSize(18)
            f_act_main.setWeight(QFont.Weight.Bold)
            lbl_main.setFont(f_act_main)
            lbl_main.setStyleSheet("background: transparent; border: none; color: #1A2A3A;")
            lbl_main.move(16, 8)   # padding trái 16px, cách top nút 8px
            lbl_main.adjustSize()

            # Label phụ — Roboto 11px, nằm dưới label chính 22px
            lbl_sub = QLabel(desc, btn)
            f_act_sub = QFont("Roboto")
            f_act_sub.setPixelSize(11)
            lbl_sub.setFont(f_act_sub)
            lbl_sub.setStyleSheet("background: transparent; border: none; color: #8A9BAC;")
            lbl_sub.move(16, 30)   # 8(top) + 18(font) ≈ 26, làm tròn 30px
            lbl_sub.adjustSize()

            self._activity_factors[i] = factor
            self._act_buttons.append((btn, lbl_main, lbl_sub))

        def _update_act(sel_idx: int):
            # TƯ DUY: loop toàn bộ nút, so sánh index → set style đúng/sai
            # Màu chữ cũng đổi: trắng khi ON (nền xanh), tối/xám khi OFF (nền trắng)
            for idx, (btn, lbl_m, lbl_s) in enumerate(self._act_buttons):
                selected = (idx == sel_idx)
                btn.setChecked(selected)
                btn.setStyleSheet(_act_style(selected))
                lbl_m.setStyleSheet(f"background: transparent; border: none; "
                                    f"color: {'white' if selected else '#1A2A3A'};")
                lbl_s.setStyleSheet(f"background: transparent; border: none; "
                                    f"color: {'rgba(255,255,255,0.8)' if selected else '#8A9BAC'};")

        _update_act(0)  # mặc định: "Ít vận động" (index 0) được chọn khi mở app

        # clicked.connect dùng lambda với idx=i để capture đúng giá trị i tại thời điểm loop
        # Nếu viết lambda: _update_act(i) mà không có idx=i → closure bug: tất cả dùng i cuối
        for i, (btn, _, __) in enumerate(self._act_buttons):
            btn.clicked.connect(lambda _, idx=i: _update_act(idx))

        # -- NÚT LƯU HỒ SƠ --------------------------------------------------------------------
        # TƯ DUY: SaveButton là local class override paintEvent để vẽ chữ thủ công
        # Lý do: Qt chỉ cho 1 setGraphicsEffect per widget → không stack shadow chữ + shadow nút
        # Giải pháp: shadow nút dùng setGraphicsEffect(sh_btn), shadow chữ vẽ bằng QPainter

        SAVE_Y = ACT_Y + 5 * (BTN_ACT_H + GAP) + 50  # dưới nút cuối + 50px margin  # CHỈNH TẠI ĐÂY

        class SaveButton(QPushButton):
            def paintEvent(self, event):
                super().paintEvent(event)  # Qt vẽ nền gradient + border trước
                p = QPainter(self)
                p.setRenderHint(QPainter.RenderHint.Antialiasing)
                p.setFont(self.font())
                rect = self.rect()
                text = self.text()
                # Outline 2px: vẽ chữ màu tối lệch 8 hướng 2px → tạo viền đều quanh chữ
                p.setPen(QColor(0, 80, 30, 200))
                for dx, dy in [(-2,0),(2,0),(0,-2),(0,2),(-2,-2),(2,-2),(-2,2),(2,2)]:
                    p.drawText(rect.translated(dx, dy), Qt.AlignmentFlag.AlignCenter, text)
                # Chữ thật trắng vẽ đè lên cùng — luôn nằm trên cùng
                p.setPen(QColor("white"))
                p.drawText(rect, Qt.AlignmentFlag.AlignCenter, text)

        self.btn_save = SaveButton("Lưu hồ sơ & Bắt đầu tính toán", right)
        self.btn_save.setGeometry(16, SAVE_Y, 918, 52)  # full width khung, cao 52px  # CHỈNH TẠI ĐÂY
        self.btn_save.setCursor(Qt.CursorShape.PointingHandCursor)

        f_save = QFont("Roboto")
        f_save.setPixelSize(20)
        f_save.setWeight(QFont.Weight.Black)                                  # weight 900
        f_save.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 3)        # expand chữ 3px
        self.btn_save.setFont(f_save)

        self.btn_save.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0.0 #3EE28C,
                    stop:0.7 #3BD585,
                    stop:1.0 #2B9E61);
                border-radius: 26px;
                border: 3px solid #00E676;
                color: transparent;
            }
            QPushButton:hover   { background: #3EE28C; }
            QPushButton:pressed { background: #2B9E61; }
        """)

        # Shadow nút: offset(0,2) = 90° xuống, blur=8 → phát sáng xanh lá dưới nút
        sh_btn = QGraphicsDropShadowEffect()
        sh_btn.setBlurRadius(8)
        sh_btn.setOffset(0, 2)
        sh_btn.setColor(QColor(0, 180, 80, 140))
        self.btn_save.setGraphicsEffect(sh_btn)  # chỉ 1 effect — sh_txt đã bỏ

        self.btn_save.clicked.connect(self._on_save)

        parent_lay.addWidget(right, 1)

    # ============================================================
    # PATCH page_user.py — OAuth không cần client_secrets.json
    # ============================================================
    # [UPDATE v1.6] — 02/06/2026 — Tài · Tuấn · Vanh
    #
    # VẤN ĐỀ CŨ:
    #   - Cần file client_secrets.json + thư viện google-auth-oauthlib
    #   - Thiếu 1 trong 2 → fallback ngay, không hiện Google sign-in
    #
    # CHIẾN THUẬT MỚI:
    #   - Build OAuth URL thủ công bằng requests thuần
    #   - Chỉ cần GOOGLE_CLIENT_ID + GOOGLE_CLIENT_SECRET trong .env
    #   - Mở full browser (Google chặn embedded webview từ 2019)
    #   - Local HTTP server bắt redirect như cũ (đã hoạt động tốt)
    #
    # HƯỚNG DẪN:
    #   1. Thêm vào file .env:
    #        GOOGLE_CLIENT_ID=xxx.apps.googleusercontent.com
    #        GOOGLE_CLIENT_SECRET=GOCSPX-xxx
    #
    #   2. Trong Google Cloud Console:
    #        Credentials → OAuth Client ID → Desktop app
    #        Authorized redirect URIs: http://localhost:8765/oauth2callback
    #
    #   3. Thay toàn bộ phần IMPORT OAuth (dòng 20-45) trong page_user.py
    #      bằng block import bên dưới
    #
    #   4. Thay hàm _on_google_login bằng hàm mới bên dưới
    # ============================================================
    def _on_google_login(self):
        """
        Mở full browser → Google Consent → redirect về localhost:8765 →
        exchange code → lấy userinfo → upsert DB → cập nhật UI.

        [v1.6] Không cần client_secrets.json — dùng CLIENT_ID từ .env
        Full browser bắt buộc: Google chặn embedded webview từ 2019.
        """
        from fooder_logger import flog

        if not _GAUTH_OK:
            missing = []
            if not _GOOGLE_CLIENT_ID:     missing.append("GOOGLE_CLIENT_ID")
            if not _GOOGLE_CLIENT_SECRET: missing.append("GOOGLE_CLIENT_SECRET")
            if not _REQUESTS_OK:          missing.append("thư viện requests")
            flog("AUTH", f"⚠️ Thiếu: {', '.join(missing)} → fallback", level="WARN")
            self._fallback_manual_login()
            return

        self.btn_google.setEnabled(False)
        self.btn_google.setText("  Đang mở trình duyệt…")
        flog("AUTH", "🔄 Bắt đầu Google OAuth flow...")

        def _run_oauth():
            try:
                import urllib.parse
                import secrets

                # ── Bước 1: Build OAuth URL thủ công ────────────────────────
                state = secrets.token_urlsafe(16)  # chống CSRF
                params = {
                    "client_id": _GOOGLE_CLIENT_ID,
                    "redirect_uri": _REDIRECT_URI,
                    "response_type": "code",
                    "scope": "openid email profile",
                    "access_type": "offline",
                    "prompt": "consent",
                    "state": state,
                }
                auth_url = "https://accounts.google.com/o/oauth2/v2/auth?" + \
                           urllib.parse.urlencode(params)

                # ── Bước 2: Mở full browser ──────────────────────────────────
                import webbrowser
                webbrowser.open(auth_url)
                flog("AUTH", f"🌐 Đã mở browser: {auth_url[:60]}...")

                # ── Bước 3: Local server bắt redirect ───────────────────────
                import http.server
                _OAuthCallbackHandler.auth_code = None
                server = http.server.HTTPServer(
                    ("localhost", _REDIRECT_PORT), _OAuthCallbackHandler
                )
                server.timeout = 120
                server.handle_request()

                code = _OAuthCallbackHandler.auth_code
                if not code:
                    flog("AUTH", "❌ Không nhận được code từ Google", level="ERROR")
                    self._oauth_signals.login_failed.emit(
                        "Không nhận được mã xác thực từ Google.\n"
                        "Kiểm tra lại trình duyệt hoặc thử lại."
                    )
                    return

                flog("AUTH", "✅ Nhận được auth code — đang exchange token...")

                # ── Bước 4: Exchange code → access token ────────────────────
                token_resp = _requests.post(
                    "https://oauth2.googleapis.com/token",
                    data={
                        "code": code,
                        "client_id": _GOOGLE_CLIENT_ID,
                        "client_secret": _GOOGLE_CLIENT_SECRET,
                        "redirect_uri": _REDIRECT_URI,
                        "grant_type": "authorization_code",
                    },
                    timeout=15,
                )
                token_data = token_resp.json()

                if "error" in token_data:
                    err = token_data.get("error_description", token_data["error"])
                    flog("AUTH", f"❌ Token exchange lỗi: {err}", level="ERROR")
                    self._oauth_signals.login_failed.emit(f"Lỗi token: {err}")
                    return

                access_token = token_data.get("access_token", "")
                flog("AUTH", "✅ Exchange token thành công")

                # ── Bước 5: Lấy thông tin user ──────────────────────────────
                user_resp = _requests.get(
                    "https://www.googleapis.com/oauth2/v2/userinfo",
                    headers={"Authorization": f"Bearer {access_token}"},
                    timeout=10,
                )
                info = user_resp.json()

                uid = info.get("id", "")
                email = info.get("email", "")
                name = info.get("name", email.split("@")[0])
                photo_url = info.get("picture", "")

                flog("AUTH", f"✅ Đăng nhập thành công: {name} ({email})")
                self._oauth_signals.login_success.emit(uid, email, name, photo_url)

            except Exception as e:
                flog("AUTH", f"❌ OAuth lỗi: {e}", level="ERROR")
                self._oauth_signals.login_failed.emit(str(e))

        threading.Thread(target=_run_oauth, daemon=True).start()

    def _fallback_manual_login(self):
        """
        Khi chưa cài OAuth lib → vẫn cho nhập tên tay để dùng Lưu hồ sơ.
        uid giả = 'local_' + tên máy (không lưu DB nhưng UI vẫn hoạt động).
        """
        import socket
        fake_uid   = f"local_{socket.gethostname()}"
        fake_email = "local@fooderai.app"
        fake_name  = "Người dùng cục bộ"
        self._apply_login(fake_uid, fake_email, fake_name, "")

    def _apply_login(self, uid: str, email: str, name: str, photo_url: str):
        """
        Chạy trên Qt main thread (emit từ signal).
        Cập nhật UI + upsert DB.
        """
        import traceback
        self._uid = uid

        # Cập nhật hiển thị lên giao diện UI trước
        self.input_name.setText(name)
        if hasattr(self, 'username_changed'):
            self.username_changed.emit(name)

        # ── Upsert DB ──────────────────────────────────────────────
        if _DB_OK:
            try:
                print(f"[DB] Đang đồng bộ tài khoản: {name} vào SQL Server...")

                # SỬA TẠI ĐÂY: Hứng cái kết quả SỐ NGUYÊN từ hàm upsert_user trả về
                self._user_id = upsert_user(uid, name, email, photo_url, None)

                # Tải lại dữ liệu cũ nếu đã có hồ sơ trong DB
                if self._user_id is not None:
                    self._load_saved_profile()
                    print("[DB] Đồng bộ và tải profile thành công!")
                else:
                    print("❌ [DB] Lỗi không lấy được user_id số nguyên từ DB.")

            except Exception as e:
                print("\n" + "!" * 40)
                print("❌❌❌ PHÁT HIỆN LỖI CHÍ MẠNG TẠI HÀM _apply_login:")
                traceback.print_exc()
                print("!" * 40 + "\n")



        # ── Cập nhật UI cột trái ───────────────────────────────────
        self.lbl_name.setText(name)
        self.lbl_email.setText(email)
        self.btn_google.setVisible(False)
        self.btn_logout.setVisible(True)

        # Avatar từ URL (download async)
        if photo_url:
            threading.Thread(
                target=self._load_avatar_url,
                args=(photo_url,),
                daemon=True,
            ).start()

        # Mở khóa ô tên
        self.input_name.setEnabled(True)
        self.input_name.setText(name)
        self.input_name.setStyleSheet("""
            QLineEdit {
                background-color: white; color: #1A2A3A;
                border-radius: 22px; border: 1.5px solid rgba(0,77,77,0.25);
                padding: 0 18px;
            }
            QLineEdit:focus { border: 1.5px solid #3EE28C; }
        """)

    def _load_saved_profile(self):
        """Tải lại hồ sơ đã lưu từ DB để điền sẵn vào form."""
        if not _DB_OK or not self._uid:
            return
        try:
            row = get_user_by_uid(self._uid)
            if not row:
                return
            # Điền form từ DB (bỏ qua None)
            if row.get("age"):
                self.input_age.setText(str(row["age"]))
            if row.get("height_cm"):
                self.input_height.setText(str(int(row["height_cm"])))
            if row.get("weight_kg"):
                self.input_weight.setText(str(int(row["weight_kg"])))
            # Giới tính
            if row.get("gender") == "female":
                self.btn_female.setChecked(True)
                self.btn_female.click()
            # Mục tiêu
            goal_map = {"lose": self.btn_lose, "maintain": self.btn_maintain, "gain": self.btn_gain}
            if row.get("goal") in goal_map:
                goal_map[row["goal"]].click()
        except Exception as e:
            print(f"[DB] load profile lỗi: {e}")

    def _load_avatar_url(self, url: str):
        """Download ảnh avatar từ URL và cập nhật widget (chạy trong thread)."""
        try:
            import urllib.request
            from io import BytesIO
            with urllib.request.urlopen(url, timeout=8) as resp:
                data = resp.read()
            pix = QPixmap()
            pix.loadFromData(data)
            if not pix.isNull():
                self.avatar.set_pixmap(pix)
        except Exception:
            pass

    def _on_login_error(self, msg: str):
        self.btn_google.setEnabled(True)
        self.btn_google.setText("  Đăng nhập với Google")
        QMessageBox.warning(self, "Đăng nhập thất bại", f"Lỗi OAuth:\n{msg}")

    def _on_logout(self):
        self._user_id = None
        self._uid     = None
        self.avatar.reset_default()
        self.lbl_name.setText("Chưa đăng nhập")
        self.lbl_email.setText("–")
        self.btn_google.setVisible(True)
        self.btn_google.setEnabled(True)
        self.btn_google.setText("  Đăng nhập với Google")
        self.btn_logout.setVisible(False)
        # Khóa lại ô tên
        self.input_name.setEnabled(False)
        self.input_name.clear()
        self.input_name.setStyleSheet("""
            QLineEdit {
                background-color: #F0F4F8; color: #8A9BAC;
                border-radius: 22px; border: 1.5px solid #C8D0D8;
                padding: 0 18px;
            }
        """)
        # Ẩn panel kết quả nếu đang hiển thị
        if hasattr(self, "_result_panel") and self._result_panel:
            self._result_panel.setVisible(False)

    # ================================================================
    # LƯU HỒ SƠ — tính BMI / BMR / TDEE → lưu DB → hiển thị kết quả
    # ================================================================
    def _on_save(self):
        # ── 1. Validate dữ liệu đầu vào (Giữ nguyên) ──────────────────────────────
        errors = []
        try:
            age = int(self.input_age.text())
            assert 5 <= age <= 120
        except Exception:
            errors.append("• Tuổi không hợp lệ (5 – 120).")

        try:
            height = float(self.input_height.text())
            assert 50 <= height <= 250
        except Exception:
            errors.append("• Chiều cao không hợp lệ (50 – 250 cm).")

        try:
            weight = float(self.input_weight.text())
            assert 10 <= weight <= 400
        except Exception:
            errors.append("• Cân nặng không hợp lệ (10 – 400 kg).")

        if errors:
            QMessageBox.warning(self, "Thiếu thông tin",
                                "Vui lòng sửa lại:\n" + "\n".join(errors))
            return

        # ── 2. Đọc giới tính & mục tiêu ───────────────────────────────
        gender = "female" if self.btn_female.isChecked() else "male"
        if self.btn_maintain.isChecked():
            goal = "maintain"
        elif self.btn_gain.isChecked():
            goal = "gain"
        else:
            goal = "lose"

        # ── 3. Đọc hệ số vận động ─────────────────────────────────────
        act_idx = next((i for i, (btn, _, __) in enumerate(self._act_buttons)
                        if btn.isChecked()), 0)
        act_factor = self._activity_factors.get(act_idx, 1.2)

        # =========================================================================
        # 4. TRUYỀN DỮ LIỆU QUA PHÂN XƯỞNG LOGIC (BACK-END) ĐỂ TÍNH TOÁN
        # =========================================================================
        bmi = NutritionLogic.calculate_bmi(weight, height)
        bmr = NutritionLogic.calculate_bmr(weight, height, age, gender)
        tdee = NutritionLogic.calculate_tdee(bmr, act_factor)

        goal_kcal, _ = self._calc_goal_kcal(tdee, goal)

        # ── 5. Lưu DB ─────────────────────────────────────────────────
        if _DB_OK and self._user_id:
            try:
                update_user_profile(
                    user_id=self._user_id,
                    age=age,
                    gender=gender,
                    height_cm=height,
                    weight_kg=weight,
                    goal=goal,
                    activity_level=act_factor,
                    bmi=round(bmi, 2),
                    bmr=int(bmr),
                    tdee=int(tdee),
                )
                print(f"[DB] update_user_profile OK — BMI={bmi:.1f} BMR={int(bmr)} TDEE={int(tdee)}")
            except Exception as e:
                print(f"[DB] update_user_profile lỗi: {e}")

        # =========================================================================
        # 6. PHÁT TÍN HIỆU ĐỂ CẬP NHẬT 4 Ô WIDGET & TIÊU ĐỀ TRÊN DASHBOARD
        # =========================================================================
        self.stats_saved.emit(float(bmi), int(bmr), int(tdee), int(goal_kcal))

        user_name = self.input_name.text().strip()
        if not user_name:
            user_name = "Người dùng"
        self.username_changed.emit(user_name)

        # ── 7. ẨN BẢNG KẾT QUẢ CŨ NẾU CÓ ───────────────────────────
        if hasattr(self, "_result_panel") and self._result_panel is not None:
            self._result_panel.setVisible(False)

    @staticmethod
    def _classify_bmi(bmi: float) -> tuple[str, str]:
        """Phân loại BMI theo WHO, trả về (nhãn, màu hex)."""
        if bmi < 18.5:
            return "⚠ Thiếu cân", "#FF9800"
        elif bmi < 25.0:
            return "✓ Bình thường", "#3EE28C"
        elif bmi < 30.0:
            return "⚠ Thừa cân", "#FF9800"
        else:
            return "⚠ Béo phì", "#F44336"

    @staticmethod
    def _calc_goal_kcal(tdee: int, goal: str) -> tuple[int, str]:
        """Tính calo mục tiêu dựa trên TDEE và goal."""
        if goal == "lose":
            return int(tdee - 500), "Giảm 0.5 kg/tuần"
        elif goal == "gain":
            return int(tdee + 500), "Tăng 0.5 kg/tuần"
        else:
            return tdee, "Duy trì cân nặng"