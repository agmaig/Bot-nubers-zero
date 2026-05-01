# DEV: @i_mmx
import telebot
from telebot import types
import sqlite3
import requests
import json
import time
import threading
import re
import random
import logging
from datetime import datetime

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════
#            إعدادات البوت
# ═══════════════════════════════════════════
BOT_TOKEN      = "8754895179:AAEiB-XZrrY7c1rWIwOvVAr4ugrv0xXkW9Y"
ADMIN_IDS      = [7747270285]
LOG_CHANNEL_ID = -1003971972615

ROXY_BASE    = "http://roxysms.net"
ROXY_USER    = "OMARSYOMAR"
ROXY_PASS    = "Ameen@1991$$"
ROXY_LOGIN   = ROXY_BASE + "/signin"
ROXY_NUMBERS = ROXY_BASE + "/agent/res/data_smsnumbers.php"
ROXY_CDR     = ROXY_BASE + "/agent/res/data_smscdr.php"

DB_NAME = "ultra_roxy.db"

COUNTRY_MAP = {
    "1":"🇺🇸","7":"🇷🇺","20":"🇪🇬","44":"🇬🇧","33":"🇫🇷","49":"🇩🇪",
    "90":"🇹🇷","91":"🇮🇳","966":"🇸🇦","971":"🇦🇪","964":"🇮🇶","965":"🇰🇼",
    "212":"🇲🇦","213":"🇩🇿","962":"🇯🇴","963":"🇸🇾","967":"🇾🇪","970":"🇵🇸",
    "62":"🇮🇩","55":"🇧🇷","60":"🇲🇾","84":"🇻🇳","86":"🇨🇳","34":"🇪🇸",
    "380":"🇺🇦","48":"🇵🇱","31":"🇳🇱","39":"🇮🇹","63":"🇵🇭","66":"🇹🇭",
    "880":"🇧🇩","27":"🇿🇦","234":"🇳🇬","216":"🇹🇳","218":"🇱🇾","249":"🇸🇩",
    "961":"🇱🇧","968":"🇴🇲","973":"🇧🇭","974":"🇶🇦","81":"🇯🇵","82":"🇰🇷",
    "65":"🇸🇬","61":"🇦🇺","52":"🇲🇽","54":"🇦🇷","98":"🇮🇷","92":"🇵🇰",
}

# ═══════════════════════════════════════════
#           روكسي
# ═══════════════════════════════════════════
roxy_session   = requests.Session()
roxy_logged_in = False

def roxy_login():
    global roxy_logged_in
    try:
        h = {"User-Agent":"Mozilla/5.0","Referer":ROXY_LOGIN}
        r = roxy_session.get(ROXY_LOGIN, headers=h, timeout=10)
        d = {"username":ROXY_USER,"password":ROXY_PASS}
        m = re.search(r'What is (\d+)\s*([+\-])\s*(\d+)', r.text)
        if m:
            n1,op,n2 = int(m.group(1)),m.group(2),int(m.group(3))
            d["capt"] = str(n1+n2 if op=="+" else n1-n2)
        roxy_session.post(ROXY_LOGIN, data=d, headers=h, timeout=10)
        roxy_logged_in = True
        return True
    except Exception as e:
        logger.error(f"roxy_login: {e}"); return False

def roxy_h(ref):
    return {"User-Agent":"Mozilla/5.0","Referer":ref,"X-Requested-With":"XMLHttpRequest"}

def fetch_roxy_numbers():
    if not roxy_logged_in: roxy_login()
    try:
        res = roxy_session.get(ROXY_NUMBERS,
            headers=roxy_h(ROXY_BASE+"/agent/MySMSNumbers"),
            params={"frange":"","fclient":"","iDisplayStart":0,"iDisplayLength":5000,"sEcho":1},
            timeout=15)
        return [r[2] for r in res.json().get("aaData",[]) if len(r)>2]
    except Exception as e:
        logger.error(f"fetch_numbers: {e}"); return []

def fetch_roxy_msgs(date_from=None, date_to=None):
    if not roxy_logged_in: roxy_login()
    try:
        now = datetime.now()
        p = {
            "fdate1": date_from or now.strftime("%Y-%m-%d 00:00:00"),
            "fdate2": date_to   or now.strftime("%Y-%m-%d 23:59:59"),
            "frange":"","fclient":"","fnum":"","fcli":"",
            "fgdate":"","fgmonth":"","fgrange":"","fgclient":"",
            "fgnumber":"","fgcli":"","fg":"0",
            "iDisplayStart":0,"iDisplayLength":1000,"sEcho":1
        }
        res = roxy_session.get(ROXY_CDR,
            headers=roxy_h(ROXY_BASE+"/agent/SMSCDRReports"),
            params=p, timeout=15)
        d = res.json()
        return d.get("aaData",[]), d.get("iTotalRecords","0")
    except Exception as e:
        logger.error(f"fetch_msgs: {e}"); return [],0

# ═══════════════════════════════════════════
#           قاعدة البيانات
# ═══════════════════════════════════════════
bot = telebot.TeleBot(BOT_TOKEN, parse_mode="HTML")

def get_db():
    return sqlite3.connect(DB_NAME, check_same_thread=False)

def init_db():
    with get_db() as c:
        c.execute('''CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY, username TEXT,
            join_date TEXT, last_msg_id INTEGER, has_image INTEGER DEFAULT 0,
            total_codes INTEGER DEFAULT 0, balance REAL DEFAULT 0.0)''')
        c.execute('''CREATE TABLE IF NOT EXISTS apps (
            id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE)''')
        c.execute('''CREATE TABLE IF NOT EXISTS combos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            service TEXT, country_code TEXT, numbers TEXT,
            UNIQUE(service,country_code))''')
        c.execute('''CREATE TABLE IF NOT EXISTS sessions (
            user_id INTEGER PRIMARY KEY, phone TEXT, service TEXT,
            chat_id INTEGER, message_id INTEGER, start_time INTEGER)''')
        c.execute('''CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)''')
        c.execute('''CREATE TABLE IF NOT EXISTS history (msg_hash TEXT PRIMARY KEY, created_at TEXT)''')
        c.execute('''CREATE TABLE IF NOT EXISTS pending_inputs (
            user_id INTEGER PRIMARY KEY, action TEXT, data TEXT)''')
        c.execute('''CREATE TABLE IF NOT EXISTS blocked_numbers (
            number TEXT PRIMARY KEY, blocked_at TEXT)''')
        # migration - إضافة أعمدة جديدة إذا ما كانت موجودة
        try: c.execute("ALTER TABLE users ADD COLUMN total_codes INTEGER DEFAULT 0")
        except: pass
        try: c.execute("ALTER TABLE history ADD COLUMN created_at TEXT")
        except: pass
        try: c.execute("ALTER TABLE blocked_numbers ADD COLUMN blocked_at TEXT")
        except: pass
        try: c.execute("ALTER TABLE users ADD COLUMN balance REAL DEFAULT 0.0")
        except: pass

        if not c.execute("SELECT * FROM apps").fetchone():
            c.executemany("INSERT OR IGNORE INTO apps(name) VALUES(?)",
                [("WhatsApp",),("Telegram",),("TikTok",),("Instagram",),
                 ("Facebook",),("Google",),("Snapchat",),("Twitter",),
                 ("Discord",),("Binance",),("PayPal",),("Netflix",)])

