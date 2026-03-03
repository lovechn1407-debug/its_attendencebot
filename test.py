import asyncio
import io
import datetime
import time
import json
import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, CallbackQueryHandler, MessageHandler, filters
from playwright.async_api import async_playwright
from aiohttp import web  # For the Web Admin Panel

# --- CONFIGURATION ---
BOT_TOKEN = "8522649340:AAEa6FlDQPz-Ph46BDUZ2wtBcm5xMWGGW84"
DB_FILE = "users_db.json"
TEXTS_FILE = "texts_db.json"

# Web Panel Config
ADMIN_PASSWORD = "admin" # Change this to secure your web panel!
WEB_PORT = 8080

# --- GLOBAL INSTANCES ---
GLOBAL_PW = None
GLOBAL_BROWSER = None
GLOBAL_APP = None

# --- TEXTS & MESSAGES MANAGEMENT ---
DEFAULT_TEXTS = {
    "start_new_user": "👋 <b>Welcome to ITS ERP Assistant!</b>\n\nIt looks like you are new here. Let's get you set up.\n\nPlease enter your <b>ERP Email ID</b>:",
    "prompt_password": "✅ Email saved!\n\nNow, please enter your <b>ERP Password</b>:\n<i>(Don't worry, your credentials are saved securely locally!)</i>",
    "login_verifying": "⏳ Verifying your credentials. Please wait...",
    "login_success": "🎉 <b>Login successful!</b> You are all set.",
    "login_failed": "❌ <b>Login failed.</b> Incorrect email or password.\n\nPlease start again using /start.",
    "menu_greeting": "👋 Welcome back, <b>{name}</b>!\n\nPlease select an option below:",
    "logout_success": "✅ You have been successfully logged out.\n\nUse /start to login again.",
    "not_logged_in": "You are not currently logged in!",
    "please_start": "Please use /start to set up your account.",
    "invalid_input": "I didn't understand that. Use the menu buttons or /start.",
    "select_month": "📅 Select the month for the master timeline:",
    "btn_profile": "👤 Profile Info",
    "btn_timetable": "🗓️ View Timetable",
    "btn_perc": "📊 Attendance Percentage",
    "btn_sub": "📅 Subject-wise (Monthly)",
    "session_expired": "⏳ Session expired. Please use /start to log in again.",
    "err_fetch": "❌ Failed to fetch data. Your credentials might be incorrect. Use /logout to reset them.",
    "err_no_data": "❌ No data found for this month. Or your credentials might be incorrect.",
    "err_profile": "❌ Failed to fetch profile. Your credentials might be incorrect. Use /logout to reset them.",
    "caption_summary": "✨ <b>Premium Attendance Summary</b>\n⏱️ Generated in {elapsed}s",
    "caption_detailed": "✨ <b>Detailed Master Timeline (Month {month})</b>\n⏱️ Generated in {elapsed}s",
    "caption_timetable": "🗓️ <b>Your Live Timetable</b>\n⏱️ Generated in {elapsed}s",
    "watermark": "© Copyright Love Chauhan, BTech CSE DS",
    "title_summary": "📊 Attendance Overview",
    "title_detailed": "📅 Monthly Master Timeline",
    "overall_att": "OVERALL ATTENDANCE",
    "no_data_html": "No data found for this month.",
    "col_date": "Date",
    "col_lunch": "LUNCH &nbsp; ☕",
    "badge_present": "PRESENT",
    "badge_absent": "ABSENT",
    "stat_attended": "Lectures Attended",
    "stat_missed": "Lectures Missed",
    "prog_init": "Initializing...",
    "prog_verify": "Verifying cached connection...",
    "prog_auth": "Authenticating with ERP...",
    "prog_intercept": "Verifying security tokens...",
    "prog_conn": "Establishing connection...",
    "prog_prof": "Fetching profile data...",
    "prog_dl": "Downloading live attendance...",
    "prog_time": "Rendering Timetable...",
    "prog_ui_sum": "Creating UI...",
    "prog_ui_det": "Creating Table UI...",
    "prog_snap": "Snapping High-Res Photo...",
    "prog_done": "Sending to Chat!"
}

def load_texts():
    if os.path.exists(TEXTS_FILE):
        try:
            with open(TEXTS_FILE, 'r') as f:
                saved_texts = json.load(f)
                merged = DEFAULT_TEXTS.copy()
                merged.update(saved_texts)
                return merged
        except: pass
    return DEFAULT_TEXTS.copy()

def save_texts(texts_dict):
    with open(TEXTS_FILE, 'w') as f:
        json.dump(texts_dict, f, indent=4)

TEXTS = load_texts()

# --- DATABASE LOGIC ---
def load_users():
    if os.path.exists(DB_FILE):
        with open(DB_FILE, 'r') as f:
            return json.load(f)
    return {}

def save_users(users):
    with open(DB_FILE, 'w') as f:
        json.dump(users, f, indent=4)

