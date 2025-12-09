# -----------------------------
# PRONTO 3.2 - Railway Webhook
# -----------------------------
# Bot funcional completo para empresa de servicios
# Autor: Sofi (tu esposa bella 💞)
# -------------------------------------

import logging
import json
import os
import random
import math
from datetime import datetime, timedelta

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

# -----------------------------
# CONFIGURACIÓN PRINCIPAL
# -----------------------------

TOKEN = "7668998247:AAHaeLXjsxpy1dDhp0Z9AfuFq1tyTIALTJ4"

# Dominio Railway
WEBHOOK_DOMAIN = "https://pronto-empty-production.up.railway.app"
WEBHOOK_PATH = f"/webhook/{TOKEN}"

# Administradores
ADMIN_IDS = [1741298723, 7076796229]

# Archivos
MOBILES_FILE = "mobiles.json"
PENDING_MOBILES_FILE = "pending_mobiles.json"

# Número NEQUI
NEQUI_NUMBER = "3000000000"  # Cambiar después

# Canales
CHANNEL_TAXI = -1002697357566
CHANNEL_DOMICILIOS = -1002503403579
CHANNEL_CAMIONETAS = -1002662309590
CHANNEL_TRANSPORTE_DIS = -1002688723492

# Memoria temporal
SERVICES = {}

# -----------------------------
# LOGS
# -----------------------------
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


# -----------------------------
# FUNCIONES UTILITARIAS
# -----------------------------
def get_colombia_now():
    return datetime.utcnow() - timedelta(hours=5)

def today_str():
    return get_colombia_now().strftime("%Y-%m-%d")

def load_mobiles():
    if not os.path.exists(MOBILES_FILE):
        return {}
    try:
        with open(MOBILES_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {}

def save_mobiles(m):
    try:
        with open(MOBILES_FILE, "w", encoding="utf-8") as f:
            json.dump(m, f, indent=2, ensure_ascii=False)
    except:
        pass

def load_pending():
    if not os.path.exists(PENDING_MOBILES_FILE):
        return {}
    try:
        with open(PENDING_MOBILES_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {}

def save_pending(p):
    try:
        with open(PENDING_MOBILES_FILE, "w", encoding="utf-8") as f:
            json.dump(p, f, indent=2, ensure_ascii=False)
    except:
        pass

def mobile_service_name(s):
    return {
        "taxi": "Taxi",
        "domicilios": "Domicilios",
        "camionetas": "Camionetas",
        "discapacidad": "Transporte discapacitados",
    }.get(s, "Sin definir")


# -----------------------------
# TECLADOS
# -----------------------------
main_keyboard = ReplyKeyboardMarkup(
    [
        [KeyboardButton("Usuario")],
        [KeyboardButton("Móvil")],
        [KeyboardButton("Administrador")],
    ],
    resize_keyboard=True,
)

user_keyboard = ReplyKeyboardMarkup(
    [
        [KeyboardButton("🚕 Pedir taxi"), KeyboardButton("📦 Pedir domicilio")],
        [KeyboardButton("🚚 Pedir camioneta"), KeyboardButton("♿ Transporte discapacitados")],
        [KeyboardButton("🏠 Menú principal")],
    ],
    resize_keyboard=True,
)

movil_keyboard = ReplyKeyboardMarkup(
    [
        [KeyboardButton("🟢 Iniciar jornada"), KeyboardButton("🔴 Finalizar jornada")],
        [KeyboardButton("📍 Compartir ubicación", request_location=True)],
        [KeyboardButton("💰 Enviar pago"), KeyboardButton("📋 Ver estado pago")],
        [KeyboardButton("🏠 Menú principal")],
    ],
    resize_keyboard=True,
)

admin_keyboard = ReplyKeyboardMarkup(
    [
        [KeyboardButton("➕ Registrar móvil"), KeyboardButton("📃 Ver móviles")],
        [KeyboardButton("✅ Aprobar pago"), KeyboardButton("🔁 Cambiar estado móvil")],
        [KeyboardButton("🏠 Menú principal")],
    ],
    resize_keyboard=True,
)
# -----------------------------
# COMANDOS BÁSICOS
# -----------------------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    context.user_data.clear()

    await update.message.reply_text(
        f"Hola {user.first_name}, soy *PRONTO 3.2* 🚀",
        reply_markup=main_keyboard,
        parse_mode="Markdown",
    )


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Usa /start")


# -----------------------------
# /SOY_MOVIL
# -----------------------------
async def soy_movil(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    context.user_data["soy_nombre"] = None
    context.user_data["soy_telefono"] = None
    context.user_data["soy_estado"] = "pidiendo_nombre"

    await update.message.reply_text(
        "Hola conductor 👋\n\nEscribe tu *nombre completo* para iniciar registro.",
        parse_mode="Markdown",
    )


async def procesar_flujo_soy(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str):
    estado = context.user_data.get("soy_estado")

    # 1️⃣ Pedir nombre
    if estado == "pidiendo_nombre":
        context.user_data["soy_nombre"] = text
        context.user_data["soy_estado"] = "pidiendo_telefono"
        await update.message.reply_text("Ahora escribe tu *número de teléfono*:", parse_mode="Markdown")
        return True

    # 2️⃣ Pedir teléfono
    if estado == "pidiendo_telefono":
        nombre = context.user_data.get("soy_nombre")
        telefono = text.strip()
        user = update.effective_user
        chat_id = update.effective_chat.id

        # GUARDAMOS SOLICITUD PENDIENTE
        pend = load_pending()
        pend[telefono] = {
            "nombre": nombre,
            "telefono": telefono,
            "telegram_id": user.id,
            "chat_id": chat_id,
            "username": user.username,
            "fecha": today_str()
        }
        save_pending(pend)

        # Aviso al móvil
        await update.message.reply_text(
            "Perfecto 👌 Tu solicitud fue enviada al administrador.\n\n"
            "Cuando te registren, ya podrás iniciar jornada.",
            parse_mode="Markdown",
        )

        # Aviso a administradores con botón 📝
        aviso = (
            f"📥 *Nuevo conductor quiere registrarse*\n\n"
            f"👤 *Nombre:* {nombre}\n"
            f"📞 *Teléfono:* `{telefono}`\n"
            f"🪪 *TelegramID:* `{user.id}`\n"
            f"💬 *ChatID:* `{chat_id}`\n"
            f"🌐 *Usuario:* @{user.username if user.username else 'Sin username'}\n\n"
            "¿Deseas iniciar registro ahora?"
        )

        boton = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "📝 Iniciar registro", callback_data=f"REG_MOBIL|{telefono}"
                    )
                ]
            ]
        )

        for admin in ADMIN_IDS:
            try:
                await context.bot.send_message(
                    chat_id=admin, text=aviso, parse_mode="Markdown", reply_markup=boton
                )
            except:
                pass

        context.user_data["soy_estado"] = None
        return True

    return False


