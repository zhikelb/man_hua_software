from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator


class Database:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.conn = sqlite3.connect(str(db_path))
        self.conn.row_factory = sqlite3.Row
        self._setup()

    def _setup(self) -> None:
        self.conn.execute("PRAGMA foreign_keys = ON;")
        self.conn.execute("PRAGMA journal_mode = WAL;")
        self.conn.execute("PRAGMA synchronous = NORMAL;")

        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS series (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                author TEXT NOT NULL DEFAULT '',
                total_episodes INTEGER NOT NULL DEFAULT 1,
                cover_path TEXT,
                is_favorite INTEGER NOT NULL DEFAULT 0,
                tags TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE UNIQUE INDEX IF NOT EXISTS idx_series_name_author
            ON series(name, author);

            CREATE TABLE IF NOT EXISTS episodes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                series_id INTEGER NOT NULL,
                episode_number INTEGER NOT NULL,
                folder_path TEXT NOT NULL,
                storage_mode TEXT NOT NULL DEFAULT 'reference',
                data_path TEXT,
                image_count INTEGER NOT NULL DEFAULT 0,
                is_read INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(series_id) REFERENCES series(id) ON DELETE CASCADE,
                UNIQUE(series_id, episode_number)
            );

            CREATE INDEX IF NOT EXISTS idx_episodes_series_id
            ON episodes(series_id);

            CREATE TABLE IF NOT EXISTS images (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                episode_id INTEGER NOT NULL,
                file_name TEXT NOT NULL,
                file_path TEXT NOT NULL,
                file_hash TEXT,
                sort_order INTEGER NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(episode_id) REFERENCES episodes(id) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_images_episode_order
            ON images(episode_id, sort_order);

            CREATE TABLE IF NOT EXISTS reading_progress (
                series_id INTEGER PRIMARY KEY,
                current_episode_id INTEGER NOT NULL,
                current_image_id INTEGER NOT NULL,
                last_read_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(series_id) REFERENCES series(id) ON DELETE CASCADE,
                FOREIGN KEY(current_episode_id) REFERENCES episodes(id) ON DELETE CASCADE,
                FOREIGN KEY(current_image_id) REFERENCES images(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS user_groups (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                sort_order INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS series_groups (
                series_id INTEGER NOT NULL,
                group_id INTEGER NOT NULL,
                added_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY(series_id, group_id),
                FOREIGN KEY(series_id) REFERENCES series(id) ON DELETE CASCADE,
                FOREIGN KEY(group_id) REFERENCES user_groups(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS bookmarks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                series_id INTEGER NOT NULL,
                episode_id INTEGER NOT NULL,
                image_id INTEGER NOT NULL,
                name TEXT NOT NULL DEFAULT '书签',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(series_id) REFERENCES series(id) ON DELETE CASCADE,
                FOREIGN KEY(episode_id) REFERENCES episodes(id) ON DELETE CASCADE,
                FOREIGN KEY(image_id) REFERENCES images(id) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_bookmarks_series
            ON bookmarks(series_id);
            """
        )
        self.conn.commit()

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        try:
            yield self.conn
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise

    def close(self) -> None:
        self.conn.close()
