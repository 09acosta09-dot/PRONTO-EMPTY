"""
Bot PRONTO - Sistema de domicilios y servicios para Telegram
=============================================================
v2.0 - Refactorizado con claves internas para servicios.
Arquitectura modular en un solo archivo para Railway.

CAMBIOS PRINCIPALES v2.0:
  - SERVICIOS: estructura centralizada con clave interna (ej: "taxi", "domicilios").
    El sistema trabaja internamente con claves, nunca con nombres visibles.
  - SERVICE_INFO eliminado y reemplazado por SERVICIOS + helpers.
  - NOMBRE_A_CLAVE: mapa de compatibilidad para registros antiguos en JSON.
  - Registro de móviles: guarda la clave interna, no el nombre visible.
  - Cancelación: notifica al admin + redistribuye al canal correcto.
  - Comparaciones de servicio: siempre via clave interna.
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
import psycopg2
import psycopg2.extras

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

TOKEN = os.getenv("TU_TOKEN_NUEVO")
if not TOKEN:
    raise RuntimeError("La variable de entorno TU_TOKEN_NUEVO no está configurada.")

# ─── ESTRUCTURA CENTRALIZADA DE SERVICIOS ────────────────────
#
# REGLA DE ORO:
#   - Todo el código interno usa la CLAVE (ej: "taxi", "domicilios").
#   - "nombre" es SOLO para mostrar al usuario en pantalla.
#   - Si renombras un servicio, cambia solo "nombre" aquí. El resto no se toca.
#
# ─────────────────────────────────────────────────────────────
SERVICIOS = {
    "taxi": {
        "nombre":  "Taxi Servicio Especial",
        "emoji":   "🚕",
        "canal_id": -1002697357566,
        "link":    "https://t.me/+Drczf-TdHCUzNDZh",
        "prefijo": "SE",
    },
    "domicilios": {
        "nombre":  "Domicilios",
        "emoji":   "📦",
        "canal_id": -1002503403579,
        "link":    "https://t.me/+gZvnu8zolb1iOTBh",
        "prefijo": "D",
    },
    "camionetas": {
        "nombre":  "Camionetas",
        "emoji":   "🚚",
        "canal_id": -1002662309590,
        "link":    "https://t.me/+KRam-XSvPQ5jNjRh",
        "prefijo": "C",
    },
    "motocarro": {
        "nombre":  "Motocarros",
        "emoji":   "🛺",
        "canal_id": -1002688723492,
        "link":    "https://t.me/+REkbglMlfxE3YjI5",
        "prefijo": "M",
    },
}

# Mapa de compatibilidad: nombres viejos/variantes → clave interna
# Útil si hay registros antiguos en el JSON con el nombre visible guardado.
NOMBRE_A_CLAVE = {
    # Nombres anteriores del sistema
    "Taxi Servicio Especial": "taxi",
    "Servicio Especial":      "taxi",
    "taxi":                   "taxi",
    "Taxi":                   "taxi",
    "Domicilios":             "domicilios",
    "domicilios":             "domicilios",
    "Camionetas":             "camionetas",
    "camionetas":             "camionetas",
    "Motocarro":              "motocarro",
    "Motocarros":             "motocarro",
    "motocarro":              "motocarro",
}


def normalizar_servicio(valor: str) -> str | None:
    """
    Convierte cualquier nombre o clave de servicio a la clave interna estándar.
    Retorna None si no se reconoce.
    Permite cambiar nombres sin romper el sistema.
    """
    if valor in SERVICIOS:
        return valor
    return NOMBRE_A_CLAVE.get(valor)


def get_nombre(clave: str) -> str:
    """Retorna el nombre visible de un servicio dado su clave interna."""
    srv = SERVICIOS.get(clave)
    if not srv:
        return clave
    return f"{srv['emoji']} {srv['nombre']}"


def get_nombre_corto(clave: str) -> str:
    """Retorna solo el nombre (sin emoji) de un servicio dado su clave."""
    srv = SERVICIOS.get(clave)
    if not srv:
        return clave
    return srv["nombre"]


def get_canal(clave: str) -> int | None:
    """Retorna el canal_id de un servicio dado su clave interna."""
    srv = SERVICIOS.get(clave)
    return srv["canal_id"] if srv else None


def get_link(clave: str) -> str | None:
    """Retorna el link de invitación de un servicio dado su clave interna."""
    srv = SERVICIOS.get(clave)
    return srv.get("link") if srv else None


def get_prefijo(clave: str) -> str:
    """Retorna el prefijo de código de un servicio (ej: 'SE', 'D')."""
    srv = SERVICIOS.get(clave)
    return srv["prefijo"] if srv else "X"


# Canal de backups
BACKUP_CHANNEL_ID = int(os.getenv("BACKUP_CHANNEL_ID", "0"))

# Nequi
NEQUI_NUMBER = "3052915231"

# ============================================================
# BASE DE DATOS POSTGRESQL
# ============================================================

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("La variable de entorno DATABASE_URL no está configurada.")


def get_db():
    """Abre una conexión nueva a PostgreSQL. Ciérrala al terminar."""
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = True
    return conn


def init_db():
    """Crea las tablas si no existen."""
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS mobiles (
            user_id TEXT PRIMARY KEY,
            codigo TEXT,
            servicio TEXT,
            lat DOUBLE PRECISION,
            lon DOUBLE PRECISION,
            activo BOOLEAN DEFAULT true,
            nombre TEXT,
            cedula TEXT,
            placa TEXT,
            marca TEXT,
            modelo TEXT,
            pago_aprobado BOOLEAN DEFAULT false
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS services (
            service_id TEXT PRIMARY KEY,
            data JSONB
        )
    """)
    cur.close()
    conn.close()
    print("[DB] Tablas verificadas correctamente.")

