-- Добавляем новые колонки
ALTER TABLE setting ADD COLUMN timeout_iterations INTEGER NOT NULL DEFAULT 350;
ALTER TABLE setting ADD COLUMN timeout_interval_secs INTEGER NOT NULL DEFAULT 9;

-- Обновляем существующие записи (на всякий случай)
UPDATE setting SET timeout_iterations = 350 WHERE timeout_iterations IS NULL;
UPDATE setting SET timeout_interval_secs = 9 WHERE timeout_interval_secs IS NULL;

-- Constraints будут проверяться на уровне приложения, так как SQLite ограничен в ALTER TABLE