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
DEFAULT_COPYRIGHT = "© AS Studios | Love Chauhan CSE DS"

def get_font(size, bold=False):
    ensure_fonts()
    try:
        return ImageFont.truetype(BOLD_FONT if bold else REGULAR_FONT, size)
    except Exception:
        return ImageFont.load_default()

def draw_rounded_rect(draw, xy, radius, fill, outline=None, width=1):
    x1, y1, x2, y2 = xy
    draw.rounded_rectangle(xy, radius=radius, fill=fill, outline=outline, width=width)

def add_watermark(draw, width, height, custom_text=None):
    text_to_draw = custom_text if custom_text else DEFAULT_COPYRIGHT
    font_wm = get_font(16, bold=False)  # Slightly larger watermark
    wm_bbox = draw.textbbox((0,0), text_to_draw, font=font_wm)
    wm_w = wm_bbox[2] - wm_bbox[0]
    draw.text(((width - wm_w) / 2, height - 40), text_to_draw, font=font_wm, fill=CARD_BORDER)

def render_summary_image(data, copyright_text=None):
    if not data or not data.get("summary"): return None
    subjects = data["summary"].get("data", [])
    
    width = 900
    row_height = 120  # Increased height for non-1:1 ratio
    padding = 50
    title_height = 120
    footer_height = 80
    
    # Grid logic
    cols = 2
    normal_subjects = [s for s in subjects if "ALL SUBJECTS" not in s.get("subjectName", "")]
    overall_subject = next((s for s in subjects if "ALL SUBJECTS" in s.get("subjectName", "")), None)
    
    normal_count = len(normal_subjects)
    rows = (normal_count + cols - 1) // cols
    if overall_subject:
        rows += 1 # Overall gets its own full row
        
    total_grids_height = rows * row_height
    height = title_height + total_grids_height + footer_height
    
    img = Image.new("RGB", (width, height), BG_COLOR)
    draw = ImageDraw.Draw(img)
    
    font_title = get_font(46, bold=True)
    draw.text((padding, padding), "📊 Attendance Overview", font=font_title, fill=ACCENT_BLUE)
    
    font_sub = get_font(20, bold=True)
    font_perc = get_font(26, bold=True)
    font_overall_sub = get_font(28, bold=True)
    font_overall_perc = get_font(42, bold=True)
    
    y = title_height
    x_gap = 30
    col_width = (width - (2 * padding) - x_gap) // 2
    
    # Draw normal subjects
    for idx, item in enumerate(normal_subjects):
        col = idx % cols
        row = idx // cols
        
        box_x1 = padding + col * (col_width + x_gap)
        box_y1 = y + row * row_height
        box_x2 = box_x1 + col_width
        box_y2 = box_y1 + 100
        
        name = item.get("subjectName", "")
        if len(name) > 35: name = name[:32] + "..."
        perc = item.get("subjectTotalPercentage", 0)
        
        color = ACCENT_GREEN if perc >= 75 else ACCENT_YELLOW if perc >= 60 else ACCENT_RED
        
        draw_rounded_rect(draw, [box_x1, box_y1, box_x2, box_y2], 12, fill=CARD_BG, outline=CARD_BORDER, width=2)
        draw.text((box_x1 + 20, box_y1 + 18), name, font=font_sub, fill=TEXT_MAIN)
        
        perc_text = f"{perc}%"
        perc_bbox = draw.textbbox((0,0), perc_text, font=font_perc)
        draw.text((box_x2 - 20 - (perc_bbox[2]-perc_bbox[0]), box_y1 + 15), perc_text, font=font_perc, fill=color)
        
        bar_y = box_y1 + 60
        draw_rounded_rect(draw, [box_x1 + 20, bar_y, box_x2 - 20, bar_y + 12], 6, "#0f172a")
        fill_width = int((col_width - 40) * (perc / 100))
        if fill_width > 10:
            draw_rounded_rect(draw, [box_x1 + 20, bar_y, box_x1 + 20 + fill_width, bar_y + 12], 6, color)

    # Draw overall subject full width
    if overall_subject:
        row = (normal_count + cols - 1) // cols
        box_x1 = padding
        box_y1 = y + row * row_height
        box_x2 = width - padding
        box_y2 = box_y1 + 100
        
        perc = overall_subject.get("subjectTotalPercentage", 0)
        color = ACCENT_BLUE

        draw_rounded_rect(draw, [box_x1, box_y1, box_x2, box_y2], 16, fill="#1e1b4b", outline=ACCENT_BLUE, width=3)
        draw.text((box_x1 + 30, box_y1 + 20), "Overall Attendance", font=font_overall_sub, fill=TEXT_MAIN)
        
        perc_text = f"{perc}%"
        perc_bbox = draw.textbbox((0,0), perc_text, font=font_overall_perc)
        draw.text((box_x2 - 30 - (perc_bbox[2]-perc_bbox[0]), box_y1 + 10), perc_text, font=font_overall_perc, fill=color)
        
        bar_y = box_y1 + 75
        draw_rounded_rect(draw, [box_x1 + 30, bar_y, box_x2 - 30, bar_y + 14], 7, "#0f172a")
        fill_width = int((width - 2 * padding - 60) * (perc / 100))
        if fill_width > 15:
            draw_rounded_rect(draw, [box_x1 + 30, bar_y, box_x1 + 30 + fill_width, bar_y + 14], 7, color)
            
    add_watermark(draw, width, height, copyright_text)
    bio = io.BytesIO()
    img.save(bio, "PNG")
    bio.seek(0)
    return bio

