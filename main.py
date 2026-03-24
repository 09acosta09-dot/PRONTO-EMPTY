"""
Bot PRONTO - Sistema de domicilios y servicios para Telegram
=============================================================
Arquitectura modular en un solo archivo para facilitar despliegue en Railway.
Secciones:
  1. IMPORTS
  2. CONFIGURACIÓN
  3. SEGURIDAD / ROLES  ← CRÍTICO: control de acceso admin
  4. UTILIDADES (archivo, tiempo, distancia)
  5. TECLADOS / MENÚS
  6. HANDLERS - /start y /soy_movil
  7. HANDLERS - USUARIO (flujo de solicitud)
  8. HANDLERS - MÓVIL (jornada)
  9. HANDLERS - ADMINISTRADOR (panel protegido)
 10. HANDLER - CALLBACKS (inline buttons)
 11. HANDLER - TEXTO (router principal)
 12. HANDLER - UBICACIÓN
 13. MAIN
"""

# ============================================================
# 1. IMPORTS
# ============================================================

import os
import json
import math
import random
from datetime import datetime, time
from zoneinfo import ZoneInfo

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

# ============================================================
# 2. CONFIGURACIÓN
# ============================================================

# Token del bot (variable de entorno en Railway)
TOKEN = os.getenv("TU_TOKEN_NUEVO")
if not TOKEN:
    raise RuntimeError("La variable de entorno TU_TOKEN_NUEVO no está configurada.")

# IDs de canales por tipo de servicio
CHANNEL_SERVICIO_ESPECIAL = -1002697357566
CHANNEL_DOMICILIOS        = -1002503403579
CHANNEL_CAMIONETAS        = -1002662309590
CHANNEL_MOTOCARRO         = -1002688723492

# Canal de backups (variable de entorno)
BACKUP_CHANNEL_ID = int(os.getenv("BACKUP_CHANNEL_ID", "0"))

# Links de invitación a los canales
LINK_SERVICIO_ESPECIAL = "https://t.me/+Drczf-TdHCUzNDZh"
LINK_DOMICILIOS        = "https://t.me/+gZvnu8zolb1iOTBh"
LINK_CAMIONETAS        = "https://t.me/+KRam-XSvPQ5jNjRh"
LINK_MOTOCARRO         = "https://t.me/+REkbglMlfxE3YjI5"

# Número Nequi para pagos
NEQUI_NUMBER = "3052915231"

# Directorio de datos persistentes
DATA_DIR = "/data"
os.makedirs(DATA_DIR, exist_ok=True)
MOBILES_FILE  = os.path.join(DATA_DIR, "mobiles.json")
SERVICES_FILE = os.path.join(DATA_DIR, "services.json")

# Webhook Railway
WEBHOOK_DOMAIN = "https://pronto-empty-production.up.railway.app"
WEBHOOK_PATH   = f"/webhook/{TOKEN}"
WEBHOOK_URL    = WEBHOOK_DOMAIN + WEBHOOK_PATH

# Zona horaria Colombia
TZ_CO  = ZoneInfo("America/Bogota")
CORTE  = time(15, 0)  # 3:00 p.m.

# Información de servicios (prefix se usa para generar códigos como D001, SE002, etc.)
SERVICE_INFO = {
    "Servicio Especial": {
        "label_user": "🚕 Servicio Especial (Taxi Blanco)",
        "channel_id": CHANNEL_SERVICIO_ESPECIAL,
        "link": LINK_SERVICIO_ESPECIAL,
        "prefix": "SE",
    },
    "Domicilios": {
        "label_user": "📦 Domicilios",
        "channel_id": CHANNEL_DOMICILIOS,
        "link": LINK_DOMICILIOS,
        "prefix": "D",
    },
    "Camionetas": {
        "label_user": "🚚 Camionetas",
        "channel_id": CHANNEL_CAMIONETAS,
        "link": LINK_CAMIONETAS,
        "prefix": "C",
    },
    "Motocarro": {
        "label_user": "🛺 Motocarro",
        "channel_id": CHANNEL_MOTOCARRO,
        "link": LINK_MOTOCARRO,
        "prefix": "M",
    },
}

# ============================================================
# 3. SEGURIDAD / ROLES
# ============================================================
#
# CÓMO FUNCIONA:
# - ADMIN_IDS: lista de user_id de Telegram autorizados como administradores.
#   Para encontrar tu user_id habla con @userinfobot en Telegram.
# - is_admin(): función que valida si un user_id tiene rol de administrador.
# - require_admin(): decorador / guard que se llama ANTES de ejecutar cualquier
#   lógica de administrador. Si el usuario no está en ADMIN_IDS, bloquea y
#   redirige al menú principal. Se aplica en TODOS los puntos de entrada admin.
#
# IMPORTANTE: agregar aquí los IDs de los admins reales de PRONTO.
# ============================================================

ADMIN_IDS = [1741298723, 7076796229]  # ← pon aquí los user_id de los admins


def is_admin(user_id: int) -> bool:
    """Retorna True si el user_id tiene rol de administrador."""
    return user_id in ADMIN_IDS


