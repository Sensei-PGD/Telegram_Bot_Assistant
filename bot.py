import telebot
import logging  # модуль для сбора логов
# подтягиваем константы из config-файла
from validators import *  # модуль для валидации
from yandex_gpt import ask_gpt  # модуль для работы с GPT
# подтягиваем константы из config файла
from config import LOGS, COUNT_LAST_MSG, BOT_TOKEN_PATH
# подтягиваем функции из database файла
from database import create_database, add_message, select_n_last_messages, count_all_blocks, insert_row, count_all_symbol, insert_row_tts
from speechkit import speech_to_text, text_to_speech


bot = telebot.TeleBot(BOT_TOKEN_PATH)
create_database()


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
    try:
        with open("logs.txt", "r") as f:
            log_contents = f.read()
            if log_contents:
                bot.send_document(message.chat.id, open("logs.txt", "rb"))
            else:
                bot.send_message(message.chat.id, "Файл с логами пустой.")
    except FileNotFoundError as e:
        bot.send_message(message.chat.id, "Файл с логами не найден.")
    except Exception as e:
        bot.send_message(message.chat.id, "Произошла ошибка при обработке команды /debug.")
        logging.error(e)


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
                                      "\n/debug - режим отладки бота"
                                      "\n/stt  - проверка stt"
                                      "\n/tts - проверка tts")


@bot.message_handler(commands=['stt'])
def stt_handler(message):
    user_id = message.from_user.id
    bot.send_message(user_id, 'Проверка. Отправь голосовое сообщение, чтобы я его распознал!')
    bot.register_next_step_handler(message, stt)


def stt(message):
    user_id = message.from_user.id
    if not message.voice:
        return
    stt_blocks, error_message = is_stt_block_limit(user_id, message)
    if not stt_blocks:
        bot.send_message(user_id, error_message)
        return
    file_id = message.voice.file_id
    file_info = bot.get_file(file_id)
    file = bot.download_file(file_info.file_path)
    status, text = speech_to_text(file)
    if status:
        # Вызываем функцию insert_row() для сохранения значения stt_blocks в базе данных
        insert_row(user_id, text, 'stt_blocks', stt_blocks)
        bot.send_message(user_id, text, reply_to_message_id=message.id)
    else:
        bot.send_message(user_id, text)


def is_stt_block_limit(user_id: int, message: telebot.types.Message):
    duration = message.voice.duration
    audio_blocks = math.ceil(duration / 15)
    all_blocks = count_all_blocks(user_id)
    if all_blocks is None:
        all_blocks = 0
    all_blocks += audio_blocks

    if duration >= 30:
        msg = "SpeechKit STT работает с голосовыми сообщениями меньше 30 секунд"
        bot.send_message(user_id, msg)
        return None, msg

    if all_blocks >= MAX_USER_STT_BLOCKS:
        msg = f"Превышен общий лимит SpeechKit STT {MAX_USER_STT_BLOCKS}. Использовано {all_blocks} блоков. Доступно: {MAX_USER_STT_BLOCKS - all_blocks}"
        bot.send_message(user_id, msg)
        return None, msg

    # Подсчет и обновление количества использованных блоков STT
    total_stt_blocks = count_all_blocks(user_id)
    max_stt_blocks = MAX_USER_STT_BLOCKS

    if total_stt_blocks is None:
        total_stt_blocks = 0

    if total_stt_blocks < max_stt_blocks:
        total_stt_blocks += 1
    else:
        return None, "Превышен лимит блоков для распознавания речи."

    return audio_blocks, None


@bot.message_handler(commands=['tts'])
def call_tts_handler(message):
    user_id = message.from_user.id
    bot.send_message(user_id, 'Проверка. Отправь следующим сообщением текст, чтобы я его озвучил!')
    bot.register_next_step_handler(message, tts)


def tts(message):
    user_id = message.from_user.id
    text = message.text
    if message.content_type != 'text':
        bot.send_message(user_id, 'Отправь текстовое сообщение')
        return
    tts_symbol, error_message = is_tts_symbol_limit(message, text)
    if not tts_symbol:
        bot.send_message(user_id, error_message)
        return
    insert_row_tts(user_id, text, tts_symbol)
    status, content = text_to_speech(text)
    if status:
        bot.send_voice(user_id, content)
    else:
        bot.send_message(user_id, content)


def is_tts_symbol_limit(user_id, text):
    text_symbols = len(text)
    all_symbols = count_all_symbol(user_id)
    if all_symbols is None:
        all_symbols = 0
    all_symbols += text_symbols
    if all_symbols >= MAX_USER_TTS_SYMBOLS:
        return None, f"Превышен общий лимит SpeechKit TTS {MAX_USER_TTS_SYMBOLS}. Использовано: {all_symbols} символов. Доступно: {MAX_USER_TTS_SYMBOLS - all_symbols}"
    return text_symbols, None


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
        #stt_blocks, error_message = is_stt_block_limit(user_id, message.voice.duration)
        stt_blocks, error_message = is_stt_block_limit(user_id, message)
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
        bot.send_message(message.from_user.id, "Не получилось ответить. Попробуй записать другое сообщение")


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


# запускаем бота
bot.polling()
