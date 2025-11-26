# PRONTO - Webhook estable para Railway con ENDPOINT /corte
# Compatible con python-telegram-bot[webhooks]==20.4

import os
import json
import logging
from datetime import datetime
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)
from http.server import BaseHTTPRequestHandler
from threading import Thread

# ----------------------------
# CONFIG
# ----------------------------

TOKEN = "7668998247:AAECr_Y1sk6P2uOWkw6ZoJMPdmT_EBksAcA"

ADMIN_IDS = [1741298723, 7076796229]

WEBHOOK_DOMAIN = "https://pronto-empty-production.up.railway.app"
WEBHOOK_PATH = f"/webhook/{TOKEN}"
WEBHOOK_URL = WEBHOOK_DOMAIN + WEBHOOK_PATH

MOBILES_FILE = "mobiles.json"

CHANNEL_TAXI = -1002697357566
CHANNEL_DOMICILIOS = -1002503403579
CHANNEL_TRASTEOS = -1002662309590
CHANNEL_TRANSPORTE_DIS = -1002688723492

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

def is_admin(uid):
    return uid in ADMIN_IDS

def get_mobile_by_telegram(uid):
    mobiles = load_mobiles()
    for m in mobiles:
        if m.get("telegram_id") == uid:
            return m
    return None

def get_mobile_by_id(id_movil):
    mobiles = load_mobiles()
    for m in mobiles:
        if m.get("id_movil") == id_movil:
            return m
    return None

def get_channel_for_mobile(m):
    tipo = (m.get("tipo") or "").lower()
    if "taxi" in tipo:
        return CHANNEL_TAXI
    if "domic" in tipo:
        return CHANNEL_DOMICILIOS
    if "trast" in tipo:
        return CHANNEL_TRASTEOS
    if "dis" in tipo or "cap" in tipo:
        return CHANNEL_TRANSPORTE_DIS
    return None

# ----------------------------
# TECLADOS
# ----------------------------

main_keyboard = ReplyKeyboardMarkup(
    [["Usuario"], ["Móvil"], ["Administrador"]],
    resize_keyboard=True,
)

user_keyboard = ReplyKeyboardMarkup(
    [
        ["📦 Pedir domicilio"],
        ["🚕 Pedir taxi"],
        ["🚚 Pedir trasteo"],
        ["♿ Transporte discapacitados"],
        ["⬅️ Volver"],
    ],
    resize_keyboard=True,
)

movil_keyboard = ReplyKeyboardMarkup(
    [
        ["🟢 Iniciar jornada"],
        ["🔴 Finalizar jornada"],
        ["💳 Pagar mi jornada"],
        ["📌 Estado"],
        ["⬅️ Volver"],
    ],
    resize_keyboard=True,
)

admin_keyboard = ReplyKeyboardMarkup(
    [
        ["➕ Registrar móvil", "📋 Ver móviles"],
        ["💳 Aprobar pago"],
        ["⬅️ Volver"],
    ],
    resize_keyboard=True,
)

