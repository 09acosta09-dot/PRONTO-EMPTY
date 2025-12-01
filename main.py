# PRONTO - Versión avanzada 2.0
# Un solo archivo - python-telegram-bot v20+
# - Formulario único para todos los servicios
# - Registro de móviles con rangos de 30 (PXXX) y luego T/D/C/E + numeración continua
# - Asignación del servicio al móvil más cercano (GPS)
# - Botón "Reservar servicio" y mensaje al cliente con el código del móvil
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

TOKEN = "7668998247:AAECr_Y1sk6P2uOWkw6ZoJMPdmT_EBksAcA"  

ADMIN_IDS = [1741298723, 7076796229]

# Canales por servicio (si quieres que el admin vea los movimientos)
CHANNEL_TAXI = -1002697357566
CHANNEL_DOMICILIOS = -1002503403579
CHANNEL_CAMIONETAS = -1002662309590
CHANNEL_ESPECIAL = -1002688723492

MOBILES_FILE = "mobiles.json"
SERVICES_FILE = "services.json"

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
    # Colombia UTC-5 sin cambio de horario
    tz = timezone(timedelta(hours=-5))
    return datetime.now(tz).strftime("%Y-%m-%d %H:%M:%S")


def haversine_distance(lat1, lon1, lat2, lon2):
    # Distancia en km entre dos puntos GPS
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
        [KeyboardButton("📲 Registrarme como móvil")],
        [KeyboardButton("📍 Enviar ubicación actual")],
        [KeyboardButton("🔚 Finalizar jornada")],
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
    await update.message.reply_text(
        "👋 Bienvenido a PRONTO.\n\nElige una opción:",
        reply_markup=main_keyboard,
    )


# ----------------------------
# REGISTRO DE MÓVILES Y CÓDIGOS
# ----------------------------

def parse_code_number(codigo: str) -> int | None:
    """
    Extrae la parte numérica de un código tipo P001, T123, D145, etc.
    """
    if not codigo or len(codigo) < 4:
        return None
    try:
        return int(codigo[1:])
    except ValueError:
        return None


def asignar_codigo_movil(servicio: str) -> str:
    """
    Asigna código al móvil según las reglas:
    - Cada servicio tiene 30 cupos iniciales con PXXX dentro de un rango específico.
    - Ej: Taxi: P001-P030, Domicilios: P031-P060, Camionetas: P061-P090, Especial: P091-P120
    - Si ya se llenaron los 30 cupos de ese servicio con PXXX, se usa:
        TXXX, DXXX, CXXX o EXXX
      donde XXX es el número que sigue después del mayor número usado (mínimo 121).
    """
    mobiles = get_mobiles()
    info = SERVICE_INFO[servicio]
    base_start = info["base_start"]
    base_end = base_start + 29  # 30 cupos

    # Ver cuántos PXXX hay en el rango de ese servicio
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

    # Si aún hay espacio en los 30 iniciales
    if count_P < 30:
        # Buscar el número disponible dentro del rango
        for posible_num in range(base_start, base_end + 1):
            if posible_num not in used_numbers_in_range:
                return f"P{posible_num:03d}"

    # Si ya se llenaron los 30, usar el prefijo del servicio
    max_num = max(all_numbers) if all_numbers else 120
    siguiente = max(max_num + 1, 121)
    prefijo = info["prefix_overflow"]
    return f"{prefijo}{siguiente:03d}"


async def registrar_movil(update: Update, context: ContextTypes.DEFAULT_TYPE, servicio: str):
    user = update.effective_user
    user_id_str = str(user.id)
    mobiles = get_mobiles()

    if user_id_str in mobiles:
        # Ya existe, solo actualizar servicio
        mobiles[user_id_str]["servicio"] = servicio
        codigo = mobiles[user_id_str]["codigo"]
        save_mobiles(mobiles)
        await update.message.reply_text(
            f"✅ Ya estabas registrado.\n\n"
            f"Ahora quedas asignado al servicio: *{servicio}*\n"
            f"Tu código de móvil es: *{codigo}*.\n\n"
            "Ahora envía tu ubicación con el botón '📍 Enviar ubicación actual' para quedar disponible.",
            parse_mode="Markdown",
            reply_markup=movil_menu_keyboard,
        )
        return

    # Asignar código nuevo
    codigo = asignar_codigo_movil(servicio)
    mobiles[user_id_str] = {
        "codigo": codigo,
        "servicio": servicio,
        "lat": None,
        "lon": None,
        "activo": False,
        "nombre": user.full_name,
    }
    save_mobiles(mobiles)

    await update.message.reply_text(
        f"✅ Te has registrado como móvil de *{servicio}*.\n\n"
        f"Tu código de móvil es: *{codigo}*.\n\n"
        "Ahora envía tu ubicación con el botón '📍 Enviar ubicación actual' para quedar disponible.",
        parse_mode="Markdown",
        reply_markup=movil_menu_keyboard,
    )


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


