import os
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters
)

# ================== CONFIG ==================
TOKEN = os.getenv("BOT_AUTH")  # ضع التوكن في Environment Variable
BANNER_IMAGE = "BACKGROUND05.png"  # صورة الواجهة

# ================== VARINT ==================
def decode_varint(data: bytes, start: int):
    value = 0
    shift = 0
    pos = start
    while True:
        b = data[pos]
        value |= (b & 0x7F) << shift
        if not (b & 0x80):
            break
        shift += 7
        pos += 1
    return value, pos - start + 1


def encode_varint(num: int) -> bytes:
    out = []
    while num > 0x7F:
        out.append((num & 0x7F) | 0x80)
        num >>= 7
    out.append(num)
    return bytes(out)


# ================== UID FINDER ==================
def find_uid(data: bytes):
    for i in range(len(data) - 6):
        if data[i] != 0x38:
            continue
        try:
            value, length = decode_varint(data, i + 1)
            end = i + 1 + length
            if (
                data[end] == 0x42
                and length >= 3
                and value > 100000
            ):
                return i + 1, length, value
        except:
            pass
    return None


# ================== UI ==================
def keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔍 Detect UID", callback_data="detect")],
        [
            InlineKeyboardButton("✏️ Update UID", callback_data="update"),
            InlineKeyboardButton("🧹 Clear UID", callback_data="clear")
        ]
    ])


# ================== HANDLERS ==================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    with open(BANNER_IMAGE, "rb") as img:
        await update.message.reply_photo(
            photo=img,
            caption=(
                "🎮 **Craftland UID Editor Bot**\n\n"
                "• أرسل ملف `.bytes`\n"
                "• سيتم استخراج UID تلقائيًا\n"
                "• عدّل UID أو امسحه بسهولة\n"
            ),
            parse_mode="Markdown",
            reply_markup=keyboard()
        )


async def file_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    doc = update.message.document
    tg_file = await doc.get_file()
    data = await tg_file.download_as_bytearray()

    uid = find_uid(data)
    if not uid:
        await update.message.reply_text("❌ UID غير موجود في الملف")
        return

    context.user_data["file"] = data
    context.user_data["uid"] = uid

    start_offset, length, value = uid

    await update.message.reply_text(
        f"✅ **UID Detected**\n\n"
        f"🔢 UID: `{value}`\n"
        f"📍 Offset: `0x{start_offset:X}`\n"
        f"📦 Length: `{length} bytes`",
        parse_mode="Markdown",
        reply_markup=keyboard()
    )


async def buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "update":
        await query.message.reply_text("✏️ أرسل UID الجديد (أرقام فقط)")

    elif query.data == "clear":
        await apply_uid(update, context, 0)


async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.text.isdigit():
        return
    new_uid = int(update.message.text)
    await apply_uid(update, context, new_uid)


async def apply_uid(update, context, new_uid: int):
    if "file" not in context.user_data:
        await update.effective_message.reply_text("❌ أرسل ملف أولًا")
        return

    data = context.user_data["file"]
    start, length, _ = context.user_data["uid"]

    new_var = encode_varint(new_uid)
    new_data = data[:start] + new_var + data[start + length:]

    await update.effective_message.reply_document(
        document=new_data,
        filename="Craftland_Modified.bytes",
        caption="✅ UID Updated Successfully"
    )


# ================== RUN ==================
def main():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.Document.ALL, file_handler))
    app.add_handler(CallbackQueryHandler(buttons))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))

    print("🤖 Bot is running...")
    app.run_polling()


if __name__ == "__main__":
    main()
