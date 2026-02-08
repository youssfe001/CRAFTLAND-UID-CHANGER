import os
import re
import io
import logging
from typing import Optional, Tuple
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputFile,
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

# ================= CONFIG =================
TOKEN = os.getenv("BOT_AUTH")  # ضع توكن البوت هنا كمتغير بيئي
BANNER_IMAGE = "BACKGROUND05.png"  # صورة الواجهة (إن وُجدت)
# قبول الأسماء ProjectData_slot_1.bytes .. ProjectData_slot_12.bytes
FILENAME_PATTERN = re.compile(r"^ProjectData_slot_(1[0-2]|[1-9])\.bytes$", re.IGNORECASE)

# ================= LOGGING =================
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ================= PROTOBUF VARINT =================
def decode_varint(data: bytes, start: int) -> Tuple[int, int]:
    """
    Decode protobuf varint starting at index `start` in `data`.
    Returns (value, length).
    Raises ValueError on invalid/malformed varint or out-of-bounds.
    """
    value = 0
    shift = 0
    pos = start
    max_bits = 64 * 2  # very generous safety limit

    while True:
        if pos >= len(data):
            raise ValueError("Unexpected end of data while decoding varint")
        b = data[pos]
        value |= (b & 0x7F) << shift
        pos += 1
        if not (b & 0x80):
            break
        shift += 7
        if shift > max_bits:
            raise ValueError("Varint too long / potentially corrupted")

    length = pos - start
    return value, length


def encode_varint(num: int) -> bytes:
    """
    Encode integer `num` as protobuf varint.
    Supports 0.
    """
    if num < 0:
        raise ValueError("Varint cannot be negative")
    if num == 0:
        return b"\x00"
    out = bytearray()
    while num:
        to_write = num & 0x7F
        num >>= 7
        if num:
            out.append(to_write | 0x80)
        else:
            out.append(to_write)
    return bytes(out)


# ================= UID FINDER =================
PATTERN_START = 0x38  # byte before varint
PATTERN_END = 0x42    # byte after varint

def find_uid(data: bytes) -> Optional[dict]:
    """
    Scan the binary for pattern: 0x38 <varint uid> 0x42
    Returns dict {offset, length, uid} for the FIRST valid match, else None.
    """
    size = len(data)
    # scan full buffer; ensure enough room for at least 3 bytes
    i = 0
    while i < size - 2:
        if data[i] != PATTERN_START:
            i += 1
            continue
        try:
            # decode varint starting at i+1
            uid_val, uid_len = decode_varint(data, i + 1)
            end_idx = i + 1 + uid_len
            # ensure in bounds and pattern end matches
            if end_idx < size and data[end_idx] == PATTERN_END:
                # optional sanity-filter: ensure UID is reasonably large (but allow small if you want)
                # Here we accept any non-negative integer; adjust if you want stricter filter
                return {"offset": i + 1, "length": uid_len, "uid": uid_val}
            # move i forward by 1 to continue scanning
            i += 1
        except Exception:
            # malformed varint at this position -> continue scanning
            i += 1
    return None


# ================= VALIDATOR =================
def validate_craftland_file(filename: str) -> bool:
    """
    Accept only ProjectData_slot_1..12.bytes (case-insensitive).
    """
    return bool(FILENAME_PATTERN.match(filename))


# ================= UI / KEYBOARD =================
def main_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔍 Detect UID", callback_data="detect")],
        [
            InlineKeyboardButton("✏️ Update UID", callback_data="update"),
            InlineKeyboardButton("🧹 Clear UID", callback_data="clear")
        ]
    ])


