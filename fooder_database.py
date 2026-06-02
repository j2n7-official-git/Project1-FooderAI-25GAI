"""
fooder_database.py — Module kết nối SQL Server cho FooderAI
============================================================
Nhiệm vụ:
  - Kết nối Python → SQL Server qua pyodbc
  - CRUD cho 5 bảng: users, user_logs, gritalyst_session,
                     gritalyst_log, food_scan_log
  - NSFWGuard load/save trạng thái từ DB (đếm giờ tính thật)

Cài module trước khi dùng (PyCharm interpreter → nhấn + → search):
  pyodbc

Cấu hình kết nối trong file .env:
  DB_SERVER=localhost
  DB_NAME=FooderAI_25GAI

[UPDATE v1.0] — 27/05/2026 — Tài · Tuấn · Vanh
  + Tạo mới toàn bộ module
  + 4 bảng: users, user_logs, gritalyst_session, gritalyst_log
  + Hỗ trợ Windows Authentication (không cần user/pass)

[UPDATE v1.1] — 31/05/2026 — Tài · Tuấn · Vanh
  + Thêm nhóm hàm FOOD SCAN LOG
  + log_scan()        : ghi kết quả quét ảnh vào food_scan_log
  + get_scan_history(): lấy lịch sử quét của user (dùng cho UI sau này)
"""

import os
import pyodbc
from datetime import datetime
from dotenv import load_dotenv

# Nạp biến môi trường từ file .env cùng thư mục
# Nếu chưa có file .env thì dùng giá trị mặc định bên dưới
load_dotenv()

# ============================================================
# CẤU HÌNH KẾT NỐI
# ============================================================
_SERVER = os.getenv("DB_SERVER", "localhost")          # tên server SQL
_DB     = os.getenv("DB_NAME",   "FooderAI_25GAI")    # tên database

# Connection string dùng Windows Authentication (Trusted_Connection)
# Không cần username/password — dùng tài khoản Windows hiện tại
# TrustServerCertificate=yes: bỏ qua lỗi SSL certificate trên dev machine
_CONN_STR = (
    f"DRIVER={{ODBC Driver 17 for SQL Server}};"
    f"SERVER={_SERVER};"
    f"DATABASE={_DB};"
    f"Trusted_Connection=yes;"
    f"TrustServerCertificate=yes;"
)

# Nếu máy chưa có ODBC Driver 17, thử fallback sang Driver 13 hoặc SQL Server
_CONN_STR_FALLBACK = (
    f"DRIVER={{SQL Server}};"
    f"SERVER={_SERVER};"
    f"DATABASE={_DB};"
    f"Trusted_Connection=yes;"
)


def get_connection() -> pyodbc.Connection:
    """
    Tạo và trả về 1 connection đến SQL Server.
    Tự động thử fallback driver nếu Driver 17 chưa cài.

    Trả về: pyodbc.Connection
    Ném: RuntimeError nếu không kết nối được
    """
    try:
        return pyodbc.connect(_CONN_STR, timeout=5)
    except pyodbc.Error:
        try:
            # Fallback: thử driver cũ hơn
            return pyodbc.connect(_CONN_STR_FALLBACK, timeout=5)
        except pyodbc.Error as e:
            raise RuntimeError(
                f"Không thể kết nối SQL Server tại '{_SERVER}'.\n"
                f"Kiểm tra: SSMS đang chạy, database '{_DB}' đã tạo, "
                f"ODBC Driver đã cài.\nLỗi gốc: {e}"
            )


# ============================================================
# NHÓM HÀM: USERS
# ============================================================

