import asyncio
import threading
from telegram.ext import Application, CommandHandler, MessageHandler, filters as Filters

from config import TELEGRAM_BOT_TOKEN
from func import (
    start, balance, lending, price_command, handle_coin_message, alert_command,
    run_scheduler
)

async def main():

    application = (
        Application.builder()
        .token(TELEGRAM_BOT_TOKEN)
        .build()
    )

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("balance", balance))
    application.add_handler(CommandHandler("lending", lending))
    application.add_handler(CommandHandler("price", price_command))
    application.add_handler(MessageHandler(Filters.TEXT & ~Filters.COMMAND, handle_coin_message))
    application.add_handler(CommandHandler("alert", alert_command))

    # 先初始化并启动 Telegram application，确保事件循环在运行后再启动 scheduler 线程
    await application.initialize()
    await application.start()
    await application.updater.start_polling()

    # 获取正在运行的事件循环并传入 scheduler 线程（避免 "no running event loop"）
    loop = asyncio.get_running_loop()
    scheduler_thread = threading.Thread(target=run_scheduler, args=(application, loop), daemon=True)
    scheduler_thread.start()

    print("机器人运行中...")
    await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.run(main())