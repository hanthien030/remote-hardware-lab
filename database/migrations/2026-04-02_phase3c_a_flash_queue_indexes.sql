USE remote_lab;

CREATE TABLE IF NOT EXISTS `flash_queue` (
  `id` INT AUTO_INCREMENT PRIMARY KEY,
  `user_id` VARCHAR(50) NOT NULL,
  `tag_name` VARCHAR(50) NOT NULL,
  `board_type` VARCHAR(20) NOT NULL,
  `firmware_path` VARCHAR(255) NOT NULL,
  `status` ENUM('waiting','flashing','success','failed','cancelled') NOT NULL DEFAULT 'waiting',
  `created_at` DATETIME DEFAULT NOW(),
  `started_at` DATETIME NULL,
  `completed_at` DATETIME NULL,
  `log_output` TEXT NULL,
  `serial_log` TEXT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

SET @idx_exists := (
  SELECT COUNT(*)
  FROM information_schema.statistics
  WHERE table_schema = DATABASE()
    AND table_name = 'flash_queue'
    AND index_name = 'idx_flash_queue_tag_status_created'
);
SET @sql := IF(
  @idx_exists = 0,
  'ALTER TABLE `flash_queue` ADD INDEX `idx_flash_queue_tag_status_created` (`tag_name`, `status`, `created_at`)',
  'SELECT ''idx_flash_queue_tag_status_created already exists'''
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @idx_exists := (
  SELECT COUNT(*)
  FROM information_schema.statistics
  WHERE table_schema = DATABASE()
    AND table_name = 'flash_queue'
    AND index_name = 'idx_flash_queue_user_status_created'
);
SET @sql := IF(
  @idx_exists = 0,
  'ALTER TABLE `flash_queue` ADD INDEX `idx_flash_queue_user_status_created` (`user_id`, `status`, `created_at`)',
  'SELECT ''idx_flash_queue_user_status_created already exists'''
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @idx_exists := (
  SELECT COUNT(*)
  FROM information_schema.statistics
  WHERE table_schema = DATABASE()
    AND table_name = 'flash_queue'
    AND index_name = 'idx_flash_queue_created_at'
);
SET @sql := IF(
  @idx_exists = 0,
  'ALTER TABLE `flash_queue` ADD INDEX `idx_flash_queue_created_at` (`created_at`)',
  'SELECT ''idx_flash_queue_created_at already exists'''
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;
