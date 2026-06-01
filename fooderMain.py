import sys
import os

# HÀM CẤP CỨU - DÙNG CHUNG TOÀN APP
def resource_path(relative_path):
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.abspath("."), relative_path)

# --- PHẦN GIẢI THÍCH CHI TIẾT CÁC LINH KIỆN (BỘ PHẬN MÁY) ---
"""
1. PySide6.QtWidgets (Bộ khung xương và Nội thất):
   - QMainWindow: Cung cấp 'Nền nhà' chính. Đây là cái khung lớn nhất chứa toàn bộ app. [cite: 1302]
   - QApplication: Là 'Nguồn điện'. Mọi dòng code giao diện đều cần nó để khởi động. [cite: 1303]
   - QWidget: Là 'Viên gạch'. Đây là đơn vị cơ bản để tạo ra các vùng chứa. [cite: 1303]
   - QLabel: Là 'Khung tranh'. Công dụng chính là để dán các file ảnh hoặc hiển thị văn bản. [cite: 1303]
   - QPushButton: Là 'Cái nút'. Linh kiện này dùng để nhận lệnh click từ người dùng. [cite: 1304]
   - QStackedWidget: Là 'Máy chiếu'. Dùng để quản lý và chuyển đổi các trang chức năng. [cite: 1598]
   - QFrame: 'Tấm ván' dùng để xây dựng các lớp nền hoặc bệ đỡ có bo góc. [cite: 1686]

2. PySide6.QtGui (Sơn, Phông bạt và Cảm biến):
   - QPixmap: Công cụ nạp và xử lý hình ảnh PNG/JPG từ thư mục assets. [cite: 1304]
   - QMouseEvent: Lớp quản lý các sự kiện di chuyển chuột để thực hiện kéo app. [cite: 1305]
   - QIcon: Dùng để đưa các hình ảnh nhỏ xíu vào trong các nút bấm. [cite: 1306]

3. PySide6.QtCore (Bộ não và Quy tắc vật lý):
   - Qt: Chứa các quy tắc hệ thống và hằng số điều khiển (như căn lề, loại cửa sổ). [cite: 1308]
   - QPoint: Quản lý tọa độ (X, Y) của app trên màn hình máy tính. [cite: 1309]
   - QSize: Quản lý thông số về chiều Rộng và chiều Cao của linh kiện. [cite: 1310]
"""

from PySide6.QtWidgets import QApplication, QMainWindow, QWidget, QLabel, QPushButton, QHBoxLayout, QStackedWidget, \
     QFrame
from PySide6.QtGui import QPixmap, QMouseEvent, QIcon, QFontDatabase, QFont
from PySide6.QtCore import Qt, QPoint, QSize

# NHẬP KHẨU TỪ CÁC PHÂN XƯỞNG KHÁC (GIỮ NGUYÊN - CẤM ĐỤNG)
from fooder_widgetUI import DashboardOverview, ModeNavBar

# [MỚI] Import các Class trang từ package 'pages'
from pages.page_ai import PageAIAssistant
from pages.page_scan import PageFoodScanner
from pages.page_almanac import PageFoodAlmanac
from pages.page_gym import PageExercise
from pages.page_user import PageUserProfile
from pages.page_version_info import InfoButton, PageVersionInfo


# --- MẠCH NẠP PHÔNG CHỮ QUỐC TẾ HÓA (BẢN ĐỦ) ---
def load_fonts():
     """
     HÀM NẠP PHÔNG CHỮ: Đăng ký các file .ttf vào hệ thống để app hiển thị đúng font Roboto[cite: 1352].
     """
     font_dir = resource_path(os.path.join("assets", "fooderai-fonts"))
     font_files = ["Roboto-Regular.ttf", "Roboto-Medium.ttf", "Roboto-Bold.ttf",
                   "Roboto-Light.ttf", "Roboto_SemiCondensed-Light.ttf",
                   "Roboto_SemiCondensed-Medium.ttf", "Roboto_SemiCondensed-Regular.ttf",
                   "Orbitron-Bold.ttf", "Orbitron-Medium.ttf", "Orbitron-Regular.ttf"]
     for f in font_files:
          path = os.path.join(font_dir, f)
          if os.path.exists(path):
               font_id = QFontDatabase.addApplicationFont(path)
               print(f"[OK] Nạp thành công: {QFontDatabase.applicationFontFamilies(font_id)}")
          else:
               print(f"[LỖI] Không tìm thấy file tại: {path}")


