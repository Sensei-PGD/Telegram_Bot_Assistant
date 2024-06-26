import logging  # модуль для сбора логов
import sqlite3
# подтягиваем константы из config-файла
from config import LOGS, DB_FILE

# настраиваем запись логов в файл
logging.basicConfig(filename=LOGS, level=logging.ERROR, format="%(asctime)s FILE: %(filename)s IN: %(funcName)s MESSAGE: %(message)s", filemode="w")
path_to_db = DB_FILE  # файл базы данных
DB_FILE = "chatbot.db"


def create_database():
    try:
        # подключаемся к базе данных
        with sqlite3.connect(path_to_db) as conn:
            cursor = conn.cursor()
            # создаём таблицу messages
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY,
                user_id INTEGER,
                message TEXT,
                role TEXT,
                total_gpt_tokens INTEGER,
                tts_symbols INTEGER,
                stt_blocks INTEGER)
            ''')
            logging.info("DATABASE: База данных создана")  # делаем запись в логах
    except Exception as e:
        logging.error(e)  # если ошибка - записываем её в логи
        return None


def add_message(user_id, full_message):
    try:
        # подключаемся к базе данных
        with sqlite3.connect(path_to_db) as conn:
            cursor = conn.cursor()
            message, role, total_gpt_tokens, tts_symbols, stt_blocks = full_message
            # записываем в таблицу новое сообщение
            cursor.execute('''
                    INSERT INTO messages (user_id, message, role, total_gpt_tokens, tts_symbols, stt_blocks) 
                    VALUES (?, ?, ?, ?, ?, ?)''',
                           (user_id, message, role, total_gpt_tokens, tts_symbols, stt_blocks)
                           )
            conn.commit()  # сохраняем изменения
            logging.info(f"DATABASE: INSERT INTO messages "
                         f"VALUES ({user_id}, {message}, {role}, {total_gpt_tokens}, {tts_symbols}, {stt_blocks})")
    except Exception as e:
        logging.error(e)  # если ошибка - записываем её в логи
        return None


# считаем количество уникальных пользователей помимо самого пользователя
def count_users(user_id):
    try:
        # подключаемся к базе данных
        with sqlite3.connect(path_to_db) as conn:
            cursor = conn.cursor()
            # получаем количество уникальных пользователей помимо самого пользователя
            cursor.execute('''SELECT COUNT(DISTINCT user_id) FROM messages WHERE user_id <> ?''', (user_id,))
            count = cursor.fetchone()[0]
            return count
    except Exception as e:
        logging.error(e)  # если ошибка - записываем её в логи
        return None


# получаем последние <n_last_messages> сообщения
def select_n_last_messages(user_id, n_last_messages=4):
    messages = []  # список с сообщениями
    total_spent_tokens = 0  # количество потраченных токенов за всё время общения
    try:
        # подключаемся к базе данных
        with sqlite3.connect(path_to_db) as conn:
            cursor = conn.cursor()
            # получаем последние <n_last_messages> сообщения для пользователя
            cursor.execute('''
            SELECT message, role, total_gpt_tokens FROM messages WHERE user_id=? ORDER BY id DESC LIMIT ?''',
                           (user_id, n_last_messages))
            data = cursor.fetchall()
            # проверяем data на наличие хоть какого-то полученного результата запроса
            # и на то, что в результате запроса есть хотя бы одно сообщение - data[0]
            if data and data[0]:
                # формируем список сообщений
                for message in reversed(data):
                    messages.append({'text': message[0], 'role': message[1]})
                    total_spent_tokens = max(total_spent_tokens, message[2])  # находим максимальное количество потраченных токенов
            # если результата нет, так как у нас ещё нет сообщений - возвращаем значения по умолчанию
            return messages, total_spent_tokens
    except Exception as e:
        logging.error(e)  # если ошибка - записываем её в логи
        return messages, total_spent_tokens


def insert_row(user_id, message, role, total_gpt_tokens, tts_symbols, stt_blocks):
    global conn
    try:
        conn = sqlite3.connect(path_to_db)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO messages (user_id, message, role, total_gpt_tokens, tts_symbols, stt_blocks) 
            VALUES (?, ?, ?, ?, ?, ?)''',
            (user_id, message, role, total_gpt_tokens, tts_symbols, stt_blocks))
        conn.commit()
        logging.info(f"DATABASE: INSERT INTO messages VALUES ({user_id}, {message}, {role}, {total_gpt_tokens}, {tts_symbols}, {stt_blocks})")
    except Exception as e:
        logging.error(e)
    finally:
        conn.close()


def count_all_limits(user_id, limit_type):
    try:
        with sqlite3.connect(path_to_db) as conn:
            cursor = conn.cursor()
            cursor.execute(f'SELECT SUM({limit_type}) FROM messages WHERE user_id=?', (user_id,))
            data = cursor.fetchone()
            if data and data[0]:
                logging.info(f"DATABASE: User_id={user_id} used {data[0]} {limit_type}")
                return data[0]
            else:
                return 0
    except Exception as e:
        logging.error(e)
        return 0


# TTS

def insert_row_tts(user_id, message, role, total_gpt_tokens, tts_symbols):
    global conn
    try:
        conn = sqlite3.connect(path_to_db)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO messages (user_id, message, role, total_gpt_tokens, tts_symbols)
            VALUES (?, ?, ?, ?, ?)''',
            (user_id, message, role, total_gpt_tokens, tts_symbols))
        conn.commit()
        logging.info(f"DATABASE: INSERT INTO messages VALUES ({user_id}, {message}, {role}, {total_gpt_tokens}, {tts_symbols})")
    except Exception as e:
        logging.error(e)
    finally:
        conn.close()