# Webhook Railway
WEBHOOK_DOMAIN = "https://pronto-empty-production.up.railway.app"
WEBHOOK_PATH   = f"/webhook/{TOKEN}"
WEBHOOK_URL    = WEBHOOK_DOMAIN + WEBHOOK_PATH

# Zona horaria Colombia
TZ_CO = ZoneInfo("America/Bogota")
CORTE = time(15, 0)  # 3:00 p.m.

# ============================================================
# 3. SEGURIDAD / ROLES
# ============================================================

ADMIN_IDS = [1741298723, 7076796229]  # ← user_id de los admins


def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


async def deny_admin_access(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text(
        "🚫 No tienes permisos para acceder a este menú.\n\n"
        "Si crees que esto es un error, comunícate con el administrador.",
        reply_markup=build_main_keyboard(),
    )


# ============================================================
# 4. UTILIDADES
# ============================================================

# --- Base de datos ---

def get_mobiles() -> dict:
    """Lee todos los móviles desde PostgreSQL y los retorna como dict {user_id: datos}."""
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT * FROM mobiles")
    rows = cur.fetchall()
    cur.close()
    conn.close()
    result = {}
    for row in rows:
        uid = row["user_id"]
        result[uid] = {
            "codigo":        row["codigo"],
            "servicio":      row["servicio"],
            "lat":           row["lat"],
            "lon":           row["lon"],
            "activo":        row["activo"],
            "nombre":        row["nombre"],
            "cedula":        row["cedula"],
            "placa":         row["placa"],
            "marca":         row["marca"],
            "modelo":        row["modelo"],
            "pago_aprobado": row["pago_aprobado"],
        }
    return result


def save_mobiles(data: dict):
    """Guarda el dict completo de móviles en PostgreSQL (upsert por user_id)."""
    conn = get_db()
    cur = conn.cursor()
    for user_id, m in data.items():
        cur.execute("""
            INSERT INTO mobiles (user_id, codigo, servicio, lat, lon, activo, nombre, cedula, placa, marca, modelo, pago_aprobado)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (user_id) DO UPDATE SET
                codigo        = EXCLUDED.codigo,
                servicio      = EXCLUDED.servicio,
                lat           = EXCLUDED.lat,
                lon           = EXCLUDED.lon,
                activo        = EXCLUDED.activo,
                nombre        = EXCLUDED.nombre,
                cedula        = EXCLUDED.cedula,
                placa         = EXCLUDED.placa,
                marca         = EXCLUDED.marca,
                modelo        = EXCLUDED.modelo,
                pago_aprobado = EXCLUDED.pago_aprobado
        """, (
            user_id,
            m.get("codigo"),
            m.get("servicio"),
            m.get("lat"),
            m.get("lon"),
            m.get("activo", True),
            m.get("nombre"),
            m.get("cedula"),
            m.get("placa"),
            m.get("marca"),
            m.get("modelo"),
            m.get("pago_aprobado", False),
        ))
    cur.close()
    conn.close()


def delete_mobile(user_id: str):
    """Elimina un móvil de PostgreSQL por su user_id."""
    conn = get_db()
    cur = conn.cursor()
    cur.execute("DELETE FROM mobiles WHERE user_id = %s", (user_id,))
    cur.close()
    conn.close()


def get_services() -> dict:
    """Lee todos los servicios desde PostgreSQL."""
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT service_id, data FROM services")
    rows = cur.fetchall()
    cur.close()
    conn.close()
    result = {}
    for row in rows:
        result[row["service_id"]] = row["data"]
    return result


def save_services(data: dict):
    """Guarda el dict completo de servicios en PostgreSQL (upsert)."""
    conn = get_db()
    cur = conn.cursor()
    for service_id, sdata in data.items():
        cur.execute("""
            INSERT INTO services (service_id, data)
            VALUES (%s, %s)
            ON CONFLICT (service_id) DO UPDATE SET data = EXCLUDED.data
        """, (service_id, json.dumps(sdata, ensure_ascii=False)))
    cur.close()
    conn.close()


async def backup_file(context, filename: str):
    # Esta función ya no aplica con PostgreSQL
    pass


# --- Tiempo ---

def now_colombia() -> datetime:
    return datetime.now(TZ_CO)


def now_colombia_str() -> str:
    return now_colombia().strftime("%Y-%m-%d %I:%M %p")


def after_cutoff() -> bool:
    return now_colombia().time() >= CORTE


def mobile_can_work(mobile: dict) -> tuple[bool, str]:
    if after_cutoff() and not mobile.get("pago_aprobado", False):
        return False, (
            "Ya pasó la hora de corte (3:00 p.m.).\n"
            "Para trabajar después de las 3:00 p.m. debes realizar el pago "
            "y esperar la aprobación del administrador."
        )
    return True, ""


# --- Distancia ---

def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi    = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def seleccionar_movil_mas_cercano(clave_servicio: str, lat_cliente, lon_cliente) -> dict | None:
    """
    Busca el móvil activo disponible más cercano al cliente para la clave de servicio dada.
    Trabaja siempre con claves internas. Los registros antiguos son normalizados al vuelo.
    """
    mobiles    = get_mobiles()
    candidatos = []

    for chat_id_str, m in mobiles.items():
        if not m.get("activo"):
            continue

        # Normalizar el servicio guardado en el registro (compatibilidad con datos viejos)
        clave_movil = normalizar_servicio(m.get("servicio", ""))
        if clave_movil != clave_servicio:
            continue

        puede, _ = mobile_can_work(m)
        if not puede:
            continue

        m_lat = m.get("lat")
        m_lon = m.get("lon")

        if all(x is not None for x in [m_lat, m_lon, lat_cliente, lon_cliente]):
            dist = haversine_distance(lat_cliente, lon_cliente, m_lat, m_lon)
        else:
            dist = float("inf")

        candidatos.append({
            "chat_id":  int(chat_id_str),
            "codigo":   m.get("codigo"),
            "servicio": clave_servicio,  # siempre clave interna
            "distancia": dist,
        })

    if not candidatos:
        return None

    candidatos.sort(key=lambda x: x["distancia"])
    dist_min  = candidatos[0]["distancia"]
    empatados = [c for c in candidatos if c["distancia"] == dist_min]
    return random.choice(empatados)


def asignar_codigo_movil(clave_servicio: str) -> str:
    """
    Genera el siguiente código correlativo para un móvil (ej: D003, SE007).
    Trabaja con la clave interna del servicio.
    """
    mobiles = get_mobiles()
    prefijo = get_prefijo(clave_servicio)
    numeros = []
    for m in mobiles.values():
        codigo = m.get("codigo", "")
        if codigo.startswith(prefijo):
            try:
                numeros.append(int(codigo[len(prefijo):]))
            except ValueError:
                continue
    next_num = max(numeros) + 1 if numeros else 1
    return f"{prefijo}{next_num:03d}"


# ============================================================
# 5. TECLADOS / MENÚS
# ============================================================

def build_start_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup([[KeyboardButton("🚀 Iniciar")]], resize_keyboard=True)


def build_main_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton("👤 Cliente")],
            [KeyboardButton("🚗 Movil")],
        ],
        resize_keyboard=True,
    )


