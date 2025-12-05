# ==============================
#   PRONTO Versión 2.4 Profesional
# ==============================

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
# UTILIDADES DE JSON
# ----------------------------

def load_json(path: str, default):
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return default

def save_json(path: str, data):
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

# ----------------------------
# UTILIDADES TIEMPO
# ----------------------------

def now_colombia():
    tz = timezone(timedelta(hours=-5))
    return datetime.now(tz)

def now_colombia_str():
    return now_colombia().strftime("%Y-%m-%d %H:%M:%S")

def after_cutoff():
    now = now_colombia()
    return now.hour > 15 or (now.hour == 15 and now.minute >= 0)

def haversine_distance(lat1, lon1, lat2, lon2):
    R = 6371.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = (
        math.sin(dphi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c

# ----------------------------
# MENÚS
# ----------------------------

main_keyboard = ReplyKeyboardMarkup(
    [
        [KeyboardButton("Usuario")],
        [KeyboardButton("Móvil")],
        [KeyboardButton("Administrador")],
    ],
    resize_keyboard=True,
)

user_service_keyboard = ReplyKeyboardMarkup(
    [
        [KeyboardButton(SERVICE_INFO["Taxi"]["label_user"])],
        [KeyboardButton(SERVICE_INFO["Domicilios"]["label_user"])],
        [KeyboardButton(SERVICE_INFO["Camionetas"]["label_user"])],
        [KeyboardButton(SERVICE_INFO["Especial"]["label_user"])],
        [KeyboardButton("⬅ Volver al inicio")],
    ],
    resize_keyboard=True,
)

user_active_service_keyboard = ReplyKeyboardMarkup(
    [
        [KeyboardButton("❌ Cancelar mi servicio")],
        [KeyboardButton("🚗 Ver mi móvil asignado")],
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

# -----------------------------------
# 🔎 FUNCIONES NUEVAS DEL USUARIO
# -----------------------------------

async def ver_movil_asignado(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    services = get_services()

    service_data = None
    for s in services.values():
        if s.get("user_chat_id") == chat_id and s.get("status") in ["pendiente", "reservado"]:
            service_data = s
            break

    if not service_data:
        await update.message.reply_text("No tienes servicios activos 💕")
        return

    movil_chat_id = service_data.get("movil_chat_id")
    if not movil_chat_id:
        await update.message.reply_text("Un móvil todavía no ha confirmado el servicio 💖")
        return

    mobiles = get_mobiles()
    movil = mobiles.get(str(movil_chat_id))
    if not movil:
        await update.message.reply_text("Hubo un pequeño problema… 😢")
        return

    texto = (
        "🚗 *Móvil asignado*\n\n"
        f"🔢 Código: *{movil.get('codigo','')}*\n"
        f"🚘 Placa: *{movil.get('placa','')}*\n"
        f"🚘 Marca/Modelo: *{movil.get('marca','')} {movil.get('modelo','')}*\n"
    )

    await update.message.reply_text(texto, parse_mode="Markdown")

async def cancelar_servicio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    services = get_services()

    service_data = None
    for s in services.values():
        if s.get("user_chat_id") == chat_id and s.get("status") in ["pendiente", "reservado"]:
            service_data = s
            break

    if not service_data:
        await update.message.reply_text("No tienes servicios activos mi cielo 💋")
        return

    movil_chat_id = service_data.get("movil_chat_id")
    services.pop(service_data["id"], None)
    save_services(services)

    await update.message.reply_text("Tu servicio ha sido cancelado ❤️")

    if movil_chat_id:
        try:
            await context.bot.send_message(chat_id=movil_chat_id, text="🚫 El usuario canceló el servicio.")
        except:
            pass
# ----------------------------
# MAIN (WEBHOOK)
# ----------------------------

def main():
    application = ApplicationBuilder().token(TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("soy_movil", soy_movil_command))
    application.add_handler(CallbackQueryHandler(button_callback))
    application.add_handler(MessageHandler(filters.LOCATION, location_handler))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))

    application.run_webhook(
        listen="0.0.0.0",
        port=int(os.environ.get("PORT", 8443)),
        url_path=WEBHOOK_PATH,
        webhook_url=WEBHOOK_URL,
    )


if __name__ == "__main__":
    main()


