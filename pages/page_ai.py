import os
import sys
import random
import socket
from datetime import datetime, timedelta

# ── SYS.PATH FIX ────────────────────────────────────────────────────────
# page_ai.py nằm trong pages/ nhưng fooder_database.py và gemini_service.py
# nằm ngoài root (FooderAI/).
# Python mặc định chỉ tìm module trong thư mục hiện tại (pages/) →
# "from fooder_database import ..." sẽ thất bại.
#
# Giải pháp: thêm thư mục CHA (root FooderAI/) vào sys.path
# os.path.dirname(__file__)      = .../FooderAI/pages
# os.path.dirname(dirname(...))  = .../FooderAI   ← đây là root cần thêm
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)   # chèn vào đầu để ưu tiên tìm ở root trước

# [UPDATE v2] Import fooder_database để lưu trạng thái NSFWGuard xuống SQL Server
# Đây là bước làm cho đồng hồ đếm "tính thật" — tắt app mở lại vẫn còn hiệu lực
try:
    from fooder_database import get_or_create_session, save_session_state, log_message, reset_chat_history
    _DB_AVAILABLE = True   # True = kết nối DB thành công
    print("[DB] AVAILABLE — fooder_database nạp thành công")
except Exception as _db_err:
    _DB_AVAILABLE = False  # False = DB lỗi → fallback RAM như cũ, app vẫn chạy
    print(f"[DB] NOT AVAILABLE — lỗi: {_db_err}")

# QFrame: khung có viền, dùng làm container có thể style được
# QVBoxLayout: xếp widget theo chiều dọc (Vertical)
# QHBoxLayout: xếp widget theo chiều ngang (Horizontal)
# QLabel: hiển thị chữ hoặc ảnh
# QWidget: widget cơ bản nhất, không có viền
# QGraphicsDropShadowEffect: hiệu ứng đổ bóng cho bất kỳ widget nào
# QLineEdit: ô nhập liệu 1 dòng
# QPushButton: nút bấm
# QScrollArea: vùng cuộn, tự động thêm thanh scroll khi nội dung dài hơn khung
# QSizePolicy: quy tắc co giãn của widget (Expanding = tự mở rộng tối đa)
from PySide6.QtWidgets import (QFrame, QVBoxLayout, QHBoxLayout, QLabel,
                               QWidget, QGraphicsDropShadowEffect, QLineEdit,
                               QPushButton, QScrollArea, QSizePolicy)

# Qt: kho hằng số của Qt (căn lề, loại cửa sổ, kiểu con trỏ...)
# QTimer: bộ đếm giờ, gọi hàm theo chu kỳ (dùng cho đồng hồ đếm ngược)
# QTime: đối tượng thời gian HH:MM:SS
# QSize: lưu cặp (width, height) — dùng khi set kích thước icon
from PySide6.QtCore import Qt, QTimer, QTime, QSize, QThread, Signal as QSignal

# QFont: đối tượng font chữ (tên font, cỡ, độ đậm)
# QColor: đối tượng màu sắc — nhận hex "#RRGGBB" hoặc RGBA (r, g, b, alpha)
# QPixmap: nạp và hiển thị ảnh PNG/JPG từ file
# QCursor: con trỏ chuột tùy chỉnh — nhận QPixmap hoặc CursorShape built-in
# QPainter: "cây bút vẽ" — dùng trong paintEvent để vẽ hình tự do
# QLinearGradient: gradient tuyến tính (màu chuyển dần từ điểm A → B)
# QBrush: "cái chổi tô màu" bên trong hình (fill)
# QPen: "cây bút vẽ đường viền" bên ngoài hình (stroke)
# QPainterPath: đường dẫn hình học phức tạp (dùng để vẽ hình đa giác)
from PySide6.QtGui import QFont, QColor, QPixmap, QCursor, QPainter, QLinearGradient, QBrush, QPen, QPainterPath, QIcon



# =====================================================================
# LOP 0: GEMINIWORKER — GOI GEMINI API TREN THREAD RIENG
# =====================================================================
# Van de: ask_gritalyst() goi API qua mang ~ 1-3 giay.
# Neu goi thang trong _send_message() thi UI bi "do" trong luc cho.
#
# Giai phap: QThread — chay API tren thread rieng song song voi UI.
# Khi API tra ve → phat signal finished(reply) → UI cap nhat bubble.
#
# So do luong:
#   [Main Thread / UI]          [GeminiWorker Thread]
#        |                              |
#        |─ worker.start() ────────────►| run() bat dau
#        |                              | ask_gritalyst() chay ngam...
#        |  (UI van hoat dong binh thuong)
#        |                              | xong → finished.emit(reply)
#        |◄──── finished signal ────────|
#        |
#        └─ _on_gemini_reply(reply): xoa "dang go...", hien tra loi that
#
class GeminiWorker(QThread):
    """Thread worker chay ask_gritalyst() ngam, khong do UI."""

    # Signal khai bao o cap CLASS (khong phai __init__):
    # finished(str) = signal mang 1 chuoi — cau tra loi tu Gemini
    # Qt yeu cau Signal phai la class attribute
    finished = QSignal(str)

    def __init__(self, user_message, chat_history, user_profile, session_id, user_id):
        super().__init__()
        self._msg     = user_message   # tin nhan user vua go
        self._history = chat_history   # lich su chat de Gemini nho ngu canh
        self._profile = user_profile   # thong tin suc khoe user (BMI, TDEE...) de ca nhan hoa
        self._session = session_id     # ID session de log vao DB
        self._uid     = user_id        # ID user de log vao DB

    def run(self):
        """Qt tu goi ham nay khi thread.start(). Chay tren thread rieng."""
        try:
            # Them thu muc cha (root du an) vao sys.path
            # Vi page_ai.py nam trong pages/ nhung gemini_service.py nam ngoai root
            # Python chi tim import trong thu muc hien tai → can chi duong ra root thu cong
            import sys, os
            root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            if root_dir not in sys.path:
                sys.path.insert(0, root_dir)

            # Import ben trong run() de tranh crash app khi chua co gemini_service.py
            from gemini_service import ask_gritalyst
            reply = ask_gritalyst(
                user_message  = self._msg,
                chat_history  = self._history,
                user_profile  = self._profile,
                session_id    = self._session,
                user_id       = self._uid,
            )
        except ImportError:
            # gemini_service.py chua co hoac thieu thu vien google-genai
            reply = "Chua tim thay gemini_service.py — kiem tra thu muc du an nhe!"
        except Exception as e:
            # Loi network, API key sai, quota het...
            reply = f"Loi ket noi Gemini: {str(e)[:120]}"

        # Phat signal — Qt tu chuyen ve main thread an toan
        self.finished.emit(reply)

# =====================================================================
# LỚP 1: NSFWGUARD — BỘ BẢO VỆ NỘI DUNG
# Nhiệm vụ: đếm tin nhắn, phát hiện vi phạm, phạt bịt mõm
# [UPDATE v2] Kết nối DB — trạng thái tồn tại qua các lần mở/tắt app
# =====================================================================
class NSFWGuard:
    """
    Bộ quản lý giới hạn chat và hệ thống phòng chống nội dung không phù hợp.
    The content moderation and rate-limiting system for GritalystAI.

    ── THUẬT TOÁN TỔNG QUAN (Algorithm Overview) ──────────────────────
    Hệ thống hoạt động theo mô hình "streak + quota kép":

      1. QUOTA (giới hạn lượt):
         Mỗi tin nhắn sạch tốn 1 xu, tin NSFW tốn 5 xu.
         Khi msg_count >= MAX_MSGS (50) → hiện thông báo, khóa nhập.
         Sau RESET_HOURS (4 tiếng) kể từ tin đầu → quota tự reset về 0.

      2. STREAK (chuỗi vi phạm liên tiếp):
         Mỗi tin NSFW tăng streak lên 1.
         Gửi 1 tin sạch bất kỳ → streak về 0 ngay lập tức.
         Khi streak >= 9 → mute 8 tiếng, không trừ quota nữa.

      3. TÍNH TOÁN PHÒNG CHỐNG XUNG ĐỘT quota vs mute:
         streak 1-8 × 5 xu = 40 xu tổng bị trừ trước khi mute.
         MAX_MSGS = 10 → còn 10 xu dư → quota KHÔNG bị chạm trước mute.
         → Đảm bảo 2 thông báo (quota card + mute card) KHÔNG hiện cùng lúc.

      4. PERSISTENCE (lưu trữ bền vững) — [UPDATE v2]:
         Trạng thái lưu vào SQL Server sau mỗi hành động.
         Khi app mở lại → load từ DB → timer tiếp tục đếm đúng giờ thật.
         Nếu DB lỗi → fallback RAM (app vẫn chạy, chỉ mất tính persistent).

    ── CÁC BIẾN TRẠNG THÁI (State Variables) ──────────────────────────
    msg_count   : int      — Số xu đã dùng (mỗi tin sạch +1, tin NSFW +5)
    nsfw_streak : int      — Chuỗi vi phạm liên tiếp chưa bị reset
    muted_until : datetime — Thời điểm hết bị khóa (None = không bị khóa)
    reset_at    : datetime — Thời điểm quota tự reset (None = chưa bắt đầu đếm)
    session_id  : int      — ID session trong DB (None nếu DB không khả dụng)
    """

    # ── HẰNG SỐ CẤU HÌNH (Configuration Constants) ──────────────────
    # Viết HOA toàn bộ theo quy ước Python — phân biệt với biến thường
    # [UPDATE v2] 27/05/2026: điều chỉnh theo plan cân bằng quota vs mute
    MAX_MSGS    = 50   # Tổng xu tối đa mỗi phiên
    RESET_HOURS = 4    # Giờ chờ để quota tự reset (7 → 4 tiếng)
    MUTE_HOURS  = 8    # Giờ bị khóa khi streak đạt ngưỡng (10 → 8 tiếng)
    MUTE_STREAK = 9    # Ngưỡng streak để kích hoạt mute (8 → 9 lần)
    # Tại sao MUTE_STREAK = 9 và không phải số khác?
    # streak 1-8 × 5xu = 40xu trừ, còn 10xu dư so với MAX_MSGS=50
    # → không bao giờ chạm quota trước khi bị mute → 2 card không tranh nhau

    # ── CÁC CÂU TRẢ LỜI KHI TỪ CHỐI (Refusal Replies) ──────────────
    # REPLIES_SOFT: 6 câu cấp độ tăng dần — dùng cho streak lần 1 đến 6
    # Thuật toán chọn câu: REPLIES_SOFT[streak - 1] tức đúng thứ tự cấp độ
    # min(streak-1, 5) để không vượt index khi streak > 6
    REPLIES_SOFT = [
        # Lần 1 — hài hước, nhẹ nhàng nhất
        "Ủa? Gritalyst nghe không rõ, tai đang bị... rau củ nhét vào rồi 🥕 Bạn hỏi lại đi!",
        # Lần 2 — gợi ý chủ đề thay thế
        "Hmm bạn ơi, câu đó hơi lạ với Gritalyst quá — thử hỏi về protein hay calo không, vui hơn đó!",
        # Lần 3 — thẳng thắn hơn
        "Gritalyst chuyên về dinh dưỡng thôi nha, câu đó mình chịu thua rồi — đổi chủ đề đi bạn ơi!",
        # Lần 4 — nhắc nhở có tình
        "Bạn ơi, Gritalyst sinh ra để giúp bạn khỏe hơn mỗi ngày, không phải để trả lời câu đó đâu nha — mình vẫn ở đây nếu bạn cần hỏi về sức khỏe nhé!",
        # Lần 5 — công nhận tò mò nhưng giữ vững lập trường
        "Câu hỏi này nằm ngoài vùng Gritalyst có thể giúp rồi bạn ơi. Mình hiểu đôi khi tò mò là chuyện bình thường, nhưng Gritalyst chỉ giỏi chuyện ăn uống và luyện tập thôi — quay lại nhé!",
        # Lần 6 — chân thành nhất, dài nhất, cấp độ cao nhất trong SOFT
        "Gritalyst muốn nói thật lòng: câu hỏi này mình không thể trả lời, không phải vì ghét bạn, mà vì Gritalyst được tạo ra với một mục đích duy nhất là đồng hành cùng bạn trên hành trình sống khỏe hơn mỗi ngày. Bạn xứng đáng được chăm sóc đúng cách — hỏi mình về dinh dưỡng nhé!",
    ]

    # REPLIES_HARD: 2 câu nghiêm — dùng cho streak lần 7 và 8
    # Thuật toán chọn câu: random.choice() để không bị đoán trước
    REPLIES_HARD = [
        "Gritalyst thấy bạn đang hỏi những điều ngoài vùng mình có thể giúp khá nhiều lần rồi đó... Mình vẫn ở đây, nhưng hãy cho Gritalyst cơ hội tư vấn đúng chuyên môn nhé! 🌿",
        "Bạn ơi, mình nhận ra cuộc trò chuyện đang đi hướng khác rồi. Gritalyst thực sự muốn giúp bạn — nhưng chỉ về dinh dưỡng và sức khỏe thôi. Thử hỏi về bữa ăn hôm nay đi?",
    ]

    def __init__(self):
        """
        Khởi tạo NSFWGuard — load trạng thái từ DB nếu có, fallback RAM nếu không.
        Initialize NSFWGuard — load state from DB if available, fallback to RAM.

        Luồng khởi tạo (Initialization flow):
          1. Lấy hostname máy tính làm machine_id (nhận diện máy khi chưa login)
          2. Nếu _DB_AVAILABLE = True → gọi get_or_create_session()
             → DB trả về dict chứa toàn bộ trạng thái phiên trước
             → Timer tiếp tục đếm đúng, không bị reset khi tắt app
          3. Nếu DB lỗi → gọi _init_ram() → khởi tạo từ 0 trong RAM
             → App vẫn chạy bình thường, chỉ mất tính persistent

        Tại sao dùng socket.gethostname() làm machine_id?
        socket.gethostname() trả về tên máy tính trong mạng nội bộ (VD: "LAPTOP-FB5BJ4FI").
        Đây là cách đơn giản nhất để phân biệt máy khi chưa có tài khoản,
        không cần cài thêm thư viện, không cần quyền admin.
        Khi user đăng nhập Google → session sẽ được gắn với user_id thay vì machine_id.
        """
        self._machine_id = socket.gethostname()  # VD: "LAPTOP-FB5BJ4FI"
        self.session_id  = None  # sẽ được set sau khi load session từ DB thành công

        if _DB_AVAILABLE:
            try:
                # get_or_create_session: tìm session theo machine_id
                # → nếu có rồi thì trả về trạng thái cũ (msg_count, streak, timer...)
                # → nếu chưa có thì tạo mới với msg_count=0, streak=0
                sess = get_or_create_session(machine_id=self._machine_id)
                self.session_id  = sess["session_id"]
                self.msg_count   = sess["msg_count"]    # số xu đã dùng từ lần trước
                self.nsfw_streak = sess["nsfw_streak"]  # streak còn lại từ lần trước
                self.muted_until = sess["muted_until"]  # datetime hoặc None
                self.reset_at    = sess["reset_at"]     # datetime hoặc None
                print(f"[DB] Session loaded: id={self.session_id}")  # ← thêm
            except Exception as e:
                # DB lỗi giữa chừng (VD: SQL Server tắt) → fallback RAM an toàn
                print(f"[DB] ERROR: {e}")  # ← thêm
                self._init_ram()
        else:
            # _DB_AVAILABLE = False ngay từ đầu (import thất bại) → dùng RAM
            print("[DB] NOT AVAILABLE")
            self._init_ram()

    def _init_ram(self):
        """
        Fallback: khởi tạo trạng thái trong RAM khi DB không khả dụng.
        RAM fallback: initialize all state to zero when DB is unavailable.

        Được gọi khi:
        - Import fooder_database thất bại (_DB_AVAILABLE = False)
        - DB kết nối thành công nhưng get_or_create_session() ném lỗi

        Hệ quả: app chạy bình thường nhưng trạng thái sẽ mất khi tắt app.
        """
        self.msg_count   = 0     # bắt đầu từ 0 xu
        self.nsfw_streak = 0     # chưa có vi phạm nào
        self.muted_until = None  # chưa bị khóa
        self.reset_at    = None  # chưa bắt đầu đếm giờ reset

    def _save(self):
        """
        Lưu trạng thái hiện tại của NSFWGuard xuống SQL Server.
        Persist current NSFWGuard state to SQL Server.

        ── Đây là trái tim của cơ chế "timer tính thật" ──────────────
        Mỗi khi msg_count, nsfw_streak, muted_until hoặc reset_at thay đổi,
        hàm này ghi ngay xuống DB. Khi app khởi động lại, __init__ đọc
        lại từ DB → timer tiếp tục từ chỗ dừng, không bị reset.

        Ví dụ (Example):
          User bị mute lúc 10:00, muted_until = 18:00.
          User tắt app lúc 12:00, mở lại lúc 15:00.
          __init__ đọc DB → muted_until = 18:00 → còn 3 tiếng nữa mới hết.
          → Không thể "lách" bằng cách tắt mở app!

        Tại sao dùng try/except im lặng (silent)?
        _save() được gọi rất thường xuyên (mỗi tin nhắn 1 lần).
        Nếu DB bị ngắt kết nối giữa chừng và ta để lỗi nổi lên,
        app sẽ crash ngay khi user đang chat → trải nghiệm tệ.
        Silent except: DB lỗi thì bỏ qua, trạng thái vẫn đúng trong RAM,
        chỉ mất tính persistent đến khi DB phục hồi.
        """
        if _DB_AVAILABLE and self.session_id:
            try:
                save_session_state(
                    self.session_id,   # int: ID phiên cần cập nhật
                    self.msg_count,    # int: số xu đã dùng
                    self.nsfw_streak,  # int: chuỗi vi phạm hiện tại
                    self.muted_until,  # datetime|None: thời điểm hết khóa
                    self.reset_at      # datetime|None: thời điểm reset quota
                )
            except Exception:
                pass  # DB lỗi giữa chừng → bỏ qua, không crash app

    def is_muted(self) -> bool:
        """
        Kiểm tra user có đang trong thời gian bị khóa không.
        Check if the user is currently muted.

        Thuật toán kiểm tra 2 nhánh:
          Nhánh 1 — muted_until có giá trị VÀ chưa đến giờ:
            → Trả về True (đang bị khóa)
          Nhánh 2 — muted_until có giá trị NHƯNG đã qua giờ:
            → Tự động mở khóa (reset muted_until + streak)
            → Trả về False
          Mặc định — muted_until = None:
            → Trả về False (chưa bao giờ bị khóa)

        Tại sao tự động mở khóa ở đây thay vì dùng QTimer?
        QTimer chạy trong background, nếu app bị treo hoặc sleep,
        QTimer có thể không tick đúng giờ. Kiểm tra tại thời điểm
        gọi is_muted() (lazy evaluation) đảm bảo kết quả luôn đúng
        bất kể app đã ngủ bao lâu.
        """
        if self.muted_until and datetime.now() < self.muted_until:
            return True   # đang trong vùng thời gian bị khóa

        if self.muted_until and datetime.now() >= self.muted_until:
            # Hết giờ phạt → dọn dẹp trạng thái, trả quyền nói chuyện
            self.muted_until = None
            self.nsfw_streak = 0
            self._save()  # ghi DB để phản ánh đã hết khóa
        return False

    def mute_remaining(self) -> str:
        """
        Tính thời gian còn lại của hình phạt, định dạng HH:MM.
        Calculate remaining mute duration, formatted as HH:MM.

        Thuật toán đổi giây → giờ:phút:
          total_sec = (muted_until - now).total_seconds()  # tổng giây còn lại
          hh = total_sec // 3600                           # lấy phần giờ nguyên
          mm = (total_sec % 3600) // 60                    # lấy phần phút còn dư

        Ví dụ (Example):
          total_sec = 9125 giây
          hh = 9125 // 3600 = 2 (giờ)
          mm = (9125 % 3600) // 60 = (1925) // 60 = 32 (phút)
          → "02:32"

        f"{hh:02d}" nghĩa là: in số nguyên, tối thiểu 2 chữ số, pad bằng 0 bên trái.
        VD: hh=9 → "09", hh=10 → "10" — giữ format đồng hồ nhất quán.
        """
        if not self.muted_until:
            return "00:00"
        delta     = self.muted_until - datetime.now()
        total_sec = max(0, int(delta.total_seconds()))
        hh        = total_sec // 3600
        mm        = (total_sec % 3600) // 60
        return f"{hh:02d}:{mm:02d}"

    def quota_remaining(self) -> tuple[str, str]:
        """Trả về (countdown HH:MM:SS, target_time HH:MM) cho quota card."""
        if not self.reset_at:
            target = datetime.now() + timedelta(hours=self.RESET_HOURS)
            return f"{self.RESET_HOURS:02d}:00:00", target.strftime("%H:%M")
        delta     = self.reset_at - datetime.now()
        total_sec = max(0, int(delta.total_seconds()))
        hh = total_sec // 3600
        mm = (total_sec % 3600) // 60
        ss = total_sec % 60
        return f"{hh:02d}:{mm:02d}:{ss:02d}", self.reset_at.strftime("%H:%M")

    def can_send(self) -> tuple[bool, str]:
        """
        Cổng kiểm tra duy nhất trước khi cho phép gửi tin.
        The single gate check before allowing a message to be sent.

        Trả về (True, "") nếu được phép gửi.
        Returns (True, "") if the message can be sent.

        Trả về (False, reason) nếu bị chặn, với reason là:
        Returns (False, reason) if blocked, where reason is:
          "muted" — đang trong thời gian bị khóa do vi phạm NSFW
          "quota" — đã dùng hết 50 xu trong phiên

        Thuật toán kiểm tra theo thứ tự ưu tiên:
          1. is_muted() trước — mute có ưu tiên cao hơn quota
          2. Kiểm tra reset_at — nếu đến giờ thì reset quota về 0
          3. Kiểm tra msg_count >= MAX_MSGS — hết quota
          4. Tất cả OK → cho gửi

        Tại sao kiểm tra reset trước quota?
        Nếu kiểm tra quota trước, user đang ở msg_count=50 vào đúng lúc
        reset_at đã qua → bị chặn oan dù đáng lẽ được reset.
        Kiểm tra reset trước giải quyết race condition này.
        """
        if self.is_muted():
            return False, "muted"

        # Auto-reset nếu đã đến giờ (lazy reset — không dùng background timer)
        if self.reset_at and datetime.now() >= self.reset_at:
            self.msg_count = 0
            self.reset_at  = None
            self._save()   # ghi DB trạng thái đã reset

        if self.msg_count >= self.MAX_MSGS:
            return False, "quota"

        return True, ""

    def record_clean(self):
        """
        Ghi nhận 1 tin nhắn sạch (không vi phạm NSFW).
        Record a clean (non-NSFW) message.

        Tác động lên trạng thái:
          msg_count  += 1      — tiêu 1 xu
          nsfw_streak = 0      — phá vỡ chuỗi vi phạm (streak bị reset)
          reset_at   được set  — nếu đây là tin đầu tiên trong phiên

        Tại sao streak về 0 khi gửi tin sạch?
        Đây là cơ chế "forgiveness" (tha thứ): người dùng được cơ hội
        dừng lại và quay về đúng hướng. 1 tin sạch là đủ để xóa slate.
        Điều này cũng ngăn người dùng "tích lũy" streak qua nhiều ngày.

        Tại sao chỉ set reset_at khi chưa có?
        reset_at đóng vai trò "điểm xuất phát" của đồng hồ 4 tiếng.
        Nếu reset lại mỗi tin thì giờ reset sẽ bị đẩy liên tục → không bao giờ reset.
        Chỉ set 1 lần duy nhất (lần gửi đầu tiên) → đếm 4 tiếng từ đó.
        """
        self.msg_count  += 1
        self.nsfw_streak = 0
        if not self.reset_at:
            self.reset_at = datetime.now() + timedelta(hours=self.RESET_HOURS)
        self._save()

    def record_nsfw(self) -> tuple[str, int]:
        """
        Ghi nhận 1 vi phạm NSFW và chọn câu phản hồi tương ứng.
        Record an NSFW violation and return the appropriate response.

        Trả về (reply, cost):
          reply : str — câu Gritalyst sẽ nói (hoặc "__muted__" nếu đạt ngưỡng)
          cost  : int — số xu bị trừ (0 nếu bị mute, 5 cho mọi trường hợp khác)

        Thuật toán chọn câu theo streak (Streak-based reply selection):
          streak 1-6 → REPLIES_SOFT[streak-1]  — tăng dần cấp độ, đúng thứ tự
          streak 7-8 → random.choice(REPLIES_HARD) — random để không đoán trước
          streak >= 9 → "__muted__" + kích hoạt timer khóa 8 tiếng

        Tại sao streak >= 9 mà không phải > 8?
        Python: streak >= 9 tương đương streak > 8, nhưng >= rõ ý hơn:
        "khi streak đạt đến 9" chứ không phải "khi streak vượt quá 8".
        Dễ đọc hơn khi maintain code sau này.

        Tại sao dùng biến trung gian `streak = self.nsfw_streak`?
        nsfw_streak đã được tăng ở dòng đầu. Nếu dùng self.nsfw_streak
        trực tiếp trong các if/else, giá trị đúng nhưng dễ nhầm khi đọc.
        Gán vào `streak` tách biệt rõ: "đây là giá trị SAU khi tăng".

        Tại sao cost luôn = 5 (không còn cost=10 ở lần 7-8)?
        Tính toán phòng chống xung đột quota vs mute:
          streak 1-8 × 5xu = 40xu → MAX_MSGS=50 → còn 10xu dư
          → quota card và mute card KHÔNG bao giờ hiện cùng lúc.
        Nếu lần 7-8 cost=10: streak 1-6×5 + 2×10 = 50xu = đúng quota
          → 2 card cùng trigger → UI lỗi, user nhìn thấy 2 thông báo chồng nhau.
        """
        self.nsfw_streak += 1
        streak = self.nsfw_streak  # giá trị sau khi tăng — dùng xuyên suốt hàm này

        if streak >= self.MUTE_STREAK:
            # Đạt ngưỡng → kích hoạt timer khóa
            # timedelta(hours=8): tạo khoảng thời gian 8 tiếng
            # datetime.now() + timedelta: cộng thêm 8 tiếng vào thời điểm hiện tại
            self.muted_until = datetime.now() + timedelta(hours=self.MUTE_HOURS)
            self._save()
            return "__muted__", 0

        cost = 5  # cost đồng đều tất cả các lần vi phạm — xem giải thích trên

        if streak >= 7:
            # HARD zone (streak 7-8): random để không đoán trước
            reply = random.choice(self.REPLIES_HARD)
        else:
            # SOFT zone (streak 1-6): tăng dần cấp độ theo đúng thứ tự
            # min(streak-1, 5): bảo vệ index — streak có thể = 6 → index = 5 (OK)
            # nếu streak = 7 thì min(6,5)=5 — nhưng streak=7 đã vào nhánh trên rồi
            reply = self.REPLIES_SOFT[min(streak - 1, 5)]

        self.msg_count += cost
        if not self.reset_at:
            self.reset_at = datetime.now() + timedelta(hours=self.RESET_HOURS)
        self._save()
        return reply, cost


