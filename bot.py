import os
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, LabeledPrice
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, PreCheckoutQueryHandler, CallbackQueryHandler
import psycopg

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHANNEL_ID = int(os.getenv("CHANNEL_ID"))
ADMIN_ID = int(os.getenv("ADMIN_ID"))
DATABASE_URL = os.getenv("DATABASE_URL")

# سعر نشر الدعاء بالنجوم
DUA_PRICE = 1 # نجمة واحدة

# الاتصال بقاعدة البيانات
conn = psycopg.connect(DATABASE_URL)
cur = conn.cursor()
cur.execute("""
    CREATE TABLE IF NOT EXISTS duas (
        id SERIAL PRIMARY KEY,
        user_id BIGINT,
        text TEXT,
        message_id BIGINT,
        amen_count INT DEFAULT 0
    )
""")
conn.commit()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "اهلاً بيك 🌟\nارسل دعاءك وادفع نجمة واحدة حتى ينشر بالقناة\n\nالدعاء + زر آمين 🤲"
    )

async def handle_dua(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_dua = update.message.text
    user_id = update.message.from_user.id
    
    # حفظ الدعاء مؤقتاً
    context.user_data['pending_dua'] = user_dua
    
    # انشاء فاتورة الدفع بالنجوم
    prices = [LabeledPrice("نشر دعاء", DUA_PRICE)]
    await update.message.reply_invoice(
        title="نشر دعاء",
        description=f"دفع {DUA_PRICE} نجمة لنشر دعاءك بالقناة",
        payload=f"dua_{user_id}",
        provider_token="", # فارغ للنجوم
        currency="XTR", # XTR = Telegram Stars
        prices=prices
    )

async def precheckout_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.pre_checkout_query
    await query.answer(ok=True)

async def successful_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    user_dua = context.user_data.get('pending_dua')
    
    if not user_dua:
        await update.message.reply_text("صار خطأ، ارسل الدعاء مرة ثانية")
        return
    
    # نشر الدعاء بالقناة
    keyboard = [[InlineKeyboardButton("آمين 🤲 0", callback_data="amen_0")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    sent_msg = await context.bot.send_message(
        chat_id=CHANNEL_ID,
        text=f"🤲 {user_dua}",
        reply_markup=reply_markup
    )
    
    # حفظ بالداتابيس
    cur.execute(
        "INSERT INTO duas (user_id, text, message_id) VALUES (%s, %s, %s) RETURNING id",
        (user_id, user_dua, sent_msg.message_id)
    )
    dua_id = cur.fetchone()[0]
    conn.commit()
    
    # تحديث زر آمين بالـ dua_id
    new_keyboard = [[InlineKeyboardButton("آمين 🤲 0", callback_data=f"amen_{dua_id}")]]
    await context.bot.edit_message_reply_markup(
        chat_id=CHANNEL_ID,
        message_id=sent_msg.message_id,
        reply_markup=InlineKeyboardMarkup(new_keyboard)
    )
    
    await update.message.reply_text("✅ تم نشر دعاءك بالقناة بنجاح")
    del context.user_data['pending_dua']

async def amen_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    dua_id = int(query.data.split("_")[1])
    
    # زيادة العداد
    cur.execute("UPDATE duas SET amen_count = amen_count + 1 WHERE id = %s RETURNING amen_count", (dua_id,))
    new_count = cur.fetchone()[0]
    conn.commit()
    
    # تحديث الزر
    keyboard = [[InlineKeyboardButton(f"آمين 🤲 {new_count}", callback_data=f"amen_{dua_id}")]]
    await query.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup(keyboard))
    await query.answer("آمين يارب 🤲")

def main():
    app = Application.builder().token(BOT_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_dua))
    app.add_handler(PreCheckoutQueryHandler(precheckout_callback))
    app.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment))
    app.add_handler(CallbackQueryHandler(amen_callback, pattern="^amen_"))
    
    app.run_polling()

if __name__ == "__main__":
    main()
