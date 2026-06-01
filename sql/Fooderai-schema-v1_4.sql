-- ============================================================
-- FOODERAI SCHEMA v1.4
-- Tác giả: nhóm 25GAI — Tài · Tuấn · Vanh
-- Ngày:    31/05/2026
-- Chạy sau: schema v1.0 → v1.1 → v1.2 → v1.3
-- ============================================================
--
-- CÁC THAY ĐỔI TRONG v1.4:
--   1. CREATE TABLE food_scan_log   → lưu lịch sử quét món ăn bằng Gemini Vision
--   2. CREATE INDEX                 → tăng tốc truy vấn lịch sử theo user + ngày
--   3. CREATE PROCEDURE usp_log_scan → Python gọi 1 dòng để lưu kết quả quét
--   4. CREATE VIEW v_scan_summary   → thống kê tổng số lần quét theo ngày
--
-- TẠI SAO CẦN PATCH NÀY?
--
--   Tính năng Food Scan dùng Gemini Vision phân tích ảnh món ăn.
--   Mỗi lần quét tiêu tốn token → cần ghi lại để:
--     a) Theo dõi mức tiêu thụ token của Vision (tách biệt với Chat)
--     b) Lưu lịch sử để user xem lại đã quét những món gì
--     c) Biết quét thành công / thất bại / không phải đồ ăn
--     d) Phục vụ báo cáo đồ án (chứng minh tính năng hoạt động)
--
-- ============================================================

USE FooderAI_25GAI;
GO


