# PRONTO 3.1 - Versión limpia y completa
# Requisitos:
#   - python-telegram-bot v20+
#
# Características:
# - Menú Usuario / Móvil / Administrador
# - 4 servicios: Taxi, Domicilios, Camionetas, Transporte discapacitados
# - Cliente puede compartir ubicación
# - Bot intenta asignar el servicio al móvil más cercano (por ubicación)
# - /soy_movil captura el chat_id del conductor y crea/vincula solicitud
# - El administrador registra el móvil (código, nombre, cédula, placa, marca, modelo, servicio)
# - Corte a las 3:00 p.m. (hora Colombia)
# - Flujo de pago con Nequi
# - Cliente ve info del móvil y el móvil ve info del cliente
# - Botón de cancelar servicio para el cliente (y opcional para el móvil)
# - Envío de información al canal correspondiente

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

# ---------------------------
# CONFIGURACIÓN
# ---------------------------

TOKEN = "7668998247:AAHaeLXjsxpy1dDhp0Z9AfuFq1tyTIALTJ4"  # Token actual de PRONTO

# IDs de administradores
ADMIN_IDS = [1741298723, 7076796229]

# Archivos de datos
MOBILES_FILE = "mobiles.json"
PENDING_MOBILES_FILE = "pending_mobiles.json"

# Número de NEQUI
NEQUI_NUMBER = "3000000000"  # Cámbialo al real

# Canales (IDs confirmados, con -100...)
CHANNEL_TAXI = -1002697357566
CHANNEL_DOMICILIOS = -1002503403579
CHANNEL_CAMIONETAS = -1002662309590
CHANNEL_TRANSPORTE_DIS = -1002688723492

# Servicios en memoria (se pierden si el bot se reinicia)
SERVICES = {}  # service_id -> dict

# ---------------------------
# LOGS
# ---------------------------

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


# ---------------------------
# UTILIDADES GENERALES
# ---------------------------

def get_colombia_now() -> datetime:
    """Devuelve la hora actual aproximada de Colombia (UTC-5) basada en UTC del servidor."""
    return datetime.utcnow() - timedelta(hours=5)


def today_str_colombia() -> str:
    return get_colombia_now().strftime("%Y-%m-%d")


def load_mobiles() -> dict:
    """Carga los móviles desde el archivo JSON, o devuelve dict vacío."""
    if not os.path.exists(MOBILES_FILE):
        return {}
    try:
        with open(MOBILES_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Error cargando {MOBILES_FILE}: {e}")
        return {}


def save_mobiles(mobiles: dict):
    """Guarda los móviles en el archivo JSON."""
    try:
        with open(MOBILES_FILE, "w", encoding="utf-8") as f:
            json.dump(mobiles, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"Error guardando {MOBILES_FILE}: {e}")


def load_pending_mobiles() -> dict:
    """Carga las solicitudes /soy_movil desde archivo."""
    if not os.path.exists(PENDING_MOBILES_FILE):
        return {}
    try:
        with open(PENDING_MOBILES_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Error cargando {PENDING_MOBILES_FILE}: {e}")
        return {}


def save_pending_mobiles(pending: dict):
    """Guarda las solicitudes /soy_movil en archivo."""
    try:
        with open(PENDING_MOBILES_FILE, "w", encoding="utf-8") as f:
            json.dump(pending, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"Error guardando {PENDING_MOBILES_FILE}: {e}")


def find_mobile_by_telegram_id(telegram_id: int):
    """Busca un móvil por telegram_id y devuelve (codigo, data) o (None, None)."""
    mobiles = load_mobiles()
    for code, data in mobiles.items():
        if data.get("telegram_id") == telegram_id:
            return code, data
    return None, None


def get_channel_for_service(service_type: str) -> int | None:
    """Devuelve el ID de canal según el tipo de servicio."""
    if service_type == "taxi":
        return CHANNEL_TAXI
    if service_type == "domicilios":
        return CHANNEL_DOMICILIOS
    if service_type == "camionetas":
        return CHANNEL_CAMIONETAS
    if service_type == "discapacidad":
        return CHANNEL_TRANSPORTE_DIS
    return None


def service_prefix(service_type: str) -> str:
    if service_type == "taxi":
        return "TAX"
    if service_type == "domicilios":
        return "DOM"
    if service_type == "camionetas":
        return "CAM"
    if service_type == "discapacidad":
        return "DIS"
    return "SRV"


def mobile_service_name(service_type: str) -> str:
    if service_type == "taxi":
        return "Taxi"
    if service_type == "domicilios":
        return "Domicilios"
    if service_type == "camionetas":
        return "Camionetas"
    if service_type == "discapacidad":
        return "Transporte discapacitados"
    return "Desconocido"


def mobile_can_work(mobile: dict) -> tuple[bool, str]:
    """
    Verifica si el móvil puede trabajar según:
    - Estado activo
    - Corte de las 3 pm
    - Pago del día
    """
    if not mobile.get("activo", True):
        return False, "Tu móvil está desactivado por el administrador."

    now = get_colombia_now()
    hour = now.hour
    today = today_str_colombia()

    if hour < 15:
        return True, "Puedes trabajar libremente antes de las 3:00 p.m."

    ultimo_pago = mobile.get("ultimo_pago_fecha")
    if ultimo_pago == today:
        return True, "Tienes el pago de hoy aprobado. Puedes trabajar después de las 3:00 p.m."

    return False, (
        "Ya pasó el corte de las 3:00 p.m.\n\n"
        "Debes realizar el pago del día a Nequi y esperar aprobación del administrador "
        "para poder tomar servicios."
    )


def haversine_km(lat1, lon1, lat2, lon2) -> float:
    """
    Calcula la distancia aproximada en kilómetros entre dos puntos (lat, lon) usando Haversine.
    """
    R = 6371.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)

    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c


# ---------------------------
# MENÚS
# ---------------------------

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

user_location_keyboard = ReplyKeyboardMarkup(
    [
        [KeyboardButton("📍 Enviar ubicación actual", request_location=True)],
        [KeyboardButton("Omitir ubicación")],
    ],
    resize_keyboard=True,
)


# ---------------------------
# COMANDOS BÁSICOS
# ---------------------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    context.user_data.clear()

    await update.message.reply_text(
        f"Hola {user.first_name}, soy *PRONTO 3.1* 🚀\n\n"
        "Elige una opción:",
        reply_markup=main_keyboard,
        parse_mode="Markdown",
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Usa /start para ver el menú principal.")


# ---------------------------
# COMANDO /SOY_MOVIL
# ---------------------------

# --- Aviso a los administradores con botón ---
aviso = (
    f"📥 *Nuevo conductor quiere registrarse*\n\n"
    f"👤 *Nombre:* {nombre}\n"
    f"📞 *Teléfono:* `{telefono}`\n"
    f"🪪 *Telegram ID:* `{user.id}`\n"
    f"💬 *Chat ID:* `{chat_id}`\n"
    f"🌐 *Usuario:* @{user.username if user.username else 'Sin username'}\n\n"
    "¿Deseas iniciar registro de este móvil ahora?"
)

# Botón para administrador
button = InlineKeyboardMarkup(
    [
        [
            InlineKeyboardButton(
                "📝 Iniciar registro", callback_data=f"REG_MOBIL|{telefono}"
            )
        ]
    ]
)

# Aviso a administradores
for admin_id in ADMIN_IDS:
    try:
            # Aviso al móvil
        await update.message.reply_text(
            "Perfecto 👌 Tu solicitud fue enviada al administrador.\n\n"
            "Cuando te registren podrás activar jornada.",
            parse_mode="Markdown",
        )

        # Botón para el administrador
        button = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "📝 Iniciar registro", callback_data=f"REG_MOBIL|{telefono}"
                    )
                ]
            ]
        )

        # Aviso a administradores
        for admin_id in ADMIN_IDS:
            try:
                await context.bot.send_message(
                    chat_id=admin_id,
                    text=aviso,
                    parse_mode="Markdown",
                    reply_markup=button
                )
            except:
                pass

        context.user_data["soy_estado"] = None
        return True


        # Intentamos vincular con un móvil ya creado por teléfono
        for code, m in mobiles.items():
            if m.get("telefono") == telefono:
                m["telegram_id"] = user.id
                m["chat_id"] = chat_id
                save_mobiles(mobiles)

                # Borramos cualquier solicitud pendiente con ese teléfono
                pending = load_pending_mobiles()
                if telefono in pending:
                    pending.pop(telefono, None)
                    save_pending_mobiles(pending)

                await update.message.reply_text(
                    f"✅ Ya estabas registrado.\n"
                    f"Quedaste vinculado como móvil *{code}*.",
                    parse_mode="Markdown",
                )

                aviso = (
                    f"✅ El conductor {nombre} ({telefono}) se vinculó automáticamente al móvil {code} "
                    f"usando /soy_movil.\n"
                    f"Telegram ID: `{user.id}`\nChat ID: `{chat_id}`"
                )
                for admin_id in ADMIN_IDS:
                    try:
                        await context.bot.send_message(
                            chat_id=admin_id, text=aviso, parse_mode="Markdown"
                        )
                    except Exception as e:
                        logger.error(f"No se pudo avisar a admin {admin_id}: {e}")
                return True

        # Si no hay móvil con ese teléfono, creamos solicitud pendiente
        pending = load_pending_mobiles()
        pending[telefono] = {
            "nombre": nombre,
            "telefono": telefono,
            "telegram_id": user.id,
            "chat_id": chat_id,
            "username": user.username,
            "fecha": today_str_colombia(),
        }
        save_pending_mobiles(pending)

        await update.message.reply_text(
            "✅ Tu solicitud de registro como móvil fue enviada al administrador.\n\n"
            "Cuando te registren, el sistema te vinculará automáticamente.",
        )

        aviso = (
            f"📥 Nueva solicitud /soy_movil\n\n"
            f"Nombre: *{nombre}*\n"
            f"Teléfono: `{telefono}`\n"
            f"Fecha: {today_str_colombia()}\n"
            f"Telegram ID: `{user.id}`\n"
            f"Chat ID: `{chat_id}`\n"
            f"Usuario: @{user.username if user.username else 'N/A'}"
        )
        for admin_id in ADMIN_IDS:
            try:
                await context.bot.send_message(
                    chat_id=admin_id, text=aviso, parse_mode="Markdown"
                )
            except Exception as e:
                logger.error(f"No se pudo avisar a admin {admin_id}: {e}")

        return True
           except:
             return False

