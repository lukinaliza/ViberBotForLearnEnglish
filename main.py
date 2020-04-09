from flask import Flask, request, Response, render_template, make_response
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship, scoped_session
from sqlalchemy.pool import NullPool

from Settings import TOKEN, WEBHOOK
from viberbot import Api
from viberbot.api.messages import TextMessage, KeyboardMessage
from viberbot.api.bot_configuration import BotConfiguration
from viberbot.api.viber_requests import ViberMessageRequest, ViberConversationStartedRequest
import random
import copy
import json
import sqlite3
import datetime
from sqlalchemy import create_engine, Column, Integer, String, DateTime, ForeignKey
from collections import deque

with open('english_words.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

app = Flask(__name__)

bot_configuration = BotConfiguration(
    name='EnglishBotLiza',
    avatar='http://viber.com/avatar.jpg',
    auth_token=TOKEN
)

viber = Api(bot_configuration)

engine = create_engine(
   'postgres://qnakjltyvuqpku:c5f08f5f6d9e839f3a50bb0b84a48a646fed55c9c7709c0a05df1937e6f42703@ec2-54-247-79-178.eu-west-1.compute.amazonaws.com:5432/d7dbjfelqdi0jl', poolclass=NullPool, echo=False)
# engine = create_engine('sqlite:///test.db', echo=False)
Base = declarative_base()

Session = sessionmaker(engine)


class Users(Base):
    __tablename__ = 'users'
    user_id = Column(Integer, primary_key=True)
    fio = Column(String, nullable=False, default='John Doe')
    viber_id = Column(String, nullable=False, unique=True)
    t_last_answer = Column(DateTime)
    time_remind = Column(DateTime)

    words = relationship("Learning", back_populates='user')

    def __repr__(self):
        return f'{self.user_id}: {self.fio}[{self.viber_id}]'


class Learning(Base):
    __tablename__ = 'learning'
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.user_id'), nullable=False)
    word = Column(String, nullable=False)
    correct_answer = Column(Integer, nullable=False, default=0)
    t_last_correct_answer = Column(DateTime)

    user = relationship("Users", back_populates='words')

    def __pepr__(self):
        return f'{self.id}: {self.user_id}[{self.word} / {self.right_answer}]'


class Settings(Base):
    __tablename__ = 'settings'
    id = Column(Integer, primary_key=True)
    deltatime_reminder = Column(Integer, nullable=False, default=30)
    session_words = Column(Integer, nullable=False, default=10)
    rightanswers_tolearnt = Column(Integer, nullable=False, default=20)


class Game:
    def __init__(self, viber_id):
        self.viber_id = viber_id
        self.word = {}
        self.count_all = 0
        self.count_correct = 0


START_KBD = {
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
        }
    ]
}

message = KeyboardMessage(tracking_data='tracking_data', keyboard=START_KBD)


def next_word(game):
    session = Session()
    user_id = session.query(Users.user_id).filter(Users.viber_id == game.viber_id)
    game.word = data[random.choice(range(50))]
    query = session.query(Learning).filter(Learning.user_id == user_id).filter(Learning.word == game.word["word"])
    learning = query.all()
    if len(learning) == 0:
        session.add(Learning(user_id=user_id, word=game.word["word"]))
        session.commit()
    else:
        correct_answer = session.query(Learning.correct_answer).filter(Learning.user_id == user_id).filter(
            Learning.word == game.word["word"]).first()
    session.close()


count = 0

def initSettings():
    session = Session()
    set = session.query(Settings).first()
    if set == None:
        s = Settings()
        session.add(s)
        session.commit()

@app.route("/")
def hello():
    return render_template('hello.html')

@app.route("/settings")
def settings():
    session = Session()
    set = session.query(Settings).first()
    if set == None:
        initSettings()
    session.close()
    return render_template('settings.html', deltatime_reminder = set.deltatime_reminder, session_words = set.session_words, rightanswers_tolearnt = set.rightanswers_tolearnt)

@app.route('/set_settings', methods = [ 'GET'] )
def set_settings():
    session = Session()
    set = session.query(Settings).first()
    if set == None:
        initSettings()
    set.deltatime_reminder = int(request.args.get('deltatime_reminder'))
    set.session_words = int(request.args.get('session_words'))
    set.rightanswers_tolearnt = int(request.args.get('rightanswers_tolearnt'))
    session.commit()
    session.close()
    string = render_template('successful.html')
    response = make_response(string)
    return response



