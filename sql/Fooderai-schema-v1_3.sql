-- ============================================================
-- FOODERAI SCHEMA v1.3
-- Tác giả: nhóm 25GAI — Tài · Tuấn · Vanh
-- Ngày:    31/05/2026
-- Chạy sau: schema v1.0 + v1.1 + v1.2
-- ============================================================
--
-- CÁC THAY ĐỔI TRONG v1.3:
--   1. ALTER gemini_usage     → thêm cột daily_limit_hit
--   2. CREATE TABLE chat_history_log → lưu lịch sử chat để bật lại app vẫn còn
--   3. CREATE VIEW v_daily_usage     → đếm số câu đã hỏi hôm nay
--
-- TẠI SAO CẦN PATCH NÀY?
--
-- VẤN ĐỀ 1 — Gemini Free Tier giới hạn 1500 request/ngày:
--   Trước v1.3: app gọi Gemini API không giới hạn → dễ hết quota giữa chừng
--   → Gemini trả về lỗi 429 (Too Many Requests) → user thấy thông báo lỗi xấu
--   Sau v1.3: đếm số câu đã hỏi hôm nay trước khi gọi API
--   → Nếu >= 1500 → hiện thông báo thân thiện thay vì lỗi kỹ thuật
--
-- VẤN ĐỀ 2 — Tắt app bật lại mất hết lịch sử chat:
--   Trước v1.3: _chat_history chỉ lưu trong RAM (list Python)
--   → Tắt app = mất hết, Gemini mất ngữ cảnh, user phải giải thích lại từ đầu
--   Sau v1.3: mỗi cặp hỏi-đáp được INSERT vào chat_history_log
--   → Mở app lại → SELECT ra → inject vào _chat_history → Gemini nhớ tiếp
--
-- ============================================================

USE FooderAI_25GAI;
GO


-- ============================================================
-- BƯỚC 1: Thêm daily_limit_hit vào gemini_usage
-- ============================================================
--
-- QUYẾT ĐỊNH THIẾT KẾ:
--   Tại sao thêm cột vào bảng CŨ thay vì tạo bảng mới?
--   → gemini_usage đã có usage_date, machine_id, user_id, request_count
--   → Chỉ cần thêm 1 cột boolean để đánh dấu "hôm nay đã hit limit chưa"
--   → Tránh JOIN thêm bảng khi check quota → query đơn giản hơn
--
--   daily_limit_hit = 0: hôm nay chưa hit limit (mặc định)
--   daily_limit_hit = 1: hôm nay đã hit 1500 request → chặn gọi API
--
--   Tại sao dùng BIT thay vì INT?
--   → BIT chỉ lưu 0/1 → tiết kiệm storage
--   → Ngữ nghĩa rõ ràng: đây là flag boolean, không phải số đếm
--
-- ============================================================
IF NOT EXISTS (
    SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_NAME  = 'gemini_usage'
      AND COLUMN_NAME = 'daily_limit_hit'
)
BEGIN
    ALTER TABLE dbo.gemini_usage
        ADD daily_limit_hit BIT NOT NULL DEFAULT 0;
    PRINT '✅ gemini_usage: đã thêm daily_limit_hit';
END
ELSE
    PRINT '⏭  gemini_usage.daily_limit_hit đã tồn tại, bỏ qua';
GO