async def deny_admin_access(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Bloquea el acceso y redirige al menú principal.
    Se llama desde cualquier punto donde se detecte acceso no autorizado al panel admin.
    """
    context.user_data.clear()
    await update.message.reply_text(
        "🚫 No tienes permisos para acceder a este menú.\n\n"
        "Si crees que esto es un error, comunícate con el administrador.",
        reply_markup=build_main_keyboard(),
    )


# ============================================================
# 4. UTILIDADES
# ============================================================

# --- Archivo ---

def load_json(path: str, default):
    """Carga un archivo JSON. Retorna `default` si no existe o hay error."""
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def save_json(path: str, data):
    """Guarda datos como JSON con indentación legible."""
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def get_mobiles() -> dict:
    data = load_json(MOBILES_FILE, {})
    return data if isinstance(data, dict) else {}


def save_mobiles(data: dict):
    save_json(MOBILES_FILE, data)


def get_services() -> dict:
    data = load_json(SERVICES_FILE, {})
    return data if isinstance(data, dict) else {}


def save_services(data: dict):
    save_json(SERVICES_FILE, data)


async def backup_file(context, filename: str):
    """Envía un archivo de datos al canal de backup como documento."""
    if not BACKUP_CHANNEL_ID:
        return
    try:
        with open(filename, "rb") as f:
            await context.bot.send_document(
                chat_id=BACKUP_CHANNEL_ID,
                document=f,
                filename=f"BACKUP_{os.path.basename(filename)}",
            )
    except Exception as e:
        print(f"[backup_file] Error: {e}")


# --- Tiempo ---

def now_colombia() -> datetime:
    return datetime.now(TZ_CO)


def now_colombia_str() -> str:
    return now_colombia().strftime("%Y-%m-%d %I:%M %p")


def after_cutoff() -> bool:
    """Retorna True si la hora actual es >= 3:00 p.m. en Colombia."""
    return now_colombia().time() >= CORTE


def mobile_can_work(mobile: dict) -> tuple[bool, str]:
    """
    Verifica si un móvil puede recibir servicios según la hora y estado de pago.
    Antes de las 3:00 p.m.: puede trabajar sin pago aprobado.
    Desde las 3:00 p.m.: requiere pago_aprobado = True.
    """
    if after_cutoff() and not mobile.get("pago_aprobado", False):
        return False, (
            "Ya pasó la hora de corte (3:00 p.m.).\n"
            "Para trabajar después de las 3:00 p.m. debes realizar el pago "
            "y esperar la aprobación del administrador."
        )
    return True, ""


# --- Distancia ---

def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calcula la distancia en km entre dos coordenadas GPS usando la fórmula de Haversine."""
    R = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi    = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def seleccionar_movil_mas_cercano(servicio: str, lat_cliente, lon_cliente) -> dict | None:
    """
    Busca el móvil activo y disponible más cercano al cliente para el servicio indicado.
    Si no hay coordenadas, asigna distancia infinita (se toma igual si no hay otro candidato).
    Retorna None si no hay candidatos.
    """
    mobiles    = get_mobiles()
    candidatos = []

    for chat_id_str, m in mobiles.items():
        if not m.get("activo"):
            continue
        if m.get("servicio") != servicio:
            continue
        puede, _ = mobile_can_work(m)
        if not puede:
            continue

        m_lat = m.get("lat")
        m_lon = m.get("lon")

        if m_lat is not None and m_lon is not None and lat_cliente is not None and lon_cliente is not None:
            dist = haversine_distance(lat_cliente, lon_cliente, m_lat, m_lon)
        else:
            dist = float("inf")

        candidatos.append({
            "chat_id":  int(chat_id_str),
            "codigo":   m.get("codigo"),
            "servicio": servicio,
            "distancia": dist,
        })

    if not candidatos:
        return None

    candidatos.sort(key=lambda x: x["distancia"])
    dist_min  = candidatos[0]["distancia"]
    empatados = [c for c in candidatos if c["distancia"] == dist_min]
    return random.choice(empatados)


def asignar_codigo_movil(servicio: str) -> str:
    """Genera el siguiente código correlativo para un móvil (ej: D003, SE007)."""
    mobiles = get_mobiles()
    prefix  = SERVICE_INFO[servicio]["prefix"]
    numeros = []
    for m in mobiles.values():
        codigo = m.get("codigo", "")
        if codigo.startswith(prefix):
            try:
                numeros.append(int(codigo[len(prefix):]))
            except ValueError:
                continue
    next_num = max(numeros) + 1 if numeros else 1
    return f"{prefix}{next_num:03d}"


# ============================================================
# 5. TECLADOS / MENÚS
# ============================================================

def build_start_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup([[KeyboardButton("🚀 Iniciar")]], resize_keyboard=True)


def build_main_keyboard() -> ReplyKeyboardMarkup:
    """
    Menú principal público. NO incluye opción de Administrador.
    El acceso al panel admin solo es por comando /admin (solo admins ven la opción).
    """
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton("👤 Cliente")],
            [KeyboardButton("🚗 Movil")],
        ],
        resize_keyboard=True,
    )


def build_admin_keyboard() -> ReplyKeyboardMarkup:
    """
    Teclado del panel de administración.
    Solo se muestra a usuarios validados como admin (is_admin() = True).
    """
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton("📲 Registrar móvil")],
            [KeyboardButton("🚗 Ver móviles registrados")],
            [KeyboardButton("🗑 Desactivar móvil")],
            [KeyboardButton("🗑 Eliminar móvil")],
            [KeyboardButton("💰 Aprobar pagos")],
            [KeyboardButton("📋 Ver servicios activos")],
            [KeyboardButton("⬅ Volver al inicio")],
        ],
        resize_keyboard=True,
    )


def build_user_service_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton(SERVICE_INFO["Camionetas"]["label_user"])],
            [KeyboardButton(SERVICE_INFO["Servicio Especial (Taxi Blanco)"]["label_user"])],
            [KeyboardButton(SERVICE_INFO["Motocarro"]["label_user"])],
            [KeyboardButton(SERVICE_INFO["Domicilios"]["label_user"])],
            [KeyboardButton("⬅ Volver al inicio")],
        ],
        resize_keyboard=True,
    )


def build_movil_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton("🚀 Iniciar jornada")],
            [KeyboardButton("📍 Compartir ubicación")],
            [KeyboardButton("💰 Enviar pago")],
            [KeyboardButton("🛑 Finalizar jornada")],
            [KeyboardButton("⬅ Volver al inicio")],
        ],
        resize_keyboard=True,
    )


def build_location_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton("📍 Enviar ubicación", request_location=True)],
            [KeyboardButton("Omitir ubicación")],
            [KeyboardButton("⬅ Volver al inicio")],
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


# ============================================================
# 6. HANDLERS - /start y /soy_movil
# ============================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Comando /start. Limpia el estado y muestra el menú de bienvenida.
    Pregunta si el usuario es Cliente u Operador.
    El menú de Administrador NO aparece aquí.
    """
    context.user_data.clear()
    await update.message.reply_text(
        "👋 Bienvenido a *PRONTO*\n\n"
        "¿Cómo deseas continuar?",
        parse_mode="Markdown",
        reply_markup=build_main_keyboard(),
    )


async def cmd_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Comando /admin — ÚNICO punto de entrada al panel de administración.
    
    SEGURIDAD:
    - Valida is_admin() antes de hacer CUALQUIER cosa.
    - Si no es admin, niega el acceso y redirige.
    - Los usuarios regulares ni siquiera saben que este comando existe
      (no aparece en ningún menú público).
    """
    user_id = update.effective_user.id

    # ── GUARD: validación de rol ──────────────────────────────
    if not is_admin(user_id):
        await deny_admin_access(update, context)
        return
    # ─────────────────────────────────────────────────────────

    context.user_data.clear()
    context.user_data["mode"]       = "admin"
    context.user_data["admin_step"] = None

    await update.message.reply_text(
        "👮 Panel de administración\n\nElige una opción:",
        reply_markup=build_admin_keyboard(),
    )


