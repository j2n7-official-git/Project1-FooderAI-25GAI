"""
gemini_service.py — Dịch vụ Gemini AI cho GritalystAI
=======================================================
Dùng google-genai 2.7.0 (package mới thay thế google-generativeai)

Cài module cần thiết:
  google-genai      (đã cài 2.7.0)
  python-dotenv     (đã cài)

[UPDATE v1.1] — 29/05/2026 — Tài · Tuấn · Vanh
  + Đổi từ google-generativeai → google-genai 2.7.0
  + Giữ nguyên system prompt + DB log
"""

import os
import sys

# SYS.PATH FIX — tìm fooder_database.py trong cùng thư mục pages/
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from google import genai
from google.genai import types
from dotenv import load_dotenv

# Nạp API key từ .env
load_dotenv(os.path.join(os.path.dirname(__file__), '', '.env'))
_API_KEY   = os.getenv("GEMINI_API_KEY", "")
#top 3 test model: "gemini-2.5-flash", "gemini-2.5-flash-lite", "gemini-2.5-pro"
_MODEL     = "gemini-2.5-flash-lite"

# Nạp fooder_database để log tin nhắn
try:
    from fooder_database import log_message
    _DB_AVAILABLE = True
except Exception:
    _DB_AVAILABLE = False

# ── SYSTEM PROMPT GRITALYSTAI ─────────────────────────────────────────
_SYSTEM_PROMPT = """
Bạn là GritalystAI — trợ lý dinh dưỡng và thể dục của FooderAI, nhóm 25GAI (VKU).

## TÍNH CÁCH
Kết hợp giữa bác sĩ dinh dưỡng nghiêm túc, điều độ và người bạn thân thiện, luôn ủng hộ.
Tức là: đưa ra lời khuyên chính xác, có cơ sở — nhưng diễn đạt ấm áp, gần gũi, không lạnh lùng.
Dùng ngôi "mình/bạn". Emoji 🌿🥗💪 dùng vừa phải, không lạm dụng.

## PHẠM VI
Bạn là bác sĩ dinh dưỡng kiêm huấn luyện viên thể lực. Trả lời thoải mái các chủ đề:
1. Dinh dưỡng: calo, macro, vi chất, chế độ ăn uống
2. Thực phẩm: món ăn, công thức, thành phần dinh dưỡng
3. Luyện tập: bài tập, lịch tập, cường độ phù hợp mục tiêu
4. Chỉ số sức khỏe: BMI, BMR, TDEE, cân nặng, chiều cao
5. Mục tiêu: giảm cân, tăng cân, duy trì cân nặng
6. Kiến thức nền liên quan: sinh lý học cơ bản, giải phẫu cơ bắp, tâm lý ăn uống, giấc ngủ & phục hồi, stress và sức khỏe
7. Tính toán đơn giản khi user đang tính khẩu phần, calo, chỉ số
8. Giao tiếp thông thường: chào hỏi, cảm ơn, hỏi thăm ngắn
9. Nếu có hỏi các câu hỏi toán, hãy giúp bạn trả lời xem như là bài tập, mô hình xin cho phép chỉ tính cộng, trừ, nhân, chia
    lũy thừa (^), và căn bậc 2 (được kí hiệu chữ là sqrt(số hoặc biểu thức)), cho phép tìm x cơ bản trong tập số R, tức nếu
    x^2 = -1 thì phương trình này sẽ không có nghiệm, tập R thôi chứ chưa phải là tập C (số phức), cởi mở thêm các bài toán đố vui
    áp dụng với thực tế.

## ĐIỀU LUẬT
1. Câu hỏi hoàn toàn ngoài phạm vi (chính trị, lập trình, pháp luật...) → từ chối nhẹ nhàng, gợi ý hỏi đúng chủ đề
2. Không chẩn đoán bệnh, không kê thuốc — gợi ý gặp bác sĩ/chuyên gia nếu cần
3. Không trả lời nội dung tục tĩu, bạo lực, gây hại
4. Luôn dùng tiếng Việt trừ khi user hỏi tiếng Anh
5. Không bịa số liệu — nếu context có sẵn dữ liệu sổ tay thì dùng, không tự bịa
6. Độ dài câu trả lời: 420–730 ký tự (tính cả dấu cách) — PHẢI kết thúc bằng câu hoàn chỉnh, không được cắt ngang

## CÁ NHÂN HÓA
Nếu có thông tin user (BMI, TDEE, mục tiêu), ưu tiên dùng để trả lời phù hợp hơn.

## ĐỊNH DẠNG
- Bullet points khi liệt kê (tối đa 5 điểm)
- **In đậm** tên món ăn hoặc chỉ số quan trọng
- Kết thúc bằng 1 câu động viên ngắn nếu phù hợp
"""


