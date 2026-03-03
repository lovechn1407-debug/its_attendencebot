import os
import io
import urllib.request
from PIL import Image, ImageDraw, ImageFont
from datetime import datetime

FONT_DIR = "/tmp" if os.environ.get("VERCEL") else "."
REGULAR_FONT = os.path.join(FONT_DIR, "Roboto-Regular.ttf")
BOLD_FONT = os.path.join(FONT_DIR, "Roboto-Bold.ttf")

def ensure_fonts():
    if not os.path.exists(REGULAR_FONT):
        urllib.request.urlretrieve("https://github.com/googlefonts/roboto/raw/main/src/hinted/Roboto-Regular.ttf", REGULAR_FONT)
    if not os.path.exists(BOLD_FONT):
        urllib.request.urlretrieve("https://github.com/googlefonts/roboto/raw/main/src/hinted/Roboto-Bold.ttf", BOLD_FONT)

# Premium Color Palette
BG_COLOR = "#0f172a"          # Slate 900
CARD_BG = "#1e293b"           # Slate 800
CARD_BORDER = "#334155"       # Slate 700
TEXT_MAIN = "#f8fafc"         # Slate 50
TEXT_MUTED = "#cbd5e1"        # Slate 300
ACCENT_BLUE = "#38bdf8"       # Sky 400
ACCENT_GREEN = "#10b981"      # Emerald 500
ACCENT_GREEN_BG = "#064e3b"   # Emerald 900
ACCENT_YELLOW = "#f59e0b"     # Amber 500
ACCENT_RED = "#ef4444"        # Red 500
ACCENT_RED_BG = "#7f1d1d"     # Red 900
ACCENT_PURPLE = "#c084fc"     # Purple 400
COPYRIGHT_TEXT = "© AS Studios | Love Chauhan CSE DS"

def get_font(size, bold=False):
    ensure_fonts()
    try:
        return ImageFont.truetype(BOLD_FONT if bold else REGULAR_FONT, size)
    except Exception:
        return ImageFont.load_default()

def draw_rounded_rect(draw, xy, radius, fill, outline=None, width=1):
    x1, y1, x2, y2 = xy
    draw.rounded_rectangle(xy, radius=radius, fill=fill, outline=outline, width=width)

def add_watermark(draw, width, height):
    font_wm = get_font(14, bold=False)
    wm_bbox = draw.textbbox((0,0), COPYRIGHT_TEXT, font=font_wm)
    wm_w = wm_bbox[2] - wm_bbox[0]
    draw.text(((width - wm_w) / 2, height - 35), COPYRIGHT_TEXT, font=font_wm, fill=CARD_BORDER)

def render_summary_image(data):
    if not data or not data.get("summary"): return None
    subjects = data["summary"].get("data", [])
    
    width = 900
    row_height = 100
    padding = 50
    title_height = 120
    footer_height = 60
    
    # Calculate grid layout
    cols = 2
    rows = (len(subjects) + cols - 1) // cols
    total_grids_height = rows * row_height
    
    height = title_height + total_grids_height + footer_height
    img = Image.new("RGB", (width, height), BG_COLOR)
    draw = ImageDraw.Draw(img)
    
    # Title
    font_title = get_font(42, bold=True)
    draw.text((padding, padding), "📊 Attendance Overview", font=font_title, fill=ACCENT_BLUE)
    
    font_sub = get_font(18, bold=True)
    font_perc = get_font(24, bold=True)
    
    y = title_height
    x_gap = 30
    col_width = (width - (2 * padding) - x_gap) // 2
    
    # Overalls first or last
    has_overall = next((s for s in subjects if "ALL SUBJECTS" in s.get("subjectName", "")), None)
    if has_overall:
        subjects.remove(has_overall)
        subjects.append(has_overall) # move to end

    for idx, item in enumerate(subjects):
        col = idx % cols
        row = idx // cols
        
        box_x1 = padding + col * (col_width + x_gap)
        box_y1 = y + row * row_height
        box_x2 = box_x1 + col_width
        box_y2 = box_y1 + 80
        
        name = item.get("subjectName", "")
        if len(name) > 35: name = name[:32] + "..."
        perc = item.get("subjectTotalPercentage", 0)
        
        is_total = "ALL SUBJECTS" in name
        
        color = ACCENT_GREEN if perc >= 75 else ACCENT_YELLOW if perc >= 60 else ACCENT_RED
        if is_total: color = ACCENT_BLUE

        # Draw Subject Card Background
        bg_fill = "#1e1b4b" if is_total else CARD_BG
        border_col = ACCENT_BLUE if is_total else CARD_BORDER
        draw_rounded_rect(draw, [box_x1, box_y1, box_x2, box_y2], 12, fill=bg_fill, outline=border_col, width=2)
        
        # Draw Text
        draw.text((box_x1 + 20, box_y1 + 15), name, font=font_sub, fill=TEXT_MAIN)
        
        # Percentage Value
        perc_text = f"{perc}%"
        perc_bbox = draw.textbbox((0,0), perc_text, font=font_perc)
        draw.text((box_x2 - 20 - (perc_bbox[2]-perc_bbox[0]), box_y1 + 12), perc_text, font=font_perc, fill=color)
        
        # Progress Bar Bar Background
        bar_y = box_y1 + 50
        draw_rounded_rect(draw, [box_x1 + 20, bar_y, box_x2 - 20, bar_y + 10], 5, "#0f172a")
        
        # Progress Bar Bar Fill
        fill_width = int((col_width - 40) * (perc / 100))
        if fill_width > 10:
            draw_rounded_rect(draw, [box_x1 + 20, bar_y, box_x1 + 20 + fill_width, bar_y + 10], 5, color)
            
    add_watermark(draw, width, height)
    bio = io.BytesIO()
    img.save(bio, "PNG")
    bio.seek(0)
    return bio

