import os
import sys  # [FIX - 21:12] Thiếu import sys → resource_path() crash ngay khi gọi hasattr(sys, ...)
from PySide6.QtWidgets import QFrame, QVBoxLayout, QLabel, QGraphicsDropShadowEffect, QWidget, QHBoxLayout
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QColor, QPixmap

"""
[HÀM CẤP CỨU] resource_path - Giải quyết bài toán đường dẫn 2 môi trường
──────────────────────────────────────────────────────────────────────────
Vấn đề cốt lõi:
  - Khi chạy .py bình thường: assets/ nằm cạnh file .py → os.path hoạt động bình thường.
  - Khi PyInstaller đóng gói thành .exe: toàn bộ assets bị giải nén vào thư mục
    tạm sys._MEIPASS (ví dụ: C:/Users/.../AppData/Local/Temp/_MEI1234/).
    Lúc này os.path.join("assets", ...) trỏ sai chỗ → không tìm thấy file → mất ảnh.

Cách sửa:
  - Kiểm tra hasattr(sys, '_MEIPASS'): nếu True tức đang chạy từ .exe đã đóng gói
    → dùng sys._MEIPASS làm gốc.
  - Nếu False tức đang chạy .py thường → dùng thư mục hiện tại làm gốc.

Cách dùng: thay os.path.join("assets", ...) bằng resource_path(os.path.join("assets", ...))
"""
def resource_path(relative_path):
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, relative_path)
    # [FIX] Dùng __file__ thay abspath(".") → luôn trỏ đúng thư mục chứa file .py
    base = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, relative_path)

# =====================================================================
# LỚP 1: STATCARD (CHỈ CHỨA LOGIC CỦA 4 CÁI HỘP BMI, BMR...)
# =====================================================================
class StatCard(QFrame):
     def __init__(self, title, sub_text, color_hex, parent=None):
          super().__init__(parent)
          self.setFixedSize(270, 140)

          base_color = QColor(color_hex)
          color_70 = base_color.darker(112).name()
          color_100 = base_color.darker(125).name()

          self.setStyleSheet(f"""
            QFrame {{
                background-color: qlineargradient(x1:0, y1:0, x2:1, y2:1, 
                                  stop:0 {color_hex}, 
                                  stop:0.7 {color_70}, 
                                  stop:1.0 {color_100});
                border-radius: 24px;
                border: 1px solid rgba(255, 255, 255, 0.2);
            }}
            QLabel {{ border: none; background: transparent; }}
        """)

          self.box_shadow = QGraphicsDropShadowEffect()
          self.box_shadow.setBlurRadius(35)
          self.box_shadow.setOffset(0, 12)
          self.box_shadow.setColor(QColor(0, 0, 0, 180))
          self.setGraphicsEffect(self.box_shadow)

          layout = QVBoxLayout(self)
          layout.setContentsMargins(22, 18, 22, 18)

          #Tiêu đề ô
          self.lbl_title = QLabel(title)
          self.lbl_title.setFont(QFont("Roboto Condensed", 18, QFont.Weight.Medium))
          self.lbl_title.setStyleSheet("color: rgba(255, 255, 255, 0.9);")

          #Chỉ số ô
          self.lbl_value = QLabel("0.0")
          self.lbl_value.setFont(QFont("Roboto ExtraBold", 32))
          self.lbl_value.setStyleSheet("color: white;")

          text_shadow = QGraphicsDropShadowEffect()
          text_shadow.setBlurRadius(8)
          text_shadow.setOffset(2, 2)
          text_shadow.setColor(QColor(0, 0, 0, 200))
          self.lbl_value.setGraphicsEffect(text_shadow)

          #Thanh Chú Thích
          self.lbl_sub = QLabel(sub_text)
          self.lbl_sub.setFont(QFont("Roboto SemiCondensed Medium", 12))
          self.lbl_sub.setStyleSheet("color: rgba(255, 255, 255, 0.7);")

          layout.addWidget(self.lbl_title)
          layout.addWidget(self.lbl_value)
          layout.addWidget(self.lbl_sub)

     def set_value(self, val):
          self.lbl_value.setText(str(val))