# ---------------------------
# MANEJO DE TEXTO GENERAL
# ---------------------------

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    user = update.effective_user
    chat_id = update.effective_chat.id

    # Primero, si estamos en flujo /soy_movil, lo atendemos
    soy_movil_estado = context.user_data.get("soy_movil_estado")
    if soy_movil_estado:
        handled = await procesar_soy_movil(update, context, text)
        if handled:
            return

    rol = context.user_data.get("rol")
    estado = context.user_data.get("estado")

    # -----------------------
    # MENÚ PRINCIPAL
    # -----------------------
    if text == "🏠 Menú principal":
        context.user_data.clear()
        await update.message.reply_text(
            "Volvemos al menú principal, elige una opción:",
            reply_markup=main_keyboard,
        )
        return

    if text == "Usuario":
        context.user_data.clear()
        context.user_data["rol"] = "usuario"
        await update.message.reply_text(
            "Eres *Usuario* 🧑‍💼\n\nElige el servicio que necesitas:",
            reply_markup=user_keyboard,
            parse_mode="Markdown",
        )
        return

    if text == "Móvil":
        context.user_data.clear()
        context.user_data["rol"] = "movil"
        context.user_data["estado"] = "movil_esperando_codigo"
        await update.message.reply_text(
            "Eres *Móvil* 🚗\n\nEscribe tu *código de móvil* (ej: T001, D002, C003, E004):",
            parse_mode="Markdown",
        )
        return

    if text == "Administrador":
        if user.id not in ADMIN_IDS:
            await update.message.reply_text("No tienes permisos de administrador.")
            return
        context.user_data.clear()
        context.user_data["rol"] = "admin"
        await update.message.reply_text(
            "Bienvenido al menú de *Administrador* 🛠️",
            reply_markup=admin_keyboard,
            parse_mode="Markdown",
        )
        return

    # -----------------------
    # ROL: MÓVIL
    # -----------------------
    if rol == "movil":
        mobiles = load_mobiles()

        # Paso de login por código
        if estado == "movil_esperando_codigo":
            code = text.upper()
            mobile = mobiles.get(code)
            if not mobile:
                await update.message.reply_text(
                    "❌ Código de móvil no encontrado. Verifica con el administrador."
                )
                return

            mobile["chat_id"] = chat_id
            mobile["telegram_id"] = user.id
            mobile.setdefault("activo", True)
            mobile.setdefault("en_jornada", False)
            save_mobiles(mobiles)

            context.user_data["estado"] = "movil_logueado"
            context.user_data["codigo_movil"] = code

            await update.message.reply_text(
                f"✅ Te has identificado como móvil *{code}* ({mobile.get('nombre')}).\n\n"
                f"Servicio: *{mobile_service_name(mobile.get('servicio', ''))}*",
                reply_markup=movil_keyboard,
                parse_mode="Markdown",
            )
            return

        code = context.user_data.get("codigo_movil")
        if not code:
            await update.message.reply_text(
                "Debes iniciar sesión como móvil primero. Toca *Móvil* en el menú principal.",
                parse_mode="Markdown",
            )
            return

        mobile = mobiles.get(code)
        if not mobile:
            await update.message.reply_text(
                "No encuentro tu móvil en el sistema. Consulta con el administrador."
            )
            return

        if text == "🟢 Iniciar jornada":
            puede, msg = mobile_can_work(mobile)
            if not puede:
                await update.message.reply_text("⛔ No puedes iniciar jornada:\n\n" + msg)
                return

            mobile["en_jornada"] = True
            save_mobiles(mobiles)
            await update.message.reply_text(
                "✅ Jornada iniciada.\n\n"
                "Por favor comparte tu ubicación usando el botón *📍 Compartir ubicación* "
                "para que podamos asignarte servicios cercanos.",
                reply_markup=movil_keyboard,
                parse_mode="Markdown",
            )
            return

        if text == "🔴 Finalizar jornada":
            mobile["en_jornada"] = False
            save_mobiles(mobiles)
            await update.message.reply_text("✅ Has finalizado tu jornada.")
            return

        if text == "💰 Enviar pago":
            today = today_str_colombia()
            mobile["pago_pendiente"] = True
            mobile["pago_pendiente_fecha"] = today
            save_mobiles(mobiles)

            await update.message.reply_text(
                "💰 *Pago del día*\n\n"
                f"Realiza el pago del corte de hoy al Nequi:\n\n"
                f"*{NEQUI_NUMBER}*\n\n"
                "Después de pagar, envía el comprobante al administrador.\n"
                "Cuando lo aprueben, podrás trabajar después de las 3:00 p.m.",
                parse_mode="Markdown",
            )

            aviso = (
                f"📢 El móvil {code} ({mobile.get('nombre')}, {mobile.get('telefono')}) "
                f"reporta pago del día {today}.\n\n"
                f"Usa /aprobar_pago {code} para aprobar."
            )
            for admin_id in ADMIN_IDS:
                try:
                    await context.bot.send_message(chat_id=admin_id, text=aviso)
                except Exception as e:
                    logger.error(f"No se pudo avisar a admin {admin_id}: {e}")
            return

        if text == "📋 Ver estado pago":
            today = today_str_colombia()
            ultimo_pago = mobile.get("ultimo_pago_fecha")
            pago_pendiente = mobile.get("pago_pendiente", False)

            if ultimo_pago == today:
                msg = "✅ Tu pago de hoy ya está aprobado."
            elif pago_pendiente and mobile.get("pago_pendiente_fecha") == today:
                msg = "⏳ Tu pago de hoy está pendiente de aprobación."
            else:
                msg = "❌ No hay pago aprobado para hoy."

            await update.message.reply_text(msg)
            return

        await update.message.reply_text(
            "No entiendo ese mensaje en modo *Móvil*. Usa los botones del menú, por favor.",
            parse_mode="Markdown",
        )
        return

    # -----------------------
    # ROL: USUARIO (CLIENTE)
    # -----------------------
    if rol == "usuario":
        # Inicio de flujos
        if text == "🚕 Pedir taxi":
            context.user_data["estado"] = "usuario_solicitando_nombre"
            context.user_data["servicio_solicitado"] = "taxi"
            await update.message.reply_text(
                "Perfecto, vamos a pedir un *Taxi* 🚕\n\n¿Cuál es tu nombre?",
                parse_mode="Markdown",
            )
            return

        if text == "📦 Pedir domicilio":
            context.user_data["estado"] = "usuario_solicitando_nombre"
            context.user_data["servicio_solicitado"] = "domicilios"
            await update.message.reply_text(
                "Listo, *Domicilio* 📦\n\n¿Cuál es tu nombre?",
                parse_mode="Markdown",
            )
            return

        if text == "🚚 Pedir camioneta":
            context.user_data["estado"] = "usuario_solicitando_nombre"
            context.user_data["servicio_solicitado"] = "camionetas"
            await update.message.reply_text(
                "Perfecto, *Camioneta* 🚚\n\n¿Cuál es tu nombre?",
                parse_mode="Markdown",
            )
            return

        if text == "♿ Transporte discapacitados":
            context.user_data["estado"] = "usuario_solicitando_nombre"
            context.user_data["servicio_solicitado"] = "discapacidad"
            await update.message.reply_text(
                "Listo, *Transporte discapacitados* ♿\n\n¿Cuál es tu nombre?",
                parse_mode="Markdown",
            )
            return

        if estado == "usuario_solicitando_nombre":
            context.user_data["cliente_nombre"] = text
            context.user_data["estado"] = "usuario_solicitando_telefono"
            await update.message.reply_text("¿Cuál es tu número de teléfono?")
            return

        if estado == "usuario_solicitando_telefono":
            context.user_data["cliente_telefono"] = text
            context.user_data["estado"] = "usuario_esperando_ubicacion"
            await update.message.reply_text(
                "Por favor comparte tu *ubicación actual* usando el botón de abajo.\n\n"
                "Si prefieres no compartirla, toca *Omitir ubicación* y escribe luego la dirección.",
                reply_markup=user_location_keyboard,
                parse_mode="Markdown",
            )
            return

        if estado == "usuario_esperando_ubicacion":
            # El usuario envió texto en vez de ubicación -> lo tomamos como dirección
            if text == "Omitir ubicación":
                context.user_data["cliente_lat"] = None
                context.user_data["cliente_lon"] = None
                context.user_data["estado"] = "usuario_solicitando_origen"
                await update.message.reply_text(
                    "Escribe la dirección desde donde te recogemos o recogemos el pedido:",
                    reply_markup=user_keyboard,
                )
                return
            else:
                # Tratamos el texto como dirección
                context.user_data["cliente_lat"] = None
                context.user_data["cliente_lon"] = None
                context.user_data["cliente_origen"] = text
                context.user_data["estado"] = "usuario_solicitando_detalles"
                await update.message.reply_text(
                    "¿Destino (si aplica) u observaciones adicionales?\n"
                    "(Ej: barrio de destino, piso, punto de referencia, etc.)",
                    reply_markup=user_keyboard,
                )
                return

        if estado == "usuario_solicitando_origen":
            context.user_data["cliente_origen"] = text
            context.user_data["estado"] = "usuario_solicitando_detalles"
            await update.message.reply_text(
                "¿Destino (si aplica) u observaciones adicionales?\n"
                "(Ej: barrio de destino, piso, punto de referencia, etc.)",
                reply_markup=user_keyboard,
            )
            return

        if estado == "usuario_solicitando_detalles":
            servicio = context.user_data.get("servicio_solicitado")
            nombre = context.user_data.get("cliente_nombre")
            telefono = context.user_data.get("cliente_telefono")
            origen = context.user_data.get("cliente_origen")
            detalles = text
            cliente_lat = context.user_data.get("cliente_lat")
            cliente_lon = context.user_data.get("cliente_lon")

            prefix = service_prefix(servicio)
            service_id = f"{prefix}-{random.randint(1000, 9999)}"

            channel_id = get_channel_for_service(servicio)
            if not channel_id:
                await update.message.reply_text(
                    "Lo siento, hubo un problema con el tipo de servicio. Intenta de nuevo."
                )
                context.user_data["estado"] = None
                return

            SERVICES[service_id] = {
                "service_id": service_id,
                "tipo": servicio,
                "cliente_id": user.id,
                "cliente_chat_id": chat_id,
                "cliente_nombre": nombre,
                "cliente_telefono": telefono,
                "cliente_lat": cliente_lat,
                "cliente_lon": cliente_lon,
                "origen": origen,
                "detalles": detalles,
                "estado": "pendiente",
                "movil_codigo": None,
                "movil_nombre": None,
                "movil_telefono": None,
                "movil_chat_id": None,
                "channel_id": channel_id,
                "channel_message_id": None,
            }

            await update.message.reply_text(
                f"✅ Tu solicitud fue registrada.\n\n"
                f"ID del servicio: *{service_id}*\n"
                "Buscando el móvil más cercano disponible...",
                parse_mode="Markdown",
            )

            context.user_data["estado"] = None

            # Asignamos al móvil más cercano o hacemos fallback al canal
            await asignar_servicio(service_id, context)
            return

        # Cualquier otro texto en modo usuario
        await update.message.reply_text(
            "No entendí tu mensaje en modo *Usuario*. Usa los botones del menú para pedir un servicio.",
            parse_mode="Markdown",
        )
        return

    # -----------------------
    # ROL: ADMINISTRADOR
    # -----------------------
    if rol == "admin":
        mobiles = load_mobiles()

        if text == "➕ Registrar móvil":
            context.user_data["estado"] = "admin_reg_codigo"
            await update.message.reply_text(
                "Vamos a registrar un nuevo móvil.\n\n"
                "Escribe el *código* del móvil (ej: T001, D001, C001, E001):",
                parse_mode="Markdown",
            )
            return

        if text == "📃 Ver móviles":
            if not mobiles:
                await update.message.reply_text("No hay móviles registrados todavía.")
                return
            lines = ["📃 *Listado de móviles registrados:*", ""]
            for code, m in mobiles.items():
                lines.append(
                    f"• *{code}* - {m.get('nombre')} - {mobile_service_name(m.get('servicio', ''))}\n"
                    f"  Tel: {m.get('telefono')} | Cédula: {m.get('cedula', 'N/A')} | "
                    f"Placa: {m.get('placa', 'N/A')}\n"
                    f"  Activo: {m.get('activo', True)} | Último pago: {m.get('ultimo_pago_fecha', 'N/A')}"
                )
            await update.message.reply_text("\n".join(lines), parse_mode="Markdown")
            return

        if text == "✅ Aprobar pago":
            context.user_data["estado"] = "admin_aprobar_pago"
            await update.message.reply_text(
                "Escribe el *código* del móvil al que deseas aprobar el pago (ej: T001):",
                parse_mode="Markdown",
            )
            return

        if text == "🔁 Cambiar estado móvil":
            context.user_data["estado"] = "admin_cambiar_estado"
            await update.message.reply_text(
                "Escribe el *código* del móvil que deseas activar/desactivar:",
                parse_mode="Markdown",
            )
            return

        # Flujo registro móvil
        estado = context.user_data.get("estado")

        if estado == "admin_reg_codigo":
            context.user_data["nuevo_movil_codigo"] = text.upper()
            context.user_data["estado"] = "admin_reg_nombre"
            await update.message.reply_text("Escribe el *nombre* del conductor:", parse_mode="Markdown")
            return

        if estado == "admin_reg_nombre":
            context.user_data["nuevo_movil_nombre"] = text
            context.user_data["estado"] = "admin_reg_telefono"
            await update.message.reply_text("Escribe el *teléfono* del conductor:", parse_mode="Markdown")
            return

        if estado == "admin_reg_telefono":
            context.user_data["nuevo_movil_telefono"] = text.strip()
            context.user_data["estado"] = "admin_reg_cedula"
            await update.message.reply_text("Escribe la *cédula* del conductor:", parse_mode="Markdown")
            return

        if estado == "admin_reg_cedula":
            context.user_data["nuevo_movil_cedula"] = text.strip()
            context.user_data["estado"] = "admin_reg_placa"
            await update.message.reply_text("Escribe la *placa* del vehículo:", parse_mode="Markdown")
            return

        if estado == "admin_reg_placa":
            context.user_data["nuevo_movil_placa"] = text.strip()
            context.user_data["estado"] = "admin_reg_marca"
            await update.message.reply_text("Escribe la *marca* del vehículo:", parse_mode="Markdown")
            return

        if estado == "admin_reg_marca":
            context.user_data["nuevo_movil_marca"] = text.strip()
            context.user_data["estado"] = "admin_reg_modelo"
            await update.message.reply_text("Escribe el *modelo* del vehículo:", parse_mode="Markdown")
            return

        if estado == "admin_reg_modelo":
            context.user_data["nuevo_movil_modelo"] = text.strip()
            context.user_data["estado"] = "admin_reg_servicio"
            await update.message.reply_text(
                "Escribe el tipo de servicio del móvil (opciones):\n"
                "- taxi\n- domicilios\n- camionetas\n- discapacidad",
            )
            return

        if estado == "admin_reg_servicio":
            servicio = text.strip().lower()
            if servicio not in ["taxi", "domicilios", "camionetas", "discapacidad"]:
                await update.message.reply_text(
                    "Tipo de servicio no válido. Escribe: taxi / domicilios / camionetas / discapacidad"
                )
                return

            code = context.user_data.get("nuevo_movil_codigo").upper()
            nombre = context.user_data.get("nuevo_movil_nombre")
            telefono = context.user_data.get("nuevo_movil_telefono")
            cedula = context.user_data.get("nuevo_movil_cedula")
            placa = context.user_data.get("nuevo_movil_placa")
            marca = context.user_data.get("nuevo_movil_marca")
            modelo = context.user_data.get("nuevo_movil_modelo")

            mobiles[code] = {
                "codigo": code,
                "nombre": nombre,
                "telefono": telefono,
                "cedula": cedula,
                "placa": placa,
                "marca": marca,
                "modelo": modelo,
                "servicio": servicio,
                "activo": True,
                "en_jornada": False,
                "ultimo_pago_fecha": None,
                "pago_pendiente": False,
                "pago_pendiente_fecha": None,
                "chat_id": None,
                "telegram_id": None,
                "ubicacion": None,
            }

            # Intentamos vincular con una solicitud /soy_movil por teléfono
            pending = load_pending_mobiles()
            info_pendiente = pending.pop(telefono, None)
            if info_pendiente:
                mobiles[code]["telegram_id"] = info_pendiente.get("telegram_id")
                mobiles[code]["chat_id"] = info_pendiente.get("chat_id")
                save_pending_mobiles(pending)

            save_mobiles(mobiles)
            context.user_data["estado"] = None

            await update.message.reply_text(
                f"✅ Móvil registrado:\n\n"
                f"Código: *{code}*\n"
                f"Nombre: *{nombre}*\n"
                f"Teléfono: `{telefono}`\n"
                f"Cédula: `{cedula}`\n"
                f"Placa: `{placa}`\n"
                f"Marca/Modelo: {marca} {modelo}\n"
                f"Servicio: *{mobile_service_name(servicio)}*",
                parse_mode="Markdown",
            )

            # Avisar al móvil si ya teníamos chat_id vinculado
            chat_id_movil = mobiles[code].get("chat_id")
            if chat_id_movil:
                try:
                    await context.bot.send_message(
                        chat_id=chat_id_movil,
                        text=(
                            f"✅ Fuiste registrado como móvil *{code}*.\n"
                            "Ya puedes iniciar jornada desde el menú *Móvil*."
                        ),
                        parse_mode="Markdown",
                    )
                except Exception as e:
                    logger.error(f"No se pudo avisar al móvil {code}: {e}")
            return

        if estado == "admin_aprobar_pago":
            code = text.upper()
            mobile = mobiles.get(code)
            if not mobile:
                await update.message.reply_text("❌ No encuentro ese código de móvil.")
                return

            today = today_str_colombia()
            mobile["ultimo_pago_fecha"] = today
            mobile["pago_pendiente"] = False
            mobile["pago_pendiente_fecha"] = today
            save_mobiles(mobiles)
            context.user_data["estado"] = None

            await update.message.reply_text(
                f"✅ Pago aprobado para el móvil *{code}* (día {today}).",
                parse_mode="Markdown",
            )

            chat_id_movil = mobile.get("chat_id")
            if chat_id_movil:
                try:
                    await context.bot.send_message(
                        chat_id=chat_id_movil,
                        text="✅ Tu pago del día ha sido aprobado. "
                             "Puedes trabajar después de las 3:00 p.m.",
                    )
                except Exception as e:
                    logger.error(f"No se pudo avisar al móvil {code}: {e}")
            return

        if estado == "admin_cambiar_estado":
            code = text.upper()
            mobile = mobiles.get(code)
            if not mobile:
                await update.message.reply_text("❌ No encuentro ese código de móvil.")
                return

            current = mobile.get("activo", True)
            mobile["activo"] = not current
            save_mobiles(mobiles)
            context.user_data["estado"] = None

            estado_texto = "ACTIVO" if mobile["activo"] else "INACTIVO"
            await update.message.reply_text(
                f"El móvil *{code}* ahora está: *{estado_texto}*",
                parse_mode="Markdown",
            )
            return

        await update.message.reply_text(
            "No entendí ese mensaje en modo *Administrador*. Usa los botones del menú.",
            parse_mode="Markdown",
        )
        return

    # -----------------------
    # SIN ROL DEFINIDO
    # -----------------------
    await update.message.reply_text(
        "No entendí tu mensaje.\n\nUsa /start para ver el menú principal."
    )