# ================= HANDLERS =================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /start - show banner if exists and short instructions.
    """
    text = (
        "🎮 *Craftland UID Editor Bot*\n\n"
        "📌 Send exactly one file named `ProjectData_slot_X.bytes` (X = 1..12).\n"
        "• Bot will detect the UID (Protobuf varint) and let you Update or Clear it.\n\n"
        "🔒 Only properly named slot files are accepted."
    )
    try:
        if os.path.isfile(BANNER_IMAGE):
            await update.message.reply_photo(
                photo=open(BANNER_IMAGE, "rb"),
                caption=text,
                parse_mode="Markdown",
                reply_markup=main_keyboard()
            )
            return
    except Exception as e:
        logger.warning("Cannot send banner image: %s", e)

    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=main_keyboard())


async def file_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handle incoming document:
    - validate filename
    - download bytes
    - detect UID
    - store state in context.user_data
    """
    doc = update.message.document
    filename = doc.file_name if doc and doc.file_name else None

    if not filename:
        await update.message.reply_text("❌ Invalid file (no filename).")
        return

    if not validate_craftland_file(filename):
        await update.message.reply_text(
            "❌ File rejected.\nFilename must be: `ProjectData_slot_1.bytes` .. `ProjectData_slot_12.bytes`",
            parse_mode="Markdown"
        )
        return

    # download file content
    try:
        tg_file = await doc.get_file()
        raw = await tg_file.download_as_bytearray()
    except Exception as e:
        logger.exception("Failed to download file: %s", e)
        await update.message.reply_text("❌ Failed to download file. Try again.")
        return

    # find UID
    result = find_uid(raw)
    if not result:
        await update.message.reply_text("❌ UID pattern not found inside the file.")
        return

    # store clean state
    context.user_data.clear()
    context.user_data["file_bytes"] = bytes(raw)  # immutable copy
    context.user_data["uid_info"] = result
    context.user_data["filename"] = filename

    # extract slot number for user clarity
    slot_match = re.search(r"_(1[0-2]|[1-9])\.bytes$", filename, re.IGNORECASE)
    slot_num = slot_match.group(1) if slot_match else "?"

    await update.message.reply_text(
        (
            f"✅ *Accepted* `{filename}` (slot `{slot_num}`)\n\n"
            f"🔢 UID: `{result['uid']}`\n"
            f"📍 Offset: `0x{result['offset']:X}`\n"
            f"📦 Length: `{result['length']} bytes`\n\n"
            "Use the buttons below to Update or Clear the UID."
        ),
        parse_mode="Markdown",
        reply_markup=main_keyboard()
    )


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handle inline buttons:
    - detect: re-send current UID info
    - update: set mode to update and ask for new UID
    - clear: apply uid=0 immediately (confirmation step)
    """
    query = update.callback_query
    await query.answer()
    data = query.data

    if "file_bytes" not in context.user_data:
        await query.message.reply_text("❌ No active file. Send a valid slot file first.")
        return

    info = context.user_data.get("uid_info")
    if data == "detect":
        await query.message.reply_text(
            f"🔍 Detected UID: `{info['uid']}`\nOffset: `0x{info['offset']:X}` Length: `{info['length']} bytes`",
            parse_mode="Markdown"
        )
        return

    if data == "update":
        context.user_data["mode"] = "update"
        await query.message.reply_text("✏️ Send the new UID as a decimal number (e.g. `6639287909`).")
        return

    if data == "clear":
        # Ask for explicit confirmation (user must reply 'CONFIRM' to proceed)
        context.user_data["mode"] = "confirm_clear"
        await query.message.reply_text(
            "⚠️ You requested to clear the UID.\n"
            "If you are sure, reply with the word `CONFIRM` to proceed.",
            parse_mode="Markdown"
        )
        return


async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handle text replies when in a specific mode:
    - update mode -> expect decimal UID
    - confirm_clear mode -> expect 'CONFIRM'
    """
    if "file_bytes" not in context.user_data:
        # ignore plain chat messages
        return

    mode = context.user_data.get("mode")
    if not mode:
        return

    text = (update.message.text or "").strip()

    if mode == "update":
        if not text.isdigit():
            await update.message.reply_text("❌ Invalid UID. Send digits only (decimal).")
            return
        new_uid = int(text)
        await apply_uid_and_send(update, context, new_uid)
        return

    if mode == "confirm_clear":
        if text.upper() != "CONFIRM":
            await update.message.reply_text("🛑 Clear canceled. Send `CONFIRM` to clear the UID.")
            context.user_data.pop("mode", None)
            return
        await apply_uid_and_send(update, context, 0)
        return


async def apply_uid_and_send(update: Update, context: ContextTypes.DEFAULT_TYPE, new_uid: int):
    """
    Perform safe splice: HEAD + newVarint + TAIL, then send file back.
    """
    try:
        raw = context.user_data["file_bytes"]
        info = context.user_data["uid_info"]
        filename = context.user_data["filename"]

        # encode new varint
        new_var = encode_varint(new_uid)

        # splice safely
        new_data = raw[: info["offset"]] + new_var + raw[info["offset"] + info["length"] :]

        # send as file
        bio = io.BytesIO(new_data)
        bio.name = filename

        await update.effective_message.reply_document(
            document=InputFile(bio),
            caption=f"✅ UID updated to `{new_uid}`. File: `{filename}`",
            parse_mode="Markdown"
        )

        # cleanup user state
        context.user_data.clear()

    except Exception as e:
        logger.exception("Failed to apply UID: %s", e)
        await update.effective_message.reply_text("❌ Failed to update file. Internal error.")


# ================= RUN =================
def main():
    if not TOKEN:
        raise RuntimeError("Missing BOT_AUTH environment variable (set your Telegram bot token).")

    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.Document.ALL, file_handler))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))

    logger.info("🤖 Bot is running (polling)...")
    app.run_polling()

if __name__ == "__main__":
    main()