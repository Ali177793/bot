import logging
import sqlite3
import asyncio
import os
from datetime import datetime, timedelta, time
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, LabeledPrice
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes, PreCheckoutQueryHandler
from dotenv import load_dotenv

load_dotenv()

# ===== ياخذها من متغيرات البيئة =====
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHANNEL_ID = int(os.getenv("CHANNEL_ID"))
ADMIN_ID = int(os.getenv("ADMIN_ID"))
BOT_USERNAME = os.getenv("BOT_USERNAME") # بدون @
# ====================================

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

def init_db():
    conn = sqlite3.connect('doaa_bot.db')
    c = conn.cursor()

    c.execute('''CREATE TABLE IF NOT EXISTS prayers
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  user_id INTEGER,
                  text TEXT,
                  message_id INTEGER,
                  ameen_count INTEGER DEFAULT 0,
                  created_at TEXT,
                  is_pinned INTEGER DEFAULT 0)''')

    c.execute('''CREATE TABLE IF NOT EXISTS ameen_users
                 (prayer_id INTEGER, user_id INTEGER, username TEXT,
                  UNIQUE(prayer_id, user_id))''')

    c.execute('''CREATE TABLE IF NOT EXISTS users
                 (user_id INTEGER PRIMARY KEY, username TEXT, first_name TEXT)''')

    # Migration لجدول users
    c.execute("PRAGMA table_info(users)")
    users_cols = [col[1] for col in c.fetchall()]
    if 'last_seen' not in users_cols:
        c.execute("ALTER TABLE users ADD COLUMN last_seen TEXT")
        logger.info("تمت إضافة عمود last_seen لجدول users")

    # Migration لجدول prayers
    c.execute("PRAGMA table_info(prayers)")
    prayers_cols = [col[1] for col in c.fetchall()]
    if 'username' not in prayers_cols:
        c.execute("ALTER TABLE prayers ADD COLUMN username TEXT")
        logger.info("تمت إضافة عمود username لجدول prayers")
    if 'first_name' not in prayers_cols:
        c.execute("ALTER TABLE prayers ADD COLUMN first_name TEXT")
        logger.info("تمت إضافة عمود first_name لجدول prayers")

    # Migration لجدول ameen_users
    c.execute("PRAGMA table_info(ameen_users)")
    ameen_cols = [col[1] for col in c.fetchall()]
    if 'first_name' not in ameen_cols:
        c.execute("ALTER TABLE ameen_users ADD COLUMN first_name TEXT")
        logger.info("تمت إضافة عمود first_name لجدول ameen_users")

    conn.commit()
    conn.close()

def add_user(user_id, username, first_name):
    conn = sqlite3.connect('doaa_bot.db')
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO users (user_id, username, first_name, last_seen) VALUES (?,?,?,?)",
              (user_id, username, first_name, datetime.now().isoformat()))
    conn.commit()
    conn.close()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user
    add_user(user.id, user.username, user.first_name)
    text = """
أهلا بيك في بوت أمّنولي 🤲

هنا تطلب دعاء والآلاف يأمنولك.

/doaa - أضف دعاء جديد
/doaa @صديقك - ادعي لصديقك ويوصله إشعار
/surprise - دعاء مفاجئ الك
/myprayers - شوف دعواتك

ميزات مدفوعة بـ ⭐ نجوم تليجرام:
📌 تثبيت 24س = 5⭐
👥 معرفة منو أمّن = 2⭐

قال ﷺ: "دعوة المسلم لأخيه بظهر الغيب مستجابة"
    """
    await update.message.reply_text(text)

async def doaa_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if args and args[0].startswith('@'):
        context.user_data['friend'] = args[0]
        await update.message.reply_text(f"اكتب دعاء لـ {args[0]} 🤲\nراح يوصله إشعار من تخلص")
    else:
        context.user_data['friend'] = None
        await update.message.reply_text("اكتب دعائك الآن 🤲\n\nمثال: اللهم اشفِ أمي\n\nأو استخدم: /doaa @يوزر_صديقك")
    context.user_data['waiting_for_doaa'] = True

