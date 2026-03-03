import os
import json
import asyncio
import aiohttp
import time
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, CallbackQueryHandler, MessageHandler, filters

# --- CONFIGURATION ---
BOT_TOKEN = os.getenv("BOT_TOKEN", "8522649340:AAEa6FlDQPz-Ph46BDUZ2wtBcm5xMWGGW84") # Keep default for testing
REDIS_URL = os.getenv("KV_URL") # Vercel KV

import redis
if REDIS_URL:
    try:
        db = redis.from_url(REDIS_URL, decode_responses=True)
        print("✅ Connected to Vercel KV (Redis)")
    except Exception as e:
        print(f"❌ Redis Connection Failed: {e}")
        db = {}
else:
    print("⚠️ No Redis URL found. Using in-memory dictionary (Will reset on Vercel cold starts).")
    db = {}

def get_users():
    if isinstance(db, dict): return db.get("users", {})
    users_str = db.get("users")
    return json.loads(users_str) if users_str else {}

def save_users(users_dict):
    if isinstance(db, dict): db["users"] = users_dict
    else: db.set("users", json.dumps(users_dict))

USER_STATES = {} 

# --- TEXTS ---
TEXTS = {
    "start_new_user": "👋 <b>Welcome to ITS ERP Assistant! (Vercel Edition)</b>\n\nLet's get you set up.\n\nPlease enter your <b>ERP Email ID</b>:",
    "prompt_password": "✅ Email saved!\n\nNow, enter your <b>ERP Password</b>:",
    "login_verifying": "⏳ Verifying your credentials...",
    "login_success": "🎉 <b>Login successful!</b> You are all set.",
    "login_failed": "❌ <b>Login failed.</b> Incorrect email or password.\nUse /start to try again.",
    "menu_greeting": "👋 Welcome back, <b>{name}</b>!\n\nPlease select an option below:",
    "logout_success": "✅ Successfully logged out.",
    "not_logged_in": "You are not logged in!",
    "please_start": "Please use /start to set up your account."
}

# --- ERP API LOGIC ---
async def fetch_api(url, method="GET", json_data=None, headers=None):
    async with aiohttp.ClientSession() as session:
        if method == "POST":
            async with session.post(url, json=json_data, headers=headers) as resp:
                return await resp.json() if resp.status == 200 else None
        else:
            async with session.get(url, headers=headers) as resp:
                return await resp.json() if resp.status == 200 else None

async def get_valid_token(email, password):
    # Direct Login via API bypassing Playwright
    payload = {"userType": 1, "email": email, "password": password, "deviceType": "web"}
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}
    data = await fetch_api("https://itsapi.aperptech.com/api/login", method="POST", json_data=payload, headers=headers)
    
    if data and data.get("success"):
        return data["data"].get("token")
    return None

async def fetch_profile_data(token):
    headers = {"Authorization": f"Bearer {token}", "User-Agent": "Mozilla/5.0"}
    return await fetch_api("https://itsapi.aperptech.com/api/profile", headers=headers)

async def fetch_erp_data(token, month=None):
    headers = {"Authorization": f"Bearer {token}", "User-Agent": "Mozilla/5.0"}
    summary_url = "https://itsapi.aperptech.com/api/my/final/attendances"
    detailed_url = f"https://itsapi.aperptech.com/api/my/attendances?month={month}&date=&session=2025-2026" if month else None
    
    summary = await fetch_api(summary_url, headers=headers)
    detailed = await fetch_api(detailed_url, headers=headers) if detailed_url else None
    return {"summary": summary, "detailed": detailed}

async def fetch_timetable_data(token):
    headers = {"Authorization": f"Bearer {token}", "User-Agent": "Mozilla/5.0"}
    return await fetch_api("https://itsapi.aperptech.com/api/student/timetables/2025-2026/9", headers=headers)


# --- TELEGRAM HANDLERS ---
def get_progress(percent, text):
    return f"⏳ <b>Processing... {percent}%</b>\n<i>{text}</i>"

