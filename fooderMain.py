import sys
import os

def resource_path(relative_path):
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.abspath("."), relative_path)

from PySide6.QtWidgets import QApplication, QMainWindow, QWidget, QLabel, QPushButton, QHBoxLayout, QStackedWidget, QFrame
from PySide6.QtGui import QPixmap, QMouseEvent, QIcon, QFontDatabase, QFont
from PySide6.QtCore import Qt, QPoint, QSize

from fooder_widgetUI import DashboardOverview, ModeNavBar

from pages.page_ai import PageAIAssistant
from pages.page_scan import PageFoodScanner
from pages.page_almanac import PageFoodAlmanac
from pages.page_gym import PageExercise
from pages.page_user import PageUserProfile
from pages.page_version_info import InfoButton, PageVersionInfo


def load_fonts():
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


class CustomButton(QPushButton):
     def __init__(self, normal_img, hover_img, parent=None):
          super().__init__(parent)
          self.normal_icon = QIcon(normal_img)
          self.hover_icon = QIcon(hover_img)
          self.setFixedSize(62, 38)
          self.setIcon(self.normal_icon)
          self.setIconSize(QSize(62, 38))
          self.setStyleSheet("background: transparent; border: none;")

     def enterEvent(self, event):
          self.setIcon(self.hover_icon)

     def leaveEvent(self, event):
          self.setIcon(self.normal_icon)


class FooderAI(QMainWindow):
     def __init__(self):
          super().__init__()

          load_fonts()

          self.setWindowFlags(Qt.WindowType.FramelessWindowHint)
          self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

          screen = QApplication.primaryScreen().availableGeometry()
          win_w  = min(1600, screen.width())
          win_h  = min(1025, screen.height())
          self.setFixedSize(win_w, win_h)

          self.central_widget = QWidget(self)
          self.setCentralWidget(self.central_widget)

          self.active_bar = QLabel(self.central_widget)
          self.active_bar.setGeometry(0, 0, 1600, 58)
          path_bar = resource_path(os.path.join("assets", "fooderai-bar", "fooder_ai_win_activebar.png"))
          self.active_bar.setPixmap(QPixmap(path_bar).scaled(1600, 58, Qt.AspectRatioMode.IgnoreAspectRatio,
                                                             Qt.TransformationMode.SmoothTransformation))

          self.bg_base = QFrame(self.central_widget)
          self.bg_base.setGeometry(0, 58, 1600, 965)
          self.bg_base.setStyleSheet("""
                         QFrame {
                              background-color: rgb(210, 215, 218); 
                              border: 1px solid rgba(0, 0, 0, 40);
                              border-radius: 0px;
                         }
                    """)

          self.canvas = QLabel(self.central_widget)
          self.canvas.setGeometry(0, 57, 1600, 960)
          path_bg = resource_path(os.path.join("assets", "fooderai-background", "fooderaibg", "fooder_bg.PNG"))
          if os.path.exists(path_bg):
               self.canvas.setPixmap(QPixmap(path_bg).scaled(1600, 960, Qt.AspectRatioMode.IgnoreAspectRatio,
                                                             Qt.TransformationMode.SmoothTransformation))

          self.canvas.raise_()
          self.active_bar.raise_()

          btn_path = resource_path(os.path.join("assets", "fooderai-interact-button"))

          self.btn_close = CustomButton(
               os.path.join(btn_path, "fooder_ai_closebutton.png"),
               os.path.join(btn_path, "fooder_ai_closebutton_triggered.png"),
               self.active_bar
          )
          self.btn_close.move(1530, 10)
          self.btn_close.clicked.connect(self.close)

          self.btn_min = CustomButton(
               os.path.join(btn_path, "fooder_ai_minimize_button.png"),
               os.path.join(btn_path, "fooder_ai_minimize_button_triggered.png"),
               self.active_bar
          )
          self.btn_min.move(1468, 10)
          self.btn_min.clicked.connect(self.showMinimized)

          self.screen_manager = QStackedWidget(self.central_widget)
          self.screen_manager.setGeometry(0, 45, 1600, 900)
          self.view_dashboard = DashboardOverview("")
          self.screen_manager.addWidget(self.view_dashboard)

          self.nav_bar = ModeNavBar(self.central_widget)
          self.nav_bar.move(180, 295)

          self.feature_stack = QStackedWidget(self.central_widget)
          self.feature_stack.setFixedSize(1240, 640)
          self.feature_stack.move(180, 365)

          self.page_ai = PageAIAssistant()
          self.page_scan = PageFoodScanner()
          self.page_almanac = PageFoodAlmanac()
          self.page_gym = PageExercise()
          self.page_user = PageUserProfile()

          self.feature_stack.addWidget(self.page_ai)
          self.feature_stack.addWidget(self.page_scan)
          self.feature_stack.addWidget(self.page_almanac)
          self.feature_stack.addWidget(self.page_gym)
          self.feature_stack.addWidget(self.page_user)

          self.page_version_info = PageVersionInfo()
          self.feature_stack.addWidget(self.page_version_info)

          self.btn_info = InfoButton(self.central_widget)
          self.btn_info.move(1432, 295)
          self.btn_info.raise_()

          self.connect_nav_buttons()

          self.page_user.stats_saved.connect(self._on_stats_saved)
          self.page_user.username_changed.connect(self.view_dashboard.update_username)

          self.btn_info.clicked.connect(
               lambda: self.feature_stack.setCurrentIndex(5)
          )

          self.feature_stack.show()

     def _on_stats_saved(self, bmi: float, bmr: int, tdee: int, goal_kcal: int):
          print(f"[DASHBOARD] BMI={bmi} BMR={bmr} TDEE={tdee} MỤC TIÊU={goal_kcal}")
          self.view_dashboard.box_bmi.set_value(bmi)
          self.view_dashboard.box_bmi.set_bmi_warning(bmi)   # ← [v1.1] BMI warning icon
          self.view_dashboard.box_bmr.set_value(f"{bmr:,}")
          self.view_dashboard.box_tdee.set_value(f"{tdee:,}")
          self.view_dashboard.box_goal.set_value(f"{goal_kcal:,}")

     def connect_nav_buttons(self):
          for index, btn in enumerate(self.nav_bar.modes):
               btn.mousePressEvent = lambda event, i=index: self.switch_feature_page(i)

     def switch_feature_page(self, index):
          self.feature_stack.setCurrentIndex(index)
          self.nav_bar.select_mode(self.nav_bar.modes[index])

     def mousePressEvent(self, event: QMouseEvent):
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
     os.environ["QT_ENABLE_HIGHDPI_SCALING"]       = "1"
     os.environ["QT_SCALE_FACTOR_ROUNDING_POLICY"] = "PassThrough"

     app = QApplication(sys.argv)
     app.setHighDpiScaleFactorRoundingPolicy(
          Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
     )

     window = FooderAI()
     window.show()
     sys.exit(app.exec())