-- ============================================================
-- BƯỚC 1: Tạo bảng food_scan_log
-- ============================================================
--
-- QUYẾT ĐỊNH THIẾT KẾ:
--
--   Tại sao KHÔNG dùng lại gritalyst_log?
--   → gritalyst_log được thiết kế cho cuộc hội thoại: có session_id,
--     turn_index, role (user/model) — cấu trúc hoàn toàn khác
--   → Food Scan là thao tác 1 chiều: user gửi ảnh → AI trả kết quả
--     không có session, không có lượt đối thoại
--   → Tách bảng → query rõ ràng hơn, không cần WHERE msg_type = 'scan'
--
--   Giải thích từng cột:
--
--   scan_id       : khóa chính tự tăng — định danh duy nhất mỗi lần quét
--   user_id       : FK đến users — NULL nếu chưa đăng nhập
--                   ON DELETE SET NULL: xóa user → giữ lại log, user_id = NULL
--                   (không xóa log vì mất dữ liệu thống kê)
--   scanned_at    : thời điểm quét — dùng để group theo ngày, lọc lịch sử
--   image_path    : đường dẫn file ảnh trên máy user
--                   VARCHAR thay vì NVARCHAR vì path thường là ASCII
--   food_name     : tên món Gemini trả về (VD: "Bánh mì thịt")
--                   NVARCHAR vì tên món tiếng Việt
--   description   : nội dung mo_ta từ Gemini (~200-400 ký tự)
--   benefits      : nội dung loi_diem từ Gemini (bullet points)
--   warnings      : nội dung luu_y từ Gemini (bullet points)
--   tokens_used   : số token Vision tiêu tốn — tách khỏi token Chat
--   scan_status   : 'success' | 'error' | 'not_food'
--                   CHECK constraint → không cho giá trị sai lọt vào
--
-- ============================================================
IF OBJECT_ID('dbo.food_scan_log', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.food_scan_log (

        -- ── KHÓA CHÍNH ────────────────────────────────────────────
        scan_id       INT IDENTITY(1,1) PRIMARY KEY,

        -- ── LIÊN KẾT USER ─────────────────────────────────────────
        -- SET NULL thay vì CASCADE: xóa user → giữ log, chỉ NULL user_id
        -- Lý do: log quét là dữ liệu thống kê, không nên mất đi cùng user
        user_id       INT NULL
            REFERENCES dbo.users(user_id)
            ON DELETE SET NULL,

        -- ── THỜI GIAN ─────────────────────────────────────────────
        -- DATETIME2 chính xác hơn DATETIME (đến 100ns vs 1/300s)
        -- DEFAULT GETDATE(): tự điền thời điểm hiện tại nếu không truyền vào
        scanned_at    DATETIME2 NOT NULL DEFAULT GETDATE(),

        -- ── ẢNH ───────────────────────────────────────────────────
        -- VARCHAR(500): path file Windows thường dưới 260 ký tự, để 500 cho rộng
        -- NULL OK: đôi khi chỉ muốn log lỗi mà không có path
        image_path    VARCHAR(500) NULL,

        -- ── KẾT QUẢ TỪ GEMINI VISION ─────────────────────────────
        -- NVARCHAR vì nội dung tiếng Việt (có dấu)
        -- (200) cho tên món: đủ chứa tên dài nhất
        -- MAX cho mô tả / lợi điểm / lưu ý: Gemini có thể trả về khá dài
        food_name     NVARCHAR(200) NULL,
        description   NVARCHAR(MAX) NULL,
        benefits      NVARCHAR(MAX) NULL,
        warnings      NVARCHAR(MAX) NULL,

        -- ── TOKEN TRACKING ────────────────────────────────────────
        -- Tách biệt với token Chat (trong gritalyst_log)
        -- Giúp so sánh: Vision tốn bao nhiêu so với Chat?
        tokens_used   INT NULL DEFAULT 0,

        -- ── TRẠNG THÁI QUÉT ───────────────────────────────────────
        -- 'success'  : Gemini nhận diện được món ăn
        -- 'not_food' : ảnh không phải món ăn
        -- 'error'    : lỗi API, lỗi đọc file, hết quota...
        -- CHECK constraint: chặn giá trị ngoài 3 loại trên
        scan_status   VARCHAR(20) NOT NULL DEFAULT 'success'
            CONSTRAINT CK_scan_status
            CHECK (scan_status IN ('success', 'not_food', 'error'))

    );

    PRINT N'✅ Tạo bảng food_scan_log thành công';
END
ELSE
    PRINT N'⏭  food_scan_log đã tồn tại, bỏ qua';
GO


-- ============================================================
-- BƯỚC 2: Tạo INDEX
-- ============================================================
--
-- QUYẾT ĐỊNH THIẾT KẾ:
--
--   Tại sao cần INDEX?
--   → Không có INDEX: mỗi lần query lịch sử → SQL phải duyệt TOÀN BỘ bảng
--   → Có INDEX: tìm ngay theo user_id + ngày → nhanh hơn nhiều lần
--
--   IX_food_scan_user_date:
--   → Query phổ biến nhất: "lịch sử quét của user X trong ngày Y"
--   → Cột đầu: user_id (filter chính)
--   → Cột hai: scanned_at (sort + range filter theo ngày)
--   → Thứ tự này quan trọng: SQL dùng index từ trái sang phải
--
--   IX_food_scan_status:
--   → Dùng khi báo cáo: "có bao nhiêu lần quét lỗi hôm nay?"
--   → Nhỏ hơn, ít cột hơn → tạo nhanh, tốn ít storage
--
-- ============================================================
IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = 'IX_food_scan_user_date'
      AND object_id = OBJECT_ID('dbo.food_scan_log')
)
BEGIN
    CREATE INDEX IX_food_scan_user_date
        ON dbo.food_scan_log (user_id, scanned_at DESC);
    PRINT N'✅ Index IX_food_scan_user_date đã tạo';
END
ELSE
    PRINT N'⏭  IX_food_scan_user_date đã tồn tại, bỏ qua';
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = 'IX_food_scan_status'
      AND object_id = OBJECT_ID('dbo.food_scan_log')
)
BEGIN
    CREATE INDEX IX_food_scan_status
        ON dbo.food_scan_log (scan_status, scanned_at DESC);
    PRINT N'✅ Index IX_food_scan_status đã tạo';
END
ELSE
    PRINT N'⏭  IX_food_scan_status đã tồn tại, bỏ qua';
GO


-- ============================================================
-- BƯỚC 3: Stored Procedure usp_log_scan
-- ============================================================
--
-- QUYẾT ĐỊNH THIẾT KẾ:
--
--   Tại sao dùng Stored Procedure thay vì INSERT thẳng từ Python?
--   → Python chỉ cần gọi: EXEC usp_log_scan ?, ?, ?, ...
--   → SP xử lý logic bên trong DB:
--       - Tự cắt food_name nếu > 200 ký tự (tránh lỗi truncation)
--       - Tự đặt scan_status dựa vào food_name nếu không truyền vào
--       - Trả về scan_id vừa tạo để Python có thể dùng tiếp
--   → Nếu sau này thêm logic (update gemini_usage Vision quota)
--     → chỉ sửa SP, không sờ vào Python code
--
--   OUTPUT parameter @new_scan_id:
--   → Trả về ID của dòng vừa INSERT
--   → Python nhận về → có thể dùng để liên kết với record khác sau này
--
-- ============================================================
IF OBJECT_ID('dbo.usp_log_scan', 'P') IS NOT NULL
    DROP PROCEDURE dbo.usp_log_scan;
