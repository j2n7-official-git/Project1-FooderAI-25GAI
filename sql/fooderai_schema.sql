-- ============================================================
-- FOODERAI DATABASE SCHEMA — SQL Server (SSMS)
-- Dự án: Trợ Lí Dinh Dưỡng Thông Minh — Nhóm 25GAI
-- Thành viên: Tài · Tuấn · Vanh
-- Phiên bản: v1.0 | 27/05/2026
-- ============================================================
-- HƯỚNG DẪN CHẠY:
--   1. Mở SSMS → kết nối localhost
--   2. New Query → paste toàn bộ file này → Execute (F5)
--   3. Database FooderAI_25GAI sẽ được tạo tự động
-- ============================================================

-- Tạo database nếu chưa có
IF NOT EXISTS (SELECT name FROM sys.databases WHERE name = N'FooderAI_25GAI')
BEGIN
    CREATE DATABASE FooderAI_25GAI;
END
GO

USE FooderAI_25GAI;
GO

-- ============================================================
-- BẢNG 1: users — Hồ sơ người dùng
-- Lưu thông tin cá nhân + chỉ số sức khỏe
-- uid: lấy từ Firebase Auth (Google OAuth) — chuỗi duy nhất mỗi tài khoản
-- ============================================================
IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='users' AND xtype='U')
BEGIN
    CREATE TABLE users (
        user_id       INT           IDENTITY(1,1) PRIMARY KEY,  -- khóa nội bộ tự tăng
        uid           NVARCHAR(128) NOT NULL UNIQUE,             -- Firebase uid (Google)
        email         NVARCHAR(255) NOT NULL UNIQUE,             -- email Google
        display_name  NVARCHAR(100) NULL,                        -- tên hiển thị từ Google
        age           INT           NULL CHECK (age BETWEEN 1 AND 120),
        gender        NVARCHAR(10)  NULL CHECK (gender IN (N'male', N'female')),
        -- male=Nam, female=Nữ (theo UI page_user.py)
        height_cm     FLOAT         NULL CHECK (height_cm BETWEEN 50 AND 300),
        weight_kg     FLOAT         NULL CHECK (weight_kg BETWEEN 10 AND 500),
        goal          NVARCHAR(20)  NULL CHECK (goal IN (N'lose', N'maintain', N'gain')),
        -- lose=giảm cân, maintain=duy trì, gain=tăng cân
        activity_level FLOAT        NULL CHECK (activity_level IN (1.2, 1.375, 1.55, 1.725, 1.9)),
        -- 1.2=ít vận động, 1.375=nhẹ nhàng, 1.55=vừa phải, 1.725=năng động, 1.9=rất cao
        bmi           FLOAT         NULL,   -- tính toán từ height/weight, lưu lại để tra nhanh
        bmr           INT           NULL,   -- Basal Metabolic Rate (kcal/ngày)
        tdee          INT           NULL,   -- Total Daily Energy Expenditure (kcal/ngày)
        created_at    DATETIME2     NOT NULL DEFAULT GETDATE(),  -- lần đầu đăng ký
        updated_at    DATETIME2     NOT NULL DEFAULT GETDATE()   -- lần cập nhật hồ sơ gần nhất
    );
END
GO

-- ============================================================
-- BẢNG 2: user_logs — Lịch sử thay đổi hồ sơ
-- Mỗi lần user nhấn "Lưu hồ sơ & Bắt đầu tính toán" → INSERT 1 dòng
-- Giúp theo dõi tiến trình sức khỏe theo thời gian
-- ============================================================
IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='user_logs' AND xtype='U')
BEGIN
    CREATE TABLE user_logs (
        log_id        BIGINT        IDENTITY(1,1) PRIMARY KEY,
        user_id       INT           NOT NULL
                      REFERENCES users(user_id) ON DELETE CASCADE,
        -- ON DELETE CASCADE: xóa user → tự xóa hết log của user đó
        logged_at     DATETIME2     NOT NULL DEFAULT GETDATE(),
        weight_kg     FLOAT         NULL,   -- cân nặng tại thời điểm log
        height_cm     FLOAT         NULL,
        bmi           FLOAT         NULL,
        bmr           INT           NULL,
        tdee          INT           NULL,
        note          NVARCHAR(500) NULL    -- ghi chú tùy chọn
    );
    CREATE INDEX idx_user_logs_user ON user_logs(user_id);      -- tìm nhanh theo user
    CREATE INDEX idx_user_logs_date ON user_logs(logged_at);    -- tìm nhanh theo ngày