def _build_user_context(user_profile: dict | None) -> str:
    """Tạo context từ hồ sơ user để cá nhân hóa câu trả lời."""
    if not user_profile:
        return ""

    goal_map     = {"lose": "giảm cân", "maintain": "duy trì", "gain": "tăng cân"}
    gender_map   = {"male": "Nam", "female": "Nữ"}
    activity_map = {
        1.2: "ít vận động", 1.375: "nhẹ nhàng",
        1.55: "vừa phải",  1.725: "năng động", 1.9: "rất cao",
    }

    age    = user_profile.get("age")
    height = user_profile.get("height_cm")
    weight = user_profile.get("weight_kg")
    if not (age and height and weight):
        return ""

    name     = user_profile.get("display_name") or "Bạn"
    gender   = gender_map.get(user_profile.get("gender", ""), "")
    goal     = goal_map.get(user_profile.get("goal", ""), "")
    activity = activity_map.get(user_profile.get("activity_level"), "")
    bmi      = user_profile.get("bmi")
    tdee     = user_profile.get("tdee")

    lines = [f"[THÔNG TIN NGƯỜI DÙNG — {name}]"]
    lines.append(f"- Tuổi: {age}, Giới tính: {gender}")
    lines.append(f"- Chiều cao: {height}cm, Cân nặng: {weight}kg")
    if bmi:      lines.append(f"- BMI: {bmi:.1f}")
    if tdee:     lines.append(f"- TDEE: {tdee} kcal/ngày")
    if goal:     lines.append(f"- Mục tiêu: {goal}")
    if activity: lines.append(f"- Mức vận động: {activity}")
    lines.append("[Dùng thông tin này để cá nhân hóa câu trả lời]\n")
    return "\n".join(lines)


