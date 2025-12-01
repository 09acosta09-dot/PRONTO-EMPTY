# PRONTO - Versión 2.1 Profesional (Webhook para Railway)
# - Webhook en Railway usando python-telegram-bot v20+
# - Token tomado desde variable de entorno BOT_TOKEN
# - Menú Usuario / Móvil / Administrador
# - Registro de móviles SOLO por administrador (con datos completos)
# - Rangos de 30 móviles por servicio (PXXX) y luego T/D/C/E + número continuo
# - Asignación del servicio al móvil más cercano (GPS)
# - Botón "Reservar servicio" y mensaje al cliente con el código del móvil
# - Menú de administrador: registrar móviles, ver móviles, desactivar, aprobar pagos, ver servicios
# - Cambio "Trasteos" -> "Camionetas"
# - Hora correcta de Colombia

import os
import json
import math
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

# Canales por servicio (para control del admin)
CHANNEL_TAXI = -1002697357566
CHANNEL_DOMICILIOS = -1002503403579
CHANNEL_CAMIONETAS = -1002662309590
CHANNEL_ESPECIAL = -1002688723492

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
        "label_movil": "Taxi",
        "channel_id": CHANNEL_TAXI,
        "prefix_overflow": "T",
        "base_start": 1,   # P001-P030
    },
    "Domicilios": {
        "label_user": "📦 Domicilios",
        "label_movil": "Domicilios",
        "channel_id": CHANNEL_DOMICILIOS,
        "prefix_overflow": "D",
        "base_start": 31,  # P031-P060
    },
    "Camionetas": {
        "label_user": "🚚 Camionetas",
        "label_movil": "Camionetas",
        "channel_id": CHANNEL_CAMIONETAS,
        "prefix_overflow": "C",
        "base_start": 61,  # P061-P090
    },
    "Especial": {
        "label_user": "♿ Especial",
        "label_movil": "Especial",
        "channel_id": CHANNEL_ESPECIAL,
        "prefix_overflow": "E",
        "base_start": 91,  # P091-P120
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

def now_colombia_str():
    tz = timezone(timedelta(hours=-5))  # Colombia UTC-5
    return datetime.now(tz).strftime("%Y-%m-%d %H:%M:%S")


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

movil_menu_keyboard = ReplyKeyboardMarkup(
    [
        [KeyboardButton("📍 Enviar ubicación actual")],
        [KeyboardButton("🔚 Finalizar jornada")],
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

movil_service_keyboard = ReplyKeyboardMarkup(
    [
        [KeyboardButton("Taxi")],
        [KeyboardButton("Domicilios")],
        [KeyboardButton("Camionetas")],
        [KeyboardButton("Especial")],
        [KeyboardButton("⬅ Cancelar registro")],
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
# ASIGNACIÓN DE CÓDIGOS PARA MÓVILES
# ----------------------------

def parse_code_number(codigo: str):
    if not codigo or len(codigo) < 4:
        return None
    try:
        return int(codigo[1:])
    except ValueError:
        return None


def asignar_codigo_movil(servicio: str) -> str:
    mobiles = get_mobiles()
    info = SERVICE_INFO[servicio]
    base_start = info["base_start"]
    base_end = base_start + 29  # 30 cupos

    count_P = 0
    used_numbers_in_range = set()
    all_numbers = []

    for m in mobiles.values():
        codigo = m.get("codigo")
        num = parse_code_number(codigo)
        if num is None:
            continue
        all_numbers.append(num)
        if codigo.startswith("P") and base_start <= num <= base_end and m.get("servicio") == servicio:
            used_numbers_in_range.add(num)
            count_P += 1

    if count_P < 30:
        for posible_num in range(base_start, base_end + 1):
            if posible_num not in used_numbers_in_range:
                return f"P{posible_num:03d}"

    max_num = max(all_numbers) if all_numbers else 120
    siguiente = max(max_num + 1, 121)
    prefijo = info["prefix_overflow"]
    return f"{prefijo}{siguiente:03d}"


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
        if sid and sid.startswith("S"):
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
        "Estamos notificando a un móvil cercano para que tome tu servicio."
    )

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
                    "✅ Reservar servicio",
                    callback_data=f"RESERVAR|{service_id}",
                )
            ]
        ]
    )

    bot = context.bot

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
            text=resumen_canal,
            parse_mode="Markdown",
        )
    except Exception:
        pass

    context.user_data.clear()


