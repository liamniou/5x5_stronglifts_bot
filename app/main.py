import os
import telebot
import pymongo

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

bot = telebot.TeleBot(os.environ.get("BOT_TOKEN"))
MONGO_CONNECTION_STRING = os.environ.get("MONGO_CONNECTION_STRING")
ALLOWED_CHAT_ID = int(os.environ.get("ALLOWED_CHAT_ID"))


@dataclass
class Entry:
    date: datetime
    type: str
    ex1: float
    ex1_addition: float
    ex2: float
    ex2_addition: float
    ex3: float
    ex3_addition: float

    _id: Optional[str] = None


def from_allowed_chat(message):
    return message.chat.id == ALLOWED_CHAT_ID


def read_mongodb_data(database_name, collection_name):
    client = pymongo.MongoClient(MONGO_CONNECTION_STRING)
    db = client[database_name]
    collection = db[collection_name]
    data = collection.find()
    client.close()

    return data


def read_last_entry(database_name, collection_name):
    client = pymongo.MongoClient(MONGO_CONNECTION_STRING)
    db = client[database_name]
    collection = db[collection_name]
    entry = collection.find_one(sort=[("_id", pymongo.DESCENDING)])

    client.close()

    if entry:
        latest_entry = Entry(**entry)
        return latest_entry
    else:
        return None


def read_second_to_last_entry(database_name, collection_name, message):
    client = pymongo.MongoClient(MONGO_CONNECTION_STRING)
    db = client[database_name]
    collection = db[collection_name]

    try:
        second_to_last_record = (
            collection.find().sort([("_id", pymongo.DESCENDING)]).limit(2)[1]
        )
    except IndexError:
        bot.send_message(
            message.chat.id,
            "Can't find previous data in DB. Provide starting values first by running /start command",
        )
        second_to_last_record = None

    client.close()
    if second_to_last_record:
        latest_entry = Entry(**second_to_last_record)
        return latest_entry
    else:
        return None


def write_data_to_mongodb(database_name, collection_name, data):
    client = pymongo.MongoClient(MONGO_CONNECTION_STRING)
    db = client[database_name]
    collection = db[collection_name]
    collection.insert_one(data)
    client.close()

    return 0


def get_today_session(last_week_data):
    if last_week_data.type == "A":
        exercise_names = ["Squat 5x5", "Bench Press 5x5", "Barbell Row 5x5"]
    else:
        exercise_names = ["Squat 5x5", "Overhead Press 5x5", "Deadlift 1x5"]

    value_1 = last_week_data.ex1 + last_week_data.ex1_addition
    value_2 = last_week_data.ex2 + last_week_data.ex2_addition
    value_3 = last_week_data.ex3 + last_week_data.ex3_addition

    text = f"Today's session is {last_week_data.type}\n1. {exercise_names[0]}: {value_1}\n2. {exercise_names[1]}: {value_2}\n3. {exercise_names[2]}: {value_3}\n`{value_1} {value_2} {value_3}`"

    return text


@bot.message_handler(
    func=lambda message: from_allowed_chat(message) and message.text.lower() == "/start"
)
def start(message):
    bot.reply_to(
        message,
        "Welcome to the 5x5 workout bot. Let's get a starting point for your workout",
    )
    bot.send_message(
        message.chat.id,
        "Provide starting values for session A (Squat, Bench Press, Barbell Row) separated by spaces",
    )
    bot.register_next_step_handler(message, record_init_data_for_a)


def record_init_data_for_a(message):
    values = list(map(float, message.text.split(" ")))
    if len(values) != 3:
        raise ValueError("Please provide exactly 3 values separated by commas")
    data = {
        "type": "A",
        "A": values[0],
        "B": values[1],
        "C": values[2],
        "D": 0,
        "E": 0,
        "F": 0,
    }
    save_data(message.chat.id, data)
    bot.reply_to(
        message,
        "Data saved successfully! Now provide starting values for session B (Squat, Overhead Press, Deadlift) separated by spaces",
    )
    bot.register_next_step_handler(message, record_init_data_for_b)


def record_init_data_for_b(message):
    values = list(map(float, message.text.split(" ")))
    if len(values) != 3:
        raise ValueError("Please provide exactly 3 values separated by commas")
    data = {
        "type": "B",
        "A": values[0],
        "B": values[1],
        "C": values[2],
        "D": 0,
        "E": 0,
        "F": 0,
    }
    save_data(message.chat.id, data)
    bot.reply_to(
        message,
        "Data saved successfully! Now you can start using the bot",
    )


@bot.message_handler(
    func=lambda message: from_allowed_chat(message)
    and message.text.lower() == "/agenda"
)
def show_agenda(message):
    data = read_second_to_last_entry("5x5", "data", message)
    if not data:
        return
    agenda_text = get_today_session(data)
    bot.reply_to(message, agenda_text, parse_mode="Markdown")


user_state = {}


@bot.message_handler(
    func=lambda message: from_allowed_chat(message)
    and message.text.lower() == "/record"
)
def record_entry(message):
    user_state[message.chat.id] = {"step": 0, "data": {}}
    bot.reply_to(message, "Provide your today's results")


@bot.message_handler(func=lambda message: True and from_allowed_chat(message))
def record_values(message):
    chat_id = message.chat.id
    state = user_state.get(chat_id)

    data = read_second_to_last_entry("5x5", "data", message)
    if not data:
        return
    today_session_type = data.type
    state["data"]["type"] = today_session_type

    if state:
        step = state["step"]
        if step == 0:
            try:
                values = list(map(float, message.text.split(" ")))
                if len(values) != 3:
                    raise ValueError(
                        "Please provide exactly 3 values separated by commas"
                    )
                state["data"]["A"], state["data"]["B"], state["data"]["C"] = values
                state["step"] += 1
                bot.reply_to(message, "Provide addition values for the next week")
            except ValueError as e:
                bot.reply_to(
                    message,
                    f"Error: {e}. Please provide 3 numeric values separated by spaces",
                )
        elif step == 1:
            try:
                values = list(map(float, message.text.split(" ")))
                if len(values) != 3:
                    raise ValueError(
                        "Please provide exactly 3 values separated by spaces"
                    )
                state["data"]["D"], state["data"]["E"], state["data"]["F"] = values
                state["step"] += 1

                save_data(chat_id, state["data"])
                bot.reply_to(message, "Data saved successfully!")
                del user_state[chat_id]  # End the conversation
            except ValueError as e:
                bot.reply_to(
                    message,
                    f"Error: {e}. Please provide 3 numeric values separated by commas",
                )
    else:
        bot.reply_to(message, "Please start the /record command first")


def save_data(chat_id, data):
    print(f"Saving data for chat_id: {chat_id}")
    current_date = datetime.now()

    data = {
        "date": current_date,
        "type": data["type"],
        "ex1": data["A"],
        "ex1_addition": data["D"],
        "ex2": data["B"],
        "ex2_addition": data["E"],
        "ex3": data["C"],
        "ex3_addition": data["F"],
    }

    write_data_to_mongodb("5x5", "data", data)


bot.polling()