def _build_almanac_context(user_message: str) -> str:
    """
    Tìm món ăn / bài tập liên quan trong FOOD_DATA và EXERCISE_MAP,
    inject vào context để Gemini tham khảo trước khi trả lời.

    Tại sao làm vậy?
    → Almanac đã có data chuẩn (calo, dinh dưỡng, bước tập...)
    → Gemini đọc data sẵn → expand thành câu trả lời đẹp, không bịa số
    → Tiết kiệm token hơn so với để Gemini tự generate từ đầu

    Cách hoạt động:
    → Tách từ khóa từ câu hỏi user
    → So khớp với tên món / tên bài tập (case-insensitive)
    → Nếu khớp → đưa data vào context, tối đa 3 món + 2 bài tập
    """
    try:
        import sys, os
        _root  = os.path.dirname(os.path.abspath(__file__))  # FooderAI/
        _pages = os.path.join(_root, "pages")                # FooderAI/pages/

        # food_image_map.py và gym_exercise_map.py nằm trong pages/
        # → thêm pages/ vào sys.path để import được
        for _p in [_root, _pages]:
            if _p not in sys.path:
                sys.path.insert(0, _p)

        # Import data từ 2 file sổ tay
        from food_image_map import FOOD_DATA
        from gym_exercise_map import EXERCISE_MAP
    except Exception:
        return ""  # không có data → trả về rỗng, Gemini tự xử

    msg_lower = user_message.lower()
    lines = []

    # ── TÌM MÓN ĂN LIÊN QUAN ────────────────────────────────────────
    # Gộp tất cả món từ food + ingredient + drink vào 1 list
    all_foods = []
    for category in FOOD_DATA.values():
        all_foods.extend(category)

    matched_foods = []
    for item in all_foods:
        ten = item[0].lower()  # item = (tên, calo, mô tả, [chất], ảnh)
        # Kiểm tra tên món có xuất hiện trong câu hỏi không
        if any(word in msg_lower for word in ten.split() if len(word) > 2):
            matched_foods.append(item)
        if len(matched_foods) >= 3:
            break

    if matched_foods:
        lines.append("[DỮ LIỆU SỔ TAY MÓN ĂN — tham khảo để trả lời chính xác]")
        for ten, calo, mo_ta, chat_dd, _ in matched_foods:
            lines.append(f"• {ten}: {calo} kcal/100g")
            lines.append(f"  Mô tả: {mo_ta}")
            lines.append(f"  Dinh dưỡng nổi bật: {', '.join(chat_dd)}")
        lines.append("")

    # ── TÌM BÀI TẬP LIÊN QUAN ───────────────────────────────────────
    matched_exercises = []
    for key, ex in EXERCISE_MAP.items():
        ten = ex.get("ten", "").lower()
        if any(word in msg_lower for word in ten.split() if len(word) > 2):
            matched_exercises.append(ex)
        if len(matched_exercises) >= 2:
            break

    if matched_exercises:
        lines.append("[DỮ LIỆU SỔ TAY BÀI TẬP — tham khảo để trả lời chính xác]")
        for ex in matched_exercises:
            lines.append(f"• {ex['ten']} ({ex['nhom_tuoi']})")
            lines.append(f"  Tổng quan: {ex['tong_quan'][:150]}...")
            loiich = ex.get("loi_ich", [])
            if loiich:
                lines.append(f"  Lợi ích: {loiich[0]}")
        lines.append("")

    if not lines:
        return ""  # không khớp gì → không inject

    lines.append("[Dùng dữ liệu trên để expand câu trả lời, không bịa thêm số liệu]\n")
    return "\n".join(lines)


def _write_token_log(user_msg: str, bot_reply: str,
                     token_in: int, token_out: int, token_total: int):
    """
    Ghi log token ra file gemini_token_log.txt cùng thư mục pages/.
    Mỗi lần gọi API → append 1 block vào file — không xóa log cũ.

    Format log:
    ════════════════════════════════════════
    [2026-05-29 09:15:32]
    USER   : Tôi nên ăn gì buổi sáng?
    BOT    : Buổi sáng bạn nên...
    TOKENS : Input=45 | Output=87 | Total=132
    ════════════════════════════════════════

    Tại sao ghi ra .txt thay vì chỉ print?
    - print mất sau khi đóng terminal
    - .txt giữ lại toàn bộ lịch sử → xem lại được
    - Dễ đọc bằng Notepad, không cần tool đặc biệt
    - Phục vụ báo cáo đồ án (chứng minh API đang hoạt động)
    """
    from datetime import datetime as _dt

    #UPDATE Tạo thư mục gritalyst_log_user/ nếu chưa có
    log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "pages/gritalyst_log_user")
    os.makedirs(log_dir, exist_ok=True)  # exist_ok=True: không lỗi nếu đã có rồi
    log_path = os.path.join(log_dir, "pages/gemini_token_log.txt")

    timestamp = _dt.now().strftime("%Y-%m-%d %H:%M:%S")
    separator = "═" * 48
    try:
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(f"\n{separator}\n")
            f.write(f"[{timestamp}]\n")
            f.write(f"USER   : {user_msg[:120]}\n")   # cắt 120 ký tự để log không quá dài
            f.write(f"BOT    : {bot_reply[:200]}\n")  # cắt 200 ký tự
            f.write(f"TOKENS : Input={token_in} | Output={token_out} | Total={token_total}\n")
            f.write(f"{separator}\n")
    except Exception:
        pass  # không crash app nếu không ghi được file


