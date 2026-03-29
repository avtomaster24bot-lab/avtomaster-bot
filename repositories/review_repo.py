# repositories/review_repo.py
from .base import BaseRepository
from models.review import Review

class ReviewRepository(BaseRepository[Review]):
    async def create(self, data: dict) -> int:
        cursor = await self._execute(
            "INSERT INTO reviews (user_id, entity_type, entity_id, rating, comment, moderated, hidden) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (data['user_id'], data['entity_type'], data['entity_id'], data['rating'], data.get('comment', ''), 0, 0)
        )
        await self.conn.commit()
        return cursor.lastrowid

    async def get_by_entity(self, entity_type: str, entity_id: int, moderated: bool = True, hidden: bool = False, limit: int = 10, offset: int = 0):
        query = """
            SELECT r.*, u.full_name, u.display_name_choice
            FROM reviews r
            JOIN users u ON r.user_id = u.telegram_id
            WHERE r.entity_type = ? AND r.entity_id = ? AND r.moderated = ? AND r.hidden = ?
            ORDER BY r.created_at DESC
            LIMIT ? OFFSET ?
        """
        rows = await self._fetch_all(query, (entity_type, entity_id, 1 if moderated else 0, 1 if hidden else 0, limit, offset))
        keys = [d[0] for d in (await self.conn.execute("PRAGMA table_info(reviews)")).fetchall()] + ['full_name', 'display_name_choice']
        return [dict(zip(keys, row)) for row in rows]

    async def get_unmoderated(self, city: str, limit: int = 50):
        """Возвращает немодерированные отзывы на объекты в указанном городе."""
        query = """
            SELECT r.id, r.entity_type, r.entity_id, r.rating, r.comment, u.telegram_id, u.full_name
            FROM reviews r
            JOIN users u ON r.user_id = u.telegram_id
            WHERE r.moderated = 0
              AND (
                  (r.entity_type IN ('station', 'sto') AND EXISTS (SELECT 1 FROM stations WHERE id = r.entity_id AND city_id = (SELECT id FROM cities WHERE name = ?)))
                  OR (r.entity_type = 'car_wash' AND EXISTS (SELECT 1 FROM car_washes WHERE id = r.entity_id AND city_id = (SELECT id FROM cities WHERE name = ?)))
                  OR (r.entity_type = 'tow_truck' AND EXISTS (SELECT 1 FROM tow_trucks WHERE id = r.entity_id AND city_id = (SELECT id FROM cities WHERE name = ?)))
                  OR (r.entity_type = 'supplier' AND EXISTS (SELECT 1 FROM suppliers WHERE id = r.entity_id AND city_id = (SELECT id FROM cities WHERE name = ?)))
                  OR (r.entity_type = 'service_provider' AND EXISTS (SELECT 1 FROM service_providers WHERE id = r.entity_id AND city_id = (SELECT id FROM cities WHERE name = ?)))
              )
            ORDER BY r.created_at DESC
            LIMIT ?
        """
        rows = await self._fetch_all(query, (city, city, city, city, city, limit))
        return rows

    async def moderate(self, review_id: int, approve: bool):
        if approve:
            await self._execute("UPDATE reviews SET moderated = 1, hidden = 0 WHERE id = ?", (review_id,))
        else:
            await self._execute("UPDATE reviews SET moderated = 1, hidden = 1 WHERE id = ?", (review_id,))
        await self.conn.commit()
        # Обновление рейтинга соответствующей сущности
        row = await self._fetch_one("SELECT entity_type, entity_id FROM reviews WHERE id = ?", (review_id,))
        if row:
            etype, eid = row
            avg = await self._fetch_one("SELECT AVG(rating) FROM reviews WHERE entity_type = ? AND entity_id = ? AND moderated = 1 AND hidden = 0", (etype, eid))
            avg_rating = avg[0] if avg[0] else 0
            cnt = await self._fetch_one("SELECT COUNT(*) FROM reviews WHERE entity_type = ? AND entity_id = ? AND moderated = 1 AND hidden = 0", (etype, eid))
            count_val = cnt[0] if cnt else 0
            if etype in ('station', 'sto'):
                await self._execute("UPDATE stations SET rating = ?, reviews_count = ? WHERE id = ?", (avg_rating, count_val, eid))
            elif etype == 'car_wash':
                await self._execute("UPDATE car_washes SET rating = ?, reviews_count = ? WHERE id = ?", (avg_rating, count_val, eid))
            elif etype == 'tow_truck':
                await self._execute("UPDATE tow_trucks SET rating = ?, reviews_count = ? WHERE id = ?", (avg_rating, count_val, eid))
            elif etype == 'supplier':
                await self._execute("UPDATE suppliers SET rating = ?, reviews_count = ? WHERE id = ?", (avg_rating, count_val, eid))
            elif etype == 'service_provider':
                await self._execute("UPDATE service_providers SET rating = ?, reviews_count = ? WHERE id = ?", (avg_rating, count_val, eid))
            await self.conn.commit()