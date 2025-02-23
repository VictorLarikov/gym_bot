from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackContext,
    ConversationHandler,
    MessageHandler,
    filters
)
from database import session, User, Program, Progress, engine  # Импортируем engine
from sqlalchemy.exc import OperationalError
from sqlalchemy import text  # Для выполнения SQL-запросов
from dotenv import load_dotenv
import os
import pandas as pd
from datetime import datetime
import asyncio

# Загрузка переменных окружения
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")

# Проверяем, существует ли столбец day, и добавляем его, если нет
try:
    session.query(Program.day).first()
except OperationalError:
    with engine.connect() as conn:
        conn.execute(text("ALTER TABLE programs ADD COLUMN day INTEGER;"))
        conn.commit()
    print("Столбец 'day' успешно добавлен в таблицу 'programs'.")

# Проверяем, существует ли столбец intensity, и добавляем его, если нет
try:
    session.query(Program.intensity).first()
except OperationalError:
    with engine.connect() as conn:
        conn.execute(text("ALTER TABLE programs ADD COLUMN intensity TEXT;"))
        conn.commit()
    print("Столбец 'intensity' успешно добавлен в таблицу 'programs'.")

# Функция для загрузки общей программы тренировок
async def load_default_program():
    try:
        # Читаем файл programs.xlsx с листа "amina"
        df = pd.read_excel("programs.xlsx", sheet_name="amina")
        
        # Группируем данные по дням и интенсивности
        grouped = df.groupby(["day", "intensity"])
        
        for (day, intensity), group in grouped:
            # Преобразуем данные в список словарей
            program_data = group.to_dict(orient="records")
            
            # Создаем запись в базе данных для "общей" программы
            program_entry = Program(
                user_id=None,  # Общая программа для всех пользователей
                day=day,
                intensity=intensity,
                program_data=str(program_data)  # Сохраняем данные как строку JSON
            )
            session.add(program_entry)
        
        session.commit()
        print("Общая программа тренировок успешно загружена!")
    
    except Exception as e:
        print(f"Ошибка при загрузке общей программы: {str(e)}")

# Состояния диалога
WAITING_FOR_DAYS = 1
CONFIRM_DAYS = 2
MAIN_MENU = 3
SELECT_INTENSITY = 4
VIEW_FULL_PLAN = 5  # Новое состояние для просмотра полного плана

# Команда /start
async def start(update: Update, context: CallbackContext):
    user_id = update.message.from_user.id
    user_name = update.message.from_user.first_name
    
    # Проверяем, существует ли пользователь в базе данных
    user = session.query(User).filter_by(id=user_id).first()
    if not user:
        new_user = User(
            id=user_id,
            name=user_name,
            weight=0,
            height=0,
            goal='',
            training_days='',
            start_time=''
        )
        session.add(new_user)
        session.commit()
        user = new_user  # Обновляем ссылку на пользователя
    
    # Если дни тренировок не указаны, запрашиваем их
    if not user.training_days:
        await update.message.reply_text(f"Привет, {user_name}! В этом боте будет вся информация о твоих тренировках.")
        await update.message.reply_text(
            "Укажи, в какие дни будут проходить твои тренировки (через запятую). Например: понедельник, среда, пятница"
        )
        return WAITING_FOR_DAYS
    else:
        await update.message.reply_text(f"Привет снова, {user_name}!")
        await main_menu(update, context)
        return MAIN_MENU

# Сохранение дней тренировок
async def save_training_days(update: Update, context: CallbackContext):
    user_id = update.message.from_user.id
    days_input = update.message.text.strip()
    
    # Разбиваем введенные дни на список
    days_list = [day.strip().capitalize() for day in days_input.split(",")]
    
    # Формируем сообщение с подтверждением
    confirmation_message = "Давай проверим, что я правильно записал дни тренировок:\n"
    for i, day in enumerate(days_list, start=1):
        confirmation_message += f"День {i} - {day}\n"
    
    confirmation_message += "\nЯ все правильно записал? Ответь: да или нет."
    
    # Сохраняем временно дни в контексте для дальнейшей обработки
    context.user_data["training_days"] = days_list
    
    await update.message.reply_text(confirmation_message)
    
    # Переходим к состоянию подтверждения
    return CONFIRM_DAYS

# Подтверждение дней тренировок
async def confirm_training_days(update: Update, context: CallbackContext):
    user_id = update.message.from_user.id
    response = update.message.text.lower()
    
    if response == "да":
        # Если пользователь подтвердил дни, сохраняем их в базу данных
        days_list = context.user_data.get("training_days", [])
        days_str = ", ".join(days_list)
        
        user = session.query(User).filter_by(id=user_id).first()
        if user:
            user.training_days = days_str
            session.commit()
            
            # Показываем главное меню
            await main_menu(update, context)
            return MAIN_MENU
    
    elif response == "нет":
        # Если пользователь не подтвердил дни, просим ввести их заново
        await update.message.reply_text(
            "Хорошо, давай попробуем еще раз. Укажи дни тренировок (через запятую). Например: понедельник, среда, пятница"
        )
        return WAITING_FOR_DAYS
    
    else:
        # Если ответ не "да" или "нет", просим повторить
        await update.message.reply_text("Пожалуйста, ответь только 'да' или 'нет'.")
        return CONFIRM_DAYS

