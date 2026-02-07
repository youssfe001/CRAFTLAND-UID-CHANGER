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

BANNER_PATH = "BACKGROUND05.png"  # نفس الصورة اللي أرسلتها

# ---------- VARINT ----------
def decode_varint(data, start):
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

def encode_varint(num):
    out = []
    while num > 0x7F:
        out.append((num & 0x7F) | 0x80)
        num >>= 7
    out.append(num)
    return bytes(out)

def find_uid(data):
    for i in range(len(data) - 6):
        if data[i] == 0x38:
            try:
                val, ln = decode_varint(data, i + 1)
                end = i + 1 + ln
                if data[end] == 0x42 and ln >= 3 and val > 100000:
                    return i + 1, ln, val
            except:
                pass
    return None

# ---------- UI ----------
def main_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔍 Detect UID", callback_data="detect")],
        [
            InlineKeyboardButton("✏️ Update UID", callback_data="update"),
            InlineKeyboardButton("🧹 Clear UID", callback_data="clear")
        ]
    ])

# ---------- HANDLERS ----------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    with open(BANNER_PATH, "rb") as img:
        await update.message.reply_photo(
            photo=img,
            caption=(
                "🎮 **Craftland UID Editor**\n\n"
                "• أرسل ملف `.bytes`\n"
                "• سيتم استخراج UID تلقائيًا\n"
                "• عدّله بضغطة زر\n\n"
                "⬇️ اختر عملية:"
            ),
            parse_mode="Markdown",
            reply_markup=main_keyboard()
        )

async def file_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    doc = update.message.document
    file = await doc.get_file()
    data = await file.download_as_bytearray()

    uid = find_uid(data)
    if not uid:
        await update.message.reply_text("❌ UID غير موجود في الملف")
        return

    context.user_data["file"] = data
    context.user_data["uid"] = uid

    await update.message.reply_text(
        f"✅ **UID Detected**\n\n"
        f"🔢 UID: `{uid[2]}`\n"
        f"📍 Offset: `0x{uid[0]:X}`",
        parse_mode="Markdown",
        reply_markup=main_keyboard()
    )

async def buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()

    if q.data == "clear":
        await apply_uid(update, context, 0)

    elif q.data == "update":
        await q.message.reply_text("✏️ أرسل UID الجديد كرقم فقط")

async def apply_uid(update, context, new_uid):
    if "file" not in context.user_data:
        await update.callback_query.message.reply_text("❌ أرسل ملف أولًا")
        return

    data = context.user_data["file"]
    start, ln, _ = context.user_data["uid"]

    new_var = encode_varint(new_uid)
    new_data = data[:start] + new_var + data[start+ln:]

    await update.callback_query.message.reply_document(
        document=new_data,
        filename="Craftland_Modified.bytes",
        caption="✅ UID Updated Successfully"
    )

async def text_uid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.text.isdigit():
        return
    await apply_uid(update, context, int(update.message.text))

# ---------- RUN ----------
app = ApplicationBuilder().token("PUT_YOUR_BOT_TOKEN").build()

app.add_handler(CommandHandler("start", start))
app.add_handler(MessageHandler(filters.Document.ALL, file_handler))
app.add_handler(CallbackQueryHandler(buttons))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_uid))

app.run_polling()