# ---------------------------
# MANEJO DE UBICACIÓN
# ---------------------------

async def handle_location(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat_id = update.effective_chat.id
    rol = context.user_data.get("rol")
    estado = context.user_data.get("estado")

    loc = update.message.location
    lat = loc.latitude
    lon = loc.longitude

    # Ubicación de MÓVIL
    if rol == "movil":
        code, mobile = find_mobile_by_telegram_id(user.id)
        if not mobile:
            await update.message.reply_text(
                "No encuentro tu registro de móvil. Vuelve a entrar por el menú *Móvil*.",
                parse_mode="Markdown",
            )
            return

        mobiles = load_mobiles()
        mobiles[code]["ubicacion"] = {
            "lat": lat,
            "lon": lon,
            "fecha": today_str_colombia(),
            "timestamp": get_colombia_now().isoformat(),
        }
        save_mobiles(mobiles)

        texto = (
            f"📍 Ubicación de móvil {code} ({mobile.get('nombre')}):\n\n"
            f"Lat: {lat}\nLon: {lon}"
        )
        for admin_id in ADMIN_IDS:
            try:
                await context.bot.send_message(chat_id=admin_id, text=texto)
            except Exception as e:
                logger.error(f"No se pudo enviar ubicación a admin {admin_id}: {e}")

        await update.message.reply_text("✅ Ubicación registrada. Gracias.")
        return

    # Ubicación de USUARIO (cliente pidiendo servicio)
    if rol == "usuario" and estado == "usuario_esperando_ubicacion":
        context.user_data["cliente_lat"] = lat
        context.user_data["cliente_lon"] = lon
        context.user_data["estado"] = "usuario_solicitando_origen"

        await update.message.reply_text(
            "✅ Ubicación recibida.\n\n"
            "Ahora escribe la dirección o referencia desde donde te recogemos o recogemos el pedido:",
            reply_markup=user_keyboard,
        )
        return

    # Si llega ubicación fuera de esos contextos, la ignoramos
    await update.message.reply_text(
        "Ubicación recibida, pero en este momento no la necesito para ningún proceso."
    )


# ---------------------------
# ASIGNACIÓN DE SERVICIO
# ---------------------------

async def asignar_servicio(service_id: str, context: ContextTypes.DEFAULT_TYPE):
    """
    Intenta asignar el servicio al móvil más cercano según ubicación.
    Si no hay móviles candidatos, se publica el servicio en el canal para que lo tomen.
    """
    service = SERVICES.get(service_id)
    if not service:
        return

    channel_id = service["channel_id"]
    cliente_lat = service.get("cliente_lat")
    cliente_lon = service.get("cliente_lon")

    # Mensaje base al canal
    texto_canal_base = (
        f"📢 *Nuevo servicio* [{service_id}]\n\n"
        f"Servicio: *{mobile_service_name(service['tipo'])}*\n"
        f"Cliente: *{service['cliente_nombre']}*\n"
        f"Teléfono: `{service['cliente_telefono']}`\n"
        f"Origen / Dirección: {service['origen']}\n"
        f"Destino / Observaciones: {service['detalles']}\n"
    )
    if cliente_lat is not None and cliente_lon is not None:
        texto_canal_base += f"\n📍 Ubicación compartida por el cliente."

    # Enviamos primero al canal como registro
    try:
        msg = await context.bot.send_message(
            chat_id=channel_id,
            text=texto_canal_base + "\n\nBuscando el móvil más cercano...",
            parse_mode="Markdown",
        )
        service["channel_message_id"] = msg.message_id
    except Exception as e:
        logger.error(f"Error enviando servicio {service_id} al canal: {e}")
        service["channel_message_id"] = None

    mobiles = load_mobiles()

    candidatos = []
    if cliente_lat is not None and cliente_lon is not None:
        # Solo buscamos cercanía si el cliente compartió ubicación
        for code, m in mobiles.items():
            if m.get("servicio") != service["tipo"]:
                continue
            if not m.get("en_jornada"):
                continue
            puede, _ = mobile_can_work(m)
            if not puede:
                continue
            ubic = m.get("ubicacion")
            if not ubic:
                continue
            lat = ubic.get("lat")
            lon = ubic.get("lon")
            if lat is None or lon is None:
                continue
            dist = haversine_km(cliente_lat, cliente_lon, lat, lon)
            candidatos.append((dist, code, m))

    # Si hay candidato(s) -> asignamos al más cercano
    if candidatos:
        candidatos.sort(key=lambda x: x[0])
        dist_km, code, mobile = candidatos[0]
        chat_id_movil = mobile.get("chat_id")

        if not chat_id_movil:
            logger.warning(f"Móvil {code} no tiene chat_id, no se puede enviar directo.")
        else:
            service["estado"] = "asignado"
            service["movil_codigo"] = code
            service["movil_nombre"] = mobile.get("nombre")
            service["movil_telefono"] = mobile.get("telefono")
            service["movil_chat_id"] = chat_id_movil

            # Aviso al móvil
            texto_movil = (
                f"✅ Te fue asignado un servicio [{service_id}] por cercanía.\n\n"
                f"Servicio: *{mobile_service_name(service['tipo'])}*\n"
                f"Cliente: *{service['cliente_nombre']}*\n"
                f"Teléfono cliente: `{service['cliente_telefono']}`\n"
                f"Origen / Dirección: {service['origen']}\n"
                f"Destino / Observaciones: {service['detalles']}\n"
            )
            if cliente_lat is not None and cliente_lon is not None:
                texto_movil += "\n📍 El cliente compartió ubicación (puedes verla en el mapa)."

            try:
                await context.bot.send_message(
                    chat_id=chat_id_movil,
                    text=texto_movil,
                    parse_mode="Markdown",
                    reply_markup=InlineKeyboardMarkup(
                        [
                            [
                                InlineKeyboardButton(
                                    "⚠️ Cancelar servicio", callback_data=f"CANCELAR_M|{service_id}"
                                )
                            ]
                        ]
                    ),
                )
            except Exception as e:
                logger.error(f"No se pudo enviar servicio al móvil {code}: {e}")

            # Aviso al cliente
            try:
                await context.bot.send_message(
                    chat_id=service["cliente_chat_id"],
                    text=(
                        f"✅ Tu servicio [{service_id}] fue asignado al móvil *{service['movil_nombre']}* "
                        f"({service['movil_codigo']}).\n\n"
                        f"Teléfono del móvil: `{service['movil_telefono']}`"
                    ),
                    parse_mode="Markdown",
                    reply_markup=InlineKeyboardMarkup(
                        [
                            [
                                InlineKeyboardButton(
                                    "⚠️ Cancelar servicio", callback_data=f"CANCELAR_C|{service_id}"
                                )
                            ]
                        ]
                    ),
                )
            except Exception as e:
                logger.error(f"No se pudo avisar al cliente para servicio {service_id}: {e}")

            # Editar mensaje en el canal
            if service["channel_message_id"]:
                texto_canal = (
                    f"📢 *Servicio asignado automáticamente por cercanía* [{service_id}]\n\n"
                    f"Servicio: *{mobile_service_name(service['tipo'])}*\n"
                    f"Cliente: *{service['cliente_nombre']}*\n"
                    f"Teléfono: `{service['cliente_telefono']}`\n"
                    f"Origen / Dirección: {service['origen']}\n"
                    f"Destino / Observaciones: {service['detalles']}\n\n"
                    f"✅ Asignado a: *{service['movil_nombre']}* ({service['movil_codigo']})\n"
                    f"Tel móvil: `{service['movil_telefono']}`\n"
                    f"Distancia aproximada: {dist_km:.1f} km"
                )
                try:
                    await context.bot.edit_message_text(
                        chat_id=channel_id,
                        message_id=service["channel_message_id"],
                        text=texto_canal,
                        parse_mode="Markdown",
                    )
                except Exception as e:
                    logger.error(f"No se pudo editar mensaje del canal para servicio {service_id}: {e}")
            return

    # Si no hay candidatos (o no se pudo enviar directo) -> fallback al canal
    service["estado"] = "pendiente"
    try:
        if service["channel_message_id"]:
            await context.bot.edit_message_text(
                chat_id=channel_id,
                message_id=service["channel_message_id"],
                text=texto_canal_base + "\n\n"
                     "No se encontró un móvil cercano activo.\n"
                     "Cualquier móvil disponible puede *tomar el servicio*.",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup(
                    [
                        [
                            InlineKeyboardButton(
                                "✅ Tomar servicio", callback_data=f"TOMAR|{service_id}"
                            )
                        ]
                    ]
                ),
            )
    except Exception as e:
        logger.error(f"No se pudo actualizar mensaje del canal en fallback para {service_id}: {e}")


# ---------------------------
# CALLBACKS (BOTONES INLINE)
# ---------------------------

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data = query.data.split("|")
    action = data[0]
    service_id = data[1] if len(data) > 1 else None

    if not service_id:
        return
if action == "REG_MOBIL":
    await handle_iniciar_registro(query, context, service_id)
    return

    if action == "TOMAR":
        await handle_tomar_servicio(query, context, service_id)
    elif action == "CANCELAR_M":
        await handle_cancelar_servicio_movil(query, context, service_id)
    elif action == "CANCELAR_C":
        await handle_cancelar_servicio_cliente(query, context, service_id)


async def handle_tomar_servicio(query, context, service_id: str):
    """Toma servicio desde el canal (fallback)."""
    user = query.from_user
    codigo_movil, mobile = find_mobile_by_telegram_id(user.id)
    if not mobile:
        try:
            await context.bot.send_message(
                chat_id=user.id,
                text=(
                    "Para tomar servicios debes iniciar sesión como *Móvil* en el bot PRONTO.\n\n"
                    "Entra al bot, toca *Móvil* y escribe tu código (ej: T001)."
                ),
                parse_mode="Markdown",
            )
        except Exception:
            pass
        return

    service = SERVICES.get(service_id)
    if not service:
        await query.edit_message_text("Este servicio ya no está disponible.")
        return

    if service.get("estado") != "pendiente":
        await query.edit_message_text("Este servicio ya fue tomado por otro móvil.")
        return

    # Verificar tipo de servicio
    if mobile.get("servicio") != service.get("tipo"):
        await context.bot.send_message(
            chat_id=user.id,
            text=(
                "Este servicio no corresponde a tu tipo de servicio.\n\n"
                f"Tu tipo: {mobile_service_name(mobile.get('servicio'))}"
            ),
        )
        return

    # Verificar corte y pago
    puede, msg = mobile_can_work(mobile)
    if not puede:
        await context.bot.send_message(
            chat_id=user.id,
            text="⛔ No puedes tomar este servicio:\n\n" + msg,
        )
        return

    # Asignar
    service["estado"] = "asignado"
    service["movil_codigo"] = codigo_movil
    service["movil_nombre"] = mobile.get("nombre")
    service["movil_telefono"] = mobile.get("telefono")
    service["movil_chat_id"] = mobile.get("chat_id") or user.id

    channel_id = service["channel_id"]
    channel_msg_id = service.get("channel_message_id")

    texto_canal = (
        f"📢 *Servicio asignado* [{service_id}]\n\n"
        f"Servicio: *{mobile_service_name(service['tipo'])}*\n"
        f"Cliente: *{service['cliente_nombre']}*\n"
        f"Teléfono: `{service['cliente_telefono']}`\n"
        f"Origen / Dirección: {service['origen']}\n"
        f"Destino / Observaciones: {service['detalles']}\n\n"
        f"✅ Asignado a: *{service['movil_nombre']}* ({service['movil_codigo']})\n"
        f"Tel móvil: `{service['movil_telefono']}`"
    )
    if channel_msg_id:
        try:
            await context.bot.edit_message_text(
                chat_id=channel_id,
                message_id=channel_msg_id,
                text=texto_canal,
                parse_mode="Markdown",
            )
        except Exception as e:
            logger.error(f"No se pudo editar mensaje del canal en TOMAR: {e}")

    # Avisar al móvil
    texto_movil = (
        f"✅ Has tomado el servicio [{service_id}]\n\n"
        f"Cliente: *{service['cliente_nombre']}*\n"
        f"Teléfono: `{service['cliente_telefono']}`\n"
        f"Origen / Dirección: {service['origen']}\n"
        f"Destino / Observaciones: {service['detalles']}\n"
    )
    try:
        await context.bot.send_message(
            chat_id=service["movil_chat_id"],
            text=texto_movil,
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            "⚠️ Cancelar servicio", callback_data=f"CANCELAR_M|{service_id}"
                        )
                    ]
                ]
            ),
        )
    except Exception as e:
        logger.error(f"No se pudo enviar mensaje al móvil en TOMAR: {e}")

    # Avisar al cliente
    try:
        await context.bot.send_message(
            chat_id=service["cliente_chat_id"],
            text=(
                f"✅ Tu servicio [{service_id}] fue tomado.\n\n"
                f"Móvil asignado: *{service['movil_nombre']}* ({service['movil_codigo']})\n"
                f"Teléfono del móvil: `{service['movil_telefono']}`"
            ),
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            "⚠️ Cancelar servicio", callback_data=f"CANCELAR_C|{service_id}"
                        )
                    ]
                ]
            ),
        )
    except Exception as e:
        logger.error(f"No se pudo avisar al cliente en TOMAR: {e}")