USERS = load_users()
USER_STATES = {} 

# --- CORE SCRAPING & RENDERING LOGIC ---

async def get_valid_headers(user_id, email, password, progress_cb=None):
    headers = USERS.get(user_id, {}).get("headers")
    api_context = await GLOBAL_PW.request.new_context()
    
    if headers:
        if progress_cb: asyncio.create_task(progress_cb(20, TEXTS.get("prog_verify", "")))
        resp = await api_context.get("https://itsapi.aperptech.com/api/profile", headers=headers)
        if resp.ok:
            await api_context.dispose()
            return headers

    if progress_cb: asyncio.create_task(progress_cb(30, TEXTS.get("prog_auth", "")))
    
    context = await GLOBAL_BROWSER.new_context()
    page = await context.new_page()
    await page.route("**/*", lambda route: route.continue_() if route.request.resource_type in ["document", "script", "xhr", "fetch"] else route.abort())
    
    stolen_headers = None
    headers_event = asyncio.Event()

    async def handle_request(request):
        nonlocal stolen_headers
        if "api/profile" in request.url and request.method == "GET":
            stolen_headers = request.headers
            headers_event.set()

    page.on("request", handle_request)
    
    try:
        await page.goto("https://students.its.aperptech.com/", wait_until="domcontentloaded")
        await page.fill('input[placeholder="Email"]', email)
        await page.fill('input[placeholder="Password"]', password)
        await page.click('button:has-text("Log in")')
        
        if progress_cb: asyncio.create_task(progress_cb(50, TEXTS.get("prog_intercept", "")))
        await asyncio.wait_for(headers_event.wait(), timeout=8.0)
        
        if stolen_headers:
            if user_id in USERS:
                USERS[user_id]["headers"] = stolen_headers
                save_users(USERS)
            return stolen_headers
    except Exception:
        pass
    finally:
        await context.close()
        await api_context.dispose()
        
    return None

async def fetch_profile_data(user_id, email, password, progress_cb=None):
    if progress_cb: asyncio.create_task(progress_cb(10, TEXTS.get("prog_conn", "")))
    headers = await get_valid_headers(user_id, email, password, progress_cb)
    if not headers: return None
    
    if progress_cb: asyncio.create_task(progress_cb(70, TEXTS.get("prog_prof", "")))
    
    api_context = await GLOBAL_PW.request.new_context()
    resp = await api_context.get("https://itsapi.aperptech.com/api/profile", headers=headers)
    data = None
    if resp.ok:
        data = await resp.json()
        if not data.get("success"):
            data = None
            
    await api_context.dispose()
    return data

async def fetch_erp_data(user_id, email, password, month=None, progress_cb=None):
    if progress_cb: asyncio.create_task(progress_cb(10, TEXTS.get("prog_conn", "")))
    headers = await get_valid_headers(user_id, email, password, progress_cb)
    if not headers: return {"summary": None, "detailed": None}
    
    if progress_cb: asyncio.create_task(progress_cb(60, TEXTS.get("prog_dl", "")))
    
    api_context = await GLOBAL_PW.request.new_context()
    summary_url = "https://itsapi.aperptech.com/api/my/final/attendances"
    detailed_url = f"https://itsapi.aperptech.com/api/my/attendances?month={month}&date=&session=2025-2026" if month else None
    
    async def fetch_api(url):
        if not url: return None
        resp = await api_context.get(url, headers=headers)
        return await resp.json() if resp.ok else None

    summary_data, detailed_data = await asyncio.gather(
        fetch_api(summary_url),
        fetch_api(detailed_url)
    )
    
    await api_context.dispose()
    return {"summary": summary_data, "detailed": detailed_data}

async def fetch_timetable_data(user_id, email, password, progress_cb=None):
    if progress_cb: asyncio.create_task(progress_cb(10, TEXTS.get("prog_conn", "")))
    headers = await get_valid_headers(user_id, email, password, progress_cb)
    if not headers: return None
    
    if progress_cb: asyncio.create_task(progress_cb(60, TEXTS.get("prog_dl", "")))
    
    api_context = await GLOBAL_PW.request.new_context()
    url = "https://itsapi.aperptech.com/api/student/timetables/2025-2026/9"
    
    resp = await api_context.get(url, headers=headers)
    data = None
    if resp.ok:
        data = await resp.json()
        
    await api_context.dispose()
    return data