def seleccionar_movil_mas_cercano(servicio: str, lat_cliente, lon_cliente):
    mobiles = get_mobiles()
    candidatos = []

    for chat_id_str, m in mobiles.items():
        if not m.get("activo"):
            continue
        if not m.get("pago_aprobado"):
            continue
        if m.get("servicio") != servicio:
            continue
        m_lat = m.get("lat")
        m_lon = m.get("lon")
        if m_lat is None or m_lon is None:
            continue

        if lat_cliente is not None and lon_cliente is not None:
            dist = haversine_distance(lat_cliente, lon_cliente, m_lat, m_lon)
        else:
            dist = 0.0

        candidatos.append(
            {
                "chat_id": int(chat_id_str),
                "codigo": m.get("codigo"),
                "servicio": servicio,
                "distancia": dist,
            }
        )

    if not candidatos:
        return None

    candidatos.sort(key=lambda x: x["distancia"])
    return candidatos[0]


# ----------------------------
# CALLBACKS (RESERVA Y PAGOS)
# ----------------------------

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    bot = context.bot

    if data.startswith("RESERVAR|"):
        service_id = data.split("|", 1)[1]
        chat_id = query.message.chat.id

        services = get_services()
        servicio_data = None
        for s in services.values():
            if s.get("id") == service_id:
                servicio_data = s
                break

        if not servicio_data:
            await query.edit_message_text(
                "Este servicio ya no está disponible o ha sido eliminado."
            )
            return

        if servicio_data.get("status") != "pendiente":
            await query.edit_message_text(
                "Este servicio ya fue tomado por otro móvil."
            )
            return

        movil_chat_id = servicio_data.get("movil_chat_id")
        movil_codigo = servicio_data.get("movil_codigo")
        if movil_chat_id != chat_id:
            await query.edit_message_text(
                "Este servicio no está asignado a tu móvil."
            )
            return

        servicio_data["status"] = "reservado"
        servicio_data["hora_reserva"] = now_colombia_str()
        services[servicio_data["id"]] = servicio_data
        save_services(services)

        texto_movil = (
            f"✅ Has *reservado* el servicio {service_id}.\n\n"
            f"Dirígete al cliente:\n"
            f"👤 {servicio_data.get('nombre','')}\n"
            f"📞 {servicio_data.get('telefono','')}\n"
            f"📍 Destino: {servicio_data.get('destino','')}\n"
        )
        if servicio_data.get("servicio") == "Camionetas":
            texto_movil += f"📦 Tipo de carga: {servicio_data.get('carga','')}\n"
        texto_movil += f"\n⏰ Hora de reserva: {servicio_data.get('hora_reserva','')} (Colombia)"

        await query.edit_message_text(
            texto_movil,
            parse_mode="Markdown",
        )

        user_chat_id = servicio_data.get("user_chat_id")
        if user_chat_id:
            try:
                await bot.send_message(
                    chat_id=user_chat_id,
                    text=(
                        f"✅ Tu servicio ha sido asignado.\n\n"
                        f"El móvil *{movil_codigo}* llegará pronto a tu ubicación.\n"
                        f"Por favor mantén tu teléfono disponible."
                    ),
                    parse_mode="Markdown",
                )
            except Exception:
                pass

        servicio = servicio_data.get("servicio")
        channel_id = SERVICE_INFO[servicio]["channel_id"]
        resumen = (
            f"✅ *Servicio reservado*\n"
            f"🆔 Servicio: *{service_id}*\n"
            f"🚗 Móvil: *{movil_codigo}*\n"
            f"👤 Cliente: *{servicio_data.get('nombre','')}*\n"
            f"📍 Destino: *{servicio_data.get('destino','')}*\n"
            f"⏰ Hora reserva: *{servicio_data.get('hora_reserva','')}* (Colombia)"
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

    if data.startswith("APROBAR_PAGO|"):
        codigo = data.split("|", 1)[1]
        mobiles = get_mobiles()
        target_key = None
        for chat_id_str, m in mobiles.items():
            if m.get("codigo", "").upper() == codigo.upper():
                target_key = chat_id_str
                break

        if not target_key:
            await query.edit_message_text("No encontré ese móvil. Es posible que haya sido eliminado.")
            return

        mobiles[target_key]["pago_aprobado"] = True
        save_mobiles(mobiles)

        await query.edit_message_text(
            f"✅ El pago del móvil *{codigo}* ha sido aprobado.",
            parse_mode="Markdown",
        )

        try:
            await bot.send_message(
                chat_id=int(target_key),
                text=(
                    "💰 Tu pago ha sido *aprobado*.\n\n"
                    "Ya puedes enviar tu ubicación para iniciar jornada "
                    "y recibir servicios."
                ),
                parse_mode="Markdown",
            )
        except Exception:
            pass

        if "pending_payment_code" in context.user_data:
            del context.user_data["pending_payment_code"]

        return

    if data.startswith("CANCELAR_PAGO|"):
        await query.edit_message_text("Operación cancelada.")
        if "pending_payment_code" in context.user_data:
            del context.user_data["pending_payment_code"]
        return


# ----------------------------
# MANEJO DE TEXTO
# ----------------------------

async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return

    text = update.message.text.strip()
    user = update.effective_user
    user_id = user.id

    if text == "⬅ Volver al inicio":
        context.user_data.clear()
        await update.message.reply_text(
            "Volviendo al inicio.\n\nElige una opción:",
            reply_markup=main_keyboard,
        )
        return

    if text == "Usuario":
        await handle_usuario_option(update, context)
        return

    if text == "Móvil":
        context.user_data["mode"] = "movil"
        await update.message.reply_text(
            "Menú de móviles.\n\n"
            "Si ya estás registrado por el administrador, envía tu ubicación para iniciar jornada.",
            reply_markup=movil_menu_keyboard,
        )
        return

    if text == "Administrador":
        if user_id not in ADMIN_IDS:
            await update.message.reply_text(
                "❌ No tienes permisos para acceder al panel de administración."
            )
            return
        context.user_data["mode"] = "admin"
        context.user_data["admin_step"] = None
        await update.message.reply_text(
            "👮 Panel de administración.\n\nElige una opción:",
            reply_markup=admin_keyboard,
        )
        return

    mode = context.user_data.get("mode")

    # ------------------- MÓVIL -------------------
    if mode == "movil":
        if text == "📍 Enviar ubicación actual":
            await update.message.reply_text(
                "Por favor comparte tu ubicación desde Telegram (icono del clip ➜ Ubicación) "
                "o usa el botón de ubicación si aparece."
            )
            return

        if text == "🔚 Finalizar jornada":
            mobiles = get_mobiles()
            user_id_str = str(user.id)
            if user_id_str in mobiles:
                mobiles[user_id_str]["activo"] = False
                save_mobiles(mobiles)
                await update.message.reply_text(
                    "Has finalizado tu jornada. Ya no recibirás nuevos servicios.",
                    reply_markup=movil_menu_keyboard,
                )
            else:
                await update.message.reply_text(
                    "No estás registrado como móvil. Pide al administrador que te registre.",
                    reply_markup=movil_menu_keyboard,
                )
            return

        if text == "⬅ Cancelar registro":
            context.user_data["movil_step"] = None
            await update.message.reply_text(
                "Registro cancelado.",
                reply_markup=movil_menu_keyboard,
            )
            return

    # ------------------- ADMINISTRADOR -------------------
    if mode == "admin" and user_id in ADMIN_IDS:
        admin_step = context.user_data.get("admin_step")

        if text == "📲 Registrar móvil":
            context.user_data["admin_step"] = "reg_name"
            context.user_data["reg_movil"] = {}
            await update.message.reply_text(
                "📲 Registro de móvil.\n\n"
                "Escribe el *nombre completo* del conductor:",
                parse_mode="Markdown",
            )
            return

        if text == "🚗 Ver móviles registrados":
            mobiles = get_mobiles()
            if not mobiles:
                await update.message.reply_text("No hay móviles registrados todavía.")
                return
            lines = ["📋 *Móviles registrados:*"]
            for m in mobiles.values():
                codigo = m.get("codigo", "SIN-COD")
                nombre = m.get("nombre", "Sin nombre")
                servicio = m.get("servicio", "Sin servicio")
                activo = "✅ Activo" if m.get("activo") else "⛔ Inactivo"
                pago = "💰 Pago OK" if m.get("pago_aprobado") else "💸 Pendiente"
                lines.append(f"- {codigo} – {nombre} – {servicio} – {activo} – {pago}")
            msg = "\n".join(lines)
            await update.message.reply_text(msg, parse_mode="Markdown")
            return

        if text == "🗑 Desactivar móvil":
            context.user_data["admin_step"] = "deactivate_code"
            await update.message.reply_text(
                "Escribe el *código del móvil* que deseas desactivar (ej: P001, T121, C090):",
                parse_mode="Markdown",
            )
            return

        if text == "💰 Aprobar pagos":
            context.user_data["admin_step"] = "approve_payment_code"
            await update.message.reply_text(
                "Escribe el *código del móvil* cuyo pago deseas aprobar (ej: P001, T121, C090):",
                parse_mode="Markdown",
            )
            return

        if text == "📋 Ver servicios activos":
            services = get_services()
            activos = [
                s for s in services.values()
                if s.get("status") in ["pendiente", "reservado"]
            ]
            if not activos:
                await update.message.reply_text("No hay servicios activos en este momento.")
                return
            lines = ["📋 *Servicios activos:*"]
            for s in activos:
                sid = s.get("id", "")
                serv = s.get("servicio", "")
                nombre = s.get("nombre", "")
                destino = s.get("destino", "")
                status = s.get("status", "")
                movil = s.get("movil_codigo", "SIN MÓVIL")
                lines.append(f"- {sid} – {serv} – {nombre} – Destino: {destino} – Estado: {status} – Móvil: {movil}")
            await update.message.reply_text("\n".join(lines), parse_mode="Markdown")
            return

        # Flujo registro móviles
        if admin_step == "reg_name":
            context.user_data["reg_movil"]["nombre"] = text
            context.user_data["admin_step"] = "reg_cedula"
            await update.message.reply_text(
                "✍ Ahora escribe la *cédula* del conductor:",
                parse_mode="Markdown",
            )
            return

        if admin_step == "reg_cedula":
            context.user_data["reg_movil"]["cedula"] = text
            context.user_data["admin_step"] = "reg_service"
            await update.message.reply_text(
                "🚗 Indica el *tipo de servicio* del móvil:\n"
                "- Taxi\n- Domicilios\n- Camionetas\n- Especial\n\n"
                "Escríbelo tal cual.",
                parse_mode="Markdown",
            )
            return

        if admin_step == "reg_service":
            servicio = text.strip()
            if servicio not in ["Taxi", "Domicilios", "Camionetas", "Especial"]:
                await update.message.reply_text(
                    "Servicio no válido. Escribe: Taxi, Domicilios, Camionetas o Especial."
                )
                return
            context.user_data["reg_movil"]["servicio"] = servicio
            context.user_data["admin_step"] = "reg_placa"
            await update.message.reply_text(
                "🚘 Escribe la *placa* del vehículo:",
                parse_mode="Markdown",
            )
            return

        if admin_step == "reg_placa":
            context.user_data["reg_movil"]["placa"] = text
            context.user_data["admin_step"] = "reg_marca"
            await update.message.reply_text(
                "🚘 Escribe la *marca* del vehículo:",
                parse_mode="Markdown",
            )
            return

        if admin_step == "reg_marca":
            context.user_data["reg_movil"]["marca"] = text
            context.user_data["admin_step"] = "reg_modelo"
            await update.message.reply_text(
                "🚘 Escribe el *modelo* del vehículo (ej: 2015):",
                parse_mode="Markdown",
            )
            return

        if admin_step == "reg_modelo":
            context.user_data["reg_movil"]["modelo"] = text
            context.user_data["admin_step"] = "reg_chatid"
            await update.message.reply_text(
                "📲 Ahora escribe el *chat ID* del conductor (número que te envía él):",
                parse_mode="Markdown",
            )
            return

        if admin_step == "reg_chatid":
            reg = context.user_data.get("reg_movil", {})
            try:
                chat_id_movil = int(text)
            except ValueError:
                await update.message.reply_text(
                    "El chat ID debe ser un número. Pide al conductor que te lo envíe correctamente."
                )
                return

            servicio = reg.get("servicio")
            if not servicio:
                await update.message.reply_text("Error interno: servicio no definido. Vuelve a intentar registrar.")
                context.user_data["admin_step"] = None
                return

            codigo = asignar_codigo_movil(servicio)
            mobiles = get_mobiles()
            mobiles[str(chat_id_movil)] = {
                "codigo": codigo,
                "servicio": servicio,
                "lat": None,
                "lon": None,
                "activo": False,
                "nombre": reg.get("nombre", ""),
                "cedula": reg.get("cedula", ""),
                "placa": reg.get("placa", ""),
                "marca": reg.get("marca", ""),
                "modelo": reg.get("modelo", ""),
                "pago_aprobado": False,
            }
            save_mobiles(mobiles)

            context.user_data["admin_step"] = None
            context.user_data["reg_movil"] = {}

            await update.message.reply_text(
                f"✅ Móvil registrado correctamente.\n\n"
                f"Conductor: *{mobiles[str(chat_id_movil)]['nombre']}*\n"
                f"Servicio: *{servicio}*\n"
                f"Código asignado: *{codigo}*\n\n"
                f"Debe enviar su ubicación desde el menú 'Móvil' para iniciar jornada "
                f"(y una vez le apruebes el pago).",
                parse_mode="Markdown",
            )
            return

        # Desactivar móvil
        if admin_step == "deactivate_code":
            codigo = text.strip().upper()
            mobiles = get_mobiles()
            target_key = None
            for chat_id_str, m in mobiles.items():
                if m.get("codigo", "").upper() == codigo:
                    target_key = chat_id_str
                    break

            if not target_key:
                await update.message.reply_text(
                    "No encontré un móvil con ese código. Verifica y vuelve a intentarlo."
                )
                return

            mobiles[target_key]["activo"] = False
            save_mobiles(mobiles)
            context.user_data["admin_step"] = None

            await update.message.reply_text(
                f"🛑 El móvil *{codigo}* ha sido desactivado.",
                parse_mode="Markdown",
            )
            return

        # Aprobar pagos (pedir código)
        if admin_step == "approve_payment_code":
            codigo = text.strip().upper()
            mobiles = get_mobiles()
            target = None
            for chat_id_str, m in mobiles.items():
                if m.get("codigo", "").upper() == codigo:
                    target = m
                    break

            if not target:
                await update.message.reply_text(
                    "No encontré un móvil con ese código. Verifica y vuelve a intentarlo."
                )
                return

            context.user_data["pending_payment_code"] = codigo

            nombre = target.get("nombre", "Sin nombre")
            servicio = target.get("servicio", "Sin servicio")
            cedula = target.get("cedula", "Sin cédula")
            placa = target.get("placa", "Sin placa")
            marca = target.get("marca", "Sin marca")
            modelo = target.get("modelo", "Sin modelo")
            pago = "💰 Pago OK" if target.get("pago_aprobado") else "💸 Pendiente"

            texto = (
                "📋 *Información del móvil:*\n\n"
                f"🔢 Código: *{codigo}*\n"
                f"👤 Nombre: *{nombre}*\n"
                f"🧾 Cédula: *{cedula}*\n"
                f"🚗 Servicio: *{servicio}*\n"
                f"🚘 Placa: *{placa}*\n"
                f"🚘 Marca: *{marca}*\n"
                f"🚘 Modelo: *{modelo}*\n"
                f"💸 Estado de pago: {pago}\n\n"
                "¿Deseas *aprobar el pago* de este móvil?"
            )

            keyboard = InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            "✅ Aprobar pago", callback_data=f"APROBAR_PAGO|{codigo}"
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            "❌ Cancelar", callback_data=f"CANCELAR_PAGO|{codigo}"
                        )
                    ],
                ]
            )

            await update.message.reply_text(
                texto,
                parse_mode="Markdown",
                reply_markup=keyboard,
            )
            return

        await update.message.reply_text(
            "Usa las opciones del menú de administrador, por favor.",
            reply_markup=admin_keyboard,
        )
        return

    # ------------------- USUARIO -------------------
    if mode == "usuario":
        step = context.user_data.get("step")

        if step == "choose_service":
            for servicio, info in SERVICE_INFO.items():
                if text == info["label_user"]:
                    await handle_usuario_service_choice(update, context, servicio)
                    return
            if text == "⬅ Volver al inicio":
                context.user_data.clear()
                await update.message.reply_text(
                    "Volviendo al inicio.",
                    reply_markup=main_keyboard,
                )
                return
            await update.message.reply_text(
                "Por favor selecciona una de las opciones del menú.",
                reply_markup=user_service_keyboard,
            )
            return

        if step == "ask_name":
            context.user_data.setdefault("data", {})["nombre"] = text
            context.user_data["step"] = "ask_phone"
            await update.message.reply_text(
                "📞 Ahora escribe tu *número de teléfono*:",
                parse_mode="Markdown",
            )
            return

        if step == "ask_phone":
            context.user_data["data"]["telefono"] = text
            context.user_data["step"] = "ask_location"
            kb = build_location_keyboard()
            await update.message.reply_text(
                "📍 Comparte tu ubicación GPS con el botón o escribe tu dirección actual:",
                reply_markup=kb,
            )
            return

        if step == "ask_location":
            context.user_data["data"]["direccion_texto"] = text
            context.user_data["data"]["lat"] = None
            context.user_data["data"]["lon"] = None
            context.user_data["step"] = "ask_destination"
            await update.message.reply_text(
                "📍 Ahora escribe el *destino o dirección* a donde necesitas ir o enviar:",
                parse_mode="Markdown",
            )
            return

        if step == "ask_destination":
            context.user_data["data"]["destino"] = text
            servicio = context.user_data.get("servicio")
            if servicio == "Camionetas":
                context.user_data["step"] = "ask_carga"
                await update.message.reply_text(
                    "📦 ¿Qué tipo de carga necesitas transportar?\n"
                    "(Ej: muebles, electrodomésticos, trasteo de apartamento, etc.)"
                )
                return
            else:
                await finalize_user_request(update, context)
                return

        if step == "ask_carga":
            context.user_data["data"]["carga"] = text
            await finalize_user_request(update, context)
            return

    await update.message.reply_text(
        "No entiendo ese mensaje. Por favor usa el menú en pantalla.",
    )


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

    if mode == "usuario" and step == "ask_location":
        context.user_data["data"]["lat"] = loc.latitude
        context.user_data["data"]["lon"] = loc.longitude
        context.user_data["data"]["direccion_texto"] = None
        context.user_data["step"] = "ask_destination"
        await update.message.reply_text(
            "✅ Ubicación recibida.\n\n"
            "Ahora escribe el *destino o dirección* a donde necesitas ir o enviar:",
            parse_mode="Markdown",
        )
        return

    mobiles = get_mobiles()
    if user_id_str in mobiles:
        if not mobiles[user_id_str].get("pago_aprobado", False):
            await update.message.reply_text(
                "💸 Tu pago aún no ha sido aprobado por el administrador.\n"
                "Habla con el administrador para que apruebe tu pago y luego envía de nuevo tu ubicación."
            )
            return

        mobiles[user_id_str]["lat"] = loc.latitude
        mobiles[user_id_str]["lon"] = loc.longitude
        mobiles[user_id_str]["activo"] = True
        save_mobiles(mobiles)

        servicio = mobiles[user_id_str].get("servicio", "Desconocido")
        codigo = mobiles[user_id_str].get("codigo", "SIN-CODIGO")

        await update.message.reply_text(
            f"✅ Ubicación registrada.\n\n"
            f"Ahora estás *activo* como móvil de *{servicio}*.\n"
            f"Código de móvil: *{codigo}*.\n\n"
            "Recibirás servicios cercanos a tu ubicación.",
            parse_mode="Markdown",
            reply_markup=movil_menu_keyboard,
        )
        return

    await update.message.reply_text(
        "He recibido tu ubicación, pero no sé en qué contexto usarla.\n\n"
        "Si eres cliente, usa la opción 'Usuario'.\n"
        "Si eres móvil, pide al administrador que te registre en el sistema."
    )


# ----------------------------
# MAIN (WEBHOOK)
# ----------------------------

def main():
    application = ApplicationBuilder().token(TOKEN).build()

    application.add_handler(CommandHandler("start", start))
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