async def handle_cancelar_servicio_movil(query, context, service_id: str):
    """Cancelación hecha por el móvil."""
    user = query.from_user
    codigo_movil, mobile = find_mobile_by_telegram_id(user.id)
    if not mobile:
        await context.bot.send_message(
            chat_id=user.id,
            text="Solo un móvil asignado al servicio puede cancelarlo.",
        )
        return

    service = SERVICES.get(service_id)
    if not service:
        await context.bot.send_message(
            chat_id=user.id,
            text="Este servicio ya no existe o el bot se reinició.",
        )
        return

    if service.get("movil_codigo") != codigo_movil:
        await context.bot.send_message(
            chat_id=user.id,
            text="No eres el móvil asignado a este servicio, no puedes cancelarlo.",
        )
        return

    # Volvemos el servicio a pendiente para que otro móvil lo tome
    service["estado"] = "pendiente"
    service["movil_codigo"] = None
    service["movil_nombre"] = None
    service["movil_telefono"] = None
    service["movil_chat_id"] = None

    channel_id = service["channel_id"]
    channel_msg_id = service.get("channel_message_id")

    texto_canal = (
        f"📢 *Servicio disponible nuevamente* [{service_id}]\n\n"
        f"Servicio: *{mobile_service_name(service['tipo'])}*\n"
        f"Cliente: *{service['cliente_nombre']}*\n"
        f"Teléfono: `{service['cliente_telefono']}`\n"
        f"Origen / Dirección: {service['origen']}\n"
        f"Destino / Observaciones: {service['detalles']}\n\n"
        "⚠️ El móvil anterior canceló el servicio.\n"
        "Cualquier móvil disponible puede tomarlo."
    )

    if channel_msg_id:
        try:
            await context.bot.edit_message_text(
                chat_id=channel_id,
                message_id=channel_msg_id,
                text=texto_canal,
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup(
                    [
                        [
                            InlineKeyboardButton(
                                "✅ Tomar servicio", callback_data=f"TOMAR|{service_id}"
                            )
                        ]
                    ]
                ),
            )
        except Exception as e:
            logger.error(f"No se pudo reactivar el servicio en el canal: {e}")

    # Avisar al móvil que canceló
    try:
        await context.bot.send_message(
            chat_id=user.id,
            text=f"Has cancelado el servicio [{service_id}].",
        )
    except Exception as e:
        logger.error(f"No se pudo avisar al móvil que canceló: {e}")

    # Avisar al cliente
    try:
        await context.bot.send_message(
            chat_id=service["cliente_chat_id"],
            text=(
                f"⚠️ El móvil que tenía tu servicio [{service_id}] lo canceló.\n"
                "Tu solicitud volvió a la lista para que otro móvil la tome."
            ),
        )
    except Exception as e:
        logger.error(f"No se pudo avisar al cliente sobre la cancelación del móvil: {e}")