def upsert_user(uid, display_name, email, photo_url=None, google_access_token=None):
    """
    Đồng bộ user từ Google/Local vào SQL Server dựa trên cột 'uid' (chuỗi).
    Trả về 'user_id' (số nguyên) để dùng cho các bảng khác.
    """
    try:
        conn = get_connection()  # Đã sửa đúng tên hàm kết nối
        cursor = conn.cursor()

        # 1. Tìm xem uid (mã Google/Local) đã tồn tại chưa
        cursor.execute("SELECT user_id FROM dbo.users WHERE uid = ?", (uid,))
        row = cursor.fetchone()

        now = datetime.now()

        if not row:
            # 2. Nếu chưa có -> THÊM MỚI (Lưu ý: KHÔNG insert vào user_id vì nó tự tăng)
            # Dùng OUTPUT INSERTED.user_id để chộp ngay cái số nguyên vừa được tạo ra
            sql = """
                INSERT INTO dbo.users (uid, display_name, email, provider, photo_url, google_access_token, created_at, last_login_at)
                OUTPUT INSERTED.user_id
                VALUES (?, ?, ?, 'google', ?, ?, ?, ?)
            """
            cursor.execute(sql, (uid, display_name, email, photo_url, google_access_token, now, now))
            internal_user_id = cursor.fetchone()[0]
            print(f"[DB] Thêm mới thành viên thành công: {display_name}")
        else:
            # 3. Nếu có rồi -> CẬP NHẬT
            internal_user_id = row[0]
            sql = """
                UPDATE dbo.users 
                SET display_name = ?, email = ?, photo_url = ?, google_access_token = ?, last_login_at = ?
                WHERE uid = ?
            """
            cursor.execute(sql, (display_name, email, photo_url, google_access_token, now, uid))
            print(f"[DB] Cập nhật phiên đăng nhập thành công: {display_name}")

        conn.commit()
        return internal_user_id  # Bắt buộc trả về SỐ NGUYÊN
    except Exception as e:
        print(f"❌ [DB] Lỗi hàm upsert_user: {e}")
        return None


