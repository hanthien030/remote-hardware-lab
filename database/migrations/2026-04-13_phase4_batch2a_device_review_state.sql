USE remote_lab;

SET @board_class_exists := (
  SELECT COUNT(*)
  FROM information_schema.columns
  WHERE table_schema = DATABASE()
    AND table_name = 'devices'
    AND column_name = 'board_class'
);

SET @sql := IF(
  @board_class_exists = 0,
  'ALTER TABLE `devices` ADD COLUMN `board_class` ENUM(''esp32'',''esp8266'',''arduino_uno'') DEFAULT NULL AFTER `usage_mode`',
  'SELECT ''devices.board_class already exists'''
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @review_state_exists := (
  SELECT COUNT(*)
  FROM information_schema.columns
  WHERE table_schema = DATABASE()
    AND table_name = 'devices'
    AND column_name = 'review_state'
);

SET @sql := IF(
  @review_state_exists = 0,
  'ALTER TABLE `devices` ADD COLUMN `review_state` ENUM(''pending_review'',''approved'') NOT NULL DEFAULT ''pending_review'' AFTER `board_class`',
  'SELECT ''devices.review_state already exists'''
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @sql := IF(
  @review_state_exists = 0,
  'UPDATE `devices` SET `review_state` = ''approved''',
  'SELECT ''devices.review_state backfill skipped'''
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;
