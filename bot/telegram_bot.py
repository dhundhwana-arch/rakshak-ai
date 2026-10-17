import os
import sys
import requests
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, MessageHandler, filters, CommandHandler

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

load_dotenv()
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
API_BASE = "http://127.0.0.1:8000/api"

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    welcome_msg = (
        "🛡️ *Namaste! Hu Rakshak AI Chhu.*\n\n"
        "Tamaro personal cybersecurity guardian. Tamne koi pan suspicious message, link, APK file, ke screenshot (Digital Arrest / Fake UPI) male, toh ahiya forward karo!\n\n"
        "Commands:\n"
        "• Koi pan link moklo -> URL scan thase\n"
        "• Message forward karo -> AI social engineering check thase\n"
        "• Screenshot moklo -> AI fraud detection thase\n"
        "• APK file moklo -> Malware & C2 scan thase"
    )
    await update.message.reply_text(welcome_msg, parse_mode="Markdown")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    text = message.text or message.caption

    if text and text.startswith(("http://", "https://", "www.")):
        await message.reply_text("🔍 URL scan thai rahyo chhe...")
        try:
            res = requests.post(f"{API_BASE}/scan/url", data={"url": text})
            data = res.json()
            reply = (
                f"🚨 *URL Security Report*\n\n"
                f"• *URL:* {data.get('domain')}\n"
                f"• *Risk Score:* {data.get('risk_score')}/100\n"
                f"• *Threat Level:* {data.get('risk_level')}\n"
                f"• *Flags:* {', '.join(data.get('flags', ['None']))}"
            )
            await message.reply_text(reply, parse_mode="Markdown")
        except Exception as e:
            await message.reply_text(f"Scan failed: {str(e)}")
        return

    if text:
        await message.reply_text("🤖 AI Scam Agent analyze kare chhe...")
        try:
            res = requests.post(f"{API_BASE}/scan/text", data={"message": text})
            data = res.json()
            reply = (
                f"🛡️ *AI Scam Analysis Report*\n\n"
                f"• *Category:* {data.get('scam_category')}\n"
                f"• *Risk Score:* {data.get('ai_risk_score')}/100\n"
                f"• *Triggers:* {', '.join(data.get('psychological_triggers', []))}\n\n"
                f"⚠️ *Gujarati Warning:*\n{data.get('explanation_gujarati')}\n\n"
                f"📋 *Action Steps:* {', '.join(data.get('action_steps', []))}"
            )
            await message.reply_text(reply, parse_mode="Markdown")
        except Exception as e:
            await message.reply_text(f"Analysis failed: {str(e)}")
        return

    if message.photo:
        await message.reply_text("🖼️ Image scan thai rahi chhe...")
        photo_file = await message.photo[-1].get_file()
        file_path = f"uploads/{photo_file.file_unique_id}.jpg"
        os.makedirs("uploads", exist_ok=True)
        await photo_file.download_to_drive(file_path)

        try:
            with open(file_path, "rb") as f:
                res = requests.post(f"{API_BASE}/scan/image", files={"file": f})
            data = res.json()
            os.remove(file_path)
            reply = (
                f"🖼️ *Image Fraud Analysis*\n\n"
                f"• *Category:* {data.get('scam_category')}\n"
                f"• *Risk Score:* {data.get('ai_risk_score')}/100\n\n"
                f"⚠️ *Gujarati Warning:*\n{data.get('explanation_gujarati')}\n\n"
                f"📋 *Action Steps:* {', '.join(data.get('action_steps', []))}"
            )
            await message.reply_text(reply, parse_mode="Markdown")
        except Exception as e:
            await message.reply_text(f"Image scan failed: {str(e)}")
        return

    if message.document and message.document.file_name.endswith('.apk'):
        await message.reply_text("📦 APK Trojan & Malware scan thai rahyo chhe...")
        doc_file = await message.document.get_file()
        file_path = f"uploads/{message.document.file_name}"
        os.makedirs("uploads", exist_ok=True)
        await doc_file.download_to_drive(file_path)

        try:
            with open(file_path, "rb") as f:
                res = requests.post(f"{API_BASE}/scan/apk", files={"file": f})
            data = res.json()
            os.remove(file_path)
            reply = (
                f"📦 *APK Malware Report*\n\n"
                f"• *SHA-256:* `{data.get('sha256')[:16]}...`\n"
                f"• *Risk Score:* {data.get('risk_score')}/100\n"
                f"• *Threat Level:* {data.get('risk_level')}\n"
                f"• *Permissions:* {', '.join(data.get('permissions', ['None']))}\n"
                f"• *Flags:* {', '.join(data.get('flags', ['None']))}"
            )
            await message.reply_text(reply, parse_mode="Markdown")
        except Exception as e:
            await message.reply_text(f"APK scan failed: {str(e)}")
        return

    await message.reply_text("Kripya koi valid link, text message, screenshot ke APK forward karo!")

if __name__ == "__main__":
    if not BOT_TOKEN:
        print("Error: TELEGRAM_BOT_TOKEN missing in .env file!")
        sys.exit(1)
    
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, handle_message))
    
    print("Rakshak AI Telegram Bot start thai gayo chhe...")
    app.run_polling()