def gs(key, default=""):
    with get_db() as c:
        r = c.execute("SELECT value FROM settings WHERE key=?",(key,)).fetchone()
        return r[0] if r else default

def ss(key, val):
    with get_db() as c:
        c.execute("INSERT OR REPLACE INTO settings(key,value) VALUES(?,?)",(key,val))

def get_img():
    v = gs("bot_image"); return v if v else None

def set_pending(uid, action, data=""):
    with get_db() as c:
        c.execute("INSERT OR REPLACE INTO pending_inputs(user_id,action,data) VALUES(?,?,?)",(uid,action,data))

def extract_code(text):
    m = re.search(r'\b(\d{4,8})\b', text)
    if m: return m.group(1)
    m = re.search(r'(\d[\d\s\-]{3,10}\d)', text)
    if m: return re.sub(r'[\s\-]','',m.group(1))
    return None

def get_flag(phone):
    for k in sorted(COUNTRY_MAP.keys(), key=len, reverse=True):
        if phone.startswith(k): return COUNTRY_MAP[k]
    return "🌍"

def send_chunks(cid, header, lines, max_len=4000):
    chunk = header
    for line in lines:
        entry = line+"\n"
        if len(chunk)+len(entry) > max_len:
            bot.send_message(cid, chunk); chunk = entry
        else:
            chunk += entry
    if chunk.strip(): bot.send_message(cid, chunk)

def btn(text, cb, color=None):
    return types.InlineKeyboardButton(text, callback_data=cb)

def back(cb="home"):
    return types.InlineKeyboardButton("🔙 رجوع", callback_data=cb)

CHANNEL_USERNAME = "@ZEROOTP1OTP"

def is_subscribed(uid):
    try:
        m = bot.get_chat_member(CHANNEL_USERNAME, uid)
        return m.status in ["member","administrator","creator"]
    except:
        return False

def check_sub(cid, uid):
    if uid in ADMIN_IDS:
        return True
    if not is_subscribed(uid):
        mk = types.InlineKeyboardMarkup()
        channel_url = "https://t.me/" + CHANNEL_USERNAME.lstrip("@")
        mk.add(types.InlineKeyboardButton("📢 اشترك في القناة", url=channel_url))
        mk.add(btn("✅ تحققت من الاشتراك", "check_sub"))
        sub_text = "⚠️ <b>يجب الاشتراك في القناة!</b>\n\n📢 " + CHANNEL_USERNAME + "\n\nاشترك ثم اضغط الزر بالأسفل"
        try:
            bot.send_message(cid, sub_text, reply_markup=mk)
        except:
            pass
        return False
    return True
# ═══════════════════════════════════════════
#         smart_edit
# ═══════════════════════════════════════════
def smart_edit(cid, uid, text, mk=None):
    with get_db() as c:
        u = c.execute("SELECT last_msg_id,has_image FROM users WHERE user_id=?",(uid,)).fetchone()
    mid     = u[0] if u else None
    has_img = bool(u[1]) if u else False
    bot_img = get_img()

    if mid:
        try:
            if bot_img:
                if not has_img:
                    bot.delete_message(cid, mid)
                    raise Exception("switch")
                bot.edit_message_caption(caption=text, chat_id=cid, message_id=mid, reply_markup=mk)
            else:
                if has_img:
                    bot.delete_message(cid, mid)
                    raise Exception("switch")
                bot.edit_message_text(text, cid, mid, reply_markup=mk)
            return
        except Exception as e:
            logger.info(f"edit failed: {e}")

    try:
        if bot_img:
            sent = bot.send_photo(cid, bot_img, caption=text, reply_markup=mk)
            with get_db() as c:
                c.execute("UPDATE users SET last_msg_id=?,has_image=1 WHERE user_id=?",(sent.message_id,uid))
        else:
            sent = bot.send_message(cid, text, reply_markup=mk)
            with get_db() as c:
                c.execute("UPDATE users SET last_msg_id=?,has_image=0 WHERE user_id=?",(sent.message_id,uid))
    except Exception as e:
        logger.error(f"smart_edit failed: {e}")

