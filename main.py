# PRONTO 3.0 - Versión limpia y completa
# - python-telegram-bot v20+
# - Menú Usuario / Móvil / Administrador
# - 4 servicios: Taxi, Domicilios, Camionetas, Transporte discapacitados
# - Registro y control de móviles en mobiles.json
# - Corte a las 3:00 p.m. (hora Colombia, UTC-5)
# - Móviles ven info del cliente y el cliente ve info del móvil
# - Botón para tomar servicio y botón para cancelar servicio
# - Nequi mostrado en el flujo de pago del móvil

import logging
import json
import os
import random
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
TOKEN = "AQUI_TU_TOKEN"  # <<< PON AQUÍ TU TOKEN CORRECTO

# IDs de administradores (TU TELEGRAM ID + el de tu cliente)
ADMIN_IDS = [1741298723, 7076796229]

# Archivo de móviles
MOBILES_FILE = "mobiles.json"

# Número de NEQUI
NEQUI_NUMBER = "3000000000"  # <<< CAMBIA AL NEQUI REAL

# Canales (IDs confirmados, con -100...)
CHANNEL_TAXI = -1002697357566
CHANNEL_DOMICILIOS = -1002503403579
CHANNEL_CAMIONETAS = -1002662309590
CHANNEL_TRANSPORTE_DIS = -1002688723492

# Diccionario en memoria para servicios
SERVICES = {}  # service_id -> dict con datos del servicio

# ---------------------------
# LOGS
# ---------------------------
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


# ---------------------------
# UTILIDADES
# ---------------------------
def get_colombia_now() -> datetime:
    """Devuelve la hora actual de Colombia (UTC-5) basada en UTC."""
    # Railway normalmente trabaja en UTC, así que restamos 5 horas
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
    """Guarda el diccionario de móviles en JSON."""
    try:
        with open(MOBILES_FILE, "w", encoding="utf-8") as f:
            json.dump(mobiles, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"Error guardando {MOBILES_FILE}: {e}")