GO

CREATE PROCEDURE dbo.usp_log_scan
    -- Tham số đầu vào — tất cả có DEFAULT NULL để dễ gọi, chỉ truyền cái có
    @user_id      INT           = NULL,
    @image_path   VARCHAR(500)  = NULL,
    @food_name    NVARCHAR(200) = NULL,
    @description  NVARCHAR(MAX) = NULL,
    @benefits     NVARCHAR(MAX) = NULL,
    @warnings     NVARCHAR(MAX) = NULL,
    @tokens_used  INT           = 0,
    @scan_status  VARCHAR(20)   = NULL,     -- NULL → tự suy ra từ food_name

    -- Tham số đầu ra — trả về scan_id vừa INSERT
    @new_scan_id  INT           = NULL OUTPUT
AS
BEGIN
    SET NOCOUNT ON;

    -- ── TỰ SUY RA scan_status NẾU KHÔNG TRUYỀN VÀO ────────────────
    -- Logic:
    --   food_name = NULL hoặc rỗng            → 'error'   (AI không trả về gì)
    --   food_name = 'KHÔNG PHẢI MÓN ĂN'       → 'not_food'
    --   food_name = 'Lỗi phân tích' hoặc có ⚠️ → 'error'
    --   Còn lại                                 → 'success'
    IF @scan_status IS NULL
    BEGIN
        SET @scan_status =
            CASE
                WHEN @food_name IS NULL OR LTRIM(RTRIM(@food_name)) = ''
                    THEN 'error'
                WHEN @food_name LIKE N'KHÔNG PHẢI MÓN ĂN%'
                    THEN 'not_food'
                WHEN @food_name LIKE N'Lỗi%' OR @food_name LIKE N'⚠️%'
                    THEN 'error'
                ELSE 'success'
            END;
    END;

    -- ── VALIDATE scan_status ────────────────────────────────────────
    -- CHECK constraint trong bảng đã chặn, nhưng bắt lỗi sớm ở đây
    -- để trả về thông báo rõ ràng hơn là lỗi constraint SQL
    IF @scan_status NOT IN ('success', 'not_food', 'error')
        SET @scan_status = 'error';

    -- ── INSERT ──────────────────────────────────────────────────────
    INSERT INTO dbo.food_scan_log (
        user_id,
        image_path,
        food_name,
        description,
        benefits,
        warnings,
        tokens_used,
        scan_status
        -- scanned_at tự động điền DEFAULT GETDATE()
    )
    VALUES (
        @user_id,
        @image_path,
        -- Cắt food_name nếu vô tình dài hơn 200 ký tự (Gemini đôi khi trả dài)
        LEFT(@food_name, 200),
        @description,
        @benefits,
        @warnings,
        ISNULL(@tokens_used, 0),
        @scan_status
    );

    -- Lấy ID của dòng vừa INSERT
    SET @new_scan_id = SCOPE_IDENTITY();
END;
GO

PRINT N'✅ Stored Procedure usp_log_scan đã tạo thành công';
GO


-- ============================================================
-- BƯỚC 4: VIEW v_scan_summary
-- ============================================================
--
-- QUYẾT ĐỊNH THIẾT KẾ:
--
--   VIEW này giống v_daily_usage nhưng cho Food Scan:
--   → Python gọi 1 dòng để biết hôm nay quét bao nhiêu lần
--   → Phân loại rõ: thành công / không phải đồ ăn / lỗi
--   → Dùng để hiển thị thống kê trên UI hoặc trong báo cáo đồ án
--
-- ============================================================
IF OBJECT_ID('dbo.v_scan_summary', 'V') IS NOT NULL
BEGIN
    DROP VIEW dbo.v_scan_summary;
    PRINT N'♻  Đã xóa VIEW v_scan_summary cũ để tạo lại';
END
GO