def ask_gritalyst(
    user_message: str,
    chat_history: list[dict] | None = None,
    user_profile: dict | None       = None,
    session_id:   int | None        = None,
    user_id:      int | None        = None,
    nsfw_level:   int               = 0,
) -> str:
    """
    Gọi Gemini API và trả về câu trả lời của GritalystAI.

    Tham số:
        user_message : tin nhắn của user
        chat_history : lịch sử chat dạng list of Content objects
        user_profile : dict thông tin sức khỏe user từ DB
        session_id   : ID session để log DB
        user_id      : ID user để log DB
        nsfw_level   : 0=sạch (đã filter trước khi gọi hàm này)

    Trả về: str — câu trả lời hoặc thông báo lỗi thân thiện
    """
    if not _API_KEY:
        return "⚠️ Gritalyst chưa được cấu hình API key. Vui lòng kiểm tra file .env!"

    try:
        # Khởi tạo client google-genai mới
        client = genai.Client(api_key=_API_KEY)

        # Đính kèm context user vào tin nhắn
        user_context    = _build_user_context(user_profile)
        almanac_context = _build_almanac_context(user_message)
        # Thứ tự: almanac data → user profile → câu hỏi
        # Almanac đứng trước để Gemini đọc data sẵn trước khi xử lý câu hỏi
        full_message = f"{almanac_context}{user_context}{user_message}" if (almanac_context or user_context) else user_message

        # Build contents từ history + tin nhắn hiện tại
        # google-genai dùng types.Content thay vì dict
        contents = []
        for msg in (chat_history or []):
            role  = msg.get("role", "user")
            parts = msg.get("parts", [""])
            contents.append(types.Content(
                role=role,
                parts=[types.Part(text=p) for p in parts]
            ))
        # Thêm tin nhắn hiện tại
        contents.append(types.Content(
            role="user",
            parts=[types.Part(text=full_message)]
        ))

        # Gọi API
        response = client.models.generate_content(
            model=_MODEL,
            contents=contents,
            config=types.GenerateContentConfig(
                # system_instruction: "linh hồn" của bot — nạp _SYSTEM_PROMPT vào đây
                # Gemini đọc cái này TRƯỚC KHI đọc tin nhắn user
                # → định hình tính cách, phạm vi, điều luật của GritalystAI
                system_instruction=_SYSTEM_PROMPT,

                # max_output_tokens: giới hạn độ dài câu trả lời
                # 1 token ≈ 4 ký tự tiếng Anh, ≈ 2-3 ký tự tiếng Việt
                # 1250 token ≈ 3000 - 4000 ký tự tiếng Việt — vừa đủ cho 420-730 ký tự yêu cầu
                # Tăng số này → câu trả lời dài hơn nhưng tốn token hơn
                max_output_tokens=750,

                # temperature: độ "sáng tạo/ngẫu nhiên" của câu trả lời
                # 0.0 = máy móc, lặp lại y chang mỗi lần
                # 0.7 = cân bằng giữa chính xác và tự nhiên ← mức khuyến nghị
                # 0.75 = nhỉnh hơn chút, câu văn đa dạng hơn, vẫn ổn ✅
                # 1.0 = rất sáng tạo, đôi khi "bay" quá
                # 2.0 = tối đa, dễ bịa đặt — KHÔNG dùng cho chatbot y tế/dinh dưỡng
                temperature=0.75,
            )
        )

        reply = response.text.strip() if response.text else ""

        # ── TOKEN TRACKING — "ví tiền" của Gemini ────────────────
        # usage_metadata chứa 3 chỉ số quan trọng:
        #   prompt_token_count     : token của câu hỏi + system prompt + history
        #   candidates_token_count : token của câu trả lời
        #   total_token_count      : tổng cả 2 (cái này tính tiền nếu paid)
        tokens_input  = None
        tokens_output = None
        tokens_used   = None
        try:
            usage         = response.usage_metadata
            tokens_input  = usage.prompt_token_count
            tokens_output = usage.candidates_token_count
            tokens_used   = usage.total_token_count

            # In ra terminal để debug trong quá trình dev
            print("-" * 40)
            print(f"📊 Token câu này:  Input: {tokens_input} | Output: {tokens_output}")
            print(f"📈 Tổng token tích lũy: {tokens_used}")
            print("-" * 40)

            # Ghi log ra file .txt để đọc sau
            # Log nằm cùng thư mục pages/ với tên gemini_token_log.txt
            _write_token_log(user_message, reply, tokens_input, tokens_output, tokens_used)

        except Exception:
            pass

        # Log vào DB
        if _DB_AVAILABLE and session_id:
            try:
                log_message(
                    session_id=session_id, user_id=user_id,
                    user_message=user_message, bot_response=reply,
                    msg_type="normal", nsfw_level=nsfw_level,
                    tokens_used=tokens_used,
                )
            except Exception:
                pass

        return reply if reply else "🌿 Gritalyst chưa có câu trả lời phù hợp — bạn thử hỏi lại nhé!"

    except Exception as e:
        err = str(e).lower()
        if "quota" in err or "429" in err:
            return "🌿 Gritalyst đang bận một chút — bạn thử lại sau vài giây nhé!"
        elif "api_key" in err or "invalid" in err or "api key" in err:
            return "⚠️ API key không hợp lệ. Vui lòng kiểm tra file .env!"
        elif "block" in err or "safety" in err:
            return "Gritalyst không thể trả lời câu này — thử hỏi về dinh dưỡng hoặc luyện tập nhé! 🌿"
        else:
            print(f"[Gemini ERROR] {e}")
            return "🌿 Gritalyst gặp chút sự cố — bạn thử lại nhé!"


