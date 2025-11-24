import logging
from telegram import (
    Update,
    ReplyKeyboardMarkup,
    KeyboardButton,
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# ---------------------------
# CONFIG
# ---------------------------
TOKEN = "7668998247:AAGR7gxbJSfF-yuWtIOxMEFI1AYFinMJygg"

# Canales (IDs confirmados, con -100...)
CHANNEL_TAXI = -1002697357566
CHANNEL_DOMICILIOS = -1002503403579
CHANNEL_TRASTEOS = -1002662309590
CHANNEL_TRANSPORTE_DIS = -1002688723492

SERVICE_CHANNELS = {
    "domicilio": CHANNEL_DOMICILIOS,
    "taxi": CHANNEL_TAXI,
    "trasteo": CHANNEL_TRASTEOS,
    "discapacitados": CHANNEL_TRANSPORTE_DIS,
}

# ---------------------------
# LOGS
# ---------------------------
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ---------------------------
# TECLADOS / MENÚS
# ---------------------------

# Menú principal de PRONTO
main_keyboard = ReplyKeyboardMarkup(
    [
        [KeyboardButton("Usuario")],
        [KeyboardButton("Móvil")],
        [KeyboardButton("Administrador")],
    ],
    resize_keyboard=True,
)

# Menú para Usuarios
user_keyboard = ReplyKeyboardMarkup(
    [
        [KeyboardButton("📍 Enviar ubicación", request_location=True)],
        [KeyboardButton("📦 Pedir domicilio")],
        [KeyboardButton("🚕 Pedir taxi")],
        [KeyboardButton("🏠 Pedir trasteo")],
        [KeyboardButton("♿ Transporte discapacitados")],
        [KeyboardButton("⬅️ Volver al inicio")],
    ],
    resize_keyboard=True,
)

# Menú para Móviles
driver_keyboard = ReplyKeyboardMarkup(
    [
        [KeyboardButton("📋 Ver servicios disponibles")],
        [KeyboardButton("✅ Marcar servicio en curso")],
        [KeyboardButton("✔️ Marcar servicio finalizado")],
        [KeyboardButton("⬅️ Volver al inicio")],
    ],
    resize_keyboard=True,
)

# Menú para Administrador
admin_keyboard = ReplyKeyboardMarkup(
    [
        [KeyboardButton("📊 Ver resumen del día")],
        [KeyboardButton("🧾 Ver servicios activos")],
        [KeyboardButton("⬅️ Volver al inicio")],
    ],
    resize_keyboard=True,
)

# ---------------------------
# HANDLERS
# ---------------------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /start: muestra el menú principal de roles."""
    user = update.effective_user
    context.user_data.clear()  # limpiamos cualquier estado anterior

    text = (
        f"Hola {user.first_name or ''}, soy PRONTO 🤖\n\n"
        "¿Quién eres hoy?\n\n"
        "• Usuario: quieres pedir un servicio\n"
        "• Móvil: eres domiciliario / taxista\n"
        "• Administrador: controlas la operación"
    )

    await update.message.reply_text(
        text,
        reply_markup=main_keyboard,
    )


async def handle_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Maneja las opciones del menú principal (Usuario / Móvil / Administrador)."""
    text = (update.message.text or "").strip().lower()

    # USUARIO
    if text == "usuario":
        context.user_data["rol"] = "usuario"
        context.user_data.pop("estado", None)
        context.user_data.pop("tipo_servicio", None)
        await update.message.reply_text(
            "Has ingresado como Usuario.\n"
            "Elige el servicio que deseas solicitar:",
            reply_markup=user_keyboard,
        )

    # MÓVIL
    elif text == "móvil" or text == "movil":
        context.user_data["rol"] = "movil"
        context.user_data.pop("estado", None)
        context.user_data.pop("tipo_servicio", None)
        await update.message.reply_text(
            "Has ingresado como Móvil.\n"
            "Este es tu menú de trabajo:",
            reply_markup=driver_keyboard,
        )

    # ADMINISTRADOR
    elif text == "administrador":
        context.user_data["rol"] = "admin"
        context.user_data.pop("estado", None)
        context.user_data.pop("tipo_servicio", None)
        await update.message.reply_text(
            "Has ingresado como Administrador.\n"
            "Estas son tus opciones:",
            reply_markup=admin_keyboard,
        )

    # VOLVER AL INICIO (desde cualquier rol)
    elif "volver al inicio" in text:
        context.user_data.clear()
        await start(update, context)

    else:
        # Si no reconoce, recuerda el menú según rol
        rol = context.user_data.get("rol")
        if rol == "usuario":
            await update.message.reply_text(
                "Por favor usa el menú de Usuario.",
                reply_markup=user_keyboard,
            )
        elif rol == "movil":
            await update.message.reply_text(
                "Por favor usa el menú de Móvil.",
                reply_markup=driver_keyboard,
            )
        elif rol == "admin":
            await update.message.reply_text(
                "Por favor usa el menú de Administrador.",
                reply_markup=admin_keyboard,
            )
        else:
            await update.message.reply_text(
                "Por favor usa las opciones del menú.",
                reply_markup=main_keyboard,
            )

# ---------------------------
# FLUJO DE USUARIO
# ---------------------------

async def handle_user_actions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Opciones del menú de Usuario y captura de datos para envío a canales."""
    text = (update.message.text or "").strip().lower()
    estado = context.user_data.get("estado")
    tipo_servicio = context.user_data.get("tipo_servicio")

    # Volver al inicio siempre tiene prioridad
    if "volver al inicio" in text:
        context.user_data.clear()
        await start(update, context)
        return

    # Si estamos esperando los datos del servicio
    if estado == "esperando_datos" and tipo_servicio:
        await procesar_solicitud_texto(update, context, tipo_servicio)
        return

    # Selección de servicio
    if "pedir domicilio" in text:
        context.user_data["tipo_servicio"] = "domicilio"
        context.user_data["estado"] = "esperando_datos"
        await update.message.reply_text(
            "Has elegido: Domicilio.\n\n"
            "Por favor escribe en un solo mensaje:\n"
            "• Dirección completa\n"
            "• Referencia del lugar\n"
            "• Número de contacto",
            reply_markup=user_keyboard,
        )

    elif "pedir taxi" in text:
        context.user_data["tipo_servicio"] = "taxi"
        context.user_data["estado"] = "esperando_datos"
        await update.message.reply_text(
            "Has elegido: Taxi.\n\n"
            "Por favor escribe en un solo mensaje:\n"
            "• Punto de recogida\n"
            "• Destino\n"
            "• Número de contacto",
            reply_markup=user_keyboard,
        )

    elif "pedir trasteo" in text:
        context.user_data["tipo_servicio"] = "trasteo"
        context.user_data["estado"] = "esperando_datos"
        await update.message.reply_text(
            "Has elegido: Trasteo.\n\n"
            "Por favor escribe en un solo mensaje:\n"
            "• Dirección de origen\n"
            "• Dirección de destino\n"
            "• Tipo de trasteo (cantidad aproximada)\n"
            "• Número de contacto",
            reply_markup=user_keyboard,
        )

    elif "transporte discapacitados" in text:
        context.user_data["tipo_servicio"] = "discapacitados"
        context.user_data["estado"] = "esperando_datos"
        await update.message.reply_text(
            "Has elegido: Transporte para personas con discapacidad.\n\n"
            "Por favor escribe en un solo mensaje:\n"
            "• Punto de recogida\n"
            "• Destino\n"
            "• Número de contacto\n"
            "• Observaciones importantes (si aplica)",
            reply_markup=user_keyboard,
        )

    else:
        # Si no coincide con ninguna opción, delegamos al menú principal
        await handle_main_menu(update, context)


async def procesar_solicitud_texto(update: Update, context: ContextTypes.DEFAULT_TYPE, tipo_servicio: str):
    """Toma el mensaje de texto del cliente y lo envía al canal correspondiente."""
    user = update.effective_user
    detalle = update.message.text

    canal = SERVICE_CHANNELS.get(tipo_servicio)
    if canal is None:
        await update.message.reply_text("No se encontró el canal para este servicio.")
        context.user_data.pop("estado", None)
        context.user_data.pop("tipo_servicio", None)
        return

    # Construir mensaje para el canal
    servicio_nombre = {
        "domicilio": "DOMICILIO",
        "taxi": "TAXI",
        "trasteo": "TRASTEO",
        "discapacitados": "TRANSPORTE DISCAPACITADOS",
    }.get(tipo_servicio, tipo_servicio.upper())

    username = f"@{user.username}" if user.username else "Sin usuario"
    chat_id = update.effective_chat.id

    mensaje_canal = (
        f"📢 NUEVO SERVICIO: {servicio_nombre}\n\n"
        f"👤 Cliente: {user.full_name}\n"
        f"🔗 Usuario: {username}\n"
        f"💬 Chat ID: {chat_id}\n\n"
        f"📝 Detalle del servicio:\n{detalle}\n\n"
        f"Por favor contactar al cliente directamente por Telegram."
    )

    try:
        await context.bot.send_message(chat_id=canal, text=mensaje_canal)
        await update.message.reply_text(
            "Tu solicitud ha sido enviada. Un operador se comunicará contigo en breve.",
            reply_markup=user_keyboard,
        )
    except Exception as e:
        logger.error(f"Error enviando al canal: {e}")
        await update.message.reply_text(
            "Ocurrió un error enviando tu solicitud. Intenta nuevamente más tarde.",
            reply_markup=user_keyboard,
        )

    # Limpiar estado
    context.user_data.pop("estado", None)
    context.user_data.pop("tipo_servicio", None)


# ---------------------------
# FLUJO DE MÓVIL
# ---------------------------

async def handle_driver_actions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Opciones del menú de Móvil (por ahora solo mensajes informativos)."""
    text = (update.message.text or "").strip().lower()

    if "ver servicios disponibles" in text:
        await update.message.reply_text(
            "Aquí se mostrarán los servicios disponibles para aceptar.\n"
            "Esta sección se conectará con los canales en una siguiente etapa.",
            reply_markup=driver_keyboard,
        )
    elif "marcar servicio en curso" in text:
        await update.message.reply_text(
            "Aquí podrás marcar un servicio como EN CURSO.",
            reply_markup=driver_keyboard,
        )
    elif "marcar servicio finalizado" in text:
        await update.message.reply_text(
            "Aquí podrás marcar un servicio como FINALIZADO.",
            reply_markup=driver_keyboard,
        )
    elif "volver al inicio" in text:
        context.user_data.clear()
        await start(update, context)
    else:
        await handle_main_menu(update, context)

# ---------------------------
# FLUJO DE ADMIN
# ---------------------------

async def handle_admin_actions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Opciones del menú de Administrador (por ahora solo mensajes informativos)."""
    text = (update.message.text or "").strip().lower()

    if "ver resumen del día" in text:
        await update.message.reply_text(
            "Aquí se mostrará un resumen de los servicios del día.",
            reply_markup=admin_keyboard,
        )
    elif "ver servicios activos" in text:
        await update.message.reply_text(
            "Aquí se mostrarán los servicios que estén en curso.",
            reply_markup=admin_keyboard,
        )
    elif "volver al inicio" in text:
        context.user_data.clear()
        await start(update, context)
    else:
        await handle_main_menu(update, context)

# ---------------------------
# HANDLER DE UBICACIÓN
# ---------------------------

async def handle_location(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cuando el usuario envía ubicación usando el botón."""
    rol = context.user_data.get("rol")
    estado = context.user_data.get("estado")
    tipo_servicio = context.user_data.get("tipo_servicio")

    if rol != "usuario" or estado != "esperando_datos" or not tipo_servicio:
        await update.message.reply_text(
            "Primero debes elegir un tipo de servicio en el menú de Usuario.",
            reply_markup=user_keyboard,
        )
        return

    location = update.message.location
    lat = location.latitude
    lon = location.longitude

    canal = SERVICE_CHANNELS.get(tipo_servicio)
    if canal is None:
        await update.message.reply_text("No se encontró el canal para este servicio.")
        context.user_data.pop("estado", None)
        context.user_data.pop("tipo_servicio", None)
        return

    user = update.effective_user
    username = f"@{user.username}" if user.username else "Sin usuario"
    chat_id = update.effective_chat.id

    maps_link = f"https://maps.google.com/?q={lat},{lon}"

    servicio_nombre = {
        "domicilio": "DOMICILIO",
        "taxi": "TAXI",
        "trasteo": "TRASTEO",
        "discapacitados": "TRANSPORTE DISCAPACITADOS",
    }.get(tipo_servicio, tipo_servicio.upper())

    mensaje_canal = (
        f"📢 NUEVO SERVICIO: {servicio_nombre}\n\n"
        f"👤 Cliente: {user.full_name}\n"
        f"🔗 Usuario: {username}\n"
        f"💬 Chat ID: {chat_id}\n\n"
        f"📍 Ubicación enviada:\n{maps_link}\n\n"
        f"El cliente no escribió detalles adicionales.\n"
        f"Por favor contactar al cliente directamente por Telegram."
    )

    try:
        await context.bot.send_message(chat_id=canal, text=mensaje_canal)
        await update.message.reply_text(
            "Tu ubicación ha sido enviada. Un operador se comunicará contigo en breve.",
            reply_markup=user_keyboard,
        )
    except Exception as e:
        logger.error(f"Error enviando al canal: {e}")
        await update.message.reply_text(
            "Ocurrió un error enviando tu solicitud. Intenta nuevamente más tarde.",
            reply_markup=user_keyboard,
        )

    context.user_data.pop("estado", None)
    context.user_data.pop("tipo_servicio", None)

# ---------------------------
# ROUTER GENERAL
# ---------------------------

async def router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rol = context.user_data.get("rol")

    if rol == "usuario":
        await handle_user_actions(update, context)
    elif rol == "movil":
        await handle_driver_actions(update, context)
    elif rol == "admin":
        await handle_admin_actions(update, context)
    else:
        await handle_main_menu(update, context)

# ---------------------------
# MAIN
# ---------------------------

def main():
    app = ApplicationBuilder().token(TOKEN).build()

    # /start
    app.add_handler(CommandHandler("start", start))

    # Mensajes de texto
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, router))

    # Ubicación
    app.add_handler(MessageHandler(filters.LOCATION, handle_location))

    app.run_polling()

if __name__ == "__main__":
    main()