async def handle_doaa_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get('waiting_for_doaa'):
        return

    user = update.message.from_user
    doaa_text = update.message.text
    add_user(user.id, user.username, user.first_name)

    if len(doaa_text.split()) < 3:
        await update.message.reply_text("الدعاء قصير كلش، اكتب جملة كاملة 🤍")
        return

    banned = ['موت', 'شر', 'لعنة', 'انتقم', 'دمر']
    if any(word in doaa_text for word in banned):
        await update.message.reply_text("عذراً، فقط الدعاء بالخير مسموح 🤍")
        context.user_data['waiting_for_doaa'] = False
        return

    conn = sqlite3.connect('doaa_bot.db')
    c = conn.cursor()
    try:
        c.execute("SELECT created_at FROM prayers WHERE user_id=? ORDER BY id DESC LIMIT 1", (user.id,))
        last = c.fetchone()
        if last:
            last_time = datetime.fromisoformat(last[0])
            if (datetime.now() - last_time).total_seconds() < 300:
                await update.message.reply_text("اصبر 5 دقايق بين كل دعاء ودعاء 🤍")
                context.user_data['waiting_for_doaa'] = False
                return

        friend = context.user_data.get('friend')
        c.execute("INSERT INTO prayers (user_id, username, first_name, text, created_at) VALUES (?,?,?,?,?)",
                  (user.id, user.username, user.first_name, doaa_text, datetime.now().isoformat()))
        prayer_id = c.lastrowid
        conn.commit()

        keyboard = [
            [InlineKeyboardButton(f"آمين يارب 🤲 0", callback_data=f"ameen_{prayer_id}")],
            [InlineKeyboardButton("📌 تثبيت 24س - 5⭐", callback_data=f"buy_pin_{prayer_id}")],
            [InlineKeyboardButton("👥 منو أمّن - 2⭐", callback_data=f"buy_who_{prayer_id}")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        if friend:
            channel_text = f"""
يا رب 🤲

صديقكم {user.first_name} يدعو لـ {friend}:
"{doaa_text}"

قولوا "آمين" بقلبكم، يمكن تكون ساعة استجابة ✨
دعاء رقم #{prayer_id}
"""
        else:
            channel_text = f"""
يا رب 🤲

واحد من اخوانكم محتاج دعائكم:
"{doaa_text}"

قولوا "آمين" بقلبكم، يمكن تكون ساعة استجابة ✨
دعاء رقم #{prayer_id}
"""

        try:
            msg = await context.bot.send_message(chat_id=CHANNEL_ID, text=channel_text, reply_markup=reply_markup)
            c.execute("UPDATE prayers SET message_id =? WHERE id =?", (msg.message_id, prayer_id))
            conn.commit()
            await update.message.reply_text(f"تم نشر دعائك رقم #{prayer_id} ✅")
        except Exception as e:
            await update.message.reply_text(f"خطأ: تأكد البوت أدمن بالقناة\n{e}")

    finally:
        conn.close()
        context.user_data['waiting_for_doaa'] = False

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    user = query.from_user
    add_user(user.id, user.username, user.first_name)
    await query.answer()

    if data.startswith("ameen_"):
        prayer_id = int(data.split("_")[1])
        conn = sqlite3.connect('doaa_bot.db')
        c = conn.cursor()

        try:
            c.execute("SELECT 1 FROM ameen_users WHERE prayer_id=? AND user_id=?", (prayer_id, user.id))
            if c.fetchone():
                await query.answer("إنت مأمّن قبل 💚", show_alert=True)
                return

            c.execute("INSERT INTO ameen_users (prayer_id, user_id, username, first_name) VALUES (?,?,?,?)",
                      (prayer_id, user.id, user.username, user.first_name))
            c.execute("UPDATE prayers SET ameen_count = ameen_count + 1 WHERE id=?", (prayer_id,))
            c.execute("SELECT ameen_count, user_id, text FROM prayers WHERE id=?", (prayer_id,))
            ameen_count, owner_id, doaa_text = c.fetchone()
            conn.commit()

            new_keyboard = [
                [InlineKeyboardButton(f"آمين يارب 🤲 {ameen_count}", callback_data=f"ameen_{prayer_id}")],
                [InlineKeyboardButton("📌 تثبيت 24س - 5⭐", callback_data=f"buy_pin_{prayer_id}")],
                [InlineKeyboardButton("👥 منو أمّن - 2⭐", callback_data=f"buy_who_{prayer_id}")]
            ]
            await query.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup(new_keyboard))

            if owner_id!= user.id:
                try:
                    await context.bot.send_message(owner_id, f"🎉 شخص جديد أمّن على دعائك رقم #{prayer_id}\n\n\"{doaa_text[:50]}...\"\n\nصاروا {ameen_count} 🤲")
                except:
                    pass
        finally:
            conn.close()

    elif data.startswith("buy_pin_"):
        prayer_id = int(data.split("_")[2])
        await context.bot.send_invoice(
            query.from_user.id, "تثبيت دعاء 24 ساعة",
            f"دعائك رقم #{prayer_id} يبقى أول القناة لمدة 24 ساعة",
            f"pin_{prayer_id}", provider_token="", currency="XTR",
            prices=[LabeledPrice("تثبيت", 5)]
        )

    elif data.startswith("buy_who_"):
        prayer_id = int(data.split("_")[2])
        await context.bot.send_invoice(
            query.from_user.id, "كشف منو أمّن",
            f"تشوف آخر 20 شخص أمّنوا على دعائك #{prayer_id}",
            f"who_{prayer_id}", provider_token="", currency="XTR",
            prices=[LabeledPrice("كشف", 2)]
        )

async def precheckout_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.pre_checkout_query
    await query.answer(ok=True)

async def unpin_later(context: ContextTypes.DEFAULT_TYPE):
    job = context.job
    msg_id = job.data
    try:
        await context.bot.unpin_chat_message(chat_id=CHANNEL_ID, message_id=msg_id)
    except Exception as e:
        logger.error(f"Unpin error: {e}")

async def successful_payment_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    payment = update.message.successful_payment
    payload = payment.invoice_payload

    if payload.startswith("pin_"):
        prayer_id = int(payload.split("_")[1])
        conn = sqlite3.connect('doaa_bot.db')
        c = conn.cursor()
        c.execute("UPDATE prayers SET is_pinned=1 WHERE id=?", (prayer_id,))
        c.execute("SELECT message_id FROM prayers WHERE id=?", (prayer_id,))
        result = c.fetchone()
        conn.close()

        if result and result[0]:
            msg_id = result[0]
            await update.message.reply_text(f"✅ تم الدفع 5⭐ بنجاح!\n\nدعائك #{prayer_id} تثبت 24 ساعة 🔥")
            try:
                await context.bot.pin_chat_message(chat_id=CHANNEL_ID, message_id=msg_id, disable_notification=True)
                context.job_queue.run_once(unpin_later, 86400, data=msg_id)
            except Exception as e:
                logger.error(f"Pin error: {e}")
        else:
            await update.message.reply_text("تم الدفع بس صار خطأ بالتثبيت. راسل الأدمن")

    elif payload.startswith("who_"):
        prayer_id = int(payload.split("_")[1])
        conn = sqlite3.connect('doaa_bot.db')
        c = conn.cursor()
        c.execute("SELECT username, first_name FROM ameen_users WHERE prayer_id=? ORDER BY ROWID DESC LIMIT 20", (prayer_id,))
        users = c.fetchall()
        conn.close()

        if users:
            text = f"👥 آخر من أمّن على دعائك #{prayer_id}:\n\n"
            for u in users:
                name = f"@{u[0]}" if u[0] else u[1]
                text += f"• {name}\n"
            text += f"\n💎 تم الدفع 2⭐"
        else:
            text = "ما أحد أمّن بعد 😢"

        await update.message.reply_text(text)

async def surprise(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn = sqlite3.connect('doaa_bot.db')
    c = conn.cursor()
    c.execute("SELECT text, ameen_count, id FROM prayers WHERE ameen_count > 5 ORDER BY RANDOM() LIMIT 1")
    doaa = c.fetchone()
    conn.close()
    if doaa:
        await update.message.reply_text(f'دعاء اليوم الك 🤍:\n\n"{doaa[0]}"\n\n{doaa[1]} شخص أمّنوا عليه قبلك\n\nجرب حظك: /doaa')
    else:
        await update.message.reply_text("بعد ما صار عدنا دعاء مشهور. اكتب /doaa وخلي دعائك يكون هو المفاجأة باجر 🤲")

async def myprayers(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    conn = sqlite3.connect('doaa_bot.db')
    c = conn.cursor()
    c.execute("SELECT id, text, ameen_count FROM prayers WHERE user_id=? ORDER BY id DESC LIMIT 5", (user_id,))
    prayers = c.fetchall()
    conn.close()

    if not prayers:
        await update.message.reply_text("ما عندك دعوات. دز /doaa وضيف أول دعاء 🤲")
        return

    text = "📿 آخر دعواتك:\n\n"
    for pid, ptext, count in prayers:
        text += f"#{pid}: {ptext[:35]}...\n🔥 آمين: {count} 🤲\n\n"
    await update.message.reply_text(text)

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.from_user.id!= ADMIN_ID:
        return
    conn = sqlite3.connect('doaa_bot.db')
    c = conn.cursor()
    total_prayers = c.execute("SELECT COUNT(*) FROM prayers").fetchone()[0]
    total_ameen = c.execute("SELECT SUM(ameen_count) FROM prayers").fetchone()[0] or 0
    total_users = c.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    conn.close()
    await update.message.reply_text(f"📊 الإحصائيات:\n\nدعوات: {total_prayers}\nتأمينات: {total_ameen}\nمستخدمين: {total_users}")

async def weekly_top(context: ContextTypes.DEFAULT_TYPE):
    conn = sqlite3.connect('doaa_bot.db')
    c = conn.cursor()
    week_ago = (datetime.now() - timedelta(days=7)).isoformat()
    c.execute("""SELECT id, text, ameen_count FROM prayers
                 WHERE created_at >? ORDER BY ameen_count DESC LIMIT 1""", (week_ago,))
    top = c.fetchone()
    conn.close()

    if top:
        pid, text, count = top
        msg = f"🔥 دعاء الأسبوع 🔥\n\n\"{text}\"\n\n{count} شخص أمّنوا عليه بظهر الغيب 🤲\nانشر الخير وضيف دعائك: @{BOT_USERNAME}"
        try:
            await context.bot.send_message(chat_id=CHANNEL_ID, text=msg)
        except Exception as e:
            logger.error(f"Weekly top error: {e}")

async def fajr_reminder(context: ContextTypes.DEFAULT_TYPE):
    conn = sqlite3.connect('doaa_bot.db')
    c = conn.cursor()
    c.execute("SELECT user_id FROM users")
    users = c.fetchall()
    conn.close()
    for u in users:
        try:
            await context.bot.send_message(u[0], "وقت استجابة 🤲\nاكتب /doaa وخل الناس تأمّن لك قبل لا يبدي يومك")
            await asyncio.sleep(0.1)
        except:
            pass

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Update {update} caused error {context.error}")

def main():
    init_db()
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_error_handler(error_handler)
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("doaa", doaa_command))
    app.add_handler(CommandHandler("myprayers", myprayers))
    app.add_handler(CommandHandler("surprise", surprise))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_doaa_text))
    app.add_handler(CallbackQueryHandler(button_callback))
    app.add_handler(PreCheckoutQueryHandler(precheckout_callback))
    app.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment_callback))

    # كل يوم جمعة الساعة 6 العصر
    app.job_queue.run_daily(weekly_top, time=time(hour=18, minute=0), days=(4,))
    # كل يوم الفجر الساعة 5
    app.job_queue.run_daily(fajr_reminder, time=time(hour=5, minute=0))

    print("بوت أمّنولي شغال...")
    app.run_polling()

if __name__ == '__main__':
    main()