# ═══════════════════════════════════════════
#         مراقبة الرسائل تلقائياً
# ═══════════════════════════════════════════
def monitor_loop():
    roxy_login()
    while True:
        try:
            rows, _ = fetch_roxy_msgs()
            with get_db() as c:
                sessions = c.execute("SELECT user_id,phone,chat_id,message_id,service FROM sessions").fetchall()
                sess_map = {re.sub(r'\D','',r[1]):r for r in sessions}
                blocked  = {r[0] for r in c.execute("SELECT number FROM blocked_numbers").fetchall()}
                for row in rows:
                    if len(row) < 5: continue
                    phone = re.sub(r'\D','',str(row[2]))
                    text  = re.sub(r'<[^>]+>','',str(row[4])).strip()
                    dt    = str(row[0])
                    if not phone or not text or phone in blocked: continue
                    h = f"{phone}_{hash(text)}_{dt}"
                    if c.execute("SELECT 1 FROM history WHERE msg_hash=?",(h,)).fetchone(): continue
                    c.execute("INSERT INTO history(msg_hash,created_at) VALUES(?,?)",(h,dt))
                    if phone not in sess_map: continue
                    uid,raw_phone,cid,mid,svc = sess_map[phone]
                    code = extract_code(text)
                    flag = get_flag(phone)
                    code_line = f"🔐 <b>الكود:</b> <code>{code}</code>\n" if code else "⚠️ <b>لم يُعثر على كود رقمي</b>\n"
                    msg_text = (
                        f"╔══════════════════╗\n║  🎉 وصلت رسالة!  ║\n╚══════════════════╝\n\n"
                        f"{code_line}"
                        f"📱 <b>الرقم:</b> <code>+{raw_phone}</code>\n"
                        f"🌍 <b>الدولة:</b> {flag}\n"
                        f"⚙️ <b>الخدمة:</b> {svc}\n"
                        f"💬 <b>الرسالة:</b>\n<i>{text}</i>"
                    )
                    mk2 = types.InlineKeyboardMarkup()
                    if code: mk2.add(btn(f"📋 نسخ الكود: {code}","none"))
                    mk2.add(btn("🏠 الرئيسية","home"))
                    try:
                        if get_img():
                            bot.edit_message_caption(caption=msg_text,chat_id=cid,message_id=mid,reply_markup=mk2)
                        else:
                            bot.edit_message_text(msg_text,cid,mid,reply_markup=mk2)
                    except:
                        bot.send_message(uid,msg_text,reply_markup=mk2)
                    try:
                        masked = raw_phone[:5] + "*" * (len(raw_phone)-5)
                        mk_log = types.InlineKeyboardMarkup()
                        mk_log.add(types.InlineKeyboardButton("🤖 احصل على كودك", url="https://t.me/ZERO_OTP1_BOT"))
                        bot.send_message(LOG_CHANNEL_ID,
                            f"🔥 <b>كود جديد!</b>\n"
                            f"┌──────────────────\n"
                            f"│ 🛠 <b>الخدمة:</b> {svc}\n"
                            f"│ 🌍 <b>الدولة:</b> {flag}\n"
                            f"│ 📱 <b>الرقم:</b> <code>+{masked}</code>\n"
                            f"│ 🔐 <b>الكود:</b> <code>{code}</code>\n"
                            f"│ 💬 <b>الرسالة:</b> {text}\n"
                            f"└──────────────────\n"
                            f"#كود_جديد #{svc}",
                            reply_markup=mk_log)
                    except: pass
                    c.execute("UPDATE users SET total_codes=total_codes+1, balance=balance+0.001 WHERE user_id=?",(uid,))
                    c.execute("DELETE FROM sessions WHERE user_id=?",(uid,))
            time.sleep(5)
        except Exception as e:
            logger.error(f"monitor_loop: {e}"); time.sleep(15)

# ═══════════════════════════════════════════
#           أوامر الأدمن السريعة
# ═══════════════════════════════════════════
@bot.message_handler(commands=['mynum'])
def cmd_mynum(msg):
    if msg.from_user.id not in ADMIN_IDS: return
    bot.reply_to(msg,"⏳ جاري جلب أرقامك من روكسي...")
    numbers = fetch_roxy_numbers()
    if not numbers: bot.reply_to(msg,"⚠️ لا توجد أرقام."); return
    send_chunks(msg.chat.id,f"📱 <b>أرقامك على روكسي ({len(numbers)}):</b>\n\n",
                [f"<code>{n}</code>" for n in numbers])

@bot.message_handler(commands=['mymsgs'])
def cmd_mymsgs(msg):
    if msg.from_user.id not in ADMIN_IDS: return
    bot.reply_to(msg,"⏳ جاري جلب رسائل اليوم...")
    rows,total = fetch_roxy_msgs()
    data_rows = [r for r in rows if len(r)>=5] if rows else []
    if not data_rows: bot.reply_to(msg,"📭 لا توجد رسائل اليوم."); return
    lines = []
    for i,row in enumerate(data_rows,1):
        to   = re.sub(r'<[^>]+>','',str(row[2])).strip()
        cli  = re.sub(r'<[^>]+>','',str(row[3])).strip()
        txt  = re.sub(r'<[^>]+>','',str(row[4])).strip()
        flag = get_flag(re.sub(r'\D','',to))
        code = extract_code(txt)
        line = f"📩 <b>#{i}</b> {flag} <code>{to}</code> | {cli}\n💬 <i>{txt}</i>"
        if code: line += f"\n🔐 <b>{code}</b>"
        lines.append(line)
    send_chunks(msg.chat.id,f"📨 <b>رسائل اليوم ({total}):</b>\n\n",lines)

@bot.message_handler(commands=['stats'])
def cmd_stats(msg):
    if msg.from_user.id not in ADMIN_IDS: return
    with get_db() as c:
        u = c.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        a = c.execute("SELECT COUNT(*) FROM apps").fetchone()[0]
        s = c.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
        h = c.execute("SELECT COUNT(*) FROM history").fetchone()[0]
        bl= c.execute("SELECT COUNT(*) FROM blocked_numbers").fetchone()[0]
    bot.reply_to(msg,
        f"📊 <b>إحصائيات البوت</b>\n\n"
        f"👥 المستخدمون: <b>{u}</b>\n"
        f"📱 التطبيقات: <b>{a}</b>\n"
        f"⏳ جلسات نشطة: <b>{s}</b>\n"
        f"📨 رسائل معالجة: <b>{h}</b>\n"
        f"🚫 أرقام محظورة: <b>{bl}</b>\n"
        f"🕐 {datetime.now().strftime('%H:%M — %d/%m/%Y')}")

# ═══════════════════════════════════════════
#           /start
# ═══════════════════════════════════════════
@bot.message_handler(commands=['start'])
def start(msg):
    uid = msg.from_user.id
    logger.info(f"▶️ /start uid={uid}")
    with get_db() as c:
        c.execute("INSERT OR IGNORE INTO users(user_id,username,join_date) VALUES(?,?,?)",
                  (uid,msg.from_user.username,datetime.now().strftime('%Y-%m-%d')))
    if not check_sub(msg.chat.id, uid):
        return
    show_home(msg.chat.id, uid)

def show_home(cid, uid):
    try: name = bot.get_chat(uid).first_name or ""
    except: name = ""
    with get_db() as c:
        u_row = c.execute("SELECT total_codes, balance FROM users WHERE user_id=?",(uid,)).fetchone()
        total_users = c.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        active_sess = c.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
    my_codes   = u_row[0] if u_row else 0
    my_balance = round(u_row[1], 3) if u_row else 0.0
    text = (
        f"👋 <b>أهلاً {name}!</b>\n\n"
        f"┌─────────────────────┐\n"
        f"│   🚀 بوت أرقام روكسي  │\n"
        f"└─────────────────────┘\n\n"
        f"⚡ تفعيل فوري لكافة التطبيقات\n"
        f"🌍 أرقام من جميع دول العالم\n"
        f"📨 استلام الكود تلقائياً\n\n"
        f"👥 <b>المستخدمون:</b> {total_users}  |  ⏳ <b>نشطون:</b> {active_sess}\n"
        f"🎯 <b>أكوادك:</b> {my_codes}  |  💰 <b>رصيدك:</b> ${my_balance}"
    )
    mk = types.InlineKeyboardMarkup(row_width=2)
    mk.add(btn("📱 شراء رقم","get_number"), btn("👤 حسابي","profile"))
    mk.add(btn("📊 إحصائيات","user_stats"), btn("ℹ️ مساعدة","help"))
    if uid in ADMIN_IDS:
        mk.add(btn("🛠 لوحة الأدمن","admin_panel"))
    smart_edit(cid, uid, text, mk)

