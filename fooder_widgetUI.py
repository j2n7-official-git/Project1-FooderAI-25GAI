import os
import sys
from PySide6.QtWidgets import QFrame, QVBoxLayout, QLabel, QGraphicsDropShadowEffect, QWidget, QHBoxLayout
from PySide6.QtCore import Qt, QPoint
from PySide6.QtGui import QFont, QColor, QPixmap

def resource_path(relative_path):
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, relative_path)
    base = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, relative_path)

# =====================================================================
# LỚP 1: STATCARD
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

          self.lbl_title = QLabel(title)
          self.lbl_title.setFont(QFont("Roboto Condensed", 18, QFont.Weight.Medium))
          self.lbl_title.setStyleSheet("color: rgba(255, 255, 255, 0.9);")

          self.lbl_value = QLabel("0.0")
          self.lbl_value.setFont(QFont("Roboto ExtraBold", 32))
          self.lbl_value.setStyleSheet("color: white;")

          text_shadow = QGraphicsDropShadowEffect()
          text_shadow.setBlurRadius(8)
          text_shadow.setOffset(2, 2)
          text_shadow.setColor(QColor(0, 0, 0, 200))
          self.lbl_value.setGraphicsEffect(text_shadow)

          self.lbl_sub = QLabel(sub_text)
          self.lbl_sub.setFont(QFont("Roboto SemiCondensed Medium", 12))
          self.lbl_sub.setStyleSheet("color: rgba(255, 255, 255, 0.7);")

          layout.addWidget(self.lbl_title)

          # ── Hàng giá trị: số + icon warning ──────────────────────
          value_row = QHBoxLayout()
          value_row.setContentsMargins(0, 0, 0, 0)
          value_row.setSpacing(0)
          value_row.addWidget(self.lbl_value, alignment=Qt.AlignmentFlag.AlignVCenter)

          self._warn_icon = QLabel("!", self)
          self._warn_icon.setFixedSize(22, 22)
          self._warn_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
          self._warn_icon.setStyleSheet("""
               QLabel {
                    background-color: #FF6B00;
                    color: white;
                    border-radius: 11px;
                    font-family: 'Roboto';
                    font-size: 13px;
                    font-weight: bold;
                    border: none;
                    margin-left: 10px;
               }
          """)
          self._warn_icon.setVisible(False)
          self._warn_icon.setCursor(Qt.CursorShape.PointingHandCursor)

          self._tooltip = self._build_tooltip()
          self._tooltip.setVisible(False)

          def _show_tip(e):
              win = self.window()
              self._tooltip.setParent(win)
              pos = self.mapTo(win, QPoint(0, self.height() - 10))
              self._tooltip.move(pos)
              self._tooltip.raise_()
              self._tooltip.setVisible(True)

          self._warn_icon.enterEvent = _show_tip
          self._warn_icon.leaveEvent = lambda e: self._tooltip.setVisible(False)

          value_row.addWidget(self._warn_icon, alignment=Qt.AlignmentFlag.AlignVCenter)
          value_row.addStretch()
          layout.addLayout(value_row)

          layout.addWidget(self.lbl_sub)

     def set_value(self, val):
          self.lbl_value.setText(str(val))

     def _build_tooltip(self):
          tip = QFrame(self)
          tip.setFixedWidth(220)
          tip.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
          tip.setStyleSheet("""
               QFrame {
                    background-color: #170d03;
                    border-radius: 10px;
                    border: 1.5px solid #FF6B00;
               }
               QLabel { border: none; background: transparent; }
          """)

          sh = QGraphicsDropShadowEffect()
          sh.setBlurRadius(16)
          sh.setOffset(0, 4)
          sh.setColor(QColor(0, 0, 0, 200))
          tip.setGraphicsEffect(sh)

          lay = QVBoxLayout(tip)
          lay.setContentsMargins(12, 10, 12, 10)
          lay.setSpacing(5)

          lbl_title = QLabel("CẢNH BÁO SỨC KHỎE")
          f_title = QFont("Roboto")
          f_title.setPixelSize(15)
          f_title.setWeight(QFont.Weight.Bold)
          lbl_title.setFont(f_title)
          lbl_title.setStyleSheet("color: #FF2020;")
          lay.addWidget(lbl_title)

          self._tooltip_desc = QLabel("")
          f_desc = QFont("Roboto")
          f_desc.setPixelSize(13)
          self._tooltip_desc.setFont(f_desc)
          self._tooltip_desc.setStyleSheet("color: rgba(255,255,255,0.85);")
          self._tooltip_desc.setWordWrap(True)
          lay.addWidget(self._tooltip_desc)

          tip.adjustSize()
          tip.move(0, 110)
          return tip

     def set_bmi_warning(self, bmi: float):
          if bmi <= 24.9:
               self._warn_icon.setVisible(False)
               self._tooltip.setVisible(False)
               return

          if bmi < 30:
               desc = ("Chỉ số BMI ở mức thừa cân. "
                       "Bạn nên điều chỉnh chế độ ăn uống, "
                       "tăng cường vận động và theo dõi cân nặng thường xuyên hơn.")
          elif bmi < 35:
               desc = ("Chỉ số BMI ở mức béo phì độ 1. "
                       "Nguy cơ cao về tim mạch và tiểu đường. "
                       "Hãy tham khảo chuyên gia dinh dưỡng ngay.")
          else:
               desc = ("Chỉ số BMI ở mức cao và nguy hiểm. "
                       "Bạn cần điều chỉnh chế độ ăn uống và tập luyện "
                       "càng sớm càng tốt để bảo vệ sức khỏe.")

          self._tooltip_desc.setText(desc)
          self._tooltip.adjustSize()
          self._warn_icon.setVisible(True)