-- ============================================================
-- BƯỚC 2: Tạo bảng chat_history_log
-- ============================================================
--
-- QUYẾT ĐỊNH THIẾT KẾ:
--   Tại sao tạo bảng RIÊNG thay vì tái dụng gritalyst_log?
--   → gritalyst_log lưu MỌI tin nhắn (kể cả NSFW bị chặn, lỗi...)
--     mục đích: audit log, thống kê, debug
--   → chat_history_log chỉ lưu các tin THÀNH CÔNG để inject vào Gemini
--     mục đích: khôi phục ngữ cảnh hội thoại khi mở lại app
--   → Hai mục đích khác nhau → tách bảng → query gọn hơn, không cần WHERE phức tạp
--
--   Cấu trúc lựa chọn:
--   - session_id  : biết của phiên nào → load đúng history khi mở lại
--   - turn_index  : thứ tự tin nhắn trong cuộc hội thoại → ORDER BY khi load
--   - role        : 'user' hoặc 'model' → đúng format Gemini API cần
--   - content     : nội dung tin nhắn → inject vào _chat_history
--   - created_at  : thời điểm → dùng khi cần lọc theo ngày
--
--   Tại sao cần turn_index thay vì chỉ dùng created_at để sắp xếp?
--   → created_at có thể trùng nhau nếu 2 tin nhắn cùng giây
--   → turn_index là số nguyên tăng dần, đảm bảo thứ tự chính xác tuyệt đối
--
-- ============================================================
IF OBJECT_ID('dbo.chat_history_log', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.chat_history_log (
        -- Khóa chính tự tăng — định danh duy nhất mỗi dòng log
        history_id  INT IDENTITY(1,1) PRIMARY KEY,

        -- Liên kết với phiên làm việc
        -- FOREIGN KEY → đảm bảo không có history của session không tồn tại
        session_id  INT NOT NULL
            REFERENCES dbo.gritalyst_session(session_id)
            ON DELETE CASCADE,  -- xóa session → tự xóa history theo → tránh orphan data

        -- Thứ tự tin nhắn trong hội thoại
        -- Khi load lại → ORDER BY turn_index → đúng thứ tự gốc
        turn_index  INT NOT NULL,

        -- 'user' hoặc 'model' — đúng format Gemini API
        -- CHECK constraint đảm bảo không có giá trị sai
        role        VARCHAR(10) NOT NULL
            CHECK (role IN ('user', 'model')),

        -- Nội dung tin nhắn
        -- NVARCHAR(MAX) vì câu trả lời Gemini có thể rất dài
        -- N prefix = Unicode → lưu được tiếng Việt
        content     NVARCHAR(MAX) NOT NULL,

        -- Thời điểm lưu — dùng để lọc history theo ngày nếu cần
        created_at  DATETIME2 DEFAULT GETDATE() NOT NULL
    );

    -- Index để tăng tốc query phổ biến nhất:
    -- "Lấy toàn bộ history của session X, sắp theo thứ tự"
    -- Không có index → SQL phải scan toàn bảng mỗi lần load app
    -- Có index → tìm ngay theo session_id, sắp theo turn_index
    CREATE INDEX IX_chat_history_session
        ON dbo.chat_history_log (session_id, turn_index);

    PRINT '✅ Tạo bảng chat_history_log thành công';
END
ELSE
    PRINT '⏭  chat_history_log đã tồn tại, bỏ qua';
GO


-- ============================================================
-- BƯỚC 3: Tạo VIEW v_daily_usage
-- ============================================================
--
-- QUYẾT ĐỊNH THIẾT KẾ:
--   Tại sao dùng VIEW thay vì query thẳng trong Python?
--   → Python cần biết "hôm nay đã gọi bao nhiêu request?" trước mỗi lần gọi API
--   → Nếu query thẳng: SELECT SUM(request_count) FROM gemini_usage WHERE usage_date = CAST(GETDATE() AS DATE)
--     → Phải viết lặp lại trong nhiều chỗ (check quota, hiển thị UI, log...)
--   → VIEW đóng gói logic → Python chỉ cần: SELECT * FROM v_daily_usage WHERE machine_id = ?
--
--   Cột today_requests: tổng request đã gọi hôm nay
--   Cột remaining    : 1500 - today_requests → hiển thị "còn X câu hôm nay"
--   Cột is_limited   : 1 nếu đã >= 1500 → Python check nhanh
--
--   Tại sao CAST(GETDATE() AS DATE)?
--   → GETDATE() trả về datetime (có giờ phút giây)
--   → CAST AS DATE bỏ phần giờ → so sánh đúng "hôm nay" bất kể mấy giờ
--
-- ============================================================
IF OBJECT_ID('dbo.v_daily_usage', 'V') IS NOT NULL
BEGIN
    DROP VIEW dbo.v_daily_usage;
    PRINT '♻  Đã xóa VIEW v_daily_usage cũ để tạo lại';
END
GO

CREATE VIEW dbo.v_daily_usage AS
SELECT
    machine_id,
    user_id,

    -- Tổng request đã gọi hôm nay
    -- COALESCE(x, 0): nếu chưa có dòng nào hôm nay → trả 0 thay vì NULL
    COALESCE(SUM(request_count), 0)  AS today_requests,

    -- Số câu còn lại hôm nay
    -- GREATEST không có trong SQL Server → dùng CASE để tránh số âm
    CASE
        WHEN COALESCE(SUM(request_count), 0) >= 1500 THEN 0
        ELSE 1500 - COALESCE(SUM(request_count), 0)
    END                              AS remaining,

    -- Flag: 1 = đã hết quota hôm nay, 0 = còn quota
    CASE
        WHEN COALESCE(SUM(request_count), 0) >= 1500 THEN 1
        ELSE 0
    END                              AS is_limited,

    -- Ngày hôm nay — để Python verify đúng ngày
    CAST(GETDATE() AS DATE)          AS today

FROM dbo.gemini_usage
-- Chỉ tính các dòng của HÔM NAY
-- CAST cả 2 vế về DATE để so sánh ngày, bỏ qua giờ phút giây
WHERE usage_date = CAST(GETDATE() AS DATE)

-- Group theo machine + user để mỗi máy/user có quota riêng
GROUP BY machine_id, user_id;
GO

PRINT '✅ VIEW v_daily_usage đã tạo thành công';
GO


-- ============================================================
-- STORED PROCEDURE: usp_increment_usage
-- ============================================================
--
-- QUYẾT ĐỊNH THIẾT KẾ:
--   Tại sao dùng Stored Procedure thay vì INSERT/UPDATE thẳng từ Python?
--   → Logic "tăng đếm hoặc tạo mới" cần MERGE (upsert)
--   → Nếu viết trong Python: dài, dễ sai race condition khi nhiều request cùng lúc
--   → SP chạy trong DB → atomic (toàn vẹn), không bị race condition
--   → Python chỉ cần gọi: EXEC usp_increment_usage ?, ?, ?
--
--   MERGE hoạt động như thế nào?
--   → Tìm dòng có (machine_id, user_id, usage_date = hôm nay)
--   → Nếu tìm thấy: UPDATE request_count += 1, token_count += @tokens
--   → Nếu không tìm thấy: INSERT dòng mới với request_count = 1
--   → Tất cả trong 1 câu lệnh → an toàn, không cần check trước
--
-- ============================================================
IF OBJECT_ID('dbo.usp_increment_usage', 'P') IS NOT NULL
    DROP PROCEDURE dbo.usp_increment_usage;
GO

CREATE PROCEDURE dbo.usp_increment_usage
    @machine_id  NVARCHAR(100),  -- ID máy tính (hostname)
    @user_id     INT = NULL,     -- ID user (NULL nếu chưa login)
    @tokens      INT = 0         -- số token dùng trong lần gọi này
AS
BEGIN
    SET NOCOUNT ON;  -- tắt thông báo "X rows affected" → Python không đọc nhầm

    MERGE dbo.gemini_usage AS target
    USING (
        -- "Nguồn" là 1 dòng ảo chứa dữ liệu muốn upsert
        SELECT @machine_id AS machine_id,
               @user_id    AS user_id,
               CAST(GETDATE() AS DATE) AS usage_date
    ) AS source
    ON (
        target.machine_id = source.machine_id
        AND (target.user_id = source.user_id OR (target.user_id IS NULL AND source.user_id IS NULL))
        AND target.usage_date = source.usage_date
    )
    -- Tìm thấy dòng hôm nay → cộng thêm
    WHEN MATCHED THEN
        UPDATE SET
            request_count = target.request_count + 1,
            token_count   = target.token_count + @tokens,
            updated_at    = GETDATE()
    -- Chưa có dòng hôm nay → tạo mới
    WHEN NOT MATCHED THEN
        INSERT (machine_id, user_id, usage_date, request_count, token_count)
        VALUES (@machine_id, @user_id, CAST(GETDATE() AS DATE), 1, @tokens);
END
GO

PRINT '✅ Stored Procedure usp_increment_usage đã tạo thành công';
GO


-- ============================================================
-- KIỂM TRA KẾT QUẢ
-- ============================================================

-- 1. Kiểm tra cột mới trong gemini_usage
SELECT COLUMN_NAME, DATA_TYPE, COLUMN_DEFAULT
FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_NAME = 'gemini_usage' AND COLUMN_NAME = 'daily_limit_hit';
GO

-- 2. Kiểm tra bảng chat_history_log
SELECT COLUMN_NAME, DATA_TYPE, IS_NULLABLE
FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_NAME = 'chat_history_log'
ORDER BY ORDINAL_POSITION;
GO

-- 3. Kiểm tra VIEW v_daily_usage (trả về rỗng nếu chưa có usage hôm nay — bình thường)
SELECT * FROM dbo.v_daily_usage;
GO

-- 4. Test Stored Procedure
EXEC dbo.usp_increment_usage @machine_id = 'TEST_MACHINE', @user_id = NULL, @tokens = 100;
SELECT * FROM dbo.gemini_usage WHERE machine_id = 'TEST_MACHINE';
-- Dọn dẹp sau test
DELETE FROM dbo.gemini_usage WHERE machine_id = 'TEST_MACHINE';
GO

-- Nếu tất cả chạy không lỗi → patch v1.3 thành công!