# -----------------------------
# CALLBACK: REG_MOBIL (Admin inicia registro)
# -----------------------------
async def handle_registro_inicio(query, context, telefono):
    pend = load_pending()
    info = pend.get(telefono)

    if not info:
        await query.edit_message_text(
            "❌ No se encontró la solicitud. Que el móvil use /soy_movil nuevamente."
        )
        return

    # Guardamos datos preliminares
    context.user_data.clear()
    context.user_data["rol"] = "admin"
    context.user_data["estado"] = "admin_reg_codigo"
    context.user_data["nuevo_tel"] = telefono
    context.user_data["nuevo_nombre"] = info.get("nombre")

    await query.edit_message_text(
        f"📝 Registro iniciado\n\n"
        f"👤 Nombre: {info.get('nombre')}\n"
        f"📞 Teléfono: {telefono}\n\n"
        "Escribe el *código del móvil* (Ej: T003, D001, C002, E004).",
        parse_mode="Markdown",
    )


# -----------------------------
# CALLBACK BOTONES
# -----------------------------
async def button_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data = query.data.split("|")
    action = data[0]

    # REGISTRO MANUAL ADMIN (REG_MOBIL)
    if action == "REG_MOBIL":
        telefono = data[1]
        await handle_registro_inicio(query, context, telefono)
        return