def show_admin(cid, uid):
    with get_db() as c:
        u = c.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        s = c.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
        h = c.execute("SELECT COUNT(*) FROM history").fetchone()[0]
    text = (
        f"🛠 <b>لوحة التحكم</b>\n\n"
        f"👥 المستخدمون: <b>{u}</b>\n"
        f"⏳ جلسات نشطة: <b>{s}</b>\n"
        f"📨 رسائل معالجة: <b>{h}</b>\n"
        f"🕐 {datetime.now().strftime('%H:%M — %d/%m/%Y')}"
    )
    mk = types.InlineKeyboardMarkup(row_width=2)
    mk.add(btn("➕ إضافة تطبيق","add_app"),       btn("🗑 حذف تطبيق","adm_apps"))
    mk.add(btn("📦 رفع أرقام","adm_combos"),       btn("🗑 حذف الأرقام","del_all_combos"))
    mk.add(btn("📲 أرقام روكسي","adm_roxy_numbers"), btn("📨 رسائل روكسي","adm_roxy_msgs"))
    mk.add(btn("🖼️ تعيين صورة","adm_setimg"),      btn("❌ حذف صورة","adm_delimg"))
    mk.add(btn("📣 إرسال جماعي","adm_broadcast"),  btn("📊 إحصائيات","adm_stats"))
    mk.add(btn("🚫 حظر مستخدم","adm_ban"),         btn("✅ رفع الحظر","adm_unban"))
    mk.add(btn("🔢 حظر رقم","adm_block_num"),      btn("📋 الأرقام المحظورة","adm_blocked_list"))
    mk.add(btn("🧪 تجربة إرسال كود","adm_test_code"))
    mk.add(btn("👥 قائمة المستخدمين","adm_users"),  btn("🗑 مسح السجل","adm_clear_history"))
    mk.add(btn("💰 إدارة الأرصدة","adm_balances"))
    mk.add(back())
    smart_edit(cid, uid, text, mk)

# ═══════════════════════════════════════════
#           معالج الأزرار
# ═══════════════════════════════════════════
@bot.callback_query_handler(func=lambda c: True)
def cb(call):
    uid  = call.from_user.id
    cid  = call.message.chat.id
    data = call.data
    logger.info(f"📲 cb uid={uid} data={data}")
    try:
        _handle(call, uid, cid, data)
    except Exception as e:
        logger.error(f"callback error: {e}", exc_info=True)
        bot.answer_callback_query(call.id,"❌ حدث خطأ",show_alert=True)

