import logging
import asyncio
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

TOKEN = "7668998247:AAGR7gxbJSfF-yuWtIOxMEFI1AYFinMJygg"

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("PRONTO está activo ✔️")

# 🔥 tarea que mantiene vivo el bot
async def keep_alive():
    while True:
        await asyncio.sleep(60)   # cada 60 segundos
        print("KeepAlive → Bot activo ✔️")

def main():
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))

    # Ejecutar keep_alive en paralelo al polling
    app.create_task(keep_alive())

    app.run_polling()

if __name__ == "__main__":
    main()

