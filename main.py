# PRONTO - Versión 2.5 Profesional (Usuario puede cancelar y ver móvil asignado)

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

# SOLO estos IDs pueden ver el menú de administrador
ADMIN_IDS = [1741298723, 7076796229]

# Canales por servicio (IDs numéricos)
CHANNEL_TAXI = -1002697357566
CHANNEL_DOMICILIOS = -1002503403579
CHANNEL_CAMIONETAS = -1002662309590
CHANNEL_ESPECIAL = -1002688723492

# Links de invitación a los canales (ajusta si cambian)
LINK_TAXI = "https://t.me/+Drczf-TdHCUzNDZh"
LINK_DOMICILIOS = "https://t.me/+gZvnu8zolb1iOTBh"
LINK_CAMIONETAS = "https://t.me/+KRam-XSvPQ5jNjRh"  # antes Trasteos
LINK_ESPECIAL = "https://t.me/+REkbglMlfxE3YjI5"

# Número de Nequi del administrador
NEQUI_NUMBER = "3052915231"

MOBILES_FILE = "mobiles.json"
SERVICES_FILE = "services.json"

# Dominio Railway para el webhook
WEBHOOK_DOMAIN = "https://pronto-empty-production.up.railway.app"
WEBHOOK_PATH = f"/webhook/{TOKEN}"
WEBHOOK_URL = WEBHOOK_DOMAIN + WEBHOOK_PATH

# Información por servicio
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
    "Especial": {
        "label_user": "♿ Especial",
        "channel_id": CHANNEL_ESPECIAL,
        "link": LINK_ESPECIAL,
        "prefix": "E",
    },
}

# ----------------------------
# UTILIDADES DE ARCHIVO
# ----------------------------

def load_json(path: str, default):
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def save_json(path: str, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def get_mobiles():
    data = load_json(MOBILES_FILE, {})
    if not isinstance(data, dict):
        data = {}
    return data


def save_mobiles(data):
    save_json(MOBILES_FILE, data)


def get_services():
    data = load_json(SERVICES_FILE, {})
    if not isinstance(data, dict):
        data = {}
    return data


def save_services(data):
    save_json(SERVICES_FILE, data)


# ----------------------------
# UTILIDADES DE TIEMPO Y DISTANCIA
# ----------------------------

def now_colombia():
    """Devuelve datetime actual en Colombia."""
    tz = timezone(timedelta(hours=-5))
    return datetime.now(tz)


def now_colombia_str():
    return now_colombia().strftime("%Y-%m-%d %H:%M:%S")


def after_cutoff():
    """Devuelve True si ya pasó la hora de corte (3:00 p.m. Colombia)."""
    now = now_colombia()
    return now.hour > 15 or (now.hour == 15 and now.minute >= 0)


def haversine_distance(lat1, lon1, lat2, lon2):
    R = 6371.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
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

# Teclado para cuando el usuario tiene un servicio activo
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

# ----------------------------
# /START
# ----------------------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    if update.message:
        await update.message.reply_text(
            "👋 Bienvenido a PRONTO.\n\nElige una opción:",
            reply_markup=main_keyboard,
        )

# ----------------------------
# /soy_movil - solicitud de registro del conductor
# ----------------------------

async def soy_movil_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """El conductor envía /soy_movil y se notifica a los administradores con su chat_id."""
    user = update.effective_user
    chat_id = update.effective_chat.id

    # Mensaje para el conductor
    await update.message.reply_text(
        "Perfecto 🚗✨\n"
        "Tu solicitud fue enviada.\n"
        "El administrador te registrará pronto para que puedas empezar a trabajar."
    )

    # Notificar a los administradores
    nombre = user.full_name or "Sin nombre"
    username = f"@{user.username}" if user.username else "Sin username"

    texto_admin = (
        "📲 *Nuevo conductor quiere registrarse*\n\n"
        f"👤 Nombre de perfil: *{nombre}*\n"
        f"🔗 Usuario: {username}\n"
        f"💬 Chat ID: `{chat_id}`\n\n"
        "¿Deseas iniciar el registro de este móvil ahora?"
    )

    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "📝 Iniciar registro",
                    callback_data=f"REG_MOVIL|{chat_id}",
                )
            ]
        ]
    )

    for admin_id in ADMIN_IDS:
        try:
            await context.bot.send_message(
                chat_id=admin_id,
                text=texto_admin,
                parse_mode="Markdown",
                reply_markup=keyboard,
            )
        except Exception:
            # Si algún admin no se puede notificar, se ignora para no romper el flujo
            pass


