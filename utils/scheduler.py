from apscheduler.schedulers.asyncio import AsyncIOScheduler

from utils.log import get_logger

logger = get_logger("bot")


def create_scheduler(client) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler()

    full_hour = client.config["polna_napoved_ob"]
    recap_hour = client.config["povzetek_napovedi_ob"]

    # polna napoved
    scheduler.add_job(
        client.send_weather, "cron", hour=full_hour, id="send_weather"
    )
    logger.info(
        f"[bot.cron]cron.send_weather[/bot.cron] "
        f"registered at hour={full_hour}"
    )

    # kratka napoved - zaenkrat isto
    scheduler.add_job(
        client.send_recap, "cron", hour=recap_hour, id="send_recap"
    )
    logger.info(
        f"[bot.cron]cron.send_recap[/bot.cron] registered at hour={recap_hour}"
    )

    return scheduler


def log_next_runs(scheduler: AsyncIOScheduler) -> None:
    for job in scheduler.get_jobs():
        nrt = job.next_run_time
        next_str = nrt.strftime("%Y-%m-%d %H:%M %Z") if nrt else "unknown"
        logger.info(
            f"[bot.cron]cron.{job.id}[/bot.cron] next run at "
            f"[bot.timing]{next_str}[/bot.timing]"
        )
