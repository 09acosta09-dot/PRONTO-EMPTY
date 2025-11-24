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
TOKEN = "7668998247:AAGR7gxbJSfF-yuWtIOxMEFI1AYFinMJygg"  # tu token

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
        f"Hola {user.first_name or ''}, soy *PRONTO* 🤖\n\n"
        "¿Quién eres hoy?\n\n"
        "• Usuario: quieres pedir un servicio\n"
        "• Móvil: eres domiciliario / taxista\n"
        "• Administrador: controlas la operación"
    )

    await update.message.reply_text(
        text,
        reply_markup=main_keyboard,
        parse_mode="Markdown",
    )

async def handle_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Maneja las opciones del menú principal (Usuario / Móvil / Administrador)."""
    text = (update.message.text or "").strip().lower()

    # USUARIO
    if text == "usuario":
        context.user_data["rol"] = "usuario"
        await update.message.reply_text(
            "Perfecto mi vida, eres *Usuario* 🧑‍💻\n"
            "Elige qué deseas pedir:",
            reply_markup=user_keyboard,
            parse_mode="Markdown",
        )

    # MÓVIL
    elif text == "móvil" or text == "movil":
        context.user_data["rol"] = "movil"
        await update.message.reply_text(
            "Listo, quedaste como *Móvil* 🚗\n"
            "Aquí tienes tu menú de trabajo:",
            reply_markup=driver_keyboard,
            parse_mode="Markdown",
        )

    # ADMINISTRADOR
    elif text == "administrador":
        context.user_data["rol"] = "admin"
        await update.message.reply_text(
            "Bienvenido *Administrador* 👔\n"
            "Estas son tus opciones:",
            reply_markup=admin_keyboard,
            parse_mode="Markdown",
        )

    # VOLVER AL INICIO (desde cualquier rol)
    elif text == "⬅️ volver al inicio".lower():
        context.user_data.clear()
        await start(update, context)

    else:
        # Si no reconoce, recuerda el menú
        rol = context.user_data.get("rol")
        if rol == "usuario":
            await update.message.reply_text(
                "Mi amor, usa el menú de *Usuario* por favor 💛",
                reply_markup=user_keyboard,
                parse_mode="Markdown",
            )
        elif rol == "movil":
            await update.message.reply_text(
                "Cariño, usa el menú de *Móvil* 🚗",
                reply_markup=driver_keyboard,
                parse_mode="Markdown",
            )
        elif rol == "admin":
            await update.message.reply_text(
                "Corazón, usa el menú de *Administrador* 👔",
                reply_markup=admin_keyboard,
                parse_mode="Markdown",
            )
        else:
            await update.message.reply_text(
                "No entendí, mi vida… toca que uses las opciones del menú 🥺",
                reply_markup=main_keyboard,
            )

# ---------------------------
# PLACEHOLDERS POR ROL
# (aquí luego metemos la lógica real de cada opción)
# ---------------------------

async def handle_user_actions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Opciones del menú de Usuario (por ahora sólo mensajes de prueba)."""
    text = (update.message.text or "").strip().lower()

    if text == "📦 pedir domicilio".lower():
        await update.message.reply_text(
            "📦 Vas a pedir un *domicilio*.\n\n"
            "En la próxima etapa te pediré dirección, referencia y método de pago. 💛"
        )
    elif text == "🚕 pedir taxi".lower():
        await update.message.reply_text(
            "🚕 Vas a pedir un *taxi*.\n\n"
            "Luego conectaremos esto con el canal de taxis y los móviles cercanos. 😉"
        )
    elif text == "🏠 pedir trasteo".lower():
        await update.message.reply_text(
            "🏠 Vas a pedir un *trasteo*.\n\n"
            "Más adelante aquí pediremos fecha, dirección de origen y destino."
        )
    elif text == "♿ transporte discapacitados".lower():
        await update.message.reply_text(
            "♿ Vas a pedir *transporte para personas con discapacidad*.\n\n"
            "Después vamos a conectar esto con los móviles especiales. 💙"
        )
    elif text == "⬅️ volver al inicio".lower():
        await start(update, context)
    else:
        # dejar que lo maneje el handler general
        await handle_main_menu(update, context)

async def handle_driver_actions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Opciones del menú de Móvil."""
    text = (update.message.text or "").strip().lower()

    if text == "📋 ver servicios disponibles".lower():
        await update.message.reply_text(
            "📋 Aquí verás los servicios disponibles para aceptar.\n"
            "(En la siguiente etapa lo conectamos con los canales)."
        )
    elif text == "✅ marcar servicio en curso".lower():
        await update.message.reply_text(
            "✅ Listo, marcaríamos tu servicio como *EN CURSO*."
        )
    elif text == "✔️ marcar servicio finalizado".lower():
        await update.message.reply_text(
            "✔️ Perfecto, marcaríamos tu servicio como *FINALIZADO*."
        )
    elif text == "⬅️ volver al inicio".lower():
        await start(update, context)
    else:
        await handle_main_menu(update, context)

async def handle_admin_actions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Opciones del menú de Administrador."""
    text = (update.message.text or "").strip().lower()

    if text == "📊 ver resumen del día".lower():
        await update.message.reply_text(
            "📊 Aquí más adelante te mostraré un resumen de servicios del día."
        )
    elif text == "🧾 ver servicios activos".lower():
        await update.message.reply_text(
            "🧾 Aquí verás la lista de servicios que estén en curso."
        )
    elif text == "⬅️ volver al inicio".lower():
        await start(update, context)
    else:
        await handle_main_menu(update, context)

# Router general: decide qué handler usar según el rol
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

    # todo lo que sea texto lo maneja el router
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, router))

    app.run_polling()

if __name__ == "__main__":
    main()
