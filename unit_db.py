import aiosqlite
import asyncio
import json
from config import DATABASE_URL

async def init_db(db_path=None):
    if db_path is None:
        db_path = DATABASE_URL.replace("sqlite:///", "")
    async with aiosqlite.connect(db_path) as db:
        await db.execute("PRAGMA foreign_keys = ON")
        await db.execute("PRAGMA journal_mode = WAL")

        # ===== Таблица пользователей =====
        await db.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY,
                telegram_id INTEGER UNIQUE,
                city TEXT,
                role TEXT DEFAULT 'client',
                full_name TEXT,
                phone TEXT,
                display_name_choice TEXT DEFAULT 'real_name',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # ===== Города =====
        await db.execute('''
            CREATE TABLE IF NOT EXISTS cities (
                id INTEGER PRIMARY KEY,
                name TEXT UNIQUE
            )
        ''')

        # ===== Категории и подкатегории =====
        await db.execute('''
            CREATE TABLE IF NOT EXISTS categories (
                id INTEGER PRIMARY KEY,
                name TEXT,
                city_id INTEGER,
                FOREIGN KEY (city_id) REFERENCES cities(id)
            )
        ''')
        await db.execute('''
            CREATE TABLE IF NOT EXISTS subcategories (
                id INTEGER PRIMARY KEY,
                name TEXT,
                category_id INTEGER,
                FOREIGN KEY (category_id) REFERENCES categories(id)
            )
        ''')

        # ===== СТО =====
        await db.execute('''
            CREATE TABLE IF NOT EXISTS stations (
                id INTEGER PRIMARY KEY,
                name TEXT,
                city_id INTEGER,
                admin_id INTEGER UNIQUE,
                phone TEXT,
                address TEXT,
                priority INTEGER DEFAULT 0,
                is_premium BOOLEAN DEFAULT 0,
                rating REAL DEFAULT 0,
                reviews_count INTEGER DEFAULT 0,
                subscription_until TIMESTAMP,
                work_hours TEXT,
                FOREIGN KEY (city_id) REFERENCES cities(id),
                FOREIGN KEY (admin_id) REFERENCES users(telegram_id)
            )
        ''')
        await db.execute('''
            CREATE TABLE IF NOT EXISTS station_categories (
                station_id INTEGER,
                category_id INTEGER,
                PRIMARY KEY (station_id, category_id),
                FOREIGN KEY (station_id) REFERENCES stations(id),
                FOREIGN KEY (category_id) REFERENCES categories(id)
            )
        ''')

        # ===== Услуги СТО с ценами =====
        await db.execute('''
            CREATE TABLE IF NOT EXISTS station_services (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                station_id INTEGER NOT NULL,
                city TEXT NOT NULL,
                brand TEXT NOT NULL,
                model TEXT NOT NULL,
                service_name TEXT NOT NULL,
                price INTEGER NOT NULL,
                currency TEXT DEFAULT 'KZT',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (station_id) REFERENCES stations(id) ON DELETE CASCADE
            )
        ''')
        await db.execute('CREATE INDEX IF NOT EXISTS idx_station_services_city_brand_model ON station_services(city, brand, model)')
        await db.execute('CREATE INDEX IF NOT EXISTS idx_station_services_station_id ON station_services(station_id)')

        # ===== Заявки =====
        await db.execute('''
            CREATE TABLE IF NOT EXISTS requests (
                id INTEGER PRIMARY KEY,
                user_id INTEGER,
                type TEXT,
                category_id INTEGER,
                subcategories TEXT,
                description TEXT,
                photo TEXT,
                city TEXT,
                status TEXT DEFAULT 'new',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                accepted_by INTEGER,
                accepted_at TIMESTAMP,
                completed_at TIMESTAMP,
                total_amount INTEGER,
                commission INTEGER,
                service_subtype TEXT,
                client_chat_id INTEGER,
                client_message_id INTEGER,
                FOREIGN KEY (user_id) REFERENCES users(telegram_id)
            )
        ''')

        # ===== Эвакуаторы и предложения =====
        await db.execute('''
            CREATE TABLE IF NOT EXISTS tow_trucks (
                id INTEGER PRIMARY KEY,
                name TEXT,
                city_id INTEGER,
                admin_id INTEGER,
                phone TEXT,
                address TEXT,
                rating REAL DEFAULT 0,
                reviews_count INTEGER DEFAULT 0,
                subscription_until TIMESTAMP,
                FOREIGN KEY (city_id) REFERENCES cities(id),
                FOREIGN KEY (admin_id) REFERENCES users(telegram_id)
            )
        ''')
        await db.execute('''
            CREATE TABLE IF NOT EXISTS tow_offers (
                id INTEGER PRIMARY KEY,
                request_id INTEGER,
                tower_id INTEGER,
                price INTEGER,
                eta TEXT,
                is_selected BOOLEAN DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (request_id) REFERENCES requests(id),
                FOREIGN KEY (tower_id) REFERENCES tow_trucks(id)
            )
        ''')

        # ===== Мойки и слоты =====
        await db.execute('''
            CREATE TABLE IF NOT EXISTS car_washes (
                id INTEGER PRIMARY KEY,
                name TEXT,
                city_id INTEGER,
                admin_id INTEGER,
                phone TEXT,
                address TEXT,
                boxes INTEGER,
                duration INTEGER,
                working_hours TEXT,
                rating REAL DEFAULT 0,
                reviews_count INTEGER DEFAULT 0,
                slot_duration INTEGER DEFAULT 30,
                break_duration INTEGER DEFAULT 5,
                work_start TEXT DEFAULT '09:00',
                work_end TEXT DEFAULT '21:00',
                days_off TEXT DEFAULT '[]',
                subscription_until TIMESTAMP,
                FOREIGN KEY (city_id) REFERENCES cities(id),
                FOREIGN KEY (admin_id) REFERENCES users(telegram_id)
            )
        ''')
        await db.execute('''
            CREATE TABLE IF NOT EXISTS wash_slots (
                id INTEGER PRIMARY KEY,
                wash_id INTEGER,
                datetime TEXT,
                status TEXT DEFAULT 'free',
                user_id INTEGER,
                progress TEXT,
                reminder_sent INTEGER DEFAULT 0,
                UNIQUE(wash_id, datetime) ON CONFLICT IGNORE,
                FOREIGN KEY (wash_id) REFERENCES car_washes(id),
                FOREIGN KEY (user_id) REFERENCES users(telegram_id)
            )
        ''')

        # ===== Поставщики и запчасти =====
        await db.execute('''
            CREATE TABLE IF NOT EXISTS suppliers (
                id INTEGER PRIMARY KEY,
                name TEXT,
                type TEXT,
                city_id INTEGER,
                admin_id INTEGER,
                phone TEXT,
                address TEXT,
                latitude REAL,
                longitude REAL,
                work_hours TEXT,
                delivery_available BOOLEAN,
                rating REAL DEFAULT 0,
                reviews_count INTEGER DEFAULT 0,
                subscription_until TIMESTAMP,
                FOREIGN KEY (city_id) REFERENCES cities(id),
                FOREIGN KEY (admin_id) REFERENCES users(telegram_id)
            )
        ''')
        await db.execute('''
            CREATE TABLE IF NOT EXISTS parts (
                id INTEGER PRIMARY KEY,
                supplier_id INTEGER,
                name TEXT,
                brand TEXT,
                part_number TEXT,
                price INTEGER,
                condition TEXT,
                compatible_models TEXT,
                quantity INTEGER,
                photo_url TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (supplier_id) REFERENCES suppliers(id)
            )
        ''')
        await db.execute('''
            CREATE TABLE IF NOT EXISTS part_orders (
                id INTEGER PRIMARY KEY,
                user_id INTEGER,
                part_id INTEGER,
                quantity INTEGER,
                total INTEGER,
                status TEXT DEFAULT 'paid',
                sto_id INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(telegram_id),
                FOREIGN KEY (part_id) REFERENCES parts(id)
            )
        ''')

        # ===== Отзывы =====
        await db.execute('''
            CREATE TABLE IF NOT EXISTS reviews (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                entity_type TEXT,
                entity_id INTEGER,
                rating INTEGER,
                comment TEXT,
                moderated INTEGER DEFAULT 0,
                hidden INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(telegram_id)
            )
        ''')

        # ===== Сервисная книжка =====
        await db.execute('''
            CREATE TABLE IF NOT EXISTS user_cars (
                id INTEGER PRIMARY KEY,
                user_id INTEGER,
                brand TEXT,
                model TEXT,
                year INTEGER,
                vin TEXT,
                license_plate TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(telegram_id)
            )
        ''')
        await db.execute('''
            CREATE TABLE IF NOT EXISTS service_records (
                id INTEGER PRIMARY KEY,
                user_id INTEGER,
                car_id INTEGER,
                date TEXT,
                mileage INTEGER,
                description TEXT,
                service_type TEXT,
                cost INTEGER,
                request_id INTEGER,
                FOREIGN KEY (user_id) REFERENCES users(telegram_id),
                FOREIGN KEY (car_id) REFERENCES user_cars(id)
            )
        ''')

        # ===== PriceMaster =====
        await db.execute('''
            CREATE TABLE IF NOT EXISTS price_list (
                id INTEGER PRIMARY KEY,
                city TEXT,
                brand TEXT,
                model TEXT,
                year_from INTEGER,
                year_to INTEGER,
                service_name TEXT,
                price_from INTEGER,
                price_to INTEGER,
                currency TEXT DEFAULT 'KZT',
                confidence TEXT DEFAULT 'high',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # ===== Платежи и подписки =====
        await db.execute('''
            CREATE TABLE IF NOT EXISTS subscriptions (
                id INTEGER PRIMARY KEY,
                entity_type TEXT,
                entity_id INTEGER,
                plan TEXT,
                start_date TIMESTAMP,
                end_date TIMESTAMP,
                auto_renew BOOLEAN,
                payment_method TEXT
            )
        ''')
        await db.execute('''
            CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY,
                user_id INTEGER,
                amount INTEGER,
                type TEXT,
                description TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # ===== ИИ =====
        await db.execute('''
            CREATE TABLE IF NOT EXISTS paid_diagnostics (
                id INTEGER PRIMARY KEY,
                user_id INTEGER,
                query TEXT,
                car_context TEXT,
                report_text TEXT,
                payment_amount INTEGER,
                status TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        await db.execute('''
            CREATE TABLE IF NOT EXISTS ai_chat_history (
                id INTEGER PRIMARY KEY,
                user_id INTEGER,
                role TEXT,
                message TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # ===== Тендеры на запчасти =====
        await db.execute('''
            CREATE TABLE IF NOT EXISTS part_requests (
                id INTEGER PRIMARY KEY,
                user_id INTEGER,
                city TEXT,
                part_name TEXT,
                car_info TEXT,
                comment TEXT,
                photo TEXT,
                status TEXT DEFAULT 'new',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                accepted_by INTEGER,
                accepted_at TIMESTAMP,
                client_chat_id INTEGER,
                client_message_id INTEGER,
                FOREIGN KEY (user_id) REFERENCES users(telegram_id)
            )
        ''')
        await db.execute('''
            CREATE TABLE IF NOT EXISTS part_offers (
                id INTEGER PRIMARY KEY,
                request_id INTEGER,
                supplier_id INTEGER,
                price INTEGER,
                comment TEXT,
                is_selected BOOLEAN DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (request_id) REFERENCES part_requests(id),
                FOREIGN KEY (supplier_id) REFERENCES suppliers(id)
            )
        ''')

        # ===== Заявки на партнёрство =====
        await db.execute('''
            CREATE TABLE IF NOT EXISTS partner_requests (
                id INTEGER PRIMARY KEY,
                user_id INTEGER,
                city TEXT,
                partner_type TEXT,
                name TEXT,
                address TEXT,
                phone TEXT,
                work_hours TEXT,
                categories TEXT,
                boxes INTEGER,
                duration INTEGER,
                supplier_type TEXT,
                delivery_available BOOLEAN,
                service_subtype TEXT,
                status TEXT DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                reviewed_at TIMESTAMP,
                reviewed_by INTEGER,
                FOREIGN KEY (user_id) REFERENCES users(telegram_id)
            )
        ''')

        # ===== Автопомощь =====
        await db.execute('''
            CREATE TABLE IF NOT EXISTS roadside_offers (
                id INTEGER PRIMARY KEY,
                request_id INTEGER,
                specialist_id INTEGER,
                price INTEGER,
                is_selected BOOLEAN DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (request_id) REFERENCES requests(id),
                FOREIGN KEY (specialist_id) REFERENCES suppliers(id)
            )
        ''')

        # ===== Срочные услуги =====
        await db.execute('''
            CREATE TABLE IF NOT EXISTS service_providers (
                id INTEGER PRIMARY KEY,
                service_type TEXT NOT NULL,
                name TEXT NOT NULL,
                city_id INTEGER NOT NULL,
                admin_id INTEGER NOT NULL,
                phone TEXT,
                address TEXT,
                rating REAL DEFAULT 0,
                reviews_count INTEGER DEFAULT 0,
                subscription_until TIMESTAMP,
                FOREIGN KEY (city_id) REFERENCES cities(id),
                FOREIGN KEY (admin_id) REFERENCES users(telegram_id)
            )
        ''')
        await db.execute('''
            CREATE TABLE IF NOT EXISTS service_offers (
                id INTEGER PRIMARY KEY,
                request_id INTEGER NOT NULL,
                provider_id INTEGER NOT NULL,
                price INTEGER NOT NULL,
                is_selected BOOLEAN DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (request_id) REFERENCES requests(id),
                FOREIGN KEY (provider_id) REFERENCES service_providers(id)
            )
        ''')

        # ===== Индексы =====
        await db.execute("CREATE INDEX IF NOT EXISTS idx_requests_user_id ON requests(user_id)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_requests_city_status ON requests(city, status)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_wash_slots_wash_id ON wash_slots(wash_id)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_wash_slots_datetime ON wash_slots(datetime)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_reviews_entity ON reviews(entity_type, entity_id)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_service_providers_city_type ON service_providers(city_id, service_type)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_part_requests_user_id ON part_requests(user_id)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_part_offers_request_id ON part_offers(request_id)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_tow_offers_request_id ON tow_offers(request_id)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_roadside_offers_request_id ON roadside_offers(request_id)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_service_offers_request_id ON service_offers(request_id)")

        await db.commit()

        # ===== Начальные данные =====
        cursor = await db.execute("SELECT COUNT(*) FROM cities")
        count = await cursor.fetchone()
        if count[0] == 0:
            cities = [("Талдыкорган",), ("Алматы",), ("Астана",), ("Шымкент",)]
            await db.executemany("INSERT INTO cities (name) VALUES (?)", cities)
            await db.commit()

        cursor = await db.execute("SELECT COUNT(*) FROM categories")
        count = await cursor.fetchone()
        if count[0] == 0:
            cursor = await db.execute("SELECT id FROM cities")
            city_ids = [row[0] for row in await cursor.fetchall()]
            base_categories = [
                "Ремонт двигателя", "Ремонт ходовой", "Электрика", "Кузовной ремонт",
                "Шиномонтаж", "Ремонт кондиционеров", "Диагностика",
                "Техническое обслуживание (ТО)", "Ремонт тормозной системы",
                "Ремонт выхлопной системы", "Ремонт рулевого управления",
                "Ремонт трансмиссии", "Ремонт топливной системы",
                "Ремонт системы охлаждения", "Автоэлектрик", "Ремонт салона"
            ]
            for city_id in city_ids:
                for cat_name in base_categories:
                    await db.execute("INSERT INTO categories (name, city_id) VALUES (?, ?)", (cat_name, city_id))
            await db.commit()

            subcategories_data = {
                "Ремонт двигателя": ["Капитальный ремонт", "Замена ГРМ", "Замена прокладки ГБЦ", "Диагностика двигателя"],
                "Кузовной ремонт": ["Ремонт бампера", "Покраска", "Рихтовка"],
                "Ремонт салона": ["Перетяжка салона кожей", "Перетяжка панелей", "Изготовление чехлов", "Перетяжка потолка", "Перетяжка ковриков", "Шумоизоляция", "Химчистка салона"]
            }
            for cat_name, subs in subcategories_data.items():
                cursor = await db.execute("SELECT id FROM categories WHERE name = ? LIMIT 1", (cat_name,))
                cat_id = await cursor.fetchone()
                if cat_id:
                    cat_id = cat_id[0]
                    for sub_name in subs:
                        await db.execute("INSERT INTO subcategories (name, category_id) VALUES (?, ?)", (sub_name, cat_id))
            await db.commit()

    print("✅ База данных успешно инициализирована.")

if __name__ == "__main__":
    asyncio.run(init_db())