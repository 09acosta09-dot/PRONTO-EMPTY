# PRONTO - Versión 2.3 Profesional (Webhook para Railway)
# python-telegram-bot v20+

import os
import json
import math
import random
from datetime import datetime, timedelta, timezone

from telegram import (
    Update,
    ReplyKeyboardMarkup,
    KeyboardButton,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

# ----------------------------
# CONFIGURACIÓN
# ----------------------------

TOKEN = os.getenv("BOT_TOKEN")
if not TOKEN:
    raise RuntimeError("La variable de entorno BOT_TOKEN no está configurada.")

ADMIN_IDS = [1741298723, 7076796229]

CHANNEL_TAXI = -1002697357566
CHANNEL_DOMICILIOS = -1002503403579
CHANNEL_CAMIONETAS = -1002662309590
CHANNEL_ESPECIAL = -1002688723492

LINK_TAXI = "https://t.me/+Drczf-TdHCUzNDZh"
LINK_DOMICILIOS = "https://t.me/+gZvnu8zolb1iOTBh"
LINK_CAMIONETAS = "https://t.me/+KRam-XSvPQ5jNjRh"
LINK_ESPECIAL = "https://t.me/+REkbglMlfxE3YjI5"

NEQUI_NUMBER = "3052915231"

MOBILES_FILE = "mobiles.json"
SERVICES_FILE = "services.json"

WEBHOOK_DOMAIN = "https://pronto-empty-production.up.railway.app"
WEBHOOK_PATH = f"/webhook/{TOKEN}"
WEBHOOK_URL = WEBHOOK_DOMAIN + WEBHOOK_PATH

SERVICE_INFO = {
    "Taxi": {"label_user": "🚕 Taxi", "channel_id": CHANNEL_TAXI, "link": LINK_TAXI, "prefix": "T"},
    "Domicilios": {"label_user": "📦 Domicilios", "channel_id": CHANNEL_DOMICILIOS, "link": LINK_DOMICILIOS, "prefix": "D"},
    "Camionetas": {"label_user": "🚚 Camionetas", "channel_id": CHANNEL_CAMIONETAS, "link": LINK_CAMIONETAS, "prefix": "C"},
    "Especial": {"label_user": "♿ Especial", "channel_id": CHANNEL_ESPECIAL, "link": LINK_ESPECIAL, "prefix": "E"},
}

# ----------------------------
# UTILIDADES
# ----------------------------

def load_json(path, default):
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default

def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def get_mobiles():
    return load_json(MOBILES_FILE, {})

def save_mobiles(data):
    save_json(MOBILES_FILE, data)

def get_services():
    return load_json(SERVICES_FILE, {})

def save_services(data):
    save_json(SERVICES_FILE, data)

def now_colombia():
    return datetime.now(timezone(timedelta(hours=-5)))

def now_colombia_str():
    return now_colombia().strftime("%Y-%m-%d %H:%M:%S")

def after_cutoff():
    now = now_colombia()
    return now.hour >= 15

def haversine_distance(lat1, lon1, lat2, lon2):
    R = 6371
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dl/2)**2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

# ----------------------------
# MENÚS
# ----------------------------

start_keyboard = ReplyKeyboardMarkup(
    [[KeyboardButton("🚀 Iniciar")]],
    resize_keyboard=True
)

main_keyboard = ReplyKeyboardMarkup(
    [[KeyboardButton("Usuario")], [KeyboardButton("Móvil")], [KeyboardButton("Administrador")]],
    resize_keyboard=True,
)

user_service_keyboard = ReplyKeyboardMarkup(
    [
        [KeyboardButton("🚕 Taxi")],
        [KeyboardButton("📦 Domicilios")],
        [KeyboardButton("🚚 Camionetas")],
        [KeyboardButton("♿ Especial")],
        [KeyboardButton("⬅ Volver al inicio")],
    ],
    resize_keyboard=True,
)

movil_menu_keyboard = ReplyKeyboardMarkup(
    [
        [KeyboardButton("🚀 Iniciar jornada")],
        [KeyboardButton("📍 Compartir ubicación")],
        [KeyboardButton("💰 Enviar pago")],
        [KeyboardButton("🛑 Finalizar jornada")],
        [KeyboardButton("⬅ Volver al inicio")],
    ],
    resize_keyboard=True,
)

admin_keyboard = ReplyKeyboardMarkup(
    [
        [KeyboardButton("📲 Registrar móvil")],
        [KeyboardButton("🚗 Ver móviles registrados")],
        [KeyboardButton("🗑 Desactivar móvil")],
        [KeyboardButton("💰 Aprobar pagos")],
        [KeyboardButton("📋 Ver servicios activos")],
        [KeyboardButton("⬅ Volver al inicio")],
    ],
    resize_keyboard=True,
)

# ----------------------------
# START
# ----------------------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text(
        "👋 Bienvenido a PRONTO.\n\nToca el botón para iniciar:",
        reply_markup=start_keyboard,
    )

# ----------------------------
# HANDLERS
# ----------------------------

async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    user_id = update.effective_user.id

    # 🚀 Botón iniciar = /start
    if text == "🚀 Iniciar":
    context.user_data.clear()
    await update.message.reply_text(
        "Elige una opción:",
        reply_markup=main_keyboard,
    )
    return

    # Volver al inicio
    if text == "⬅ Volver al inicio":
        context.user_data.clear()
        await update.message.reply_text("Elige una opción:", reply_markup=main_keyboard)
        return

    if text == "Usuario":
        context.user_data["mode"] = "usuario"
        await update.message.reply_text("Seleccione el servicio:", reply_markup=user_service_keyboard)
        return

    if text == "Móvil":
        context.user_data.clear()
        context.user_data["mode"] = "movil_auth"
        await update.message.reply_text("🔐 Escribe tu código de móvil:")
        return

    if text == "Administrador":
        if user_id not in ADMIN_IDS:
            await update.message.reply_text("❌ No autorizado.")
            return
        context.user_data["mode"] = "admin"
        await update.message.reply_text("Panel administrador:", reply_markup=admin_keyboard)
        return

        # 🔁 Redirección automática SOLO si el usuario no está en ningún flujo
    mode = context.user_data.get("mode")

    if not mode:
        await update.message.reply_text(
            "Para comenzar, toca el botón 👇",
            reply_markup=start_keyboard,
        )
        return

# ----------------------------
# MAIN
# ----------------------------

def main():
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))
    app.run_webhook(
        listen="0.0.0.0",
        port=int(os.environ.get("PORT", 8443)),
        url_path=WEBHOOK_PATH,
        webhook_url=WEBHOOK_URL,
    )

if __name__ == "__main__":
    main()
