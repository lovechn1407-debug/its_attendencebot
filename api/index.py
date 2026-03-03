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
    if request.method == 'POST':
        try:
            update = Update.de_json(request.get_json(force=True), ptb_app.bot)
            loop.run_until_complete(ptb_app.process_update(update))
            return jsonify({"ok": True}), 200
        except Exception as e:
            print(f"Error: {e}")
            return str(e), 500
            
    return "🚀 Webhook Server Active! Send POST requests from Telegram to this URL.", 200

# Vercel requires the app to be named `app` or `handler`