def build_admin_keyboard() -> ReplyKeyboardMarkup:
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
    """
    Construye el menú de servicios para el cliente dinámicamente desde SERVICIOS.
    Si se cambia un nombre en SERVICIOS, el menú se actualiza solo.
    """
    botones = []
    for clave, info in SERVICIOS.items():
        botones.append([KeyboardButton(f"{info['emoji']} {info['nombre']}")])
    botones.append([KeyboardButton("⬅ Volver al inicio")])
    return ReplyKeyboardMarkup(botones, resize_keyboard=True)


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
            [KeyboardButton("📍 Compartir ubicación GPS (opcional)", request_location=True)],
            [KeyboardButton("⬅ Volver al inicio")],
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def build_registro_servicio_keyboard() -> ReplyKeyboardMarkup:
    """
    Teclado para que el admin elija el servicio al registrar un móvil.
    Generado dinámicamente desde SERVICIOS para que siempre esté sincronizado.
    """
    botones = []
    for clave, info in SERVICIOS.items():
        botones.append([KeyboardButton(f"{info['emoji']} {info['nombre']}")])
    return ReplyKeyboardMarkup(botones, resize_keyboard=True, one_time_keyboard=True)


# ============================================================
# 6. HANDLERS - /start y /soy_movil
# ============================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text(
        "👋 Bienvenido a *PRONTO*\n\n¿Cómo deseas continuar?",
        parse_mode="Markdown",
        reply_markup=build_main_keyboard(),
    )