async def soy_movil_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Comando /soy_movil — el conductor lo usa para solicitar registro.
    Notifica a todos los admins con botón para iniciar el registro.
    """
    user    = update.effective_user
    chat_id = update.effective_chat.id

    await update.message.reply_text(
        "✅ Tu solicitud fue enviada.\n"
        "El administrador te registrará pronto para que puedas empezar a trabajar."
    )

    nombre   = user.full_name or "Sin nombre"
    username = f"@{user.username}" if user.username else "Sin username"

    texto_admin = (
        "📲 *Nuevo conductor quiere registrarse*\n\n"
        f"👤 Nombre: *{nombre}*\n"
        f"🔗 Usuario: {username}\n"
        f"💬 Chat ID: `{chat_id}`\n\n"
        "¿Deseas iniciar el registro de este móvil ahora?"
    )
    keyboard = InlineKeyboardMarkup(
        [[InlineKeyboardButton("📝 Iniciar registro", callback_data=f"REG_MOVIL|{chat_id}")]]
    )

    for admin_id in ADMIN_IDS:
        try:
            await context.bot.send_message(
                chat_id=admin_id,
                text=texto_admin,
                parse_mode="Markdown",
                reply_markup=keyboard,
            )
        except Exception:
            pass


# ============================================================
# 7. HANDLERS - USUARIO (flujo de solicitud de servicio)
# ============================================================

async def handle_cliente_option(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Inicia el flujo de solicitud de servicio para el cliente."""
    context.user_data["mode"] = "usuario"
    context.user_data["step"] = "choose_service"
    await update.message.reply_text(
        "Selecciona el tipo de servicio que necesitas:",
        reply_markup=build_user_service_keyboard(),
    )


async def handle_usuario_service_choice(update: Update, context: ContextTypes.DEFAULT_TYPE, servicio: str):
    """El cliente eligió un tipo de servicio. Comienza a recolectar datos."""
    context.user_data["mode"]    = "usuario"
    context.user_data["step"]    = "ask_name"
    context.user_data["servicio"] = servicio
    context.user_data["data"]    = {}
    await update.message.reply_text(
        "📝 Por favor escribe tu *nombre completo*:",
        parse_mode="Markdown",
    )