def find_mobile_by_telegram_id(telegram_id: int) -> tuple[str, dict] | tuple[None, None]:
    """Busca un móvil por telegram_id y lo devuelve (codigo, data)."""
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
    Verifica si el móvil puede trabajar según corte de las 3 pm y pagos.
    - Antes de las 3pm: puede trabajar siempre que esté activo.
    - Después de las 3pm: necesita último pago aprobado hoy.
    """
    if not mobile.get("activo", True):
        return False, "Tu móvil está desactivado por el administrador."

    now = get_colombia_now()
    hour = now.hour
    today = today_str_colombia()

    # Si es antes de las 3pm, puede trabajar
    if hour < 15:
        return True, "Puedes trabajar libremente antes de las 3:00 p.m."

    # Después de las 3pm, se exige pago de hoy
    ultimo_pago = mobile.get("ultimo_pago_fecha")
    if ultimo_pago == today:
        return True, "Tienes el pago de hoy aprobado. Puedes trabajar después de las 3:00 p.m."

    return False, (
        "Ya pasó el corte de las 3:00 p.m.\n\n"
        "Debes realizar el pago del día a Nequi y esperar aprobación del administrador "
        "para poder tomar servicios."
    )


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


# ---------------------------
# COMANDOS
# ---------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    context.user_data.clear()

    await update.message.reply_text(
        f"Hola {user.first_name}, soy *PRONTO 3.0* 🚀\n\n"
        "Elige una opción:",
        reply_markup=main_keyboard,
        parse_mode="Markdown",
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Soy el bot PRONTO.\n\n"
        "Usa /start para ver el menú principal."
    )


# ---------------------------
# FLUJO TEXTO (MENÚS Y ESTADOS)
# ---------------------------
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    user = update.effective_user
    chat_id = update.effective_chat.id

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
            "Eres *Móvil* 🚗\n\nPor favor escribe tu *código de móvil* (ej: T001, D002, C003, E004):",
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

    # A partir de aquí, según rol:
    # ===========================

    # -----------------------
    # ROL: MÓVIL
    # -----------------------
    if rol == "movil":
        mobiles = load_mobiles()

        # Paso 1: ingreso de código de móvil
        if estado == "movil_esperando_codigo":
            code = text.upper()
            mobile = mobiles.get(code)
            if not mobile:
                await update.message.reply_text(
                    "❌ Código de móvil no encontrado. Verifica con el administrador."
                )
                return

            # Guardamos info de sesión
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

        # Ya está logueado
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

        # Botones del menú móvil
        if text == "🟢 Iniciar jornada":
            puede, msg = mobile_can_work(mobile)
            if not puede:
                await update.message.reply_text("⛔ No puedes iniciar jornada:\n\n" + msg)
                return

            mobile["en_jornada"] = True
            save_mobiles(mobiles)
            await update.message.reply_text(
                "✅ Jornada iniciada.\n\n" + msg
            )
            return

        if text == "🔴 Finalizar jornada":
            mobile["en_jornada"] = False
            save_mobiles(mobiles)
            await update.message.reply_text("✅ Has finalizado tu jornada.")
            return

        if text == "💰 Enviar pago":
            # Marcamos pago pendiente y avisamos a los admins
            today = today_str_colombia()
            mobile["pago_pendiente"] = True
            mobile["pago_pendiente_fecha"] = today
            save_mobiles(mobiles)

            await update.message.reply_text(
                "💰 *Pago del día*\n\n"
                f"Por favor realiza el pago del corte de hoy al Nequi:\n\n"
                f"*{NEQUI_NUMBER}*\n\n"
                "Después de pagar, envía el comprobante al administrador.\n\n"
                "El administrador aprobará tu pago y podrás trabajar después de las 3:00 p.m.",
                parse_mode="Markdown",
            )

            # Avisar a los administradores
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
                msg = "⏳ Tu pago de hoy está pendiente de aprobación por el administrador."
            else:
                msg = "❌ No hay pago aprobado para hoy."

            await update.message.reply_text(msg)
            return

        # Cualquier otro mensaje en móvil
        await update.message.reply_text(
            "No entiendo ese mensaje en modo *Móvil*. Usa los botones del menú, por favor.",
            parse_mode="Markdown",
        )
        return

    # -----------------------
    # ROL: USUARIO (CLIENTE)
    # -----------------------
    if rol == "usuario":
        # Inicio de flujos de servicio
        if text == "🚕 Pedir taxi":
            context.user_data["estado"] = "usuario_solicitando_nombre"
            context.user_data["servicio_solicitado"] = "taxi"
            await update.message.reply_text("Perfecto, vamos a pedir un *Taxi* 🚕\n\n¿Cuál es tu nombre?")
            return

        if text == "📦 Pedir domicilio":
            context.user_data["estado"] = "usuario_solicitando_nombre"
            context.user_data["servicio_solicitado"] = "domicilios"
            await update.message.reply_text("Listo, *Domicilio* 📦\n\n¿Cuál es tu nombre?")
            return

        if text == "🚚 Pedir camioneta":
            context.user_data["estado"] = "usuario_solicitando_nombre"
            context.user_data["servicio_solicitado"] = "camionetas"
            await update.message.reply_text("Perfecto, *Camioneta* 🚚\n\n¿Cuál es tu nombre?")
            return

        if text == "♿ Transporte discapacitados":
            context.user_data["estado"] = "usuario_solicitando_nombre"
            context.user_data["servicio_solicitado"] = "discapacidad"
            await update.message.reply_text("Listo, *Transporte discapacitados* ♿\n\n¿Cuál es tu nombre?")
            return

        # Pasos del formulario
        if estado == "usuario_solicitando_nombre":
            context.user_data["cliente_nombre"] = text
            context.user_data["estado"] = "usuario_solicitando_telefono"
            await update.message.reply_text("¿Cuál es tu número de teléfono?")
            return

        if estado == "usuario_solicitando_telefono":
            context.user_data["cliente_telefono"] = text
            context.user_data["estado"] = "usuario_solicitando_origen"
            await update.message.reply_text("¿Desde dónde te recogemos o recogemos el pedido? (Dirección exacta)")
            return

        if estado == "usuario_solicitando_origen":
            context.user_data["cliente_origen"] = text
            context.user_data["estado"] = "usuario_solicitando_detalles"
            await update.message.reply_text(
                "¿Destino (si aplica) u observaciones adicionales?\n"
                "(Ej: barrio de destino, piso, punto de referencia, etc.)"
            )
            return

        if estado == "usuario_solicitando_detalles":
            servicio = context.user_data.get("servicio_solicitado")
            nombre = context.user_data.get("cliente_nombre")
            telefono = context.user_data.get("cliente_telefono")
            origen = context.user_data.get("cliente_origen")
            detalles = text

            # Crear ID de servicio
            prefix = service_prefix(servicio)
            service_id = f"{prefix}-{random.randint(1000, 9999)}"

            channel_id = get_channel_for_service(servicio)
            if not channel_id:
                await update.message.reply_text(
                    "Lo siento, hubo un problema con el tipo de servicio. Intenta de nuevo."
                )
                context.user_data["estado"] = None
                return

            # Guardamos servicio en memoria
            SERVICES[service_id] = {
                "service_id": service_id,
                "tipo": servicio,
                "cliente_id": user.id,
                "cliente_chat_id": chat_id,
                "cliente_nombre": nombre,
                "cliente_telefono": telefono,
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

            texto_canal = (
                f"📢 *Nuevo servicio* [{service_id}]\n\n"
                f"Servicio: *{mobile_service_name(servicio)}*\n"
                f"Cliente: *{nombre}*\n"
                f"Teléfono: `{telefono}`\n"
                f"Origen / Dirección: {origen}\n"
                f"Destino / Observaciones: {detalles}\n"
            )

            try:
                msg = await context.bot.send_message(
                    chat_id=channel_id,
                    text=texto_canal,
                    reply_markup=InlineKeyboardMarkup(
                        [
                            [
                                InlineKeyboardButton(
                                    "✅ Tomar servicio", callback_data=f"TOMAR|{service_id}"
                                )
                            ]
                        ]
                    ),
                    parse_mode="Markdown",
                )
                SERVICES[service_id]["channel_message_id"] = msg.message_id
            except Exception as e:
                logger.error(f"Error enviando a canal: {e}")
                await update.message.reply_text(
                    "Lo siento, hubo un error enviando tu solicitud al canal. Intenta nuevamente."
                )
                context.user_data["estado"] = None
                return

            await update.message.reply_text(
                f"✅ Tu solicitud fue enviada.\n\n"
                f"ID del servicio: *{service_id}*\n"
                "Un móvil cercano tomará tu servicio y te informaré cuando lo haga.",
                parse_mode="Markdown",
            )
            context.user_data["estado"] = None
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

        # Botones de menú admin
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
                    f"  Tel: {m.get('telefono')} | Activo: {m.get('activo', True)} | "
                    f"Último pago: {m.get('ultimo_pago_fecha', 'N/A')}"
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

        # Flujos multi-paso ADMIN
        if estado == "admin_reg_codigo":
            code = text.upper()
            context.user_data["nuevo_movil_codigo"] = code
            context.user_data["estado"] = "admin_reg_nombre"
            await update.message.reply_text("Escribe el *nombre* del conductor:", parse_mode="Markdown")
            return

        if estado == "admin_reg_nombre":
            context.user_data["nuevo_movil_nombre"] = text
            context.user_data["estado"] = "admin_reg_telefono"
            await update.message.reply_text("Escribe el *teléfono* del conductor:", parse_mode="Markdown")
            return

        if estado == "admin_reg_telefono":
            context.user_data["nuevo_movil_telefono"] = text
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

            mobiles[code] = {
                "codigo": code,
                "nombre": nombre,
                "telefono": telefono,
                "servicio": servicio,
                "activo": True,
                "en_jornada": False,
                "ultimo_pago_fecha": None,
                "pago_pendiente": False,
                "chat_id": None,
                "telegram_id": None,
            }
            save_mobiles(mobiles)

            context.user_data["estado"] = None
            await update.message.reply_text(
                f"✅ Móvil registrado:\n\n"
                f"Código: *{code}*\n"
                f"Nombre: *{nombre}*\n"
                f"Teléfono: `{telefono}`\n"
                f"Servicio: *{mobile_service_name(servicio)}*",
                parse_mode="Markdown",
            )
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

            # Avisar al móvil si tiene chat_id
            chat_id_movil = mobile.get("chat_id")
            if chat_id_movil:
                try:
                    await context.bot.send_message(
                        chat_id=chat_id_movil,
                        text="✅ Tu pago del día ha sido aprobado. Puedes trabajar después de las 3:00 p.m.",
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

        # Cualquier otro texto admin
        await update.message.reply_text(
            "No entendí ese comando en modo *Administrador*. Usa los botones del menú.",
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
# MANEJO DE UBICACIÓN (MÓVIL)
# ---------------------------
async def handle_location(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat_id = update.effective_chat.id
    rol = context.user_data.get("rol")

    if rol != "movil":
        # Ignoramos ubicaciones fuera de rol móvil
        return

    code, mobile = find_mobile_by_telegram_id(user.id)
    if not mobile:
        await update.message.reply_text(
            "No encuentro tu registro de móvil. Vuelve a entrar por el menú *Móvil*.",
            parse_mode="Markdown",
        )
        return

    loc = update.message.location
    lat = loc.latitude
    lon = loc.longitude

    # Avisar a los administradores con la ubicación
    texto = (
        f"📍 Ubicación de móvil {code} ({mobile.get('nombre')}):\n\n"
        f"Lat: {lat}\nLon: {lon}"
    )
    for admin_id in ADMIN_IDS:
        try:
            await context.bot.send_message(chat_id=admin_id, text=texto)
        except Exception as e:
            logger.error(f"No se pudo enviar ubicación a admin {admin_id}: {e}")

    await update.message.reply_text("✅ Ubicación enviada al administrador.")


# ---------------------------
# CALLBACKS (BOTONES INLINE)
# ---------------------------
async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data = query.data.split("|")
    action = data[0]

    if action == "TOMAR":
        if len(data) < 2:
            return
        service_id = data[1]
        await handle_tomar_servicio(query, context, service_id)
        return

    if action == "CANCELAR":
        if len(data) < 2:
            return
        service_id = data[1]
        await handle_cancelar_servicio(query, context, service_id)
        return


async def handle_tomar_servicio(query, context, service_id: str):
    user = query.from_user
    codigo_movil, mobile = find_mobile_by_telegram_id(user.id)
    if not mobile:
        # No está logueado como móvil
        await context.bot.send_message(
            chat_id=user.id,
            text=(
                "Para tomar servicios debes iniciar sesión como *Móvil* en el bot PRONTO.\n\n"
                "Entra al bot, toca *Móvil* y escribe tu código (ej: T001)."
            ),
            parse_mode="Markdown",
        )
        return

    service = SERVICES.get(service_id)
    if not service:
        await context.bot.send_message(
            chat_id=user.id,
            text="Este servicio ya no está disponible o el bot se reinició.",
        )
        return

    # Verificar estado del servicio
    if service.get("estado") != "pendiente":
        await context.bot.send_message(
            chat_id=user.id,
            text="Este servicio ya fue tomado por otro móvil.",
        )
        return

    # Verificar tipo de servicio del móvil
    servicio_movil = mobile.get("servicio")
    if servicio_movil != service.get("tipo"):
        await context.bot.send_message(
            chat_id=user.id,
            text=(
                "Este servicio no corresponde a tu tipo de servicio.\n\n"
                f"Tu tipo: {mobile_service_name(servicio_movil)}"
            ),
        )
        return

    # Verificar que pueda trabajar (corte 3pm)
    puede, msg = mobile_can_work(mobile)
    if not puede:
        await context.bot.send_message(
            chat_id=user.id,
            text="⛔ No puedes tomar este servicio:\n\n" + msg,
        )
        return

    # Asignar servicio
    service["estado"] = "asignado"
    service["movil_codigo"] = codigo_movil
    service["movil_nombre"] = mobile.get("nombre")
    service["movil_telefono"] = mobile.get("telefono")
    service["movil_chat_id"] = mobile.get("chat_id") or user.id

    channel_id = service["channel_id"]
    channel_msg_id = service["channel_message_id"]

    # Editar mensaje en el canal
    texto_editado = (
        f"📢 *Servicio asignado* [{service_id}]\n\n"
        f"Servicio: *{mobile_service_name(service['tipo'])}*\n"
        f"Cliente: *{service['cliente_nombre']}*\n"
        f"Teléfono: `{service['cliente_telefono']}`\n"
        f"Origen / Dirección: {service['origen']}\n"
        f"Destino / Observaciones: {service['detalles']}\n\n"
        f"✅ Asignado a: *{service['movil_nombre']}* ({service['movil_codigo']})\n"
        f"Tel móvil: `{service['movil_telefono']}`"
    )
    try:
        await context.bot.edit_message_text(
            chat_id=channel_id,
            message_id=channel_msg_id,
            text=texto_editado,
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            "⚠️ Cancelar servicio", callback_data=f"CANCELAR|{service_id}"
                        )
                    ]
                ]
            ),
        )
    except Exception as e:
        logger.error(f"No se pudo editar mensaje del canal: {e}")

    # Avisar al móvil (privado)
    msg_movil = (
        f"✅ Has tomado el servicio [{service_id}]\n\n"
        f"Cliente: *{service['cliente_nombre']}*\n"
        f"Teléfono: `{service['cliente_telefono']}`\n"
        f"Origen / Dirección: {service['origen']}\n"
        f"Destino / Observaciones: {service['detalles']}\n"
    )
    try:
        await context.bot.send_message(
            chat_id=service["movil_chat_id"],
            text=msg_movil,
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            "⚠️ Cancelar servicio", callback_data=f"CANCELAR|{service_id}"
                        )
                    ]
                ]
            ),
        )
    except Exception as e:
        logger.error(f"No se pudo enviar mensaje al móvil: {e}")

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
        )
    except Exception as e:
        logger.error(f"No se pudo avisar al cliente: {e}")


async def handle_cancelar_servicio(query, context, service_id: str):
    user = query.from_user
    codigo_movil, mobile = find_mobile_by_telegram_id(user.id)
    if not mobile:
        await context.bot.send_message(
            chat_id=user.id,
            text="Solo un móvil que haya tomado el servicio puede cancelarlo.",
        )
        return

    service = SERVICES.get(service_id)
    if not service:
        await context.bot.send_message(
            chat_id=user.id,
            text="Este servicio ya no existe o el bot se reinició.",
        )
        return

    # Verificar que ese móvil sea el asignado
    if service.get("movil_codigo") != codigo_movil:
        await context.bot.send_message(
            chat_id=user.id,
            text="No eres el móvil asignado a este servicio, no puedes cancelarlo.",
        )
        return

    # Volvemos el servicio a pendiente
    service["estado"] = "pendiente"
    service["movil_codigo"] = None
    service["movil_nombre"] = None
    service["movil_telefono"] = None
    service["movil_chat_id"] = None

    channel_id = service["channel_id"]
    channel_msg_id = service["channel_message_id"]

    texto_canal = (
        f"📢 *Servicio disponible nuevamente* [{service_id}]\n\n"
        f"Servicio: *{mobile_service_name(service['tipo'])}*\n"
        f"Cliente: *{service['cliente_nombre']}*\n"
        f"Teléfono: `{service['cliente_telefono']}`\n"
        f"Origen / Dirección: {service['origen']}\n"
        f"Destino / Observaciones: {service['detalles']}\n\n"
        "⚠️ El móvil anterior canceló el servicio."
    )

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
        logger.error(f"No se pudo re-activar el servicio en el canal: {e}")

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
        logger.error(f"No se pudo avisar al cliente sobre la cancelación: {e}")


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

    # Avisar al móvil
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
def main():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("aprobar_pago", aprobar_pago_cmd))

    app.add_handler(CallbackQueryHandler(button_callback))

    app.add_handler(MessageHandler(filters.LOCATION, handle_location))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    app.run_polling()


if __name__ == "__main__":
    main()