def _handle(call, uid, cid, data):
    if gs(f"ban_{uid}") == "1" and data != "home":
        bot.answer_callback_query(call.id,"🚫 أنت محظور.",show_alert=True); return

    # ══ تحقق اشتراك (فقط زر التحقق) ══
    if data == "check_sub":
        if is_subscribed(uid):
            bot.answer_callback_query(call.id,"✅ شكراً! أنت مشترك الآن",show_alert=False)
            show_home(cid, uid)
        else:
            bot.answer_callback_query(call.id,"❌ لم تشترك بعد! اشترك أولاً ثم اضغط التحقق",show_alert=True)
        return

    # باقي الأزرار بدون شرط الاشتراك

    # ══ عام ══
    if data == "home":
        if not check_sub(cid, uid): return
        show_home(cid, uid)

    elif data == "help":
        text = (
            "ℹ️ <b>كيفية الاستخدام</b>\n\n"
            "1️⃣ اضغط 📱 <b>شراء رقم</b>\n"
            "2️⃣ اختر التطبيق المطلوب\n"
            "3️⃣ اختر الدولة\n"
            "4️⃣ استخدم الرقم في التطبيق\n"
            "5️⃣ الكود يصلك <b>تلقائياً</b> 🎉\n\n"
            "⚠️ <b>ملاحظات:</b>\n"
            "• إذا تأخر الكود اضغط 📩 <b>طلب يدوي</b>\n"
            "• كل رقم صالح لاستخدام واحد فقط\n"
            "• تواصل مع الدعم عند أي مشكلة\n\n"
            
        )
        mk = types.InlineKeyboardMarkup(); mk.add(back())
        smart_edit(cid, uid, text, mk)

    elif data == "user_stats":
        with get_db() as c:
            u = c.execute("SELECT COUNT(*) FROM users").fetchone()[0]
            a = c.execute("SELECT COUNT(*) FROM apps").fetchone()[0]
            s = c.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
            h = c.execute("SELECT COUNT(*) FROM history").fetchone()[0]
        text = (
            f"📊 <b>إحصائيات البوت</b>\n\n"
            f"┌─────────────────────┐\n"
            f"│ 👥 المستخدمون: {u}\n"
            f"│ 📱 التطبيقات: {a}\n"
            f"│ ⏳ جلسات نشطة: {s}\n"
            f"│ 📨 رسائل معالجة: {h}\n"
            f"└─────────────────────┘\n"
            f"🕐 {datetime.now().strftime('%H:%M — %d/%m/%Y')}"
        )
        mk = types.InlineKeyboardMarkup(); mk.add(back())
        smart_edit(cid, uid, text, mk)

    elif data == "profile":
        with get_db() as c:
            u    = c.execute("SELECT join_date,total_codes,balance FROM users WHERE user_id=?",(uid,)).fetchone()
            sess = c.execute("SELECT phone,service,start_time FROM sessions WHERE user_id=?",(uid,)).fetchone()
        join       = u[0] if u else "—"
        my_codes   = u[1] if u else 0
        my_balance = round(u[2], 3) if u else 0.0
        sl = ""
        if sess:
            elapsed = int(time.time()) - sess[2]
            sl = f"\n\n🔄 <b>جلسة نشطة:</b>\n⚙️ {sess[1]} — <code>+{sess[0]}</code>\n⏱ منذ {elapsed//60} دقيقة"
        can_withdraw = my_balance >= 5.0
        text = (
            f"👤 <b>ملفك الشخصي</b>\n\n"
            f"🆔 المعرف: <code>{uid}</code>\n"
            f"📅 الانضمام: {join}\n"
            f"🎯 الأكواد المستلمة: <b>{my_codes}</b>\n"
            f"💰 الرصيد: <b>${my_balance}</b>\n"
            f"📊 كل كود = <b>$0.001</b>\n"
            f"💵 أقل حد للسحب: <b>$5.00</b>\n"
            + (f"✅ <b>رصيدك كافٍ للسحب!</b>" if can_withdraw else f"⏳ تحتاج <b>{round(5.0-my_balance,3)}$</b> إضافية للسحب")
            + f"{sl}"
        )
        mk = types.InlineKeyboardMarkup()
        if can_withdraw:
            mk.add(btn("💸 طلب سحب الرصيد","withdraw_request"))
        if sess: mk.add(btn("❌ إلغاء الجلسة","cancel_session"))
        mk.add(back())
        smart_edit(cid, uid, text, mk)

    elif data == "cancel_session":
        with get_db() as c:
            c.execute("DELETE FROM sessions WHERE user_id=?",(uid,))
        bot.answer_callback_query(call.id,"✅ تم إلغاء الجلسة")
        show_home(cid, uid)

    elif data == "withdraw_request":
        with get_db() as c:
            u = c.execute("SELECT balance FROM users WHERE user_id=?",(uid,)).fetchone()
        balance = round(u[0],3) if u else 0
        if balance < 5.0:
            bot.answer_callback_query(call.id,f"❌ رصيدك ${balance} أقل من الحد الأدنى $5.00",show_alert=True)
            return
        smart_edit(cid,uid,
            f"💸 <b>طلب سحب الرصيد</b>\n\n"
            f"💰 رصيدك الحالي: <b>${balance}</b>\n\n"
            f"أرسل رقم محفظتك أو معلومات الدفع\n"
            f"(USDT TRC20 / PayPal / بنك محلي)",
            types.InlineKeyboardMarkup().add(btn("❌ إلغاء","cancel_input")))
        set_pending(uid,"withdraw_info")

    elif data == "get_number":
        with get_db() as c:
            apps = c.execute("SELECT id,name FROM apps").fetchall()
        mk = types.InlineKeyboardMarkup(row_width=3)
        for a in apps: mk.add(btn(a[1],f"app_{a[1]}"))
        mk.add(back())
        smart_edit(cid, uid, "📲 <b>اختر الخدمة:</b>", mk)

    elif data.startswith("app_"):
        app_name = data[4:]
        with get_db() as c:
            rows = c.execute("SELECT country_code,numbers FROM combos WHERE service=?",(app_name.upper(),)).fetchall()
        if not rows:
            bot.answer_callback_query(call.id,"🚫 لا توجد أرقام",show_alert=True); return
        mk = types.InlineKeyboardMarkup(row_width=3)
        for code,nj in rows:
            count = len(json.loads(nj))
            if count > 0:
                mk.add(btn(f"{COUNTRY_MAP.get(code,code)} ({count})",f"buy_{app_name}_{code}"))
        mk.add(back("get_number"))
        smart_edit(cid, uid, f"🌍 <b>اختر الدولة — {app_name}:</b>", mk)

    elif data.startswith("buy_"):
        parts = data.split("_",2); app_name=parts[1]; code=parts[2]
        with get_db() as c:
            row = c.execute("SELECT numbers FROM combos WHERE service=? AND country_code=?",(app_name.upper(),code)).fetchone()
            if not row: bot.answer_callback_query(call.id,"نفذت الكمية",show_alert=True); return
            numbers = json.loads(row[0])
            if not numbers: bot.answer_callback_query(call.id,"نفذت الكمية",show_alert=True); return
            phone = random.choice(numbers)
            flag  = COUNTRY_MAP.get(code,"🌍")
            text  = (
                f"✅ <b>تم حجز الرقم!</b>\n\n"
                f"📱 <b>الرقم:</b> <code>+{phone}</code>\n"
                f"🌍 <b>الدولة:</b> {flag}\n"
                f"⚙️ <b>الخدمة:</b> {app_name}\n\n"
                f"┌─────────────────────┐\n│   ⏳ بانتظار الكود...  │\n└─────────────────────┘\n\n"
                f"<i>سيصلك الكود تلقائياً 🔄</i>"
            )
            mk = types.InlineKeyboardMarkup()
            mk.add(btn("📩 طلب الكود يدوياً","check_code"))
            mk.add(btn("🔄 تغيير الرقم",data))
            mk.add(back("get_number"))
            smart_edit(cid, uid, text, mk)
            usr = c.execute("SELECT last_msg_id FROM users WHERE user_id=?",(uid,)).fetchone()
            c.execute("INSERT OR REPLACE INTO sessions(user_id,phone,service,chat_id,message_id,start_time) VALUES(?,?,?,?,?,?)",
                      (uid,phone,app_name,cid,usr[0] if usr else None,int(time.time())))

    elif data == "check_code":
        with get_db() as c:
            sess = c.execute("SELECT phone,service,chat_id,message_id FROM sessions WHERE user_id=?",(uid,)).fetchone()
        if not sess: bot.answer_callback_query(call.id,"❌ الجلسة منتهية",show_alert=True); return
        phone,service,chat_id,msg_id = sess
        clean = re.sub(r'\D','',phone)
        rows,_ = fetch_roxy_msgs()
        found = False
        for row in rows:
            if len(row)<5: continue
            if re.sub(r'\D','',str(row[2])) != clean: continue
            txt  = re.sub(r'<[^>]+>','',str(row[4])).strip()
            code = extract_code(txt)
            flag = get_flag(clean)
            code_line = f"🔐 <b>الكود:</b> <code>{code}</code>\n" if code else "⚠️ <b>لم يُعثر على كود</b>\n"
            final = (
                f"╔══════════════════╗\n║  🎉 وصلت رسالة!  ║\n╚══════════════════╝\n\n"
                f"{code_line}📱 <code>+{phone}</code>\n🌍 {flag}\n⚙️ {service}\n💬 <i>{txt}</i>"
            )
            mk2 = types.InlineKeyboardMarkup()
            if code: mk2.add(btn(f"📋 نسخ: {code}","none"))
            mk2.add(btn("🏠 الرئيسية","home"))
            try:
                if get_img(): bot.edit_message_caption(caption=final,chat_id=chat_id,message_id=msg_id,reply_markup=mk2)
                else: bot.edit_message_text(final,chat_id,msg_id,reply_markup=mk2)
            except: bot.send_message(uid,final,reply_markup=mk2)
            try:
                masked2 = phone[:5] + "*" * (len(phone)-5)
                mk_log2 = types.InlineKeyboardMarkup()
                mk_log2.add(types.InlineKeyboardButton("🤖 احصل على كودك", url="https://t.me/ZERO_OTP1_BOT"))
                bot.send_message(LOG_CHANNEL_ID,
                    f"🔥 <b>كود جديد!</b>\n┌──────────────────\n"
                    f"│ 🛠 {service} | {flag}\n│ 📱 <code>+{masked2}</code>\n"
                    f"│ 🔐 <code>{code}</code>\n│ 💬 {txt}\n└──────────────────\n#كود_جديد #{service}",
                    reply_markup=mk_log2)
            except: pass
            with get_db() as c:
                c.execute("UPDATE users SET total_codes=total_codes+1, balance=balance+0.001 WHERE user_id=?",(uid,))
                c.execute("DELETE FROM sessions WHERE user_id=?",(uid,))
            found = True; break
        if not found:
            bot.answer_callback_query(call.id,"⏳ لم يصل الكود بعد.",show_alert=True)

    # ══ أدمن ══
    elif data == "admin_panel" and uid in ADMIN_IDS:
        show_admin(cid, uid)

    elif data == "adm_test_code" and uid in ADMIN_IDS:
        # تجربة إرسال كود وهمي للقناة
        fake_services = ["WhatsApp","Telegram","Google","Instagram","TikTok"]
        fake_codes    = ["123456","234567","345678","456789","567890","678901"]
        fake_phones   = ["201552340002","966512345678","971501234567","962791234567","963912345678"]
        svc   = random.choice(fake_services)
        code  = random.choice(fake_codes)
        phone = random.choice(fake_phones)
        flag  = get_flag(phone)
        try:
            masked3 = phone[:5] + "*" * (len(phone)-5)
            mk_test = types.InlineKeyboardMarkup()
            mk_test.add(types.InlineKeyboardButton("🤖 احصل على كودك", url="https://t.me/ZERO_OTP1_BOT"))
            bot.send_message(LOG_CHANNEL_ID,
                f"🔥 <b>كود جديد!</b>\n"
                f"┌──────────────────\n"
                f"│ 🛠 <b>الخدمة:</b> {svc}\n"
                f"│ 🌍 <b>الدولة:</b> {flag}\n"
                f"│ 📱 <b>الرقم:</b> <code>+{masked3}</code>\n"
                f"│ 🔐 <b>الكود:</b> <code>{code}</code>\n"
                f"│ 💬 <b>الرسالة:</b> Your {svc} code is {code}\n"
                f"└──────────────────\n"
                f"#كود_جديد #{svc} ⚠️ <i>هذه رسالة تجريبية</i>",
                reply_markup=mk_test)
            bot.answer_callback_query(call.id,f"✅ تم إرسال كود تجريبي للقناة!\n🔐 الكود: {code}",show_alert=True)
        except Exception as e:
            bot.answer_callback_query(call.id,f"❌ فشل الإرسال: {e}",show_alert=True)

    elif data == "adm_roxy_numbers" and uid in ADMIN_IDS:
        bot.answer_callback_query(call.id,"⏳ جاري جلب الأرقام...")
        numbers = fetch_roxy_numbers()
        if not numbers: bot.send_message(cid,"⚠️ لا توجد أرقام."); return
        send_chunks(cid,f"📱 <b>أرقام روكسي ({len(numbers)}):</b>\n\n",[f"<code>{n}</code>" for n in numbers])

    elif data == "adm_roxy_msgs" and uid in ADMIN_IDS:
        bot.answer_callback_query(call.id,"⏳ جاري جلب الرسائل...")
        rows,total = fetch_roxy_msgs()
        data_rows = [r for r in rows if len(r)>=5] if rows else []
        if not data_rows: bot.send_message(cid,"📭 لا توجد رسائل اليوم."); return
        lines = []
        for i,row in enumerate(data_rows,1):
            dt   = str(row[0])
            to   = re.sub(r'<[^>]+>','',str(row[2])).strip()
            cli  = re.sub(r'<[^>]+>','',str(row[3])).strip()
            msg  = re.sub(r'<[^>]+>','',str(row[4])).strip()
            flag = get_flag(re.sub(r'\D','',to))
            code = extract_code(msg)
            line = (f"{'═'*20}\n📩 <b>#{i}</b> | 🕐 {dt}\n"
                    f"📱 {flag} <code>{to}</code> | ⚙️ {cli}\n💬 <i>{msg}</i>")
            if code: line += f"\n🔐 <b>الكود: <code>{code}</code></b>"
            lines.append(line)
        send_chunks(cid,f"📨 <b>رسائل اليوم ({total}):</b>\n\n",lines)

    elif data == "adm_users" and uid in ADMIN_IDS:
        with get_db() as c:
            users = c.execute("SELECT user_id,username,join_date,total_codes FROM users ORDER BY total_codes DESC LIMIT 20").fetchall()
        lines = []
        for i,u in enumerate(users,1):
            un = f"@{u[1]}" if u[1] else "—"
            lines.append(f"{i}. <code>{u[0]}</code> | {un} | 🎯{u[3]} | 📅{u[2]}")
        send_chunks(cid,f"👥 <b>أحدث المستخدمين (Top 20):</b>\n\n",lines)

    elif data == "adm_balances" and uid in ADMIN_IDS:
        with get_db() as c:
            users = c.execute("SELECT user_id,username,balance,total_codes FROM users WHERE balance>0 ORDER BY balance DESC LIMIT 20").fetchall()
            total_paid = c.execute("SELECT SUM(balance) FROM users").fetchone()[0] or 0
        if not users:
            bot.answer_callback_query(call.id,"لا يوجد مستخدمون لديهم رصيد",show_alert=True); return
        lines = []
        for i,u in enumerate(users,1):
            un = f"@{u[1]}" if u[1] else "—"
            lines.append(f"{i}. <code>{u[0]}</code> {un}\n💰 ${round(u[2],3)} | 🎯 {u[3]} كود")
        lines.append(f"\n📊 <b>إجمالي الأرصدة: ${round(total_paid,3)}</b>")
        send_chunks(cid, "💰 <b>أرصدة المستخدمين:</b>\n\n", lines)

    elif data == "adm_clear_history" and uid in ADMIN_IDS:
        with get_db() as c:
            count = c.execute("SELECT COUNT(*) FROM history").fetchone()[0]
            c.execute("DELETE FROM history")
        bot.answer_callback_query(call.id,f"✅ تم مسح {count} سجل من التاريخ",show_alert=True)

    elif data == "adm_block_num" and uid in ADMIN_IDS:
        smart_edit(cid,uid,"🔢 <b>أرسل الرقم المراد حظره:</b>",
                   types.InlineKeyboardMarkup().add(btn("❌ إلغاء","cancel_input")))
        set_pending(uid,"block_num")

    elif data == "adm_blocked_list" and uid in ADMIN_IDS:
        with get_db() as c:
            nums = c.execute("SELECT number,blocked_at FROM blocked_numbers").fetchall()
        if not nums: bot.answer_callback_query(call.id,"لا توجد أرقام محظورة",show_alert=True); return
        lines = [f"🚫 <code>{n[0]}</code> — {n[1]}" for n in nums]
        send_chunks(cid,f"🔢 <b>الأرقام المحظورة ({len(nums)}):</b>\n\n",lines)

    elif data == "adm_broadcast" and uid in ADMIN_IDS:
        smart_edit(cid,uid,"📣 <b>أرسل نص الرسالة الجماعية:</b>",
                   types.InlineKeyboardMarkup().add(btn("❌ إلغاء","cancel_input")))
        set_pending(uid,"broadcast")

    elif data == "adm_ban" and uid in ADMIN_IDS:
        smart_edit(cid,uid,"🚫 <b>أرسل ID المستخدم للحظر:</b>",
                   types.InlineKeyboardMarkup().add(btn("❌ إلغاء","cancel_input")))
        set_pending(uid,"ban_user")

    elif data == "adm_unban" and uid in ADMIN_IDS:
        smart_edit(cid,uid,"✅ <b>أرسل ID المستخدم لرفع الحظر:</b>",
                   types.InlineKeyboardMarkup().add(btn("❌ إلغاء","cancel_input")))
        set_pending(uid,"unban_user")

    elif data == "adm_setimg" and uid in ADMIN_IDS:
        smart_edit(cid,uid,"🖼️ <b>أرسل الصورة الآن:</b>",
                   types.InlineKeyboardMarkup().add(btn("❌ إلغاء","cancel_input")))
        set_pending(uid,"set_image")

    elif data == "adm_delimg" and uid in ADMIN_IDS:
        ss("bot_image","")
        with get_db() as c: c.execute("UPDATE users SET has_image=0")
        bot.answer_callback_query(call.id,"✅ تم حذف الصورة")
        show_admin(cid,uid)

    elif data == "adm_apps" and uid in ADMIN_IDS:
        with get_db() as c: apps = c.execute("SELECT * FROM apps").fetchall()
        mk = types.InlineKeyboardMarkup(row_width=2)
        for a in apps: mk.add(btn(f"🗑 {a[1]}",f"del_app_{a[0]}"))
        mk.add(back("admin_panel"))
        smart_edit(cid,uid,"📱 <b>اختر التطبيق للحذف:</b>",mk)

    elif data == "add_app" and uid in ADMIN_IDS:
        smart_edit(cid,uid,"✏️ <b>أرسل اسم التطبيق:</b>",
                   types.InlineKeyboardMarkup().add(btn("❌ إلغاء","cancel_input")))
        set_pending(uid,"add_app")

    elif data.startswith("del_app_") and uid in ADMIN_IDS:
        aid = data.split("_")[2]
        with get_db() as c: c.execute("DELETE FROM apps WHERE id=?",(aid,))
        bot.answer_callback_query(call.id,"✅ تم الحذف")
        with get_db() as c: apps = c.execute("SELECT * FROM apps").fetchall()
        mk = types.InlineKeyboardMarkup(row_width=2)
        for a in apps: mk.add(btn(f"🗑 {a[1]}",f"del_app_{a[0]}"))
        mk.add(back("admin_panel"))
        smart_edit(cid,uid,"📱 <b>اختر التطبيق للحذف:</b>",mk)

    elif data == "adm_combos" and uid in ADMIN_IDS:
        with get_db() as c: apps = c.execute("SELECT name FROM apps").fetchall()
        mk = types.InlineKeyboardMarkup(row_width=3)
        for a in apps: mk.add(btn(a[0],f"up_combo_{a[0]}"))
        mk.add(back("admin_panel"))
        smart_edit(cid,uid,"📦 <b>اختر التطبيق لرفع الأرقام:</b>",mk)

    elif data.startswith("up_combo_") and uid in ADMIN_IDS:
        app_name = data[9:]
        smart_edit(cid,uid,f"📤 <b>رفع أرقام {app_name}</b>\nأرسل ملف TXT بالأرقام.",
                   types.InlineKeyboardMarkup().add(btn("❌ إلغاء","cancel_input")))
        set_pending(uid,"upload_combo",app_name)

    elif data == "del_all_combos" and uid in ADMIN_IDS:
        with get_db() as c: c.execute("DELETE FROM combos")
        bot.answer_callback_query(call.id,"✅ تم حذف جميع الأرقام",show_alert=True)

    elif data == "adm_stats" and uid in ADMIN_IDS:
        with get_db() as c:
            u  = c.execute("SELECT COUNT(*) FROM users").fetchone()[0]
            a  = c.execute("SELECT COUNT(*) FROM apps").fetchone()[0]
            s  = c.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
            h  = c.execute("SELECT COUNT(*) FROM history").fetchone()[0]
            bl = c.execute("SELECT COUNT(*) FROM blocked_numbers").fetchone()[0]
            tc = c.execute("SELECT SUM(total_codes) FROM users").fetchone()[0] or 0
        bot.answer_callback_query(call.id,
            f"📊 إحصائيات\n\n"
            f"👥 المستخدمون: {u}\n📱 التطبيقات: {a}\n"
            f"⏳ جلسات: {s}\n📨 رسائل: {h}\n"
            f"🎯 أكواد موزّعة: {tc}\n🚫 أرقام محظورة: {bl}",show_alert=True)

    elif data == "cancel_input":
        with get_db() as c: c.execute("DELETE FROM pending_inputs WHERE user_id=?",(uid,))
        show_home(cid,uid)

    elif data == "none":
        bot.answer_callback_query(call.id)