CREATE VIEW dbo.v_scan_summary AS
SELECT
    -- Lọc theo user (NULL = chưa login — group riêng)
    user_id,

    -- Ngày quét (bỏ phần giờ)
    CAST(scanned_at AS DATE)                                        AS scan_date,

    -- Tổng số lần quét trong ngày
    COUNT(*)                                                        AS total_scans,

    -- Đếm theo từng loại kết quả
    SUM(CASE WHEN scan_status = 'success'  THEN 1 ELSE 0 END)      AS success_count,
    SUM(CASE WHEN scan_status = 'not_food' THEN 1 ELSE 0 END)      AS not_food_count,
    SUM(CASE WHEN scan_status = 'error'    THEN 1 ELSE 0 END)      AS error_count,

    -- Tổng token Vision tiêu thụ trong ngày
    COALESCE(SUM(tokens_used), 0)                                   AS total_tokens

FROM dbo.food_scan_log
GROUP BY
    user_id,
    CAST(scanned_at AS DATE);
GO

PRINT N'✅ VIEW v_scan_summary đã tạo thành công';
GO


-- ============================================================
-- BƯỚC 5: KIỂM TRA KẾT QUẢ
-- ============================================================

-- 1. Xem cấu trúc bảng food_scan_log
SELECT
    COLUMN_NAME,
    DATA_TYPE,
    CHARACTER_MAXIMUM_LENGTH,
    IS_NULLABLE,
    COLUMN_DEFAULT
FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_NAME = 'food_scan_log'
ORDER BY ORDINAL_POSITION;
GO

-- 2. Xem các INDEX đã tạo
SELECT
    i.name          AS index_name,
    c.name          AS column_name,
    ic.key_ordinal  AS col_order
FROM sys.indexes i
JOIN sys.index_columns ic ON i.object_id = ic.object_id AND i.index_id = ic.index_id
JOIN sys.columns c        ON ic.object_id = c.object_id AND ic.column_id = c.column_id
WHERE i.object_id = OBJECT_ID('dbo.food_scan_log')
ORDER BY i.name, ic.key_ordinal;
GO

-- 3. Test Stored Procedure với dữ liệu mẫu
DECLARE @id INT;

-- Test case 1: Quét thành công
EXEC dbo.usp_log_scan
    @user_id     = NULL,
    @image_path  = 'C:\test\banh_mi.jpg',
    @food_name   = N'Bánh mì thịt nguội',
    @description = N'Ổ bánh mì giòn với thịt nguội, chả lụa, rau thơm.',
    @benefits    = N'• Cung cấp tinh bột nhanh\n• Protein từ thịt nguội',
    @warnings    = N'• Nhiều natri\n• Không nên ăn quá 2 ổ/ngày',
    @tokens_used = 350,
    @new_scan_id = @id OUTPUT;
PRINT N'Test 1 — scan_id vừa tạo: ' + CAST(@id AS VARCHAR);

-- Test case 2: Không phải món ăn
EXEC dbo.usp_log_scan
    @user_id     = NULL,
    @image_path  = 'C:\test\chay.jpg',
    @food_name   = N'KHÔNG PHẢI MÓN ĂN',
    @description = N'Ảnh không chứa món ăn',
    @tokens_used = 120,
    @new_scan_id = @id OUTPUT;
PRINT N'Test 2 — scan_id vừa tạo: ' + CAST(@id AS VARCHAR);

-- Test case 3: Lỗi API
EXEC dbo.usp_log_scan
    @user_id     = NULL,
    @food_name   = N'Lỗi kết nối',
    @tokens_used = 0,
    @new_scan_id = @id OUTPUT;
PRINT N'Test 3 — scan_id vừa tạo: ' + CAST(@id AS VARCHAR);
GO

-- 4. Xem dữ liệu test vừa insert
SELECT
    scan_id,
    food_name,
    tokens_used,
    scan_status,
    scanned_at
FROM dbo.food_scan_log
ORDER BY scan_id DESC;
GO

-- 5. Test VIEW v_scan_summary
SELECT * FROM dbo.v_scan_summary;
GO

-- 6. Dọn dẹp dữ liệu test sau khi xác nhận OK
-- ⚠️ Bỏ comment dòng dưới SAU KHI đã xem kết quả bước 4 và 5
-- DELETE FROM dbo.food_scan_log WHERE image_path LIKE 'C:\test\%' OR food_name = N'Lỗi kết nối';
-- PRINT N'🧹 Đã xóa dữ liệu test';
GO

-- ============================================================
-- Nếu tất cả chạy không lỗi → patch v1.4 thành công! ✅
-- Bước tiếp theo: thêm hàm log_scan() vào fooder_database.py
-- ============================================================