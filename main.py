import logging
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters

# ----------------------
# CONFIGURACIÓN
# ----------------------
TOKEN = "7668998247:AAGR7gxbJ5FF-yuWtIOxMEFl1AYFinMJygg"

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)

# ----------------------
# MENÚ PRINCIPAL
# ----------------------
menu_principal = ReplyKeyboardMarkup(
    [
        ["Usuario", "Móvil", "Administrador"]
    ],
    resize_keyboard=True
)

# ----------------------
# COMANDO START
# ----------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Bienvenido a PRONTO 🚀\nSelecciona una opción:",
        reply_markup=menu_principal
    )

# ----------------------
# MANEJO DE MENÚ
# ----------------------
async def mensaje(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texto = update.message.text

    if texto == "Usuario":
        await update.message.reply_text("Eres un *Usuario*. ¿Qué deseas hacer?", parse_mode="Markdown")

    elif texto == "Móvil":
        await update.message.reply_text("Eres un *Móvil*. Aquí pronto pondremos el menú de operadores.", parse_mode="Markdown")

    elif texto == "Administrador":
        await update.message.reply_text("Eres un *Administrador*. Opciones administrativas disponibles pronto.")

    else:
        await update.message.reply_text("No entiendo eso 🤔\nPor favor usa el menú.")

# ----------------------
# APP PRINCIPAL (Railway Worker)
# ----------------------
async def main():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT, mensaje))

    print("PRONTO está activo en Railway... 🚀")
    await app.run_polling()


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
