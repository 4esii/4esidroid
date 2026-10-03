"""
A Telegram bot: parancskezelők + napi ütemezett automatikus elemzés és küldés.
"""
import logging

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from apscheduler.schedulers.asyncio import AsyncIOScheduler

import config
import analysis

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Szia! Ez a sportfogadás value-tipp botod. ⚽\n\n"
        "Parancsok:\n"
        "/today - azonnal lefuttatja az elemzést a következő meccsekre\n"
        "/leagues - a figyelt bajnokságok listája\n\n"
        f"Minden nap {config.DAILY_RUN_HOUR:02d}:{config.DAILY_RUN_MINUTE:02d}-kor "
        "(szerver idő szerint) automatikusan is elküldöm a napi value tippeket."
    )


async def leagues_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"Figyelt liga ID-k: {config.LEAGUE_IDS}")


async def today_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Elemzés indul, ez eltarthat egy percig...")
    try:
        tips, diag = analysis.run_analysis()
    except Exception as e:
        logger.exception("Hiba a /today elemzés futtatása közben")
        await update.message.reply_text(f"Hiba történt az elemzés közben: {e}")
        return

    if not tips:
        await update.message.reply_text("Nincs value tipp a mostani kritériumok alapján.")
    else:
        for tip in tips:
            await update.message.reply_text(tip, parse_mode="Markdown")

    # Mindig küldünk diagnosztikát is, hogy látszódjon hol "fogynak el" a meccsek
    await update.message.reply_text(analysis.format_diag_message(diag), parse_mode="Markdown")


async def scheduled_job(app: Application):
    logger.info("Napi ütemezett elemzés indul...")
    try:
        tips, diag = analysis.run_analysis()
        logger.info(f"Diagnosztika: {diag}")
    except Exception:
        logger.exception("Hiba a napi ütemezett elemzés futtatása közben")
        return

    if not tips:
        logger.info("Nincs value tipp ma.")
        return

    if not config.TELEGRAM_CHAT_ID:
        logger.warning("TELEGRAM_CHAT_ID nincs beállítva, nem tudom hova küldeni a tippet.")
        return

    for tip in tips:
        await app.bot.send_message(chat_id=config.TELEGRAM_CHAT_ID, text=tip, parse_mode="Markdown")


def build_app():
    if not config.TELEGRAM_BOT_TOKEN:
        raise RuntimeError("TELEGRAM_BOT_TOKEN nincs beállítva a .env fájlban!")

    app = Application.builder().token(config.TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("leagues", leagues_cmd))
    app.add_handler(CommandHandler("today", today_cmd))

    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        lambda: app.create_task(scheduled_job(app)),
        "cron", hour=config.DAILY_RUN_HOUR, minute=config.DAILY_RUN_MINUTE,
    )
    scheduler.start()
    return app


def main():
    app = build_app()
    logger.info("Bot elindult, polling...")
    app.run_polling()


if __name__ == "__main__":
    main()
# force redeploy 
