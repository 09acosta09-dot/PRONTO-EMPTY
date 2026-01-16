import os
import json
import math
import random
from datetime import datetime, time
from zoneinfo import ZoneInfo

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
CHANNEL_MOTOCARRO = -1002688723492

LINK_TAXI = "https://t.me/+Drczf-TdHCUzNDZh"
LINK_DOMICILIOS = "https://t.me/+gZvnu8zolb1iOTBh"
LINK_CAMIONETAS = "https://t.me/+KRam-XSvPQ5jNjRh"
LINK_MOTOCARRO = "https://t.me/+REkbglMlfxE3YjI5"

NEQUI_NUMBER = "3052915231"

MOBILES_FILE = "mobiles.json"
SERVICES_FILE = "services.json"

WEBHOOK_DOMAIN = "https://pronto-empty-production.up.railway.app"
WEBHOOK_PATH = f"/webhook/{TOKEN}"
WEBHOOK_URL = WEBHOOK_DOMAIN + WEBHOOK_PATH

TZ_CO = ZoneInfo("America/Bogota")
CORTE = time(15, 0)

SERVICE_INFO = {
    "Taxi": {
        "label_user": "🚕 Taxi",
        "channel_id": CHANNEL_TAXI,
        "link": LINK_TAXI,
        "prefix": "T",
    },
    "Domicilios": {
        "label_user": "📦 Domicilios",
        "channel_id": CHANNEL_DOMICILIOS,
        "link": LINK_DOMICILIOS,
        "prefix": "D",
    },
    "Camionetas": {
        "label_user": "🚚 Camionetas",
        "channel_id": CHANNEL_CAMIONETAS,
        "link": LINK_CAMIONETAS,
        "prefix": "C",
    },
    "Motocarro": {
        "label_user": "🛺 Motocarro",
        "channel_id": CHANNEL_MOTOCARRO,
        "link": LINK_MOTOCARRO,
        "prefix": "M",
    },
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
    return datetime.now(TZ_CO)

def now_colombia_str():
    return now_colombia().strftime("%Y-%m-%d %I:%M %p")

def after_cutoff():
    return now_colombia().time() >= CORTE

def mobile_can_work(mobile):
    if after_cutoff() and not mobile.get("pago_aprobado", False):
        return False, (
            "Ya pasó la hora de corte (3:00 p.m.).\n"
            "Para trabajar después de las 3:00 p.m. debes realizar el pago."
        )
    return True, ""

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
    [[KeyboardButton("🚀 Iniciar")]], resize_keyboard=True
)

main_keyboard = ReplyKeyboardMarkup(
    [[KeyboardButton("Usuario")],
     [KeyboardButton("Móvil")],
     [KeyboardButton("Administrador")]],
    resize_keyboard=True,
)

user_service_keyboard = ReplyKeyboardMarkup(
    [
        [KeyboardButton(SERVICE_INFO["Taxi"]["label_user"])],
        [KeyboardButton(SERVICE_INFO["Domicilios"]["label_user"])],
        [KeyboardButton(SERVICE_INFO["Camionetas"]["label_user"])],
        [KeyboardButton(SERVICE_INFO["Motocarro"]["label_user"])],
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
# REGISTRO / ASIGNACIÓN
# ----------------------------

def asignar_codigo_movil(servicio):
    mobiles = get_mobiles()
    prefix = SERVICE_INFO[servicio]["prefix"]
    nums = []
    for m in mobiles.values():
        c = m.get("codigo", "")
        if c.startswith(prefix):
            try:
                nums.append(int(c[1:]))
            except:
                pass
    n = max(nums) + 1 if nums else 1
    return f"{prefix}{n:03d}"

# ----------------------------
# SELECCIÓN DE MÓVIL
# ----------------------------

def seleccionar_movil_mas_cercano(servicio, lat_cliente, lon_cliente):
    mobiles = get_mobiles()
    candidatos = []

    # Compatibilidad si hay datos viejos "Especial"
    if servicio == "Motocarro":
        servicios_validos = {"Motocarro", "Especial"}
    else:
        servicios_validos = {servicio}

    for chat_id, m in mobiles.items():
        if not m.get("activo"):
            continue
        if m.get("servicio") not in servicios_validos:
            continue

        puede, _ = mobile_can_work(m)
        if not puede:
            continue

        if lat_cliente and lon_cliente and m.get("lat") and m.get("lon"):
            dist = haversine_distance(lat_cliente, lon_cliente, m["lat"], m["lon"])
        else:
            dist = float("inf")

        candidatos.append({
            "chat_id": int(chat_id),
            "codigo": m.get("codigo"),
            "servicio": servicio,
            "distancia": dist
        })

    if not candidatos:
        return None

    candidatos.sort(key=lambda x: x["distancia"])
    return candidatos[0]

# ----------------------------
# MAIN
# ----------------------------

def main():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.LOCATION, lambda u, c: None))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, lambda u, c: None))

    app.run_webhook(
        listen="0.0.0.0",
        port=int(os.environ.get("PORT", 8443)),
        url_path=WEBHOOK_PATH,
        webhook_url=WEBHOOK_URL,
    )

if __name__ == "__main__":
    main()