def get_base_css():
    return """
    body { 
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif, "Apple Color Emoji", "Segoe UI Emoji", "Segoe UI Symbol"; 
        background: #09090b; 
        background-image: radial-gradient(circle at top right, #1e1b4b, #09090b), linear-gradient(#ffffff05 1px, transparent 1px), linear-gradient(90deg, #ffffff05 1px, transparent 1px);
        background-size: 100% 100%, 20px 20px, 20px 20px;
        padding: 40px; 
        color: #f8fafc; 
    }
    .card { 
        background: rgba(24, 24, 27, 0.6); 
        backdrop-filter: blur(16px); 
        border: 1px solid rgba(255, 255, 255, 0.08); 
        padding: 40px; 
        border-radius: 24px; 
        box-shadow: 0 0 40px rgba(0, 0, 0, 0.8), inset 0 0 0 1px rgba(255,255,255,0.05); 
        max-width: 1400px; 
        margin: 0 auto; 
    }
    h1 { 
        text-align: center; 
        font-size: 2.8em; 
        font-weight: 800;
        background: linear-gradient(135deg, #38bdf8, #818cf8, #c084fc); 
        -webkit-background-clip: text; 
        -webkit-text-fill-color: transparent; 
        margin-top: 0;
        margin-bottom: 35px; 
        letter-spacing: -1px; 
    }
    .watermark {
        text-align: center;
        margin-top: 30px;
        padding-top: 20px;
        border-top: 1px solid rgba(255, 255, 255, 0.05);
        color: rgba(255, 255, 255, 0.3);
        font-size: 0.85em;
        font-weight: 500;
        letter-spacing: 1px;
    }
    """

async def render_summary_image(data, progress_cb=None):
    if not data.get("summary"): return None
    if progress_cb: asyncio.create_task(progress_cb(85, TEXTS.get("prog_ui_sum", "")))
    
    subjects = data["summary"].get("data", [])
    html = f"<html><head><style>{get_base_css()}" + """
    .subject-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(350px, 1fr)); gap: 20px; }
    .subject-card { background: rgba(30, 41, 59, 0.5); padding: 24px; border-radius: 16px; border: 1px solid rgba(255, 255, 255, 0.05); }
    .label { display: flex; justify-content: space-between; font-weight: 600; margin-bottom: 15px; font-size: 1.1em; color: #e2e8f0; }
    .bar-bg { background: #0f172a; border-radius: 100px; height: 14px; width: 100%; box-shadow: inset 0 2px 4px rgba(0,0,0,0.5); overflow: hidden; }
    .bar-fill { height: 100%; border-radius: 100px; }
    .total-card { margin-top: 30px; background: linear-gradient(135deg, rgba(56, 189, 248, 0.08), rgba(129, 140, 248, 0.08)); border: 1px solid rgba(56, 189, 248, 0.3); padding: 30px; border-radius: 20px; font-size: 1.3em; box-shadow: 0 0 30px rgba(56, 189, 248, 0.15); }
    .total-card .bar-bg { height: 18px; }
    </style></head><body><div class="card"><h1>""" + TEXTS.get("title_summary", "") + """</h1><div class="subject-grid">"""
    
    total_html = ""
    for item in subjects:
        name = item.get("subjectName")
        perc = item.get("subjectTotalPercentage", 0)
        
        if perc >= 75:
            color, shadow = "linear-gradient(90deg, #10b981, #34d399)", "rgba(16, 185, 129, 0.4)"
        elif perc >= 60:
            color, shadow = "linear-gradient(90deg, #f59e0b, #fbbf24)", "rgba(245, 158, 11, 0.4)"
        else:
            color, shadow = "linear-gradient(90deg, #ef4444, #f87171)", "rgba(239, 68, 68, 0.4)"
            
        row_html = f"""
        <div class="subject-card">
            <div class="label"><span>{name}</span><span style="color: #fff; text-shadow: 0 0 10px {shadow};">{perc}%</span></div>
            <div class="bar-bg"><div class="bar-fill" style="width: {perc}%; background: {color}; box-shadow: 0 0 12px {shadow};"></div></div>
        </div>
        """
        if name == "ALL SUBJECTS": 
            total_html = f"</div><div class='total-card'><div class='label'><span style='color:#38bdf8'>{TEXTS.get('overall_att', '')}</span><span style='color: #fff; text-shadow: 0 0 15px {shadow};'>{perc}%</span></div><div class='bar-bg'><div class='bar-fill' style='width: {perc}%; background: {color}; box-shadow: 0 0 15px {shadow};'></div></div></div>"
        else: 
            html += row_html
    
    html += total_html + f"<div class='watermark'>{TEXTS.get('watermark', '')}</div></div></body></html>"
    return await take_screenshot(html, ".card", progress_cb)