# ═══════════════════════════════════════════
#           معالج الرسائل
# ═══════════════════════════════════════════
@bot.message_handler(content_types=['text','photo','document'])
def handle_inputs(msg):
    uid = msg.from_user.id
    cid = msg.chat.id
    logger.info(f"✉️ uid={uid} type={msg.content_type}")
    with get_db() as c:
        pending = c.execute("SELECT action,data FROM pending_inputs WHERE user_id=?",(uid,)).fetchone()
    if not pending: return
    action,pdata = pending

    try:
        if action == "add_app" and msg.text:
            with get_db() as c:
                try:
                    c.execute("INSERT INTO apps(name) VALUES(?)",(msg.text.strip(),))
                    bot.reply_to(msg,f"✅ تم إضافة <b>{msg.text.strip()}</b>")
                except: bot.reply_to(msg,"❌ التطبيق موجود مسبقاً")
                c.execute("DELETE FROM pending_inputs WHERE user_id=?",(uid,))
            show_home(cid,uid)

        elif action == "set_image" and msg.photo:
            ss("bot_image",msg.photo[-1].file_id)
            with get_db() as c:
                c.execute("UPDATE users SET has_image=1 WHERE user_id=?",(uid,))
                c.execute("DELETE FROM pending_inputs WHERE user_id=?",(uid,))
            bot.reply_to(msg,"✅ تم تعيين الصورة")
            show_home(cid,uid)

        elif action == "broadcast" and msg.text and uid in ADMIN_IDS:
            with get_db() as c:
                users = c.execute("SELECT user_id FROM users").fetchall()
                c.execute("DELETE FROM pending_inputs WHERE user_id=?",(uid,))
            ok = 0
            for (u_id,) in users:
                try:
                    bot.send_message(u_id,f"📣 <b>رسالة من الإدارة:</b>\n\n{msg.text}")
                    ok+=1; time.sleep(0.05)
                except: pass
            bot.reply_to(msg,f"✅ تم الإرسال لـ <b>{ok}</b> من {len(users)}")
            show_home(cid,uid)

        elif action == "ban_user" and msg.text and uid in ADMIN_IDS:
            ss(f"ban_{msg.text.strip()}","1")
            with get_db() as c: c.execute("DELETE FROM pending_inputs WHERE user_id=?",(uid,))
            bot.reply_to(msg,f"🚫 تم حظر <code>{msg.text.strip()}</code>")
            show_home(cid,uid)

        elif action == "unban_user" and msg.text and uid in ADMIN_IDS:
            with get_db() as c:
                c.execute("DELETE FROM settings WHERE key=?",(f"ban_{msg.text.strip()}",))
                c.execute("DELETE FROM pending_inputs WHERE user_id=?",(uid,))
            bot.reply_to(msg,f"✅ تم رفع الحظر عن <code>{msg.text.strip()}</code>")
            show_home(cid,uid)

        elif action == "block_num" and msg.text and uid in ADMIN_IDS:
            num = re.sub(r'\D','',msg.text.strip())
            with get_db() as c:
                c.execute("INSERT OR IGNORE INTO blocked_numbers(number,blocked_at) VALUES(?,?)",
                          (num,datetime.now().strftime('%Y-%m-%d %H:%M')))
                c.execute("DELETE FROM pending_inputs WHERE user_id=?",(uid,))
            bot.reply_to(msg,f"🚫 تم حظر الرقم <code>{num}</code>")
            show_home(cid,uid)

        elif action == "withdraw_info" and msg.text:
            with get_db() as c:
                u = c.execute("SELECT balance FROM users WHERE user_id=?",(uid,)).fetchone()
                balance = round(u[0],3) if u else 0
                c.execute("DELETE FROM pending_inputs WHERE user_id=?",(uid,))
            try:
                uname = msg.from_user.username or "—"
                bot.send_message(ADMIN_IDS[0],
                    f"💸 <b>طلب سحب جديد!</b>\n\n"
                    f"👤 المستخدم: @{uname} (<code>{uid}</code>)\n"
                    f"💰 المبلغ: <b>${balance}</b>\n"
                    f"📋 التفاصيل:\n{msg.text}")
            except: pass
            bot.reply_to(msg,
                f"✅ <b>تم إرسال طلب السحب!</b>\n\n"
                f"💰 المبلغ: <b>${balance}</b>\n"
                f"⏳ سيتم مراجعة طلبك خلال 24 ساعة")
            show_home(cid,uid)

        elif action == "upload_combo" and msg.document:
            fi = bot.get_file(msg.document.file_id)
            content = bot.download_file(fi.file_path).decode('utf-8',errors='ignore')
            sorted_nums = {}; total = 0
            for line in content.splitlines():
                phone = re.sub(r'\D','',line)
                if len(phone)<7: continue
                fc = "UNKNOWN"
                for code in sorted(COUNTRY_MAP.keys(),key=len,reverse=True):
                    if phone.startswith(code): fc=code; break
                if fc!="UNKNOWN":
                    sorted_nums.setdefault(fc,[]).append(phone); total+=1
            with get_db() as c:
                for code,nums in sorted_nums.items():
                    ex = c.execute("SELECT numbers FROM combos WHERE service=? AND country_code=?",
                                   (pdata.upper(),code)).fetchone()
                    nl = list(set(json.loads(ex[0])+nums)) if ex else nums
                    c.execute("INSERT OR REPLACE INTO combos(service,country_code,numbers) VALUES(?,?,?)",
                              (pdata.upper(),code,json.dumps(nl)))
                c.execute("DELETE FROM pending_inputs WHERE user_id=?",(uid,))
            bot.reply_to(msg,f"✅ تم رفع <b>{total}</b> رقم!")
            show_home(cid,uid)

    except Exception as e:
        logger.error(f"handle_inputs: {e}",exc_info=True)
        bot.reply_to(msg,"❌ حدث خطأ، حاول مجدداً")

# ═══════════════════════════════════════════
#           تشغيل البوت
# ═══════════════════════════════════════════
if __name__ == "__main__":
    logger.info("🔧 تهيئة قاعدة البيانات...")
    init_db()
    logger.info("✅ قاعدة البيانات جاهزة")
    logger.info("🔗 تسجيل الدخول على روكسي...")
    ok = roxy_login()
    logger.info(f"{'✅ تم تسجيل الدخول' if ok else '⚠️ فشل تسجيل الدخول'}")
    logger.info("🚀 بدء مراقبة الرسائل...")
    threading.Thread(target=monitor_loop,daemon=True).start()
    logger.info("🤖 البوت يعمل الآن ✅")
    bot.infinity_polling(timeout=60,long_polling_timeout=60)
()