END
GO

-- ============================================================
-- BẢNG 3: gritalyst_session — Trạng thái phiên chat
-- Lưu msg_count, nsfw_streak, muted_until, reset_at để
-- đếm giờ "tính thật" dù tắt app rồi mở lại
-- ============================================================
IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='gritalyst_session' AND xtype='U')
BEGIN
    CREATE TABLE gritalyst_session (
        session_id    INT           IDENTITY(1,1) PRIMARY KEY,
        user_id       INT           NULL
                      REFERENCES users(user_id) ON DELETE SET NULL,
        -- NULL = khách chưa đăng nhập vẫn có session (theo machine_id)
        machine_id    NVARCHAR(64)  NULL,   -- ID máy (fallback khi chưa login)
        msg_count     INT           NOT NULL DEFAULT 0,     -- số tin đã dùng (tối đa 50)
        nsfw_streak   INT           NOT NULL DEFAULT 0,     -- chuỗi vi phạm liên tiếp
        muted_until   DATETIME2     NULL,   -- NULL = không bị khóa; có giá trị = đang bị khóa
        reset_at      DATETIME2     NULL,   -- thời điểm token tự reset về 0 (sau 4 tiếng)
        created_at    DATETIME2     NOT NULL DEFAULT GETDATE(),
        updated_at    DATETIME2     NOT NULL DEFAULT GETDATE()
    );
    CREATE INDEX idx_session_user ON gritalyst_session(user_id);
END
GO

-- ============================================================
-- BẢNG 4: gritalyst_log — Log từng tin nhắn
-- Ghi lại toàn bộ lịch sử chat: tin nhắn + kết quả xử lý
-- Dùng để debug, phân tích hành vi, phát hiện quấy rối
-- ============================================================
IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='gritalyst_log' AND xtype='U')
BEGIN
    CREATE TABLE gritalyst_log (
        log_id        BIGINT        IDENTITY(1,1) PRIMARY KEY,
        session_id    INT           NOT NULL
                      REFERENCES gritalyst_session(session_id) ON DELETE CASCADE,
        user_id       INT           NULL
                      REFERENCES users(user_id) ON DELETE SET NULL,
        sent_at       DATETIME2     NOT NULL DEFAULT GETDATE(),
        user_message  NVARCHAR(MAX) NOT NULL,    -- nội dung user gõ (tối đa ~1 tỷ ký tự)
        bot_response  NVARCHAR(MAX) NULL,        -- câu Gritalyst trả về (NULL nếu bị chặn)
        msg_type      NVARCHAR(20)  NOT NULL DEFAULT N'normal'
                      CHECK (msg_type IN (
                          N'normal',   -- hỏi đáp bình thường
                          N'nsfw',     -- bị filter NSFW, bot reply cảnh báo
                          N'blocked'   -- bị chặn hoàn toàn (đang bị khóa)
                      )),
        nsfw_level    TINYINT       NOT NULL DEFAULT 0
                      CHECK (nsfw_level BETWEEN 0 AND 9),
        -- 0=sạch, 1-6=soft warning, 7-8=hard warning, 9=bị mute
        tokens_used   INT           NULL    -- token Gemini tiêu thụ (điền sau khi có API)
    );
    CREATE INDEX idx_gritalyst_log_session ON gritalyst_log(session_id);
    CREATE INDEX idx_gritalyst_log_sent    ON gritalyst_log(sent_at);
    CREATE INDEX idx_gritalyst_log_type    ON gritalyst_log(msg_type);
END
GO

-- ============================================================
-- KIỂM TRA KẾT QUẢ — chạy sau khi Execute xong
-- Nên thấy 4 dòng: users, user_logs, gritalyst_session, gritalyst_log
-- ============================================================
SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES
WHERE TABLE_TYPE = 'BASE TABLE'
ORDER BY TABLE_NAME;
GO