# ----------------------------
# HANDLERS
# ----------------------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Hola 💛, soy PRONTO.\nElige una opción:", reply_markup=main_keyboard)

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    uid = update.effective_user.id

    # ---------------- VINCULAR MOVIL ----------------
    if context.user_data.get("mobile_linking"):
        id_movil = text.strip()
        m = get_mobile_by_id(id_movil)
        if not m:
            await update.message.reply_text("Ese ID no existe. Ejemplo correcto: P100")
            return

        mobiles = load_mobiles()
        for mob in mobiles:
            if mob.get("id_movil") == id_movil:
                mob["telegram_id"] = uid
        save_mobiles(mobiles)

        context.user_data["mobile_linking"] = False
        await update.message.reply_text(f"Vinculado correctamente como {id_movil}.", reply_markup=movil_keyboard)
        return

    # ---------------- VOLVER ----------------
    if text == "⬅️ Volver":
        context.user_data.clear()
        await update.message.reply_text("Volviste al menú.", reply_markup=main_keyboard)
        return

    # ---------------- ADMIN ----------------
    if text == "Administrador":
        if not is_admin(uid):
            await update.message.reply_text("❌ No tienes permisos.")
            return
        await update.message.reply_text("Panel Administrativo", reply_markup=admin_keyboard)
        return

    # Registrar móvil
    if is_admin(uid) and text == "➕ Registrar móvil":
        context.user_data["admin_action"] = "reg_nombre"
        context.user_data["temp"] = {}
        await update.message.reply_text("Nombre del conductor:")
        return

    # ---------------- REGISTRO FLUJO ----------------
    if context.user_data.get("admin_action", "").startswith("reg_"):
        temp = context.user_data["temp"]
        step = context.user_data["admin_action"]

        if step == "reg_nombre":
            temp["nombre"] = text
            context.user_data["admin_action"] = "reg_cedula"
            await update.message.reply_text("Cédula:")
            return

        if step == "reg_cedula":
            temp["cedula"] = text
            context.user_data["admin_action"] = "reg_tipo"
            await update.message.reply_text("Tipo (Taxi, Domicilios, Trasteos, Discapacitados):")
            return

        if step == "reg_tipo":
            temp["tipo"] = text
            context.user_data["admin_action"] = "reg_marca"
            await update.message.reply_text("Marca y modelo:")
            return

        if step == "reg_marca":
            temp["marca"] = text
            context.user_data["admin_action"] = "reg_placa"
            await update.message.reply_text("Placa:")
            return

        if step == "reg_placa":
            temp["placa"] = text
            temp["activo"] = False
            temp["en_jornada"] = False

            mobiles = load_mobiles()
            id_movil = "P" + str(100 + len(mobiles))
            temp["id_movil"] = id_movil

            mobiles.append(temp)
            save_mobiles(mobiles)
            context.user_data.clear()

            await update.message.reply_text(
                f"✔️ Móvil registrado\n\n"
                f"ID: {id_movil}\n"
                f"Nombre: {temp['nombre']}\n"
                f"Cédula: {temp['cedula']}\n"
                f"Vehículo: {temp['tipo']} - {temp['marca']}\n"
                f"Placa: {temp['placa']}\n"
                f"Estado: INACTIVO",
                reply_markup=admin_keyboard,
            )
            return

    # ---------------- VER MOVILES ----------------
    if is_admin(uid) and text == "📋 Ver móviles":
        mobiles = load_mobiles()
        if not mobiles:
            await update.message.reply_text("No hay móviles registrados.")
            return
        msg = "📋 *Móviles registrados:*\n\n"
        for m in mobiles:
            estado = "ACTIVO" if m.get("activo") else "INACTIVO"
            msg += (
                f"ID: {m['id_movil']}\n"
                f"{m['nombre']} - {m['cedula']}\n"
                f"{m['tipo']} - {m['marca']}\n"
                f"Placa: {m['placa']}\n"
                f"{estado}\n\n"
            )
        await update.message.reply_text(msg, parse_mode="Markdown")
        return

    # ---------------- APROBAR PAGO ----------------
    if is_admin(uid) and text == "💳 Aprobar pago":
        context.user_data["admin_action"] = "pago_id"
        await update.message.reply_text("Escribe el ID del móvil (ej: P100):")
        return

    if context.user_data.get("admin_action") == "pago_id":
        id_movil = text.strip()
        mobiles = load_mobiles()
        found = False
        for m in mobiles:
            if m.get("id_movil") == id_movil:
                m["activo"] = True
                found = True
                break
        save_mobiles(mobiles)
        context.user_data.clear()
        if found:
            await update.message.reply_text(f"✔️ Móvil {id_movil} ACTIVADO.")
        else:
            await update.message.reply_text("❌ Ese ID no existe.")
        return

    # ---------------- USUARIO ----------------
    if text == "Usuario":
        await update.message.reply_text("Menú Usuario 👤", reply_markup=user_keyboard)
        return

    # ---------------- SERVICIO TAXI ----------------
    if text == "🚕 Pedir taxi":
        context.user_data["servicio"] = "taxi_origen"
        await update.message.reply_text("📍 Envíame tu ubicación o escríbela:")
        return

    if context.user_data.get("servicio") == "taxi_origen":
        context.user_data["origen"] = text
        context.user_data["servicio"] = "taxi_destino"
        await update.message.reply_text("🎯 ¿Cuál es tu *destino*?")
        return

    if context.user_data.get("servicio") == "taxi_destino":
        context.user_data["destino"] = text
        context.user_data["servicio"] = "taxi_referencia"
        await update.message.reply_text("🗒️ ¿Referencia?")
        return

    if context.user_data.get("servicio") == "taxi_referencia":
        referencia = text
        origen = context.user_data.get("origen")
        destino = context.user_data.get("destino")
        nombre = update.effective_user.first_name or "Cliente"
        hora = datetime.now().strftime("%I:%M %p")

        msg = (
            "🚕 *NUEVO SERVICIO DE TAXI* 🚕\n\n"
            f"📍 *Origen:* {origen}\n"
            f"🎯 *Destino:* {destino}\n"
            f"🗒️ *Referencia:* {referencia}\n\n"
            f"👤 *Cliente:* {nombre}\n"
            f"⏰ *Hora:* {hora}"
        )

        await context.bot.send_message(chat_id=CHANNEL_TAXI, text=msg, parse_mode="Markdown")
        await update.message.reply_text("✔️ Tu solicitud fue enviada 💛", reply_markup=user_keyboard)
        context.user_data.clear()
        return

    # ---------------- SERVICIO DOMICILIOS ----------------
    if text == "📦 Pedir domicilio":
        context.user_data["servicio"] = "dom_origen"
        await update.message.reply_text("📍 ¿Cuál es el origen?")
        return

    if context.user_data.get("servicio") == "dom_origen":
        context.user_data["origen"] = text
        context.user_data["servicio"] = "dom_pedido"
        await update.message.reply_text("📦 ¿Qué deseas enviar o pedir?")
        return

    if context.user_data.get("servicio") == "dom_pedido":
        context.user_data["pedido"] = text
        context.user_data["servicio"] = "dom_destino"
        await update.message.reply_text("🎯 ¿Destino?")
        return

    if context.user_data.get("servicio") == "dom_destino":
        context.user_data["destino"] = text
        context.user_data["servicio"] = "dom_referencia"
        await update.message.reply_text("🗒️ ¿Referencia?")
        return

    if context.user_data.get("servicio") == "dom_referencia":
        referencia = text
        origen = context.user_data.get("origen")
        pedido = context.user_data.get("pedido")
        destino = context.user_data.get("destino")
        nombre = update.effective_user.first_name or "Cliente"
        hora = datetime.now().strftime("%I:%M %p")

        msg = (
            "📦 *NUEVO SERVICIO DE DOMICILIO* 📦\n\n"
            f"📍 *Origen:* {origen}\n"
            f"📦 *Pedido:* {pedido}\n"
            f"🎯 *Destino:* {destino}\n"
            f"🗒️ *Referencia:* {referencia}\n\n"
            f"👤 *Cliente:* {nombre}\n"
            f"⏰ *Hora:* {hora}"
        )

        await context.bot.send_message(chat_id=CHANNEL_DOMICILIOS, text=msg, parse_mode="Markdown")
        await update.message.reply_text("✔️ Tu solicitud fue enviada 💛", reply_markup=user_keyboard)
        context.user_data.clear()
        return

    # ---------------- SERVICIO TRASTEOS ----------------
    if text == "🚚 Pedir trasteo":
        context.user_data["servicio"] = "tras_nombre"
        await update.message.reply_text("👤 ¿Cuál es tu nombre completo?")
        return

    if context.user_data.get("servicio") == "tras_nombre":
        context.user_data["nombre_trasteo"] = text
        context.user_data["servicio"] = "tras_tel"
        await update.message.reply_text("📞 ¿Cuál es tu número de teléfono?")
        return

    if context.user_data.get("servicio") == "tras_tel":
        telefono = text
        nombre = context.user_data.get("nombre_trasteo")
        hora = datetime.now().strftime("%I:%M %p")

        msg = (
            "🚚 *NUEVO SERVICIO DE TRASTEO* 🚚\n\n"
            f"👤 *Cliente:* {nombre}\n"
            f"📞 *Teléfono:* {telefono}\n"
            f"⏰ *Hora:* {hora}"
        )

        await context.bot.send_message(chat_id=CHANNEL_TRASTEOS, text=msg, parse_mode="Markdown")
        await update.message.reply_text("✔️ Tu solicitud fue enviada 💛", reply_markup=user_keyboard)
        context.user_data.clear()
        return

    # ---------------- SERVICIO DISCAPACITADOS (IGUAL A TRASTEOS) ----------------
    if text == "♿ Transporte discapacitados":
        context.user_data["servicio"] = "dis_nombre"
        await update.message.reply_text("👤 ¿Cuál es tu nombre completo?")
        return

    if context.user_data.get("servicio") == "dis_nombre":
        context.user_data["nombre_dis"] = text
        context.user_data["servicio"] = "dis_tel"
        await update.message.reply_text("📞 ¿Cuál es tu número de teléfono?")
        return

    if context.user_data.get("servicio") == "dis_tel":
        telefono = text
        nombre = context.user_data.get("nombre_dis")
        hora = datetime.now().strftime("%I:%M %p")

        msg = (
            "♿ *NUEVO SERVICIO – TRANSPORTE A DISCAPACITADOS* ♿\n\n"
            f"👤 *Cliente:* {nombre}\n"
            f"📞 *Teléfono:* {telefono}\n"
            f"⏰ *Hora:* {hora}"
        )

        await context.bot.send_message(
            chat_id=CHANNEL_TRANSPORTE_DIS,
            text=msg,
            parse_mode="Markdown"
        )

        await update.message.reply_text("✔️ Tu solicitud fue enviada 💛", reply_markup=user_keyboard)
        context.user_data.clear()
        return

    # ---------------- MÓVIL ----------------
    if text == "Móvil":
        mobile = get_mobile_by_telegram(uid)
        if not mobile:
            context.user_data["mobile_linking"] = True
            await update.message.reply_text("Escribe tu ID de móvil (ej: P100):")
            return
        await update.message.reply_text("Menú Móvil 🚗", reply_markup=movil_keyboard)
        return

    # --- INICIAR JORNADA
    from datetime import datetime, time

