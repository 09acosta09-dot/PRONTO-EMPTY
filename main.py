# PRONTO - Webhook estable para Railway
# Compatible con Python 3.13 y python-telegram-bot[webhooks]==20.4

import os
import logging
import json
from datetime import datetime, time as dtime
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# ----------------------------
# CONFIG
# ----------------------------

TOKEN = "7668998247:AAECr_Y1sk6P2uOWkw6ZoJMPdmT_EBksAcA"

ADMIN_IDS = [1741298723, 7076796229]

WEBHOOK_DOMAIN = "https://pronto-empty-production.up.railway.app"
WEBHOOK_PATH = f"/webhook/{TOKEN}"
WEBHOOK_URL = WEBHOOK_DOMAIN + WEBHOOK_PATH

MOBILES_FILE = "mobiles.json"
SERVICES_FILE = "services.json"

# Canales (ya confirmados, bot debe ser admin en todos)
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
    except Exception:
        return default


def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def is_admin(uid: int) -> bool:
    return uid in ADMIN_IDS


def load_mobiles():
    return load_json(MOBILES_FILE, [])


def save_mobiles(data):
    save_json(MOBILES_FILE, data)


def get_mobile_by_telegram(uid: int):
    """Busca un móvil vinculado a este Telegram ID."""
    mobiles = load_mobiles()
    for m in mobiles:
        if m.get("telegram_id") == uid:
            return m
    return None


def get_mobile_by_id(id_movil: str):
    """Busca un móvil por su ID tipo P100."""
    mobiles = load_mobiles()
    for m in mobiles:
        if m.get("id_movil") == id_movil:
            return m
    return None


def get_channel_for_mobile(m: dict):
    """Devuelve el canal según el tipo de vehículo."""
    tipo = (m.get("tipo") or "").lower()
    if "taxi" in tipo:
        return CHANNEL_TAXI
    if "domic" in tipo:
        return CHANNEL_DOMICILIOS
    if "trast" in tipo:
        return CHANNEL_TRASTEOS
    if "dis" in tipo or "capac" in tipo:
        return CHANNEL_TRANSPORTE_DIS
    return None