def update_user_profile(user_id: int, age: int, gender: str,
                        height_cm: float, weight_kg: float,
                        goal: str, activity_level: float,
                        bmi: float, bmr: int, tdee: int):
    """
    Cập nhật thông tin sức khỏe sau khi user nhấn 'Lưu hồ sơ'.
    Đồng thời INSERT 1 dòng vào user_logs để lưu lịch sử.

    [UPDATE v1] Gộp 2 thao tác: UPDATE users + INSERT user_logs trong 1 transaction
    """
    with get_connection() as conn:
        # Cập nhật bảng users
        conn.execute("""
            UPDATE users SET
                age            = ?,
                gender         = ?,
                height_cm      = ?,
                weight_kg      = ?,
                goal           = ?,
                activity_level = ?,
                bmi            = ?,
                bmr            = ?,
                tdee           = ?,
                updated_at     = GETDATE()
            WHERE user_id = ?
        """, (age, gender, height_cm, weight_kg, goal,
              activity_level, bmi, bmr, tdee, user_id))

        # Ghi log thay đổi vào user_logs
        conn.execute("""
            INSERT INTO user_logs
                (user_id, weight_kg, height_cm, bmi, bmr, tdee)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (user_id, weight_kg, height_cm, bmi, bmr, tdee))

        conn.commit()


def get_user_by_uid(uid: str) -> dict | None:
    """
    Lấy toàn bộ thông tin user theo Firebase uid.
    Trả về dict hoặc None nếu chưa có.
    """
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE uid = ?", uid
        ).fetchone()
        if not row:
            return None
        # Chuyển pyodbc.Row → dict để dùng trong Python dễ hơn
        cols = [desc[0] for desc in conn.execute(
            "SELECT * FROM users WHERE uid = ?", uid
        ).description]
        return dict(zip(cols, row))


# ============================================================
# NHÓM HÀM: GRITALYST SESSION (đếm giờ tính thật)
# ============================================================

def get_or_create_session(user_id: int = None, machine_id: str = None) -> dict:
    """
    Lấy session hiện tại của user/máy, hoặc tạo mới nếu chưa có.
    Ưu tiên user_id nếu đã đăng nhập, fallback sang machine_id nếu chưa.

    Trả về dict gồm: session_id, msg_count, nsfw_streak, muted_until, reset_at

    [UPDATE v1] Machine_id = hostname máy tính, dùng khi chưa login
    """
    with get_connection() as conn:
        # Tìm session theo user_id hoặc machine_id
        if user_id:
            row = conn.execute(
                "SELECT * FROM gritalyst_session WHERE user_id = ?", user_id
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT * FROM gritalyst_session WHERE machine_id = ? AND user_id IS NULL",
                machine_id
            ).fetchone()

        if row:
            cols = [d[0] for d in conn.execute(
                "SELECT * FROM gritalyst_session WHERE session_id = ?", row[0]
            ).description]
            return dict(zip(cols, row))

        # Chưa có → tạo mới
        conn.execute("""
            INSERT INTO gritalyst_session (user_id, machine_id)
            VALUES (?, ?)
        """, (user_id, machine_id))
        conn.commit()

        # Lấy lại session vừa tạo
        row = conn.execute(
            "SELECT * FROM gritalyst_session WHERE session_id = SCOPE_IDENTITY()"
        ).fetchone()
        if not row:
            # Fallback: query lại theo điều kiện
            if user_id:
                row = conn.execute(
                    "SELECT TOP 1 * FROM gritalyst_session WHERE user_id = ? ORDER BY created_at DESC",
                    user_id
                ).fetchone()
            else:
                row = conn.execute(
                    "SELECT TOP 1 * FROM gritalyst_session WHERE machine_id = ? ORDER BY created_at DESC",
                    machine_id
                ).fetchone()

        cols = ["session_id", "user_id", "machine_id", "msg_count",
                "nsfw_streak", "muted_until", "reset_at", "created_at", "updated_at"]
        return dict(zip(cols, row))


def save_session_state(session_id: int, msg_count: int, nsfw_streak: int,
                       muted_until: datetime = None, reset_at: datetime = None):
    """
    Lưu trạng thái NSFWGuard xuống DB sau mỗi lần gửi tin.
    Gọi trong record_clean() và record_nsfw() của NSFWGuard.
    """
    with get_connection() as conn:
        # SỬA TẠI ĐÂY: Thêm khối cursor giống hệt 2 hàm dưới để nói chuyện với SQL Server
        with conn.cursor() as cursor:
            try:
                cursor.execute("""
                    UPDATE gritalyst_session SET
                        msg_count   = ?,
                        nsfw_streak = ?,
                        muted_until = ?,
                        reset_at    = ?,
                        updated_at  = GETDATE()
                    WHERE session_id = ?
                """, (msg_count, nsfw_streak, muted_until, reset_at, session_id))

                # Xác nhận lưu trạng thái và nhả khóa database
                conn.commit()
                print(f"[SQL SERVER] Đã cập nhật trạng thái session {session_id} xuống DB!")
            except Exception as e:
                print(f"[SQL SERVER ERROR] Lỗi cập nhật trạng thái session: {e}")
                conn.rollback()


# ============================================================
# NHÓM HÀM: GRITALYST LOG (lịch sử chat)
# ============================================================

def log_message(session_id: int, user_id: int = None,
                user_message: str = "",
                bot_response: str = None,
                msg_type: str = "normal",
                nsfw_level: int = 0,
                tokens_used: int = None):
    # Dùng context manager bọc cả kết nối và cursor để tự động giải phóng bộ nhớ khi chạy xong
    with get_connection() as conn:
        with conn.cursor() as cursor:
            # Lưu ý: Nếu dùng thư viện pymssql thì thay các dấu ? thành %s
            cursor.execute("""
                INSERT INTO gritalyst_log
                    (session_id, user_id, user_message, bot_response,
                     msg_type, nsfw_level, tokens_used)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (session_id, user_id, user_message, bot_response,
                  msg_type, nsfw_level, tokens_used))
            conn.commit()


def reset_chat_history(session_id: int):
    # Khối with thứ nhất: Đảm bảo conn luôn luôn được giải phóng và ĐÓNG hoàn toàn
    with get_connection() as conn:
        # Khối with thứ hai: Đảm bảo cursor được giải phóng ngay sau khi dùng xong
        with conn.cursor() as cursor:
            try:
                # Thực thi lệnh xóa trên SQL Server
                cursor.execute("DELETE FROM gritalyst_log WHERE session_id = ?", (session_id,))

                # 🌟 BẮT BUỘC PHẢI CÓ DÒNG NÀY: Xác nhận lưu và nhả ổ khóa dữ liệu trên SSMS ngay lập tức!
                conn.commit()
                print(f"[SQL SERVER] Đã giải phóng hoàn toàn session {session_id} thành công!")

            except Exception as e:
                print(f"[SQL SERVER ERROR] Lỗi thực thi lệnh DELETE: {e}")
                # Nếu lỗi thì hủy thao tác, không cho treo lệnh chờ
                conn.rollback()