# =====================================================================
# LỚP 2: DASHBOARD OVERVIEW
# =====================================================================
class DashboardOverview(QWidget):
     def __init__(self, username, parent=None):
          super().__init__(parent)
          self.setFixedSize(1600, 900)

          display_name = username if username else "[username]"

          self.header_container = QWidget(self)
          self.header_container.setGeometry(100, 20, 800, 40)
          self.header_layout = QHBoxLayout(self.header_container)
          self.header_layout.setContentsMargins(0, 0, 0, 0)

          self.header_icon = QLabel()
          self.header_icon.setFixedSize(30, 30)

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
          exact_font.setStyleStrategy(QFont.StyleStrategy.PreferAntialias)

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


# =====================================================================
# LỚP 3: MODEBUTTON
# =====================================================================
class ModeButton(QFrame):
     def __init__(self, icon_name, text, parent=None):
          super().__init__(parent)

          self.setFixedSize(200, 50)
          self.is_selected = False

          self.layout = QHBoxLayout(self)
          self.layout.setContentsMargins(0, 0, 0, 0)
          self.layout.setSpacing(10)

          self.lbl_icon = QLabel()
          self.lbl_icon.setStyleSheet("border: none; background: transparent;")
          self.lbl_icon.setFixedHeight(28)

          self.lbl_text = QLabel(text)

          exact_font = QFont("Roboto")
          exact_font.setPixelSize(18)
          exact_font.setWeight(QFont.Weight.Medium)
          exact_font.setStretch(QFont.Stretch.SemiCondensed)

          self.lbl_text.setFont(exact_font)
          self.lbl_text.setStyleSheet("color: #266066; border: none; background: transparent;")

          path_icon = resource_path(os.path.join("assets", "fooderai-blockcomponent", icon_name))
          if os.path.exists(path_icon):
               pix = QPixmap(path_icon)
               self.lbl_icon.setPixmap(pix.scaledToHeight(28, Qt.TransformationMode.SmoothTransformation))
          else:
               print(f"[LOG LỖI] Không tìm thấy icon: {path_icon}")

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


# =====================================================================
# LỚP 4: MODENAVBAR
# =====================================================================
class ModeNavBar(QFrame):
     def __init__(self, parent=None):
          super().__init__(parent)

          self.setFixedSize(1240, 60)

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
          self.layout.setContentsMargins(40, 2, 40, 2)
          self.layout.setSpacing(40)

          self.modes = [
               ModeButton("fooderai-ai-assistant.png", "Trợ lý AI", self),
               ModeButton("fooderai-food-scanner.png", "Quét món ăn", self),
               ModeButton("fooderai-food-almanac.png", "Sổ tay món ăn", self),
               ModeButton("fooderai-exercise-assistant.png", "Chế độ thể dục", self),
               ModeButton("fooderai-userinfo.png", "Hồ sơ người dùng", self)
          ]

          for mode in self.modes:
               self.layout.addWidget(mode)

          self.select_mode(self.modes[0])

     def select_mode(self, target_mode):
          for mode in self.modes:
               mode.is_selected = (mode == target_mode)
               mode.update_style()