# =====================================================================
# LỚP 2: CHATBUBBLE — 1 BONG BÓNG TIN NHẮN
# =====================================================================
class ChatBubble(QFrame):
    """
    Vẽ 1 bong bóng tin nhắn.
    - is_user=True  → căn phải, nền gradient xanh lá (tin của user)
    - is_user=False → căn trái, nền trắng viền nhạt (tin của Gritalyst)

    [UPDATE v2.2] — thiết kế lại width:
      - lbl.setFixedWidth(400) cho cả 2 loại — không stretch, không bóp
      - QFrame bản thân Fixed theo chiều ngang, Minimum theo chiều dọc
      - Không dùng addStretch() trong outer layout nữa
        → căn trái/phải xử lý ở _add_bot_bubble / _add_user_bubble qua Qt.AlignmentFlag
    """
    # Chiều rộng cố định của bubble — chỉnh 1 chỗ này là đủ
    BUBBLE_WIDTH = 400

    def __init__(self, text: str, is_user: bool, parent=None):
        super().__init__(parent)
        self.is_user = is_user

        # Fixed theo ngang (không stretch, không bóp), Minimum theo dọc (cao theo nội dung)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Minimum)

        # outer chỉ để padding trên/dưới — không stretch nữa
        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 4, 0, 4)
        outer.setSpacing(0)

        # ── Convert Markdown → HTML ────────────────────────────────────
        import re, html as _html
        safe = _html.escape(text)
        safe = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', safe, flags=re.DOTALL)
        safe = re.sub(r'^\*\s+', '• ', safe, flags=re.MULTILINE)
        safe = safe.replace('\n', '<br>')

        lbl = QLabel(safe)
        lbl.setTextFormat(Qt.TextFormat.RichText)
        lbl.setWordWrap(True)

        # ── FIXED WIDTH — không max, không min, không stretch ──────────
        # setFixedWidth = setMinimumWidth + setMaximumWidth cùng giá trị
        # → Qt không bao giờ co hay giãn lbl ra ngoài 400px
        # → wordWrap tự xuống dòng khi text dài hơn 400px
        lbl.setFixedWidth(self.BUBBLE_WIDTH)

        font = QFont("Roboto")
        font.setPixelSize(16)
        lbl.setFont(font)

        if is_user:
            lbl.setStyleSheet("""
                QLabel {
                    background: qlineargradient(
                        x1:1, y1:0, x2:0, y2:1,
                        stop:0   #2DB84D,
                        stop:0.75 #27A849,
                        stop:1.0  #1F8A3C
                    );
                    color: white;
                    border-radius: 18px;
                    padding: 10px 16px;
                    border: none;
                }
            """)
        else:
            lbl.setStyleSheet("""
                QLabel {
                    background-color: #FFFFFF;
                    color: #1A2A3A;
                    border-radius: 18px;
                    padding: 10px 16px;
                    border: 1.5px solid #D0EAD0;
                }
            """)

        outer.addWidget(lbl)