async def finalize_user_request(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Completa la solicitud del usuario:
    - Genera un ID de servicio único.
    - Busca el móvil más cercano disponible.
    - Notifica al móvil y al canal correspondiente.
    """
    user    = update.effective_user
    chat_id = update.effective_chat.id
    data    = context.user_data.get("data", {})
    servicio = context.user_data.get("servicio")

    if not servicio or not data:
        await update.message.reply_text("Ocurrió un problema. Intenta de nuevo.")
        return

    hora             = now_colombia_str()
    data["hora"]     = hora
    data["servicio"] = servicio
    data["user_chat_id"] = chat_id
    data["user_id"]  = user.id

    # Generar ID único de servicio (S00001, S00002...)
    services = get_services()
    nums = []
    for sid in services:
        if isinstance(sid, str) and sid.startswith("S"):
            try:
                nums.append(int(sid[1:]))
            except ValueError:
                pass
    service_id = f"S{(max(nums) + 1 if nums else 1):05d}"

    data["id"]             = service_id
    data["status"]         = "pendiente"
    data["movil_codigo"]   = None
    data["movil_chat_id"]  = None

    # Buscar móvil más cercano
    movil_info = seleccionar_movil_mas_cercano(servicio, data.get("lat"), data.get("lon"))
    if movil_info is None:
        await update.message.reply_text(
            "😔 En este momento no hay móviles disponibles para este servicio.\n"
            "Por favor intenta en unos minutos."
        )
        return

    movil_chat_id  = movil_info["chat_id"]
    movil_codigo   = movil_info["codigo"]
    movil_servicio = movil_info["servicio"]

    data["movil_codigo"]  = movil_codigo
    data["movil_chat_id"] = movil_chat_id
    services[service_id]  = data
    save_services(services)

    await update.message.reply_text(
        "✅ Tu solicitud ha sido registrada.\n"
        "Estamos notificando a un móvil cercano para que tome tu servicio."
    )

    # Mensaje al móvil
    texto_movil  = f"🚨 *Nuevo servicio de {movil_servicio}*\n\n"
    texto_movil += f"🆔 Código de servicio: *{service_id}*\n"
    texto_movil += f"👤 Cliente: *{data.get('nombre', '(sin nombre)')}*\n"
    texto_movil += f"📞 Teléfono cliente: *{data.get('telefono', '(sin teléfono)')}*\n"
    texto_movil += f"📍 Destino: *{data.get('destino', '(sin destino)')}*\n"
    if movil_servicio == "Camionetas":
        texto_movil += f"📦 Tipo de carga: *{data.get('carga', '(no especificada)')}*\n"
    if data.get("lat") is not None and data.get("lon") is not None:
        texto_movil += "\n🌎 El cliente compartió ubicación GPS.\n"
    texto_movil += f"\n⏰ Hora: *{hora}* (Colombia)\n\nPresiona el botón para tomar el servicio."

    keyboard = InlineKeyboardMarkup(
        [[InlineKeyboardButton("🚨🔴 RESERVAR SERVICIO 🔴🚨", callback_data=f"RESERVAR|{service_id}")]]
    )

    try:
        await context.bot.send_message(
            chat_id=movil_chat_id,
            text=texto_movil,
            reply_markup=keyboard,
            parse_mode="Markdown",
        )
    except Exception:
        await update.message.reply_text("Problema al notificar al móvil. Intenta de nuevo.")
        return

    # Resumen al canal del servicio
    channel_id = SERVICE_INFO[movil_servicio]["channel_id"]
    resumen_canal = (
        f"📢 *Nuevo servicio de {movil_servicio}*\n"
        f"🆔 Servicio: *{service_id}*\n"
        f"👤 Cliente: *{data.get('nombre','')}*\n"
        f"📞 Tel: *{data.get('telefono','')}*\n"
        f"📍 Destino: *{data.get('destino','')}*\n"
        f"🕒 Hora: *{hora}* (Colombia)\n"
        f"🚗 Móvil asignado: *{movil_codigo}* (en espera de reserva)"
    )
    try:
        await context.bot.send_message(chat_id=channel_id, text=resumen_canal, parse_mode="Markdown")
    except Exception:
        pass

    context.user_data.clear()


# ============================================================
# 8. HANDLERS - MÓVIL (gestión de jornada)
# ============================================================

async def handle_operador_option(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Inicia el flujo de autenticación para el operador/móvil."""
    context.user_data.clear()
    context.user_data["mode"]       = "movil_auth"
    context.user_data["movil_step"] = "ask_code"
    await update.message.reply_text(
        "🔐 Escribe tu *código de móvil* (ej: SE001, D005, C010, M003):",
        parse_mode="Markdown",
    )


async def handle_movil_menu(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str):
    """Maneja las acciones del menú del móvil una vez autenticado."""
    user_id_str = str(update.effective_user.id)
    mobiles     = get_mobiles()
    m           = mobiles.get(user_id_str)

    if not m:
        await update.message.reply_text(
            "❌ No estás registrado como móvil. Pide al administrador que te registre.",
            reply_markup=build_main_keyboard(),
        )
        context.user_data.clear()
        return

    codigo   = m.get("codigo", "SIN-CODIGO")
    servicio = m.get("servicio", "Desconocido")

    if text == "🚀 Iniciar jornada":
        puede, msg = mobile_can_work(m)
        if not puede:
            await update.message.reply_text("⛔ " + msg, reply_markup=build_movil_keyboard())
            return
        m["activo"] = True
        mobiles[user_id_str] = m
        save_mobiles(mobiles)
        link    = SERVICE_INFO.get(servicio, {}).get("link")
        mensaje = f"✅ Jornada iniciada para el móvil *{codigo}* ({servicio}).\n\n"
        if link:
            mensaje += f"Para ver servicios de *{servicio}*, entra al canal:\n{link}"
        else:
            mensaje += "El administrador te indicará el canal de servicios."
        await update.message.reply_text(mensaje, parse_mode="Markdown", reply_markup=build_movil_keyboard())
        return

    if text == "📍 Compartir ubicación":
        await update.message.reply_text(
            "Comparte tu ubicación desde Telegram (📎 ➜ Ubicación) para asignación por cercanía.",
            reply_markup=build_movil_keyboard(),
        )
        return

    if text == "💰 Enviar pago":
        await update.message.reply_text(
            "💰 *Instrucciones de pago:*\n\n"
            f"1️⃣ Realiza el pago a Nequi: 👉 *{NEQUI_NUMBER}*\n"
            "2️⃣ Envía aquí la captura del comprobante.\n"
            "3️⃣ El administrador revisará y aprobará tu pago.\n\n"
            "Con pago aprobado podrás trabajar después de las 3:00 p.m.",
            parse_mode="Markdown",
            reply_markup=build_movil_keyboard(),
        )
        return

    if text == "🛑 Finalizar jornada":
        m["activo"] = False
        mobiles[user_id_str] = m
        save_mobiles(mobiles)
        await update.message.reply_text(
            "🛑 Has finalizado tu jornada. Ya no recibirás servicios hasta que vuelvas a iniciar.",
            reply_markup=build_movil_keyboard(),
        )
        return

    await update.message.reply_text("Usa las opciones del menú.", reply_markup=build_movil_keyboard())


# ============================================================
# 9. HANDLERS - ADMINISTRADOR (panel protegido)
# ============================================================

async def handle_admin_menu(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str):
    """
    Maneja todas las acciones del panel de administración.
    
    SEGURIDAD:
    Esta función SIEMPRE verifica is_admin() antes de procesar cualquier acción.
    Aunque el mode="admin" esté guardado en user_data, se re-valida el user_id
    en cada llamada para evitar que alguien manipule el estado de la sesión.
    """
    user_id    = update.effective_user.id
    admin_step = context.user_data.get("admin_step")

    # ── GUARD: doble validación en cada acción admin ──────────
    if not is_admin(user_id):
        await deny_admin_access(update, context)
        return
    # ─────────────────────────────────────────────────────────

    # --- Registrar móvil ---
    if text == "📲 Registrar móvil":
        context.user_data["admin_step"] = "reg_name"
        context.user_data["reg_movil"]  = {}
        await update.message.reply_text(
            "📲 Registro de móvil.\n\nEscribe el *nombre completo* del conductor:",
            parse_mode="Markdown",
        )
        return

    # --- Ver móviles ---
    if text == "🚗 Ver móviles registrados":
        mobiles = get_mobiles()
        if not mobiles:
            await update.message.reply_text("No hay móviles registrados todavía.")
            return
        lines = ["📋 *Móviles registrados:*\n"]
        for m in mobiles.values():
            activo = "✅ Activo" if m.get("activo") else "⛔ Inactivo"
            pago   = "💰 Pago OK" if m.get("pago_aprobado") else "💸 Pendiente"
            lines.append(
                f"• {m.get('codigo','?')} – {m.get('nombre','Sin nombre')} "
                f"– {m.get('servicio','?')} – {activo} – {pago}"
            )
        await update.message.reply_text("\n".join(lines), parse_mode="Markdown")
        return

    # --- Eliminar móvil ---
    if text == "🗑 Eliminar móvil":
        mobiles = get_mobiles()
        if not mobiles:
            await update.message.reply_text("No hay móviles registrados.")
            return
        lista  = "📋 *Móviles registrados:*\n\n"
        lista += "\n".join(f"• {m.get('codigo','?')} - {m.get('nombre','?')}" for m in mobiles.values())
        lista += "\n\nEscribe el *código* del móvil que deseas eliminar:"
        context.user_data["admin_step"] = "eliminar_movil"
        await update.message.reply_text(lista, parse_mode="Markdown")
        return

    # --- Desactivar móvil ---
    if text == "🗑 Desactivar móvil":
        context.user_data["admin_step"] = "deactivate_code"
        await update.message.reply_text(
            "Escribe el *código del móvil* que deseas desactivar (ej: SE001, D015):",
            parse_mode="Markdown",
        )
        return

    # --- Aprobar pagos ---
    if text == "💰 Aprobar pagos":
        context.user_data["admin_step"] = "approve_payment_code"
        await update.message.reply_text(
            "Escribe el *código del móvil* cuyo pago deseas aprobar (ej: SE001, D015):",
            parse_mode="Markdown",
        )
        return

    # --- Ver servicios activos ---
    if text == "📋 Ver servicios activos":
        services = get_services()
        activos  = [s for s in services.values() if s.get("status") in ["pendiente", "reservado"]]
        if not activos:
            await update.message.reply_text("No hay servicios activos en este momento.")
            return
        lines = ["📋 *Servicios activos:*\n"]
        for s in activos:
            lines.append(
                f"• {s.get('id','')} – {s.get('servicio','')} – {s.get('nombre','')} "
                f"– Destino: {s.get('destino','')} – Estado: {s.get('status','')} "
                f"– Móvil: {s.get('movil_codigo','Sin móvil')}"
            )
        await update.message.reply_text("\n".join(lines), parse_mode="Markdown")
        return

    # --- Flujos de registro por pasos ---

    if admin_step == "reg_name":
        context.user_data["reg_movil"]["nombre"] = text
        context.user_data["admin_step"] = "reg_cedula"
        await update.message.reply_text("✍ Escribe la *cédula* del conductor:", parse_mode="Markdown")
        return

    if admin_step == "reg_cedula":
        context.user_data["reg_movil"]["cedula"] = text
        context.user_data["admin_step"] = "reg_service"
        await update.message.reply_text(
            "🚗 Indica el *tipo de servicio*:\n"
            "- Servicio Especial\n- Domicilios\n- Camionetas\n- Motocarro\n\n"
            "Escríbelo exactamente como aparece arriba.",
            parse_mode="Markdown",
        )
        return

    if admin_step == "reg_service":
        servicio_ingresado = text.strip()
        if servicio_ingresado not in SERVICE_INFO:
            await update.message.reply_text(
                "❌ Servicio no válido. Escribe: Servicio Especial, Domicilios, Camionetas o Motocarro."
            )
            return
        context.user_data["reg_movil"]["servicio"] = servicio_ingresado
        context.user_data["admin_step"] = "reg_placa"
        await update.message.reply_text("🚘 Escribe la *placa* del vehículo:", parse_mode="Markdown")
        return

    if admin_step == "reg_placa":
        context.user_data["reg_movil"]["placa"] = text
        context.user_data["admin_step"] = "reg_marca"
        await update.message.reply_text("🚘 Escribe la *marca* del vehículo:", parse_mode="Markdown")
        return

    if admin_step == "reg_marca":
        context.user_data["reg_movil"]["marca"] = text
        context.user_data["admin_step"] = "reg_modelo"
        await update.message.reply_text("🚘 Escribe el *modelo* del vehículo (ej: 2015):", parse_mode="Markdown")
        return

    if admin_step == "reg_modelo":
        context.user_data["reg_movil"]["modelo"] = text
        reg = context.user_data.get("reg_movil", {})

        if reg.get("chat_id"):
            # Chat ID conocido (vino desde botón /soy_movil)
            await _finalizar_registro_movil(update, context, reg, int(reg["chat_id"]))
        else:
            # Pedir el chat ID manualmente
            context.user_data["admin_step"] = "reg_chatid"
            await update.message.reply_text(
                "📲 Escribe el *chat ID* del conductor:",
                parse_mode="Markdown",
            )
        return

    if admin_step == "reg_chatid":
        try:
            chat_id_movil = int(text)
        except ValueError:
            await update.message.reply_text("El chat ID debe ser un número. Intenta de nuevo.")
            return
        reg = context.user_data.get("reg_movil", {})
        await _finalizar_registro_movil(update, context, reg, chat_id_movil)
        return

    if admin_step == "eliminar_movil":
        codigo_ingresado = text.strip().upper()
        mobiles = get_mobiles()
        target  = None
        for cid, m in mobiles.items():
            if m.get("codigo", "").upper() == codigo_ingresado:
                target = cid
                break
        if not target:
            await update.message.reply_text("❌ No encontré un móvil con ese código.")
            return
        nombre = mobiles[target].get("nombre", "")
        del mobiles[target]
        save_mobiles(mobiles)
        context.user_data["admin_step"] = None
        await update.message.reply_text(f"🗑 Móvil *{nombre}* ({codigo_ingresado}) eliminado.", parse_mode="Markdown")
        return

    if admin_step == "deactivate_code":
        codigo  = text.strip().upper()
        mobiles = get_mobiles()
        target  = None
        for cid, m in mobiles.items():
            if m.get("codigo", "").upper() == codigo:
                target = cid
                break
        if not target:
            await update.message.reply_text("No encontré un móvil con ese código.")
            return
        mobiles[target]["activo"] = False
        save_mobiles(mobiles)
        context.user_data["admin_step"] = None
        await update.message.reply_text(f"🛑 El móvil *{codigo}* ha sido desactivado.", parse_mode="Markdown")
        return

    if admin_step == "approve_payment_code":
        codigo  = text.strip().upper()
        mobiles = get_mobiles()
        target  = None
        target_data = None
        for cid, m in mobiles.items():
            if m.get("codigo", "").upper() == codigo:
                target      = cid
                target_data = m
                break
        if not target:
            await update.message.reply_text("No encontré un móvil con ese código.")
            return

        context.user_data["pending_payment_code"] = codigo
        pago  = "💰 Pago OK" if target_data.get("pago_aprobado") else "💸 Pendiente"
        texto = (
            "📋 *Información del móvil:*\n\n"
            f"🔢 Código: *{codigo}*\n"
            f"👤 Nombre: *{target_data.get('nombre','?')}*\n"
            f"🧾 Cédula: *{target_data.get('cedula','?')}*\n"
            f"🚗 Servicio: *{target_data.get('servicio','?')}*\n"
            f"🚘 Placa: *{target_data.get('placa','?')}*\n"
            f"🚘 Marca: *{target_data.get('marca','?')}*\n"
            f"🚘 Modelo: *{target_data.get('modelo','?')}*\n"
            f"💸 Estado de pago: {pago}\n\n"
            "¿Deseas *aprobar el pago* de este móvil?"
        )
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Aprobar pago", callback_data=f"APROBAR_PAGO|{codigo}")],
            [InlineKeyboardButton("❌ Cancelar",     callback_data=f"CANCELAR_PAGO|{codigo}")],
        ])
        await update.message.reply_text(texto, parse_mode="Markdown", reply_markup=keyboard)
        return

    # Fallback
    await update.message.reply_text("Usa las opciones del menú de administrador.", reply_markup=build_admin_keyboard())