# =====================================================================
# LỚP 2: DASHBOARD OVERVIEW (ĐÂY MỚI LÀ NƠI CHỨA ICON TIÊU ĐỀ)
# =====================================================================
class DashboardOverview(QWidget):
     def __init__(self, username, parent=None):
          super().__init__(parent)
          self.setFixedSize(1600, 900)

          display_name = username if username else "[username]"

          self.header_container = QWidget(self)
          self.header_container.setGeometry(100, 20, 800, 40) #(x, y, w, h)
          self.header_layout = QHBoxLayout(self.header_container)
          self.header_layout.setContentsMargins(0, 0, 0, 0)

          self.header_icon = QLabel()
          self.header_icon.setFixedSize(30, 30)

          # [FIX - 21:12] Dùng resource_path() → load đúng khi chạy .exe
          icon_path = resource_path(os.path.join("assets", "fooderai-blockcomponent", "fooderai-tqsk-username.png"))

          if os.path.exists(icon_path):
               self.header_icon.setPixmap(QPixmap(icon_path).scaled(
                    30, 30,
                    Qt.AspectRatioMode.IgnoreAspectRatio,
                    Qt.TransformationMode.SmoothTransformation
               ))
          else:
               print(f"[LỖI ĐƯỜNG DẪN] Không tìm thấy icon tại: {icon_path}")

          self.lbl_header_text = QLabel(f"Tổng quan sức khỏe của {display_name}")

          exact_font = QFont("Roboto")
          exact_font.setPixelSize(25)
          exact_font.setStyleStrategy(QFont.StyleStrategy.PreferAntialias)  # [FIX - 21:12] PySide6 yêu cầu dùng QFont.StyleStrategy.PreferAntialias thay vì QFont.PreferAntialias (cú pháp cũ PyQt5)

          self.lbl_header_text.setFont(exact_font)
          self.lbl_header_text.setStyleSheet("color: #266066; background: transparent;")

          self.header_layout.addWidget(self.header_icon)
          self.header_layout.addWidget(self.lbl_header_text)
          self.header_layout.addStretch()

          Y_BOX = 90
          X_GAP = 100
          BOX_W = 270

          self.box_bmi = StatCard("BMI", "Tỉ lệ cân nặng & chiều cao", "#3B82F6", self)
          self.box_bmi.move(X_GAP, Y_BOX)

          self.box_goal = StatCard("MỤC TIÊU", "Năng lượng hằng ngày", "#10B981", self)
          self.box_goal.move(X_GAP * 2 + BOX_W, Y_BOX)

          self.box_bmr = StatCard("BMR", "Năng lượng nghỉ ngơi", "#F59E0B", self)
          self.box_bmr.move(X_GAP * 3 + BOX_W * 2, Y_BOX)

          self.box_tdee = StatCard("TDEE", "Tổng tiêu thụ thực tế", "#EF4444", self)
          self.box_tdee.move(X_GAP * 4 + BOX_W * 3, Y_BOX)

     def update_username(self, new_username):
          display_name = new_username if new_username else "[username]"
          self.lbl_header_text.setText(f"Tổng quan sức khỏe của {display_name}")