# ══════════════════════════════════════════════════════════════════════
# SCAN FOOD IMAGE — Gemini Vision
# Thêm vào cuối gemini_service.py
# ══════════════════════════════════════════════════════════════════════

_SCAN_SYSTEM_PROMPT = """
Bạn là chuyên gia dinh dưỡng của FooderAI. Khi nhận được ảnh món ăn, hãy phân tích và trả lời ĐÚNG theo định dạng JSON sau, KHÔNG thêm bất kỳ text nào ngoài JSON:

{
  "ten": "Tên món ăn (tiếng Việt, ngắn gọn)",
  "mo_ta": "Mô tả nguồn gốc và sự tương tác của món ăn (~100 từ). Sau đó liệt kê các chất dinh dưỡng và số kcal ước tính. Dùng dấu gạch ngang, 6-8 ý.",
  "loi_diem": "Nêu lợi điểm khi ăn món này. Liệt kê 4-6 ý, mỗi ý 1 dòng bắt đầu bằng dấu •",
  "luu_y": "Nêu các lưu ý khi sử dụng (lạm dụng quá không tốt, nên kết hợp với gì). Liệt kê 4-5 ý, mỗi ý 1 dòng bắt đầu bằng dấu •"
}

Nếu ảnh KHÔNG phải món ăn:
{"ten": "KHÔNG PHẢI MÓN ĂN", "mo_ta": "Ảnh không chứa món ăn", "loi_diem": "", "luu_y": ""}
"""