# ----------------------------
# TECLADOS
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
    await update.message.reply_text(
        "Hola 💛, soy PRONTO.\nElige una opción:",
        reply_markup=main_keyboard,
    )


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    uid = update.effective_user.id

    # ---------------- VINCULACIÓN DE MÓVIL POR ID (P100...) ----------------
    if context.user_data.get("mobile_linking"):
        id_movil = text.strip()
        m = get_mobile_by_id(id_movil)
        if not m:
            await update.message.reply_text(
                "No encontré ese ID de móvil.\n"
                "Verifica con tu administrador (ejemplo: P100) y escríbelo de nuevo."
            )
            return

        mobiles = load_mobiles()
        for mob in mobiles:
            if mob.get("id_movil") == id_movil:
                mob["telegram_id"] = uid
                break
        save_mobiles(mobiles)
        context.user_data["mobile_linking"] = False

        await update.message.reply_text(
            f"Perfecto ✅\nQuedaste vinculado como {id_movil}.",
            reply_markup=movil_keyboard,
        )
        return

    # ---------------- BOTÓN VOLVER ----------------
    if text == "⬅️ Volver":
        context.user_data.clear()
        await update.message.reply_text("Volviste al menú principal.", reply_markup=main_keyboard)
        return

    # ---------------- ADMINISTRADOR ----------------
    if text == "Administrador":
        if not is_admin(uid):
            await update.message.reply_text("❌ No tienes permisos para esta sección.")
            return
        await update.message.reply_text("Panel Administrador 🛠️", reply_markup=admin_keyboard)
        return

    # Registrar móvil (admin)
    if is_admin(uid) and text == "➕ Registrar móvil":
        context.user_data["admin_action"] = "reg_nombre"
        context.user_data["temp"] = {}
        await update.message.reply_text("Nombre del conductor:")
        return

    # Flujo de registro de móvil
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
            await update.message.reply_text(
                "Tipo de vehículo (Taxi, Domicilios, Trasteos, Discapacitados):"
            )
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
            # ID tipo P100, P101, etc.
            id_movil = "P" + str(100 + len(mobiles))
            temp["id_movil"] = id_movil

            mobiles.append(temp)
            save_mobiles(mobiles)

            context.user_data.clear()

            await update.message.reply_text(
                f"✔️ Móvil registrado:\n\n"
                f"ID: {id_movil}\n"
                f"Nombre: {temp['nombre']}\n"
                f"Cédula: {temp['cedula']}\n"
                f"Vehículo: {temp['tipo']} - {temp['marca']}\n"
                f"Placa: {temp['placa']}\n"
                f"Estado: INACTIVO",
                reply_markup=admin_keyboard,
            )
            return

    # Ver móviles (admin)
    if is_admin(uid) and text == "📋 Ver móviles":
        mobiles = load_mobiles()
        if not mobiles:
            await update.message.reply_text("No hay móviles registrados.")
            return

        msg = "📋 *Móviles registrados:*\n\n"
        for m in mobiles:
            estado = "ACTIVO ✅" if m.get("activo") else "INACTIVO ⛔"
            msg += (
                f"ID: {m.get('id_movil', 'N/A')}\n"
                f"{m.get('nombre', '')} - {m.get('cedula', '')}\n"
                f"{m.get('tipo', '')} - {m.get('marca', '')}\n"
                f"Placa: {m.get('placa', '')}\n"
                f"{estado}\n\n"
            )
        await update.message.reply_text(msg, parse_mode="Markdown")
        return

    # Aprobar pago (admin) por ID de móvil
    if is_admin(uid) and text == "💳 Aprobar pago":
        context.user_data["admin_action"] = "pago_id"
        await update.message.reply_text(
            "Escribe el *ID del móvil* (ejemplo P100):",
            parse_mode="Markdown",
        )
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
        context.user_data.clear()
        if found:
            save_mobiles(mobiles)
            await update.message.reply_text(f"✔️ Móvil {id_movil} ACTIVADO.")
        else:
            await update.message.reply_text("❌ No encontré ese ID de móvil.")
        return

    # ---------------- USUARIO ----------------
    if text == "Usuario":
        await update.message.reply_text("Menú Usuario 👤", reply_markup=user_keyboard)
        return

    if text == "📦 Pedir domicilio":
        await update.message.reply_text(
            "Aquí irá el flujo para pedir domicilio 🏍️ (en construcción)."
        )
        return

    if text == "🚕 Pedir taxi":
        await update.message.reply_text(
            "Aquí irá el flujo para pedir taxi 🚕 (en construcción)."
        )
        return

    if text == "🚚 Pedir trasteo":
        await update.message.reply_text(
            "Aquí irá el flujo para pedir trasteo 🚚 (en construcción)."
        )
        return

    if text == "♿ Transporte discapacitados":
        await update.message.reply_text(
            "Aquí irá el flujo para transporte discapacitados ♿ (en construcción)."
        )
        return

    # ---------------- MÓVIL ----------------
    if text == "Móvil":
        mobile = get_mobile_by_telegram(uid)
        if not mobile:
            context.user_data["mobile_linking"] = True
            await update.message.reply_text(
                "Para continuar, escribe tu *ID de móvil* (ejemplo P100).\n"
                "Si no lo recuerdas, pídelo a tu administrador.",
                parse_mode="Markdown",
            )
            return
        await update.message.reply_text("Menú Móvil 🚗", reply_markup=movil_keyboard)
        return

    # Iniciar jornada
    if text == "🟢 Iniciar jornada":
        mobile = get_mobile_by_telegram(uid)
        if not mobile:
            await update.message.reply_text(
                "No estás vinculado a ningún móvil.\n"
                "Toca 'Móvil' en el menú principal para vincular tu ID primero."
            )
            return

        if not mobile.get("activo"):
            await update.message.reply_text(
                "Tu pago está pendiente 💳\n"
                "Paga tu jornada con '💳 Pagar mi jornada' y espera aprobación."
            )
            return

        mobiles = load_mobiles()
        for m in mobiles:
            if m.get("id_movil") == mobile.get("id_movil"):
                m["en_jornada"] = True
                break
        save_mobiles(mobiles)

        channel_id = get_channel_for_mobile(mobile)
        if channel_id:
            try:
                invite = await context.bot.create_chat_invite_link(
                    chat_id=channel_id,
                    name=f"Acceso {mobile.get('id_movil')}",
                )
                await update.message.reply_text(
                    "Jornada iniciada ✅\n"
                    "Usa este enlace para acceder a tu canal de servicios:\n"
                    f"{invite.invite_link}"
                )
            except Exception as e:
                logger.error(f"Error creando link de canal: {e}")
                await update.message.reply_text(
                    "Jornada iniciada ✅\n"
                    "Pero no pude generar el link del canal, contacta a tu administrador."
                )
        else:
            await update.message.reply_text(
                "Jornada iniciada ✅\n"
                "Consulta con tu administrador el canal de servicios."
            )
        return

    # Finalizar jornada
    if text == "🔴 Finalizar jornada":
        mobile = get_mobile_by_telegram(uid)
        if not mobile:
            await update.message.reply_text(
                "No estás vinculado a ningún móvil.\n"
                "Toca 'Móvil' en el menú principal para vincular tu ID primero."
            )
            return

        mobiles = load_mobiles()
        for m in mobiles:
            if m.get("id_movil") == mobile.get("id_movil"):
                m["en_jornada"] = False
                break
        save_mobiles(mobiles)

        await update.message.reply_text(
            "Has finalizado tu jornada de hoy.\nGracias por usar PRONTO 💛",
            reply_markup=movil_keyboard,
        )
        return

    # Pagar jornada
    if text == "💳 Pagar mi jornada":
        mobile = get_mobile_by_telegram(uid)
        if not mobile:
            await update.message.reply_text(
                "No estás vinculado a ningún móvil.\n"
                "Toca 'Móvil' en el menú principal para vincular tu ID primero."
            )
            return

        id_movil = mobile.get("id_movil", "N/D")
        await update.message.reply_text(
            "💳 *PAGO NEQUI*\n\n"
            "Envía tu pago a:\n"
            "`Nequi: 3052915231`\n\n"
            "En el mensaje de la transferencia escribe:\n"
            f"`Móvil {id_movil}`\n\n"
            "Después del pago, espera a que el administrador apruebe tu acceso ✅",
            parse_mode="Markdown",
        )
        return

    # Estado del móvil
    if text == "📌 Estado":
        mobile = get_mobile_by_telegram(uid)
        if not mobile:
            await update.message.reply_text(
                "No estás vinculado a ningún móvil.\n"
                "Toca 'Móvil' en el menú principal para vincular tu ID primero."
            )
            return

        estado_pago = "ACTIVO ✅" if mobile.get("activo") else "INACTIVO ⛔ (pendiente pago)"
        jornada = "EN JORNADA 🟢" if mobile.get("en_jornada") else "FUERA DE JORNADA 🔴"

        msg = (
            "📌 *Estado actual*\n\n"
            f"ID: {mobile.get('id_movil','N/D')}\n"
            f"Nombre: {mobile.get('nombre','')}\n"
            f"Vehículo: {mobile.get('tipo','')} - {mobile.get('marca','')}\n"
            f"Placa: {mobile.get('placa','')}\n\n"
            f"Pago: {estado_pago}\n"
            f"Jornada: {jornada}\n"
            "Corte diario: 3:00 PM\n"
        )
        await update.message.reply_text(msg, parse_mode="Markdown")
        return

    # ---------------- DEFAULT ----------------
    await update.message.reply_text("Usa el menú 💛", reply_markup=main_keyboard)

