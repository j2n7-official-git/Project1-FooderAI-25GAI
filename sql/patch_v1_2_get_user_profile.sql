-- ============================================================
-- FOODERAI DB PATCH v1.2 — hỗ trợ page_ai tích hợp Gemini
-- Chạy file này trong SSMS sau schema v1.0 và v1.1
-- ============================================================
USE FooderAI_25GAI;
GO

-- ============================================================
-- TẠI SAO CẦN PATCH NÀY?
--
-- page_ai.py gọi: get_user_profile(session_id)
-- → hàm Python cần JOIN gritalyst_session → users
--   để lấy BMI, TDEE, goal... truyền vào Gemini cá nhân hóa
--
-- Hiện tại fooder_database.py CHƯA có hàm get_user_profile()
-- → Gemini luôn nhận user_profile=None → không cá nhân hóa được
-- ============================================================


-- ============================================================
-- BƯỚC 1: VIEW v_user_profile
-- Dồn tất cả thông tin cần cho Gemini vào 1 chỗ
--
-- Tại sao dùng VIEW thay vì query thẳng trong Python?
-- → Python chỉ cần SELECT * FROM v_user_profile WHERE session_id=?
-- → Gọn hơn, nếu sau này thêm cột chỉ sửa VIEW, không sửa Python
-- ============================================================
IF OBJECT_ID('dbo.v_user_profile', 'V') IS NOT NULL
    DROP VIEW dbo.v_user_profile;
GO

CREATE VIEW dbo.v_user_profile AS
SELECT
    -- Lấy session_id để Python WHERE session_id = ?
    gs.session_id,

    -- Lấy user_id phòng khi cần log sau này
    u.user_id,

    -- Tên hiển thị — Gemini dùng để xưng hô "Bạn Tài ơi..."
    u.display_name,

    -- Thông tin cơ thể — Gemini dùng để cá nhân hóa
    u.age,
    u.gender,
    u.height_cm,
    u.weight_kg,
    u.goal,           -- 'lose' | 'maintain' | 'gain'
    u.activity_level, -- 1.2 | 1.375 | 1.55 | 1.725 | 1.9

    -- Chỉ số đã tính sẵn — truyền thẳng vào system prompt Gemini
    u.bmi,
    u.bmr,
    u.tdee

FROM dbo.gritalyst_session gs
-- LEFT JOIN vì session có thể chưa gắn user (chưa login)
-- → trả về NULL thay vì mất dòng
LEFT JOIN dbo.users u ON u.user_id = gs.user_id;
GO


-- ============================================================
-- BƯỚC 2: Thêm cột chat_count vào gritalyst_session
--
-- Tại sao cần cột này?
-- → Hiện tại chỉ có msg_count (đếm "xu" quota)
-- → chat_count đếm số lần GeminiWorker thật sự gọi API thành công
-- → Dùng để thống kê "user đã hỏi bao nhiêu câu" không bị ảnh hưởng
--   bởi việc 1 tin NSFW trừ 5 xu
-- ============================================================
IF NOT EXISTS (
    SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_NAME = 'gritalyst_session'
      AND COLUMN_NAME = 'chat_count'
)
BEGIN
    ALTER TABLE dbo.gritalyst_session
        ADD chat_count INT NOT NULL DEFAULT 0;

    -- Giải thích: DEFAULT 0 để các session cũ không bị NULL
    PRINT '✅ Đã thêm cột chat_count vào gritalyst_session';
END
ELSE
    PRINT '⏭ chat_count đã tồn tại, bỏ qua';
GO


-- ============================================================
-- BƯỚC 3: Cập nhật gritalyst_log — thêm chat_history_len
--
-- Tại sao?
-- → Mỗi lần gọi Gemini, Python gửi kèm _chat_history (tối đa 30 tin)
-- → Lưu độ dài history giúp sau này debug:
--   "Lần này Gemini có đủ ngữ cảnh không? History dài bao nhiêu?"
-- ============================================================
IF NOT EXISTS (
    SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_NAME = 'gritalyst_log'
      AND COLUMN_NAME = 'chat_history_len'
)
BEGIN
    ALTER TABLE dbo.gritalyst_log
        ADD chat_history_len INT NULL;
    -- NULL = không truyền vào (tin NSFW bị chặn trước khi gọi Gemini)
    -- Số nguyên = history gửi kèm lần gọi đó dài bao nhiêu tin

    PRINT '✅ Đã thêm cột chat_history_len vào gritalyst_log';
END
ELSE
    PRINT '⏭ chat_history_len đã tồn tại, bỏ qua';
GO


-- ============================================================
-- KIỂM TRA KẾT QUẢ
-- Chạy 3 SELECT này để xác nhận patch thành công
-- ============================================================

-- Kiểm tra VIEW đã tạo
SELECT 'VIEW v_user_profile' AS object_name,
       COUNT(*) AS column_count
FROM INFORMATION_SCHEMA.VIEW_COLUMN_USAGE
WHERE VIEW_NAME = 'v_user_profile';

-- Kiểm tra cột mới trong gritalyst_session
SELECT COLUMN_NAME, DATA_TYPE, COLUMN_DEFAULT
FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_NAME = 'gritalyst_session'
  AND COLUMN_NAME = 'chat_count';

-- Kiểm tra cột mới trong gritalyst_log
SELECT COLUMN_NAME, DATA_TYPE, IS_NULLABLE
FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_NAME = 'gritalyst_log'
  AND COLUMN_NAME = 'chat_history_len';
GO