def scan_food_image(image_path: str) -> dict:
    """
    Dùng Gemini Vision để nhận diện và phân tích món ăn từ ảnh.

    Tham số:
        image_path : đường dẫn đến file ảnh (.png / .jpg / .jpeg / .webp)

    Trả về: dict với keys: ten | mo_ta | loi_diem | luu_y
    """
    import base64, json, mimetypes

    _ERR = {"ten": "Lỗi phân tích", "mo_ta": "Không thể phân tích ảnh.", "loi_diem": "", "luu_y": ""}

    if not _API_KEY:
        return {**_ERR, "mo_ta": "⚠️ Chưa cấu hình API key. Kiểm tra file .env!"}
    if not os.path.exists(image_path):
        return {**_ERR, "mo_ta": f"⚠️ Không tìm thấy file ảnh: {image_path}"}

    # ── Đọc ảnh, encode base64 ────────────────────────────────────────
    mime_type, _ = mimetypes.guess_type(image_path)
    if not mime_type or not mime_type.startswith("image/"):
        mime_type = "image/jpeg"

    try:
        with open(image_path, "rb") as f:
            img_b64 = base64.b64encode(f.read()).decode("utf-8")
    except Exception as e:
        return {**_ERR, "mo_ta": f"⚠️ Lỗi đọc file ảnh: {e}"}

    try:
        client = genai.Client(api_key=_API_KEY)

        response = client.models.generate_content(
            model=_MODEL,  # gemini-2.5-flash-lite hỗ trợ vision
            contents=[
                types.Content(
                    role="user",
                    parts=[
                        # Part 1: ảnh gửi inline (base64)
                        types.Part(
                            inline_data=types.Blob(
                                mime_type=mime_type,
                                data=img_b64
                            )
                        ),
                        # Part 2: yêu cầu text
                        types.Part(text="Phân tích món ăn trong ảnh này theo đúng định dạng JSON yêu cầu.")
                    ]
                )
            ],
            config=types.GenerateContentConfig(
                system_instruction=_SCAN_SYSTEM_PROMPT,
                max_output_tokens=1200,
                temperature=0.4,  # thấp → ưu tiên chính xác hơn sáng tạo
            )
        )

        raw = response.text.strip() if response.text else ""

        # Xử lý trường hợp Gemini bọc trong ```json ... ```
        if raw.startswith("```"):
            lines = raw.split("\n")
            raw = "\n".join(lines[1:-1])

        result = json.loads(raw)

        # Đảm bảo đủ 4 keys
        for key in ("ten", "mo_ta", "loi_diem", "luu_y"):
            if key not in result:
                result[key] = ""

        print(f"[SCAN ✅] Nhận diện: {result.get('ten', '?')}")
        return result

    except json.JSONDecodeError as e:
        # Gemini trả lời nhưng không đúng JSON — vẫn hiển thị raw text
        print(f"[SCAN ⚠️] JSON parse lỗi: {e} | raw={raw[:150]}")
        return {"ten": "Đã nhận diện", "mo_ta": raw, "loi_diem": "", "luu_y": ""}

    except Exception as e:
        err = str(e).lower()
        msg = "🌿 Gemini đang bận — thử lại sau nhé!" if ("quota" in err or "429" in err) else f"⚠️ Lỗi: {e}"
        print(f"[SCAN ❌] {e}")
        return {**_ERR, "mo_ta": msg}

# ── TEST KHI CHẠY TRỰC TIẾP ──────────────────────────────────────────
if __name__ == "__main__":
    print("Test GeminiService...")
    reply = ask_gritalyst(
        user_message="Tôi nên ăn gì vào buổi sáng để giảm cân?",
        user_profile={
            "display_name": "Vanh", "age": 20, "gender": "female",
            "height_cm": 160, "weight_kg": 55, "goal": "lose",
            "activity_level": 1.375, "bmi": 21.5, "bmr": 1380, "tdee": 1898,
        },
    )
    print(f"\nGritalyst: {reply}")
    print(f"Độ dài: {len(reply)} ký tự")  # ← THÊM DÒNG NÀY

