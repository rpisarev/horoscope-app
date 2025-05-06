from apscheduler.schedulers.blocking import BlockingScheduler
from datetime import date
from app import create_app
from app.services import SIGNS, generate_horoscope, save_forecast

app = create_app()
app.app_context().push()

scheduler = BlockingScheduler(timezone="Europe/Kyiv")

@scheduler.scheduled_job("cron", hour=1)
def nightly():
    today = date.today()
    for sign in SIGNS:
        text = generate_horoscope(sign, today)
        save_forecast(sign, today, text, model_version="stub")

if __name__ == "__main__":
    scheduler.start()
