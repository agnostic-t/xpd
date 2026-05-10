import json
import sqlite3


class DataBase:
    def __init__(self, db_name="data.db"):
        self.connection = sqlite3.connect(db_name, check_same_thread=False)
        self.__create_table()

    def __create_table(self):
        with self.connection:
            self.connection.execute("""
                CREATE TABLE IF NOT EXISTS data (
                    key TEXT PRIMARY KEY,
                    value TEXT
                )
            """)

    def all(self):
        cursor = self.connection.cursor()
        cursor.execute("SELECT key FROM data")
        keys = [row[0] for row in cursor.fetchall()]
        return keys

    def set(self, key, value):
        serialized_value = json.dumps(value)

        with self.connection:
            self.connection.execute(
                """
                INSERT INTO data (key, value) VALUES (?, ?)
                ON CONFLICT(key) DO UPDATE SET value=excluded.value
            """,
                (key, serialized_value),
            )

    def ensure_set(self, key, value):
        if self.get(key) is None:
            self.set(key, value)

    def batch_set(self, items):
        with self.connection:
            self.connection.executemany(
                """
                INSERT INTO data (key, value) VALUES (?, ?)
                ON CONFLICT(key) DO UPDATE SET value=excluded.value
            """,
                [(key, json.dumps(value)) for key, value in items],
            )

    def get(self, key):
        cursor = self.connection.cursor()
        cursor.execute("SELECT value FROM data WHERE key = ?", (key,))
        result = cursor.fetchone()
        return json.loads(result[0]) if result else None

    def delete(self, key) -> bool:
        with self.connection:
            cursor = self.connection.cursor()
            cursor.execute("DELETE FROM data WHERE key = ?", (key,))
            return cursor.rowcount > 0

    def close(self):
        self.connection.close()
