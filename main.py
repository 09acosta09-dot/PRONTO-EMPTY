# PRONTO - Bot con módulo de ADMINISTRADOR
# Requisitos: python-telegram-bot v20+
# Ejecutar con: python main.py (en Railway se configura el comando de arranque)

import logging
import json
import os
from datetime import datetime

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

# Admins (tú y tu cliente)
ADMIN_IDS = [1741298723, 7076796229]

# Canales (por si ya los usas en otros flujos)
CHANNEL_TAXI = -1002697357566
CHANNEL_DOMICILIOS = -1002503403579
CHANNEL_TRASTEOS = -1002662309590
CHANNEL_TRANSPORTE_DIS = -1002688723492

# Archivos "base de datos" simples
MOBILES_FILE = "mobiles.json"
SERVICES_FILE = "services.json"

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

# Menú para Usuarios (ejemplo, lo puedes ampliar)
user_keyboard = ReplyKeyboardMarkup(
    [
        [KeyboardButton("📦 Pedir domicilio")],
        [KeyboardButton("🚕 Pedir taxi")],
        [KeyboardButton("⬅️ Volver al menú principal")],
    ],
    resize_keyboard=True,
)

# Menú para Móviles (ejemplo, lo puedes ampliar)
movil_keyboard = ReplyKeyboardMarkup(
    [
        [KeyboardButton("🟢 Marcar disponible")],
        [KeyboardButton("🔴 Marcar no disponible")],
        [KeyboardButton("⬅️ Volver al menú principal")],
    ],
    resize_keyboard=True,
)

# Menú para Administrador
admin_keyboard = ReplyKeyboardMarkup(
    [
        [KeyboardButton("➕ Registrar móvil"), KeyboardButton("📋 Ver móviles")],
        [KeyboardButton("📜 Historial de servicios"), KeyboardButton("💳 Aprobar pago")],
        [KeyboardButton("⬅️ Volver al menú principal")],
    ],
    resize_keyboard=True,
)

# ---------------------------
# FUNCIONES AUXILIARES BD
# ---------------------------

def load_json(path, default):
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Error cargando {path}: {e}")
        return default


def save_json(path, data):
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"Error guardando {path}: {e}")


def load_mobiles():
    return load_json(MOBILES_FILE, [])


def save_mobiles(mobiles):
    save_json(MOBILES_FILE, mobiles)


def load_services():
    return load_json(SERVICES_FILE, [])


def save_services(services):
    save_json(SERVICES_FILE, services)


def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


# ---------------------------
# HANDLERS
# ---------------------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    logger.info(f"/start de {user.id} - {user.first_name}")
    await update.message.reply_text(
        "Hola 💛, soy PRONTO.\n\n"
        "Elige una opción del menú:",
        reply_markup=main_keyboard,
    )


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    user = update.effective_user
    user_id = user.id

    logger.info(f"Mensaje de {user_id} ({user.first_name}): {text}")

    # Si el admin está en algún flujo especial, lo manejamos primero
    if is_admin(user_id):
        # Flujo de registro de móvil
        if context.user_data.get("admin_action") == "register_mobile":
            await handle_admin_register_flow(update, context, text)
            return

        # Flujo de aprobación de pago
        if context.user_data.get("admin_action") == "approve_payment":
            await handle_admin_approve_flow(update, context, text)
            return

    # ------- Menú principal -------
    if text == "Usuario":
        await update.message.reply_text(
            "Menú de Usuario 👤\nElige una opción:",
            reply_markup=user_keyboard,
        )
        return

    if text == "Móvil":
        await update.message.reply_text(
            "Menú para Móviles 🚗\nElige una opción:",
            reply_markup=movil_keyboard,
        )
        return

    if text == "Administrador":
        # Verificar si es admin
        if not is_admin(user_id):
            await update.message.reply_text(
                "⛔ Acceso denegado.\n\n"
                "Esta sección es solo para administradores autorizados."
            )
            return

        await update.message.reply_text(
            "Panel de Administrador 🛠️\nElige una opción:",
            reply_markup=admin_keyboard,
        )
        return

    # ------- Botón volver al menú principal -------
    if text == "⬅️ Volver al menú principal":
        # Limpiamos posibles acciones pendientes del admin
        context.user_data.pop("admin_action", None)
        context.user_data.pop("register_step", None)
        context.user_data.pop("register_temp", None)
        context.user_data.pop("approve_step", None)

        await update.message.reply_text(
            "Has vuelto al menú principal.",
            reply_markup=main_keyboard,
        )
        return

    # ------- Opciones de ADMIN -------
    if is_admin(user_id):
        if text == "➕ Registrar móvil":
            await start_admin_register_mobile(update, context)
            return

        if text == "📋 Ver móviles":
            await admin_show_mobiles(update, context)
            return

        if text == "📜 Historial de servicios":
            await admin_show_history(update, context)
            return

        if text == "💳 Aprobar pago":
            await start_admin_approve_payment(update, context)
            return

    # ------- Opciones ejemplo de Usuario -------
    if text == "📦 Pedir domicilio":
        await update.message.reply_text(
            "Aquí iría el flujo para pedir un domicilio 🏍️ (aún en construcción)."
        )
        return

    if text == "🚕 Pedir taxi":
        await update.message.reply_text(
            "Aquí iría el flujo para pedir un taxi 🚕 (aún en construcción)."
        )
        return

    # ------- Opciones ejemplo de Móvil -------
    if text == "🟢 Marcar disponible":
        await update.message.reply_text(
            "Perfecto, has marcado tu estado como disponible ✅."
        )
        return

    if text == "🔴 Marcar no disponible":
        await update.message.reply_text(
            "Listo, has marcado tu estado como no disponible ⛔."
        )
        return

    # ------- Mensaje por defecto -------
    await update.message.reply_text(
        "No entiendo eso, usa el menú por favor 😊",
        reply_markup=main_keyboard,
    )

