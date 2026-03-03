from flask import Flask, request, jsonify
import asyncio
import os
from telegram import Update
from bot_logic import app as ptb_app

app = Flask(__name__)

# Try to get existing loop or create new one for Vercel environment
try:
    loop = asyncio.get_event_loop()
except RuntimeError:
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

# Pre-initialize PTB to prevent startup delays
loop.run_until_complete(ptb_app.initialize())

@app.route('/', defaults={'path': ''}, methods=['GET', 'POST'])
@app.route('/<path:path>', methods=['GET', 'POST'])
def webhook(path):
    if request.method == 'POST' and path == '':
        try:
            update = Update.de_json(request.get_json(force=True), ptb_app.bot)
            loop.run_until_complete(ptb_app.process_update(update))
            return jsonify({"ok": True}), 200
        except Exception as e:
            print(f"Error: {e}")
            return str(e), 500
            
    # Admin Panel serving
    if path == 'admin':
        try:
            with open('admin.html', 'r', encoding='utf-8') as f:
                return f.read(), 200, {'Content-Type': 'text/html'}
        except Exception as e:
            return str(e), 500
            
    return "🚀 Webhook Server Active! Send POST requests from Telegram to this URL. Access /admin for the Admin Panel.", 200

# ADMIN API Handlers
def check_auth(req):
    auth = req.headers.get('Authorization')
    expected = "Bearer " + os.getenv("ADMIN_PASSWORD", "lovech20")
    return auth == expected

@app.route('/api/stats', methods=['GET'])
def api_stats():
    if not check_auth(request): return jsonify({"error": "Unauthorized"}), 401
    from bot_logic import get_users
    users = get_users()
    return jsonify({"users": len(users)})

@app.route('/api/settings', methods=['GET', 'POST'])
def api_settings():
    if not check_auth(request): return jsonify({"error": "Unauthorized"}), 401
    from bot_logic import get_settings, save_settings
    if request.method == 'POST':
        data = request.get_json(force=True)
        save_settings(data)
        return jsonify({"success": True})
    return jsonify(get_settings())

@app.route('/api/announce', methods=['POST'])
def api_announce():
    if not check_auth(request): return jsonify({"error": "Unauthorized"}), 401
    from bot_logic import get_users
    data = request.get_json(force=True)
    msg = data.get("message", "")
    users = get_users()
    sent = 0
    for uid, udata in users.items():
        name = udata.get("name", "Student")
        email = udata.get("email", "")
        formatted_msg = msg.replace("{name}", name).replace("{email}", email)
        try:
            loop.run_until_complete(ptb_app.bot.send_message(chat_id=uid, text=formatted_msg, parse_mode="HTML"))
            sent += 1
        except Exception:
            pass
    return jsonify({"sent": sent})

# Vercel requires the app to be named `app` or `handler`
