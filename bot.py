import telebot
import logging  # модуль для сбора логов
# подтягиваем константы из config-файла
from validators import *  # модуль для валидации
from yandex_gpt import ask_gpt  # модуль для работы с GPT
# подтягиваем константы из config файла
from config import LOGS, COUNT_LAST_MSG
# подтягиваем функции из database файла
from database import create_database, add_message, select_n_last_messages
from speechkit import speech_to_text, text_to_speech
from creds import get_bot_token  # модуль для получения bot_token

bot = telebot.TeleBot(get_bot_token())

# настраиваем запись логов в файл
logging.basicConfig(filename=LOGS, level=logging.ERROR, format="%(asctime)s FILE: %(filename)s IN: %(funcName)s MESSAGE: %(message)s", filemode="w")


# обрабатываем команду /start
@bot.message_handler(commands=['start'])
def start(message):
    bot.send_message(message.from_user.id, "Привет! Отправь мне голосовое сообщение или текст, и я тебе отвечу!")


# обрабатываем команду /help
@bot.message_handler(commands=['help'])
def help(message):
    bot.send_message(message.from_user.id, "Чтобы приступить к общению, отправь мне голосовое сообщение или текст")


# обрабатываем команду /debug - отправляем файл с логами
@bot.message_handler(commands=['debug'])
def debug(message):
    with open("logs.txt", "rb") as f:
        bot.send_document(message.chat.id, f)


@bot.message_handler(commands=['info'])  # получение информации о боте
def info(message):
    bot.send_message(message.chat.id,
                     "Бот-GPT — это телеграмм-бот с функцией YandexGPT-Lite, которая позволяет пользователю"
                     "общаться и получать информацию как через текст, так и через аудио.\n"               
                     "\nЖелаю Вам приятного общения!")


@bot.message_handler(commands=['command'])  # вывод доступных команд
def say_start(message):
    bot.send_message(message.chat.id, " Доступные команды 📋:\n"
                                      "\n/start - начать диалог"
                                      "\n/help - помощь"
                                      "\n/info - информация о боте"
                                      "\n/command - команды"
                                      "\n/limits – ваш профиль с потраченными токенами/сессиями"
                                      "\n/debug - режим отладки бота"
                                      "\n/stt  - проверка stt"
                                      "\n/tts - проверка tts")


@bot.message_handler(commands=['tts'])
def call_tts_handler(message):
    user_id = message.from_user.id
    bot.send_message(user_id, 'Проверка режима синтеза речи, пришлите сообщение')
    bot.register_next_step_handler(message, tts)


@bot.message_handler(commands=['stt'])
def stt_handler(message):
    user_id = message.from_user.id
    bot.send_message(user_id, 'Проверка режима распознавания речи, пришлите голосовое сообщение')
    bot.register_next_step_handler(message, stt)


def tts(message):
    user_id = message.from_user.id
    text = message.text
    status_tts, voice_response = text_to_speech(text)
    if status_tts:
        bot.send_voice(user_id, voice_response)
    else:
        bot.send_message(user_id, "Не удалось синтезировать речь")


def stt(message):
    user_id = message.from_user.id

    if message.voice:
        duration = message.voice.duration
        stt_blocks = is_stt_block_limit(user_id, duration)
        if stt_blocks:
            bot.send_message(user_id, "Речь распознана: " + message.voice.file_id)
            full_message = {
                'message': message.voice.file_id,
                'role': 'user',
                'total_gpt_tokens': 0,
                'tts_symbols': 0,
                'stt_blocks': stt_blocks
            }
            add_message(user_id, full_message)
        else:
            bot.send_message(user_id, "Превышен лимит распознавания речи.")
    else:
        bot.send_message(user_id, "Пришлите голосовое сообщение для распознавания.")