def render_timetable_image(data, copyright_text=None):
    if not data or not data.get("success"): return None
    raw_data = data.get("data", [])
    if not raw_data: return None
    
    abbr_map = {str(a.get("SN")): a for a in data.get("abbreviations", [])}
    
    days = ["MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY", "FRIDAY", "SATURDAY"]
    periods = [str(x) for x in range(1, 9)]
    
    cell_w = 170 # Wider cells to fit teacher names
    cell_h = 105 # Taller cells
    pad = 50
    title_h = 100
    header_w = 110
    
    total_w = pad*2 + header_w + (len(periods) * cell_w)
    total_h = pad*2 + title_h + (len(days) * cell_h) + 60
    
    img = Image.new("RGB", (total_w, total_h), BG_COLOR)
    draw = ImageDraw.Draw(img)
    
    font_title = get_font(46, bold=True)
    font_day = get_font(18, bold=True)
    font_cell = get_font(14, bold=True)
    font_fac = get_font(12, bold=False)
    font_room = get_font(12, bold=False)
    
    draw.text((pad, pad), "🗓️ Live Timetable", font=font_title, fill=ACCENT_PURPLE)
    
    for i, p in enumerate(periods):
        x = pad + header_w + (i * cell_w)
        draw_rounded_rect(draw, [x+4, pad+title_h-40, x+cell_w-4, pad+title_h-10], 8, fill="#1e1b4b", outline=ACCENT_PURPLE, width=1)
        draw.text((x + 50, pad+title_h-33), f"Period {p}", font=font_cell, fill=ACCENT_PURPLE)

    y_offset = pad + title_h
    for i, day in enumerate(days):
        y = y_offset + (i * cell_h)
        draw_rounded_rect(draw, [pad, y+4, pad+header_w-6, y+cell_h-4], 10, fill="#1e1b4b", outline=ACCENT_PURPLE, width=1)
        draw.text((pad + 15, y + 43), day[:3], font=font_day, fill=TEXT_MAIN)
        
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
                    if len(sub) > 20: sub = sub[:17]+".."
                    room = cell.get("roomNo", "")
                    
                    fac_data = cell.get("faculty")
                    fac = (fac_data.get("employeeName") or fac_data.get("firstName")) if isinstance(fac_data, dict) else fac_data if isinstance(fac_data, str) else cell.get("facultyName", "")
                    if fac and len(fac) > 20: fac = fac[:18] + ".."
                    
                    draw.text((x + 12, y + 15), sub, font=font_cell, fill=TEXT_MAIN)
                    if fac:
                        draw.text((x + 12, y + 45), f"👨‍🏫 {fac}", font=font_fac, fill=TEXT_MUTED)
                    if room:
                        draw.text((x + 12, y + 70), f"📍 {room}", font=font_room, fill=ACCENT_BLUE)

    add_watermark(draw, total_w, total_h, copyright_text)
    bio = io.BytesIO()
    img.save(bio, "PNG")
    bio.seek(0)
    return bio