async def render_subjectwise_image(data, progress_cb=None):
    if not data.get("detailed"): return None
    if progress_cb: asyncio.create_task(progress_cb(85, TEXTS.get("prog_ui_det", "")))
    
    subject_map = {}
    if data.get("summary"):
        for item in data["summary"].get("data", []):
            subject_map[item.get("subjectCode")] = item.get("subjectName")

    days_data = data["detailed"].get("data", [])
    
    html = f"<html><head><style>{get_base_css()}" + """
    .table-container { overflow: hidden; border-radius: 20px; background: rgba(15, 23, 42, 0.5); border: 1px solid rgba(255,255,255,0.05); padding: 15px; margin-top: 20px;}
    table { width: 100%; border-collapse: separate; border-spacing: 6px; }
    th { color: #38bdf8; text-transform: uppercase; font-size: 0.85em; padding: 12px 5px; background: rgba(0,0,0,0.4); border-radius: 10px; text-align: center; font-weight: 800; letter-spacing: 1px;}
    td { background: rgba(30, 41, 59, 0.6); padding: 10px; border-radius: 10px; text-align: center; vertical-align: middle; box-shadow: inset 0 0 0 1px rgba(255,255,255,0.02);}
    
    .date-col { font-weight: 800; color: #f8fafc; font-size: 0.95em; background: rgba(56, 189, 248, 0.1); border: 1px solid rgba(56,189,248,0.2); white-space: nowrap; width: 80px;}
    .lunch-col { background: rgba(245, 158, 11, 0.1); color: #fbbf24; border: 1px solid rgba(245, 158, 11, 0.25); font-size: 1.2em; font-weight: 800; letter-spacing: 5px; writing-mode: vertical-rl; text-orientation: upright; padding: 0; box-shadow: 0 0 20px rgba(245, 158, 11, 0.1); width: 50px;}
    
    .cell-sub { font-weight: 600; color: #e2e8f0; font-size: 0.8em; margin-bottom: 8px; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; line-height: 1.3;}
    .p-badge { background: rgba(16, 185, 129, 0.15); color: #34d399; padding: 4px 10px; border-radius: 6px; border: 1px solid rgba(16, 185, 129, 0.3); font-weight: 800; font-size: 0.75em; box-shadow: 0 0 12px rgba(16,185,129,0.2); letter-spacing: 1px;}
    .a-badge { background: rgba(239, 68, 68, 0.15); color: #f87171; padding: 4px 10px; border-radius: 6px; border: 1px solid rgba(239, 68, 68, 0.3); font-weight: 800; font-size: 0.75em; box-shadow: 0 0 12px rgba(239,68,68,0.2); letter-spacing: 1px;}
    .empty-cell { color: #334155; font-style: italic; font-size: 1.5em;}
    
    .stats { display: flex; justify-content: space-around; margin-top: 30px; background: rgba(30, 41, 59, 0.6); padding: 25px; border-radius: 16px; border: 1px solid rgba(255,255,255,0.05); }
    .stat-item { text-align: center; }
    .stat-val { font-size: 2.5em; font-weight: 800; margin-bottom: 5px; }
    .val-p { color: #10b981; text-shadow: 0 0 20px rgba(16, 185, 129, 0.3); }
    .val-a { color: #ef4444; text-shadow: 0 0 20px rgba(239, 68, 68, 0.3); }
    .stat-label { color: #94a3b8; font-size: 0.85em; text-transform: uppercase; letter-spacing: 1.5px; font-weight: 600; }
    </style></head><body><div class="card"><h1>""" + TEXTS.get("title_detailed", "") + """</h1><div class="table-container">"""

    if not days_data:
        html += f"<h2 style='text-align:center; color:#94a3b8;'>{TEXTS.get('no_data_html', '')}</h2></div><div class='watermark'>{TEXTS.get('watermark', '')}</div></div></body></html>"
        return await take_screenshot(html, ".card", progress_cb)

    html += f"<table><tr><th>{TEXTS.get('col_date', '')}</th><th>Period 1</th><th>Period 2</th><th>Period 3</th><th>Period 4</th><th>Break</th><th>Period 5</th><th>Period 6</th><th>Period 7</th><th>Period 8</th></tr>"

    for idx, day in enumerate(days_data):
        date_str = day.get("attendanceDate", "").split("T")[0]
        try:
            d_obj = datetime.datetime.strptime(date_str, "%Y-%m-%d")
            clean_date = d_obj.strftime("%d %b")
        except:
            clean_date = date_str
            
        html += f"<tr><td class='date-col'>{clean_date}</td>"
        attendances = day.get("attendances", [])
        
        def get_cell(p_idx):
            if p_idx < len(attendances):
                lec = attendances[p_idx]
                sub_code = lec.get("subjectCode", "N/A")
                sub_name = subject_map.get(sub_code, sub_code)
                if len(sub_name) > 18: sub_name = sub_name[:16] + ".."
                
                stat = lec.get("status", "")
                if stat == "P": badge = f"<span class='p-badge'>{TEXTS.get('badge_present', '')}</span>"
                elif stat == "A": badge = f"<span class='a-badge'>{TEXTS.get('badge_absent', '')}</span>"
                else: badge = f"<span class='p-badge' style='color:gray;'>{stat}</span>"
                
                return f"<div class='cell-sub'>{sub_name}</div><div class='cell-stat'>{badge}</div>"
            return "<div class='empty-cell'>-</div>"

        for p in range(4): html += f"<td>{get_cell(p)}</td>"
        if idx == 0: html += f"<td rowspan='{len(days_data)}' class='lunch-col'>{TEXTS.get('col_lunch', '')}</td>"
        for p in range(4, 8): html += f"<td>{get_cell(p)}</td>"
            
        html += "</tr>"
        
    html += "</table></div>"
    
    html += f"""
    <div class='stats'>
        <div class='stat-item'><div class='stat-val val-p'>{data['detailed'].get('presentDays', 0)}</div><div class='stat-label'>{TEXTS.get('stat_attended', '')}</div></div>
        <div class='stat-item'><div class='stat-val val-a'>{data['detailed'].get('absentDays', 0)}</div><div class='stat-label'>{TEXTS.get('stat_missed', '')}</div></div>
    </div>
    <div class='watermark'>{TEXTS.get('watermark', '')}</div>
    </div></body></html>
    """
    
    return await take_screenshot(html, ".card", progress_cb)

