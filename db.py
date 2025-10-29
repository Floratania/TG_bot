from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from config import DATABASE_URL
from sqlalchemy.exc import OperationalError, ArgumentError # Додаємо для обробки помилок

# Змінні ініціалізуються як None
engine = None
SessionLocal = None

try:
    # Перевіряємо, чи існує URL
    if not DATABASE_URL:
        raise ValueError("DATABASE_URL не визначено у config.py")

    # Ініціалізуємо Engine
    print("DEBUG: Спроба ініціалізації SQLAlchemy Engine...")
    engine = create_engine(DATABASE_URL, echo=True, future=True)
    
    # Спроба підключення для перевірки URL
    # engine.connect().close() 
    # Примітка: Ми не використовуємо .connect() тут, щоб не створювати його на рівні модуля,
    # але engine.connect() є першою дією, яка викликає збій, якщо URL невірний.

    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    print("DEBUG: Ініціалізація SQLAlchemy Engine успішна.")
    
except (OperationalError, ArgumentError, ValueError, Exception) as e:
    print(f"FATAL ERROR: Не вдалося ініціалізувати підключення до бази даних.")
    print(f"Перевірте DATABASE_URL у config.py та доступність сервера.")
    print(f"Помилка: {e}")
    # Якщо збій тут, бот не зможе працювати, але принаймні ми побачимо помилку.
    # Ми не можемо просто завершити роботу, тому залишаємо engine=None.

Base = declarative_base()

def get_db():
    # Ця функція тепер перевіряє, чи було ініціалізовано SessionLocal
    if SessionLocal is None:
        raise Exception("Database connection failed during startup. Cannot open session.")
        
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
