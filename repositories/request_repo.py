# repositories/request_repo.py
import json
from typing import Optional, List
from .base import BaseRepository
from models.request import Request

class RequestRepository(BaseRepository[Request]):
    async def create(self, data: dict) -> int:
        if "subcategories" in data and isinstance(data["subcategories"], list):
            data["subcategories"] = json.dumps(data["subcategories"])
        columns = ", ".join(data.keys())
        placeholders = ", ".join(["?"] * len(data))
        query = f"INSERT INTO requests ({columns}) VALUES ({placeholders})"
        cursor = await self._execute(query, tuple(data.values()))
        await self.conn.commit()
        return cursor.lastrowid

    async def update(self, request_id: int, data: dict) -> None:
        if "subcategories" in data and isinstance(data["subcategories"], list):
            data["subcategories"] = json.dumps(data["subcategories"])
        set_clause = ", ".join([f"{k} = ?" for k in data.keys()])
        query = f"UPDATE requests SET {set_clause} WHERE id = ?"
        await self._execute(query, tuple(data.values()) + (request_id,))
        await self.conn.commit()

    async def get_by_id(self, request_id: int) -> Optional[Request]:
        row = await self._fetch_one("SELECT * FROM requests WHERE id = ?", (request_id,))
        if not row:
            return None
        cursor = await self.conn.execute("PRAGMA table_info(requests)")
        columns = await cursor.fetchall()
        keys = [col[1] for col in columns]
        data = dict(zip(keys, row))
        if data.get("subcategories"):
            data["subcategories"] = json.loads(data["subcategories"])
        return Request(**data)

    async def get_by_user_id(self, user_id: int, limit: int = 20) -> List[Request]:
        rows = await self._fetch_all(
            "SELECT * FROM requests WHERE user_id = ? ORDER BY created_at DESC LIMIT ?",
            (user_id, limit)
        )
        if not rows:
            return []
        cursor = await self.conn.execute("PRAGMA table_info(requests)")
        columns = await cursor.fetchall()
        keys = [col[1] for col in columns]
        result = []
        for row in rows:
            data = dict(zip(keys, row))
            if data.get("subcategories"):
                data["subcategories"] = json.loads(data["subcategories"])
            result.append(Request(**data))
        return result

    async def get_by_station_id(self, station_id: int) -> List[Request]:
        """
        Возвращает заявки:
        - все новые заявки на СТО (status='new' и type='sto')
        - заявки, назначенные на это СТО (accepted_by = station_id) со статусами new, accepted, in_progress
        """
        rows = await self._fetch_all(
            "SELECT * FROM requests WHERE (status = 'new' AND type = 'sto') OR (accepted_by = ? AND status IN ('new', 'accepted', 'in_progress'))",
            (station_id,)
        )
        if not rows:
            return []
        cursor = await self.conn.execute("PRAGMA table_info(requests)")
        columns = await cursor.fetchall()
        keys = [col[1] for col in columns]
        result = []
        for row in rows:
            data = dict(zip(keys, row))
            if data.get("subcategories"):
                data["subcategories"] = json.loads(data["subcategories"])
            result.append(Request(**data))
        return result

    async def get_client_info(self, user_id: int) -> str:
        cursor = await self._fetch_one(
            "SELECT full_name, phone FROM users WHERE telegram_id = ?", (user_id,)
        )
        if cursor:
            name, phone = cursor
            return f"{name or 'Не указан'} (📞 {phone or 'не указан'})"
        return "Неизвестный клиент"