def render_timetable_image(data):
    if not data or not data.get("success"): return None
    raw_data = data.get("data", [])
    if not raw_data: return None
    
    abbr_map = {str(a.get("SN")): a for a in data.get("abbreviations", [])}
    
    days = ["MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY", "FRIDAY", "SATURDAY"]
    periods = [str(x) for x in range(1, 9)]
    
    cell_w = 130
    cell_h = 85
    pad = 50
    title_h = 100
    header_w = 110
    
    total_w = pad*2 + header_w + (len(periods) * cell_w)
    total_h = pad*2 + title_h + (len(days) * cell_h) + 40
    
    img = Image.new("RGB", (total_w, total_h), BG_COLOR)
    draw = ImageDraw.Draw(img)
    
    font_title = get_font(42, bold=True)
    font_day = get_font(18, bold=True)
    font_cell = get_font(13, bold=True)
    font_room = get_font(11, bold=False)
    
    draw.text((pad, pad), "🗓️ Live Timetable", font=font_title, fill=ACCENT_PURPLE)
    
    for i, p in enumerate(periods):
        x = pad + header_w + (i * cell_w)
        draw_rounded_rect(draw, [x+4, pad+title_h-40, x+cell_w-4, pad+title_h-10], 8, fill="#1e1b4b", outline=ACCENT_PURPLE, width=1)
        draw.text((x + 35, pad+title_h-33), f"Period {p}", font=font_cell, fill=ACCENT_PURPLE)

    y_offset = pad + title_h
    for i, day in enumerate(days):
        y = y_offset + (i * cell_h)
        draw_rounded_rect(draw, [pad, y+4, pad+header_w-6, y+cell_h-4], 10, fill="#1e1b4b", outline=ACCENT_PURPLE, width=1)
        draw.text((pad + 15, y + 33), day[:3], font=font_day, fill=TEXT_MAIN)
        
        row_data = next((r for r in raw_data if str(r.get("day", "")).upper() == day), {})
        
        for j, p in enumerate(periods):
            x = pad + header_w + (j * cell_w)
            draw_rounded_rect(draw, [x+4, y+4, x+cell_w-4, y+cell_h-4], 10, fill=CARD_BG, outline=CARD_BORDER, width=1)
            
            cell = row_data.get(p)
            if cell:
                if isinstance(cell, list) and cell: cell = cell[0]
                if isinstance(cell, (int, str)) and str(cell) in abbr_map: cell = abbr_map[str(cell)]
                
                if isinstance(cell, dict):
                    sub = cell.get("subjectCode", "")
                    if len(sub) > 15: sub = sub[:12]+".."
                    room = cell.get("roomNo", "")
                    
                    draw.text((x + 12, y + 22), sub, font=font_cell, fill=TEXT_MAIN)
                    if room:
                        draw.text((x + 12, y + 48), f"📍 {room}", font=font_room, fill=ACCENT_BLUE)

    add_watermark(draw, total_w, total_h)
    bio = io.BytesIO()
    img.save(bio, "PNG")
    bio.seek(0)
    return bio

