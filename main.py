# PRONTO - Webhook nativo para Railway
# Requisitos: python-telegram-bot==20.4

import os
import logging
import json
from datetime import datetime
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# ----------------------------
# CONFIG
# ----------------------------

TOKEN = "7668998247:AAGR7gxbJSFf-yuWtIOxMEFI1AYFinMJygg"

ADMIN_IDS = [1741298723, 7076796229]

WEBHOOK_DOMAIN = "https://pronto-empty-production.up.railway.app"
WEBHOOK_PATH = f"/webhook/{TOKEN}"
WEBHOOK_URL = WEBHOOK_DOMAIN + WEBHOOK_PATH

MOBILES_FILE = "mobiles.json"
SERVICES_FILE = "services.json"

# ----------------------------
# LOGS
# ----------------------------

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ----------------------------
# BD SIMPLE
# ----------------------------

def load_json(path, default):
    try:
        if not os.path.exists(path):
            return default
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return default

def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def load_mobiles():
    return load_json(MOBILES_FILE, [])

def save_mobiles(data):
    save_json(MOBILES_FILE, data)

def load_services():
    return load_json(SERVICES_FILE, [])

def save_services(data):
    save_json(SERVICES_FILE, data)

def is_admin(uid):
    return uid in ADMIN_IDS

# ----------------------------
# TECLADOS / MENÚS
# ----------------------------

main_keyboard = ReplyKeyboardMarkup(
    [
        ["Usuario"],
        ["Móvil"],
        ["Administrador"],
    ],
    resize_keyboard=True,
)

user_keyboard = ReplyKeyboardMarkup(
    [
        ["📦 Pedir domicilio"],
        ["🚕 Pedir taxi"],
        ["⬅️ Volver"],
    ],
    resize_keyboard=True,
)

movil_keyboard = ReplyKeyboardMarkup(
    [
        ["🟢 Disponible"],
        ["🔴 No disponible"],
        ["⬅️ Volver"],
    ],
    resize_keyboard=True,
)

admin_keyboard = ReplyKeyboardMarkup(
    [
        ["➕ Registrar móvil", "📋 Ver móviles"],
        ["📜 Historial", "💳 Aprobar pago"],
        ["⬅️ Volver"],
    ],
    resize_keyboard=True,
)

# ----------------------------
# HANDLERS
# ----------------------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Hola 💛, soy PRONTO.\nElige una opción:",
        reply_markup=main_keyboard,
    )

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    uid = update.effective_user.id

    # Volver al menú
    if text == "⬅️ Volver":
        context.user_data.clear()
        await update.message.reply_text("Volviste al menú principal.", reply_markup=main_keyboard)
        return

    # ---------------- ADMIN ----------------
    if text == "Administrador":
        if not is_admin(uid):
            await update.message.reply_text("❌ No tienes permisos para esta sección.")
            return
        await update.message.reply_text("Panel Administrador 🛠️", reply_markup=admin_keyboard)
        return

    # Registrar móvil
    if is_admin(uid) and text == "➕ Registrar móvil":
        context.user_data["admin_action"] = "reg_nombre"
        context.user_data["temp"] = {}
        await update.message.reply_text("Escribe el *nombre*:", parse_mode="Markdown")
        return

    # Flujo de registro
    if context.user_data.get("admin_action", "").startswith("reg_"):
        step = context.user_data["admin_action"]
        temp = context.user_data["temp"]

        if step == "reg_nombre":
            temp["nombre"] = text
            context.user_data["admin_action"] = "reg_cedula"
            await update.message.reply_text("Cédula:", parse_mode="Markdown")
            return

        if step == "reg_cedula":
            temp["cedula"] = text
            context.user_data["admin_action"] = "reg_tipo"
            await update.message.reply_text("Tipo de vehículo:", parse_mode="Markdown")
            return

        if step == "reg_tipo":
            temp["tipo"] = text
            context.user_data["admin_action"] = "reg_marca"
            await update.message.reply_text("Marca y modelo:", parse_mode="Markdown")
            return

        if step == "reg_marca":
            temp["marca"] = text
            context.user_data["admin_action"] = "reg_placa"
            await update.message.reply_text("Placa:", parse_mode="Markdown")
            return

        if step == "reg_placa":
            temp["placa"] = text
            temp["activo"] = False
            temp["registrado"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            moviles = load_mobiles()
            moviles.append(temp)
            save_mobiles(moviles)

            context.user_data.clear()

            await update.message.reply_text(
                f"✔️ Móvil registrado:\n\n"
                f"👤 {temp['nombre']}\n"
                f"🆔 {temp['cedula']}\n"
                f"🚗 {temp['tipo']} - {temp['marca']}\n"
                f"🔢 Placa: {temp['placa']}\n"
                f"Estado: INACTIVO\n",
                reply_markup=admin_keyboard,
            )
            return

    # Ver móviles
    if is_admin(uid) and text == "📋 Ver móviles":
        moviles = load_mobiles()
        if not moviles:
            await update.message.reply_text("No hay móviles registrados.")
            return

        msg = "📋 *Móviles registrados:*\n\n"
        for m in moviles:
            estado = "ACTIVO ✅" if m["activo"] else "INACTIVO ⛔"
            msg += (
                f"👤 {m['nombre']} ({m['cedula']})\n"
                f"🚗 {m['tipo']} - {m['marca']}\n"
                f"🔢 {m['placa']}\n"
                f"{estado}\n\n"
            )
        await update.message.reply_text(msg, parse_mode="Markdown")
        return

    # Aprobar pago
    if is_admin(uid) and text == "💳 Aprobar pago":
        context.user_data["admin_action"] = "pago"
        await update.message.reply_text("Cédula del móvil:", parse_mode="Markdown")
        return

    if context.user_data.get("admin_action") == "pago":
        ced = text
        moviles = load_mobiles()
        found = False

        for m in moviles:
            if m["cedula"] == ced:
                m["activo"] = True
                m["activado"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                found = True
                break

        context.user_data.clear()

        if found:
            save_mobiles(moviles)
            await update.message.reply_text("✔️ Móvil ACTIVADO.")
        else:
            await update.message.reply_text("❌ No existe esa cédula.")
        return

    # ---------------- USUARIO ----------------

    if text == "Usuario":
        await update.message.reply_text("Menú Usuario 👤", reply_markup=user_keyboard)
        return

    if text == "Móvil":
        await update.message.reply_text("Menú Móvil 🚗", reply_markup=movil_keyboard)
        return

    # Respuesta por defecto
    await update.message.reply_text("Usa el menú 💛", reply_markup=main_keyboard)

# ----------------------------
# MAIN - WEBHOOK NATIVO
# ----------------------------

if __name__ == "__main__":
    PORT = int(os.environ.get("PORT", 8080))

    application = ApplicationBuilder().token(TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    async def run():
        await application.bot.set_webhook(WEBHOOK_URL)

        await application.run_webhook(
            listen="0.0.0.0",
            port=PORT,
            url_path=WEBHOOK_PATH,
            webhook_url=WEBHOOK_URL,
        )

    import asyncio
    asyncio.run(run())