# ----------------------------
# CORTE DIARIO 3 PM
# ----------------------------

async def corte_diario(context: ContextTypes.DEFAULT_TYPE):
    """Job diario: apaga jornada y pago de todos los móviles a las 3 PM."""
    mobiles = load_mobiles()
    changed = False

    for m in mobiles:
        if m.get("activo") or m.get("en_jornada"):
            m["activo"] = False
            m["en_jornada"] = False
            changed = True

            tid = m.get("telegram_id")
            if tid:
                try:
                    await context.bot.send_message(
                        chat_id=tid,
                        text=(
                            "⏰ Tu jornada de hoy ha finalizado.\n"
                            "Si deseas trabajar mañana, realiza tu pago nuevamente 💳."
                        ),
                    )
                except Exception as e:
                    logger.error(f"Error enviando mensaje de corte a {tid}: {e}")

    if changed:
        save_mobiles(mobiles)

# ----------------------------
# MAIN - WEBHOOK + JOB
# ----------------------------

if __name__ == "__main__":
    PORT = int(os.environ.get("PORT", 8080))

    application = ApplicationBuilder().token(TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    # Job diario de corte a las 3:00 PM (hora del servidor)
    job_queue = application.job_queue
    job_queue.run_daily(corte_diario, time=dtime(hour=15, minute=0))

    application.run_webhook(
        listen="0.0.0.0",
        port=PORT,
        url_path=WEBHOOK_PATH,
        webhook_url=WEBHOOK_URL,
    )