async def _finalizar_registro_movil(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    reg: dict,
    chat_id_movil: int,
):
    """Guarda el registro completo del móvil y notifica al admin."""
    servicio = reg.get("servicio")
    if not servicio:
        await update.message.reply_text("❌ Error interno: servicio no definido. Intenta de nuevo.")
        context.user_data["admin_step"] = None
        return

    codigo  = asignar_codigo_movil(servicio)
    mobiles = get_mobiles()
    mobiles[str(chat_id_movil)] = {
        "codigo":        codigo,
        "servicio":      servicio,
        "lat":           None,
        "lon":           None,
        "activo":        False,
        "nombre":        reg.get("nombre", ""),
        "cedula":        reg.get("cedula", ""),
        "placa":         reg.get("placa", ""),
        "marca":         reg.get("marca", ""),
        "modelo":        reg.get("modelo", ""),
        "pago_aprobado": False,
    }
    save_mobiles(mobiles)

    context.user_data["admin_step"] = None
    context.user_data["reg_movil"]  = {}

    await update.message.reply_text(
        f"✅ Móvil registrado correctamente.\n\n"
        f"Conductor: *{reg.get('nombre', '')}*\n"
        f"Servicio: *{servicio}*\n"
        f"Código asignado: *{codigo}*\n\n"
        "El conductor debe entrar al bot, elegir '🚗 Operador' y autenticarse con este código.",
        parse_mode="Markdown",
    )