# ============================================================
# NHÓM HÀM: FOOD SCAN LOG
# ============================================================
#
# Tại sao tách nhóm hàm riêng?
# → Food Scan hoàn toàn độc lập với Chat (không có session, không có role)
# → Giữ code gọn: ai cần tính năng scan thì import log_scan / get_scan_history
#   mà không cần đọc hết code chat
#
# Luồng gọi:
#   ScanWorker (page_scan.py)
#     → scan_food_image() (gemini_service.py)   ← gọi Gemini Vision
#     → _update_result_ui() (page_scan.py)      ← cập nhật UI
#     → log_scan() (fooder_database.py)         ← lưu xuống DB  ← ĐÂY
# ============================================================

def log_scan(
    food_name:   str,
    description: str  = None,
    benefits:    str  = None,
    warnings:    str  = None,
    image_path:  str  = None,
    tokens_used: int  = 0,
    user_id:     int  = None,
) -> int | None:
    """
    Ghi 1 kết quả quét ảnh món ăn vào bảng food_scan_log.
    Gọi trong _update_result_ui() sau khi ScanWorker trả về kết quả.

    Tham số:
        food_name   : tên món Gemini trả về (VD: "Bánh mì thịt nguội")
        description : nội dung mo_ta  (~200-400 ký tự, có bullet)
        benefits    : nội dung loi_diem (bullet points)
        warnings    : nội dung luu_y   (bullet points)
        image_path  : đường dẫn file ảnh trên máy user (có thể None)
        tokens_used : số token Vision đã dùng (từ response.usage_metadata)
        user_id     : ID user đã đăng nhập; None nếu chưa login

    Trả về:
        scan_id (int) vừa được tạo — để debug hoặc liên kết sau này
        None nếu có lỗi DB (app vẫn chạy bình thường, chỉ không lưu được)

    Ghi chú scan_status:
        SP usp_log_scan tự suy ra scan_status từ food_name:
          - food_name = None / rỗng          → 'error'
          - food_name = 'KHÔNG PHẢI MÓN ĂN'  → 'not_food'
          - food_name = 'Lỗi...' / '⚠️...'  → 'error'
          - còn lại                           → 'success'
        Python không cần truyền scan_status — để SP tự xử lý.
    """
    try:
        with get_connection() as conn:
            # ── Gọi stored procedure usp_log_scan ─────────────────────────
            # SP nhận OUTPUT parameter @new_scan_id → dùng pyodbc OUTPUT param
            #
            # Cú pháp pyodbc cho OUTPUT param:
            #   cursor.execute("{CALL sp_name (?, ?, ?, ...)}", params)
            # Output param cần khai báo trước bằng pyodbc.SQL_INTEGER
            #
            # Tại sao dùng SP thay vì INSERT thẳng?
            # → SP tự cắt food_name nếu > 200 ký tự
            # → SP tự suy ra scan_status từ food_name
            # → SP trả về scan_id → Python biết ID vừa tạo
            # → Nếu sau này thêm logic (VD: cộng vào gemini_usage Vision quota)
            #   → chỉ sửa SP, không đụng Python
            cursor = conn.cursor()

            # Khai báo OUTPUT param — pyodbc yêu cầu truyền giá trị khởi đầu (0)
            scan_id_out = cursor.var(int)   # pyodbc output variable

            cursor.execute(
                """
                DECLARE @out_id INT;
                EXEC dbo.usp_log_scan
                    @user_id     = ?,
                    @image_path  = ?,
                    @food_name   = ?,
                    @description = ?,
                    @benefits    = ?,
                    @warnings    = ?,
                    @tokens_used = ?,
                    @new_scan_id = @out_id OUTPUT;
                SELECT @out_id AS scan_id;
                """,
                (
                    user_id,
                    image_path,
                    food_name,
                    description,
                    benefits,
                    warnings,
                    tokens_used or 0,
                )
            )

            # Đọc scan_id từ SELECT @out_id cuối SP
            row = cursor.fetchone()
            conn.commit()

            scan_id = row[0] if row else None
            print(f"[DB SCAN] ✅ Đã lưu scan_id={scan_id} | món: {food_name}")
            return scan_id

    except Exception as e:
        # Không crash app — chỉ in lỗi và trả None
        # Lý do: lỗi DB không nên làm hỏng trải nghiệm scan của user
        print(f"[DB SCAN] ⚠️ Không lưu được food_scan_log: {e}")
        return None