async def location_keyboard():
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
    Cuando ya tenemos todos los datos del usuario (nombre, tel, ubicación opcional, destino, carga) se crea
    el servicio, se busca el móvil más cercano y se envía el servicio.
    """
    user = update.effective_user
    chat_id = update.effective_chat.id
    data = context.user_data.get("data", {})
    servicio = context.user_data.get("servicio")

    if not servicio or not data:
        await update.message.reply_text("Ocurrió un problema con la solicitud. Intenta de nuevo con 'Usuario'.")
        return

    # Hora
    hora = now_colombia_str()
    data["hora"] = hora
    data["servicio"] = servicio
    data["user_chat_id"] = chat_id
    data["user_id"] = user.id

    # Guardar servicio y asignar a móvil
    services = get_services()

    # Crear ID de servicio S00001, S00002, etc.
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

    # Buscar móvil más cercano
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

    # Guardar en archivo
    services[service_id] = data
    save_services(services)

    # Mensaje al usuario: hemos encontrado móvil
    await update.message.reply_text(
        "✅ Tu solicitud ha sido registrada.\n"
        "Estamos notificando a un móvil cercano para que tome tu servicio."
    )

    # Mensaje al móvil
    texto_movil = f"🚨 *Nuevo servicio de {movil_servicio}*\n\n"
    texto_movil += f"🆔 Código de servicio: *{service_id}*\n"
    texto_movil += f"👤 Cliente: *{data.get('nombre','(sin nombre)')}*\n"
    texto_movil += f"📞 Teléfono: *{data.get('telefono','(sin teléfono)')}*\n"
    texto_movil += f"📍 Destino / Dirección: *{data.get('destino','(sin destino)')}*\n"
    if movil_servicio == "Camionetas":
        texto_movil += f"📦 Tipo de carga: *{data.get('carga','(no especificada)')}*\n"
    if data.get("lat") is not None and data.get("lon") is not None:
        texto_movil += f"\n🌎 El cliente compartió ubicación GPS.\n"

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

    application = ApplicationBuilder().token(TOKEN).build()  # solo para obtener el bot en modo async
    bot = application.bot

    try:
        await bot.send_message(
            chat_id=movil_chat_id,
            text=texto_movil,
            reply_markup=keyboard,
            parse_mode="Markdown",
        )
    except Exception:
        # Si por alguna razón no se puede enviar al móvil
        await update.message.reply_text(
            "Hubo un problema notificando al móvil. Intenta de nuevo más tarde."
        )
        return

    # Enviar también resumen al canal correspondiente (para control del admin)
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
        pass  # No es crítico si falla

    # Limpiar estado de usuario
    context.user_data.clear()


def seleccionar_movil_mas_cercano(servicio: str, lat_cliente, lon_cliente):
    """
    Selecciona el móvil más cercano que esté activo y tenga el mismo tipo de servicio.
    Si el cliente no envía ubicación, simplemente toma cualquiera activo.
    """
    mobiles = get_mobiles()
    candidatos = []

    for chat_id_str, m in mobiles.items():
        if not m.get("activo"):
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
            dist = 0.0  # si no hay ubicación del cliente, no calculamos distancia real

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

    # Ordenar por distancia
    candidatos.sort(key=lambda x: x["distancia"])
    return candidatos[0]


# ----------------------------
# CALLBACK RESERVAR SERVICIO
# ----------------------------

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data.startswith("RESERVAR|"):
        service_id = data.split("|", 1)[1]
        user = query.from_user
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

        # Verificar que el móvil que presiona sea el asignado
        movil_chat_id = servicio_data.get("movil_chat_id")
        movil_codigo = servicio_data.get("movil_codigo")
        if movil_chat_id != chat_id:
            await query.edit_message_text(
                "Este servicio no está asignado a tu móvil."
            )
            return

        # Marcar como reservado
        servicio_data["status"] = "reservado"
        servicio_data["hora_reserva"] = now_colombia_str()
        services[servicio_data["id"]] = servicio_data
        save_services(services)

        # Mensaje al móvil
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

        # Mensaje al cliente
        user_chat_id = servicio_data.get("user_chat_id")
        if user_chat_id:
            application = ApplicationBuilder().token(TOKEN).build()
            bot = application.bot
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

        # Mensaje al canal/admin
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
            application = ApplicationBuilder().token(TOKEN).build()
            bot = application.bot
            await bot.send_message(
                chat_id=channel_id,
                text=resumen,
                parse_mode="Markdown",
            )
        except Exception:
            pass


# ----------------------------
# MANEJO DE TEXTO GENERAL
# ----------------------------

async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return

    text = update.message.text.strip()
    user = update.effective_user

    # Volver al inicio
    if text == "⬅ Volver al inicio":
        context.user_data.clear()
        await update.message.reply_text(
            "Volviendo al inicio.\n\nElige una opción:",
            reply_markup=main_keyboard,
        )
        return

    # Entrar como Usuario
    if text == "Usuario":
        await handle_usuario_option(update, context)
        return

    # Modo Móvil
    if text == "Móvil":
        context.user_data["mode"] = "movil"
        await update.message.reply_text(
            "Menú de móviles. Elige una opción:",
            reply_markup=movil_menu_keyboard,
        )
        return

    # Modo Administrador (simple por ahora)
    if text == "Administrador":
        context.user_data["mode"] = "admin"
        mobiles = get_mobiles()
        activos = [m for m in mobiles.values() if m.get("activo")]
        await update.message.reply_text(
            f"👮 Panel administrador básico:\n\n"
            f"📱 Móviles registrados: {len(mobiles)}\n"
            f"✅ Móviles activos ahora: {len(activos)}\n\n"
            "En próximas versiones se ampliarán más funciones para administrador.",
            reply_markup=main_keyboard,
        )
        return

    mode = context.user_data.get("mode")

    # ------------------- MÓVIL -------------------
    if mode == "movil":
        if text == "📲 Registrarme como móvil":
            context.user_data["movil_step"] = "ask_service"
            await update.message.reply_text(
                "¿Para qué servicio trabajas?",
                reply_markup=movil_service_keyboard,
            )
            return

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
                    "No estás registrado como móvil todavía.",
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

        # Respuesta al paso de elegir servicio
        if context.user_data.get("movil_step") == "ask_service":
            if text in ["Taxi", "Domicilios", "Camionetas", "Especial"]:
                await registrar_movil(update, context, servicio=text)
                context.user_data["movil_step"] = None
                return
            else:
                await update.message.reply_text(
                    "Por favor elige una opción válida de servicio.",
                    reply_markup=movil_service_keyboard,
                )
                return

    # ------------------- USUARIO -------------------
    if mode == "usuario":
        step = context.user_data.get("step")

        # Elegir servicio
        if step == "choose_service":
            # Comparar con las etiquetas de usuario
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

        # Nombre
        if step == "ask_name":
            context.user_data.setdefault("data", {})["nombre"] = text
            context.user_data["step"] = "ask_phone"
            await update.message.reply_text(
                "📞 Ahora escribe tu *número de teléfono*:",
                parse_mode="Markdown",
            )
            return

        # Teléfono
        if step == "ask_phone":
            context.user_data["data"]["telefono"] = text
            context.user_data["step"] = "ask_location"
            kb = await location_keyboard()
            await update.message.reply_text(
                "📍 Comparte tu ubicación GPS con el botón o escribe tu dirección actual:",
                reply_markup=kb,
            )
            return

        # Ubicación (si la escribe en texto)
        if step == "ask_location":
            # El usuario escribió algo como dirección
            context.user_data["data"]["direccion_texto"] = text
            context.user_data["data"]["lat"] = None
            context.user_data["data"]["lon"] = None

            context.user_data["step"] = "ask_destination"
            await update.message.reply_text(
                "📍 Ahora escribe el *destino o dirección* a donde necesitas ir o enviar:",
                parse_mode="Markdown",
            )
            return

        # Destino
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
                # Finalizar para servicios normales
                await finalize_user_request(update, context)
                return

        # Tipo de carga (solo Camionetas)
        if step == "ask_carga":
            context.user_data["data"]["carga"] = text
            await finalize_user_request(update, context)
            return

    # Si nada de lo anterior coincide
    await update.message.reply_text(
        "No entiendo ese mensaje. Por favor usa el menú en pantalla."
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

    # 1) Caso usuario enviando ubicación en el flujo de solicitud
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

    # 2) Caso móvil enviando ubicación para iniciar jornada
    mobiles = get_mobiles()
    if user_id_str in mobiles:
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

    # 3) Usuario que manda ubicación sin estar en flujo ni ser móvil
    await update.message.reply_text(
        "He recibido tu ubicación, pero no sé en qué contexto usarla.\n\n"
        "Si eres cliente, usa la opción 'Usuario'.\n"
        "Si eres móvil, primero regístrate en el menú 'Móvil'."
    )


# ----------------------------
# MAIN
# ----------------------------

def main():
    application = ApplicationBuilder().token(TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(button_callback))

    application.add_handler(MessageHandler(filters.LOCATION, location_handler))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))

    application.run_polling()


if __name__ == "__main__":
    main()