# =======================================================================================================
# LỚP 3: MODEBUTTON - CẤU TRÚC PHẲNG (FLAT ARCHITECTURE)
# =======================================================================================================
class ModeButton(QFrame):
     def __init__(self, icon_name, text, parent=None):
          super().__init__(parent)

          # Kích thước khối Highlight (CHỈNH SỐ TẠI ĐÂY)
          self.setFixedSize(200, 50)
          self.is_selected = False

          self.layout = QHBoxLayout(self)
          self.layout.setContentsMargins(0, 0, 0, 0)

          # Khoảng cách giữa Icon và Text
          self.layout.setSpacing(10)    #<-- chỉnh tại đây

          # 1. Chế tác Icon (Đã fix lỗi đồng bộ 25px)
          self.lbl_icon = QLabel()
          self.lbl_icon.setStyleSheet("border: none; background: transparent;")
          self.lbl_icon.setFixedHeight(28)

          """
          [FIX - 21:12] Tách lbl_text ra NGOÀI khối if os.path.exists
          ──────────────────────────────────────────────────────────────
          Lỗi gốc: self.lbl_text = QLabel(text) nằm BÊN TRONG if os.path.exists(path_icon).
          Hậu quả: Nếu file icon không tồn tại (đặc biệt khi chạy .exe vì đường dẫn sai),
          Python bỏ qua toàn bộ khối if → self.lbl_text không bao giờ được tạo ra.
          Nhưng phía dưới layout.addWidget(self.lbl_text) vẫn cố gọi nó → AttributeError.

          Nguyên tắc: Widget nào LUÔN CẦN HIỂN THỊ thì phải tạo TRƯỚC, NGOÀI mọi điều kiện.
          Chỉ những thứ phụ thuộc điều kiện (ví dụ: pixmap của icon) mới nằm trong if.
          """

          # 2. Chế tác nhãn chữ - tạo TRƯỚC, ĐỘC LẬP với việc icon có load được hay không
          self.lbl_text = QLabel(text)

          """
          [CÚ PHÁP TRIỆU HỒI CHUẨN MỰC]
          - Bước 1: Gọi đúng "họ" gốc là Roboto.
          - Bước 2: Khóa cứng 18px.
          - Bước 3: Ép cân nặng (Weight) là Medium.
          - Bước 4: (QUAN TRỌNG NHẤT) Ép độ hẹp (Stretch) là SemiCondensed.
          """
          exact_font = QFont("Roboto")
          exact_font.setPixelSize(18)
          exact_font.setWeight(QFont.Weight.Medium)

          # Đây chính là "chìa khóa" để biến Roboto thường thành Roboto SemiCondensed!
          exact_font.setStretch(QFont.Stretch.SemiCondensed)

          self.lbl_text.setFont(exact_font)
          self.lbl_text.setStyleSheet("color: #266066; border: none; background: transparent;")

          # [FIX - 21:12] Dùng resource_path() thay os.path.join() thẳng
          # → đảm bảo tìm đúng thư mục dù chạy .py hay .exe đã đóng gói
          path_icon = resource_path(os.path.join("assets", "fooderai-blockcomponent", icon_name))
          if os.path.exists(path_icon):
               pix = QPixmap(path_icon)
               self.lbl_icon.setPixmap(pix.scaledToHeight(28, Qt.TransformationMode.SmoothTransformation))
          else:
               print(f"[LOG LỖI - 21:12] Không tìm thấy icon: {path_icon} — nút vẫn hiển thị chữ bình thường")

          # 3. Ép trọng tâm
          self.layout.addStretch()
          self.layout.addWidget(self.lbl_icon, alignment=Qt.AlignmentFlag.AlignVCenter)
          self.layout.addWidget(self.lbl_text, alignment=Qt.AlignmentFlag.AlignVCenter)
          self.layout.addStretch()

          self.update_style()

     def update_style(self):
          if self.is_selected:
               self.setStyleSheet("ModeButton { background-color: white; border-radius: 25px; border: none; }")
          else:
               self.setStyleSheet("ModeButton { background-color: transparent; border: none; }")

     def mousePressEvent(self, event):
          if self.parent(): self.parent().select_mode(self)


# ============================================================================================
# LỚP 4: MODENAVBAR - TỔNG KHUNG LAYER 3
# ============================================================================================
class ModeNavBar(QFrame):
     def __init__(self, parent=None):
          super().__init__(parent)

          self.setFixedSize(1240, 60) #(1240x60)

          self.setStyleSheet("""
            QFrame {
                background-color: rgba(255, 255, 255, 0.6);
                border: 3px solid rgba(0, 77, 77, 0.5);
                border-radius: 30px;
            }
        """)

          self.menu_shadow = QGraphicsDropShadowEffect()
          self.menu_shadow.setBlurRadius(6)
          self.menu_shadow.setOffset(0, 4)
          self.menu_shadow.setColor(QColor(0, 0, 0, 70))
          self.setGraphicsEffect(self.menu_shadow)

          self.layout = QHBoxLayout(self)

          # ---------------------------------------------------------
          # TOÁN HỌC KHÍT LỊM (Bỏ hẳn Lò xo và AlignVCenter gây lỗi)
          # Công thức: Lõi 1234px. 5 nút x 188px = 940px. Dư 294px.
          # 294px / 6 khe = 49px mỗi khe! Đều tăm tắp!
          # ---------------------------------------------------------
          self.layout.setContentsMargins(40, 2, 40, 2)
          self.layout.setSpacing(40)

          self.modes = [
               ModeButton("fooderai-ai-assistant.png", "Trợ lý AI", self),
               ModeButton("fooderai-food-scanner.png", "Quét món ăn", self),
               ModeButton("fooderai-food-almanac.png", "Sổ tay món ăn", self),
               ModeButton("fooderai-exercise-assistant.png", "Chế độ thể dục", self),
               ModeButton("fooderai-userinfo.png", "Hồ sơ người dùng", self)
          ]

          # Cứ thế ném vào, không cần lò xo nữa vì Spacing đã lo hết khoảng cách
          for mode in self.modes:
               self.layout.addWidget(mode)

          self.select_mode(self.modes[0])

     def select_mode(self, target_mode):
          for mode in self.modes:
               mode.is_selected = (mode == target_mode)
               mode.update_style()