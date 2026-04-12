USE remote_lab;

SET @baud_rate_exists := (
  SELECT COUNT(*)
  FROM information_schema.columns
  WHERE table_schema = DATABASE()
    AND table_name = 'flash_queue'
    AND column_name = 'baud_rate'
);

SET @sql := IF(
  @baud_rate_exists = 0,
  'ALTER TABLE `flash_queue` ADD COLUMN `baud_rate` INT NOT NULL DEFAULT 115200 AFTER `firmware_path`',
  'SELECT ''flash_queue.baud_rate already exists'''
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

UPDATE `flash_queue`
SET `baud_rate` = 115200
WHERE `baud_rate` IS NULL OR `baud_rate` <= 0;
