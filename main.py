import logging
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
)

# ---------------------------
# CONFIG
# ---------------------------
TOKEN = "7668998247:AAGR7gxbJSfF-yuWtIOxMEFI1AYFinMJygg"

# ---------------------------
# LOGS
# ---------------------------
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)


# ---------------------------
# HANDLERS
# ---------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("PRONTO está activo ✔️")


# ---------------------------
# MAIN
# ---------------------------
def main():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))

    app.run_polling()   # Mantiene el bot vivo 24/7 en Railway


if __name__ == "__main__":
    main()