async def show_main_menu(update: Update):
    user_id = str(update.effective_user.id)
    users = get_users()
    name = users.get(user_id, {}).get("name", "Student")
    
    keyboard = [
        [InlineKeyboardButton("👤 Profile Info", callback_data='menu_profile'), InlineKeyboardButton("🗓️ View Timetable", callback_data='menu_timetable')],
        [InlineKeyboardButton("📊 Attendance Percentage", callback_data='menu_perc')],
        [InlineKeyboardButton("📅 Subject-wise (Monthly)", callback_data='menu_sub_list')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    text = TEXTS["menu_greeting"].replace("{name}", name)
    
    if update.message: await update.message.reply_text(text, reply_markup=reply_markup, parse_mode="HTML")
    elif update.callback_query: await update.callback_query.message.edit_text(text, reply_markup=reply_markup, parse_mode="HTML")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    if user_id in get_users(): await show_main_menu(update)
    else:
        USER_STATES[user_id] = {"state": "WAITING_EMAIL"}
        await update.message.reply_text(TEXTS["start_new_user"], parse_mode="HTML")

async def logout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    users = get_users()
    if user_id in users:
        del users[user_id]
        save_users(users)
        await update.message.reply_text(TEXTS["logout_success"], parse_mode="HTML")
    else:
        await update.message.reply_text(TEXTS["not_logged_in"], parse_mode="HTML")

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    text = update.message.text.strip()
    
    if user_id in USER_STATES:
        state = USER_STATES[user_id].get("state")
        if state == "WAITING_EMAIL":
            USER_STATES[user_id]["email"] = text
            USER_STATES[user_id]["state"] = "WAITING_PASSWORD"
            await update.message.reply_text(TEXTS["prompt_password"], parse_mode="HTML")
        elif state == "WAITING_PASSWORD":
            email = USER_STATES[user_id]["email"]
            password = text
            
            loading_msg = await update.message.reply_text(TEXTS["login_verifying"], parse_mode="HTML")
            token = await get_valid_token(email, password)
            
            if token:
                profile_data = await fetch_profile_data(token)
                d = profile_data.get("data", {}) if profile_data else {}
                first_name = d.get("firstName", "Student").title()
                
                users = get_users()
                users[user_id] = {"email": email, "password": password, "name": first_name, "token": token}
                save_users(users)
                
                del USER_STATES[user_id]
                await loading_msg.delete()
                await update.message.reply_text(TEXTS["login_success"], parse_mode="HTML")
                await show_main_menu(update)
            else:
                del USER_STATES[user_id]
                await loading_msg.edit_text(TEXTS["login_failed"], parse_mode="HTML")

def generate_markdown_bar(perc):
    filled = int((perc / 100) * 10)
    bar = "🟩" * filled + "⬜" * (10 - filled)
    if perc < 60: bar = "🟥" * filled + "⬜" * (10 - filled)
    elif perc < 75: bar = "🟨" * filled + "⬜" * (10 - filled)
    return bar

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = str(query.from_user.id)
    await query.answer()

    users = get_users()
    if user_id not in users:
        await query.message.edit_text("⏳ Session expired. Use /start.", parse_mode="HTML")
        return

    email = users[user_id]["email"]
    password = users[user_id]["password"]

    # Re-login to get fresh token if needed (tokens expire)
    token = await get_valid_token(email, password)
    if not token:
        await query.message.edit_text("❌ Login expired or credentials invalid. Use /logout.", parse_mode="HTML")
        return

    if query.data == 'menu_profile':
        await query.edit_message_text(get_progress(10, "Fetching profile..."), parse_mode="HTML")
        profile_data = await fetch_profile_data(token)
        
        if profile_data and profile_data.get("success"):
            d = profile_data.get("data", {})
            course = d.get("course", {}).get("courseNickName", "N/A")
            branch = d.get("branch", {}).get("branchNickName", "")
            if branch: course += f" ({branch})"
            
            msg = f"👤 <b>PROFILE</b>\n━━━━━━━━━━━━━━━━━━\n📛 Name: {d.get('fullName', 'N/A')}\n🎓 Course: {course}\n🔢 Roll No: {d.get('rollNo', 'N/A')}\n📧 Email: {d.get('email', 'N/A')}\n📱 Mobile: {d.get('mobile', 'N/A')}\n"
            await query.edit_message_text(msg, parse_mode="HTML")
        else:
            await query.edit_message_text("❌ Failed to fetch profile.", parse_mode="HTML")
            
    elif query.data == 'menu_perc':
        await query.edit_message_text(get_progress(30, "Downloading attendance..."), parse_mode="HTML")
        data = await fetch_erp_data(token)
        
        if data.get("summary") and data["summary"].get("success"):
            subjects = data["summary"].get("data", [])
            msg = "📊 <b>ATTENDANCE SUMMARY</b>\n━━━━━━━━━━━━━━━━━━\n\n"
            
            for item in subjects:
                name = item.get("subjectName", "Unknown")
                if len(name) > 25: name = name[:22] + "..."
                perc = item.get("subjectTotalPercentage", 0)
                bar = generate_markdown_bar(perc)
                
                if "ALL SUBJECTS" in name:
                    msg += f"\n🎯 <b>OVERALL: {perc}%</b>\n{bar}\n"
                else:
                    msg += f"📚 <b>{name}</b>\n{bar} <b>{perc}%</b>\n\n"
                    
            await query.edit_message_text(msg, parse_mode="HTML")
        else:
            await query.edit_message_text("❌ Failed to fetch data.", parse_mode="HTML")

    elif query.data == 'menu_timetable':
        await query.edit_message_text(get_progress(40, "Fetching Timetable..."), parse_mode="HTML")
        data = await fetch_timetable_data(token)
        
        if data and data.get("success"):
            raw_data = data.get("data", [])
            abbr_map = {str(a.get("SN")): a for a in data.get("abbreviations", [])}
            
            msg = "🗓️ <b>LIVE TIMETABLE</b>\n━━━━━━━━━━━━━━━━━━\n"
            for row in raw_data:
                day = str(row.get("day", "")).upper()
                if "DAY" in day or not day: continue
                
                msg += f"\n📅 <b>{day}</b>\n"
                for i in range(1, 9):
                    cell = row.get(str(i))
                    if cell:
                        if isinstance(cell, list) and cell: cell = cell[0] # Take first if multiple
                        
                        if isinstance(cell, (int, str)) and str(cell) in abbr_map: cell = abbr_map[str(cell)]
                        
                        if isinstance(cell, dict):
                            sub = cell.get("subjectCode", "")
                            room = cell.get("roomNo", "")
                            if sub: msg += f"• P{i}: <b>{sub}</b> (📍 {room})\n"
                            
            await query.edit_message_text(msg, parse_mode="HTML")
        else:
            await query.edit_message_text("❌ Failed to fetch timetable.", parse_mode="HTML")

    elif query.data == 'menu_sub_list':
        keyboard = [
            [InlineKeyboardButton("Jan", callback_data='month_1'), InlineKeyboardButton("Feb", callback_data='month_2'), InlineKeyboardButton("Mar", callback_data='month_3')],
            [InlineKeyboardButton("Apr", callback_data='month_4'), InlineKeyboardButton("May", callback_data='month_5'), InlineKeyboardButton("Jun", callback_data='month_6')],
            [InlineKeyboardButton("Jul", callback_data='month_7'), InlineKeyboardButton("Aug", callback_data='month_8'), InlineKeyboardButton("Sep", callback_data='month_9')],
            [InlineKeyboardButton("Oct", callback_data='month_10'), InlineKeyboardButton("Nov", callback_data='month_11'), InlineKeyboardButton("Dec", callback_data='month_12')]
        ]
        await query.edit_message_text("📅 Select month for Master Timeline:", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")

    elif query.data.startswith('month_'):
        month_idx = query.data.split('_')[1]
        await query.edit_message_text(get_progress(40, "Downloading records..."), parse_mode="HTML")
        
        data = await fetch_erp_data(token, month=month_idx)
        detailed = data.get("detailed")
        
        if detailed and detailed.get("success") and detailed.get("data"):
            days = detailed.get("data", [])
            msg = f"📅 <b>MONTH {month_idx} REGISTRY</b>\n━━━━━━━━━━━━━━━━━━\n\n"
            
            for day in days[:10]: # Limit to 10 days to fit in Telegram max message length
                date_str = day.get("attendanceDate", "").split("T")[0]
                msg += f"🗓️ {date_str}:\n"
                for lec in day.get("attendances", []):
                    code = lec.get("subjectCode", "NA")
                    stat = lec.get("status", "-")
                    icon = "✅" if stat == "P" else "❌" if stat == "A" else "➖"
                    msg += f" {icon} {code}\n"
                msg += "\n"
                
            if len(days) > 10:
                msg += f"\n<i>...and {len(days)-10} more days. (Truncated for Vercel)</i>\n"
                
            msg += f"━━━━━━━━━━━━━━━━━━\n🙋 Attended: {detailed.get('presentDays', 0)} | 🏃 Missed: {detailed.get('absentDays', 0)}"
            await query.edit_message_text(msg, parse_mode="HTML")
        else:
            await query.edit_message_text("❌ No data found for this month.", parse_mode="HTML")

# Build the app structure
app = ApplicationBuilder().token(BOT_TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("logout", logout))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
app.add_handler(CallbackQueryHandler(button_handler))