async def render_timetable_image(api_response, progress_cb=None):
    if not api_response or not api_response.get("success"): return None
    if progress_cb: asyncio.create_task(progress_cb(85, TEXTS.get("prog_ui_det", "")))

    try:
        raw_data = api_response.get("data", [])
        if not raw_data: return None

        abbr_map = {}
        for abbr in api_response.get("abbreviations", []):
            sn = str(abbr.get("SN", ""))
            if sn: abbr_map[sn] = abbr

        header_row = next((r for r in raw_data if str(r.get("weekDay")) == "0" or "Day" in str(r.get("day", ""))), None)
        if not header_row: header_row = raw_data[0]
        
        period_keys = [k for k in header_row.keys() if str(k).isdigit()]
        period_keys.sort(key=int)

        html = f"<html><head><style>{get_base_css()}" + """
        .table-container { overflow: hidden; border-radius: 20px; background: rgba(15, 23, 42, 0.5); border: 1px solid rgba(255,255,255,0.05); padding: 15px; margin-top: 20px;}
        table { width: 100%; border-collapse: separate; border-spacing: 6px; }
        th { color: #c084fc; text-transform: uppercase; font-size: 0.85em; padding: 12px 5px; background: rgba(0,0,0,0.4); border-radius: 10px; text-align: center; font-weight: 800; letter-spacing: 1px;}
        td { background: rgba(30, 41, 59, 0.6); padding: 10px; border-radius: 10px; text-align: center; vertical-align: middle; box-shadow: inset 0 0 0 1px rgba(255,255,255,0.02);}
        
        .day-col { font-weight: 800; color: #f8fafc; font-size: 0.95em; background: rgba(192, 132, 252, 0.1); border: 1px solid rgba(192, 132, 252, 0.2); white-space: nowrap; width: 60px;}
        
        .cell-sub { font-weight: 700; color: #e2e8f0; font-size: 0.85em; margin-bottom: 4px; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; line-height: 1.2;}
        .cell-fac { font-size: 0.7em; color: #94a3b8; font-weight: 500; margin-bottom: 2px;}
        .cell-room { font-size: 0.7em; color: #38bdf8; font-weight: 600; background: rgba(56,189,248,0.1); display: inline-block; padding: 2px 6px; border-radius: 4px; border: 1px solid rgba(56,189,248,0.2);}
        .empty-cell { color: #334155; font-style: italic; font-size: 1.2em;}
        </style></head><body><div class="card"><h1>🗓️ Live Timetable</h1><div class="table-container"><table>
        """

        html += "<tr><th>DAY</th>"
        for pk in period_keys:
            time_val = header_row.get(pk, f"Period {pk}")
            html += f"<th>{time_val}</th>"
        html += "</tr>"

        def parse_cell_data(cell_val):
            if isinstance(cell_val, (int, str)) and str(cell_val) in abbr_map:
                cell_val = abbr_map[str(cell_val)]

            if isinstance(cell_val, dict):
                sub_data = cell_val.get("subject")
                sub = sub_data.get("subjectCode") if isinstance(sub_data, dict) else sub_data if isinstance(sub_data, str) else None
                if not sub: sub = cell_val.get("subjectCode")
                
                fac_data = cell_val.get("faculty")
                fac = (fac_data.get("employeeName") or fac_data.get("firstName")) if isinstance(fac_data, dict) else fac_data if isinstance(fac_data, str) else None
                if not fac: fac = cell_val.get("facultyName")
                
                room_data = cell_val.get("room")
                room = room_data.get("roomNo") if isinstance(room_data, dict) else room_data if isinstance(room_data, str) else None
                if not room: room = cell_val.get("roomNo")
                
                return str(sub or ""), str(fac or ""), str(room or "")
            
            return str(cell_val or ""), "", ""

        for row in raw_data:
            if str(row.get("weekDay")) == "0" or "Day" in str(row.get("day", "")): continue
            if str(row.get("isActive", True)).lower() == "false": continue
            
            day_name = str(row.get("day", "N/A")).upper()
            html += f"<tr><td class='day-col'>{day_name}</td>"
            
            for pk in period_keys:
                cell = row.get(pk)
                cell_html = "<div class='empty-cell'>-</div>"
                
                if cell:
                    if isinstance(cell, list):
                        cell_html = ""
                        for item in cell:
                            sub, fac, room = parse_cell_data(item)
                            if sub or fac:
                                cell_html += f"<div style='margin-bottom: 6px; border-bottom: 1px solid rgba(255,255,255,0.05); padding-bottom: 4px;'><div class='cell-sub'>{sub}</div>"
                                if fac: cell_html += f"<div class='cell-fac'>{fac}</div>"
                                if room: cell_html += f"<div class='cell-room'>📍 {room}</div>"
                                cell_html += "</div>"
                    else:
                        sub, fac, room = parse_cell_data(cell)
                        if sub or fac:
                            cell_html = f"<div class='cell-sub'>{sub}</div>"
                            if fac: cell_html += f"<div class='cell-fac'>{fac}</div>"
                            if room: cell_html += f"<div class='cell-room'>📍 {room}</div>"
                        else:
                            val = str(cell).strip()
                            if val and val != "None":
                                cell_html = f"<div class='cell-sub'>{val}</div>"

                html += f"<td>{cell_html}</td>"
            html += "</tr>"

        html += f"</table></div><div class='watermark'>{TEXTS.get('watermark', '')}</div></div></body></html>"
        
        return await take_screenshot(html, ".card", progress_cb)
    except Exception as e:
        print(f"Timetable Render Error: {e}")
        return None