# Главное меню
async def main_menu(update: Update, context: CallbackContext):
    user_id = update.message.from_user.id
    
    # Проверяем, существуют ли дни тренировок
    user = session.query(User).filter_by(id=user_id).first()
    if not user or not user.training_days:
        await update.message.reply_text("Сначала укажи дни тренировок с помощью команды /start.")
        return
    
    # Создаем клавиатуру с кнопками
    keyboard = [
        ["План тренировок"],  # Кнопка для просмотра полного плана
        ["Тренировка сегодня"],  # Кнопка для текущего дня
        ["Отследить прогресс"]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    
    await update.message.reply_text("Главное меню:", reply_markup=reply_markup)

# Обработка выбора из главного меню
async def handle_menu_choice(update: Update, context: CallbackContext):
    user_id = update.message.from_user.id
    choice = update.message.text
    
    if choice == "План тренировок":
        # Показываем меню выбора типа тренировок
        await show_plan_intensity_menu(update, context)
        return VIEW_FULL_PLAN
    
    elif choice == "Тренировка сегодня":
        # Показываем программу для текущего дня
        await show_today_program(update, context)
        return MAIN_MENU
    
    elif choice == "Отследить прогресс":
        # Ищем прогресс пользователя
        progress_data = session.query(Progress).filter_by(user_id=user_id).all()
        
        if progress_data:
            response = "Твой прогресс:\n"
            for entry in progress_data:
                response += f"{entry.date}: {entry.exercise} - {entry.reps} повторений, {entry.weight} кг\n"
            await update.message.reply_text(response)
        else:
            await update.message.reply_text("У тебя пока нет записей о прогрессе.")
    
    else:
        await update.message.reply_text("Неизвестная команда. Пожалуйста, используй кнопки из главного меню.")
    
    return MAIN_MENU

# Меню выбора интенсивности для просмотра полного плана
async def show_plan_intensity_menu(update: Update, context: CallbackContext):
    user_id = update.message.from_user.id
    
    # Создаем клавиатуру с кнопками выбора интенсивности
    keyboard = [
        ["Активные тренировки"],
        ["Легкие тренировки"]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    
    await update.message.reply_text("Какие тренировки тебя интересуют?", reply_markup=reply_markup)
    
    # Переходим к состоянию просмотра полного плана
    return VIEW_FULL_PLAN

# Обработка выбора интенсивности для просмотра полного плана
async def handle_view_full_plan(update: Update, context: CallbackContext):
    user_id = update.message.from_user.id
    choice = update.message.text
    
    # Получаем все дни тренировок пользователя
    user = session.query(User).filter_by(id=user_id).first()
    if not user or not user.training_days:
        await update.message.reply_text("Сначала укажи дни тренировок с помощью команды /start.")
        return MAIN_MENU
    
    training_days = user.training_days.split(",")
    day_mapping = {
        "понедельник": 1,
        "вторник": 2,
        "среда": 3,
        "четверг": 4,
        "пятница": 5,
        "суббота": 6,
        "воскресенье": 7
    }
    
    if choice == "Активные тренировки":
        # Загружаем активные программы тренировок для всех дней
        full_program = ""
        for i, day in enumerate(training_days, start=1):
            program_data = session.query(Program).filter_by(user_id=None, intensity="active", day=i).first()
            if program_data:
                try:
                    exercises = eval(program_data.program_data)
                    program_info = "\n".join([f"{exercise['exercise']} - {exercise['sets']} подходов по {exercise['reps']} повторений" for exercise in exercises])
                    full_program += f"{day.strip().capitalize()}:\n{program_info}\n\n"
                except Exception as e:
                    await update.message.reply_text(f"Ошибка при обработке данных для дня {i}: {str(e)}")
                    full_program += f"{day.strip().capitalize()}: Ошибка обработки данных.\n\n"
            else:
                full_program += f"{day.strip().capitalize()}: Программа активных тренировок не загружена.\n\n"
        
        await update.message.reply_text(f"Твой план активных тренировок:\n{full_program}")
    
    elif choice == "Легкие тренировки":
        # Загружаем легкие программы тренировок для всех дней
        full_program = ""
        for i, day in enumerate(training_days, start=1):
            program_data = session.query(Program).filter_by(user_id=None, intensity="light", day=i).first()
            if program_data:
                try:
                    exercises = eval(program_data.program_data)
                    program_info = "\n".join([f"{exercise['exercise']} - {exercise['sets']} подходов по {exercise['reps']} повторений" for exercise in exercises])
                    full_program += f"{day.strip().capitalize()}:\n{program_info}\n\n"
                except Exception as e:
                    await update.message.reply_text(f"Ошибка при обработке данных для дня {i}: {str(e)}")
                    full_program += f"{day.strip().capitalize()}: Ошибка обработки данных.\n\n"
            else:
                full_program += f"{day.strip().capitalize()}: Программа легких тренировок не загружена.\n\n"
        
        await update.message.reply_text(f"Твой план легких тренировок:\n{full_program}")
    
    else:
        await update.message.reply_text("Неизвестная команда. Пожалуйста, используй кнопки из меню.")
    
    # Возвращаемся в главное меню
    await main_menu(update, context)
    return MAIN_MENU

# Показать программу тренировок для текущего дня
async def show_today_program(update: Update, context: CallbackContext):
    user_id = update.message.from_user.id
    
    # Получаем текущий день тренировки
    current_day = get_current_training_day(user_id)
    if not current_day:
        await update.message.reply_text("Сегодня нет тренировки.")
        return MAIN_MENU
    
    # Загружаем программы для текущего дня
    active_program = session.query(Program).filter_by(user_id=None, intensity="active", day=current_day).first()
    light_program = session.query(Program).filter_by(user_id=None, intensity="light", day=current_day).first()
    
    response = f"Тренировка на сегодня (День {current_day}):\n\n"
    
    if active_program:
        try:
            exercises = eval(active_program.program_data)
            program_info = "\n".join([f"{exercise['exercise']} - {exercise['sets']} подходов по {exercise['reps']} повторений" for exercise in exercises])
            response += f"Активные тренировки:\n{program_info}\n\n"
        except Exception as e:
            response += f"Ошибка при обработке активных тренировок: {str(e)}\n\n"
    else:
        response += "Активные тренировки не загружены.\n\n"
    
    if light_program:
        try:
            exercises = eval(light_program.program_data)
            program_info = "\n".join([f"{exercise['exercise']} - {exercise['sets']} подходов по {exercise['reps']} повторений" for exercise in exercises])
            response += f"Легкие тренировки:\n{program_info}\n"
        except Exception as e:
            response += f"Ошибка при обработке легких тренировок: {str(e)}\n"
    else:
        response += "Легкие тренировки не загружены.\n"
    
    await update.message.reply_text(response)

# Определение текущего дня тренировки
def get_current_training_day(user_id: int):
    user = session.query(User).filter_by(id=user_id).first()
    if not user or not user.training_days:
        return None
    
    today = datetime.today().weekday() + 1  # Нумерация дней с 1
    training_days = user.training_days.split(",")
    day_mapping = {
        "понедельник": 1,
        "вторник": 2,
        "среда": 3,
        "четверг": 4,
        "пятница": 5,
        "суббота": 6,
        "воскресенье": 7
    }
    
    for i, day in enumerate(training_days, start=1):
        if day_mapping.get(day.strip().lower()) == today:
            return i  # Возвращаем номер дня (1, 2, 3)
    
    return None  # Если сегодня нет тренировки

# Команда /deleteuser
async def delete_user(update: Update, context: CallbackContext):
    user_id = update.message.from_user.id
    
    # Ищем пользователя в базе данных
    user = session.query(User).filter_by(id=user_id).first()
    if user:
        # Удаляем пользователя
        session.delete(user)
        session.commit()
        await update.message.reply_text("Твоя учетная запись успешно удалена. Ты можешь начать заново.")
    else:
        await update.message.reply_text("Ты еще не зарегистрирован в боте.")

# Создание ConversationHandler
conversation_handler = ConversationHandler(
    entry_points=[CommandHandler("start", start)],
    states={
        WAITING_FOR_DAYS: [MessageHandler(filters.TEXT & ~filters.COMMAND, save_training_days)],
        CONFIRM_DAYS: [MessageHandler(filters.TEXT & ~filters.COMMAND, confirm_training_days)],
        MAIN_MENU: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_menu_choice)],
        SELECT_INTENSITY: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_intensity_choice)],  # Состояние для выбора интенсивности # type: ignore
        VIEW_FULL_PLAN: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_view_full_plan)]  # Состояние для просмотра полного плана
    },
    fallbacks=[]
)

# Запуск бота
if __name__ == '__main__':
    # Загружаем общую программу тренировок при старте бота
    asyncio.run(load_default_program())
    
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Добавляем ConversationHandler
    application.add_handler(conversation_handler)
    
    # Добавляем остальные команды
    application.add_handler(CommandHandler("deleteuser", delete_user))
    
    print("Бот запущен!")
    application.run_polling()