import requests
from Settings import TOKEN
from viberbot import Api
from viberbot.api.bot_configuration import BotConfiguration
from viberbot.api.messages import TextMessage
from main import Session, Users
import datetime

bot_configuration = BotConfiguration(
    name='LearnEnglishBot',
    avatar='http://viber.com/avatar.jpg',
    auth_token=TOKEN
)
viber = Api(bot_configuration)

# стартовая клавиатура
KEYBOARD = {
    "Type": "keyboard",
    "Buttons": [
        {
            "Columns": 6,
            "Rows": 1,
            "BgColor": "#e6f5ff",
            "BgMedia": "http://link.to.button.image",
            "BgMediaType": "picture",
            "BgLoop": True,
            "ActionType": "reply",
            "ActionBody": "Старт",
            "ReplyType": "message",
            "Text": "Старт"
        }, {
            "Columns": 6,
            "Rows": 1,
            "BgColor": "#e6f5ff",
            "BgMedia": "http://link.to.button.image",
            "BgMediaType": "picture",
            "BgLoop": True,
            "ActionType": "reply",
            "ActionBody": "Напомнить позже",
            "ReplyType": "message",
            "Text": "Напомнить позже"
        }
    ]
}

# словарь пользователя и его времени последнего оповещения
user_alert = {}

from apscheduler.schedulers.blocking import BlockingScheduler

sched = BlockingScheduler()


@sched.scheduled_job('interval', minutes=5)
def timed_job():
    session = Session()
    users = session.query(Users)
    for u in users:
        if datetime.datetime.now() >= u.time_remind:
            viber.send_messages(u.viber_id, [TextMessage(text="Пора учить слова", keyboard=KEYBOARD,
                                                         tracking_data='tracking_data')])
    session.close()


@sched.scheduled_job('interval', minutes=10)
def wake_up():
    r = requests.get('https://viberbotforen.herokuapp.com/')

sched.start()