# =====================================================================
# LỚP 3: MUTEOVERLAY — LỚP PHỦ KHI BỊ BỊT MÕM
# Hiện lên phủ toàn bộ vùng chat khi nsfw_streak >= 8
# =====================================================================
class MuteOverlay(QFrame):
    """
    Lớp phủ bán trong suốt phủ lên vùng chat.
    Hiển thị đồng hồ đếm ngược và tự ẩn khi hết giờ.
    """
    def __init__(self, guard: NSFWGuard, parent=None):
        super().__init__(parent)
        self.guard = guard  # giữ tham chiếu đến NSFWGuard để hỏi thời gian còn lại

        # Nền trắng xanh nhạt, gần như đục hoàn toàn (alpha 0.97)
        self.setStyleSheet("""
            QFrame {
                background-color: rgba(240, 250, 245, 0.97);
                border-radius: 16px;
                border: 2px solid #B8E0C8;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)  # căn giữa tất cả nội dung
        layout.setSpacing(12)

        # Tiêu đề overlay
        lbl_title = QLabel("Nhu cầu cao")
        font_title = QFont("Roboto")
        font_title.setPixelSize(22)
        font_title.setWeight(QFont.Weight.Bold)
        lbl_title.setFont(font_title)
        lbl_title.setStyleSheet("color: #1A6A3A; border: none; background: transparent;")
        lbl_title.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Mô tả lý do bị khóa — dùng \n để xuống dòng thủ công
        lbl_desc = QLabel(
            "Gritalyst hiện đang ghi nhận một số lượng lớn yêu cầu không phù hợp\n"
            "trong thời gian ngắn. Để đảm bảo chất lượng tư vấn cho tất cả mọi người,\n"
            "hệ thống tạm thời nghỉ ngơi một chút. Bạn có thể thử lại sau:"
        )
        font_desc = QFont("Roboto")
        font_desc.setPixelSize(15)
        lbl_desc.setFont(font_desc)
        lbl_desc.setStyleSheet("color: #4A6A5A; border: none; background: transparent;")
        lbl_desc.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Đồng hồ đếm ngược — hiển thị HH:MM, cập nhật mỗi giây
        self.lbl_timer = QLabel("10:00")
        font_timer = QFont("Roboto")
        font_timer.setPixelSize(42)  # to hơn để dễ đọc
        font_timer.setWeight(QFont.Weight.Bold)
        self.lbl_timer.setFont(font_timer)
        self.lbl_timer.setStyleSheet("color: #2A7A4A; border: none; background: transparent;")
        self.lbl_timer.setAlignment(Qt.AlignmentFlag.AlignCenter)

        layout.addWidget(lbl_title)
        layout.addWidget(lbl_desc)
        layout.addWidget(self.lbl_timer)

        # QTimer: gọi hàm _tick() mỗi 1000ms (1 giây)
        # Đây là "nhịp tim" của đồng hồ đếm ngược
        self._ticker = QTimer(self)
        self._ticker.timeout.connect(self._tick)  # mỗi lần timeout → gọi _tick
        self._ticker.start(1000)                  # bắt đầu đếm, chu kỳ 1000ms

    def _tick(self):
        """Chạy mỗi giây: cập nhật số đếm ngược, tắt overlay khi về 00:00."""
        remaining = self.guard.mute_remaining()  # hỏi NSFWGuard còn bao lâu
        self.lbl_timer.setText(remaining)        # cập nhật hiển thị
        if remaining == "00:00":
            self._ticker.stop()  # dừng timer để không gọi _tick vô ích nữa
            self.hide()          # ẩn overlay, trả lại vùng chat cho user


# =====================================================================
# LỚP 3B: SYSTEMNOTICECARD — THẺ THÔNG BÁO HỆ THỐNG
# Hiển thị inline trong chat khi hết quota (50 tin) hoặc bị mute (NSFW)
# Có đếm ngược realtime HH:MM:SS, giữ đến hết giờ thật mới biến mất
# =====================================================================
class SystemNoticeCard(QFrame):
    """
    Thẻ thông báo hệ thống với countdown realtime.
    Không có avatar — đây là tin nhắn của HỆ THỐNG, không phải Gritalyst.

    2 loại:
      quota → hết 50 tin → đếm ngược đến reset_at (4 tiếng)
      mute  → streak 9 NSFW → đếm ngược đến muted_until (8 tiếng)

    Thiết kế:
      - Tự co theo chiều rộng chat (Expanding)
      - Gradient xanh -60° từ #38D45F → #2EAA4C
      - Tiêu đề 24px Bold + shadow đen nhẹ
      - Body 16px Regular + countdown HH:MM:SS cập nhật mỗi giây
    """

    def __init__(self, notice_type: str, guard=None, parent=None):
        super().__init__(parent)
        self._guard       = guard
        self._notice_type = notice_type

        # Kích thước tự co theo chiều rộng chat
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setFixedHeight(155)

        # Nền gradient + bo góc
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet("""
            QFrame {
                background: qlineargradient(
                    x1:0, y1:0, x2:0.5, y2:0.87,
                    stop:0 #38D45F, stop:1 #2EAA4C
                );
                border-radius: 12px;
                border: none;
            }
            QLabel { border: none; background: transparent; }
        """)

        # Glow shadow xanh nhẹ
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(16)
        shadow.setOffset(0, 4)
        shadow.setColor(QColor(38, 180, 80, 100))
        self.setGraphicsEffect(shadow)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 18, 28, 18)
        layout.setSpacing(8)
        layout.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        # ── TIÊU ĐỀ 24px Bold ────────────────────────────────────
        title_text = "⛔  Đã đạt giới hạn phiên chat" if notice_type == "quota" \
                else "⚠️  Hệ thống tạm dừng — Nhu cầu cao"

        lbl_title = QLabel(title_text)
        f_title = QFont("Roboto")
        f_title.setPixelSize(24)
        f_title.setWeight(QFont.Weight.Bold)
        lbl_title.setFont(f_title)
        lbl_title.setStyleSheet("color: white;")
        sh_t = QGraphicsDropShadowEffect()
        sh_t.setBlurRadius(0); sh_t.setOffset(1, 2)
        sh_t.setColor(QColor(0, 50, 0, 200))
        lbl_title.setGraphicsEffect(sh_t)

        # ── BODY 16px + countdown realtime ───────────────────────
        # Tính countdown ban đầu khi khởi tạo card
        countdown, target_time = self._calc_countdown()
        body_text = self._make_body(countdown, target_time)

        self.lbl_body = QLabel(body_text)
        f_body = QFont("Roboto")
        f_body.setPixelSize(16)
        self.lbl_body.setFont(f_body)
        self.lbl_body.setStyleSheet("color: rgba(255,255,255,0.93);")
        self.lbl_body.setWordWrap(True)
        sh_b = QGraphicsDropShadowEffect()
        sh_b.setBlurRadius(0); sh_b.setOffset(1, 1)
        sh_b.setColor(QColor(0, 50, 0, 150))
        self.lbl_body.setGraphicsEffect(sh_b)

        layout.addWidget(lbl_title)
        layout.addWidget(self.lbl_body)

        # ── TIMER ĐẾM NGƯỢC 1 GIÂY ───────────────────────────────
        self._target_time = target_time
        self._ticker = QTimer(self)
        self._ticker.timeout.connect(self._tick)
        self._ticker.start(1000)

    def _calc_countdown(self) -> tuple[str, str]:
        """
        Tính (countdown HH:MM:SS, target_time HH:MM) từ guard.
        Dùng cho cả quota lẫn mute.
        """
        if self._notice_type == "quota":
            deadline = self._guard.reset_at if self._guard else None
            fallback_hours = 4
        else:
            deadline = self._guard.muted_until if self._guard else None
            fallback_hours = 8

        if deadline:
            delta     = deadline - datetime.now()
            total_sec = max(0, int(delta.total_seconds()))
            target    = deadline.strftime("%H:%M")
        else:
            total_sec = fallback_hours * 3600
            target    = "--:--"

        hh = total_sec // 3600
        mm = (total_sec % 3600) // 60
        ss = total_sec % 60
        return f"{hh:02d}:{mm:02d}:{ss:02d}", target

    def _make_body(self, countdown: str, target_time: str) -> str:
        """
        Tạo text body theo loại thông báo.
        quota: cảm ơn + đếm ngược
        mute : nhẹ nhàng + đếm ngược
        """
        if self._notice_type == "quota":
            return (
                f"Cảm ơn bạn đã đồng hành cùng GritalystAI hôm nay! 🌿   "
                f"Hãy quay lại sau  {countdown}  (lúc {target_time}) nhé."
            )
        else:
            return (
                f"Gritalyst cần chút thời gian lấy lại năng lượng — "
                f"hẹn gặp lại bạn sau  {countdown}  (lúc {target_time}) 🌿"
            )

    def _tick(self):
        """Cập nhật countdown mỗi giây. Dừng khi về 00:00:00."""
        countdown, _ = self._calc_countdown()
        self.lbl_body.setText(self._make_body(countdown, self._target_time))
        if countdown == "00:00:00":
            self._ticker.stop()


# =====================================================================
# HÀM NẠP FONT — đăng ký Orbitron + Roboto vào hệ thống Qt
# Phải gọi 1 lần trước khi dùng QFont("Orbitron")
# =====================================================================
def load_gritalyst_fonts():
    """
    Nạp 3 file Orbitron + toàn bộ Roboto từ thư mục assets/fooderai-fonts.
    QFontDatabase.addApplicationFont() đăng ký font vào Qt runtime —
    sau đó mới có thể gọi QFont("Orbitron") hay QFont("Roboto") đúng.
    """
    from PySide6.QtGui import QFontDatabase
    font_dir = os.path.join("assets", "fooderai-fonts")

    # Danh sách đầy đủ theo ảnh thư mục: Orbitron 3 file + Roboto các biến thể
    font_files = [
        "Orbitron-Bold.ttf",
        "Orbitron-Medium.ttf",
        "Orbitron-Regular.ttf",
        "Roboto_SemiCondensed-Light.ttf",
        "Roboto_SemiCondensed-Medium.ttf",
        "Roboto_SemiCondensed-Regular.ttf",
        "Roboto-Black.ttf",
        "Roboto-Bold.ttf",
        "Roboto-Light.ttf",
        "Roboto-Medium.ttf",
        "Roboto-Regular.ttf",
    ]
    for f in font_files:
        path = os.path.join(font_dir, f)
        if os.path.exists(path):
            QFontDatabase.addApplicationFont(path)


# Đường dẫn ảnh logo — dùng chung ở cả 3 chỗ: avatar bubble, avatar banner, logo widget
_LOGO_PATH = os.path.join("assets", "fooderai-chatbot", "gritalyst-ai-logo.png")


# =====================================================================
# LỚP 4: GRITALYSTAVATAR — LOAD ẢNH PNG THAY VÌ VẼ TAY
# =====================================================================
class GritalystAvatar(QLabel):
    """
    Avatar hình tròn dùng ảnh PNG logo thật.
    Kế thừa QLabel thay vì QWidget vì QLabel có sẵn setPixmap().
    Size mặc định 46px cho header banner, 36px cho bubble chat.
    """
    def __init__(self, size=46, parent=None):
        super().__init__(parent)
        self.setFixedSize(size, size)  # khóa cứng, không cho co giãn
        self.setStyleSheet("border: none; background: transparent;")

        if os.path.exists(_LOGO_PATH):
            # scaledToWidth: scale giữ tỉ lệ theo chiều rộng
            # SmoothTransformation: dùng thuật toán nội suy mịn (chống răng cưa)
            pix = QPixmap(_LOGO_PATH).scaled(
                size, size,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
            self.setPixmap(pix)
            self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        else:
            # Fallback: hiện chữ "G" nếu không tìm thấy file
            self.setText("G")
            self.setAlignment(Qt.AlignmentFlag.AlignCenter)


# =====================================================================
# LỚP 4B: LOGOWIDGET — LOGO 300px + TÊN + SLOGAN (dùng trong chat header)
# Widget này được đặt vào đầu chat_layout để cuộn cùng với tin nhắn
# =====================================================================
class LogoWidget(QWidget):
    """
    Khối logo trung tâm gồm:
    - Ảnh logo tròn 300x300
    - Tên "GritalystAI" font Orbitron Bold màu đen
    - Slogan font Roboto SemiCondensed màu xám

    Đặt vào đầu chat_layout → sẽ cuộn lên khi user nhắn tin.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background: transparent;")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 10, 0, 10) #UPDATE cập nhật
        layout.setSpacing(10)
        layout.setAlignment(Qt.AlignmentFlag.AlignHCenter)

        # --- Ảnh logo 300x300 ---
        lbl_logo = QLabel()
        lbl_logo.setFixedSize(132, 132)
        lbl_logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_logo.setStyleSheet("border: none; background: transparent;")

        if os.path.exists(_LOGO_PATH):
            pix = QPixmap(_LOGO_PATH).scaled(
                132, 132, #kích thước mói: 3.5 cm x 3.5 cm
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
            lbl_logo.setPixmap(pix)
        else:
            lbl_logo.setText("[ Logo ]")  # placeholder nếu file chưa có

        # --- Tên "GritalystAI" — Orbitron Bold, đen, to ---
        lbl_name = QLabel("GritalystAI")
        font_name = QFont("Orbitron")          # họ font đã nạp từ load_gritalyst_fonts()
        font_name.setPixelSize(28)
        font_name.setWeight(QFont.Weight.Bold) # Bold = 700
        lbl_name.setFont(font_name)
        lbl_name.setStyleSheet("color: #111111; border: none; background: transparent;")
        lbl_name.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # --- Slogan — Roboto SemiCondensed, xám nhạt ---
        lbl_slogan = QLabel("Đồng hành sức khỏe — Dinh dưỡng thông minh, mỗi ngày.")
        font_slogan = QFont("Roboto")
        font_slogan.setPixelSize(14)
        font_slogan.setStretch(QFont.Stretch.SemiCondensed)  # ép thành SemiCondensed
        lbl_slogan.setFont(font_slogan)
        lbl_slogan.setStyleSheet("color: #6A8A7A; border: none; background: transparent;")
        lbl_slogan.setAlignment(Qt.AlignmentFlag.AlignCenter)

        layout.addWidget(lbl_logo,    alignment=Qt.AlignmentFlag.AlignHCenter)
        layout.addWidget(lbl_name,    alignment=Qt.AlignmentFlag.AlignHCenter)
        layout.addWidget(lbl_slogan,  alignment=Qt.AlignmentFlag.AlignHCenter)


# =====================================================================
# LỚP 4C: STROKELABEL — QLABEL CÓ VIỀN CHỮ ĐEN (TEXT STROKE)
# =====================================================================
# [UPDATE v1] Thêm mới — thay thế QLabel + QGraphicsDropShadowEffect
# Lý do: QGraphicsDropShadowEffect blur cả widget, không tạo được
# viền sắc nét cho chữ trắng trên nền xanh sáng (#3DE365).
#
# Giải pháp: override paintEvent(), dùng QPainter vẽ 2 lần:
#   Lần 1 — vẽ chữ đen offset 8 hướng (±2px) → tạo viền bao quanh
#   Lần 2 — vẽ chữ trắng đè lên chính giữa → fill bên trong viền
#
# Kết quả: stroke đen rõ nét, không phụ thuộc nền, không cần file CSS
# =====================================================================
class StrokeLabel(QLabel):
    """
    QLabel vẽ chữ có viền đen bằng QPainter.
    Dùng cho tiêu đề GritalystAI trên banner gradient xanh sáng.

    Tham số:
        text         : chuỗi chữ cần hiển thị
        font         : QFont đã set sẵn (pixelSize, weight...)
        stroke_color : QColor màu viền (mặc định đen alpha 210)
        stroke_width : độ dày viền tính bằng px offset (mặc định 2)
    """
    def __init__(self, text: str, font: QFont,
                 stroke_color: QColor = None,
                 stroke_width: int = 2,
                 parent=None):
        super().__init__(text, parent)
        self._font         = font
        self._stroke_color = stroke_color or QColor(0, 0, 0, 210)  # đen 82% đục
        self._stroke_w     = stroke_width
        self.setFont(font)
        self.setStyleSheet("background: transparent; border: none;")

        # Tính kích thước widget vừa đủ chứa chữ + padding stroke
        # horizontalAdvance(): chiều rộng chuỗi theo font hiện tại
        # height(): chiều cao 1 dòng chữ theo font
        from PySide6.QtGui import QFontMetrics
        fm  = QFontMetrics(font)
        pad = stroke_width + 3          # padding = độ dày stroke + 3px đệm mỗi bên (update)
        self.setFixedSize(
            fm.horizontalAdvance(text) + pad * 2,   # width  = chữ + padding 2 bên
            fm.height()                + pad * 2    # height = cao chữ + padding trên/dưới
        )

    def paintEvent(self, event):
        """
        Qt gọi hàm này mỗi khi widget cần vẽ lại.
        Quy trình 2 bước:
          Bước 1 — vẽ chữ đen 8 hướng offset → tạo stroke bao quanh
          Bước 2 — vẽ chữ trắng chính giữa đè lên stroke → fill trắng
        """
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setFont(self._font)

        w = self._stroke_w   # độ rộng offset viền (pixel)

        # --- BƯỚC 1: stroke đen 8 hướng ---
        # 8 hướng: trái/phải/trên/dưới + 4 góc chéo
        # Mỗi hướng offset (dx, dy) pixel so với vị trí chính giữa
        painter.setPen(QPen(self._stroke_color))
        for dx, dy in [
            (-w,  0), ( w,  0),   # trái, phải
            ( 0, -w), ( 0,  w),   # trên, dưới
            (-w, -w), ( w, -w),   # góc trên-trái, góc trên-phải
            (-w,  w), ( w,  w),   # góc dưới-trái, góc dưới-phải
        ]:
            # drawText(x, y, w, h, flags, text):
            # vẽ chữ trong rect (dx, dy, width, height) căn giữa
            painter.drawText(
                dx, dy,
                self.width(), self.height(),
                Qt.AlignmentFlag.AlignCenter,
                self.text()
            )

        # --- BƯỚC 2: fill trắng chính giữa ---
        painter.setPen(QPen(QColor(255, 255, 255)))   # trắng tuyệt đối alpha 255
        painter.drawText(
            0, 0,
            self.width(), self.height(),
            Qt.AlignmentFlag.AlignCenter,
            self.text()
        )
        painter.end()   # bắt buộc gọi end() khi tạo QPainter thủ công


# =====================================================================
# LỚP 5: PAGEAIASSISTANT — TRANG CHÍNH GHÉP TẤT CẢ LẠI
# =====================================================================
class PageAIAssistant(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(1240, 640)  # kích thước cố định khớp với feature_stack trong main

        # Khởi tạo bộ bảo vệ NSFW — dùng xuyên suốt phiên chat
        self.guard = NSFWGuard()

        # Lich su chat gui kem moi lan goi Gemini API
        # Cau truc: [{"role": "user", "parts": ["cau hoi"]}, {"role": "model", "parts": ["tra loi"]}, ...]
        # Gioi han toi da 30 tin (15 cap) de tranh ton qua nhieu token
        self._chat_history: list = []

        # Giu reference den worker dang chay
        # → Tranh Python garbage-collect thread truoc khi no xong viec
        self._current_worker = None

        # Style cho toàn bộ trang: nền trắng, viền teal mờ, góc bo 24px
        self.setStyleSheet("""
            PageAIAssistant {
                background-color: white;
                border: 3px solid rgba(0, 77, 77, 0.5);
                border-radius: 24px;
            }
        """)

        # Đổ bóng nhẹ cho cả trang để nổi lên trên nền app
        box_shadow = QGraphicsDropShadowEffect()
        box_shadow.setBlurRadius(5)
        box_shadow.setOffset(0, 3)               # bóng lệch xuống 3px
        box_shadow.setColor(QColor(150, 150, 150, 180))
        self.setGraphicsEffect(box_shadow)

        # Layout dọc chính: Banner → Vùng chat → Thanh nhập
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(15, 6, 15, 6)
        main_layout.setSpacing(4)  # khoảng cách giữa 3 vùng # cho nhỏ lại

        # ===========================================================
        # PHẦN 1: BANNER GRITALYSTAI
        # ===========================================================
        self.banner = QFrame()
        self.banner.setFixedSize(1210, 70)  # rộng hết trang, cao 70px

        # Tính màu gradient động từ màu gốc #3DE365
        color_hex = "#3DE365"
        base_color = QColor(color_hex)
        color_80  = base_color.darker(108).name()  # tối hơn 8% → dùng cho stop giữa
        color_100 = base_color.darker(124).name()  # tối hơn 24% → dùng cho stop cuối

        # Gradient chạy từ trái-giữa (x1:0, y1:0.2) sang phải-dưới (x2:1, y2:1)
        # y1:0.2 thay vì 0 để gradient không bắt đầu từ góc trên-trái mà từ giữa-trái
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

        # Bóng nhẹ phía dưới banner
        banner_shadow = QGraphicsDropShadowEffect()
        banner_shadow.setBlurRadius(6)
        banner_shadow.setOffset(0, 2)
        banner_shadow.setColor(QColor(0, 0, 0, 160))
        self.banner.setGraphicsEffect(banner_shadow)

        # Layout ngang bên trong banner: [Avatar] [Tên + Subtitle] [---stretch---]
        banner_layout = QHBoxLayout(self.banner)
        banner_layout.setContentsMargins(8, 0, 8, 0)
        banner_layout.setSpacing(12)

        # Avatar hình tròn chữ G — size 46px cho header
        self.avatar_header = GritalystAvatar(size=46)

        # [UPDATE] Thay QLabel thường bằng StrokeLabel để có viền đen rõ nét
        # QGraphicsDropShadowEffect không hoạt động tốt với chữ trắng trên nền xanh sáng
        # → dùng QPainter vẽ thủ công: stroke đen trước, fill trắng đè lên sau
        font_name = QFont("Orbitron")
        font_name.setPixelSize(25)
        font_name.setWeight(QFont.Weight.Bold)
        # Dòng tạo StrokeLabel trong banner — đổi stroke_width từ 2 → 1
        lbl_name = StrokeLabel("GritalystAI", font_name, stroke_width=1)

        # Ghép vào banner: Avatar → tên (căn giữa dọc) → stretch
        banner_layout.addWidget(self.avatar_header, alignment=Qt.AlignmentFlag.AlignVCenter)
        banner_layout.addWidget(lbl_name, alignment=Qt.AlignmentFlag.AlignVCenter)
        banner_layout.addStretch()

        # ── NÚT RESET CHAT — góc phải banner ─────────────────────────
        # Tạo chat mới: xóa toàn bộ bubble UI + lịch sử Gemini + log DB
        # Dùng QPushButton hình tròn với icon bút/tờ giấy
        self.btn_reset = QPushButton()
        self.btn_reset.setFixedSize(42, 42)
        self.btn_reset.setToolTip("Tạo cuộc trò chuyện mới")
        self.btn_reset.setCursor(Qt.CursorShape.PointingHandCursor)

        # Icon: dùng emoji ✏️ hoặc file PNG nếu có
        _reset_icon = os.path.join("assets", "fooderai-chatbot", "reset-chat.png")
        if os.path.exists(_reset_icon):
            self.btn_reset.setIcon(QIcon(_reset_icon))
            self.btn_reset.setIconSize(QSize(36, 36))
        else:
            # Fallback: dùng text ký hiệu
            self.btn_reset.setText("✦")
            font_r = QFont("Roboto")
            font_r.setPixelSize(18)
            self.btn_reset.setFont(font_r)

        self.btn_reset.setStyleSheet("""
            QPushButton {
                background-color: rgba(255, 255, 255, 0.25);
                border-radius: 21px;
                border: 1.5px solid rgba(255, 255, 255, 0.6);
                color: white;
            }
            QPushButton:hover   { background-color: rgba(255, 255, 255, 0.40); }
            QPushButton:pressed { background-color: rgba(255, 255, 255, 0.15); }
        """)
        self.btn_reset.clicked.connect(self._reset_chat)
        banner_layout.addWidget(self.btn_reset, alignment=Qt.AlignmentFlag.AlignVCenter)

        #update: for get a freedom strech
        main_layout.addWidget(self.banner)
        self.banner.setContentsMargins(0, 0, 0, 0)

        # ===========================================================
        # PHẦN 2: VÙNG CHAT (ScrollArea + Overlay bịt mõm)
        # ===========================================================

        # Container trong suốt bao quanh scroll — dùng để overlay bịt mõm biết phủ vào đâu
        self.chat_container = QFrame()
        self.chat_container.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.chat_container.setStyleSheet("QFrame { background: transparent; border: none; }")

        container_layout = QVBoxLayout(self.chat_container)
        container_layout.setContentsMargins(0, 0, 0, 0)

        # ScrollArea: tự thêm thanh scroll khi nội dung dài hơn khung
        # setWidgetResizable(True): widget bên trong co giãn theo khung scroll
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setStyleSheet("""
            QScrollArea { background: transparent; border: none; }
            QScrollBar:vertical {
                width: 6px;                  /* thanh scroll mỏng 6px */
                background: #F0F0F0;
                border-radius: 3px;
            }
            QScrollBar::handle:vertical {
                background: #3DE365;         /* tay cầm màu xanh lá */
                border-radius: 3px;
                min-height: 20px;            /* tối thiểu 20px để dễ kéo */
            }
            QScrollBar::add-line:vertical,
            QScrollBar::sub-line:vertical { height: 0; }  /* ẩn nút mũi tên */
        """)

        # Widget thật chứa các bubble — nằm bên trong ScrollArea
        self.chat_widget = QWidget()
        self.chat_widget.setStyleSheet("background: transparent;")

        self.chat_layout = QVBoxLayout(self.chat_widget)
        self.chat_layout.setContentsMargins(30, 0, 30, 3)  # [UPDATE] 10 → 30px mỗi bên
        self.chat_layout.setSpacing(3)
        self.chat_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        # LogoWidget nằm TRONG chat_layout → cuộn cùng với các bubble
        # Khi user nhắn tin nhiều, logo tự cuộn lên trên và biến mất như ChatGPT
        self.logo_widget = LogoWidget()
        self.chat_layout.addWidget(self.logo_widget,
                                   alignment=Qt.AlignmentFlag.AlignHCenter)  # ← vào đây

        self.scroll_area.setWidget(self.chat_widget)
        container_layout.addWidget(self.scroll_area)

        # BUG FIX: Đã XÓA dòng self.mute_overlay = MuteOverlay(...)
        # MuteOverlay (overlay phủ màn hình cũ) không còn dùng nữa —
        # đã thay bằng SystemNoticeCard inline trong chat_layout.
        # Nếu để lại: widget vô hình vẫn được tạo, chiếm memory,
        # và có thể intercept mouse event do nằm trên layer trên cùng.

        # Tham số "1" ở đây là stretch factor — vùng chat chiếm hết phần còn lại sau banner và input
        main_layout.addWidget(self.chat_container, 1)

        # ===========================================================
        # PHẦN 3: THANH NHẬP CHAT (Input + Nút gửi)
        # ===========================================================
        input_row = QHBoxLayout()
        input_row.setSpacing(10)         # khoảng cách giữa ô nhập và nút gửi
        input_row.setContentsMargins(0, 0, 0, 0)

        # Ô nhập liệu
        self.input_box = QLineEdit()
        self.input_box.setPlaceholderText("Nhắn gì đó với Gritalyst...")
        self.input_box.setFixedHeight(50)
        self.input_box.setMaxLength(450)  # giới hạn 450 ký tự, ngăn spam dài

        font_input = QFont("Roboto")
        font_input.setPixelSize(15)
        self.input_box.setFont(font_input)

        # Style capsule (bo tròn 2 đầu bằng border-radius bằng nửa chiều cao)
        self.input_box.setStyleSheet("""
            QLineEdit {
                background-color: rgba(255, 255, 255, 0.92);
                color: #1A2A3A;
                border-radius: 25px;
                border: 2px solid rgba(61, 227, 101, 0.5);
                padding: 0px 20px;
            }
            QLineEdit:focus {
                border: 2px solid #3DE365;   /* viền sáng lên khi đang gõ */
                background-color: #FFFFFF;
            }
        """)

        # Glow xanh nhẹ cho ô nhập — QColor(61, 227, 101, 90) là màu RGBA
        # 61,227,101 = #3DE365 viết theo số thập phân; 90 = alpha (35% trong suốt)
        shadow_input = QGraphicsDropShadowEffect()
        shadow_input.setBlurRadius(18)
        shadow_input.setOffset(0, 4)
        shadow_input.setColor(QColor(61, 227, 101, 90))
        self.input_box.setGraphicsEffect(shadow_input)

        # Nút gửi — hình tròn 50x50, không có chữ, chỉ có icon mũi tên
        self.btn_send = QPushButton()
        self.btn_send.setFixedSize(50, 50)  # width = height → hình tròn khi border-radius = 25

        # Nạp icon từ file PNG — nếu không tìm thấy thì nút vẫn chạy, chỉ không có icon
        icon_path = os.path.join("assets", "fooderai-chatbot", "fooderai-ai-submit.png")
        if os.path.exists(icon_path):
            self.btn_send.setIcon(QIcon(icon_path))
            self.btn_send.setIconSize(QSize(28, 28))  # icon 28px nằm giữa nút 50px

        # Gradient chạy chéo 45° từ trên-trái → dưới-phải (x1:0,y1:0 → x2:1,y2:1)
        self.btn_send.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 #3DE365, stop:0.75 #2FC455, stop:1.0 #27A849);
                border-radius: 25px;   /* = nửa chiều cao → hình tròn hoàn hảo */
                border: none;
            }
            QPushButton:hover   { background: #4AEF70; }   /* sáng hơn khi hover */
            QPushButton:pressed { background: #27A849; }   /* tối hơn khi nhấn */
        """)

        # Bóng xanh cho nút gửi — màu lấy từ #27A849 viết dạng RGBA
        # BUG FIX: lưu vào self._shadow_btn thay vì local variable shadow_btn
        # Lý do: _lock_input() cần gọi setGraphicsEffect(None) để xóa shadow này
        # trước khi đổi stylesheet xám. Nếu chỉ là local var thì sau __init__
        # biến mất khỏi scope nhưng Qt vẫn giữ reference nội bộ — setGraphicsEffect(None)
        # trên widget vẫn hoạt động đúng. Lưu vào self để dễ debug sau này.
        self._shadow_btn = QGraphicsDropShadowEffect()
        self._shadow_btn.setBlurRadius(14)
        self._shadow_btn.setOffset(0, 4)
        self._shadow_btn.setColor(QColor(39, 168, 73, 160))
        self.btn_send.setGraphicsEffect(self._shadow_btn)

        # Khi chuột di vào nút → con trỏ đổi thành bàn tay 👆
        self.btn_send.setCursor(Qt.CursorShape.PointingHandCursor)

        input_row.addWidget(self.input_box, 1)  # stretch=1 → ô nhập chiếm hết phần còn lại
        input_row.addWidget(self.btn_send)       # nút gửi kích thước cố định, không co giãn
        main_layout.addLayout(input_row)

        # Kết nối signal → slot:
        # clicked = signal phát ra khi nhấn nút chuột
        # returnPressed = signal phát ra khi nhấn phím Enter trong QLineEdit
        # Cả 2 đều dẫn đến cùng 1 hàm _send_message — không cần viết 2 hàm riêng
        self.btn_send.clicked.connect(self._send_message)
        self.input_box.returnPressed.connect(self._send_message)

        # Tin nhắn chào mừng tự động khi mở trang
        self._add_bot_bubble("Chào bạn! Tôi là GritalystAI — trợ lý dinh dưỡng và thể dục của bạn. Tôi có thể giúp gì cho bạn hôm nay? 🌿")

    def resizeEvent(self, event):
        """
        Qt tự gọi hàm này mỗi khi widget thay đổi kích thước.
        BUG FIX: Đã xóa block check mute_overlay vì MuteOverlay (lớp overlay cũ)
        không còn được khởi tạo trong __init__ nữa — đã thay bằng SystemNoticeCard
        inline trong chat. Giữ lại resizeEvent nhưng chỉ gọi super() để tránh
        AttributeError khi Qt resize widget lần đầu.
        """
        super().resizeEvent(event)

    def _reset_chat(self):
        """
        Tạo cuộc trò chuyện mới — xóa sạch 3 thứ:
          1. UI: xóa toàn bộ bubble trong chat_layout (giữ lại logo_widget)
          2. RAM: reset _chat_history → Gemini mất ngữ cảnh cũ
          3. DB: DELETE gritalyst_log WHERE session_id = ? → log cũ biến mất

        Tại sao xóa cả 3?
        → Chỉ xóa UI: bubble hết nhưng Gemini vẫn nhớ ngữ cảnh → không thật sự "mới"
        → Chỉ xóa RAM: bubble cũ vẫn hiển thị → user nhầm tưởng còn lịch sử
        → Chỉ xóa DB: lần sau mở app vẫn load lại được → không triệt để
        → Xóa cả 3: trải nghiệm "tờ giấy trắng" thật sự
        """
        # Bước 1: Xóa toàn bộ widget trong chat_layout TRỪ logo_widget
        # Lấy danh sách tất cả widget con, xóa từng cái
        # Dùng reversed() để xóa từ cuối lên — tránh index shift khi xóa giữa chừng
        while self.chat_layout.count() > 0:
            item = self.chat_layout.takeAt(0)
            if item and item.widget():
                w = item.widget()
                if w is self.logo_widget:
                    # Giữ lại logo, đặt lại vào layout
                    self.chat_layout.addWidget(w, alignment=Qt.AlignmentFlag.AlignHCenter)
                    continue
                w.setParent(None)
                w.deleteLater()

        # Bước 2: Reset lịch sử chat trong RAM
        # → Gemini sẽ không còn nhớ gì từ cuộc trò chuyện trước
        self._chat_history.clear()

        # Bước 3: Xóa log DB
        if _DB_AVAILABLE and self.guard.session_id:
            try:
                reset_chat_history(self.guard.session_id)
            except Exception:
                pass  # DB lỗi → vẫn reset UI và RAM, chỉ log cũ còn trong DB

        # Bước 4: Hiện lại bubble chào mừng
        self._add_bot_bubble(
            "Cuộc trò chuyện mới bắt đầu! 🌿 Tôi có thể giúp gì cho bạn hôm nay?"
        )

    def _add_bot_bubble(self, text: str):
        """Thêm 1 tin nhắn của Gritalyst vào cuối danh sách chat (căn trái)."""
        row = QHBoxLayout()
        row.setSpacing(8)
        row.setContentsMargins(0, 0, 0, 0)

        avatar = GritalystAvatar(size=36)
        bubble = ChatBubble(text, is_user=False)

        # AlignTop: avatar căn trên dù bubble cao bao nhiêu
        row.addWidget(avatar, alignment=Qt.AlignmentFlag.AlignTop)
        # AlignLeft | AlignTop: bubble dính trái, không stretch, không bóp
        row.addWidget(bubble, alignment=Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        row.addStretch()  # đẩy toàn bộ cụm avatar+bubble sang trái

        wrapper = QWidget()
        wrapper.setStyleSheet("background: transparent;")
        wrapper.setLayout(row)
        self.chat_layout.addWidget(wrapper)
        self._scroll_to_bottom()

    def _add_user_bubble(self, text: str):
        """Thêm 1 tin nhắn của user vào cuối danh sách chat (căn phải)."""
        row = QHBoxLayout()
        row.setSpacing(0)
        row.setContentsMargins(0, 0, 0, 0)

        bubble = ChatBubble(text, is_user=True)

        row.addStretch()  # đẩy bubble sang phải
        # AlignRight | AlignTop: bubble dính phải, không stretch, không bóp
        row.addWidget(bubble, alignment=Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop)

        wrapper = QWidget()
        wrapper.setStyleSheet("background: transparent;")
        wrapper.setLayout(row)
        self.chat_layout.addWidget(wrapper)
        self._scroll_to_bottom()

    def _add_typing_bubble(self) -> QWidget:
        """
        Hien GIF loading trong luc cho Gemini tra loi.

        Tra ve wrapper QWidget de sau nay co the xoa khi Gemini tra loi xong:
            typing_w = self._add_typing_bubble()   # hien GIF loading
            # ... goi API ngam ...
            typing_w.setParent(None)               # xoa khi co tra loi that
            typing_w.deleteLater()                 # giai phong bo nho
        """
        import os
        from PySide6.QtGui import QMovie
        from PySide6.QtWidgets import QLabel

        row = QHBoxLayout()
        row.setSpacing(8)
        row.setContentsMargins(0, 4, 0, 4)

        avatar = GritalystAvatar(size=36)

        # Tìm file GIF theo đường dẫn tương đối từ vị trí file page_ai.py
        # page_ai.py nằm trong pages/ → đi lên 1 cấp → vào assets/fooderai-chatbot/
        _here    = os.path.dirname(os.path.abspath(__file__))
        gif_path = os.path.join(_here, "..", "assets", "fooderai-chatbot", "fdai-response-loading.gif")
        gif_path = os.path.normpath(gif_path)  # chuẩn hóa đường dẫn, bỏ ../

        gif_label = QLabel()
        gif_label.setStyleSheet("background: transparent;")

        if os.path.exists(gif_path):
            # File GIF tồn tại → chạy animation
            movie = QMovie(gif_path)
            movie.setScaledSize(QSize(200, 28))  # scale vừa bubble, giữ tỉ lệ
            gif_label.setMovie(movie)
            movie.start()
            # Giữ reference để Python không garbage-collect movie
            # trong khi nó vẫn đang chạy
            gif_label._movie = movie
        else:
            # Fallback: nếu không tìm thấy GIF thì hiện chữ bình thường
            gif_label.setText("GritalystAI đang soạn câu trả lời...")
            gif_label.setStyleSheet("color: #555; font-style: italic; background: transparent;")

        row.addWidget(avatar, alignment=Qt.AlignmentFlag.AlignVCenter)
        row.addWidget(gif_label, alignment=Qt.AlignmentFlag.AlignVCenter)
        row.addStretch()

        wrapper = QWidget()
        wrapper.setStyleSheet("background: transparent;")
        wrapper.setLayout(row)
        self.chat_layout.addWidget(wrapper)
        self._scroll_to_bottom()
        return wrapper  # tra ve de caller co the xoa sau

    def _add_system_notice(self, notice_type: str):
        """
        Thêm thẻ thông báo hệ thống (SystemNoticeCard) vào chat như 1 tin nhắn,
        sau đó tự xóa sau 10 giây.
        Add a system notice card to chat as a message, then auto-remove after 10s.

        Cơ chế hoạt động (How it works):
          1. Tạo card + wrapper → addWidget vào chat_layout (hiện ngay trong chat)
          2. Scroll xuống cuối (200ms delay cho Qt tính lại layout)
          3. Lock input (disable Enter + btn_send)
          4. QTimer.singleShot(10000ms) → sau 10 giây gọi lambda xóa wrapper

        Tại sao xóa wrapper thay vì xóa card?
          card nằm BÊN TRONG wrapper (wrapper là QWidget bọc ngoài để căn giữa).
          Nếu chỉ xóa card: wrapper rỗng vẫn còn trong layout → chiếm khoảng trống.
          Xóa wrapper: xóa cả card lẫn khoảng trống → layout gọn lại hoàn toàn.

        Tại sao dùng setParent(None) thay vì deleteLater()?
          deleteLater(): Qt đánh dấu widget để xóa ở event loop tiếp theo — an toàn
          nhưng widget vẫn còn nhìn thấy 1 frame trước khi biến mất.
          setParent(None): tách widget ra khỏi layout ngay lập tức, ẩn luôn.
          Sau đó gọi deleteLater() để giải phóng bộ nhớ đúng cách.
          Kết hợp 2 cách: ẩn ngay + dọn memory sau → tốt nhất.

        Tại sao KHÔNG unlock input sau khi card biến mất?
          Card biến mất chỉ là UI — trạng thái mute/quota vẫn còn trong NSFWGuard.
          Unlock input phải chờ timer thật (muted_until hoặc reset_at) hết hạn.
          Card chỉ là thông báo tạm, không phải điều kiện để unlock.

        notice_type: 'quota' = hết 50 tin | 'mute' = bị khóa NSFW
        AUTO_REMOVE_MS: 10000ms = 10 giây — đủ để user đọc thông báo
        """
        # Card giữ đến khi hết giờ thật — quota 4 tiếng, mute 8 tiếng
        if notice_type == "quota" and self.guard.reset_at:
            delta = self.guard.reset_at - datetime.now()
        elif notice_type == "mute" and self.guard.muted_until:
            delta = self.guard.muted_until - datetime.now()
        else:
            delta = timedelta(hours=4 if notice_type == "quota" else 8)
        AUTO_REMOVE_MS = max(5000, int(delta.total_seconds() * 1000))

        card = SystemNoticeCard(notice_type, guard=self.guard)

        # wrapper full width — không addStretch, card tự Expanding
        wrapper = QWidget()
        wrapper.setStyleSheet("background: transparent;")
        row = QHBoxLayout(wrapper)
        row.setContentsMargins(8, 8, 8, 8)  # 8px mỗi bên — chữ không bị sát viền
        row.addWidget(card)

        self.chat_layout.addWidget(wrapper)

        QTimer.singleShot(200, lambda: self.scroll_area.verticalScrollBar().setValue(
            self.scroll_area.verticalScrollBar().maximum()
        ))

        self._lock_input()

        # Auto-remove sau 10s → unlock nếu can_send() OK
        def _on_card_expired():
            wrapper.setParent(None)
            wrapper.deleteLater()
            ok, _ = self.guard.can_send()
            if ok:
                self._unlock_input()

        QTimer.singleShot(AUTO_REMOVE_MS, _on_card_expired)

    def _scroll_to_bottom(self):
        """
        Cuộn ScrollArea xuống tin nhắn mới nhất.
        Dùng QTimer.singleShot(50ms) vì layout cần thêm 1 chút thời gian
        để tính toán chiều cao bubble mới trước khi biết vị trí maximum.
        """
        QTimer.singleShot(50, lambda: self.scroll_area.verticalScrollBar().setValue(
            self.scroll_area.verticalScrollBar().maximum()
        ))

    def _send_message(self):
        """
        Hàm xử lý chính khi user gửi tin — được gọi từ cả nút Gửi lẫn phím Enter.

        Luồng xử lý:
        1. Lấy text, bỏ qua nếu trống
        2. Xóa ô nhập + hiện bubble user ngay lập tức
        3. Hỏi NSFWGuard xem có được gửi không
        4. Nếu bị chặn (quota/mute): dùng QTimer.singleShot(0) để hiện
           SystemNoticeCard VÀ lock input SAU KHI hàm này return xong.
           → Tại sao phải singleShot(0)?
             _lock_input() gọi btn_send.clicked.disconnect() ngay trong lúc
             signal clicked đang kích hoạt hàm này → Qt phát warning và card
             không render kịp. singleShot(0) đẩy việc đó ra event loop tiếp theo,
             đảm bảo hàm hiện tại đã return hoàn toàn trước khi disconnect.
        5. Nếu OK: kiểm tra NSFW → phản hồi tương ứng → cập nhật nút
        """
        text = self.input_box.text().strip()  # strip() xóa khoảng trắng 2 đầu
        if not text:
            return  # không làm gì nếu ô trống

        # Xóa ô nhập + hiện bubble user ngay — trước khi kiểm tra bất kỳ thứ gì
        # BUG FIX: xóa dòng self.input_box.clear() thừa ở dưới (dòng cũ 789)
        # Trước đây có 2 lần clear(): 1 ở đây và 1 sau block "if not ok" →
        # nếu ok=False thì clear() chạy 2 lần (không hại nhưng thừa và confusing)
        self.input_box.clear()
        self._add_user_bubble(text)

        # Cổng kiểm tra — NSFWGuard quyết định có cho gửi không
        ok, reason = self.guard.can_send()

        if not ok:
            if reason == "muted":
                self._add_system_notice("mute")
            else:
                self._add_system_notice("quota")
            return

        # Kiểm tra NSFW bằng từ khóa đơn giản
        # any() trả về True nếu có ÍT NHẤT 1 từ trong list xuất hiện trong text
        # text.lower() để tìm không phân biệt hoa thường
        nsfw_words = [
            # Từ tục trực tiếp
            "cặc", "cu", "lồn", "địt", "đéo", "đĩ", "cave", "điếm",
            "dâm", "thủ dâm", "xuất tinh", "đụ",
            # Viết tắt
            "cc", "đcm", "đcmm", "đm", "clm", "vcl",
            # Cụm tục
            "địt con mẹ", "đụ má mày", "có cái lồn",
            "cái lồn mẹ mày", "con đĩ mẹ",
        ]
        is_nsfw = any(w in text.lower() for w in nsfw_words)

        if is_nsfw:
            reply, cost = self.guard.record_nsfw()
            if reply == "__muted__":
                self._add_system_notice("mute")
                return
            else:
                self._add_bot_bubble(reply)
        else:
            # ─────────────────────────────────────────────────────────────────
            # BUOC 1: Ghi nhan tin sach (tru 1 xu quota)
            # ─────────────────────────────────────────────────────────────────
            self.guard.record_clean()

            # BUOC 2: Hien bubble "dang go..." ngay lap tuc
            # → User thay phan hoi tuc thi, khong tuong app bi do
            typing_wrapper = self._add_typing_bubble()

            # BUOC 3: Lay user_profile tu DB de Gemini ca nhan hoa cau tra loi
            # VD: user co BMI=28 → Gemini tu van an it calo hon
            _profile = None
            if _DB_AVAILABLE:
                try:
                    from fooder_database import get_user_profile
                    _profile = get_user_profile(self.guard.session_id)
                except Exception:
                    pass  # khong co profile → Gemini van tra loi, chi khong ca nhan hoa

            # BUOC 4: Tao GeminiWorker va chay tren thread rieng
            # text = cau hoi user vua go (da luu o dau _send_message)
            self._current_worker = GeminiWorker(
                user_message  = text,
                chat_history  = self._chat_history,   # truyen lich su vao de Gemini nho
                user_profile  = _profile,
                session_id    = self.guard.session_id,
                user_id       = None,  # sau nay co login thi truyen user_id that vao
            )

            # BUOC 5: Dinh nghia ham callback chay khi Gemini tra ve ket qua
            # Dung closure de "bao" typing_wrapper va text vao trong ham nay
            def _on_gemini_reply(reply: str):
                # 5a: Xoa bubble "dang go..." — thay bang cau tra loi that
                # setParent(None): tach khoi layout ngay lap tuc → an di
                # deleteLater(): giai phong bo nho o event loop sau
                typing_wrapper.setParent(None)
                typing_wrapper.deleteLater()

                # 5b: Hien cau tra loi that cua Gemini
                self._add_bot_bubble(reply)

                # 5c: Luu cap hoi-dap vao lich su de Gemini nho o lan tiep theo
                self._chat_history.append({"role": "user",  "parts": [text]})
                self._chat_history.append({"role": "model", "parts": [reply]})

                # 5d: Gioi han lich su toi da 30 tin (15 cap hoi-dap)
                # Sliding window: xoa 2 tin cu nhat khi vuot nguong
                # → Tranh gui qua nhieu token → ton tien + cham hon
                MAX_HISTORY = 30
                if len(self._chat_history) > MAX_HISTORY:
                    del self._chat_history[0:2]  # xoa 1 cap (user + model) cu nhat

                # 5e: [FIX] Kiem tra quota SAU KHI bot da reply
                # Bot reply truoc → notice card chen ngay ben duoi sau 300ms
                if self.guard.msg_count >= self.guard.MAX_MSGS:
                    QTimer.singleShot(300, lambda: self._add_system_notice("quota"))
                    return

                # 5f: Cap nhat trang thai nut gui
                self._update_send_button()

            # BUOC 6: Ket noi signal finished → callback _on_gemini_reply
            # Khi GeminiWorker goi self.finished.emit(reply) → Qt goi _on_gemini_reply(reply)
            self._current_worker.finished.connect(_on_gemini_reply)

            # BUOC 7: Khoi dong thread — Qt tu goi run() tren thread rieng
            self._current_worker.start()

            # BUOC 8: return som — quota check da duoc chuyen vao _on_gemini_reply
            return

    def _show_mute_overlay(self):
        """
        Thay vì bubble AI, hiện SystemNoticeCard kiểu 'mute' trong chat.
        - Không có icon Gritalyst vì đây là thông báo hệ thống
        - _lock_input() được gọi bên trong _add_system_notice
        """
        self._add_system_notice("mute")

    def _lock_input(self):
        """
        Khóa hoàn toàn thanh nhập sau khi hiện SystemNoticeCard.
        - User vẫn gõ chữ trong ô input được (QLineEdit không bị disable)
        - Nhưng Enter bị ngắt → không gửi được
        - Nút gửi bị vô hiệu hóa + xám + cursor gạch chéo (ForbiddenCursor)

        Tại sao KHÔNG setEnabled(False) trên input_box?
        - Nếu disable input_box, ô sẽ xám xịt và user không gõ được gì,
          trông như app bị treo — trải nghiệm không tốt.
        - Thay vào đó: cho gõ thoải mái nhưng Enter/nút không phản hồi
          → user hiểu rõ "tôi vẫn ở đây, nhưng hệ thống đang chờ".

        Cursor ForbiddenCursor vs file .cur/.ico?
        - Qt.CursorShape.ForbiddenCursor = con trỏ ⊘ built-in của hệ điều hành
        - Ưu điểm: không cần file ngoài, hiển thị đúng trên Windows/macOS/Linux
        - Nếu muốn dùng file tùy chỉnh: dùng QCursor(QPixmap("path/prohibited.cur"))
          NOTE: Windows hỗ trợ cả .ico và .cur; macOS/Linux chỉ dùng QPixmap PNG
          → Khuyến nghị: dùng PNG 32x32 với điểm hotspot (16,16) cho đa nền tảng
          → assets/fooderai-chatbot/prohibited-cursor.png (nếu muốn customize sau)
        """
        # Ngắt Enter
        try:
            self.input_box.returnPressed.disconnect(self._send_message)
        except RuntimeError:
            pass

        # Ngắt click nút gửi
        try:
            self.btn_send.clicked.disconnect(self._send_message)
        except RuntimeError:
            pass

        # Xóa shadow để stylesheet xám hiển thị đúng (Qt 1 widget = 1 effect)
        self.btn_send.setGraphicsEffect(None)

        # Disable nút
        self.btn_send.setEnabled(False)

        # Cursor từ file — QPixmap KHÔNG đọc được .cur binary trực tiếp.
        # Qt trên Windows load .cur thông qua WinAPI, không qua QPixmap.
        # Giải pháp đúng: dùng file .png cùng thư mục (prohibited-cursor.cur.png)
        # vì QPixmap đọc PNG bình thường và QCursor nhận QPixmap.
        # Thứ tự ưu tiên: PNG → ForbiddenCursor built-in
        _png_path = os.path.join("assets", "fooderai-chatbot", "prohibited-cursor.cur.png")
        _cur_path = os.path.join("assets", "fooderai-chatbot", "prohibited-cursor.cur")
        if os.path.exists(_png_path):
            _pix = QPixmap(_png_path)
            # hotspot (0,0): điểm tác động góc trên-trái — phù hợp icon dạng gạch chéo
            # đổi thành (16,16) nếu muốn điểm tác động nằm chính giữa icon 32x32
            self.btn_send.setCursor(QCursor(_pix, 0, 0))
        elif os.path.exists(_cur_path):
            # Thử load .cur — hoạt động nếu Qt build với WinAPI cursor support
            _pix = QPixmap(_cur_path)
            if not _pix.isNull():
                self.btn_send.setCursor(QCursor(_pix, 0, 0))
            else:
                self.btn_send.setCursor(Qt.CursorShape.ForbiddenCursor)
        else:
            self.btn_send.setCursor(Qt.CursorShape.ForbiddenCursor)

        # Nút xám desaturate — giữ nguyên icon mũi tên, chỉ đổi nền
        self.btn_send.setStyleSheet("""
            QPushButton {
                background-color: #909090;
                border-radius: 25px;
                border: none;
            }
            QPushButton:disabled { background-color: #909090; }
        """)

    def _unlock_input(self):
        """Mở khóa thanh nhập sau khi card biến mất và can_send() = True."""
        try:
            self.input_box.returnPressed.disconnect(self._send_message)
        except RuntimeError:
            pass
        self.input_box.returnPressed.connect(self._send_message)
        try:
            self.btn_send.clicked.disconnect(self._send_message)
        except RuntimeError:
            pass
        self.btn_send.clicked.connect(self._send_message)
        self.btn_send.setEnabled(True)
        self.btn_send.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_send.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 #3DE365, stop:0.75 #2FC455, stop:1.0 #27A849);
                border-radius: 25px; border: none;
            }
            QPushButton:hover   { background: #4AEF70; }
            QPushButton:pressed { background: #27A849; }
        """)
        self._shadow_btn = QGraphicsDropShadowEffect()
        self._shadow_btn.setBlurRadius(14)
        self._shadow_btn.setOffset(0, 4)
        self._shadow_btn.setColor(QColor(39, 168, 73, 160))
        self.btn_send.setGraphicsEffect(self._shadow_btn)

    def _update_send_button(self):
        """
        Cập nhật trạng thái nút gửi + phím Enter sau mỗi lần gửi tin.
        Gọi sau mỗi _send_message() để đồng bộ UI với trạng thái NSFWGuard.

        Lưu ý: khi _lock_input() đã được gọi (quota/mute), hàm này chỉ
        đảm bảo trạng thái đúng chứ không unlock — unlock chỉ xảy ra
        khi quota được reset (sau RESET_HOURS) hoặc mute hết hạn.

        Tại sao KHÔNG dùng blockSignals(True) cho input_box?
        - blockSignals(True) tắt TẤT CẢ signal của widget đó,
          bao gồm cả textChanged, textEdited... có thể gây side effect
          nếu sau này ta cần lắng nghe các signal đó (ví dụ: đếm ký tự).
        - Thay vào đó, ta disconnect() ĐÚNG signal cần chặn (returnPressed)
          và connect() lại khi cần — phẫu thuật chính xác, không ảnh hưởng gì khác.

        Tại sao dùng try/except quanh disconnect()?
        - disconnect() trong Qt sẽ ném RuntimeError nếu signal đó
          chưa được connect hoặc đã bị disconnect trước đó.
        - Dùng try/except để bỏ qua lỗi đó một cách an toàn —
          vì ta chỉ cần "chắc chắn nó đã bị ngắt", không cần biết
          nó có đang kết nối hay không.

        Tại sao phải setGraphicsEffect(None) trước khi đổi stylesheet?
        - Qt chỉ cho mỗi widget giữ ĐÚNG 1 GraphicsEffect tại 1 thời điểm.
        - shadow_btn đang chiếm slot đó từ lúc khởi tạo.
        - Nếu không xóa shadow trước, stylesheet màu xám sẽ bị shadow
          override và không có tác dụng trực quan.
        - setGraphicsEffect(None) giải phóng slot → stylesheet mới
          được Qt render đúng.
        """
        # Nếu đang bị mute (NSFW) → giữ locked
        if self.guard.is_muted():
            self._lock_input()
            return

        quota_ok = self.guard.msg_count < self.guard.MAX_MSGS

        if quota_ok:
            # ===========================================================
            # CÒN LƯỢT — khôi phục toàn bộ về trạng thái hoạt động
            # ===========================================================

            # Bước 1: Kết nối lại phím Enter → _send_message.
            # disconnect() trước để tránh connect() bị gọi 2 lần
            # (nếu connect 2 lần thì 1 lần Enter sẽ gọi _send_message 2 lần!).
            # try/except để bỏ qua nếu chưa từng bị disconnect.
            try:
                self.input_box.returnPressed.disconnect(self._send_message)
            except RuntimeError:
                pass  # chưa bị disconnect → không cần làm gì
            self.input_box.returnPressed.connect(self._send_message)

            # Bước 2: Bật lại nút gửi — setEnabled(True) cho phép click
            self.btn_send.setEnabled(True)

            # Bước 3: Con trỏ bàn tay 👆 khi hover vào nút
            self.btn_send.setCursor(Qt.CursorShape.PointingHandCursor)

            # Bước 4: Khôi phục màu gradient xanh lá ban đầu
            self.btn_send.setStyleSheet("""
                    QPushButton {
                        background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                            stop:0 #3DE365, stop:0.75 #2FC455, stop:1.0 #27A849);
                        border-radius: 25px;
                        border: none;
                    }
                    QPushButton:hover   { background: #4AEF70; }
                    QPushButton:pressed { background: #27A849; }
                """)

        else:
            # ===========================================================
            # HẾT LƯỢT hoặc bị MUTE — ủy quyền toàn bộ cho _lock_input()
            # ===========================================================
            self._lock_input()

import os
import sys
import random
import socket
from datetime import datetime, timedelta

# ── SYS.PATH FIX ────────────────────────────────────────────────────────
# page_ai.py nằm trong pages/ nhưng fooder_database.py và gemini_service.py
# nằm ngoài root (FooderAI/).
# Python mặc định chỉ tìm module trong thư mục hiện tại (pages/) →
# "from fooder_database import ..." sẽ thất bại.
#
# Giải pháp: thêm thư mục CHA (root FooderAI/) vào sys.path
# os.path.dirname(__file__)      = .../FooderAI/pages
# os.path.dirname(dirname(...))  = .../FooderAI   ← đây là root cần thêm
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)   # chèn vào đầu để ưu tiên tìm ở root trước

# [UPDATE v2] Import fooder_database để lưu trạng thái NSFWGuard xuống SQL Server
# Đây là bước làm cho đồng hồ đếm "tính thật" — tắt app mở lại vẫn còn hiệu lực
try:
    from fooder_database import get_or_create_session, save_session_state, log_message, reset_chat_history
    _DB_AVAILABLE = True   # True = kết nối DB thành công
    print("[DB] AVAILABLE — fooder_database nạp thành công")
except Exception as _db_err:
    _DB_AVAILABLE = False  # False = DB lỗi → fallback RAM như cũ, app vẫn chạy
    print(f"[DB] NOT AVAILABLE — lỗi: {_db_err}")

# QFrame: khung có viền, dùng làm container có thể style được
# QVBoxLayout: xếp widget theo chiều dọc (Vertical)
# QHBoxLayout: xếp widget theo chiều ngang (Horizontal)
# QLabel: hiển thị chữ hoặc ảnh
# QWidget: widget cơ bản nhất, không có viền
# QGraphicsDropShadowEffect: hiệu ứng đổ bóng cho bất kỳ widget nào
# QLineEdit: ô nhập liệu 1 dòng
# QPushButton: nút bấm
# QScrollArea: vùng cuộn, tự động thêm thanh scroll khi nội dung dài hơn khung
# QSizePolicy: quy tắc co giãn của widget (Expanding = tự mở rộng tối đa)
from PySide6.QtWidgets import (QFrame, QVBoxLayout, QHBoxLayout, QLabel,
                               QWidget, QGraphicsDropShadowEffect, QLineEdit,
                               QPushButton, QScrollArea, QSizePolicy)

# Qt: kho hằng số của Qt (căn lề, loại cửa sổ, kiểu con trỏ...)
# QTimer: bộ đếm giờ, gọi hàm theo chu kỳ (dùng cho đồng hồ đếm ngược)
# QTime: đối tượng thời gian HH:MM:SS
# QSize: lưu cặp (width, height) — dùng khi set kích thước icon
from PySide6.QtCore import Qt, QTimer, QTime, QSize, QThread, Signal as QSignal

# QFont: đối tượng font chữ (tên font, cỡ, độ đậm)
# QColor: đối tượng màu sắc — nhận hex "#RRGGBB" hoặc RGBA (r, g, b, alpha)
# QPixmap: nạp và hiển thị ảnh PNG/JPG từ file
# QCursor: con trỏ chuột tùy chỉnh — nhận QPixmap hoặc CursorShape built-in
# QPainter: "cây bút vẽ" — dùng trong paintEvent để vẽ hình tự do
# QLinearGradient: gradient tuyến tính (màu chuyển dần từ điểm A → B)
# QBrush: "cái chổi tô màu" bên trong hình (fill)
# QPen: "cây bút vẽ đường viền" bên ngoài hình (stroke)
# QPainterPath: đường dẫn hình học phức tạp (dùng để vẽ hình đa giác)
from PySide6.QtGui import QFont, QColor, QPixmap, QCursor, QPainter, QLinearGradient, QBrush, QPen, QPainterPath, QIcon



# =====================================================================
# LOP 0: GEMINIWORKER — GOI GEMINI API TREN THREAD RIENG
# =====================================================================
# Van de: ask_gritalyst() goi API qua mang ~ 1-3 giay.
# Neu goi thang trong _send_message() thi UI bi "do" trong luc cho.
#
# Giai phap: QThread — chay API tren thread rieng song song voi UI.
# Khi API tra ve → phat signal finished(reply) → UI cap nhat bubble.
#
# So do luong:
#   [Main Thread / UI]          [GeminiWorker Thread]
#        |                              |
#        |─ worker.start() ────────────►| run() bat dau
#        |                              | ask_gritalyst() chay ngam...
#        |  (UI van hoat dong binh thuong)
#        |                              | xong → finished.emit(reply)
#        |◄──── finished signal ────────|
#        |
#        └─ _on_gemini_reply(reply): xoa "dang go...", hien tra loi that
#
class GeminiWorker(QThread):
    """Thread worker chay ask_gritalyst() ngam, khong do UI."""

    # Signal khai bao o cap CLASS (khong phai __init__):
    # finished(str) = signal mang 1 chuoi — cau tra loi tu Gemini
    # Qt yeu cau Signal phai la class attribute
    finished = QSignal(str)

    def __init__(self, user_message, chat_history, user_profile, session_id, user_id):
        super().__init__()
        self._msg     = user_message   # tin nhan user vua go
        self._history = chat_history   # lich su chat de Gemini nho ngu canh
        self._profile = user_profile   # thong tin suc khoe user (BMI, TDEE...) de ca nhan hoa
        self._session = session_id     # ID session de log vao DB
        self._uid     = user_id        # ID user de log vao DB

    def run(self):
        """Qt tu goi ham nay khi thread.start(). Chay tren thread rieng."""
        try:
            # Them thu muc cha (root du an) vao sys.path
            # Vi page_ai.py nam trong pages/ nhung gemini_service.py nam ngoai root
            # Python chi tim import trong thu muc hien tai → can chi duong ra root thu cong
            import sys, os
            root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            if root_dir not in sys.path:
                sys.path.insert(0, root_dir)

            # Import ben trong run() de tranh crash app khi chua co gemini_service.py
            from gemini_service import ask_gritalyst
            reply = ask_gritalyst(
                user_message  = self._msg,
                chat_history  = self._history,
                user_profile  = self._profile,
                session_id    = self._session,
                user_id       = self._uid,
            )
        except ImportError:
            # gemini_service.py chua co hoac thieu thu vien google-genai
            reply = "Chua tim thay gemini_service.py — kiem tra thu muc du an nhe!"
        except Exception as e:
            # Loi network, API key sai, quota het...
            reply = f"Loi ket noi Gemini: {str(e)[:120]}"

        # Phat signal — Qt tu chuyen ve main thread an toan
        self.finished.emit(reply)

# =====================================================================
# LỚP 1: NSFWGUARD — BỘ BẢO VỆ NỘI DUNG
# Nhiệm vụ: đếm tin nhắn, phát hiện vi phạm, phạt bịt mõm
# [UPDATE v2] Kết nối DB — trạng thái tồn tại qua các lần mở/tắt app
# =====================================================================
class NSFWGuard:
    """
    Bộ quản lý giới hạn chat và hệ thống phòng chống nội dung không phù hợp.
    The content moderation and rate-limiting system for GritalystAI.

    ── THUẬT TOÁN TỔNG QUAN (Algorithm Overview) ──────────────────────
    Hệ thống hoạt động theo mô hình "streak + quota kép":

      1. QUOTA (giới hạn lượt):
         Mỗi tin nhắn sạch tốn 1 xu, tin NSFW tốn 5 xu.
         Khi msg_count >= MAX_MSGS (50) → hiện thông báo, khóa nhập.
         Sau RESET_HOURS (4 tiếng) kể từ tin đầu → quota tự reset về 0.

      2. STREAK (chuỗi vi phạm liên tiếp):
         Mỗi tin NSFW tăng streak lên 1.
         Gửi 1 tin sạch bất kỳ → streak về 0 ngay lập tức.
         Khi streak >= 9 → mute 8 tiếng, không trừ quota nữa.

      3. TÍNH TOÁN PHÒNG CHỐNG XUNG ĐỘT quota vs mute:
         streak 1-8 × 5 xu = 40 xu tổng bị trừ trước khi mute.
         MAX_MSGS = 10 → còn 10 xu dư → quota KHÔNG bị chạm trước mute.
         → Đảm bảo 2 thông báo (quota card + mute card) KHÔNG hiện cùng lúc.

      4. PERSISTENCE (lưu trữ bền vững) — [UPDATE v2]:
         Trạng thái lưu vào SQL Server sau mỗi hành động.
         Khi app mở lại → load từ DB → timer tiếp tục đếm đúng giờ thật.
         Nếu DB lỗi → fallback RAM (app vẫn chạy, chỉ mất tính persistent).

    ── CÁC BIẾN TRẠNG THÁI (State Variables) ──────────────────────────
    msg_count   : int      — Số xu đã dùng (mỗi tin sạch +1, tin NSFW +5)
    nsfw_streak : int      — Chuỗi vi phạm liên tiếp chưa bị reset
    muted_until : datetime — Thời điểm hết bị khóa (None = không bị khóa)
    reset_at    : datetime — Thời điểm quota tự reset (None = chưa bắt đầu đếm)
    session_id  : int      — ID session trong DB (None nếu DB không khả dụng)
    """

    # ── HẰNG SỐ CẤU HÌNH (Configuration Constants) ──────────────────
    # Viết HOA toàn bộ theo quy ước Python — phân biệt với biến thường
    # [UPDATE v2] 27/05/2026: điều chỉnh theo plan cân bằng quota vs mute
    MAX_MSGS    = 50   # Tổng xu tối đa mỗi phiên
    RESET_HOURS = 4    # Giờ chờ để quota tự reset (7 → 4 tiếng)
    MUTE_HOURS  = 8    # Giờ bị khóa khi streak đạt ngưỡng (10 → 8 tiếng)
    MUTE_STREAK = 9    # Ngưỡng streak để kích hoạt mute (8 → 9 lần)
    # Tại sao MUTE_STREAK = 9 và không phải số khác?
    # streak 1-8 × 5xu = 40xu trừ, còn 10xu dư so với MAX_MSGS=50
    # → không bao giờ chạm quota trước khi bị mute → 2 card không tranh nhau

    # ── CÁC CÂU TRẢ LỜI KHI TỪ CHỐI (Refusal Replies) ──────────────
    # REPLIES_SOFT: 6 câu cấp độ tăng dần — dùng cho streak lần 1 đến 6
    # Thuật toán chọn câu: REPLIES_SOFT[streak - 1] tức đúng thứ tự cấp độ
    # min(streak-1, 5) để không vượt index khi streak > 6
    REPLIES_SOFT = [
        # Lần 1 — hài hước, nhẹ nhàng nhất
        "Ủa? Gritalyst nghe không rõ, tai đang bị... rau củ nhét vào rồi 🥕 Bạn hỏi lại đi!",
        # Lần 2 — gợi ý chủ đề thay thế
        "Hmm bạn ơi, câu đó hơi lạ với Gritalyst quá — thử hỏi về protein hay calo không, vui hơn đó!",
        # Lần 3 — thẳng thắn hơn
        "Gritalyst chuyên về dinh dưỡng thôi nha, câu đó mình chịu thua rồi — đổi chủ đề đi bạn ơi!",
        # Lần 4 — nhắc nhở có tình
        "Bạn ơi, Gritalyst sinh ra để giúp bạn khỏe hơn mỗi ngày, không phải để trả lời câu đó đâu nha — mình vẫn ở đây nếu bạn cần hỏi về sức khỏe nhé!",
        # Lần 5 — công nhận tò mò nhưng giữ vững lập trường
        "Câu hỏi này nằm ngoài vùng Gritalyst có thể giúp rồi bạn ơi. Mình hiểu đôi khi tò mò là chuyện bình thường, nhưng Gritalyst chỉ giỏi chuyện ăn uống và luyện tập thôi — quay lại nhé!",
        # Lần 6 — chân thành nhất, dài nhất, cấp độ cao nhất trong SOFT
        "Gritalyst muốn nói thật lòng: câu hỏi này mình không thể trả lời, không phải vì ghét bạn, mà vì Gritalyst được tạo ra với một mục đích duy nhất là đồng hành cùng bạn trên hành trình sống khỏe hơn mỗi ngày. Bạn xứng đáng được chăm sóc đúng cách — hỏi mình về dinh dưỡng nhé!",
    ]

    # REPLIES_HARD: 2 câu nghiêm — dùng cho streak lần 7 và 8
    # Thuật toán chọn câu: random.choice() để không bị đoán trước
    REPLIES_HARD = [
        "Gritalyst thấy bạn đang hỏi những điều ngoài vùng mình có thể giúp khá nhiều lần rồi đó... Mình vẫn ở đây, nhưng hãy cho Gritalyst cơ hội tư vấn đúng chuyên môn nhé! 🌿",
        "Bạn ơi, mình nhận ra cuộc trò chuyện đang đi hướng khác rồi. Gritalyst thực sự muốn giúp bạn — nhưng chỉ về dinh dưỡng và sức khỏe thôi. Thử hỏi về bữa ăn hôm nay đi?",
    ]

    def __init__(self):
        """
        Khởi tạo NSFWGuard — load trạng thái từ DB nếu có, fallback RAM nếu không.
        Initialize NSFWGuard — load state from DB if available, fallback to RAM.

        Luồng khởi tạo (Initialization flow):
          1. Lấy hostname máy tính làm machine_id (nhận diện máy khi chưa login)
          2. Nếu _DB_AVAILABLE = True → gọi get_or_create_session()
             → DB trả về dict chứa toàn bộ trạng thái phiên trước
             → Timer tiếp tục đếm đúng, không bị reset khi tắt app
          3. Nếu DB lỗi → gọi _init_ram() → khởi tạo từ 0 trong RAM
             → App vẫn chạy bình thường, chỉ mất tính persistent

        Tại sao dùng socket.gethostname() làm machine_id?
        socket.gethostname() trả về tên máy tính trong mạng nội bộ (VD: "LAPTOP-FB5BJ4FI").
        Đây là cách đơn giản nhất để phân biệt máy khi chưa có tài khoản,
        không cần cài thêm thư viện, không cần quyền admin.
        Khi user đăng nhập Google → session sẽ được gắn với user_id thay vì machine_id.
        """
        self._machine_id = socket.gethostname()  # VD: "LAPTOP-FB5BJ4FI"
        self.session_id  = None  # sẽ được set sau khi load session từ DB thành công

        if _DB_AVAILABLE:
            try:
                # get_or_create_session: tìm session theo machine_id
                # → nếu có rồi thì trả về trạng thái cũ (msg_count, streak, timer...)
                # → nếu chưa có thì tạo mới với msg_count=0, streak=0
                sess = get_or_create_session(machine_id=self._machine_id)
                self.session_id  = sess["session_id"]
                self.msg_count   = sess["msg_count"]    # số xu đã dùng từ lần trước
                self.nsfw_streak = sess["nsfw_streak"]  # streak còn lại từ lần trước
                self.muted_until = sess["muted_until"]  # datetime hoặc None
                self.reset_at    = sess["reset_at"]     # datetime hoặc None
                print(f"[DB] Session loaded: id={self.session_id}")  # ← thêm
            except Exception as e:
                # DB lỗi giữa chừng (VD: SQL Server tắt) → fallback RAM an toàn
                print(f"[DB] ERROR: {e}")  # ← thêm
                self._init_ram()
        else:
            # _DB_AVAILABLE = False ngay từ đầu (import thất bại) → dùng RAM
            print("[DB] NOT AVAILABLE")
            self._init_ram()

    def _init_ram(self):
        """
        Fallback: khởi tạo trạng thái trong RAM khi DB không khả dụng.
        RAM fallback: initialize all state to zero when DB is unavailable.

        Được gọi khi:
        - Import fooder_database thất bại (_DB_AVAILABLE = False)
        - DB kết nối thành công nhưng get_or_create_session() ném lỗi

        Hệ quả: app chạy bình thường nhưng trạng thái sẽ mất khi tắt app.
        """
        self.msg_count   = 0     # bắt đầu từ 0 xu
        self.nsfw_streak = 0     # chưa có vi phạm nào
        self.muted_until = None  # chưa bị khóa
        self.reset_at    = None  # chưa bắt đầu đếm giờ reset

    def _save(self):
        """
        Lưu trạng thái hiện tại của NSFWGuard xuống SQL Server.
        Persist current NSFWGuard state to SQL Server.

        ── Đây là trái tim của cơ chế "timer tính thật" ──────────────
        Mỗi khi msg_count, nsfw_streak, muted_until hoặc reset_at thay đổi,
        hàm này ghi ngay xuống DB. Khi app khởi động lại, __init__ đọc
        lại từ DB → timer tiếp tục từ chỗ dừng, không bị reset.

        Ví dụ (Example):
          User bị mute lúc 10:00, muted_until = 18:00.
          User tắt app lúc 12:00, mở lại lúc 15:00.
          __init__ đọc DB → muted_until = 18:00 → còn 3 tiếng nữa mới hết.
          → Không thể "lách" bằng cách tắt mở app!

        Tại sao dùng try/except im lặng (silent)?
        _save() được gọi rất thường xuyên (mỗi tin nhắn 1 lần).
        Nếu DB bị ngắt kết nối giữa chừng và ta để lỗi nổi lên,
        app sẽ crash ngay khi user đang chat → trải nghiệm tệ.
        Silent except: DB lỗi thì bỏ qua, trạng thái vẫn đúng trong RAM,
        chỉ mất tính persistent đến khi DB phục hồi.
        """
        if _DB_AVAILABLE and self.session_id:
            try:
                save_session_state(
                    self.session_id,   # int: ID phiên cần cập nhật
                    self.msg_count,    # int: số xu đã dùng
                    self.nsfw_streak,  # int: chuỗi vi phạm hiện tại
                    self.muted_until,  # datetime|None: thời điểm hết khóa
                    self.reset_at      # datetime|None: thời điểm reset quota
                )
            except Exception:
                pass  # DB lỗi giữa chừng → bỏ qua, không crash app

    def is_muted(self) -> bool:
        """
        Kiểm tra user có đang trong thời gian bị khóa không.
        Check if the user is currently muted.

        Thuật toán kiểm tra 2 nhánh:
          Nhánh 1 — muted_until có giá trị VÀ chưa đến giờ:
            → Trả về True (đang bị khóa)
          Nhánh 2 — muted_until có giá trị NHƯNG đã qua giờ:
            → Tự động mở khóa (reset muted_until + streak)
            → Trả về False
          Mặc định — muted_until = None:
            → Trả về False (chưa bao giờ bị khóa)

        Tại sao tự động mở khóa ở đây thay vì dùng QTimer?
        QTimer chạy trong background, nếu app bị treo hoặc sleep,
        QTimer có thể không tick đúng giờ. Kiểm tra tại thời điểm
        gọi is_muted() (lazy evaluation) đảm bảo kết quả luôn đúng
        bất kể app đã ngủ bao lâu.
        """
        if self.muted_until and datetime.now() < self.muted_until:
            return True   # đang trong vùng thời gian bị khóa

        if self.muted_until and datetime.now() >= self.muted_until:
            # Hết giờ phạt → dọn dẹp trạng thái, trả quyền nói chuyện
            self.muted_until = None
            self.nsfw_streak = 0
            self._save()  # ghi DB để phản ánh đã hết khóa
        return False

    def mute_remaining(self) -> str:
        """
        Tính thời gian còn lại của hình phạt, định dạng HH:MM.
        Calculate remaining mute duration, formatted as HH:MM.

        Thuật toán đổi giây → giờ:phút:
          total_sec = (muted_until - now).total_seconds()  # tổng giây còn lại
          hh = total_sec // 3600                           # lấy phần giờ nguyên
          mm = (total_sec % 3600) // 60                    # lấy phần phút còn dư

        Ví dụ (Example):
          total_sec = 9125 giây
          hh = 9125 // 3600 = 2 (giờ)
          mm = (9125 % 3600) // 60 = (1925) // 60 = 32 (phút)
          → "02:32"

        f"{hh:02d}" nghĩa là: in số nguyên, tối thiểu 2 chữ số, pad bằng 0 bên trái.
        VD: hh=9 → "09", hh=10 → "10" — giữ format đồng hồ nhất quán.
        """
        if not self.muted_until:
            return "00:00"
        delta     = self.muted_until - datetime.now()
        total_sec = max(0, int(delta.total_seconds()))
        hh        = total_sec // 3600
        mm        = (total_sec % 3600) // 60
        return f"{hh:02d}:{mm:02d}"

    def quota_remaining(self) -> tuple[str, str]:
        """Trả về (countdown HH:MM:SS, target_time HH:MM) cho quota card."""
        if not self.reset_at:
            target = datetime.now() + timedelta(hours=self.RESET_HOURS)
            return f"{self.RESET_HOURS:02d}:00:00", target.strftime("%H:%M")
        delta     = self.reset_at - datetime.now()
        total_sec = max(0, int(delta.total_seconds()))
        hh = total_sec // 3600
        mm = (total_sec % 3600) // 60
        ss = total_sec % 60
        return f"{hh:02d}:{mm:02d}:{ss:02d}", self.reset_at.strftime("%H:%M")

    def can_send(self) -> tuple[bool, str]:
        """
        Cổng kiểm tra duy nhất trước khi cho phép gửi tin.
        The single gate check before allowing a message to be sent.

        Trả về (True, "") nếu được phép gửi.
        Returns (True, "") if the message can be sent.

        Trả về (False, reason) nếu bị chặn, với reason là:
        Returns (False, reason) if blocked, where reason is:
          "muted" — đang trong thời gian bị khóa do vi phạm NSFW
          "quota" — đã dùng hết 50 xu trong phiên

        Thuật toán kiểm tra theo thứ tự ưu tiên:
          1. is_muted() trước — mute có ưu tiên cao hơn quota
          2. Kiểm tra reset_at — nếu đến giờ thì reset quota về 0
          3. Kiểm tra msg_count >= MAX_MSGS — hết quota
          4. Tất cả OK → cho gửi

        Tại sao kiểm tra reset trước quota?
        Nếu kiểm tra quota trước, user đang ở msg_count=50 vào đúng lúc
        reset_at đã qua → bị chặn oan dù đáng lẽ được reset.
        Kiểm tra reset trước giải quyết race condition này.
        """
        if self.is_muted():
            return False, "muted"

        # Auto-reset nếu đã đến giờ (lazy reset — không dùng background timer)
        if self.reset_at and datetime.now() >= self.reset_at:
            self.msg_count = 0
            self.reset_at  = None
            self._save()   # ghi DB trạng thái đã reset

        if self.msg_count >= self.MAX_MSGS:
            return False, "quota"

        return True, ""

    def record_clean(self):
        """
        Ghi nhận 1 tin nhắn sạch (không vi phạm NSFW).
        Record a clean (non-NSFW) message.

        Tác động lên trạng thái:
          msg_count  += 1      — tiêu 1 xu
          nsfw_streak = 0      — phá vỡ chuỗi vi phạm (streak bị reset)
          reset_at   được set  — nếu đây là tin đầu tiên trong phiên

        Tại sao streak về 0 khi gửi tin sạch?
        Đây là cơ chế "forgiveness" (tha thứ): người dùng được cơ hội
        dừng lại và quay về đúng hướng. 1 tin sạch là đủ để xóa slate.
        Điều này cũng ngăn người dùng "tích lũy" streak qua nhiều ngày.

        Tại sao chỉ set reset_at khi chưa có?
        reset_at đóng vai trò "điểm xuất phát" của đồng hồ 4 tiếng.
        Nếu reset lại mỗi tin thì giờ reset sẽ bị đẩy liên tục → không bao giờ reset.
        Chỉ set 1 lần duy nhất (lần gửi đầu tiên) → đếm 4 tiếng từ đó.
        """
        self.msg_count  += 1
        self.nsfw_streak = 0
        if not self.reset_at:
            self.reset_at = datetime.now() + timedelta(hours=self.RESET_HOURS)
        self._save()

    def record_nsfw(self) -> tuple[str, int]:
        """
        Ghi nhận 1 vi phạm NSFW và chọn câu phản hồi tương ứng.
        Record an NSFW violation and return the appropriate response.

        Trả về (reply, cost):
          reply : str — câu Gritalyst sẽ nói (hoặc "__muted__" nếu đạt ngưỡng)
          cost  : int — số xu bị trừ (0 nếu bị mute, 5 cho mọi trường hợp khác)

        Thuật toán chọn câu theo streak (Streak-based reply selection):
          streak 1-6 → REPLIES_SOFT[streak-1]  — tăng dần cấp độ, đúng thứ tự
          streak 7-8 → random.choice(REPLIES_HARD) — random để không đoán trước
          streak >= 9 → "__muted__" + kích hoạt timer khóa 8 tiếng

        Tại sao streak >= 9 mà không phải > 8?
        Python: streak >= 9 tương đương streak > 8, nhưng >= rõ ý hơn:
        "khi streak đạt đến 9" chứ không phải "khi streak vượt quá 8".
        Dễ đọc hơn khi maintain code sau này.

        Tại sao dùng biến trung gian `streak = self.nsfw_streak`?
        nsfw_streak đã được tăng ở dòng đầu. Nếu dùng self.nsfw_streak
        trực tiếp trong các if/else, giá trị đúng nhưng dễ nhầm khi đọc.
        Gán vào `streak` tách biệt rõ: "đây là giá trị SAU khi tăng".

        Tại sao cost luôn = 5 (không còn cost=10 ở lần 7-8)?
        Tính toán phòng chống xung đột quota vs mute:
          streak 1-8 × 5xu = 40xu → MAX_MSGS=50 → còn 10xu dư
          → quota card và mute card KHÔNG bao giờ hiện cùng lúc.
        Nếu lần 7-8 cost=10: streak 1-6×5 + 2×10 = 50xu = đúng quota
          → 2 card cùng trigger → UI lỗi, user nhìn thấy 2 thông báo chồng nhau.
        """
        self.nsfw_streak += 1
        streak = self.nsfw_streak  # giá trị sau khi tăng — dùng xuyên suốt hàm này

        if streak >= self.MUTE_STREAK:
            # Đạt ngưỡng → kích hoạt timer khóa
            # timedelta(hours=8): tạo khoảng thời gian 8 tiếng
            # datetime.now() + timedelta: cộng thêm 8 tiếng vào thời điểm hiện tại
            self.muted_until = datetime.now() + timedelta(hours=self.MUTE_HOURS)
            self._save()
            return "__muted__", 0

        cost = 5  # cost đồng đều tất cả các lần vi phạm — xem giải thích trên

        if streak >= 7:
            # HARD zone (streak 7-8): random để không đoán trước
            reply = random.choice(self.REPLIES_HARD)
        else:
            # SOFT zone (streak 1-6): tăng dần cấp độ theo đúng thứ tự
            # min(streak-1, 5): bảo vệ index — streak có thể = 6 → index = 5 (OK)
            # nếu streak = 7 thì min(6,5)=5 — nhưng streak=7 đã vào nhánh trên rồi
            reply = self.REPLIES_SOFT[min(streak - 1, 5)]

        self.msg_count += cost
        if not self.reset_at:
            self.reset_at = datetime.now() + timedelta(hours=self.RESET_HOURS)
        self._save()
        return reply, cost


# =====================================================================
# LỚP 2: CHATBUBBLE — 1 BONG BÓNG TIN NHẮN
# =====================================================================
class ChatBubble(QFrame):
    """
    Vẽ 1 bong bóng tin nhắn.
    - is_user=True  → căn phải, nền gradient xanh lá (tin của user)
    - is_user=False → căn trái, nền trắng viền nhạt (tin của Gritalyst)

    [UPDATE v2.2] — thiết kế lại width:
      - lbl.setFixedWidth(400) cho cả 2 loại — không stretch, không bóp
      - QFrame bản thân Fixed theo chiều ngang, Minimum theo chiều dọc
      - Không dùng addStretch() trong outer layout nữa
        → căn trái/phải xử lý ở _add_bot_bubble / _add_user_bubble qua Qt.AlignmentFlag
    """
    # Chiều rộng cố định của bubble — chỉnh 1 chỗ này là đủ
    BUBBLE_WIDTH = 450

    def __init__(self, text: str, is_user: bool, parent=None):
        super().__init__(parent)
        self.is_user = is_user

        # Fixed theo ngang (không stretch, không bóp), Minimum theo dọc (cao theo nội dung)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Minimum)

        # outer chỉ để padding trên/dưới — không stretch nữa
        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 4, 0, 4)
        outer.setSpacing(0)

        # ── Convert Markdown → HTML ────────────────────────────────────
        import re, html as _html
        safe = _html.escape(text)
        safe = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', safe, flags=re.DOTALL)
        safe = re.sub(r'^\*\s+', '• ', safe, flags=re.MULTILINE)
        safe = safe.replace('\n', '<br>')

        lbl = QLabel(safe)
        lbl.setTextFormat(Qt.TextFormat.RichText)
        lbl.setWordWrap(True)

        # ── FIXED WIDTH — không max, không min, không stretch ──────────
        # setFixedWidth = setMinimumWidth + setMaximumWidth cùng giá trị
        # → Qt không bao giờ co hay giãn lbl ra ngoài 400px
        # → wordWrap tự xuống dòng khi text dài hơn 400px
        lbl.setFixedWidth(self.BUBBLE_WIDTH)

        font = QFont("Roboto")
        font.setPixelSize(16)
        lbl.setFont(font)

        if is_user:
            lbl.setStyleSheet("""
                QLabel {
                    background: qlineargradient(
                        x1:1, y1:0, x2:0, y2:1,
                        stop:0   #2DB84D,
                        stop:0.75 #27A849,
                        stop:1.0  #1F8A3C
                    );
                    color: white;
                    border-radius: 18px;
                    padding: 10px 16px;
                    border: none;
                }
            """)
        else:
            lbl.setStyleSheet("""
                QLabel {
                    background-color: #FFFFFF;
                    color: #1A2A3A;
                    border-radius: 18px;
                    padding: 10px 16px;
                    border: 1.5px solid #D0EAD0;
                }
            """)

        outer.addWidget(lbl)


# =====================================================================
# LỚP 3: MUTEOVERLAY — LỚP PHỦ KHI BỊ BỊT MÕM
# Hiện lên phủ toàn bộ vùng chat khi nsfw_streak >= 8
# =====================================================================
class MuteOverlay(QFrame):
    """
    Lớp phủ bán trong suốt phủ lên vùng chat.
    Hiển thị đồng hồ đếm ngược và tự ẩn khi hết giờ.
    """
    def __init__(self, guard: NSFWGuard, parent=None):
        super().__init__(parent)
        self.guard = guard  # giữ tham chiếu đến NSFWGuard để hỏi thời gian còn lại

        # Nền trắng xanh nhạt, gần như đục hoàn toàn (alpha 0.97)
        self.setStyleSheet("""
            QFrame {
                background-color: rgba(240, 250, 245, 0.97);
                border-radius: 16px;
                border: 2px solid #B8E0C8;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)  # căn giữa tất cả nội dung
        layout.setSpacing(12)

        # Tiêu đề overlay
        lbl_title = QLabel("Nhu cầu cao")
        font_title = QFont("Roboto")
        font_title.setPixelSize(22)
        font_title.setWeight(QFont.Weight.Bold)
        lbl_title.setFont(font_title)
        lbl_title.setStyleSheet("color: #1A6A3A; border: none; background: transparent;")
        lbl_title.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Mô tả lý do bị khóa — dùng \n để xuống dòng thủ công
        lbl_desc = QLabel(
            "Gritalyst hiện đang ghi nhận một số lượng lớn yêu cầu không phù hợp\n"
            "trong thời gian ngắn. Để đảm bảo chất lượng tư vấn cho tất cả mọi người,\n"
            "hệ thống tạm thời nghỉ ngơi một chút. Bạn có thể thử lại sau:"
        )
        font_desc = QFont("Roboto")
        font_desc.setPixelSize(15)
        lbl_desc.setFont(font_desc)
        lbl_desc.setStyleSheet("color: #4A6A5A; border: none; background: transparent;")
        lbl_desc.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Đồng hồ đếm ngược — hiển thị HH:MM, cập nhật mỗi giây
        self.lbl_timer = QLabel("10:00")
        font_timer = QFont("Roboto")
        font_timer.setPixelSize(42)  # to hơn để dễ đọc
        font_timer.setWeight(QFont.Weight.Bold)
        self.lbl_timer.setFont(font_timer)
        self.lbl_timer.setStyleSheet("color: #2A7A4A; border: none; background: transparent;")
        self.lbl_timer.setAlignment(Qt.AlignmentFlag.AlignCenter)

        layout.addWidget(lbl_title)
        layout.addWidget(lbl_desc)
        layout.addWidget(self.lbl_timer)

        # QTimer: gọi hàm _tick() mỗi 1000ms (1 giây)
        # Đây là "nhịp tim" của đồng hồ đếm ngược
        self._ticker = QTimer(self)
        self._ticker.timeout.connect(self._tick)  # mỗi lần timeout → gọi _tick
        self._ticker.start(1000)                  # bắt đầu đếm, chu kỳ 1000ms

    def _tick(self):
        """Chạy mỗi giây: cập nhật số đếm ngược, tắt overlay khi về 00:00."""
        remaining = self.guard.mute_remaining()  # hỏi NSFWGuard còn bao lâu
        self.lbl_timer.setText(remaining)        # cập nhật hiển thị
        if remaining == "00:00":
            self._ticker.stop()  # dừng timer để không gọi _tick vô ích nữa
            self.hide()          # ẩn overlay, trả lại vùng chat cho user


# =====================================================================
# LỚP 3B: SYSTEMNOTICECARD — THẺ THÔNG BÁO HỆ THỐNG
# Hiển thị inline trong chat khi hết quota (50 tin) hoặc bị mute (NSFW)
# Có đếm ngược realtime HH:MM:SS, giữ đến hết giờ thật mới biến mất
# =====================================================================
class SystemNoticeCard(QFrame):
    """
    Thẻ thông báo hệ thống với countdown realtime.
    Không có avatar — đây là tin nhắn của HỆ THỐNG, không phải Gritalyst.

    2 loại:
      quota → hết 50 tin → đếm ngược đến reset_at (4 tiếng)
      mute  → streak 9 NSFW → đếm ngược đến muted_until (8 tiếng)

    Thiết kế:
      - Tự co theo chiều rộng chat (Expanding)
      - Gradient xanh -60° từ #38D45F → #2EAA4C
      - Tiêu đề 24px Bold + shadow đen nhẹ
      - Body 16px Regular + countdown HH:MM:SS cập nhật mỗi giây
    """

    def __init__(self, notice_type: str, guard=None, parent=None):
        super().__init__(parent)
        self._guard       = guard
        self._notice_type = notice_type

        # Kích thước tự co theo chiều rộng chat
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setFixedHeight(155)

        # Nền gradient + bo góc
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet("""
            QFrame {
                background: qlineargradient(
                    x1:0, y1:0, x2:0.5, y2:0.87,
                    stop:0 #38D45F, stop:1 #2EAA4C
                );
                border-radius: 12px;
                border: none;
            }
            QLabel { border: none; background: transparent; }
        """)

        # Glow shadow xanh nhẹ
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(16)
        shadow.setOffset(0, 4)
        shadow.setColor(QColor(38, 180, 80, 100))
        self.setGraphicsEffect(shadow)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 18, 28, 18)
        layout.setSpacing(8)
        layout.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        # ── TIÊU ĐỀ 24px Bold ────────────────────────────────────
        title_text = "⛔  Đã đạt giới hạn phiên chat" if notice_type == "quota" \
                else "⚠️  Hệ thống tạm dừng — Nhu cầu cao"

        lbl_title = QLabel(title_text)
        f_title = QFont("Roboto")
        f_title.setPixelSize(24)
        f_title.setWeight(QFont.Weight.Bold)
        lbl_title.setFont(f_title)
        lbl_title.setStyleSheet("color: white;")
        sh_t = QGraphicsDropShadowEffect()
        sh_t.setBlurRadius(0); sh_t.setOffset(1, 2)
        sh_t.setColor(QColor(0, 50, 0, 200))
        lbl_title.setGraphicsEffect(sh_t)

        # ── BODY 16px + countdown realtime ───────────────────────
        # Tính countdown ban đầu khi khởi tạo card
        countdown, target_time = self._calc_countdown()
        body_text = self._make_body(countdown, target_time)

        self.lbl_body = QLabel(body_text)
        f_body = QFont("Roboto")
        f_body.setPixelSize(16)
        self.lbl_body.setFont(f_body)
        self.lbl_body.setStyleSheet("color: rgba(255,255,255,0.93);")
        self.lbl_body.setWordWrap(True)
        sh_b = QGraphicsDropShadowEffect()
        sh_b.setBlurRadius(0); sh_b.setOffset(1, 1)
        sh_b.setColor(QColor(0, 50, 0, 150))
        self.lbl_body.setGraphicsEffect(sh_b)

        layout.addWidget(lbl_title)
        layout.addWidget(self.lbl_body)

        # ── TIMER ĐẾM NGƯỢC 1 GIÂY ───────────────────────────────
        self._target_time = target_time
        self._ticker = QTimer(self)
        self._ticker.timeout.connect(self._tick)
        self._ticker.start(1000)

    def _calc_countdown(self) -> tuple[str, str]:
        """
        Tính (countdown HH:MM:SS, target_time HH:MM) từ guard.
        Dùng cho cả quota lẫn mute.
        """
        if self._notice_type == "quota":
            deadline = self._guard.reset_at if self._guard else None
            fallback_hours = 4
        else:
            deadline = self._guard.muted_until if self._guard else None
            fallback_hours = 8

        if deadline:
            delta     = deadline - datetime.now()
            total_sec = max(0, int(delta.total_seconds()))
            target    = deadline.strftime("%H:%M")
        else:
            total_sec = fallback_hours * 3600
            target    = "--:--"

        hh = total_sec // 3600
        mm = (total_sec % 3600) // 60
        ss = total_sec % 60
        return f"{hh:02d}:{mm:02d}:{ss:02d}", target

    def _make_body(self, countdown: str, target_time: str) -> str:
        """
        Tạo text body theo loại thông báo.
        quota: cảm ơn + đếm ngược
        mute : nhẹ nhàng + đếm ngược
        """
        if self._notice_type == "quota":
            return (
                f"Cảm ơn bạn đã đồng hành cùng GritalystAI hôm nay! 🌿   "
                f"Hãy quay lại sau  {countdown}  (lúc {target_time}) nhé."
            )
        else:
            return (
                f"Gritalyst cần chút thời gian lấy lại năng lượng — "
                f"hẹn gặp lại bạn sau  {countdown}  (lúc {target_time}) 🌿"
            )

    def _tick(self):
        """Cập nhật countdown mỗi giây. Dừng khi về 00:00:00."""
        countdown, _ = self._calc_countdown()
        self.lbl_body.setText(self._make_body(countdown, self._target_time))
        if countdown == "00:00:00":
            self._ticker.stop()


# =====================================================================
# HÀM NẠP FONT — đăng ký Orbitron + Roboto vào hệ thống Qt
# Phải gọi 1 lần trước khi dùng QFont("Orbitron")
# =====================================================================
def load_gritalyst_fonts():
    """
    Nạp 3 file Orbitron + toàn bộ Roboto từ thư mục assets/fooderai-fonts.
    QFontDatabase.addApplicationFont() đăng ký font vào Qt runtime —
    sau đó mới có thể gọi QFont("Orbitron") hay QFont("Roboto") đúng.
    """
    from PySide6.QtGui import QFontDatabase
    font_dir = os.path.join("assets", "fooderai-fonts")

    # Danh sách đầy đủ theo ảnh thư mục: Orbitron 3 file + Roboto các biến thể
    font_files = [
        "Orbitron-Bold.ttf",
        "Orbitron-Medium.ttf",
        "Orbitron-Regular.ttf",
        "Roboto_SemiCondensed-Light.ttf",
        "Roboto_SemiCondensed-Medium.ttf",
        "Roboto_SemiCondensed-Regular.ttf",
        "Roboto-Black.ttf",
        "Roboto-Bold.ttf",
        "Roboto-Light.ttf",
        "Roboto-Medium.ttf",
        "Roboto-Regular.ttf",
    ]
    for f in font_files:
        path = os.path.join(font_dir, f)
        if os.path.exists(path):
            QFontDatabase.addApplicationFont(path)


# Đường dẫn ảnh logo — dùng chung ở cả 3 chỗ: avatar bubble, avatar banner, logo widget
_LOGO_PATH = os.path.join("assets", "fooderai-chatbot", "gritalyst-ai-logo.png")


# =====================================================================
# LỚP 4: GRITALYSTAVATAR — LOAD ẢNH PNG THAY VÌ VẼ TAY
# =====================================================================
class GritalystAvatar(QLabel):
    """
    Avatar hình tròn dùng ảnh PNG logo thật.
    Kế thừa QLabel thay vì QWidget vì QLabel có sẵn setPixmap().
    Size mặc định 46px cho header banner, 36px cho bubble chat.
    """
    def __init__(self, size=46, parent=None):
        super().__init__(parent)
        self.setFixedSize(size, size)  # khóa cứng, không cho co giãn
        self.setStyleSheet("border: none; background: transparent;")

        if os.path.exists(_LOGO_PATH):
            # scaledToWidth: scale giữ tỉ lệ theo chiều rộng
            # SmoothTransformation: dùng thuật toán nội suy mịn (chống răng cưa)
            pix = QPixmap(_LOGO_PATH).scaled(
                size, size,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
            self.setPixmap(pix)
            self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        else:
            # Fallback: hiện chữ "G" nếu không tìm thấy file
            self.setText("G")
            self.setAlignment(Qt.AlignmentFlag.AlignCenter)


# =====================================================================
# LỚP 4B: LOGOWIDGET — LOGO 300px + TÊN + SLOGAN (dùng trong chat header)
# Widget này được đặt vào đầu chat_layout để cuộn cùng với tin nhắn
# =====================================================================
class LogoWidget(QWidget):
    """
    Khối logo trung tâm gồm:
    - Ảnh logo tròn 300x300
    - Tên "GritalystAI" font Orbitron Bold màu đen
    - Slogan font Roboto SemiCondensed màu xám

    Đặt vào đầu chat_layout → sẽ cuộn lên khi user nhắn tin.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background: transparent;")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 10, 0, 10) #UPDATE cập nhật
        layout.setSpacing(10)
        layout.setAlignment(Qt.AlignmentFlag.AlignHCenter)

        # --- Ảnh logo 300x300 ---
        lbl_logo = QLabel()
        lbl_logo.setFixedSize(132, 132)
        lbl_logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_logo.setStyleSheet("border: none; background: transparent;")

        if os.path.exists(_LOGO_PATH):
            pix = QPixmap(_LOGO_PATH).scaled(
                132, 132, #kích thước mói: 3.5 cm x 3.5 cm
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
            lbl_logo.setPixmap(pix)
        else:
            lbl_logo.setText("[ Logo ]")  # placeholder nếu file chưa có

        # --- Tên "GritalystAI" — Orbitron Bold, đen, to ---
        lbl_name = QLabel("GritalystAI")
        font_name = QFont("Orbitron")          # họ font đã nạp từ load_gritalyst_fonts()
        font_name.setPixelSize(28)
        font_name.setWeight(QFont.Weight.Bold) # Bold = 700
        lbl_name.setFont(font_name)
        lbl_name.setStyleSheet("color: #111111; border: none; background: transparent;")
        lbl_name.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # --- Slogan — Roboto SemiCondensed, xám nhạt ---
        lbl_slogan = QLabel("Đồng hành sức khỏe — Dinh dưỡng thông minh, mỗi ngày.")
        font_slogan = QFont("Roboto")
        font_slogan.setPixelSize(14)
        font_slogan.setStretch(QFont.Stretch.SemiCondensed)  # ép thành SemiCondensed
        lbl_slogan.setFont(font_slogan)
        lbl_slogan.setStyleSheet("color: #6A8A7A; border: none; background: transparent;")
        lbl_slogan.setAlignment(Qt.AlignmentFlag.AlignCenter)

        layout.addWidget(lbl_logo,    alignment=Qt.AlignmentFlag.AlignHCenter)
        layout.addWidget(lbl_name,    alignment=Qt.AlignmentFlag.AlignHCenter)
        layout.addWidget(lbl_slogan,  alignment=Qt.AlignmentFlag.AlignHCenter)


# =====================================================================
# LỚP 4C: STROKELABEL — QLABEL CÓ VIỀN CHỮ ĐEN (TEXT STROKE)
# =====================================================================
# [UPDATE v1] Thêm mới — thay thế QLabel + QGraphicsDropShadowEffect
# Lý do: QGraphicsDropShadowEffect blur cả widget, không tạo được
# viền sắc nét cho chữ trắng trên nền xanh sáng (#3DE365).
#
# Giải pháp: override paintEvent(), dùng QPainter vẽ 2 lần:
#   Lần 1 — vẽ chữ đen offset 8 hướng (±2px) → tạo viền bao quanh
#   Lần 2 — vẽ chữ trắng đè lên chính giữa → fill bên trong viền
#
# Kết quả: stroke đen rõ nét, không phụ thuộc nền, không cần file CSS
# =====================================================================
class StrokeLabel(QLabel):
    """
    QLabel vẽ chữ có viền đen bằng QPainter.
    Dùng cho tiêu đề GritalystAI trên banner gradient xanh sáng.

    Tham số:
        text         : chuỗi chữ cần hiển thị
        font         : QFont đã set sẵn (pixelSize, weight...)
        stroke_color : QColor màu viền (mặc định đen alpha 210)
        stroke_width : độ dày viền tính bằng px offset (mặc định 2)
    """
    def __init__(self, text: str, font: QFont,
                 stroke_color: QColor = None,
                 stroke_width: int = 2,
                 parent=None):
        super().__init__(text, parent)
        self._font         = font
        self._stroke_color = stroke_color or QColor(0, 0, 0, 210)  # đen 82% đục
        self._stroke_w     = stroke_width
        self.setFont(font)
        self.setStyleSheet("background: transparent; border: none;")

        # Tính kích thước widget vừa đủ chứa chữ + padding stroke
        # horizontalAdvance(): chiều rộng chuỗi theo font hiện tại
        # height(): chiều cao 1 dòng chữ theo font
        from PySide6.QtGui import QFontMetrics
        fm  = QFontMetrics(font)
        pad = stroke_width + 3          # padding = độ dày stroke + 3px đệm mỗi bên (update)
        self.setFixedSize(
            fm.horizontalAdvance(text) + pad * 2,   # width  = chữ + padding 2 bên
            fm.height()                + pad * 2    # height = cao chữ + padding trên/dưới
        )

    def paintEvent(self, event):
        """
        Qt gọi hàm này mỗi khi widget cần vẽ lại.
        Quy trình 2 bước:
          Bước 1 — vẽ chữ đen 8 hướng offset → tạo stroke bao quanh
          Bước 2 — vẽ chữ trắng chính giữa đè lên stroke → fill trắng
        """
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setFont(self._font)

        w = self._stroke_w   # độ rộng offset viền (pixel)

        # --- BƯỚC 1: stroke đen 8 hướng ---
        # 8 hướng: trái/phải/trên/dưới + 4 góc chéo
        # Mỗi hướng offset (dx, dy) pixel so với vị trí chính giữa
        painter.setPen(QPen(self._stroke_color))
        for dx, dy in [
            (-w,  0), ( w,  0),   # trái, phải
            ( 0, -w), ( 0,  w),   # trên, dưới
            (-w, -w), ( w, -w),   # góc trên-trái, góc trên-phải
            (-w,  w), ( w,  w),   # góc dưới-trái, góc dưới-phải
        ]:
            # drawText(x, y, w, h, flags, text):
            # vẽ chữ trong rect (dx, dy, width, height) căn giữa
            painter.drawText(
                dx, dy,
                self.width(), self.height(),
                Qt.AlignmentFlag.AlignCenter,
                self.text()
            )

        # --- BƯỚC 2: fill trắng chính giữa ---
        painter.setPen(QPen(QColor(255, 255, 255)))   # trắng tuyệt đối alpha 255
        painter.drawText(
            0, 0,
            self.width(), self.height(),
            Qt.AlignmentFlag.AlignCenter,
            self.text()
        )
        painter.end()   # bắt buộc gọi end() khi tạo QPainter thủ công


# =====================================================================
# LỚP 5: PAGEAIASSISTANT — TRANG CHÍNH GHÉP TẤT CẢ LẠI
# =====================================================================
class PageAIAssistant(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(1240, 640)  # kích thước cố định khớp với feature_stack trong main

        # Khởi tạo bộ bảo vệ NSFW — dùng xuyên suốt phiên chat
        self.guard = NSFWGuard()

        # Lich su chat gui kem moi lan goi Gemini API
        # Cau truc: [{"role": "user", "parts": ["cau hoi"]}, {"role": "model", "parts": ["tra loi"]}, ...]
        # Gioi han toi da 30 tin (15 cap) de tranh ton qua nhieu token
        self._chat_history: list = []

        # Giu reference den worker dang chay
        # → Tranh Python garbage-collect thread truoc khi no xong viec
        self._current_worker = None

        # Style cho toàn bộ trang: nền trắng, viền teal mờ, góc bo 24px
        self.setStyleSheet("""
            PageAIAssistant {
                background-color: white;
                border: 3px solid rgba(0, 77, 77, 0.5);
                border-radius: 24px;
            }
        """)

        # Đổ bóng nhẹ cho cả trang để nổi lên trên nền app
        box_shadow = QGraphicsDropShadowEffect()
        box_shadow.setBlurRadius(5)
        box_shadow.setOffset(0, 3)               # bóng lệch xuống 3px
        box_shadow.setColor(QColor(150, 150, 150, 180))
        self.setGraphicsEffect(box_shadow)

        # Layout dọc chính: Banner → Vùng chat → Thanh nhập
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(15, 6, 15, 6)
        main_layout.setSpacing(4)  # khoảng cách giữa 3 vùng # cho nhỏ lại

        # ===========================================================
        # PHẦN 1: BANNER GRITALYSTAI
        # ===========================================================
        self.banner = QFrame()
        self.banner.setFixedSize(1210, 70)  # rộng hết trang, cao 70px

        # Tính màu gradient động từ màu gốc #3DE365
        color_hex = "#3DE365"
        base_color = QColor(color_hex)
        color_80  = base_color.darker(108).name()  # tối hơn 8% → dùng cho stop giữa
        color_100 = base_color.darker(124).name()  # tối hơn 24% → dùng cho stop cuối

        # Gradient chạy từ trái-giữa (x1:0, y1:0.2) sang phải-dưới (x2:1, y2:1)
        # y1:0.2 thay vì 0 để gradient không bắt đầu từ góc trên-trái mà từ giữa-trái
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

        # Bóng nhẹ phía dưới banner
        banner_shadow = QGraphicsDropShadowEffect()
        banner_shadow.setBlurRadius(6)
        banner_shadow.setOffset(0, 2)
        banner_shadow.setColor(QColor(0, 0, 0, 160))
        self.banner.setGraphicsEffect(banner_shadow)

        # Layout ngang bên trong banner: [Avatar] [Tên + Subtitle] [---stretch---]
        banner_layout = QHBoxLayout(self.banner)
        banner_layout.setContentsMargins(8, 0, 8, 0)
        banner_layout.setSpacing(12)

        # Avatar hình tròn chữ G — size 46px cho header
        self.avatar_header = GritalystAvatar(size=46)

        # [UPDATE] Thay QLabel thường bằng StrokeLabel để có viền đen rõ nét
        # QGraphicsDropShadowEffect không hoạt động tốt với chữ trắng trên nền xanh sáng
        # → dùng QPainter vẽ thủ công: stroke đen trước, fill trắng đè lên sau
        font_name = QFont("Orbitron")
        font_name.setPixelSize(25)
        font_name.setWeight(QFont.Weight.Bold)
        # Dòng tạo StrokeLabel trong banner — đổi stroke_width từ 2 → 1
        lbl_name = StrokeLabel("GritalystAI", font_name, stroke_width=1)

        # Ghép vào banner: Avatar → tên (căn giữa dọc) → stretch
        banner_layout.addWidget(self.avatar_header, alignment=Qt.AlignmentFlag.AlignVCenter)
        banner_layout.addWidget(lbl_name, alignment=Qt.AlignmentFlag.AlignVCenter)
        banner_layout.addStretch()

        # ── NÚT RESET CHAT — góc phải banner ─────────────────────────
        # Tạo chat mới: xóa toàn bộ bubble UI + lịch sử Gemini + log DB
        # Dùng QPushButton hình tròn với icon bút/tờ giấy
        self.btn_reset = QPushButton()
        self.btn_reset.setFixedSize(42, 42)
        self.btn_reset.setToolTip("Tạo cuộc trò chuyện mới")
        self.btn_reset.setCursor(Qt.CursorShape.PointingHandCursor)

        # Icon: dùng emoji ✏️ hoặc file PNG nếu có
        _reset_icon = os.path.join("assets", "fooderai-chatbot", "reset-chat.png")
        if os.path.exists(_reset_icon):
            self.btn_reset.setIcon(QIcon(_reset_icon))
            self.btn_reset.setIconSize(QSize(36, 36))
        else:
            # Fallback: dùng text ký hiệu
            self.btn_reset.setText("✦")
            font_r = QFont("Roboto")
            font_r.setPixelSize(18)
            self.btn_reset.setFont(font_r)

        self.btn_reset.setStyleSheet("""
            QPushButton {
                background-color: rgba(255, 255, 255, 0.25);
                border-radius: 21px;
                border: 1.5px solid rgba(255, 255, 255, 0.6);
                color: white;
            }
            QPushButton:hover   { background-color: rgba(255, 255, 255, 0.40); }
            QPushButton:pressed { background-color: rgba(255, 255, 255, 0.15); }
        """)
        self.btn_reset.clicked.connect(self._reset_chat)
        banner_layout.addWidget(self.btn_reset, alignment=Qt.AlignmentFlag.AlignVCenter)

        #update: for get a freedom strech
        main_layout.addWidget(self.banner)
        self.banner.setContentsMargins(0, 0, 0, 0)

        # ===========================================================
        # PHẦN 2: VÙNG CHAT (ScrollArea + Overlay bịt mõm)
        # ===========================================================

        # Container trong suốt bao quanh scroll — dùng để overlay bịt mõm biết phủ vào đâu
        self.chat_container = QFrame()
        self.chat_container.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.chat_container.setStyleSheet("QFrame { background: transparent; border: none; }")

        container_layout = QVBoxLayout(self.chat_container)
        container_layout.setContentsMargins(0, 0, 0, 0)

        # ScrollArea: tự thêm thanh scroll khi nội dung dài hơn khung
        # setWidgetResizable(True): widget bên trong co giãn theo khung scroll
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setStyleSheet("""
            QScrollArea { background: transparent; border: none; }
            QScrollBar:vertical {
                width: 6px;                  /* thanh scroll mỏng 6px */
                background: #F0F0F0;
                border-radius: 3px;
            }
            QScrollBar::handle:vertical {
                background: #3DE365;         /* tay cầm màu xanh lá */
                border-radius: 3px;
                min-height: 20px;            /* tối thiểu 20px để dễ kéo */
            }
            QScrollBar::add-line:vertical,
            QScrollBar::sub-line:vertical { height: 0; }  /* ẩn nút mũi tên */
        """)

        # Widget thật chứa các bubble — nằm bên trong ScrollArea
        self.chat_widget = QWidget()
        self.chat_widget.setStyleSheet("background: transparent;")

        self.chat_layout = QVBoxLayout(self.chat_widget)
        self.chat_layout.setContentsMargins(30, 0, 30, 3)  # [UPDATE] 10 → 30px mỗi bên
        self.chat_layout.setSpacing(3)
        self.chat_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        # LogoWidget nằm TRONG chat_layout → cuộn cùng với các bubble
        # Khi user nhắn tin nhiều, logo tự cuộn lên trên và biến mất như ChatGPT
        self.logo_widget = LogoWidget()
        self.chat_layout.addWidget(self.logo_widget,
                                   alignment=Qt.AlignmentFlag.AlignHCenter)  # ← vào đây

        self.scroll_area.setWidget(self.chat_widget)
        container_layout.addWidget(self.scroll_area)

        # BUG FIX: Đã XÓA dòng self.mute_overlay = MuteOverlay(...)
        # MuteOverlay (overlay phủ màn hình cũ) không còn dùng nữa —
        # đã thay bằng SystemNoticeCard inline trong chat_layout.
        # Nếu để lại: widget vô hình vẫn được tạo, chiếm memory,
        # và có thể intercept mouse event do nằm trên layer trên cùng.

        # Tham số "1" ở đây là stretch factor — vùng chat chiếm hết phần còn lại sau banner và input
        main_layout.addWidget(self.chat_container, 1)

        # ===========================================================
        # PHẦN 3: THANH NHẬP CHAT (Input + Nút gửi)
        # ===========================================================
        input_row = QHBoxLayout()
        input_row.setSpacing(10)         # khoảng cách giữa ô nhập và nút gửi
        input_row.setContentsMargins(0, 0, 0, 0)

        # Ô nhập liệu
        self.input_box = QLineEdit()
        self.input_box.setPlaceholderText("Nhắn gì đó với Gritalyst...")
        self.input_box.setFixedHeight(50)
        self.input_box.setMaxLength(450)  # giới hạn 450 ký tự, ngăn spam dài

        font_input = QFont("Roboto")
        font_input.setPixelSize(15)
        self.input_box.setFont(font_input)

        # Style capsule (bo tròn 2 đầu bằng border-radius bằng nửa chiều cao)
        self.input_box.setStyleSheet("""
            QLineEdit {
                background-color: rgba(255, 255, 255, 0.92);
                color: #1A2A3A;
                border-radius: 25px;
                border: 2px solid rgba(61, 227, 101, 0.5);
                padding: 0px 20px;
            }
            QLineEdit:focus {
                border: 2px solid #3DE365;   /* viền sáng lên khi đang gõ */
                background-color: #FFFFFF;
            }
        """)

        # Glow xanh nhẹ cho ô nhập — QColor(61, 227, 101, 90) là màu RGBA
        # 61,227,101 = #3DE365 viết theo số thập phân; 90 = alpha (35% trong suốt)
        shadow_input = QGraphicsDropShadowEffect()
        shadow_input.setBlurRadius(18)
        shadow_input.setOffset(0, 4)
        shadow_input.setColor(QColor(61, 227, 101, 90))
        self.input_box.setGraphicsEffect(shadow_input)

        # Nút gửi — hình tròn 50x50, không có chữ, chỉ có icon mũi tên
        self.btn_send = QPushButton()
        self.btn_send.setFixedSize(50, 50)  # width = height → hình tròn khi border-radius = 25

        # Nạp icon từ file PNG — nếu không tìm thấy thì nút vẫn chạy, chỉ không có icon
        icon_path = os.path.join("assets", "fooderai-chatbot", "fooderai-ai-submit.png")
        if os.path.exists(icon_path):
            self.btn_send.setIcon(QIcon(icon_path))
            self.btn_send.setIconSize(QSize(28, 28))  # icon 28px nằm giữa nút 50px

        # Gradient chạy chéo 45° từ trên-trái → dưới-phải (x1:0,y1:0 → x2:1,y2:1)
        self.btn_send.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 #3DE365, stop:0.75 #2FC455, stop:1.0 #27A849);
                border-radius: 25px;   /* = nửa chiều cao → hình tròn hoàn hảo */
                border: none;
            }
            QPushButton:hover   { background: #4AEF70; }   /* sáng hơn khi hover */
            QPushButton:pressed { background: #27A849; }   /* tối hơn khi nhấn */
        """)

        # Bóng xanh cho nút gửi — màu lấy từ #27A849 viết dạng RGBA
        # BUG FIX: lưu vào self._shadow_btn thay vì local variable shadow_btn
        # Lý do: _lock_input() cần gọi setGraphicsEffect(None) để xóa shadow này
        # trước khi đổi stylesheet xám. Nếu chỉ là local var thì sau __init__
        # biến mất khỏi scope nhưng Qt vẫn giữ reference nội bộ — setGraphicsEffect(None)
        # trên widget vẫn hoạt động đúng. Lưu vào self để dễ debug sau này.
        self._shadow_btn = QGraphicsDropShadowEffect()
        self._shadow_btn.setBlurRadius(14)
        self._shadow_btn.setOffset(0, 4)
        self._shadow_btn.setColor(QColor(39, 168, 73, 160))
        self.btn_send.setGraphicsEffect(self._shadow_btn)

        # Khi chuột di vào nút → con trỏ đổi thành bàn tay 👆
        self.btn_send.setCursor(Qt.CursorShape.PointingHandCursor)

        input_row.addWidget(self.input_box, 1)  # stretch=1 → ô nhập chiếm hết phần còn lại
        input_row.addWidget(self.btn_send)       # nút gửi kích thước cố định, không co giãn
        main_layout.addLayout(input_row)

        # Kết nối signal → slot:
        # clicked = signal phát ra khi nhấn nút chuột
        # returnPressed = signal phát ra khi nhấn phím Enter trong QLineEdit
        # Cả 2 đều dẫn đến cùng 1 hàm _send_message — không cần viết 2 hàm riêng
        self.btn_send.clicked.connect(self._send_message)
        self.input_box.returnPressed.connect(self._send_message)

        # Tin nhắn chào mừng tự động khi mở trang
        self._add_bot_bubble("Chào bạn! Tôi là GritalystAI — trợ lý dinh dưỡng và thể dục của bạn. Tôi có thể giúp gì cho bạn hôm nay? 🌿")

    def resizeEvent(self, event):
        """
        Qt tự gọi hàm này mỗi khi widget thay đổi kích thước.
        BUG FIX: Đã xóa block check mute_overlay vì MuteOverlay (lớp overlay cũ)
        không còn được khởi tạo trong __init__ nữa — đã thay bằng SystemNoticeCard
        inline trong chat. Giữ lại resizeEvent nhưng chỉ gọi super() để tránh
        AttributeError khi Qt resize widget lần đầu.
        """
        super().resizeEvent(event)

    def _reset_chat(self):
        """
        Tạo cuộc trò chuyện mới — xóa sạch 3 thứ:
          1. UI: xóa toàn bộ bubble trong chat_layout (giữ lại logo_widget)
          2. RAM: reset _chat_history → Gemini mất ngữ cảnh cũ
          3. DB: DELETE gritalyst_log WHERE session_id = ? → log cũ biến mất

        Tại sao xóa cả 3?
        → Chỉ xóa UI: bubble hết nhưng Gemini vẫn nhớ ngữ cảnh → không thật sự "mới"
        → Chỉ xóa RAM: bubble cũ vẫn hiển thị → user nhầm tưởng còn lịch sử
        → Chỉ xóa DB: lần sau mở app vẫn load lại được → không triệt để
        → Xóa cả 3: trải nghiệm "tờ giấy trắng" thật sự
        """
        # Bước 1: Xóa toàn bộ widget trong chat_layout TRỪ logo_widget
        # Lấy danh sách tất cả widget con, xóa từng cái
        # Dùng reversed() để xóa từ cuối lên — tránh index shift khi xóa giữa chừng
        while self.chat_layout.count() > 0:
            item = self.chat_layout.takeAt(0)
            if item and item.widget():
                w = item.widget()
                if w is self.logo_widget:
                    # Giữ lại logo, đặt lại vào layout
                    self.chat_layout.addWidget(w, alignment=Qt.AlignmentFlag.AlignHCenter)
                    continue
                w.setParent(None)
                w.deleteLater()

        # Bước 2: Reset lịch sử chat trong RAM
        # → Gemini sẽ không còn nhớ gì từ cuộc trò chuyện trước
        self._chat_history.clear()

        # Bước 3: Xóa log DB
        if _DB_AVAILABLE and self.guard.session_id:
            try:
                reset_chat_history(self.guard.session_id)
            except Exception:
                pass  # DB lỗi → vẫn reset UI và RAM, chỉ log cũ còn trong DB

        # Bước 4: Hiện lại bubble chào mừng
        self._add_bot_bubble(
            "Cuộc trò chuyện mới bắt đầu! 🌿 Tôi có thể giúp gì cho bạn hôm nay?"
        )

    def _add_bot_bubble(self, text: str):
        """Thêm 1 tin nhắn của Gritalyst vào cuối danh sách chat (căn trái)."""
        row = QHBoxLayout()
        row.setSpacing(8)
        row.setContentsMargins(0, 0, 0, 0)

        avatar = GritalystAvatar(size=36)
        bubble = ChatBubble(text, is_user=False)

        # AlignTop: avatar căn trên dù bubble cao bao nhiêu
        row.addWidget(avatar, alignment=Qt.AlignmentFlag.AlignTop)
        # AlignLeft | AlignTop: bubble dính trái, không stretch, không bóp
        row.addWidget(bubble, alignment=Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        row.addStretch()  # đẩy toàn bộ cụm avatar+bubble sang trái

        wrapper = QWidget()
        wrapper.setStyleSheet("background: transparent;")
        wrapper.setLayout(row)
        self.chat_layout.addWidget(wrapper)
        self._scroll_to_bottom()

    def _add_user_bubble(self, text: str):
        """Thêm 1 tin nhắn của user vào cuối danh sách chat (căn phải)."""
        row = QHBoxLayout()
        row.setSpacing(0)
        row.setContentsMargins(0, 0, 0, 0)

        bubble = ChatBubble(text, is_user=True)

        row.addStretch()  # đẩy bubble sang phải
        # AlignRight | AlignTop: bubble dính phải, không stretch, không bóp
        row.addWidget(bubble, alignment=Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop)

        wrapper = QWidget()
        wrapper.setStyleSheet("background: transparent;")
        wrapper.setLayout(row)
        self.chat_layout.addWidget(wrapper)
        self._scroll_to_bottom()

    def _add_typing_bubble(self) -> QWidget:
        """
        Hien GIF loading trong luc cho Gemini tra loi.

        Tra ve wrapper QWidget de sau nay co the xoa khi Gemini tra loi xong:
            typing_w = self._add_typing_bubble()   # hien GIF loading
            # ... goi API ngam ...
            typing_w.setParent(None)               # xoa khi co tra loi that
            typing_w.deleteLater()                 # giai phong bo nho
        """
        import os
        from PySide6.QtGui import QMovie
        from PySide6.QtWidgets import QLabel

        row = QHBoxLayout()
        row.setSpacing(8)
        row.setContentsMargins(0, 4, 0, 4)

        avatar = GritalystAvatar(size=36)

        # Tìm file GIF theo đường dẫn tương đối từ vị trí file page_ai.py
        # page_ai.py nằm trong pages/ → đi lên 1 cấp → vào assets/fooderai-chatbot/
        _here    = os.path.dirname(os.path.abspath(__file__))
        gif_path = os.path.join(_here, "..", "assets", "fooderai-chatbot", "fdai-response-loading.gif")
        gif_path = os.path.normpath(gif_path)  # chuẩn hóa đường dẫn, bỏ ../

        gif_label = QLabel()
        gif_label.setStyleSheet("background: transparent;")

        if os.path.exists(gif_path):
            # File GIF tồn tại → chạy animation
            movie = QMovie(gif_path)
            movie.setScaledSize(QSize(200, 28))  # scale vừa bubble, giữ tỉ lệ
            gif_label.setMovie(movie)
            movie.start()
            # Giữ reference để Python không garbage-collect movie
            # trong khi nó vẫn đang chạy
            gif_label._movie = movie
        else:
            # Fallback: nếu không tìm thấy GIF thì hiện chữ bình thường
            gif_label.setText("GritalystAI đang soạn câu trả lời...")
            gif_label.setStyleSheet("color: #555; font-style: italic; background: transparent;")

        row.addWidget(avatar, alignment=Qt.AlignmentFlag.AlignVCenter)
        row.addWidget(gif_label, alignment=Qt.AlignmentFlag.AlignVCenter)
        row.addStretch()

        wrapper = QWidget()
        wrapper.setStyleSheet("background: transparent;")
        wrapper.setLayout(row)
        self.chat_layout.addWidget(wrapper)
        self._scroll_to_bottom()
        return wrapper  # tra ve de caller co the xoa sau

    def _add_system_notice(self, notice_type: str):
        """
        Thêm thẻ thông báo hệ thống (SystemNoticeCard) vào chat như 1 tin nhắn,
        sau đó tự xóa sau 10 giây.
        Add a system notice card to chat as a message, then auto-remove after 10s.

        Cơ chế hoạt động (How it works):
          1. Tạo card + wrapper → addWidget vào chat_layout (hiện ngay trong chat)
          2. Scroll xuống cuối (200ms delay cho Qt tính lại layout)
          3. Lock input (disable Enter + btn_send)
          4. QTimer.singleShot(10000ms) → sau 10 giây gọi lambda xóa wrapper

        Tại sao xóa wrapper thay vì xóa card?
          card nằm BÊN TRONG wrapper (wrapper là QWidget bọc ngoài để căn giữa).
          Nếu chỉ xóa card: wrapper rỗng vẫn còn trong layout → chiếm khoảng trống.
          Xóa wrapper: xóa cả card lẫn khoảng trống → layout gọn lại hoàn toàn.

        Tại sao dùng setParent(None) thay vì deleteLater()?
          deleteLater(): Qt đánh dấu widget để xóa ở event loop tiếp theo — an toàn
          nhưng widget vẫn còn nhìn thấy 1 frame trước khi biến mất.
          setParent(None): tách widget ra khỏi layout ngay lập tức, ẩn luôn.
          Sau đó gọi deleteLater() để giải phóng bộ nhớ đúng cách.
          Kết hợp 2 cách: ẩn ngay + dọn memory sau → tốt nhất.

        Tại sao KHÔNG unlock input sau khi card biến mất?
          Card biến mất chỉ là UI — trạng thái mute/quota vẫn còn trong NSFWGuard.
          Unlock input phải chờ timer thật (muted_until hoặc reset_at) hết hạn.
          Card chỉ là thông báo tạm, không phải điều kiện để unlock.

        notice_type: 'quota' = hết 50 tin | 'mute' = bị khóa NSFW
        AUTO_REMOVE_MS: 10000ms = 10 giây — đủ để user đọc thông báo
        """
        # Card giữ đến khi hết giờ thật — quota 4 tiếng, mute 8 tiếng
        if notice_type == "quota" and self.guard.reset_at:
            delta = self.guard.reset_at - datetime.now()
        elif notice_type == "mute" and self.guard.muted_until:
            delta = self.guard.muted_until - datetime.now()
        else:
            delta = timedelta(hours=4 if notice_type == "quota" else 8)
        AUTO_REMOVE_MS = max(5000, int(delta.total_seconds() * 1000))

        card = SystemNoticeCard(notice_type, guard=self.guard)

        # wrapper full width — không addStretch, card tự Expanding
        wrapper = QWidget()
        wrapper.setStyleSheet("background: transparent;")
        row = QHBoxLayout(wrapper)
        row.setContentsMargins(8, 8, 8, 8)  # 8px mỗi bên — chữ không bị sát viền
        row.addWidget(card)

        self.chat_layout.addWidget(wrapper)

        QTimer.singleShot(200, lambda: self.scroll_area.verticalScrollBar().setValue(
            self.scroll_area.verticalScrollBar().maximum()
        ))

        self._lock_input()

        # Auto-remove sau 10s → unlock nếu can_send() OK
        def _on_card_expired():
            wrapper.setParent(None)
            wrapper.deleteLater()
            ok, _ = self.guard.can_send()
            if ok:
                self._unlock_input()

        QTimer.singleShot(AUTO_REMOVE_MS, _on_card_expired)

    def _scroll_to_bottom(self):
        """
        Cuộn ScrollArea xuống tin nhắn mới nhất.
        Dùng QTimer.singleShot(50ms) vì layout cần thêm 1 chút thời gian
        để tính toán chiều cao bubble mới trước khi biết vị trí maximum.
        """
        QTimer.singleShot(50, lambda: self.scroll_area.verticalScrollBar().setValue(
            self.scroll_area.verticalScrollBar().maximum()
        ))

    def _send_message(self):
        """
        Hàm xử lý chính khi user gửi tin — được gọi từ cả nút Gửi lẫn phím Enter.

        Luồng xử lý:
        1. Lấy text, bỏ qua nếu trống
        2. Xóa ô nhập + hiện bubble user ngay lập tức
        3. Hỏi NSFWGuard xem có được gửi không
        4. Nếu bị chặn (quota/mute): dùng QTimer.singleShot(0) để hiện
           SystemNoticeCard VÀ lock input SAU KHI hàm này return xong.
           → Tại sao phải singleShot(0)?
             _lock_input() gọi btn_send.clicked.disconnect() ngay trong lúc
             signal clicked đang kích hoạt hàm này → Qt phát warning và card
             không render kịp. singleShot(0) đẩy việc đó ra event loop tiếp theo,
             đảm bảo hàm hiện tại đã return hoàn toàn trước khi disconnect.
        5. Nếu OK: kiểm tra NSFW → phản hồi tương ứng → cập nhật nút
        """
        text = self.input_box.text().strip()  # strip() xóa khoảng trắng 2 đầu
        if not text:
            return  # không làm gì nếu ô trống

        # Xóa ô nhập + hiện bubble user ngay — trước khi kiểm tra bất kỳ thứ gì
        # BUG FIX: xóa dòng self.input_box.clear() thừa ở dưới (dòng cũ 789)
        # Trước đây có 2 lần clear(): 1 ở đây và 1 sau block "if not ok" →
        # nếu ok=False thì clear() chạy 2 lần (không hại nhưng thừa và confusing)
        self.input_box.clear()
        self._add_user_bubble(text)

        # Cổng kiểm tra — NSFWGuard quyết định có cho gửi không
        ok, reason = self.guard.can_send()

        if not ok:
            if reason == "muted":
                self._add_system_notice("mute")
            else:
                self._add_system_notice("quota")
            return

        # Kiểm tra NSFW bằng từ khóa đơn giản
        # any() trả về True nếu có ÍT NHẤT 1 từ trong list xuất hiện trong text
        # text.lower() để tìm không phân biệt hoa thường
        nsfw_words = [
            # Từ tục trực tiếp
            "cặc", "cu", "lồn", "địt", "đéo", "đĩ", "cave", "điếm",
            "dâm", "thủ dâm", "xuất tinh", "đụ",
            # Viết tắt
            "cc", "đcm", "đcmm", "đm", "clm", "vcl",
            # Cụm tục
            "địt con mẹ", "đụ má mày", "có cái lồn",
            "cái lồn mẹ mày", "con đĩ mẹ",
        ]
        is_nsfw = any(w in text.lower() for w in nsfw_words)

        if is_nsfw:
            reply, cost = self.guard.record_nsfw()
            if reply == "__muted__":
                self._add_system_notice("mute")
                return
            else:
                self._add_bot_bubble(reply)
        else:
            # ─────────────────────────────────────────────────────────────────
            # BUOC 1: Ghi nhan tin sach (tru 1 xu quota)
            # ─────────────────────────────────────────────────────────────────
            self.guard.record_clean()

            # BUOC 2: Hien bubble "dang go..." ngay lap tuc
            # → User thay phan hoi tuc thi, khong tuong app bi do
            typing_wrapper = self._add_typing_bubble()

            # BUOC 3: Lay user_profile tu DB de Gemini ca nhan hoa cau tra loi
            # VD: user co BMI=28 → Gemini tu van an it calo hon
            _profile = None
            if _DB_AVAILABLE:
                try:
                    from fooder_database import get_user_profile
                    _profile = get_user_profile(self.guard.session_id)
                except Exception:
                    pass  # khong co profile → Gemini van tra loi, chi khong ca nhan hoa

            # BUOC 4: Tao GeminiWorker va chay tren thread rieng
            # text = cau hoi user vua go (da luu o dau _send_message)
            self._current_worker = GeminiWorker(
                user_message  = text,
                chat_history  = self._chat_history,   # truyen lich su vao de Gemini nho
                user_profile  = _profile,
                session_id    = self.guard.session_id,
                user_id       = None,  # sau nay co login thi truyen user_id that vao
            )

            # BUOC 5: Dinh nghia ham callback chay khi Gemini tra ve ket qua
            # Dung closure de "bao" typing_wrapper va text vao trong ham nay
            def _on_gemini_reply(reply: str):
                # 5a: Xoa bubble "dang go..." — thay bang cau tra loi that
                # setParent(None): tach khoi layout ngay lap tuc → an di
                # deleteLater(): giai phong bo nho o event loop sau
                typing_wrapper.setParent(None)
                typing_wrapper.deleteLater()

                # 5b: Hien cau tra loi that cua Gemini
                self._add_bot_bubble(reply)

                # 5c: Luu cap hoi-dap vao lich su de Gemini nho o lan tiep theo
                self._chat_history.append({"role": "user",  "parts": [text]})
                self._chat_history.append({"role": "model", "parts": [reply]})

                # 5d: Gioi han lich su toi da 30 tin (15 cap hoi-dap)
                # Sliding window: xoa 2 tin cu nhat khi vuot nguong
                # → Tranh gui qua nhieu token → ton tien + cham hon
                MAX_HISTORY = 30
                if len(self._chat_history) > MAX_HISTORY:
                    del self._chat_history[0:2]  # xoa 1 cap (user + model) cu nhat

                # 5e: [FIX] Kiem tra quota SAU KHI bot da reply
                # Bot reply truoc → notice card chen ngay ben duoi sau 300ms
                if self.guard.msg_count >= self.guard.MAX_MSGS:
                    QTimer.singleShot(300, lambda: self._add_system_notice("quota"))
                    return

                # 5f: Cap nhat trang thai nut gui
                self._update_send_button()

            # BUOC 6: Ket noi signal finished → callback _on_gemini_reply
            # Khi GeminiWorker goi self.finished.emit(reply) → Qt goi _on_gemini_reply(reply)
            self._current_worker.finished.connect(_on_gemini_reply)

            # BUOC 7: Khoi dong thread — Qt tu goi run() tren thread rieng
            self._current_worker.start()

            # BUOC 8: return som — quota check da duoc chuyen vao _on_gemini_reply
            return

    def _show_mute_overlay(self):
        """
        Thay vì bubble AI, hiện SystemNoticeCard kiểu 'mute' trong chat.
        - Không có icon Gritalyst vì đây là thông báo hệ thống
        - _lock_input() được gọi bên trong _add_system_notice
        """
        self._add_system_notice("mute")

    def _lock_input(self):
        """
        Khóa hoàn toàn thanh nhập sau khi hiện SystemNoticeCard.
        - User vẫn gõ chữ trong ô input được (QLineEdit không bị disable)
        - Nhưng Enter bị ngắt → không gửi được
        - Nút gửi bị vô hiệu hóa + xám + cursor gạch chéo (ForbiddenCursor)

        Tại sao KHÔNG setEnabled(False) trên input_box?
        - Nếu disable input_box, ô sẽ xám xịt và user không gõ được gì,
          trông như app bị treo — trải nghiệm không tốt.
        - Thay vào đó: cho gõ thoải mái nhưng Enter/nút không phản hồi
          → user hiểu rõ "tôi vẫn ở đây, nhưng hệ thống đang chờ".

        Cursor ForbiddenCursor vs file .cur/.ico?
        - Qt.CursorShape.ForbiddenCursor = con trỏ ⊘ built-in của hệ điều hành
        - Ưu điểm: không cần file ngoài, hiển thị đúng trên Windows/macOS/Linux
        - Nếu muốn dùng file tùy chỉnh: dùng QCursor(QPixmap("path/prohibited.cur"))
          NOTE: Windows hỗ trợ cả .ico và .cur; macOS/Linux chỉ dùng QPixmap PNG
          → Khuyến nghị: dùng PNG 32x32 với điểm hotspot (16,16) cho đa nền tảng
          → assets/fooderai-chatbot/prohibited-cursor.png (nếu muốn customize sau)
        """
        # Ngắt Enter
        try:
            self.input_box.returnPressed.disconnect(self._send_message)
        except RuntimeError:
            pass

        # Ngắt click nút gửi
        try:
            self.btn_send.clicked.disconnect(self._send_message)
        except RuntimeError:
            pass

        # Xóa shadow để stylesheet xám hiển thị đúng (Qt 1 widget = 1 effect)
        self.btn_send.setGraphicsEffect(None)

        # Disable nút
        self.btn_send.setEnabled(False)

        # Cursor từ file — QPixmap KHÔNG đọc được .cur binary trực tiếp.
        # Qt trên Windows load .cur thông qua WinAPI, không qua QPixmap.
        # Giải pháp đúng: dùng file .png cùng thư mục (prohibited-cursor.cur.png)
        # vì QPixmap đọc PNG bình thường và QCursor nhận QPixmap.
        # Thứ tự ưu tiên: PNG → ForbiddenCursor built-in
        _png_path = os.path.join("assets", "fooderai-chatbot", "prohibited-cursor.cur.png")
        _cur_path = os.path.join("assets", "fooderai-chatbot", "prohibited-cursor.cur")
        if os.path.exists(_png_path):
            _pix = QPixmap(_png_path)
            # hotspot (0,0): điểm tác động góc trên-trái — phù hợp icon dạng gạch chéo
            # đổi thành (16,16) nếu muốn điểm tác động nằm chính giữa icon 32x32
            self.btn_send.setCursor(QCursor(_pix, 0, 0))
        elif os.path.exists(_cur_path):
            # Thử load .cur — hoạt động nếu Qt build với WinAPI cursor support
            _pix = QPixmap(_cur_path)
            if not _pix.isNull():
                self.btn_send.setCursor(QCursor(_pix, 0, 0))
            else:
                self.btn_send.setCursor(Qt.CursorShape.ForbiddenCursor)
        else:
            self.btn_send.setCursor(Qt.CursorShape.ForbiddenCursor)

        # Nút xám desaturate — giữ nguyên icon mũi tên, chỉ đổi nền
        self.btn_send.setStyleSheet("""
            QPushButton {
                background-color: #909090;
                border-radius: 25px;
                border: none;
            }
            QPushButton:disabled { background-color: #909090; }
        """)

    def _unlock_input(self):
        """Mở khóa thanh nhập sau khi card biến mất và can_send() = True."""
        try:
            self.input_box.returnPressed.disconnect(self._send_message)
        except RuntimeError:
            pass
        self.input_box.returnPressed.connect(self._send_message)
        try:
            self.btn_send.clicked.disconnect(self._send_message)
        except RuntimeError:
            pass
        self.btn_send.clicked.connect(self._send_message)
        self.btn_send.setEnabled(True)
        self.btn_send.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_send.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 #3DE365, stop:0.75 #2FC455, stop:1.0 #27A849);
                border-radius: 25px; border: none;
            }
            QPushButton:hover   { background: #4AEF70; }
            QPushButton:pressed { background: #27A849; }
        """)
        self._shadow_btn = QGraphicsDropShadowEffect()
        self._shadow_btn.setBlurRadius(14)
        self._shadow_btn.setOffset(0, 4)
        self._shadow_btn.setColor(QColor(39, 168, 73, 160))
        self.btn_send.setGraphicsEffect(self._shadow_btn)

    def _update_send_button(self):
        """
        Cập nhật trạng thái nút gửi + phím Enter sau mỗi lần gửi tin.
        Gọi sau mỗi _send_message() để đồng bộ UI với trạng thái NSFWGuard.

        Lưu ý: khi _lock_input() đã được gọi (quota/mute), hàm này chỉ
        đảm bảo trạng thái đúng chứ không unlock — unlock chỉ xảy ra
        khi quota được reset (sau RESET_HOURS) hoặc mute hết hạn.

        Tại sao KHÔNG dùng blockSignals(True) cho input_box?
        - blockSignals(True) tắt TẤT CẢ signal của widget đó,
          bao gồm cả textChanged, textEdited... có thể gây side effect
          nếu sau này ta cần lắng nghe các signal đó (ví dụ: đếm ký tự).
        - Thay vào đó, ta disconnect() ĐÚNG signal cần chặn (returnPressed)
          và connect() lại khi cần — phẫu thuật chính xác, không ảnh hưởng gì khác.

        Tại sao dùng try/except quanh disconnect()?
        - disconnect() trong Qt sẽ ném RuntimeError nếu signal đó
          chưa được connect hoặc đã bị disconnect trước đó.
        - Dùng try/except để bỏ qua lỗi đó một cách an toàn —
          vì ta chỉ cần "chắc chắn nó đã bị ngắt", không cần biết
          nó có đang kết nối hay không.

        Tại sao phải setGraphicsEffect(None) trước khi đổi stylesheet?
        - Qt chỉ cho mỗi widget giữ ĐÚNG 1 GraphicsEffect tại 1 thời điểm.
        - shadow_btn đang chiếm slot đó từ lúc khởi tạo.
        - Nếu không xóa shadow trước, stylesheet màu xám sẽ bị shadow
          override và không có tác dụng trực quan.
        - setGraphicsEffect(None) giải phóng slot → stylesheet mới
          được Qt render đúng.
        """
        # Nếu đang bị mute (NSFW) → giữ locked
        if self.guard.is_muted():
            self._lock_input()
            return

        quota_ok = self.guard.msg_count < self.guard.MAX_MSGS

        if quota_ok:
            # ===========================================================
            # CÒN LƯỢT — khôi phục toàn bộ về trạng thái hoạt động
            # ===========================================================

            # Bước 1: Kết nối lại phím Enter → _send_message.
            # disconnect() trước để tránh connect() bị gọi 2 lần
            # (nếu connect 2 lần thì 1 lần Enter sẽ gọi _send_message 2 lần!).
            # try/except để bỏ qua nếu chưa từng bị disconnect.
            try:
                self.input_box.returnPressed.disconnect(self._send_message)
            except RuntimeError:
                pass  # chưa bị disconnect → không cần làm gì
            self.input_box.returnPressed.connect(self._send_message)

            # Bước 2: Bật lại nút gửi — setEnabled(True) cho phép click
            self.btn_send.setEnabled(True)

            # Bước 3: Con trỏ bàn tay 👆 khi hover vào nút
            self.btn_send.setCursor(Qt.CursorShape.PointingHandCursor)

            # Bước 4: Khôi phục màu gradient xanh lá ban đầu
            self.btn_send.setStyleSheet("""
                    QPushButton {
                        background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                            stop:0 #3DE365, stop:0.75 #2FC455, stop:1.0 #27A849);
                        border-radius: 25px;
                        border: none;
                    }
                    QPushButton:hover   { background: #4AEF70; }
                    QPushButton:pressed { background: #27A849; }
                """)

        else:
            # ===========================================================
            # HẾT LƯỢT hoặc bị MUTE — ủy quyền toàn bộ cho _lock_input()
            # ===========================================================
            self._lock_input()