def get_scan_history(user_id: int = None, limit: int = 20) -> list[dict]:
    """
    Lấy lịch sử quét ảnh món ăn của 1 user, sắp xếp mới nhất trước.
    Dùng để hiển thị lịch sử trong UI (sau này).

    Tham số:
        user_id : ID user đã đăng nhập; None = lấy tất cả (dùng khi debug)
        limit   : số dòng tối đa trả về (mặc định 20)

    Trả về: list of dict, mỗi dict là 1 lần quét
    """
    try:
        with get_connection() as conn:
            if user_id is not None:
                # Lấy lịch sử của user cụ thể
                rows = conn.execute(
                    """
                    SELECT TOP (?)
                        scan_id, food_name, scan_status,
                        tokens_used, scanned_at, image_path
                    FROM dbo.food_scan_log
                    WHERE user_id = ?
                    ORDER BY scanned_at DESC
                    """,
                    (limit, user_id)
                ).fetchall()
            else:
                # Không có user_id → lấy tất cả (dùng khi debug / chưa login)
                rows = conn.execute(
                    """
                    SELECT TOP (?)
                        scan_id, food_name, scan_status,
                        tokens_used, scanned_at, image_path
                    FROM dbo.food_scan_log
                    ORDER BY scanned_at DESC
                    """,
                    (limit,)
                ).fetchall()

            # Chuyển list of Row → list of dict để dùng trong Python dễ hơn
            cols = ["scan_id", "food_name", "scan_status",
                    "tokens_used", "scanned_at", "image_path"]
            return [dict(zip(cols, row)) for row in rows]

    except Exception as e:
        print(f"[DB SCAN] ⚠️ get_scan_history lỗi: {e}")
        return []  # trả list rỗng thay vì crash


# ============================================================
# KIỂM TRA KẾT NỐI — chạy thử khi mở file trực tiếp
# ============================================================
if __name__ == "__main__":
    print("Đang kiểm tra kết nối SQL Server...")
    try:
        conn = get_connection()
        print(f"✅ Kết nối thành công: {_SERVER} → {_DB}")

        # Kiểm tra các bảng tồn tại (v1.4 phải có food_scan_log)
        tables = conn.execute("""
            SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES
            WHERE TABLE_TYPE = 'BASE TABLE'
            ORDER BY TABLE_NAME
        """).fetchall()
        print("📋 Các bảng trong DB:")
        for t in tables:
            marker = " ✅" if t[0] == "food_scan_log" else ""
            print(f"   - {t[0]}{marker}")
        conn.close()
    except RuntimeError as e:
        print(f"❌ {e}")

    # ── TEST log_scan() ─────────────────────────────────────────────
    print("\n--- Test log_scan() ---")

    # Test 1: quét thành công
    sid = log_scan(
        food_name   = "Bánh mì thịt nguội",
        description = "Ổ bánh mì giòn với thịt nguội, chả lụa, rau thơm.\n- Tinh bột: 45g\n- Protein: 18g\n- Calo: ~220 kcal",
        benefits    = "• Cung cấp năng lượng nhanh\n• Protein từ thịt nguội\n• Tiện lợi, dễ mang theo",
        warnings    = "• Nhiều natri\n• Không ăn quá 2 ổ/ngày\n• Kết hợp rau xanh để cân bằng",
        image_path  = "C:/test/banh_mi.jpg",
        tokens_used = 400,
        user_id     = None,
    )
    print(f"Test 1 — scan_id: {sid}")

    # Test 2: không phải món ăn
    sid2 = log_scan(
        food_name   = "KHÔNG PHẢI MÓN ĂN",
        description = "Ảnh không chứa món ăn",
        tokens_used = 150,
    )
    print(f"Test 2 — scan_id: {sid2}")

    # Test 3: lỗi kết nối Gemini
    sid3 = log_scan(
        food_name   = "Lỗi kết nối",
        description = "⚠️ Gemini đang bận — thử lại sau nhé!",
        tokens_used = 0,
    )
    print(f"Test 3 — scan_id: {sid3}")

    # Test 4: đọc lại lịch sử vừa ghi
    print("\n--- Test get_scan_history() ---")
    history = get_scan_history(user_id=None, limit=5)
    for item in history:
        print(f"  [{item['scan_id']}] {item['food_name']} | {item['scan_status']} | {item['scanned_at']}")