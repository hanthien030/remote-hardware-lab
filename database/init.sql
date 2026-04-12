-- =================================================================
-- TẠO DATABASE
-- =================================================================
CREATE DATABASE IF NOT EXISTS remote_lab;
USE remote_lab;

-- =================================================================
-- BẢNG USERS - Quản lý người dùng
-- =================================================================
CREATE TABLE IF NOT EXISTS `users` (
  `id` INT AUTO_INCREMENT PRIMARY KEY,
  `username` VARCHAR(50) NOT NULL UNIQUE,
  `password` VARCHAR(255) NOT NULL,
  `email` VARCHAR(255) NULL UNIQUE,
  `full_name` VARCHAR(100) NULL,
  `role` ENUM('admin','user') NOT NULL DEFAULT 'user',
  `status` ENUM('pending','active','blocked') NOT NULL DEFAULT 'pending',
  `ssh_port` INT NULL UNIQUE,
  `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- =================================================================
-- BẢNG DEVICE_IDENTITIES - Định danh thiết bị qua VID/PID
-- =================================================================
CREATE TABLE IF NOT EXISTS `device_identities` (
  `id` INT AUTO_INCREMENT PRIMARY KEY,
  `vendor_id` VARCHAR(10) NOT NULL,
  `product_id` VARCHAR(10) NOT NULL,
  `device_type` VARCHAR(100) NOT NULL,
  `description` TEXT NULL,
  UNIQUE KEY `vendor_product_unique` (`vendor_id`, `product_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- =================================================================
-- BẢNG DEVICES - Quản lý thiết bị phần cứng
-- =================================================================
CREATE TABLE IF NOT EXISTS `devices` (
  `id` INT AUTO_INCREMENT PRIMARY KEY,
  `port` VARCHAR(255) NULL,                     -- Bỏ UNIQUE, cho phép NULL
  `serial_number` VARCHAR(255) NULL UNIQUE,
  `mac_address` VARCHAR(17) NULL UNIQUE, -- VD: '6c:c8:40:55:63:dc'   -- Cho phép NULL, nhưng nếu có thì phải là duy nhất
  `type` VARCHAR(100) NOT NULL,
  `tag_name` VARCHAR(100) NOT NULL UNIQUE,
  `device_name` VARCHAR(255) NULL,
  `status` ENUM('connected','disconnected') NOT NULL DEFAULT 'disconnected',
  `usage_mode` ENUM('free','share','block') NOT NULL DEFAULT 'free',
  `board_class` ENUM('esp32','esp8266','arduino_uno') DEFAULT NULL,
  `review_state` ENUM('pending_review','approved') NOT NULL DEFAULT 'pending_review',
  -- ==============(LOCK)_==============
  `is_virtualized` BOOLEAN NOT NULL DEFAULT FALSE,
  `locked_by_user` VARCHAR(50) NULL,
  -- ===================================
  `last_seen` TIMESTAMP NULL,
  `in_use_by` VARCHAR(50) NULL,
  `used_at` TIMESTAMP NULL,
  `vendor_id` VARCHAR(10) NULL,
  `product_id` VARCHAR(10) NULL,
  -- CÁC CỠ MỚI CHO TÍNH NĂNG ÁO HÀ --
  `total_slots` INT NOT NULL DEFAULT 1,
  `slot_config` JSON NULL,
  `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (`in_use_by`) REFERENCES `users`(`username`) ON DELETE SET NULL ON UPDATE CASCADE,
  FOREIGN KEY (`locked_by_user`) REFERENCES `users`(`username`) ON DELETE SET NULL ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- =================================================================
-- BẢNG ASSIGNMENTS - Phân quyền sử dụng thiết bị
-- =================================================================
CREATE TABLE IF NOT EXISTS `assignments` (
  `id` INT AUTO_INCREMENT PRIMARY KEY,
  `user_id` VARCHAR(50) NOT NULL,
  `tag_name` VARCHAR(100) NOT NULL,
  `expires_at` DATETIME NOT NULL,
  `is_active` BOOLEAN DEFAULT TRUE,
  `created_by` VARCHAR(50) NULL,
  `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY `unique_user_device` (`user_id`, `tag_name`),
  FOREIGN KEY (`user_id`) REFERENCES `users`(`username`) ON DELETE CASCADE ON UPDATE CASCADE,
  FOREIGN KEY (`tag_name`) REFERENCES `devices`(`tag_name`) ON DELETE CASCADE ON UPDATE CASCADE,
  FOREIGN KEY (`created_by`) REFERENCES `users`(`username`) ON DELETE SET NULL ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- =================================================================
-- BẢNG LOGS - Ghi log hành động
-- =================================================================
CREATE TABLE IF NOT EXISTS `logs` (
  `id` INT AUTO_INCREMENT PRIMARY KEY,
  `username` VARCHAR(50) NOT NULL,
  `action` VARCHAR(255) NOT NULL,
  `timestamp` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `success` BOOLEAN DEFAULT TRUE,
  `details` JSON NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- =================================================================
-- BẢNG FLASH_QUEUE - Hàng đợi nạp firmware (Phase 3C)
-- =================================================================
CREATE TABLE IF NOT EXISTS `flash_queue` (
  `id` INT AUTO_INCREMENT PRIMARY KEY,
  `user_id` VARCHAR(50) NOT NULL,
  `tag_name` VARCHAR(50) NOT NULL,         -- thiết bị yêu cầu
  `board_type` VARCHAR(20) NOT NULL,       -- esp32/esp8266/arduino_uno
  `firmware_path` VARCHAR(255) NOT NULL,   -- đường dẫn file .bin
  `baud_rate` INT NOT NULL DEFAULT 115200, -- baud cho serial capture sau flash
  `status` ENUM('waiting','flashing','success','failed','cancelled') NOT NULL DEFAULT 'waiting',
  `created_at` DATETIME DEFAULT NOW(),
  `started_at` DATETIME NULL,
  `completed_at` DATETIME NULL,
  `log_output` TEXT NULL,                  -- log từ esptool
  `serial_log` TEXT NULL,                  -- log từ serial monitor 1 phút
  KEY `idx_flash_queue_tag_status_created` (`tag_name`, `status`, `created_at`),
  KEY `idx_flash_queue_user_status_created` (`user_id`, `status`, `created_at`),
  KEY `idx_flash_queue_created_at` (`created_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- =================================================================
-- Dữ liệu khởi tạo
-- =================================================================

-- Tạo admin user với password là 'admin'
-- LƯU Ý: HASH NÀY CHỈ DÀNH CHO MÔI TRƯỜNG PHÁT TRIỂN.
-- Cần được thay thế bằng hash an toàn khi triển khai.
-- Werkzeug hash for 'admin': pbkdf2:sha256:260000$salt$hash
INSERT INTO `users` (`username`, `password`, `email`, `full_name`, `role`, `status`)
SELECT 'admin',
       'scrypt:32768:8:1$b6cpeObUVY1lAHfc$f896f37c0019654f56e3fecc9a52e93860b185842e263c295ff24e30688a43d641b96125031bcb68c86ba0c6a21de966590fd54363442f6e82d4e365bb844c4a', -- HASH Cá»¦A 'admin'
       'admin@remotelab.com',
       'System Administrator',
       'admin',
       'active'
WHERE NOT EXISTS (SELECT 1 FROM `users` WHERE `username` = 'admin');

-- Dữ liệu nhận dạng thiết bị mẫu
INSERT INTO `device_identities` (`vendor_id`, `product_id`, `device_type`, `description`) VALUES
('1a86', '7523', 'ESP_CH340', 'USB-Serial chip for NodeMCU, ESP8266 boards'),
('10c4', 'ea60', 'ESP_CP2102', 'Silicon Labs CP2102 for ESP32 DevKits'),
('2341', '0043', 'Arduino_Uno', 'Arduino Uno R3')
ON DUPLICATE KEY UPDATE device_type=VALUES(device_type);

-- =================================================================
-- CẬP NHẬT THÊM CỘT is_virtualized CHO device_identities
-- =================================================================
ALTER TABLE `device_identities` 
  ADD COLUMN `is_virtualized` BOOLEAN NOT NULL DEFAULT FALSE;

-- ESP32 (có MPU) -> ảo hóa được
UPDATE `device_identities` 
SET `is_virtualized` = TRUE 
WHERE `device_type` = 'ESP_CP2102';

-- ESP8266 (không MPU) -> không ảo hóa
UPDATE `device_identities` 
SET `is_virtualized` = FALSE 
WHERE `device_type` = 'ESP_CH340';

-- =================================================================
-- STORED PROCEDURE - Dọn dẹp assignments hết hạn
-- =================================================================
DELIMITER $$
CREATE PROCEDURE CleanupExpiredAssignments()
BEGIN
    UPDATE assignments
    SET is_active = FALSE
    WHERE is_active = TRUE AND expires_at <= NOW();
END$$
DELIMITER ;

-- =================================================================
-- EVENT - Tự động chạy stored procedure mỗi giờ
-- =================================================================
SET GLOBAL event_scheduler = ON;
CREATE EVENT IF NOT EXISTS `auto_cleanup_assignments`
ON SCHEDULE EVERY 1 HOUR
DO
  CALL CleanupExpiredAssignments();