# ============================================================
# 10. HANDLER - CALLBACKS (inline buttons)
# ============================================================

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Maneja todos los callbacks de botones inline.
    
    SEGURIDAD en callbacks admin (REG_MOVIL, APROBAR_PAGO, CANCELAR_PAGO):
    - Se re-valida is_admin() antes de ejecutar cualquier acción privilegiada.
    - Así se evita que alguien reenvíe un mensaje con botón admin y lo ejecute.
    """
    query   = update.callback_query
    await query.answer()
    data    = query.data
    bot     = context.bot
    user_id = query.from_user.id

    # ── VOLVER AL INICIO ──────────────────────────────────────
    if data == "volver_inicio":
        context.user_data.clear()
        await query.edit_message_text("🏠 Menú principal\n\nElige una opción:")
        return

    # ── SERVICIO COMPLETADO ───────────────────────────────────
    if data.startswith("servicio_completado_"):
        service_id = data.split("_")[2]
        services   = get_services()
        if service_id in services:
            services[service_id]["status"] = "completado"
            save_services(services)
            cliente_id = services[service_id].get("user_chat_id")
            if cliente_id:
                try:
                    await bot.send_message(chat_id=cliente_id, text="✅ Tu servicio ha sido completado.")
                except Exception:
                    pass
            for admin_id in ADMIN_IDS:
                try:
                    await bot.send_message(chat_id=admin_id, text=f"✅ Servicio {service_id} completado.")
                except Exception:
                    pass
        await query.edit_message_text("✅ Servicio marcado como completado.")
        return

    # ── RESERVAR SERVICIO (móvil) ─────────────────────────────
    if data.startswith("RESERVAR|"):
        service_id     = data.split("|", 1)[1]
        movil_chat_id  = query.message.chat.id
        mobiles        = get_mobiles()
        mobile         = mobiles.get(str(movil_chat_id))

        if mobile:
            puede, msg = mobile_can_work(mobile)
            if not puede:
                await query.edit_message_text("⛔ No puedes reservar servicios:\n\n" + msg)
                return
            if not mobile.get("activo", False):
                await query.edit_message_text(
                    "⛔ No tienes jornada iniciada.\n\nEntra al bot ➜ Operador ➜ 🚀 Iniciar jornada."
                )
                return

        services     = get_services()
        servicio_data = services.get(service_id)
        if not servicio_data:
            await query.edit_message_text("Este servicio ya no está disponible o ha sido eliminado.")
            return
        if servicio_data.get("status") == "reservado":
            await query.edit_message_text("Este servicio ya fue tomado por otro móvil.")
            return
        if servicio_data.get("movil_chat_id") != movil_chat_id:
            await query.edit_message_text("Este servicio no está asignado a tu móvil.")
            return

        servicio_data["status"]       = "reservado"
        servicio_data["hora_reserva"] = now_colombia_str()
        services[service_id]          = servicio_data
        save_services(services)

        movil_codigo = servicio_data.get("movil_codigo")
        texto_reserva  = (
            f"✅ Has *reservado* el servicio {service_id}.\n\n"
            f"👤 {servicio_data.get('nombre', '')}\n"
            f"📞 Teléfono: *{servicio_data.get('telefono', '')}*\n"
            f"📍 Destino: {servicio_data.get('destino', '')}\n"
        )
        if servicio_data.get("servicio") == "Camionetas":
            texto_reserva += f"📦 Carga: {servicio_data.get('carga', '')}\n"
        texto_reserva += f"\n⏰ Hora reserva: {servicio_data.get('hora_reserva', '')} (Colombia)"

        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ SERVICIO COMPLETADO", callback_data=f"servicio_completado_{service_id}")],
            [InlineKeyboardButton("❌ CANCELAR SERVICIO",   callback_data=f"cancelar_servicio_{service_id}")],
        ])
        await query.edit_message_text(texto_reserva, parse_mode="Markdown", reply_markup=keyboard)

        # Notificar al cliente
        user_chat_id = servicio_data.get("user_chat_id")
        if user_chat_id:
            try:
                await bot.send_message(
                    chat_id=user_chat_id,
                    text=(
                        f"✅ Tu servicio ha sido asignado.\n\n"
                        f"El móvil *{movil_codigo}* llegará pronto.\n"
                        "Por favor mantén tu teléfono disponible."
                    ),
                    parse_mode="Markdown",
                )
            except Exception:
                pass

        # Resumen al canal
        servicio_tipo = servicio_data.get("servicio")
        channel_id    = SERVICE_INFO[servicio_tipo]["channel_id"]
        resumen = (
            f"✅ *Servicio reservado*\n"
            f"🆔 Servicio: *{service_id}*\n"
            f"🚗 Móvil: *{movil_codigo}*\n"
            f"👤 Cliente: *{servicio_data.get('nombre','')}*\n"
            f"📞 Tel: *{servicio_data.get('telefono','')}*\n"
            f"📍 Destino: *{servicio_data.get('destino','')}*\n"
            f"⏰ Hora reserva: *{servicio_data.get('hora_reserva','')}* (Colombia)"
        )
        try:
            await bot.send_message(chat_id=channel_id, text=resumen, parse_mode="Markdown")
        except Exception:
            pass
        return

    # ── CANCELAR SERVICIO (móvil solicita cancelación) ────────
    if data.startswith("cancelar_servicio_"):
        service_id = data.split("_")[2]
        context.user_data["cancelando_servicio"] = service_id
        await query.edit_message_text("✍️ Escribe el motivo de la cancelación:")
        return

    # ── APROBAR PAGO (solo admin) ──────────────────────────────
    if data.startswith("APROBAR_PAGO|"):
        # Guard: solo admins pueden aprobar pagos aunque el botón llegue a otro usuario
        if not is_admin(user_id):
            await query.edit_message_text("🚫 No tienes permisos para esta acción.")
            return

        codigo  = data.split("|", 1)[1]
        mobiles = get_mobiles()
        target  = None
        for cid, m in mobiles.items():
            if m.get("codigo", "").upper() == codigo.upper():
                target = cid
                break
        if not target:
            await query.edit_message_text("No encontré ese móvil. Puede haber sido eliminado.")
            return

        mobiles[target]["pago_aprobado"] = True
        save_mobiles(mobiles)
        await query.edit_message_text(f"✅ El pago del móvil *{codigo}* ha sido aprobado.", parse_mode="Markdown")

        try:
            await bot.send_message(
                chat_id=int(target),
                text=(
                    "💰 Tu pago ha sido *aprobado*.\n\n"
                    "Ya puedes iniciar jornada y recibir servicios, incluso después de las 3:00 p.m."
                ),
                parse_mode="Markdown",
            )
        except Exception:
            pass

        context.user_data.pop("pending_payment_code", None)
        return

    # ── CANCELAR PAGO (solo admin) ────────────────────────────
    if data.startswith("CANCELAR_PAGO|"):
        if not is_admin(user_id):
            await query.edit_message_text("🚫 No tienes permisos para esta acción.")
            return
        await query.edit_message_text("Operación cancelada.")
        context.user_data.pop("pending_payment_code", None)
        return

    # ── INICIO DE REGISTRO DE MÓVIL (solo admin) ─────────────
    if data.startswith("REG_MOVIL|"):
        # Guard: solo admins pueden iniciar un registro desde el botón de notificación
        if not is_admin(user_id):
            await query.edit_message_text("🚫 No tienes permisos para esta acción.")
            return

        chat_id_movil_str = data.split("|", 1)[1].strip()
        context.user_data["mode"]       = "admin"
        context.user_data["admin_step"] = "reg_name"
        context.user_data["reg_movil"]  = {"chat_id": chat_id_movil_str}
        await query.edit_message_text(
            "📝 Vamos a registrar este móvil.\n\nEscribe el *nombre completo* del conductor:",
            parse_mode="Markdown",
        )
        return


# ============================================================
# 11. HANDLER - TEXTO (router principal)
# ============================================================

async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Router principal de mensajes de texto.
    Orden de evaluación:
      1. Acciones globales (Volver al inicio, Iniciar)
      2. Cancelación de servicio pendiente (móvil)
      3. Selección de rol (Cliente / Operador)
      4. Flujo según mode guardado en user_data
    """
    if not update.message:
        return

    text    = update.message.text.strip()
    user_id = update.effective_user.id

    # ── GLOBALES ──────────────────────────────────────────────
    if text == "⬅ Volver al inicio":
        context.user_data.clear()
        await start(update, context)
        return

    if text == "🚀 Iniciar":
        context.user_data.clear()
        await update.message.reply_text(
            "¿Cómo deseas continuar?",
            reply_markup=build_main_keyboard(),
        )
        return

    # ── CANCELACIÓN DE SERVICIO (flujo pendiente de móvil) ────
    if "cancelando_servicio" in context.user_data:
        service_id = context.user_data["cancelando_servicio"]
        motivo     = text
        services   = get_services()

        if service_id in services:
            servicio = services[service_id]
            servicio["motivo_cancelacion"] = motivo
            servicio["cancelado_por"]      = "movil"
            servicio["status"]             = "pendiente"
            servicio["movil_codigo"]       = None
            save_services(services)

            servicio_tipo = servicio.get("servicio")
            channel_id    = SERVICE_INFO.get(servicio_tipo, {}).get("channel_id")
            mensaje = (
                f"♻️ *SERVICIO LIBERADO*\n\n"
                f"📍 Destino: {servicio.get('destino','')}\n"
                f"👤 Cliente: {servicio.get('nombre','')}\n\n"
                f"⚠️ El móvil canceló este servicio.\n"
                f"Motivo: {motivo}"
            )
            if channel_id:
                try:
                    await context.bot.send_message(chat_id=channel_id, text=mensaje, parse_mode="Markdown")
                except Exception:
                    pass

        del context.user_data["cancelando_servicio"]
        await update.message.reply_text(
            "✅ Cancelación registrada. El servicio volvió a estar disponible.",
            reply_markup=build_movil_keyboard(),
        )
        return

    # ── SELECCIÓN DE ROL ──────────────────────────────────────
    if text == "👤 Cliente":
        await handle_cliente_option(update, context)
        return

    if text == "🚗 Operador":
        await handle_operador_option(update, context)
        return

    # ── FLUJO SEGÚN MODO ──────────────────────────────────────
    mode = context.user_data.get("mode")

    if not mode:
        await update.message.reply_text(
            "Para comenzar, usa /start o toca el botón 👇",
            reply_markup=build_start_keyboard(),
        )
        return

    # --- Autenticación del móvil ---
    if mode == "movil_auth":
        step = context.user_data.get("movil_step")
        if step == "ask_code":
            codigo_ingresado = text.upper()
            user_id_str      = str(user_id)
            mobiles          = get_mobiles()
            m = mobiles.get(user_id_str)

            if not m:
                await update.message.reply_text(
                    "❌ No estás registrado como móvil.\n"
                    "Comunícate con el administrador o usa /soy_movil para solicitar registro."
                )
                context.user_data.clear()
                await update.message.reply_text("Volviendo al inicio.", reply_markup=build_main_keyboard())
                return

            codigo_real = m.get("codigo", "").upper()
            if codigo_ingresado != codigo_real:
                await update.message.reply_text(
                    f"❌ El código no coincide.\n"
                    f"Código esperado para tu cuenta: *{codigo_real}*\n"
                    "Verifica e inténtalo de nuevo.",
                    parse_mode="Markdown",
                )
                return

            context.user_data["mode"]           = "movil"
            context.user_data["movil_codigo"]   = codigo_real
            context.user_data["movil_servicio"] = m.get("servicio", "Desconocido")

            await update.message.reply_text(
                f"✅ Bienvenido, móvil *{codigo_real}* ({m.get('servicio','')}).\n\nUsa el menú:",
                parse_mode="Markdown",
                reply_markup=build_movil_keyboard(),
            )
        return

    # --- Menú del móvil ---
    if mode == "movil":
        await handle_movil_menu(update, context, text)
        return

    # --- Panel de administración ---
    #
    # SEGURIDAD: aunque el mode="admin" esté en user_data,
    # handle_admin_menu() re-valida is_admin() antes de ejecutar cualquier acción.
    # Esto previene que alguien manipule su propio user_data para acceder al panel.
    if mode == "admin":
        await handle_admin_menu(update, context, text)
        return

    # --- Flujo del usuario/cliente ---
    if mode == "usuario":
        step = context.user_data.get("step")

        if step == "choose_service":
            for servicio, info in SERVICE_INFO.items():
                if text == info["label_user"]:
                    await handle_usuario_service_choice(update, context, servicio)
                    return
            await update.message.reply_text(
                "Por favor selecciona una opción del menú.",
                reply_markup=build_user_service_keyboard(),
            )
            return

        if step == "ask_name":
            context.user_data.setdefault("data", {})["nombre"] = text
            context.user_data["step"] = "ask_phone"
            await update.message.reply_text("📞 Escribe tu *número de teléfono*:", parse_mode="Markdown")
            return

        if step == "ask_phone":
            context.user_data["data"]["telefono"] = text
            context.user_data["step"] = "ask_location"
            await update.message.reply_text(
                "📍 Comparte tu ubicación GPS con el botón o escribe tu dirección actual:",
                reply_markup=build_location_keyboard(),
            )
            return

        if step == "ask_location":
            context.user_data["data"]["direccion_texto"] = text
            context.user_data["data"]["lat"] = None
            context.user_data["data"]["lon"] = None
            context.user_data["step"] = "ask_destination"
            await update.message.reply_text(
                "📍 Ahora escribe el *destino* a donde necesitas ir o enviar:",
                parse_mode="Markdown",
            )
            return

        if step == "ask_destination":
            context.user_data["data"]["destino"] = text
            servicio = context.user_data.get("servicio")
            if servicio == "Camionetas":
                context.user_data["step"] = "ask_carga"
                await update.message.reply_text(
                    "📦 ¿Qué tipo de carga necesitas transportar?\n(Ej: muebles, electrodomésticos, trasteo, etc.)"
                )
                return
            await finalize_user_request(update, context)
            return

        if step == "ask_carga":
            context.user_data["data"]["carga"] = text
            await finalize_user_request(update, context)
            return

    await update.message.reply_text(
        "No entiendo ese mensaje. Por favor usa el menú en pantalla.",
        reply_markup=build_main_keyboard(),
    )