# вопрос
def question(game):
    session = Session()
    set = session.query(Settings).first()
    sw=set.session_words-1
    if game.count_all <= sw:
        # вывести вопрос
        next_word(game)
        bot_response = TextMessage(text=f'Вопрос №{game.count_all + 1}. Как переводится слово : {game.word["word"]}',
                                   keyboard=CreateKBD(game), tracking_data='tracking_data')
        viber.send_messages(game.viber_id, [bot_response])
    else:
        # вывести итоги раунда
        bot_response = TextMessage(
            text=f"Вы верно ответили на {game.count_correct} из {game.count_all} Сыграем снова?! ЖМИ НА СТАРТ",
            keyboard=START_KBD,
            tracking_data='tracking_data')
        viber.send_messages(game.viber_id, [bot_response])
    session.close()


# обработать ответ
def answer(text, game):
    session = Session()
    text = eval(text)
    if text[0] == game.count_all:
        if text[1] == game.word["translation"]:
            # счётчик правильных ответов
            game.count_correct += 1
            user_id = session.query(Users.user_id).filter(Users.viber_id == game.viber_id)
            learning = session.query(Learning).filter(Learning.user_id == user_id).filter(
                Learning.word == game.word["word"]).first()
            learning.correct_answer += 1
            session.commit()
            bot_response = TextMessage(text=f'Вопрос № {game.count_all + 1}. Ответ верный :)')
        else:
            bot_response = TextMessage(text=f'Вопрос № {game.count_all + 1}. Ответ неверный :(')
        # всего ответов
        game.count_all += 1
        viber.send_messages(game.viber_id, [bot_response])
        return True
    session.close()
    # question(game)
    return False


# привести пример
def example(game, number):
    session = Session()
    bot_response = TextMessage(text=f'{game.word["examples"][number]}',
                               keyboard=CreateKBD(game), tracking_data='tracking_data')
    keyboard = KeyboardMessage(tracking_data='tracking_data', keyboard=CreateKBD(game))
    viber.send_messages(game.viber_id, [bot_response])
    session.close()


# клавиатура ползователя
def CreateKBD(game):
    session = Session()
    # список с вариантами переводов слова
    translation = []
    # правильный перевод
    translation.append(game.word["translation"])
    while len(translation) != 4:
        # заносим новое слово если его нет в списке
        if random.choice(data)["translation"] not in translation:
            translation.append(random.choice(data)["translation"])
        random.shuffle(translation)
    KEYBOARD = {
        "Type": "keyboard",
        "Buttons": [
            {
                "Columns": 3,
                "Rows": 1,
                "BgColor": "#e6f5ff",
                "BgMedia": "http://link.to.button.image",
                "BgMediaType": "picture",
                "BgLoop": True,
                "ActionType": "reply",
                "ActionBody": f"{game.count_all, translation[0]}",
                "ReplyType": "message",
                "Text": f"{translation[0]}"
            },
            {
                "Columns": 3,
                "Rows": 1,
                "BgColor": "#e6f5ff",
                "BgMedia": "http://link.to.button.image",
                "BgMediaType": "picture",
                "BgLoop": True,
                "ActionType": "reply",
                "ActionBody": f"{game.count_all, translation[1]}",
                "ReplyType": "message",
                "Text": f"{translation[1]}"
            },
            {
                "Columns": 3,
                "Rows": 1,
                "BgColor": "#e6f5ff",
                "BgMedia": "http://link.to.button.image",
                "BgMediaType": "picture",
                "BgLoop": True,
                "ActionType": "reply",
                "ActionBody": f"{game.count_all, translation[2]}",
                "ReplyType": "message",
                "Text": f"{translation[2]}"
            },
            {
                "Columns": 3,
                "Rows": 1,
                "BgColor": "#e6f5ff",
                "BgMedia": "http://link.to.button.image",
                "BgMediaType": "picture",
                "BgLoop": True,
                "ActionType": "reply",
                "ActionBody": f"{game.count_all, translation[3]}",
                "ReplyType": "message",
                "Text": f"{translation[3]}"
            },
            {
                "Columns": 6,
                "Rows": 1,
                "BgColor": "#e6f5ff",
                "BgMedia": "http://link.to.button.image",
                "BgMediaType": "picture",
                "BgLoop": True,
                "ActionType": "reply",
                "ActionBody": "Пример использования",
                "ReplyType": "message",
                "Text": "Пример использования"
            }
        ]
    }
    session.close()
    return KEYBOARD


