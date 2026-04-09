USE remote_lab;

SET @usage_mode_exists := (
  SELECT COUNT(*)
  FROM information_schema.columns
  WHERE table_schema = DATABASE()
    AND table_name = 'devices'
    AND column_name = 'usage_mode'
);

SET @sql := IF(
  @usage_mode_exists = 0,
  'ALTER TABLE `devices` ADD COLUMN `usage_mode` ENUM(''free'',''share'',''block'') NOT NULL DEFAULT ''free'' AFTER `status`',
  'SELECT ''devices.usage_mode already exists'''
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

UPDATE `devices`
SET `usage_mode` = 'free'
WHERE `usage_mode` IS NULL OR `usage_mode` = '';

ALTER TABLE `devices`
  MODIFY COLUMN `usage_mode` ENUM('free','share','block') NOT NULL DEFAULT 'free';
