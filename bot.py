import os
import psycopg2
from urllib.parse import urlparse
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHANNEL_ID = int(os.getenv("CHANNEL_ID"))
ADMIN_ID = int(os.getenv("ADMIN_ID"))
BOT_USERNAME = os.getenv("BOT_USERNAME")

def get_db():
    result = urlparse(os.getenv("DATABASE_URL"))
    return psycopg2.connect(
        database=result.path[1:],
        user=result.username,
        password=result.password,
        host=result.hostname,
        port=result.port
    )

def init_db():
    conn = get_db()
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS prayers
                 (id SERIAL PRIMARY KEY,
                  user_id BIGINT,
                  text TEXT,
                  message_id BIGINT,
                  ameen_count INTEGER DEFAULT 0,
                  created_at TEXT,
                  is_pinned INTEGER DEFAULT 0,
                  username TEXT,
                  first_name TEXT)''')
    conn.commit()
    conn.close()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("أهلاً بك في بوت الأدعية 🤲\nأرسل دعاءك وسيتم نشره في القناة.")

async def handle_prayer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    text = update.message.text
    
    keyboard = [[InlineKeyboardButton("آمين 🤲", callback_data=f"ameen_0")]]
    sent = await context.bot.send_message(
        chat_id=CHANNEL_ID,
        text=f"دعاء من {user.first_name}:\n\n{text}",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    
    conn = get_db()
    c = conn.cursor()
    c.execute("INSERT INTO prayers (user_id, text, message_id, created_at, username, first_name) VALUES (%s, %s, %s, %s, %s, %s)",
              (user.id, text, sent.message_id, update.message.date.isoformat(), user.username, user.first_name))
    conn.commit()
    
    c.execute("SELECT id FROM prayers WHERE message_id = %s", (sent.message_id,))
    prayer_id = c.fetchone()[0]
    conn.close()
    
    keyboard = [[InlineKeyboardButton("آمين 🤲", callback_data=f"ameen_{prayer_id}")]]
    await context.bot.edit_message_reply_markup(chat_id=CHANNEL_ID, message_id=sent.message_id, reply_markup=InlineKeyboardMarkup(keyboard))
    
    await update.message.reply_text("تم نشر دعاءك ✅")

async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    prayer_id = int(query.data.split("_")[1])
    
    conn = get_db()
    c = conn.cursor()
    c.execute("UPDATE prayers SET ameen_count = ameen_count + 1 WHERE id = %s RETURNING ameen_count", (prayer_id,))
    count = c.fetchone()[0]
    conn.commit()
    conn.close()
    
    keyboard = [[InlineKeyboardButton(f"آمين 🤲 {count}", callback_data=f"ameen_{prayer_id}")]]
    await query.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup(keyboard))
    await query.answer("آمين يا رب 🤲")

def main():
    init_db()
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_prayer))
    app.add_handler(CallbackQueryHandler(button))
    app.run_polling()

if __name__ == "__main__":
    main()