# ----------------------------
# ASIGNACIÓN DE CÓDIGOS PARA MÓVILES
# ----------------------------

def asignar_codigo_movil(servicio: str) -> str:
    """
    Asigna código al móvil según el servicio:
        Taxi       -> T001, T002, ...
        Domicilios -> D001, D002, ...
        Camionetas -> C001, C002, ...
        Especial   -> E001, E002, ...
    """
    mobiles = get_mobiles()
    prefix = SERVICE_INFO[servicio]["prefix"]

    numeros = []
    for m in mobiles.values():
        codigo = m.get("codigo", "")
        if codigo.startswith(prefix):
            try:
                num = int(codigo[1:])
                numeros.append(num)
            except ValueError:
                continue

    next_num = max(numeros) + 1 if numeros else 1
    return f"{prefix}{next_num:03d}"


# ----------------------------
# FLUJO USUARIO - PEDIR SERVICIO
# ----------------------------

async def handle_usuario_option(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["mode"] = "usuario"
    context.user_data["step"] = "choose_service"
    await update.message.reply_text(
        "Seleccione el tipo de servicio que desea solicitar:",
        reply_markup=user_service_keyboard,
    )


async def handle_usuario_service_choice(update: Update, context: ContextTypes.DEFAULT_TYPE, servicio: str):
    context.user_data["mode"] = "usuario"
    context.user_data["step"] = "ask_name"
    context.user_data["servicio"] = servicio
    context.user_data["data"] = {}
    await update.message.reply_text(
        "📝 Por favor escribe tu *nombre completo*:",
        parse_mode="Markdown",
    )


def build_location_keyboard():
    kb = ReplyKeyboardMarkup(
        [
            [KeyboardButton("📍 Enviar ubicación", request_location=True)],
            [KeyboardButton("Omitir ubicación")],
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
    )
    return kb


async def finalize_user_request(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Cuando ya tenemos todos los datos del usuario se crea el servicio,
    se busca el móvil más cercano y se envía el servicio.
    """
    user = update.effective_user
    chat_id = update.effective_chat.id
    data = context.user_data.get("data", {})
    servicio = context.user_data.get("servicio")

    if not servicio or not data:
        await update.message.reply_text("Ocurrió un problema con la solicitud. Intenta de nuevo con 'Usuario'.")
        return

    hora = now_colombia_str()
    data["hora"] = hora
    data["servicio"] = servicio
    data["user_chat_id"] = chat_id
    data["user_id"] = user.id

    services = get_services()

    existing_ids = [s.get("id") for s in services.values()]
    all_nums = []
    for sid in existing_ids:
        if sid and isinstance(sid, str) and sid.startswith("S"):
            try:
                all_nums.append(int(sid[1:]))
            except ValueError:
                pass
    next_num = max(all_nums) + 1 if all_nums else 1
    service_id = f"S{next_num:05d}"

    data["id"] = service_id
    data["status"] = "pendiente"
    data["movil_codigo"] = None
    data["movil_chat_id"] = None

    movil_info = seleccionar_movil_mas_cercano(servicio, data.get("lat"), data.get("lon"))

    if movil_info is None:
        await update.message.reply_text(
            "😔 En este momento no hay móviles disponibles para este servicio.\n"
            "Por favor intenta nuevamente en unos minutos."
        )
        return

    movil_chat_id = movil_info["chat_id"]
    movil_codigo = movil_info["codigo"]
    movil_servicio = movil_info["servicio"]

    data["movil_codigo"] = movil_codigo
    data["movil_chat_id"] = movil_chat_id

    services[service_id] = data
    save_services(services)

    await update.message.reply_text(
        "✅ Tu solicitud ha sido registrada.\n"
        "Estamos notificando a un móvil cercano para que tome tu servicio.\n\n"
        "Si deseas cancelar o ver el móvil asignado, usa las opciones de abajo.",
        reply_markup=user_active_service_keyboard,
    )

    bot = context.bot

    texto_movil = f"🚨 *Nuevo servicio de {movil_servicio}*\n\n"
    texto_movil += f"🆔 Código de servicio: *{service_id}*\n"
    texto_movil += f"👤 Cliente: *{data.get('nombre','(sin nombre)')}*\n"
    texto_movil += f"📞 Teléfono: *{data.get('telefono','(sin teléfono)')}*\n"
    texto_movil += f"📍 Destino / Dirección: *{data.get('destino','(sin destino)')}*\n"
    if movil_servicio == "Camionetas":
        texto_movil += f"📦 Tipo de carga: *{data.get('carga','(no especificada)')}*\n"
    if data.get("lat") is not None and data.get("lon") is not None:
        texto_movil += "\n🌎 El cliente compartió ubicación GPS.\n"

    texto_movil += f"\n⏰ Hora de solicitud: *{hora}* (hora Colombia)\n\n"
    texto_movil += "Para tomar este servicio, usa el botón de abajo."

    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "🚨🔴 RESERVAR SERVICIO 🔴🚨",
                    callback_data=f"RESERVAR|{service_id}",
                )
            ]
        ]
    )

    try:
        await bot.send_message(
            chat_id=movil_chat_id,
            text=texto_movil,
            reply_markup=keyboard,
            parse_mode="Markdown",
        )
    except Exception:
        await update.message.reply_text(
            "Hubo un problema notificando al móvil. Intenta de nuevo más tarde."
        )
        return

    channel_id = SERVICE_INFO[movil_servicio]["channel_id"]
    resumen_canal = (
        f"📢 *Nuevo servicio de {movil_servicio}*\n"
        f"🆔 Servicio: *{service_id}*\n"
        f"👤 Cliente: *{data.get('nombre','')}*\n"
        f"📍 Destino: *{data.get('destino','')}*\n"
        f"🕒 Hora: *{hora}* (Colombia)\n"
        f"🚗 Móvil asignado: *{movil_codigo}* (en espera de reserva)"
    )
            try:
            await bot.send_message(
                chat_id=channel_id,
                text=resumen,
                parse_mode="Markdown",
            )
        except Exception:
            pass

        return

    # Aquí continúan los demás callback (APROBAR_PAGO, CANCELAR_PAGO, REG_MOVIL)
    # (Tu código original sigue igual, no se cambian esas partes)
# ----------------------------
# MANEJO DE UBICACIÓN
# ----------------------------
async def location_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.location:
        return

    loc = update.message.location
    user = update.effective_user
    user_id_str = str(user.id)
    mode = context.user_data.get("mode")
    step = context.user_data.get("step")

    # 1) Usuario enviando ubicación
    if mode == "usuario" and step == "ask_location":
        context.user_data["data"]["lat"] = loc.latitude
        context.user_data["data"]["lon"] = loc.longitude
        context.user_data["data"]["direccion_texto"] = None
        context.user_data["step"] = "ask_destination"
        await update.message.reply_text(
            "📍 Ubicación recibida.\n\nAhora escribe el destino:",
            parse_mode="Markdown"
        )
        return

    # 2) Móvil enviando ubicación
    mobiles = get_mobiles()
    if user_id_str in mobiles:
        m = mobiles[user_id_str]
        m["lat"] = loc.latitude
        m["lon"] = loc.longitude
        mobiles[user_id_str] = m
        save_mobiles(mobiles)

        await update.message.reply_text(
            "📍 Ubicación guardada correctamente.",
            reply_markup=movil_menu_keyboard
        )
        return
    await update.message.reply_text(
        "No entiendo eso, usa el menú por favor.",
    )
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