async def handle_cancelar_servicio_cliente(query, context, service_id: str):
    """Cancelación hecha por el cliente."""
    user = query.from_user
    service = SERVICES.get(service_id)
    if not service:
        await context.bot.send_message(
            chat_id=user.id,
            text="Este servicio ya no existe o el bot se reinició.",
        )
        return

    if user.id != service.get("cliente_id"):
        await context.bot.send_message(
            chat_id=user.id,
            text="Solo el cliente que pidió el servicio puede cancelarlo.",
        )
        return

    estado = service.get("estado")
    service["estado"] = "cancelado_cliente"

    # Avisar al móvil, si había uno asignado
    if service.get("movil_chat_id"):
        try:
            await context.bot.send_message(
                chat_id=service["movil_chat_id"],
                text=(
                    f"⚠️ El cliente canceló el servicio [{service_id}].\n"
                    "Ya no debes atender esta solicitud."
                ),
            )
        except Exception as e:
            logger.error(f"No se pudo avisar al móvil en cancelación del cliente: {e}")

    # Avisar a los administradores
    aviso = (
        f"⚠️ El cliente canceló el servicio [{service_id}].\n\n"
        f"Cliente: {service['cliente_nombre']} ({service['cliente_telefono']})\n"
        f"Estado anterior: {estado}\n"
        f"Servicio: {mobile_service_name(service['tipo'])}"
    )
    for admin_id in ADMIN_IDS:
        try:
            await context.bot.send_message(chat_id=admin_id, text=aviso)
        except Exception as e:
            logger.error(f"No se pudo avisar a admin en cancelación del cliente: {e}")

    # Avisar al cliente
    try:
        await context.bot.send_message(
            chat_id=service["cliente_chat_id"],
            text=f"✅ Has cancelado tu servicio [{service_id}].",
        )
    except Exception as e:
        logger.error(f"No se pudo confirmar al cliente su cancelación: {e}")

    # Actualizar mensaje en el canal (solo como registro)
    channel_id = service["channel_id"]
    channel_msg_id = service.get("channel_message_id")
    if channel_msg_id:
        texto_canal = (
            f"📢 *Servicio cancelado por el cliente* [{service_id}]\n\n"
            f"Servicio: *{mobile_service_name(service['tipo'])}*\n"
            f"Cliente: *{service['cliente_nombre']}*\n"
            f"Teléfono: `{service['cliente_telefono']}`\n"
            f"Origen / Dirección: {service['origen']}\n"
            f"Destino / Observaciones: {service['detalles']}\n"
        )
        try:
            await context.bot.edit_message_text(
                chat_id=channel_id,
                message_id=channel_msg_id,
                text=texto_canal,
                parse_mode="Markdown",
            )
        except Exception as e:
            logger.error(f"No se pudo editar mensaje del canal en cancelación cliente: {e}")


