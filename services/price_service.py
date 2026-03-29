import re
from thefuzz import fuzz
from transliterate import translit
import aiosqlite
from database import db

def normalize_text(text: str) -> str:
    if not text:
        return ""
    text = text.strip().lower()
    if re.search('[а-я]', text):
        try:
            text = translit(text, 'ru', reversed=True)
        except Exception:
            pass
    return text

class PriceService:
    async def find_services(self, city: str, brand: str, model: str, service: str):
        norm_brand = normalize_text(brand)
        norm_model = normalize_text(model)
        norm_service = normalize_text(service)

        async with db.session() as conn:
            rows = await conn.execute(
                "SELECT ss.id, ss.station_id, s.name, s.rating, ss.price, ss.service_name, ss.brand, ss.model "
                "FROM station_services ss JOIN stations s ON ss.station_id = s.id "
                "WHERE LOWER(ss.city) = LOWER(?)",
                (city,)
            )
            all_services = await rows.fetchall()

        matched = []
        for rec in all_services:
            service_id, station_id, station_name, rating, price, service_name, db_brand, db_model = rec
            db_brand_norm = normalize_text(db_brand)
            db_model_norm = normalize_text(db_model)
            db_service_norm = normalize_text(service_name)

            brand_score = fuzz.token_sort_ratio(norm_brand, db_brand_norm)
            model_score = fuzz.token_sort_ratio(norm_model, db_model_norm)
            service_score = fuzz.token_set_ratio(norm_service, db_service_norm)

            total_score = brand_score * 0.1 + model_score * 0.1 + service_score * 0.8
            if total_score >= 70:
                matched.append((total_score, service_id, station_id, station_name, rating, price, service_name, db_brand, db_model))

        matched.sort(key=lambda x: x[0], reverse=True)
        return matched