async def cmd_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_admin(user_id):
        await deny_admin_access(update, context)
        return

    context.user_data.clear()
    context.user_data["mode"]       = "admin"
    context.user_data["admin_step"] = None

    await update.message.reply_text(
        "👮 Panel de administración\n\nElige una opción:",
        reply_markup=build_admin_keyboard(),
    )


async def soy_movil_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
    context.user_data["mode"] = "usuario"
    context.user_data["step"] = "choose_service"
    await update.message.reply_text(
        "Selecciona el tipo de servicio que necesitas:",
        reply_markup=build_user_service_keyboard(),
    )


async def handle_usuario_service_choice(update: Update, context: ContextTypes.DEFAULT_TYPE, clave_servicio: str):
    """
    El cliente eligió un servicio. Guarda la CLAVE INTERNA, no el nombre.
    """
    context.user_data["mode"]     = "usuario"
    context.user_data["step"]     = "ask_name"
    context.user_data["servicio"] = clave_servicio  # ← siempre clave interna
    context.user_data["data"]     = {}
    await update.message.reply_text(
        "📝 Por favor escribe tu *nombre completo*:",
        parse_mode="Markdown",
    )


async def finalize_user_request(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Completa la solicitud del usuario:
    - Genera ID de servicio único.
    - Busca el móvil más cercano usando clave interna.
    - Notifica al móvil y publica en el canal correspondiente.
    """
    user    = update.effective_user
    chat_id = update.effective_chat.id
    data    = context.user_data.get("data", {})
    clave_servicio = context.user_data.get("servicio")  # clave interna

    if not clave_servicio or clave_servicio not in SERVICIOS:
        await update.message.reply_text("Ocurrió un problema con el servicio. Intenta de nuevo.")
        return

    if not data:
        await update.message.reply_text("Ocurrió un problema. Intenta de nuevo.")
        return

    hora         = now_colombia_str()
    nombre_srv   = get_nombre_corto(clave_servicio)

    data["hora"]         = hora
    data["servicio"]     = clave_servicio      # ← clave interna en el registro
    data["user_chat_id"] = chat_id
    data["user_id"]      = user.id

    # Generar ID único de servicio
    services = get_services()
    nums = []
    for sid in services:
        if isinstance(sid, str) and sid.startswith("S"):
            try:
                nums.append(int(sid[1:]))
            except ValueError:
                pass
    service_id = f"S{(max(nums) + 1 if nums else 1):05d}"

    data["id"]            = service_id
    data["status"]        = "pendiente"
    data["movil_codigo"]  = None
    data["movil_chat_id"] = None

    # Buscar móvil más cercano (con clave interna)
    movil_info = seleccionar_movil_mas_cercano(clave_servicio, data.get("lat"), data.get("lon"))
    if movil_info is None:
        await update.message.reply_text(
            "😔 En este momento no hay móviles disponibles para este servicio.\n"
            "Por favor intenta en unos minutos."
        )
        return

    movil_chat_id = movil_info["chat_id"]
    movil_codigo  = movil_info["codigo"]

    data["movil_codigo"]  = movil_codigo
    data["movil_chat_id"] = movil_chat_id
    services[service_id]  = data
    save_services(services)

    await update.message.reply_text(
        "✅ Tu solicitud ha sido registrada.\n"
        "Estamos notificando a un móvil cercano para que tome tu servicio."
    )

    # Mensaje al móvil
    texto_movil  = f"🚨 *Nuevo servicio de {nombre_srv}*\n\n"
    texto_movil += f"🆔 Código de servicio: *{service_id}*\n"
    texto_movil += f"👤 Cliente: *{data.get('nombre', '(sin nombre)')}*\n"
    texto_movil += f"📞 Teléfono cliente: *{data.get('telefono', '(sin teléfono)')}*\n"
    texto_movil += f"📍 Destino: *{data.get('destino', '(sin destino)')}*\n"
    if clave_servicio == "camionetas":
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

    # Publicar resumen en el canal del servicio
    canal_id = get_canal(clave_servicio)
    resumen_canal = (
        f"📢 *Nuevo servicio de {nombre_srv}*\n"
        f"🆔 Servicio: *{service_id}*\n"
        f"👤 Cliente: *{data.get('nombre','')}*\n"
        f"📞 Tel: *{data.get('telefono','')}*\n"
        f"📍 Destino: *{data.get('destino','')}*\n"
        f"🕒 Hora: *{hora}* (Colombia)\n"
        f"🚗 Móvil asignado: *{movil_codigo}* (en espera de reserva)"
    )
    if canal_id:
        try:
            await context.bot.send_message(chat_id=canal_id, text=resumen_canal, parse_mode="Markdown")
        except Exception:
            pass

    context.user_data.clear()


# ============================================================
# 8. HANDLERS - MÓVIL (gestión de jornada)
# ============================================================

async def handle_operador_option(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    context.user_data["mode"]       = "movil_auth"
    context.user_data["movil_step"] = "ask_code"
    await update.message.reply_text(
        "🔐 Escribe tu *código de móvil* (ej: SE001, D005, C010, M003):",
        parse_mode="Markdown",
    )


async def handle_movil_menu(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str):
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

    codigo         = m.get("codigo", "SIN-CODIGO")
    clave_servicio = normalizar_servicio(m.get("servicio", ""))  # normalizar por si es registro viejo
    nombre_srv     = get_nombre_corto(clave_servicio) if clave_servicio else "Desconocido"

    if text == "🚀 Iniciar jornada":
        puede, msg = mobile_can_work(m)
        if not puede:
            await update.message.reply_text("⛔ " + msg, reply_markup=build_movil_keyboard())
            return
        m["activo"] = True
        # Actualizar clave normalizada en el registro si era nombre viejo
        if clave_servicio:
            m["servicio"] = clave_servicio
        mobiles[user_id_str] = m
        save_mobiles(mobiles)
        link    = get_link(clave_servicio) if clave_servicio else None
        mensaje = f"✅ Jornada iniciada para el móvil *{codigo}* ({nombre_srv}).\n\n"
        if link:
            mensaje += f"Para ver servicios de *{nombre_srv}*, entra al canal:\n{link}"
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
    user_id    = update.effective_user.id
    admin_step = context.user_data.get("admin_step")

    if not is_admin(user_id):
        await deny_admin_access(update, context)
        return

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
            activo  = "✅ Activo" if m.get("activo") else "⛔ Inactivo"
            pago    = "💰 Pago OK" if m.get("pago_aprobado") else "💸 Pendiente"
            clave   = normalizar_servicio(m.get("servicio", "")) or m.get("servicio", "?")
            nombre  = get_nombre_corto(clave) if clave in SERVICIOS else clave
            lines.append(
                f"• {m.get('codigo','?')} – {m.get('nombre','Sin nombre')} "
                f"– {nombre} – {activo} – {pago}"
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
            clave   = normalizar_servicio(s.get("servicio", "")) or s.get("servicio", "?")
            nombre  = get_nombre_corto(clave) if clave in SERVICIOS else clave
            lines.append(
                f"• {s.get('id','')} – {nombre} – {s.get('nombre','')} "
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

        # Construir lista de servicios disponibles desde SERVICIOS (no hardcodeada)
        opciones = "\n".join(f"  • {info['emoji']} {info['nombre']}" for info in SERVICIOS.values())
        await update.message.reply_text(
            f"🚗 Indica el *tipo de servicio*:\n{opciones}\n\n"
            "Escríbelo exactamente como aparece arriba.",
            parse_mode="Markdown",
        )
        return

    if admin_step == "reg_service":
        clave_ingresada = normalizar_servicio(text.strip())
        if not clave_ingresada:
            opciones = ", ".join(info["nombre"] for info in SERVICIOS.values())
            await update.message.reply_text(
                f"❌ Servicio no válido. Opciones disponibles:\n{opciones}"
            )
            return
        # Guardar la CLAVE INTERNA, nunca el nombre visible
        context.user_data["reg_movil"]["servicio"] = clave_ingresada
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
            await _finalizar_registro_movil(update, context, reg, int(reg["chat_id"]))
        else:
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
        delete_mobile(target)
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
        target      = None
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
        clave = normalizar_servicio(target_data.get("servicio", "")) or "?"
        nombre_srv = get_nombre_corto(clave) if clave in SERVICIOS else clave
        texto = (
            "📋 *Información del móvil:*\n\n"
            f"🔢 Código: *{codigo}*\n"
            f"👤 Nombre: *{target_data.get('nombre','?')}*\n"
            f"🧾 Cédula: *{target_data.get('cedula','?')}*\n"
            f"🚗 Servicio: *{nombre_srv}*\n"
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

    await update.message.reply_text("Usa las opciones del menú de administrador.", reply_markup=build_admin_keyboard())


async def _finalizar_registro_movil(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    reg: dict,
    chat_id_movil: int,
):
    """
    Guarda el registro completo del móvil.
    Siempre guarda la CLAVE INTERNA del servicio (nunca el nombre visible).
    """
    clave_servicio = reg.get("servicio")  # ya viene como clave interna desde reg_service

    # Validación extra: si por algún motivo vino como nombre, normalizamos
    clave_servicio = normalizar_servicio(clave_servicio) if clave_servicio else None

    if not clave_servicio:
        await update.message.reply_text("❌ Error interno: servicio no definido. Intenta de nuevo.")
        context.user_data["admin_step"] = None
        return

    codigo  = asignar_codigo_movil(clave_servicio)
    mobiles = get_mobiles()
    mobiles[str(chat_id_movil)] = {
        "codigo":        codigo,
        "servicio":      clave_servicio,   # ← SIEMPRE clave interna
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

    nombre_srv = get_nombre_corto(clave_servicio)
    await update.message.reply_text(
        f"✅ Móvil registrado correctamente.\n\n"
        f"Conductor: *{reg.get('nombre', '')}*\n"
        f"Servicio: *{nombre_srv}*\n"
        f"Código asignado: *{codigo}*\n\n"
        "El conductor debe entrar al bot, elegir '🚗 Operador' y autenticarse con este código.",
        parse_mode="Markdown",
    )


# ============================================================
# 10. HANDLER - CALLBACKS (inline buttons)
# ============================================================

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
        service_id = data.split("_", 3)[2]
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
        service_id    = data.split("|", 1)[1]
        movil_chat_id = query.message.chat.id
        mobiles       = get_mobiles()
        mobile        = mobiles.get(str(movil_chat_id))

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

        services      = get_services()
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

        movil_codigo   = servicio_data.get("movil_codigo")
        clave_servicio = normalizar_servicio(servicio_data.get("servicio", "")) or ""
        nombre_srv     = get_nombre_corto(clave_servicio) if clave_servicio else "?"

        texto_reserva  = (
            f"✅ Has *reservado* el servicio {service_id}.\n\n"
            f"👤 {servicio_data.get('nombre', '')}\n"
            f"📞 Teléfono: *{servicio_data.get('telefono', '')}*\n"
            f"📍 Destino: {servicio_data.get('destino', '')}\n"
        )
        if clave_servicio == "camionetas":
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

        # Publicar en canal
        canal_id = get_canal(clave_servicio)
        resumen = (
            f"✅ *Servicio reservado*\n"
            f"🆔 Servicio: *{service_id}*\n"
            f"🚗 Móvil: *{movil_codigo}*\n"
            f"👤 Cliente: *{servicio_data.get('nombre','')}*\n"
            f"📞 Tel: *{servicio_data.get('telefono','')}*\n"
            f"📍 Destino: *{servicio_data.get('destino','')}*\n"
            f"⏰ Hora reserva: *{servicio_data.get('hora_reserva','')}* (Colombia)"
        )
        if canal_id:
            try:
                await bot.send_message(chat_id=canal_id, text=resumen, parse_mode="Markdown")
            except Exception:
                pass
        return

    # ── CANCELAR SERVICIO (móvil solicita cancelación) ────────
    if data.startswith("cancelar_servicio_"):
        parts      = data.split("_")
        service_id = parts[-1]
        context.user_data["cancelando_servicio"] = service_id
        await query.edit_message_text("✍️ Escribe el motivo de la cancelación:")
        return

    # ── APROBAR PAGO (solo admin) ──────────────────────────────
    if data.startswith("APROBAR_PAGO|"):
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
            servicio_data = services[service_id]

            # Normalizar clave del servicio (compatibilidad con registros viejos)
            clave_servicio = normalizar_servicio(servicio_data.get("servicio", ""))
            canal_id       = get_canal(clave_servicio) if clave_servicio else None
            nombre_srv     = get_nombre_corto(clave_servicio) if clave_servicio else "?"
            movil_cancelador = servicio_data.get("movil_codigo", "desconocido")

            # Resetear estado del servicio a pendiente
            servicio_data["motivo_cancelacion"] = motivo
            servicio_data["cancelado_por"]      = "movil"
            servicio_data["status"]             = "pendiente"
            servicio_data["movil_codigo"]       = None
            servicio_data["movil_chat_id"]      = None
            save_services(services)

            # 1) Notificar a todos los admins
            texto_admin = (
                f"⚠️ *Cancelación de servicio*\n\n"
                f"🆔 Servicio: *{service_id}*\n"
                f"🚗 Móvil que canceló: *{movil_cancelador}*\n"
                f"📍 Destino: {servicio_data.get('destino','')}\n"
                f"👤 Cliente: {servicio_data.get('nombre','')}\n"
                f"❌ Motivo: {motivo}\n\n"
                "El servicio fue vuelto a estado *disponible* y republicado en el canal."
            )
            for admin_id in ADMIN_IDS:
                try:
                    await context.bot.send_message(
                        chat_id=admin_id,
                        text=texto_admin,
                        parse_mode="Markdown",
                    )
                except Exception:
                    pass

            # 2) Republicar en el canal como servicio disponible nuevamente
            hora_actual = now_colombia_str()
            texto_canal = (
                f"🚨 *SERVICIO DISPONIBLE NUEVAMENTE* 🚨\n\n"
                f"🆔 Servicio: *{service_id}*\n"
                f"🚗 Tipo: *{nombre_srv}*\n"
                f"👤 Cliente: {servicio_data.get('nombre','')}\n"
                f"📞 Tel: {servicio_data.get('telefono','')}\n"
                f"📍 Destino: {servicio_data.get('destino','')}\n"
                f"🕒 Hora: *{hora_actual}* (Colombia)\n\n"
                "⚠️ El móvil anterior canceló. Este servicio necesita un nuevo operador."
            )
            if canal_id:
                try:
                    await context.bot.send_message(
                        chat_id=canal_id,
                        text=texto_canal,
                        parse_mode="Markdown",
                    )
                except Exception:
                    pass

            # 3) Intentar reasignar automáticamente a otro móvil
            lat_cliente = servicio_data.get("lat")
            lon_cliente = servicio_data.get("lon")
            nuevo_movil = seleccionar_movil_mas_cercano(clave_servicio, lat_cliente, lon_cliente) if clave_servicio else None

            if nuevo_movil:
                nuevo_chat_id = nuevo_movil["chat_id"]
                nuevo_codigo  = nuevo_movil["codigo"]
                servicio_data["movil_codigo"]  = nuevo_codigo
                servicio_data["movil_chat_id"] = nuevo_chat_id
                servicio_data["status"]        = "pendiente"
                save_services(services)

                hora_reasig = now_colombia_str()
                texto_movil  = f"🚨 *Nuevo servicio de {nombre_srv}*\n\n"
                texto_movil += f"🆔 Código de servicio: *{service_id}*\n"
                texto_movil += f"👤 Cliente: *{servicio_data.get('nombre', '(sin nombre)')}*\n"
                texto_movil += f"📞 Teléfono cliente: *{servicio_data.get('telefono', '(sin teléfono)')}*\n"
                texto_movil += f"📍 Destino: *{servicio_data.get('destino', '(sin destino)')}*\n"
                if clave_servicio == "camionetas":
                    texto_movil += f"📦 Tipo de carga: *{servicio_data.get('carga', '(no especificada)')}*\n"
                texto_movil += f"\n⏰ Hora: *{hora_reasig}* (Colombia)\n\nPresiona el botón para tomar el servicio."

                keyboard = InlineKeyboardMarkup(
                    [[InlineKeyboardButton("🚨🔴 RESERVAR SERVICIO 🔴🚨", callback_data=f"RESERVAR|{service_id}")]]
                )
                try:
                    await context.bot.send_message(
                        chat_id=nuevo_chat_id,
                        text=texto_movil,
                        reply_markup=keyboard,
                        parse_mode="Markdown",
                    )
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

    if text in ("🚗 Movil", "🚗 Operador"):
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

            # Normalizar servicio en el registro al autenticar
            clave = normalizar_servicio(m.get("servicio", ""))
            if clave and m.get("servicio") != clave:
                m["servicio"] = clave
                mobiles[user_id_str] = m
                save_mobiles(mobiles)

            context.user_data["mode"]           = "movil"
            context.user_data["movil_codigo"]   = codigo_real
            context.user_data["movil_servicio"] = clave or m.get("servicio", "")

            nombre_srv = get_nombre_corto(clave) if clave else m.get("servicio", "")
            await update.message.reply_text(
                f"✅ Bienvenido, móvil *{codigo_real}* ({nombre_srv}).\n\nUsa el menú:",
                parse_mode="Markdown",
                reply_markup=build_movil_keyboard(),
            )
        return

    # --- Menú del móvil ---
    if mode == "movil":
        await handle_movil_menu(update, context, text)
        return

    # --- Panel de administración ---
    if mode == "admin":
        await handle_admin_menu(update, context, text)
        return

    # --- Flujo del usuario/cliente ---
    if mode == "usuario":
        step = context.user_data.get("step")

        if step == "choose_service":
            # Detectar servicio por texto del botón usando SERVICIOS dinámicamente
            clave_encontrada = None
            for clave, info in SERVICIOS.items():
                label = f"{info['emoji']} {info['nombre']}"
                if text == label:
                    clave_encontrada = clave
                    break
            if clave_encontrada:
                await handle_usuario_service_choice(update, context, clave_encontrada)
            else:
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
            context.user_data["step"] = "ask_location_gps"
            await update.message.reply_text(
                "📍 Si deseas, comparte tu *ubicación GPS* para mayor precisión (es opcional).\n\n"
                "Usa el botón de abajo o simplemente escribe tu *dirección* en el siguiente paso.",
                parse_mode="Markdown",
                reply_markup=build_location_keyboard(),
            )
            return

        if step == "ask_location_gps":
            # El cliente escribió texto en vez de compartir GPS — lo ignoramos y pedimos dirección
            context.user_data["data"]["lat"] = None
            context.user_data["data"]["lon"] = None
            context.user_data["step"] = "ask_location_text"
            await update.message.reply_text(
                "📝 Escribe tu *dirección de recogida* (barrio, calle, punto de referencia):",
                parse_mode="Markdown",
            )
            return

        if step == "ask_location_text":
            context.user_data["data"]["direccion_texto"] = text
            context.user_data["step"] = "ask_destination"
            await update.message.reply_text(
                "📍 Ahora escribe el *destino* a donde necesitas ir o enviar:",
                parse_mode="Markdown",
            )
            return

        if step == "ask_destination":
            context.user_data["data"]["destino"] = text
            clave_servicio = context.user_data.get("servicio")
            if clave_servicio == "camionetas":
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
    if not update.message or not update.message.location:
        return

    loc         = update.message.location
    user_id_str = str(update.effective_user.id)
    mode        = context.user_data.get("mode")
    step        = context.user_data.get("step")

    # Cliente compartiendo su ubicación de origen
    if mode == "usuario" and step in ("ask_location_gps", "ask_location"):
        context.user_data["data"]["lat"]  = loc.latitude
        context.user_data["data"]["lon"]  = loc.longitude
        context.user_data["step"]         = "ask_location_text"
        await update.message.reply_text(
            "✅ Ubicación GPS recibida.\n\n"
            "📝 Ahora escribe tu *dirección de recogida* (barrio, calle, punto de referencia):",
            parse_mode="Markdown",
        )
        return

    # Móvil actualizando su ubicación
    mobiles = get_mobiles()
    if user_id_str in mobiles:
        m        = mobiles[user_id_str]
        m["lat"] = loc.latitude
        m["lon"] = loc.longitude
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
async def cmd_exportar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    try:
        mobiles = get_mobiles()
        contenido = json.dumps(mobiles, ensure_ascii=False, indent=2)
        await update.message.reply_document(
            document=contenido.encode("utf-8"),
            filename="mobiles_backup.json",
            caption="✅ Backup de móviles registrados (desde PostgreSQL)"
        )
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")

def main():
    init_db()  # Verificar/crear tablas al arrancar
    application = (
        ApplicationBuilder()
        .token(TOKEN)
        .concurrent_updates(False)
        .build()
    )

    application.add_handler(CommandHandler("start",     start))
    application.add_handler(CommandHandler("admin",     cmd_admin))
    application.add_handler(CommandHandler("soy_movil", soy_movil_command))
    application.add_handler(CommandHandler("exportar", cmd_exportar))

    application.add_handler(CallbackQueryHandler(button_callback))
    application.add_handler(MessageHandler(filters.LOCATION, location_handler))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))

    print("✅ Bot PRONTO v2.0 iniciado correctamente.")
    application.run_polling(drop_pending_updates=True, allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