"""
PHÂN XƯỞNG 1: LỚP CUSTOMBUTTON (Nút bấm thông minh)
"""
class CustomButton(QPushButton):
     def __init__(self, normal_img, hover_img, parent=None):
          super().__init__(parent)
          self.normal_icon = QIcon(normal_img)
          self.hover_icon = QIcon(hover_img)

          # --- THIẾT LẬP THÔNG SỐ VẬT LÝ CHO NÚT ---
          self.setFixedSize(62, 38)
          self.setIcon(self.normal_icon)
          self.setIconSize(QSize(62, 38))
          self.setStyleSheet("background: transparent; border: none;")

     def enterEvent(self, event):
          """ Hiệu ứng chuột 'bước vào': Đổi sang ảnh phát sáng (triggered)[cite: 1030]. """
          self.setIcon(self.hover_icon)

     def leaveEvent(self, event):
          """ Hiệu ứng chuột 'rời đi': Trả lại ảnh bình thường. """
          self.setIcon(self.normal_icon)


"""
PHÂN XƯỞNG 2: LỚP CHÍNH (FooderAI)
Nhiệm vụ: Lắp ghép Thanh Active Bar, Bệ đỡ và Nền Canvas thành một khối khít lịm[cite: 1313].
"""


class FooderAI(QMainWindow):
     def __init__(self):
          super().__init__()

          # Đảm bảo hàm nạp font chạy ngay khi mở App
          load_fonts()

          # --- CẤU HÌNH KHUNG XƯƠNG CỬA SỔ ---
          self.setWindowFlags(Qt.WindowType.FramelessWindowHint)  # Xóa khung Windows mặc định [cite: 991]
          self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)  # Cho phép bo góc trong suốt [cite: 1007]
          """
          [BUG — fooderMain.py] DPI SCALING MISMATCH — Feedback: Nguyên Việt Anh (25AI002)
          Máy Tài (25AI045) chạy Windows Display Scale 125%/150% → setFixedSize(1600, 1025)
          bị nhân vật lý lên 1.25x = 2000px → cửa sổ tràn màn hình, mất thanh input + nút gửi.
          FIX (260527): Dùng availableGeometry() để đọc kích thước màn hình THỰC TẾ sau khi
          Qt đã áp dụng DPI scale, rồi min() giới hạn tối đa 1600×1025 — máy to vẫn đủ,
          máy nhỏ/scale cao tự co lại vừa vặn, không bao giờ tràn ra ngoài màn hình nữa.
          """
          screen = QApplication.primaryScreen().availableGeometry()
          win_w  = min(1600, screen.width())
          win_h  = min(1025, screen.height())
          self.setFixedSize(win_w, win_h)

          self.central_widget = QWidget(self)
          self.setCentralWidget(self.central_widget)

          # --- BỘ PHẬN 1: THANH ACTIVE BAR (VÔ LĂNG) ---
          self.active_bar = QLabel(self.central_widget)
          self.active_bar.setGeometry(0, 0, 1600, 58)  # Nằm ở tọa độ y=0, cao 58px [cite: 1744]
          path_bar = resource_path(os.path.join("assets", "fooderai-bar", "fooder_ai_win_activebar.png")) #<=UPDATE
          self.active_bar.setPixmap(QPixmap(path_bar).scaled(1600, 58, Qt.AspectRatioMode.IgnoreAspectRatio,
                                                             Qt.TransformationMode.SmoothTransformation))

          # --- BỘ PHẬN 2: BỆ ĐỠ XÁM (BASE PEDESTAL) ---
          """ 
          TOÁN HỌC KHU VỰC BASE (BỆ ĐỠ):
          Lớp này không tính từ Window Bar, mà bắt đầu ngay dưới Bar (Y=58).
          Nó phủ kín phần còn lại của cửa sổ: 985 - 58 = 927px.
          """
          self.bg_base = QFrame(self.central_widget)
          self.bg_base.setGeometry(0, 57, 1600, 900)  # Chốt tọa độ y=58
          self.bg_base.setStyleSheet("""
               QFrame {
                    background-color: rgb(210, 215, 218); 
                    border-bottom-left-radius: 20px;     /* Bo góc chỉ ở đáy để hít chặt vào Bar */
                    border-bottom-right-radius: 20px;
                    border: 1px solid rgba(0, 0, 0, 40);
               }
          """)

          # --- [BƯỚC 3]: BỆ ĐỠ XÁM (PHẲNG 100% - KHÔNG CONG) ---
          """ 
          TOÁN HỌC BỆ ĐỠ:
          Bắt đầu tại Y=58. Cao = 1023 - 58 = 965px. 
          Lưu ý: Đã xóa border-radius để nó là hình chữ nhật phẳng đúng ý em.
          """
          self.bg_base = QFrame(self.central_widget)
          self.bg_base.setGeometry(0, 58, 1600, 965)
          self.bg_base.setStyleSheet("""
                         QFrame {
                              background-color: rgb(210, 215, 218); 
                              border: 1px solid rgba(0, 0, 0, 40);
                              border-radius: 0px; /* ÉP PHẲNG LỲ */
                         }
                    """)

          # --- [BƯỚC 4]: CANVAS NỀN (GIỮ NGUYÊN 1600x960 - KHÔNG CROP) ---
          """
          CƠ CHẾ GIỮ NGUYÊN GỐC:
          Canvas bắt đầu tại Y=58 và cao đúng 960px theo kịch bản PowerPoint.
          Điểm kết thúc: 58 + 960 = 1018px. 
          Vì cửa sổ cao 1023px, em sẽ thấy đúng 5px gầm xám ở dưới cùng[cite: 1747, 1806].
          """
          self.canvas = QLabel(self.central_widget)
          self.canvas.setGeometry(0, 57, 1600, 960)
          path_bg  = resource_path(os.path.join("assets", "fooderai-background", "fooderaibg", "fooder_bg.PNG")) #<= UPDATE
          if os.path.exists(path_bg):
               self.canvas.setPixmap(QPixmap(path_bg).scaled(1600, 960, Qt.AspectRatioMode.IgnoreAspectRatio,
                                                             Qt.TransformationMode.SmoothTransformation))

          # XẾP LỚP: Táo nằm trên bệ đỡ, Bar nằm trên cùng
          self.canvas.raise_()
          self.active_bar.raise_()

          # --- BỘ PHẬN 5: HỆ THỐNG NÚT BẤM (MARGIN 30 DỌC) ---
          btn_path = resource_path(os.path.join("assets", "fooderai-interact-button")) #<=UPDATE

          self.btn_close = CustomButton(
               os.path.join(btn_path, "fooder_ai_closebutton.png"),
               os.path.join(btn_path, "fooder_ai_closebutton_triggered.png"),
               self.active_bar
          )
          self.btn_close.move(1530, 10)  # Nằm gọn trong Bar cao 48px
          self.btn_close.clicked.connect(self.close)

          self.btn_min = CustomButton(
               os.path.join(btn_path, "fooder_ai_minimize_button.png"),
               os.path.join(btn_path, "fooder_ai_minimize_button_triggered.png"),
               self.active_bar
          )
          self.btn_min.move(1468, 10)
          self.btn_min.clicked.connect(self.showMinimized)

          # --- BỘ PHẬN 5: BỘ MÁY CHUYỂN CẢNH VÀ DASHBOARD ---
          self.screen_manager = QStackedWidget(self.central_widget)
          self.screen_manager.setGeometry(0, 45, 1600, 900)
          self.view_dashboard = DashboardOverview("")
          self.screen_manager.addWidget(self.view_dashboard)

          # --- BỘ PHẬN 6: THANH MENU ĐIỀU HƯỚNG VIÊN NHỘNG ---
          self.nav_bar = ModeNavBar(self.central_widget)
          self.nav_bar.move(180, 295)  # Vị trí cân đối dưới StatCard

          # --- BỘ PHẬN 7: MÁY CHIẾU TRANG NỘI DUNG (CONTENT STACK) ---
          self.feature_stack = QStackedWidget(self.central_widget)
          self.feature_stack.setFixedSize(1240, 640) # <=== SỬA CONTENT TẠI ĐÂY
          self.feature_stack.move(180, 365)  # Kết thúc tại 977, vẫn nằm trên bệ đỡ 5px

          # Khởi tạo và nạp 5 trang chức năng
          self.page_ai = PageAIAssistant()
          self.page_scan = PageFoodScanner()
          self.page_almanac = PageFoodAlmanac()
          self.page_gym = PageExercise()
          self.page_user = PageUserProfile()

          self.feature_stack.addWidget(self.page_ai)  # Index 0
          self.feature_stack.addWidget(self.page_scan)  # Index 1
          self.feature_stack.addWidget(self.page_almanac)  # Index 2
          self.feature_stack.addWidget(self.page_gym)  # Index 3
          self.feature_stack.addWidget(self.page_user)  # Index 4

          # ── [MỚI] Trang Version Info ──────────────────────────────
          self.page_version_info = PageVersionInfo()
          self.feature_stack.addWidget(self.page_version_info)  # Index 5

          # ── [MỚI] Nút ⓘ — bên phải ModeNavBar ───────────────────
          self.btn_info = InfoButton(self.central_widget)
          self.btn_info.move(1432, 295) #chỉnh sửa tọa độ tại đây
          self.btn_info.raise_()

          self.connect_nav_buttons()  # ← dòng này giữ nguyên

          self.btn_info.clicked.connect(
               lambda: self.feature_stack.setCurrentIndex(5)
          )

          self.feature_stack.show()


          self.connect_nav_buttons()
          self.feature_stack.show()

     def connect_nav_buttons(self):
          for index, btn in enumerate(self.nav_bar.modes):
               btn.mousePressEvent = lambda event, i=index: self.switch_feature_page(i)

     def switch_feature_page(self, index):
          self.feature_stack.setCurrentIndex(index)
          self.nav_bar.select_mode(self.nav_bar.modes[index])

     # --- ĐỘNG CƠ KÉO THẢ APP (DRAG ENGINE) ---
     def mousePressEvent(self, event: QMouseEvent):
          # Chỉ cho phép kéo app khi click vào thanh Active Bar (y < 58)
          if event.button() == Qt.MouseButton.LeftButton and event.position().y() < 58:
               self.old_pos = event.globalPosition().toPoint()

     def mouseMoveEvent(self, event: QMouseEvent):
          if hasattr(self, 'old_pos') and self.old_pos is not None:
               delta = QPoint(event.globalPosition().toPoint() - self.old_pos)
               self.move(self.x() + delta.x(), self.y() + delta.y())
               self.old_pos = event.globalPosition().toPoint()

     def mouseReleaseEvent(self, event: QMouseEvent):
          self.old_pos = None