# обрабатываем голосовые сообщения
# Декоратор для обработки голосовых сообщений, полученных ботом
@bot.message_handler(content_types=['voice'])
def handle_voice(message: telebot.types.Message):
    try:
        user_id = message.from_user.id
        status_check_users, error_message = check_number_of_users(user_id)
        if not status_check_users:
            bot.send_message(user_id, error_message)
            return
        stt_blocks, error_message = is_stt_block_limit(user_id, message.voice.duration)
        if error_message:
            bot.send_message(user_id, error_message)
            return
        file_id = message.voice.file_id
        file_info = bot.get_file(file_id)
        file = bot.download_file(file_info.file_path)
        status_stt, stt_text = speech_to_text(file)
        if not status_stt:
            bot.send_message(user_id, stt_text)
            return
        add_message(user_id=user_id, full_message=[stt_text, 'user', 0, 0, stt_blocks])
        last_messages, total_spent_tokens = select_n_last_messages(user_id, COUNT_LAST_MSG)
        total_gpt_tokens, error_message = is_gpt_token_limit(last_messages, total_spent_tokens)
        if error_message:
            bot.send_message(user_id, error_message)
            return
        status_gpt, answer_gpt, tokens_in_answer = ask_gpt(last_messages)
        if not status_gpt:
            bot.send_message(user_id, answer_gpt)
            return
        total_gpt_tokens += tokens_in_answer
        tts_symbols, error_message = is_tts_symbol_limit(user_id, answer_gpt)
        add_message(user_id=user_id, full_message=[answer_gpt, 'assistant', total_gpt_tokens, tts_symbols, 0])
        if error_message:
            bot.send_message(user_id, error_message)
            return
        status_tts, voice_response = text_to_speech(answer_gpt)
        if status_tts:
            bot.send_voice(user_id, voice_response, reply_to_message_id=message.id)
        else:
            bot.send_message(user_id, answer_gpt, reply_to_message_id=message.id)
    except Exception as e:
        logging.error(e)
        bot.send_message(message.from_user.id, "Не получилось ответить. Попробуй записать другое сообщение") #user_id


# обрабатываем текстовые сообщения
@bot.message_handler(content_types=['text'])
def handle_text(message):
    try:
        user_id = message.from_user.id

        # ВАЛИДАЦИЯ: проверяем, есть ли место для ещё одного пользователя (если пользователь новый)
        status_check_users, error_message = check_number_of_users(user_id)
        if not status_check_users:
            bot.send_message(user_id, error_message)  # мест нет =(
            return

        # БД: добавляем сообщение пользователя и его роль в базу данных
        full_user_message = [message.text, 'user', 0, 0, 0]
        add_message(user_id=user_id, full_message=full_user_message)

        # ВАЛИДАЦИЯ: считаем количество доступных пользователю GPT-токенов
        # получаем последние 4 (COUNT_LAST_MSG) сообщения и количество уже потраченных токенов
        last_messages, total_spent_tokens = select_n_last_messages(user_id, COUNT_LAST_MSG)
        # получаем сумму уже потраченных токенов + токенов в новом сообщении и оставшиеся лимиты пользователя
        total_gpt_tokens, error_message = is_gpt_token_limit(last_messages, total_spent_tokens)
        if error_message:
            # если что-то пошло не так — уведомляем пользователя и прекращаем выполнение функции
            bot.send_message(user_id, error_message)
            return

        # GPT: отправляем запрос к GPT
        status_gpt, answer_gpt, tokens_in_answer = ask_gpt(last_messages)
        # GPT: обрабатываем ответ от GPT
        if not status_gpt:
            # если что-то пошло не так — уведомляем пользователя и прекращаем выполнение функции
            bot.send_message(user_id, answer_gpt)
            return
        # сумма всех потраченных токенов + токены в ответе GPT
        total_gpt_tokens += tokens_in_answer

        # БД: добавляем ответ GPT и потраченные токены в базу данных
        full_gpt_message = [answer_gpt, 'assistant', total_gpt_tokens, 0, 0]
        add_message(user_id=user_id, full_message=full_gpt_message)

        bot.send_message(user_id, answer_gpt, reply_to_message_id=message.id)  # отвечаем пользователю текстом
    except Exception as e:
        logging.error(e)  # если ошибка — записываем её в логи
        bot.send_message(message.from_user.id, "Не получилось ответить. Попробуй написать другое сообщение")


# обрабатываем все остальные типы сообщений
@bot.message_handler(func=lambda: True)
def handler(message):
    bot.send_message(message.from_user.id, "Отправь мне голосовое или текстовое сообщение, и я тебе отвечу")


@bot.message_handler(content_types=['photo', 'video', 'document', 'sticker'])
def handle_non_text_message(message):
    bot.send_message(message.chat.id, "❗ Извините, не могу обработать фотографии, видео, документы или стикеры.")


@bot.message_handler(commands=['limits'])
def limits(message):
    user_id = message.from_user.id
    total_tokens = count_all_limits(user_id, 'total_gpt_tokens')
    if total_tokens is not None:
        bot.send_message(user_id, f"Общее количество потраченных токенов: {total_tokens}")
    else:
        bot.send_message(user_id, "У вас нет потраченных токенов или лимит их использования не установлен!")


# запускаем бота
bot.polling()