# ---------------------------
# COMANDO /APROBAR_PAGO DIRECTO
# ---------------------------

async def aprobar_pago_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user.id not in ADMIN_IDS:
        await update.message.reply_text("No tienes permisos para usar este comando.")
        return

    if not context.args:
        await update.message.reply_text("Uso: /aprobar_pago CODIGO (ej: /aprobar_pago T001)")
        return

    code = context.args[0].upper()
    mobiles = load_mobiles()
    mobile = mobiles.get(code)
    if not mobile:
        await update.message.reply_text("❌ No encuentro ese código de móvil.")
        return

    today = today_str_colombia()
    mobile["ultimo_pago_fecha"] = today
    mobile["pago_pendiente"] = False
    mobile["pago_pendiente_fecha"] = today
    save_mobiles(mobiles)

    await update.message.reply_text(
        f"✅ Pago aprobado para el móvil *{code}* (día {today}).",
        parse_mode="Markdown",
    )

    chat_id_movil = mobile.get("chat_id")
    if chat_id_movil:
        try:
            await context.bot.send_message(
                chat_id=chat_id_movil,
                text="✅ Tu pago del día ha sido aprobado. Puedes trabajar después de las 3:00 p.m.",
            )
        except Exception as e:
            logger.error(f"No se pudo avisar al móvil {code}: {e}")


