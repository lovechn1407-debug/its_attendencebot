import os
import io
import urllib.request
from PIL import Image, ImageDraw, ImageFont
from datetime import datetime

# Download fonts to /tmp if on Vercel
FONT_DIR = "/tmp" if os.environ.get("VERCEL") else "."
REGULAR_FONT = os.path.join(FONT_DIR, "Roboto-Regular.ttf")
BOLD_FONT = os.path.join(FONT_DIR, "Roboto-Bold.ttf")

def ensure_fonts():
    if not os.path.exists(REGULAR_FONT):
        print("Downloading Regular Font...")
        urllib.request.urlretrieve("https://github.com/googlefonts/roboto/raw/main/src/hinted/Roboto-Regular.ttf", REGULAR_FONT)
    if not os.path.exists(BOLD_FONT):
        print("Downloading Bold Font...")
        urllib.request.urlretrieve("https://github.com/googlefonts/roboto/raw/main/src/hinted/Roboto-Bold.ttf", BOLD_FONT)

# Colors
BG_COLOR = "#09090b"
CARD_BG = "#18181b"
TEXT_COLOR = "#f8fafc"
MUTED_TEXT = "#94a3b8"
ACCENT_BLUE = "#38bdf8"
ACCENT_GREEN = "#10b981"
ACCENT_YELLOW = "#f59e0b"
ACCENT_RED = "#ef4444"

def get_font(size, bold=False):
    ensure_fonts()
    try:
        return ImageFont.truetype(BOLD_FONT if bold else REGULAR_FONT, size)
    except Exception:
        return ImageFont.load_default()

def draw_rounded_rect(draw, xy, radius, fill):
    x1, y1, x2, y2 = xy
    draw.rectangle([x1, y1+radius, x2, y2-radius], fill=fill)
    draw.rectangle([x1+radius, y1, x2-radius, y2], fill=fill)
    draw.pieslice([x1, y1, x1+radius*2, y1+radius*2], 180, 270, fill=fill)
    draw.pieslice([x2-radius*2, y1, x2, y1+radius*2], 270, 360, fill=fill)
    draw.pieslice([x1, y2-radius*2, x1+radius*2, y2], 90, 180, fill=fill)
    draw.pieslice([x2-radius*2, y2-radius*2, x2, y2], 0, 90, fill=fill)

def render_summary_image(data):
    if not data or not data.get("summary"): return None
    subjects = data["summary"].get("data", [])
    
    width = 800
    row_height = 90
    padding = 40
    title_height = 100
    height = title_height + (len(subjects) * row_height) + padding
    
    img = Image.new("RGB", (width, height), BG_COLOR)
    draw = ImageDraw.Draw(img)
    
    # Title
    font_title = get_font(36, bold=True)
    draw.text((padding, padding), "📊 Attendance Overview", font=font_title, fill=ACCENT_BLUE)
    
    font_sub = get_font(18, bold=True)
    font_perc = get_font(20, bold=True)
    
    y = title_height + 20
    for item in subjects:
        name = item.get("subjectName", "")
        if len(name) > 40: name = name[:37] + "..."
        perc = item.get("subjectTotalPercentage", 0)
        
        # Color logic
        color = ACCENT_GREEN if perc >= 75 else ACCENT_YELLOW if perc >= 60 else ACCENT_RED
        if "ALL SUBJECTS" in name: 
            color = ACCENT_BLUE
            
        # Draw text
        draw.text((padding, y), name, font=font_sub, fill=TEXT_COLOR)
        
        # Draw percentage right aligned
        perc_text = f"{perc}%"
        perc_bbox = draw.textbbox((0,0), perc_text, font=font_perc)
        draw.text((width - padding - (perc_bbox[2]-perc_bbox[0]), y), perc_text, font=font_perc, fill=color)
        
        # Draw Progress Bar Background
        bar_y = y + 30
        draw_rounded_rect(draw, [padding, bar_y, width - padding, bar_y + 14], 7, "#1e293b")
        
        # Draw Progress Bar Fill
        fill_width = int((width - 2*padding) * (perc / 100))
        if fill_width > 10:
            draw_rounded_rect(draw, [padding, bar_y, padding + fill_width, bar_y + 14], 7, color)
            
        y += row_height
        
    bio = io.BytesIO()
    img.save(bio, "PNG")
    bio.seek(0)
    return bio