# ---------------------------
# ADMIN: REGISTRAR MÓVIL
# ---------------------------

async def start_admin_register_mobile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Inicia el flujo para registrar un nuevo móvil."""
    context.user_data["admin_action"] = "register_mobile"
    context.user_data["register_step"] = "nombre"
    context.user_data["register_temp"] = {}

    await update.message.reply_text(
        "Vamos a registrar un nuevo móvil 🚗\n\n"
        "Por favor escribe el *Nombre* del conductor:",
        parse_mode="Markdown",
    )


async def handle_admin_register_flow(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str):
    step = context.user_data.get("register_step")
    temp = context.user_data.get("register_temp", {})

    if step == "nombre":
        temp["nombre"] = text
        context.user_data["register_step"] = "cedula"
        context.user_data["register_temp"] = temp
        await update.message.reply_text("Ahora escribe la *cédula* del conductor:", parse_mode="Markdown")
        return

    if step == "cedula":
        temp["cedula"] = text
        context.user_data["register_step"] = "tipo_vehiculo"
        context.user_data["register_temp"] = temp
        await update.message.reply_text("Escribe el *tipo de vehículo* (ej: moto, taxi, carro, etc.):", parse_mode="Markdown")
        return

    if step == "tipo_vehiculo":
        temp["tipo_vehiculo"] = text
        context.user_data["register_step"] = "marca_modelo"
        context.user_data["register_temp"] = temp
        await update.message.reply_text("Escribe la *marca y modelo* del vehículo:", parse_mode="Markdown")
        return

    if step == "marca_modelo":
        temp["marca_modelo"] = text
        context.user_data["register_step"] = "placa"
        context.user_data["register_temp"] = temp
        await update.message.reply_text("Finalmente, escribe la *placa* del vehículo:", parse_mode="Markdown")
        return

    if step == "placa":
        temp["placa"] = text
        temp["activo"] = False  # por defecto inactivo hasta que pague
        temp["registrado_en"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        mobiles = load_mobiles()
        mobiles.append(temp)
        save_mobiles(mobiles)

        # Limpiamos el flujo
        context.user_data["admin_action"] = None
        context.user_data["register_step"] = None
        context.user_data["register_temp"] = None

        resumen = (
            f"✅ Móvil registrado correctamente:\n\n"
            f"👤 Nombre: {temp['nombre']}\n"
            f"🆔 Cédula: {temp['cedula']}\n"
            f"🚘 Tipo: {temp['tipo_vehiculo']}\n"
            f"🚗 Marca/Modelo: {temp['marca_modelo']}\n"
            f"🔢 Placa: {temp['placa']}\n"
            f"💳 Estado: INACTIVO (pendiente pago)\n"
        )
        await update.message.reply_text(
            resumen,
            reply_markup=admin_keyboard,
        )
        return

    # Si por alguna razón el paso no está, reseteamos
    context.user_data["admin_action"] = None
    context.user_data["register_step"] = None
    context.user_data["register_temp"] = None
    await update.message.reply_text(
        "Se perdió el flujo de registro, volvamos a empezar.",
        reply_markup=admin_keyboard,
    )


# ---------------------------
# ADMIN: VER MÓVILES
# ---------------------------

async def admin_show_mobiles(update: Update, context: ContextTypes.DEFAULT_TYPE):
    mobiles = load_mobiles()
    if not mobiles:
        await update.message.reply_text(
            "No hay móviles registrados todavía.",
            reply_markup=admin_keyboard,
        )
        return

    lines = ["📋 *Móviles registrados:*", ""]
    for i, m in enumerate(mobiles, start=1):
        estado = "ACTIVO ✅" if m.get("activo") else "INACTIVO ⛔"
        lines.append(
            f"{i}. {m.get('nombre', 'N/A')} - {m.get('tipo_vehiculo', 'N/A')}\n"
            f"   Cédula: {m.get('cedula', 'N/A')}\n"
            f"   Marca/Modelo: {m.get('marca_modelo', 'N/A')}\n"
            f"   Placa: {m.get('placa', 'N/A')}\n"
            f"   Estado: {estado}\n"
        )

    msg = "\n".join(lines)
    await update.message.reply_text(
        msg,
        parse_mode="Markdown",
        reply_markup=admin_keyboard,
    )


# ---------------------------
# ADMIN: HISTORIAL SERVICIOS
# ---------------------------

async def admin_show_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    services = load_services()
    if not services:
        await update.message.reply_text(
            "Aún no hay historial de servicios registrados.",
            reply_markup=admin_keyboard,
        )
        return

    # Mostramos máximo los últimos 10 para no saturar
    last_services = services[-10:]

    lines = ["📜 *Últimos servicios registrados:*", ""]
    for s in last_services:
        fecha = s.get("fecha", "N/A")
        cliente = s.get("cliente", "N/A")
        direccion = s.get("direccion", "N/A")
        operador = s.get("operador", "N/A")
        estado = s.get("estado", "N/A")

        lines.append(
            f"🕒 {fecha}\n"
            f"👤 Cliente: {cliente}\n"
            f"📍 Dirección: {direccion}\n"
            f"🚗 Operador: {operador}\n"
            f"📌 Estado: {estado}\n"
        )

    msg = "\n".join(lines)
    await update.message.reply_text(
        msg,
        parse_mode="Markdown",
        reply_markup=admin_keyboard,
    )


# ---------------------------
# ADMIN: APROBAR PAGO
# ---------------------------

async def start_admin_approve_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["admin_action"] = "approve_payment"
    context.user_data["approve_step"] = "cedula"

    await update.message.reply_text(
        "💳 Aprobación de pago de un móvil.\n\n"
        "Por favor escribe la *cédula* del móvil que ya realizó el pago:",
        parse_mode="Markdown",
    )


async def handle_admin_approve_flow(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str):
    step = context.user_data.get("approve_step")

    if step == "cedula":
        cedula = text.strip()

        mobiles = load_mobiles()
        found = False
        for m in mobiles:
            if m.get("cedula") == cedula:
                m["activo"] = True
                m["activo_desde"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                found = True
                break

        if not found:
            await update.message.reply_text(
                "No encontré ningún móvil con esa cédula.\n"
                "Verifica el dato o revisa la lista de móviles.",
                reply_markup=admin_keyboard,
            )
        else:
            save_mobiles(mobiles)
            await update.message.reply_text(
                f"✅ El móvil con cédula *{cedula}* ha sido marcado como ACTIVO.\n"
                f"Ahora puede recibir servicios normalmente.",
                parse_mode="Markdown",
                reply_markup=admin_keyboard,
            )

        # Limpiamos flujo
        context.user_data["admin_action"] = None
        context.user_data["approve_step"] = None
        return

    # Si algo raro pasa, limpiamos
    context.user_data["admin_action"] = None
    context.user_data["approve_step"] = None
    await update.message.reply_text(
        "Se perdió el flujo de aprobación, volvamos al menú de administrador.",
        reply_markup=admin_keyboard,
    )


# ---------------------------
# MAIN
# ---------------------------

async def main():
    application = ApplicationBuilder().token(TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    logger.info("Bot PRONTO iniciado. Esperando mensajes...")
    await application.run_polling()


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