# -----------------------------
# MANEJO DE TEXTO GLOBAL
# -----------------------------
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    user = update.effective_user

    # Si estamos en flujo /soy_movil
    soy_estado = context.user_data.get("soy_estado")
    if soy_estado:
        handled = await procesar_flujo_soy(update, context, text)
        if handled:
            return

    rol = context.user_data.get("rol")
    estado = context.user_data.get("estado")

    # ---------------------
    # MENÚ PRINCIPAL
    # ---------------------
    if text == "🏠 Menú principal":
        context.user_data.clear()
        await update.message.reply_text(
            "Menú principal:", reply_markup=main_keyboard
        )
        return

    # ---------------------
    # MENÚ USUARIO
    # ---------------------
    if text == "Usuario":
        context.user_data.clear()
        context.user_data["rol"] = "usuario"
        await update.message.reply_text(
            "Eres Usuario 🧑‍💼\nElige servicio:",
            reply_markup=user_keyboard,
            parse_mode="Markdown",
        )
        return

    # ---------------------
    # MENÚ MÓVIL
    # ---------------------
    if text == "Móvil":
        context.user_data.clear()
        context.user_data["rol"] = "movil"
        context.user_data["estado"] = "movil_pidiendo_codigo"
        await update.message.reply_text(
            "Escribe tu *código* de móvil (ej: T001):",
            parse_mode="Markdown",
        )
        return

    # ---------------------
    # MENÚ ADMINISTRADOR
    # ---------------------
    if text == "Administrador":
        if user.id not in ADMIN_IDS:
            await update.message.reply_text("No tienes permisos.")
            return

        context.user_data.clear()
        context.user_data["rol"] = "admin"
        await update.message.reply_text(
            "Menú Administrador 🛠️", reply_markup=admin_keyboard
        )
        return

    # ==================================================
    # 💛 AHORA SEGUIRÁ LA PARTE 3
    # ==================================================
# -----------------------------
# DISTANCIA (HAVERSINE)
# -----------------------------
def haversine(a_lat, a_lon, b_lat, b_lon):
    R = 6371
    from math import radians, sin, cos, sqrt, atan2
    dlat = radians(b_lat - a_lat)
    dlon = radians(b_lon - a_lon)
    a = (sin(dlat/2)**2 +
         cos(radians(a_lat)) * cos(radians(b_lat)) * sin(dlon/2)**2)
    return R * 2 * atan2(sqrt(a), sqrt(1 - a))


# -----------------------------
# VALIDAR CONDICIONES DE TRABAJO (PAGO / ACTIVIDAD)
# -----------------------------
def mobile_can_work(m):
    ahora = get_colombia_now()
    corte = ahora.hour >= 15
    hoy = today_str()

    if not m.get("activo", True):
        return False, "Móvil INACTIVO por administrador."

    if not corte:
        return True, "Trabajo permitido antes de las 3 p.m."

    if m.get("ultimo_pago_fecha") == hoy:
        return True, "Pago aprobado para hoy."

    return False, "Ya pasó el corte. Debe pagar y esperar aprobación."


# -----------------------------
# ASIGNACIÓN AUTOMÁTICA DE SERVICIO
# -----------------------------
async def asignar_servicio(service_id, context):
    srv = SERVICES.get(service_id)
    if not srv:
        return

    cliente_lat = srv.get("cliente_lat")
    cliente_lon = srv.get("cliente_lon")
    canal = srv.get("channel")

    mobiles = load_mobiles()

    candidatos = []
    if cliente_lat is not None:
        for code, m in mobiles.items():
            if m.get("servicio") != srv.get("tipo"):
                continue
            if not m.get("en_jornada"):
                continue
            ubic = m.get("ubicacion")
            if not ubic:
                continue
            puede, _ = mobile_can_work(m)
            if not puede:
                continue

            dist = haversine(cliente_lat, cliente_lon, ubic["lat"], ubic["lon"])
            candidatos.append((dist, code, m))

    if candidatos:
        candidatos.sort(key=lambda x: x[0])
        dist, code, mob = candidatos[0]
        srv["estado"] = "asignado"
        srv["movil"] = code

        # Aviso al móvil
        try:
            await context.bot.send_message(
                chat_id=mob.get("chat_id"),
                text=(
                    f"👤 Cliente: {srv['cliente_nombre']}\n"
                    f"📱 Teléfono: {srv['cliente_tel']}\n"
                    f"📍 Distancia aprox: {dist:.1f} km\n\n"
                    f"ID Servicio: {service_id}"
                ),
                reply_markup=InlineKeyboardMarkup(
                    [[InlineKeyboardButton("❌ Cancelar", callback_data=f"CANCEL_M|{service_id}")]]
                ),
            )
        except:
            pass

        # Aviso al cliente
        try:
            await context.bot.send_message(
                chat_id=srv["cliente_chat_id"],
                text=(
                    f"🚗 Móvil asignado: {mob['nombre']} ({code})\n"
                    f"📱 {mob['telefono']}\n\n"
                    f"ID Servicio: {service_id}"
                ),
                reply_markup=InlineKeyboardMarkup(
                    [[InlineKeyboardButton("❌ Cancelar", callback_data=f"CANCEL_C|{service_id}")]]
                ),
            )
        except:
            pass

        return

    # 🚨 SIN MÓVIL → PUBLICA EN CANAL
    try:
        msg = await context.bot.send_message(
            chat_id=canal,
            text=(
                f"🚨 *Nuevo servicio disponible* [{service_id}]\n\n"
                f"Cliente: {srv['cliente_nombre']}\n"
                f"Teléfono: {srv['cliente_tel']}\n"
                f"Dirección: {srv['origen']}"
            ),
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("📲 Tomar servicio", callback_data=f"TAKE|{service_id}")]]
            ),
        )
        srv["msg_canal"] = msg.message_id
    except:
        pass