async def take_screenshot(html, selector, progress_cb=None):
    page = await GLOBAL_BROWSER.new_page()
    await page.set_content(html, wait_until="domcontentloaded") 
    
    if progress_cb: asyncio.create_task(progress_cb(95, TEXTS.get("prog_snap", "")))
    
    element = await page.query_selector(selector)
    img = await element.screenshot() if element else await page.screenshot(full_page=True)
    await page.close()
    return img


# --- AIOHTTP ADMIN WEB SERVER LOGIC ---

@web.middleware
async def auth_middleware(request, handler):
    # Allow rendering the main HTML page
    if request.path == '/':
        return await handler(request)
        
    # Protect API routes
    if request.path.startswith('/api/'):
        auth_header = request.headers.get("Authorization", "")
        if auth_header != f"Bearer {ADMIN_PASSWORD}":
            return web.json_response({"error": "Unauthorized"}, status=401)
    
    return await handler(request)

async def serve_admin_panel(request):
    return web.FileResponse('admin.html')

async def api_get_stats(request):
    return web.json_response({"users": len(USERS)})

async def api_get_texts(request):
    return web.json_response(TEXTS)

async def api_update_texts(request):
    global TEXTS
    new_data = await request.json()
    TEXTS.update(new_data)
    save_texts(TEXTS)
    return web.json_response({"success": True})

async def api_send_announcement(request):
    data = await request.json()
    raw_msg = data.get("message", "")
    success_count = 0
    
    if raw_msg and GLOBAL_APP:
        for uid, user_data in USERS.items():
            try:
                # Safely format the message with individual user data 
                # using .replace to avoid KeyError if `{unknown_var}` is typed
                formatted_msg = raw_msg\
                    .replace("{name}", user_data.get("name", "Student"))\
                    .replace("{email}", user_data.get("email", "Unknown"))\
                    .replace("{rollNo}", user_data.get("rollNo", "N/A"))\
                    .replace("{course}", user_data.get("course", "N/A"))

                await GLOBAL_APP.bot.send_message(chat_id=uid, text=formatted_msg, parse_mode="HTML")
                success_count += 1
            except Exception as e:
                print(f"Failed to send broadcast to {uid}: {e}")
                
    return web.json_response({"success": True, "sent": success_count})

async def start_web_server():
    app = web.Application(middlewares=[auth_middleware])
    app.router.add_get('/', serve_admin_panel)
    app.router.add_get('/api/stats', api_get_stats)
    app.router.add_get('/api/texts', api_get_texts)
    app.router.add_post('/api/texts', api_update_texts)
    app.router.add_post('/api/announce', api_send_announcement)
    
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', WEB_PORT)
    await site.start()
    print(f"🌐 Admin Panel running on: http://localhost:{WEB_PORT}")


# --- TELEGRAM HANDLERS ---

def generate_progress_bar(percent, text):
    bar_length = 15
    filled = int((percent / 100) * bar_length)
    bar = "█" * filled + "▒" * (bar_length - filled)
    return f"⚡ <b>Processing...</b>\n<code>[{bar}] {percent}%</code>\n<i>{text}</i>"