# ---------------------------
# MAIN
# ---------------------------
async def handle_iniciar_registro(query, context, telefono):
    # Buscamos info en pending
    pending = load_pending_mobiles()
    info = pending.get(telefono)

    if not info:
        await query.edit_message_text(
            "❌ No se encuentra la solicitud pendiente. El móvil debe enviar /soy_movil nuevamente."
        )
        return

    # Guardamos la info en user_data del admin
    context.user_data.clear()
    context.user_data["rol"] = "admin"
    context.user_data["estado"] = "admin_reg_codigo"
    context.user_data["nuevo_movil_telefono"] = telefono
    context.user_data["nuevo_movil_nombre"] = info.get("nombre")

    await query.edit_message_text(
        f"📝 Registro iniciado del móvil:\n\n"
        f"👤 Nombre: {info.get('nombre')}\n"
        f"📱 Teléfono: {telefono}\n\n"
        "Escribe el *código de móvil* (ejemplo: T005)",
        parse_mode="Markdown",
    )

def main():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("soy_movil", soy_movil_command))
    app.add_handler(CommandHandler("aprobar_pago", aprobar_pago_cmd))

    app.add_handler(CallbackQueryHandler(button_callback))

    app.add_handler(MessageHandler(filters.LOCATION, handle_location))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    app.run_polling()


if __name__ == "__main__":
    main()