# ============================================================
# 12. HANDLER - UBICACIÓN
# ============================================================

async def location_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Procesa ubicaciones GPS compartidas por clientes y móviles."""
    if not update.message or not update.message.location:
        return

    loc         = update.message.location
    user_id_str = str(update.effective_user.id)
    mode        = context.user_data.get("mode")
    step        = context.user_data.get("step")

    # Cliente compartiendo su ubicación de origen
    if mode == "usuario" and step == "ask_location":
        context.user_data["data"]["lat"]             = loc.latitude
        context.user_data["data"]["lon"]             = loc.longitude
        context.user_data["data"]["direccion_texto"] = None
        context.user_data["step"]                    = "ask_destination"
        await update.message.reply_text(
            "✅ Ubicación recibida.\n\nAhora escribe el *destino* a donde necesitas ir:",
            parse_mode="Markdown",
        )
        return

    # Móvil actualizando su ubicación en tiempo real
    mobiles = get_mobiles()
    if user_id_str in mobiles:
        m         = mobiles[user_id_str]
        m["lat"]  = loc.latitude
        m["lon"]  = loc.longitude
        mobiles[user_id_str] = m
        save_mobiles(mobiles)
        await update.message.reply_text(
            "✅ Ubicación registrada. PRONTO usará esta ubicación para asignarte servicios cercanos.",
            reply_markup=build_movil_keyboard(),
        )
        return

    await update.message.reply_text(
        "He recibido tu ubicación, pero no sé en qué contexto usarla.\n\n"
        "Si eres cliente, usa la opción '👤 Cliente'.\n"
        "Si eres móvil, pide al administrador que te registre."
    )


# ============================================================
# 13. MAIN
# ============================================================

def main():
    application = (
        ApplicationBuilder()
        .token(TOKEN)
        .concurrent_updates(False)
        .build()
    )

    # Comandos
    application.add_handler(CommandHandler("start",     start))
    application.add_handler(CommandHandler("admin",     cmd_admin))    # ← panel admin (solo admins)
    application.add_handler(CommandHandler("soy_movil", soy_movil_command))

    # Callbacks de botones inline
    application.add_handler(CallbackQueryHandler(button_callback))

    # Mensajes de ubicación GPS
    application.add_handler(MessageHandler(filters.LOCATION, location_handler))

    # Mensajes de texto
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))

    print("✅ Bot PRONTO iniciado correctamente.")
    application.run_polling(drop_pending_updates=True, allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