# -----------------------------------
# FUNCIÓN: DETERMINAR SI DEBE PAGAR
# -----------------------------------
def requiere_pago():
    ahora = datetime.now().time()
    hora_limite = time(15, 0)  # 3:00 pm
    return ahora >= hora_limite  # Solo aplicar bloqueo después de las 3pm


# -----------------------------------
# FUNCIÓN: INICIAR JORNADA
# -----------------------------------
async def iniciar_jornada(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    mobiles = cargar_mobiles()

    if str(user_id) not in mobiles:
        await update.message.reply_text("No estás registrado como móvil 🚫")
        return

    movil = mobiles[str(user_id)]
    nombre = movil.get("nombre", "Móvil")
    servicio = movil.get("servicio", None)
    pagado = movil.get("pagado", False)

    # ⚠️ BLOQUEO SI ES DESPUÉS DE LAS 3PM Y NO HA PAGADO
    if requiere_pago() and not pagado:
        await update.message.reply_text(
            "⛔ *Debes pagar tu cuota diaria para continuar trabajando*\n"
            "El sistema se bloquea desde las 3:00 pm.\n\n"
            "Por favor realiza tu pago y espera aprobación del administrador ❤️",
            parse_mode="Markdown"
        )
        return

    # LINKS REALES DE LOS CANALES
    enlaces = {
        "taxi": "https://t.me/c/1002697357566",  
        "domicilios": "https://t.me/c/1002503403579",
        "trasteos": "https://t.me/c/1002662309590",
        "discapacidad": "https://t.me/c/1002688723492",
    }

    if servicio not in enlaces:
        await update.message.reply_text("Error: No tienes un servicio asignado 🚫")
        return

    enlace = enlaces[servicio]

    # ACTIVACIÓN DE JORNADA
    movil["activo"] = True
    guardar_mobiles(mobiles)

    await update.message.reply_text(
        f"🚀 *Jornada iniciada*\n"
        f"Bienvenido {nombre}, ya puedes recibir servicios aquí:\n{enlace}",
        parse_mode="Markdown"
    )

    # --- FINALIZAR JORNADA
    if text == "🔴 Finalizar jornada":
        mobile = get_mobile_by_telegram(uid)
        if not mobile:
            await update.message.reply_text("No estás vinculado.")
            return

        mobiles = load_mobiles()
        for m in mobiles:
            if m["id_movil"] == mobile["id_movil"]:
                m["en_jornada"] = False
        save_mobiles(mobiles)

        await update.message.reply_text("Jornada finalizada 💛")
        return

    # --- PAGO
    if text == "💳 Pagar mi jornada":
        mobile = get_mobile_by_telegram(uid)
        if not mobile:
            await update.message.reply_text("No estás vinculado.")
            return

        await update.message.reply_text(
            "💳 *PAGO NEQUI*\n\n"
            "Número: `3052915231`\n\n"
            "Mensaje:\n"
            f"`Móvil {mobile['id_movil']}`\n\n"
            "Espera aprobación del administrador.",
            parse_mode="Markdown",
        )
        return

    # --- ESTADO
    if text == "📌 Estado":
        mobile = get_mobile_by_telegram(uid)
        if not mobile:
            await update.message.reply_text("No estás vinculado.")
            return

        estado = "ACTIVO" if mobile.get("activo") else "INACTIVO"
        jornada = "EN JORNADA" if mobile.get("en_jornada") else "FUERA DE JORNADA"

        await update.message.reply_text(
            f"📌 *Estado actual*\n\n"
            f"ID: {mobile['id_movil']}\n"
            f"Nombre: {mobile['nombre']}\n"
            f"Vehículo: {mobile['tipo']} - {mobile['marca']}\n"
            f"Placa: {mobile['placa']}\n"
            f"Pago: {estado}\n"
            f"Jornada: {jornada}\n"
            f"Corte diario: 3:00 PM",
            parse_mode="Markdown",
        )
        return

    await update.message.reply_text("Usa el menú 💛", reply_markup=main_keyboard)

# ----------------------------
# ENDPOINT /corte (CRON 3 PM)
# ----------------------------

async def ejecutar_corte(context: ContextTypes.DEFAULT_TYPE):
    mobiles = load_mobiles()
    cambios = False

    for m in mobiles:
        if m.get("activo") or m.get("en_jornada"):
            m["activo"] = False
            m["en_jornada"] = False
            cambios = True

            tid = m.get("telegram_id")
            if tid:
                try:
                    await context.bot.send_message(
                        chat_id=tid,
                        text=(
                            "⏰ Tu jornada de hoy terminó.\n"
                            "Si deseas trabajar mañana, realiza tu pago nuevamente 💳."
                        )
                    )
                except:
                    pass

    if cambios:
        save_mobiles(mobiles)

class CorteHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/corte":
            loop = application.bot._application_loop
            loop.create_task(ejecutar_corte(application.bot._context))

            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"Corte ejecutado correctamente.")
        else:
            self.send_response(404)
            self.end_headers()

def iniciar_servidor_corte():
    from http.server import HTTPServer
    server = HTTPServer(("0.0.0.0", 8000), CorteHandler)
    server.serve_forever()

# ----------------------------
# MAIN
# ----------------------------

if __name__ == "__main__":
    PORT = int(os.environ.get("PORT", 8080))

    application = ApplicationBuilder().token(TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    Thread(target=iniciar_servidor_corte, daemon=True).start()

    application.run_webhook(
        listen="0.0.0.0",
        port=PORT,
        url_path=WEBHOOK_PATH,
        webhook_url=WEBHOOK_URL,
    )