def render_timetable_image(data):
    if not data or not data.get("success"): return None
    raw_data = data.get("data", [])
    if not raw_data: return None
    
    abbr_map = {str(a.get("SN")): a for a in data.get("abbreviations", [])}
    
    # Pre-parse grid
    # 6 days, 8 periods
    days = ["MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY", "FRIDAY", "SATURDAY"]
    periods = [str(x) for x in range(1, 9)]
    
    cell_w = 120
    cell_h = 80
    pad = 40
    title_h = 80
    header_w = 100
    
    total_w = pad*2 + header_w + (len(periods) * cell_w)
    total_h = pad*2 + title_h + (len(days) * cell_h)
    
    img = Image.new("RGB", (total_w, total_h), BG_COLOR)
    draw = ImageDraw.Draw(img)
    
    font_title = get_font(32, bold=True)
    font_day = get_font(16, bold=True)
    font_cell = get_font(12, bold=True)
    font_room = get_font(10, bold=False)
    
    draw.text((pad, pad), "🗓️ Live Timetable", font=font_title, fill="#c084fc")
    
    # Draw Headers P1-P8
    for i, p in enumerate(periods):
        x = pad + header_w + (i * cell_w)
        draw_rounded_rect(draw, [x+2, pad+title_h-30, x+cell_w-2, pad+title_h-5], 5, "#1e1b4b")
        draw.text((x + 35, pad+title_h-25), f"Period {p}", font=font_cell, fill="#c084fc")

    y_offset = pad + title_h
    for i, day in enumerate(days):
        y = y_offset + (i * cell_h)
        # Draw Day Header
        draw_rounded_rect(draw, [pad, y+2, pad+header_w-5, y+cell_h-2], 8, "#1e1b4b")
        draw.text((pad + 10, y + 30), day[:3], font=font_day, fill="#f8fafc")
        
        # Find row in data
        row_data = next((r for r in raw_data if str(r.get("day", "")).upper() == day), {})
        
        for j, p in enumerate(periods):
            x = pad + header_w + (j * cell_w)
            draw_rounded_rect(draw, [x+2, y+2, x+cell_w-2, y+cell_h-2], 8, CARD_BG)
            
            cell = row_data.get(p)
            if cell:
                if isinstance(cell, list) and cell: cell = cell[0]
                if isinstance(cell, (int, str)) and str(cell) in abbr_map: cell = abbr_map[str(cell)]
                
                if isinstance(cell, dict):
                    sub = cell.get("subjectCode", "")
                    if len(sub) > 15: sub = sub[:12]+".."
                    room = cell.get("roomNo", "")
                    
                    draw.text((x + 10, y + 20), sub, font=font_cell, fill=TEXT_COLOR)
                    if room:
                        draw.text((x + 10, y + 45), f"📍 {room}", font=font_room, fill=ACCENT_BLUE)

    bio = io.BytesIO()
    img.save(bio, "PNG")
    bio.seek(0)
    return bio

def render_subjectwise_image(data, month_idx):
    if not data or not data.get("detailed"): return None
    detailed = data.get("detailed", {})
    days = detailed.get("data", [])
    if not days: return None
    
    subject_map = {item.get("subjectCode"): item.get("subjectName") for item in data.get("summary", {}).get("data", [])}
    
    pad = 40
    title_h = 100
    col_w = [120, 150, 150, 150, 150] # Date, P1, P2, P3, P4
    row_h = 60
    
    total_w = pad*2 + sum(col_w)
    total_h = pad*2 + title_h + (len(days[:15]) * row_h) + 100 # limit 15 days for sanity
    
    img = Image.new("RGB", (total_w, total_h), BG_COLOR)
    draw = ImageDraw.Draw(img)
    
    font_title = get_font(32, bold=True)
    font_head = get_font(14, bold=True)
    font_date = get_font(14, bold=True)
    font_sub = get_font(12, bold=True)
    font_stat = get_font(24, bold=True)
    
    draw.text((pad, pad), f"📅 Month {month_idx} Details", font=font_title, fill=ACCENT_BLUE)
    
    # Table Headers
    x_offset = pad
    headers = ["Date", "Period 1", "Period 2", "Period 3", "Period 4"]
    for i, h in enumerate(headers):
        draw.text((x_offset + 10, pad + title_h - 30), h, font=font_head, fill=ACCENT_BLUE)
        x_offset += col_w[i]
        
    y_offset = pad + title_h
    for i, day in enumerate(days[:15]):
        y = y_offset + (i * row_h)
        date_str = day.get("attendanceDate", "").split("T")[0][-5:] # MM-DD
        
        draw_rounded_rect(draw, [pad, y+2, pad+col_w[0]-5, y+row_h-2], 8, "#0f172a")
        draw.text((pad + 20, y + 20), date_str, font=font_date, fill=TEXT_COLOR)
        
        lecs = day.get("attendances", [])
        x = pad + col_w[0]
        
        for j in range(4):
            draw_rounded_rect(draw, [x+2, y+2, x+col_w[j+1]-2, y+row_h-2], 8, CARD_BG)
            if j < len(lecs):
                lec = lecs[j]
                sub = lec.get("subjectCode", "NA")
                if len(sub) > 15: sub = sub[:13]+".."
                stat = lec.get("status", "-")
                
                color = ACCENT_GREEN if stat == "P" else ACCENT_RED if stat == "A" else MUTED_TEXT
                draw.text((x + 10, y + 15), sub, font=font_sub, fill=TEXT_COLOR)
                draw.text((x + 10, y + 35), stat, font=font_head, fill=color)
            else:
                draw.text((x + 20, y + 20), "-", font=font_head, fill=MUTED_TEXT)
            x += col_w[j+1]

    # Stats footer
    footer_y = total_h - pad - 60
    draw_rounded_rect(draw, [pad, footer_y, total_w-pad, footer_y+60], 10, CARD_BG)
    draw.text((pad + 50, footer_y + 15), f"Present: {detailed.get('presentDays', 0)}", font=font_stat, fill=ACCENT_GREEN)
    draw.text((pad + 300, footer_y + 15), f"Absent: {detailed.get('absentDays', 0)}", font=font_stat, fill=ACCENT_RED)
    
    bio = io.BytesIO()
    img.save(bio, "PNG")
    bio.seek(0)
    return bio
