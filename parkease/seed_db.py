import sqlite3
import os
from werkzeug.security import generate_password_hash
from datetime import datetime, timedelta

DB_PATH = os.path.join(os.path.abspath(os.path.dirname(__file__)), "parkease.db")


def seed():
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
        print("Старая база удалена.")

    db = sqlite3.connect(DB_PATH)
    db.execute("PRAGMA foreign_keys = ON")

    # 1. Создание таблиц
    db.executescript("""
        CREATE TABLE users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            full_name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            birth_date TEXT,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'driver'
        );
        CREATE TABLE parkings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            address TEXT NOT NULL,
            price_per_hour REAL NOT NULL,
            work_hours TEXT NOT NULL,
            description TEXT,
            total_slots INTEGER NOT NULL DEFAULT 40
        );
        CREATE TABLE slots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            parking_id INTEGER NOT NULL,
            number INTEGER NOT NULL,
            type TEXT NOT NULL DEFAULT 'Обычное',
            FOREIGN KEY (parking_id) REFERENCES parkings(id) ON DELETE CASCADE
        );
        CREATE TABLE bookings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            slot_id INTEGER NOT NULL,
            start_time TEXT NOT NULL,
            end_time TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'PENDING',
            amount REAL NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id),
            FOREIGN KEY (slot_id) REFERENCES slots(id)
        );
        CREATE TABLE reviews (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            parking_id INTEGER NOT NULL,
            rating INTEGER NOT NULL,
            title TEXT NOT NULL,
            text TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'PUBLISHED',
            created_at TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id),
            FOREIGN KEY (parking_id) REFERENCES parkings(id) ON DELETE CASCADE
        );
        CREATE TABLE parking_admins (
            parking_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            PRIMARY KEY (parking_id, user_id),
            FOREIGN KEY (parking_id) REFERENCES parkings(id) ON DELETE CASCADE,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        );
    """)

    # 2. Пользователи
    pwd = generate_password_hash("123456")
    users = [
        ("Иванов Иван", "ivan@example.com", "2000-05-14", pwd, "driver"),
        ("Петрова Анна", "anna@example.com", "1995-08-20", pwd, "driver"),
        ("Смирнов Алексей", "smirnov@parkease.by", "1985-01-10", pwd, "admin"),
        ("Лебедева Ольга", "lebedeva@parkease.by", "1990-03-22", pwd, "admin"),
        ("Менеджер Системы", "manager@parkease.by", "1980-07-01", pwd, "manager"),
    ]
    db.executemany("INSERT INTO users (full_name, email, birth_date, password_hash, role) VALUES (?, ?, ?, ?, ?)",
                   users)

    # 3. Парковки
    parkings = [
        ("Парковка «Центральная»", "пр-т Независимости, 12", 3.00, "Ежедневно, 06:00 – 23:00",
         "Охраняемая парковка в центре города, въезд со стороны ул. Янки Купалы. Есть места для людей с инвалидностью.",
         40),
        ("Гараж «Октябрьская»", "ул. Куйбышева, 5", 2.50, "Ежедневно, 07:00 – 22:00", "Тёплый подземный гараж.", 18),
        ("Стоянка у ТЦ «Галерея»", "пр-т Победителей, 9", 4.00, "Ежедневно, 08:00 – 23:00", "Удобно для шопинга.", 120),
        ("Частная площадка «Двор»", "ул. Мясникова, 40", 1.80, "Ежедневно, 00:00 – 24:00", "Небольшая площадка.", 12),
    ]
    db.executemany(
        "INSERT INTO parkings (name, address, price_per_hour, work_hours, description, total_slots) VALUES (?, ?, ?, ?, ?, ?)",
        parkings)

    # 4. Слоты
    for parking_id in range(1, len(parkings) + 1):
        total = parkings[parking_id - 1][5]
        for n in range(1, min(total, 10) + 1):
            slot_type = "Обычное"
            if n == 3:
                slot_type = "Для инвалидов"
            elif n == 4:
                slot_type = "Электро"
            db.execute("INSERT INTO slots (parking_id, number, type) VALUES (?, ?, ?)", (parking_id, n, slot_type))

    # 5. Назначение админов
    db.execute("INSERT INTO parking_admins (parking_id, user_id) VALUES (1, 3)")
    db.execute("INSERT INTO parking_admins (parking_id, user_id) VALUES (2, 4)")
    db.execute("INSERT INTO parking_admins (parking_id, user_id) VALUES (3, 3)")

    # 6. Отзывы
    now = datetime.now().isoformat()
    reviews = [
        (1, 1, 5, "Удобный въезд", "Всегда есть места, охрана вежливая.", "PUBLISHED", now),
        (2, 1, 4, "Хорошо, но дороговато", "Парковка чистая, освещение отличное.", "PUBLISHED", now),
        (3, 1, 5, "Тесновато", "Сложно разъехаться на втором ярусе.", "PUBLISHED", now),
        (1, 2, 4, "Нормально", "Парковка чистая, освещение отличное.", "PUBLISHED", now),
    ]
    db.executemany(
        "INSERT INTO reviews (user_id, parking_id, rating, title, text, status, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        reviews)

    # 7. Бронирования (несколько штук для наглядности)
    db.execute(
        "INSERT INTO bookings (user_id, slot_id, start_time, end_time, status, amount, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (1, 1, "2026-10-20 10:00", "2026-10-20 13:00", "CONFIRMED", 9.00, now))
    db.execute(
        "INSERT INTO bookings (user_id, slot_id, start_time, end_time, status, amount, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (2, 4, "2026-10-19 09:00", "2026-10-19 18:00", "COMPLETED", 40.50, now))

    db.commit()
    db.close()
    print("База данных успешно заполнена тестовыми данными!")


if __name__ == "__main__":
    seed()