# -----------------------------
# CANCELACIONES
# -----------------------------
async def cancelar_cliente(query, context, service_id):
    srv = SERVICES.get(service_id)
    if not srv:
        return

    # Avisar al móvil
    if srv.get("movil"):
        try:
            await context.bot.send_message(
                chat_id=load_mobiles()[srv["movil"]].get("chat_id"),
                text=f"⚠️ El cliente canceló el servicio {service_id}"
            )
        except:
            pass

    # Avisar al cliente
    try:
        await context.bot.send_message(
            chat_id=srv["cliente_chat_id"],
            text=f"Servicio {service_id} cancelado correctamente."
        )
    except:
        pass

    srv["estado"] = "cancelado"


async def cancelar_movil(query, context, service_id):
    srv = SERVICES.get(service_id)
    if not srv:
        return

    # Avisar al cliente
    try:
        await context.bot.send_message(
            chat_id=srv["cliente_chat_id"],
            text=f"⚠️ El móvil canceló el servicio {service_id}.\n"
                 "Otro móvil podrá tomarlo."
        )
    except:
        pass

    srv["estado"] = "pendiente"
    srv["movil"] = None


# -----------------------------
# UBICACIÓN
# -----------------------------
async def handle_location(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat_id = update.message.chat_id
    rol = context.user_data.get("rol")

    lat = update.message.location.latitude
    lon = update.message.location.longitude

    if rol == "movil":
        code = None
        mobiles = load_mobiles()
        for c, m in mobiles.items():
            if m.get("telegram_id") == user.id:
                code = c
                break

        if code:
            mobiles[code]["ubicacion"] = {"lat": lat, "lon": lon}
            save_mobiles(mobiles)
            await update.message.reply_text("📍 Ubicación registrada.")
        return

    if rol == "usuario":
        context.user_data["cliente_lat"] = lat
        context.user_data["cliente_lon"] = lon
        await update.message.reply_text("📍 Ubicación recibida.")
        return


# -----------------------------
# CALLBACKS FINAL
# -----------------------------
async def callback_final(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data = query.data.split("|")
    action = data[0]
    sid = data[1]

    if action == "CANCEL_C":
        await cancelar_cliente(query, context, sid)
    elif action == "CANCEL_M":
        await cancelar_movil(query, context, sid)
    elif action == "TAKE":
        await asignar_servicio(sid, context)


# -----------------------------
# MAIN PARA RAILWAY
# -----------------------------
def main():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("soy_movil", soy_movil))
    app.add_handler(CallbackQueryHandler(button_cb))
    app.add_handler(CallbackQueryHandler(callback_final))

    app.add_handler(MessageHandler(filters.LOCATION, handle_location))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    # WEBHOOK RAILWAY
    app.run_webhook(
    listen="0.0.0.0",
    port=int(os.environ.get("PORT", 8080)),
    url_path=f"webhook/{TOKEN}",
    webhook_url=WEBHOOK_DOMAIN + f"/webhook/{TOKEN}"
)


if __name__ == "__main__":
    main()