def render_subjectwise_image(data, month_idx, copyright_text=None):
    if not data or not data.get("detailed"): return None
    detailed = data.get("detailed", {})
    days = detailed.get("data", [])
    if not days: return None
    
    # Map for full subject names
    subject_map = {item.get("subjectCode", ""): item.get("subjectName", "") for item in data.get("summary", {}).get("data", [])}
    
    pad = 60
    title_h = 160
    
    # Updated logic: Make columns much wider to fit Subject Names inside cells!
    # Date (180), P1-P4 (220x4), LUNCH (80), P5-P8 (220x4)
    col_widths = [180, 220, 220, 220, 220, 80, 220, 220, 220, 220]
    row_h = 120 # Double the height to fit multi-line subject names
    
    total_w = pad*2 + sum(col_widths)
    # limit to 15 days max
    days_to_draw = days[:15]
    total_h = pad*2 + title_h + (len(days_to_draw) * row_h) + 120 
    
    img = Image.new("RGB", (total_w, total_h), BG_COLOR)
    draw = ImageDraw.Draw(img)
    
    font_title = get_font(54, bold=True)
    font_head = get_font(20, bold=True)
    font_date = get_font(20, bold=True)
    font_sub = get_font(14, bold=True)
    font_lunch = get_font(24, bold=True)
    font_stat = get_font(36, bold=True)
    font_stat_sub = get_font(20, bold=False)
    
    mn_name = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]
    m_str = mn_name[int(month_idx)-1] if 1 <= int(month_idx) <= 12 else month_idx
    draw.text((pad, pad), f"📅 Master Timeline : {m_str}", font=font_title, fill=ACCENT_BLUE)
    
    # Table Headers
    x_offset = pad
    headers = ["DATE", "P1", "P2", "P3", "P4", "☕", "P5", "P6", "P7", "P8"]
    for i, h in enumerate(headers):
        align_x = x_offset + (col_widths[i] // 2) - 20
        draw.text((align_x, pad + title_h - 60), h, font=font_head, fill=TEXT_MUTED)
        x_offset += col_widths[i]
        
    y_offset = pad + title_h
    
    # Lunch Column Background
    lunch_x1 = pad + sum(col_widths[:5])
    draw_rounded_rect(draw, [lunch_x1+2, y_offset, lunch_x1+col_widths[5]-2, y_offset + (len(days_to_draw)*row_h)], 10, fill="#1e1b4b", outline=ACCENT_YELLOW, width=1)
    
    for i, day in enumerate(days_to_draw):
        y = y_offset + (i * row_h)
        date_str = day.get("attendanceDate", "").split("T")[0][-5:] # MM-DD
        
        # Date Box
        draw_rounded_rect(draw, [pad, y+6, pad+col_widths[0]-8, y+row_h-6], 12, fill=CARD_BG, outline=ACCENT_BLUE, width=2)
        draw.text((pad + 40, y + 45), date_str, font=font_date, fill=TEXT_MAIN)
        
        lecs = day.get("attendances", [])
        
        def draw_period(x, y, j, lecs):
            draw_rounded_rect(draw, [x+6, y+6, x+col_widths[j]-8, y+row_h-6], 12, fill=CARD_BG, outline=CARD_BORDER, width=2)
            if j-1 < len(lecs): # j is col index (1 to 4, 6 to 9)
                lec = lecs[j-1 if j < 5 else j-2]
                stat = lec.get("status", "-")
                code = lec.get("subjectCode", "")
                full_name = subject_map.get(code, code)
                if len(full_name) > 22: full_name = full_name[:19] + "..."
                
                color = ACCENT_GREEN if stat == "P" else ACCENT_RED if stat == "A" else TEXT_MUTED
                bg = ACCENT_GREEN_BG if stat == "P" else ACCENT_RED_BG if stat == "A" else CARD_BG
                
                draw_rounded_rect(draw, [x+6, y+6, x+col_widths[j]-8, y+row_h-6], 12, fill=bg, outline=color, width=2)
                
                # Draw subject name on top, status bottom right
                draw.text((x + 20, y + 25), full_name, font=font_sub, fill=TEXT_MAIN)
                draw.text((x + col_widths[j] - 50, y + row_h - 45), stat, font=font_head, fill=TEXT_MAIN)
        
        # Draw Periods 1-4
        x = pad + col_widths[0]
        for j in range(1, 5):
            draw_period(x, y, j, lecs)
            x += col_widths[j]
            
        # Draw Lunch Indicator centrally
        if i == len(days_to_draw) // 2:
            draw.text((lunch_x1 + 30, y + 10), "L\nU\nN\nC\nH", font=font_lunch, fill=ACCENT_YELLOW)
            
        x += col_widths[5] # Skip lunch col
        
        # Draw Periods 5-8
        for j in range(6, 10):
            draw_period(x, y, j, lecs)
            x += col_widths[j]

    # Stats footer
    footer_y = total_h - pad - 90
    draw_rounded_rect(draw, [pad, footer_y, total_w-pad, footer_y+80], 15, fill=CARD_BG, outline=CARD_BORDER, width=2)
    
    p_box_center = pad + 150
    a_box_center = total_w - pad - 150
    
    draw.text((p_box_center, footer_y + 15), f"{detailed.get('presentDays', 0)}", font=font_stat, fill=ACCENT_GREEN)
    draw.text((p_box_center-25, footer_y + 55), "ATTENDED", font=font_stat_sub, fill=TEXT_MUTED)
    
    draw.text((a_box_center, footer_y + 15), f"{detailed.get('absentDays', 0)}", font=font_stat, fill=ACCENT_RED)
    draw.text((a_box_center-20, footer_y + 55), "MISSED", font=font_stat_sub, fill=TEXT_MUTED)
    
    add_watermark(draw, total_w, total_h, copyright_text)
    
    bio = io.BytesIO()
    img.save(bio, "PNG")
    bio.seek(0)
    return bio