def render_subjectwise_image(data, month_idx):
    if not data or not data.get("detailed"): return None
    detailed = data.get("detailed", {})
    days = detailed.get("data", [])
    if not days: return None
    
    pad = 50
    title_h = 130
    
    # Updated logic: now 1 date column + 8 period columns + 1 LUNCH separator
    # Date (120), P1-P4 (90x4), LUNCH (40), P5-P8 (90x4)
    col_widths = [120, 90, 90, 90, 90, 40, 90, 90, 90, 90]
    row_h = 55
    
    total_w = pad*2 + sum(col_widths)
    # limit to 15 days max
    days_to_draw = days[:15]
    total_h = pad*2 + title_h + (len(days_to_draw) * row_h) + 120 
    
    img = Image.new("RGB", (total_w, total_h), BG_COLOR)
    draw = ImageDraw.Draw(img)
    
    font_title = get_font(42, bold=True)
    font_head = get_font(13, bold=True)
    font_date = get_font(15, bold=True)
    font_sub = get_font(10, bold=True)
    font_lunch = get_font(16, bold=True)
    font_stat = get_font(28, bold=True)
    font_stat_sub = get_font(14, bold=False)
    
    mn_name = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]
    m_str = mn_name[int(month_idx)-1] if 1 <= int(month_idx) <= 12 else month_idx
    draw.text((pad, pad), f"📅 Master Timeline : {m_str}", font=font_title, fill=ACCENT_BLUE)
    
    # Table Headers
    x_offset = pad
    headers = ["DATE", "P1", "P2", "P3", "P4", "☕", "P5", "P6", "P7", "P8"]
    for i, h in enumerate(headers):
        align_x = x_offset + (col_widths[i] // 2) - 10
        draw.text((align_x, pad + title_h - 40), h, font=font_head, fill=TEXT_MUTED)
        x_offset += col_widths[i]
        
    y_offset = pad + title_h
    
    # Lunch Column Background
    lunch_x1 = pad + sum(col_widths[:5])
    draw_rounded_rect(draw, [lunch_x1+2, y_offset, lunch_x1+col_widths[5]-2, y_offset + (len(days_to_draw)*row_h)], 10, fill="#1e1b4b", outline=ACCENT_YELLOW, width=1)
    
    for i, day in enumerate(days_to_draw):
        y = y_offset + (i * row_h)
        date_str = day.get("attendanceDate", "").split("T")[0][-5:] # MM-DD
        
        # Date Box
        draw_rounded_rect(draw, [pad, y+3, pad+col_widths[0]-5, y+row_h-3], 8, fill=CARD_BG, outline=ACCENT_BLUE, width=1)
        draw.text((pad + 30, y + 18), date_str, font=font_date, fill=TEXT_MAIN)
        
        lecs = day.get("attendances", [])
        
        # Draw Periods 1-4
        x = pad + col_widths[0]
        for j in range(4):
            draw_rounded_rect(draw, [x+3, y+3, x+col_widths[j+1]-3, y+row_h-3], 6, fill=CARD_BG, outline=CARD_BORDER, width=1)
            
            if j < len(lecs):
                lec = lecs[j]
                stat = lec.get("status", "-")
                color = ACCENT_GREEN if stat == "P" else ACCENT_RED if stat == "A" else TEXT_MUTED
                bg = ACCENT_GREEN_BG if stat == "P" else ACCENT_RED_BG if stat == "A" else CARD_BG
                
                draw_rounded_rect(draw, [x+3, y+3, x+col_widths[j+1]-3, y+row_h-3], 6, fill=bg, outline=color, width=1)
                draw.text((x + 35, y + 18), stat, font=font_head, fill=TEXT_MAIN)
            x += col_widths[j+1]
            
        # Draw Lunch Indicator centrally
        if i == len(days_to_draw) // 2:
            draw.text((lunch_x1 + 10, y + 15), "L\nU\nN\nC\nH", font=font_lunch, fill=ACCENT_YELLOW)
            
        x += col_widths[5] # Skip lunch col
        
        # Draw Periods 5-8
        for j in range(4, 8):
            draw_rounded_rect(draw, [x+3, y+3, x+col_widths[j+1]-3, y+row_h-3], 6, fill=CARD_BG, outline=CARD_BORDER, width=1)
            if j < len(lecs):
                lec = lecs[j]
                stat = lec.get("status", "-")
                color = ACCENT_GREEN if stat == "P" else ACCENT_RED if stat == "A" else TEXT_MUTED
                bg = ACCENT_GREEN_BG if stat == "P" else ACCENT_RED_BG if stat == "A" else CARD_BG
                
                draw_rounded_rect(draw, [x+3, y+3, x+col_widths[j+1]-3, y+row_h-3], 6, fill=bg, outline=color, width=1)
                draw.text((x + 35, y + 18), stat, font=font_head, fill=TEXT_MAIN)
            x += col_widths[j+1]

    # Stats footer
    footer_y = total_h - pad - 90
    draw_rounded_rect(draw, [pad, footer_y, total_w-pad, footer_y+80], 15, fill=CARD_BG, outline=CARD_BORDER, width=2)
    
    p_box_center = pad + 150
    a_box_center = total_w - pad - 150
    
    draw.text((p_box_center, footer_y + 15), f"{detailed.get('presentDays', 0)}", font=font_stat, fill=ACCENT_GREEN)
    draw.text((p_box_center-20, footer_y + 50), "ATTENDED", font=font_stat_sub, fill=TEXT_MUTED)
    
    draw.text((a_box_center, footer_y + 15), f"{detailed.get('absentDays', 0)}", font=font_stat, fill=ACCENT_RED)
    draw.text((a_box_center-15, footer_y + 50), "MISSED", font=font_stat_sub, fill=TEXT_MUTED)
    
    add_watermark(draw, total_w, total_h)
    
    bio = io.BytesIO()
    img.save(bio, "PNG")
    bio.seek(0)
    return bio