# справочник соответствия пользователя и его текущей игры
game_usera = {}


def poisk(viber_id):
    return game_usera[viber_id]


class TokenHolder():

    def __init__(self):
        self.q = deque()

    def add(self, token):
        self.q.append(token)

    def pop(self):
        self.q.popleft()

    def clear(self, num):
        i = 0
        while i < num:
            self.q.popleft()
            i += 1

    def isIn(self, token):
        if token in self.q:
            return True
        return False

    def __len__(self):
        return self.q.__len__()

    def __repr__(self):
        for t in self.q:
            print(t)

mes_token = TokenHolder()

init = False
@app.route('/incoming', methods=['POST'])
def incoming():
    Base.metadata.create_all(engine)
    global init
    if (init == False):
        initSettings()
        init = True
    # обработка
    session = Session()
    viber_request = viber.parse_request(request.get_data())

    if isinstance(viber_request, ViberConversationStartedRequest):
        viber_user = viber_request.user.id
        if len(session.query(Users).filter(Users.viber_id == viber_user).all()) == 0:
            add_user = Users(fio=viber_request.user.name, viber_id=viber_user, t_last_answer=datetime.datetime.utcnow())
            session.add(add_user)
            session.commit()
        new_game = Game(viber_user)
        game_usera[viber_user] = new_game
        user_id = session.query(Users.user_id).filter(Users.viber_id == game_usera[viber_user].viber_id)
        set = session.query(Settings).first()
        count_correct = session.query(Learning).filter(Learning.user_id == user_id).filter(
            Learning.correct_answer > set.rightanswers_tolearnt).count()
        date_last_visit = str(session.query(Users.t_last_answer).filter(Users.user_id == user_id).first()).replace(', ',
                                                                                                                   '/ ')[
                          19:29]
        time_last_visit = str(session.query(Users.t_last_answer).filter(Users.user_id == user_id).first()).replace(', ',
                                                                                                                   ': ')[
                          31:41]
        text = " Привет! это бот предназначенный для изучения английских слов! \n" \
               f'Нажмите старт чтобы начать:).\n' \
               f'Вы выучили {count_correct+1} слов \n' \
               f'Время последнего посещения: дата {date_last_visit}  время {time_last_visit}'
        viber.send_messages(viber_user, [TextMessage(text=text, keyboard=START_KBD,
                                                     tracking_data='tracking_data')])
    if isinstance(viber_request, ViberMessageRequest):
        if not mes_token.isIn(viber_request.message_token):
            mes_token.add(viber_request.message_token)
            mes_token.__repr__()
            if mes_token.__len__() > 10000:
                mes_token.clear(100)
            user = session.query(Users).filter(Users.viber_id == viber_request.sender.id).first()
            game = poisk(user.viber_id)
            message = viber_request.message
            set = session.query(Settings).first()
            if isinstance(message, TextMessage):
                text = message.text
                if text == "Старт":
                    user.t_last_answer = datetime.datetime.utcnow()
                    user.time_remind = datetime.datetime.utcnow() + datetime.timedelta(minutes=set.deltatime_reminder)
                    session.commit()
                    game.count_all = 0
                    game.count_correct = 0
                    question(game)
                # вызов примера использования
                elif text == "Пример использования":
                    global count_example
                    # проверяем количетво примеров
                    if count_example >= len(game.word["examples"]):
                        count_example = 0
                    else:
                        count_example += 1
                    example(game, count_example)
                elif text == 'Напомнить позже':
                    user.time_remind = datetime.datetime.utcnow() + datetime.timedelta(minutes=set.deltatime_reminder)
                    session.commit()
                else:
                    # ответ пользователя
                    if answer(text, game):
                        question(game)
            session.close()
    return Response(status=200)


if __name__ == '__main__':
    app.run(host='127.0.0.1', port=8008)