async def show_main_menu(update: Update):
    user_id = str(update.effective_user.id)
    name = USERS.get(user_id, {}).get("name", "Student")
    
    keyboard = [
        [InlineKeyboardButton(TEXTS.get("btn_profile", ""), callback_data='menu_profile'),
         InlineKeyboardButton(TEXTS.get("btn_timetable", ""), callback_data='menu_timetable')],
        [InlineKeyboardButton(TEXTS.get("btn_perc", ""), callback_data='menu_perc')],
        [InlineKeyboardButton(TEXTS.get("btn_sub", ""), callback_data='menu_sub_list')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Safely replace format string in case admins alter the text format
    text = TEXTS.get("menu_greeting", "").replace("{name}", name)
    
    if update.message:
        await update.message.reply_text(text, reply_markup=reply_markup, parse_mode="HTML")
    elif update.callback_query:
        await update.callback_query.message.edit_text(text, reply_markup=reply_markup, parse_mode="HTML")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    if user_id in USERS:
        await show_main_menu(update)
    else:
        USER_STATES[user_id] = {"state": "WAITING_EMAIL"}
        await update.message.reply_text(TEXTS.get("start_new_user", ""), parse_mode="HTML")

async def logout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    if user_id in USERS:
        del USERS[user_id]
        save_users(USERS)
        await update.message.reply_text(TEXTS.get("logout_success", ""), parse_mode="HTML")
    else:
        await update.message.reply_text(TEXTS.get("not_logged_in", ""), parse_mode="HTML")

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    text = update.message.text.strip()
    
    if user_id in USER_STATES:
        state = USER_STATES[user_id].get("state")
        
        if state == "WAITING_EMAIL":
            USER_STATES[user_id]["email"] = text
            USER_STATES[user_id]["state"] = "WAITING_PASSWORD"
            await update.message.reply_text(TEXTS.get("prompt_password", ""), parse_mode="HTML")
        elif state == "WAITING_PASSWORD":
            email = USER_STATES[user_id]["email"]
            password = text
            
            loading_msg = await update.message.reply_text(TEXTS.get("login_verifying", ""), parse_mode="HTML")
            USERS[user_id] = {"email": email, "password": password, "name": "Student"}
            
            profile_data = await fetch_profile_data(user_id, email, password)
            
            if profile_data:
                d = profile_data.get("data", {})
                first_name = d.get("firstName", "Student").title()
                
                # --- NEW: Extracting extra data for the Web Panel Variables ---
                roll_no = d.get("rollNo", "N/A")
                course_nick = d.get("course", {}).get("courseNickName", "N/A")
                if "branch" in d and d["branch"]:
                     branch_nick = d.get("branch", {}).get("branchNickName", "")
                     if branch_nick:
                         course_nick += f" ({branch_nick})"

                USERS[user_id]["name"] = first_name
                USERS[user_id]["rollNo"] = roll_no
                USERS[user_id]["course"] = course_nick
                # --------------------------------------------------------------
                
                save_users(USERS)
                del USER_STATES[user_id]
                
                await loading_msg.delete()
                await update.message.reply_text(TEXTS.get("login_success", ""), parse_mode="HTML")
                await show_main_menu(update)
            else:
                del USERS[user_id]
                del USER_STATES[user_id]
                await loading_msg.edit_text(TEXTS.get("login_failed", ""), parse_mode="HTML")
    else:
        if user_id not in USERS:
            await update.message.reply_text(TEXTS.get("please_start", ""), parse_mode="HTML")
        else:
            await update.message.reply_text(TEXTS.get("invalid_input", ""), parse_mode="HTML")

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = str(query.from_user.id)
    await query.answer()

    if user_id not in USERS:
        await query.message.edit_text(TEXTS.get("session_expired", ""), parse_mode="HTML")
        return

    email = USERS[user_id]["email"]
    password = USERS[user_id]["password"]

    async def update_progress(percent, text):
        try:
            await query.edit_message_text(generate_progress_bar(percent, text), parse_mode="HTML")
        except Exception: 
            pass 

    if query.data == 'menu_profile':
        start_time = time.time()
        asyncio.create_task(update_progress(5, TEXTS.get("prog_init", "")))
        profile_data = await fetch_profile_data(user_id, email, password, progress_cb=update_progress)
        
        if profile_data:
            d = profile_data.get("data", {})
            course = d.get("course", {}).get("courseNickName", "N/A")
            branch = d.get("branch", {}).get("branchNickName", "N/A")
            elapsed = round(time.time() - start_time, 1)
            
            prof_msg = (
                f"👤 <b>STUDENT PROFILE</b>\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"📛 <b>Name:</b> {d.get('fullName', 'N/A')}\n"
                f"🎓 <b>Course:</b> {course} ({branch})\n"
                f"🔢 <b>Roll No:</b> {d.get('rollNo', 'N/A')}\n"
                f"🆔 <b>Student ID:</b> {d.get('studentId', 'N/A')}\n"
                f"📅 <b>Session:</b> {d.get('currentSession', 'N/A')} (Yr {d.get('currentYear', '-')}, Sem {d.get('currentSemester', '-')})\n"
                f"📧 <b>Email:</b> {d.get('email', 'N/A')}\n"
                f"📱 <b>Mobile:</b> {d.get('mobile', 'N/A')}\n"
                f"🏠 <b>Address:</b> {d.get('localAddressLine1', 'N/A')}\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"⏱️ <i>Loaded in {elapsed}s</i>"
            )
            await query.message.reply_text(prof_msg, parse_mode="HTML")
            try: await query.message.delete()
            except: pass
        else:
            await query.edit_message_text(TEXTS.get("err_profile", ""), parse_mode="HTML")
            
    elif query.data == 'menu_timetable':
        start_time = time.time()
        asyncio.create_task(update_progress(5, TEXTS.get("prog_init", "")))
        
        data = await fetch_timetable_data(user_id, email, password, progress_cb=update_progress)
        img = await render_timetable_image(data, progress_cb=update_progress)
        
        if img:
            elapsed = round(time.time() - start_time, 1)
            
            # Use replace for safety against custom text edits
            caption_text = TEXTS.get("caption_timetable", "").replace("{elapsed}", str(elapsed))
            await query.message.reply_photo(photo=img, caption=caption_text, parse_mode="HTML")
            try: await query.message.delete()
            except: pass
        else:
            await query.edit_message_text(TEXTS.get("err_fetch", ""), parse_mode="HTML")

    elif query.data == 'menu_perc':
        start_time = time.time()
        asyncio.create_task(update_progress(5, TEXTS.get("prog_init", "")))
        data = await fetch_erp_data(user_id, email, password, progress_cb=update_progress)
        img = await render_summary_image(data, progress_cb=update_progress)
        
        if img:
            elapsed = round(time.time() - start_time, 1)
            caption_text = TEXTS.get("caption_summary", "").replace("{elapsed}", str(elapsed))
            await query.message.reply_photo(photo=img, caption=caption_text, parse_mode="HTML")
            try: await query.message.delete()
            except: pass
        else:
            await query.edit_message_text(TEXTS.get("err_fetch", ""), parse_mode="HTML")

    elif query.data == 'menu_sub_list':
        keyboard = [
            [InlineKeyboardButton("January", callback_data='month_1'), InlineKeyboardButton("February", callback_data='month_2')],
            [InlineKeyboardButton("March", callback_data='month_3'), InlineKeyboardButton("April", callback_data='month_4')],
            [InlineKeyboardButton("May", callback_data='month_5'), InlineKeyboardButton("June", callback_data='month_6')],
            [InlineKeyboardButton("July", callback_data='month_7'), InlineKeyboardButton("August", callback_data='month_8')],
            [InlineKeyboardButton("September", callback_data='month_9'), InlineKeyboardButton("October", callback_data='month_10')],
            [InlineKeyboardButton("November", callback_data='month_11'), InlineKeyboardButton("December", callback_data='month_12')]
        ]
        await query.edit_message_text(TEXTS.get("select_month", ""), reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")

    elif query.data.startswith('month_'):
        month_idx = query.data.split('_')[1]
        start_time = time.time()
        asyncio.create_task(update_progress(5, TEXTS.get("prog_init", "")))
        
        data = await fetch_erp_data(user_id, email, password, month=month_idx, progress_cb=update_progress)
        img = await render_subjectwise_image(data, progress_cb=update_progress)
        
        if img:
            elapsed = round(time.time() - start_time, 1)
            caption_text = TEXTS.get("caption_detailed", "").replace("{month}", str(month_idx)).replace("{elapsed}", str(elapsed))
            
            await query.message.reply_photo(photo=img, caption=caption_text, parse_mode="HTML")
            try: await query.message.delete()
            except: pass
        else:
            await query.edit_message_text(TEXTS.get("err_no_data", ""), parse_mode="HTML")

async def post_init(application):
    global GLOBAL_PW, GLOBAL_BROWSER, GLOBAL_APP
    GLOBAL_APP = application
    print("🚀 Initializing Playwright Global Engine...")
    GLOBAL_PW = await async_playwright().start()
    GLOBAL_BROWSER = await GLOBAL_PW.chromium.launch(headless=True)
    print("✅ Playwright Ready!")

    # Start the integrated web server gracefully behind the scenes
    asyncio.create_task(start_web_server())

    await application.bot.set_my_commands([
        BotCommand("start", "Open the main menu"),
        BotCommand("attendance", "Check your attendance"),
        BotCommand("logout", "Log out of your ERP account")
    ])

if __name__ == '__main__':
    app = ApplicationBuilder().token(BOT_TOKEN).post_init(post_init).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("attendance", start))
    app.add_handler(CommandHandler("logout", logout))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(CallbackQueryHandler(button_handler))
    
    print("🤖 ERP Premium UI Bot + Web Admin is running...")
    app.run_polling()