if __name__ == "__main__":
     """
     [BUG — fooderMain.py] HIGH DPI AWARENESS MISSING — Feedback: Nguyên Việt Anh (25AI002)
     Thiếu khai báo DPI policy trước khi tạo QApplication khiến Qt dùng chế độ scale mặc định
     → trên máy Tài (Windows 125%) toàn bộ widget bị phóng to vật lý, tràn ra ngoài viewport.
     FIX (260527): Set 2 env var TRƯỚC khi QApplication() khởi tạo — Qt đọc biến này ở giai
     đoạn boot, nếu set sau thì không có hiệu lực. PassThrough = giữ nguyên tỉ lệ thực, không
     làm tròn lên/xuống → widget render đúng pixel trên mọi mức scale (100%, 125%, 150%, 200%).
     """
     os.environ["QT_ENABLE_HIGHDPI_SCALING"]       = "1"
     os.environ["QT_SCALE_FACTOR_ROUNDING_POLICY"] = "PassThrough"

     app = QApplication(sys.argv)
     app.setHighDpiScaleFactorRoundingPolicy(
          Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
          # PassThrough: Qt KHÔNG làm tròn hệ số scale (ví dụ: 1.25 giữ nguyên 1.25)
          # Nếu dùng Round (mặc định): 1.25 → 1.0 hoặc 2.0 → layout sai lệch hoàn toàn
     )

     window = FooderAI()
     window.show()
     sys.exit(app.exec())