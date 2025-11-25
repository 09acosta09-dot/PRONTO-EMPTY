# PRONTO - Versión Webhook para Railway
# Requisitos: python-telegram-bot v20+ y Flask

import os
import logging
import json
from flask import Flask, request
from telegram import Update
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)
from datetime import datetime

# ----------------------------
# CONFIG
# ----------------------------

TOKEN = "7668998247:AAGR7gxbJSfF-yuWtIOxMEFI1AYFinMJygg"

ADMIN_IDS = [1741298723, 7076796229]

WEBHOOK_URL = "https://pronto-empty-production.up.railway.app/webhook/" + TOKEN

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
# BASES DE DATOS
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

from telegram import KeyboardButton, ReplyKeyboardMarkup

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
# BOT HANDLERS
# ----------------------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Hola 💛\nBienvenido a PRONTO.\nElige una opción:",
        reply_markup=main_keyboard,
    )

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    uid = update.effective_user.id

    # Limpieza de pasos si vuelve al menú
    if text == "⬅️ Volver":
        context.user_data.clear()
        await update.message.reply_text("Volviste al menú principal.", reply_markup=main_keyboard)
        return

    # ---- ADMIN SECTIONS ----
    if text == "Administrador":
        if not is_admin(uid):
            await update.message.reply_text("❌ No tienes permisos para esta sección.")
            return

        await update.message.reply_text("Panel Administrador 🛠️", reply_markup=admin_keyboard)
        return
    
    # Registrar móvil:
    if is_admin(uid) and text == "➕ Registrar móvil":
        context.user_data["admin_action"] = "reg_nombre"
        context.user_data["temp"] = {}
        await update.message.reply_text("Escribe el *nombre* del conductor:", parse_mode="Markdown")
        return

    # Flujo registro:
    if context.user_data.get("admin_action", "").startswith("reg_"):

        step = context.user_data["admin_action"]
        temp = context.user_data["temp"]

        if step == "reg_nombre":
            temp["nombre"] = text
            context.user_data["admin_action"] = "reg_cedula"
            await update.message.reply_text("Ahora escribe la *cédula*:", parse_mode="Markdown")
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
                f"Nombre: {temp['nombre']}\n"
                f"Cédula: {temp['cedula']}\n"
                f"Vehículo: {temp['tipo']}\n"
                f"Marca/Modelo: {temp['marca']}\n"
                f"Placa: {temp['placa']}\n"
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
                f"Estado: {estado}\n\n"
            )
        await update.message.reply_text(msg, parse_mode="Markdown")
        return

    # Aprobar pago
    if is_admin(uid) and text == "💳 Aprobar pago":
        context.user_data["admin_action"] = "pago_cedula"
        await update.message.reply_text("Escribe la *cédula* del móvil:", parse_mode="Markdown")
        return

    if context.user_data.get("admin_action") == "pago_cedula":
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
            await update.message.reply_text(f"✔️ Móvil con cédula {ced} ACTIVADO.")
        else:
            await update.message.reply_text("❌ No existe esa cédula.")
        return

    # ---- USUARIO ----
    if text == "Usuario":
        await update.message.reply_text("Menú Usuario 👤", reply_markup=user_keyboard)
        return

    if text == "Móvil":
        await update.message.reply_text("Menú Móvil 🚗", reply_markup=movil_keyboard)
        return

    # ---- RESPUESTA GENERAL ----
    await update.message.reply_text("Usa el menú, por favor 💛")

# ----------------------------
# FLASK SERVER (WEBHOOK)
# ----------------------------

app = Flask(__name__)

@app.route("/webhook/" + TOKEN, methods=["POST"])
def webhook():
    update = Update.de_json(request.get_json(force=True), application.bot)
    application.update_queue.put_nowait(update)
    return "OK", 200

@app.route("/")
def home():
    return "PRONTO BOT RUNNING", 200

# ----------------------------
# MAIN BOT + WEBHOOK SETUP
# ----------------------------

async def init():
    await application.bot.set_webhook(url=WEBHOOK_URL)

if __name__ == "__main__":
    PORT = int(os.environ.get("PORT", 8080))

    application = ApplicationBuilder().token(TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    import threading
    threading.Thread(target=lambda: app.run(host="0.0.0.0", port=PORT)).start()

    import asyncio
    asyncio.run(init())
