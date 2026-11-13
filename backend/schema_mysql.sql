CREATE DATABASE IF NOT EXISTS `ganpati_shop_db` DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE `ganpati_shop_db`;

-- Drop in reverse order of foreign-key dependency
DROP TABLE IF EXISTS `restock_alerts`;
DROP TABLE IF EXISTS `branch_stock`;
DROP TABLE IF EXISTS `reviews`;
DROP TABLE IF EXISTS `user_cart_items`;
DROP TABLE IF EXISTS `recently_viewed`;
DROP TABLE IF EXISTS `password_resets`;
DROP TABLE IF EXISTS `user_wishlist`;
DROP TABLE IF EXISTS `bookings`;
DROP TABLE IF EXISTS `branches`;
DROP TABLE IF EXISTS `idols`;
DROP TABLE IF EXISTS `users`;

-- 1. USERS (registration, login, password recovery)
CREATE TABLE `users` (
    `id` INT AUTO_INCREMENT PRIMARY KEY,
    `username` VARCHAR(100) NOT NULL UNIQUE,
    `email` VARCHAR(150) NOT NULL UNIQUE,
    `password` VARCHAR(255) NOT NULL,              -- stored as a password hash
    `phone` VARCHAR(20) NULL,
    `address` TEXT NULL,
    `security_question` VARCHAR(255) DEFAULT 'What is your favourite sweet?',
    `security_answer` VARCHAR(255) DEFAULT 'modak',
    `role` ENUM('user', 'admin') DEFAULT 'user',
    `is_active` TINYINT(1) NOT NULL DEFAULT 1,           -- admin can deactivate an account
    `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 2. IDOLS / CATALOGUE
CREATE TABLE `idols` (
    `id` INT AUTO_INCREMENT PRIMARY KEY,
    `name` VARCHAR(150) NOT NULL,
    `category` VARCHAR(100) NOT NULL,
    `price` DECIMAL(10,2) NOT NULL,
    `size` INT NOT NULL DEFAULT 0,
    `material` VARCHAR(100) NOT NULL,
    `design_type` VARCHAR(150) NOT NULL,
    `availability` VARCHAR(50) DEFAULT 'In Stock',
    `stock_count` INT DEFAULT 15,
    `low_stock_limit` INT NOT NULL DEFAULT 5,            -- 'Low Stock' warning level
    `is_active` TINYINT(1) NOT NULL DEFAULT 1,           -- 0 = hidden from the shop
    `description` TEXT,
    `rating` DECIMAL(2,1) DEFAULT 4.9,
    `image_url` VARCHAR(255) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 3. BRANCHES (branch management)
CREATE TABLE `branches` (
    `id` INT AUTO_INCREMENT PRIMARY KEY,
    `branch_name` VARCHAR(150) NOT NULL,
    `address` VARCHAR(255) NOT NULL,
    `city` VARCHAR(100) NOT NULL,
    `phone` VARCHAR(20) NOT NULL,
    `manager_name` VARCHAR(150) NOT NULL,
    `status` VARCHAR(20) NOT NULL DEFAULT 'Active',
    `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 4. BOOKINGS (order details & status)
CREATE TABLE `bookings` (
    `id` INT AUTO_INCREMENT PRIMARY KEY,
    `booking_id` VARCHAR(50) NOT NULL UNIQUE,
    `user_id` INT NULL,                                  -- customer account that made the booking
    `branch_id` INT NULL,                                -- branch chosen at booking time
    `customer_name` VARCHAR(150) NOT NULL,
    `contact_number` VARCHAR(20) NOT NULL,
    `email` VARCHAR(150),
    `idol_id` INT NOT NULL,
    `quantity` INT NOT NULL DEFAULT 1,
    `total_price` DECIMAL(10,2) NOT NULL,
    `booking_date` DATE NOT NULL,
    `delivery_option` VARCHAR(50) NOT NULL,
    `delivery_address` TEXT,
    `payment_status` VARCHAR(50) DEFAULT 'Advance Paid (₹500)',
    `payment_type` VARCHAR(30) NULL,                     -- demo payment: full / advance
    `payment_method` VARCHAR(30) NULL,                   -- upi / netbanking / card / cash
    `receipt_no` VARCHAR(40) NULL,
    `txn_id` VARCHAR(40) NULL,
    `status` ENUM('Confirmed', 'Ready for Pickup', 'Out for Delivery', 'Delivered', 'Cancelled') DEFAULT 'Confirmed',
    `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT `fk_bookings_idols` FOREIGN KEY (`idol_id`) REFERENCES `idols` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 4b. WISHLIST & CART (per logged-in customer)
CREATE TABLE `user_wishlist` (
    `id` INT AUTO_INCREMENT PRIMARY KEY,
    `user_id` INT NOT NULL,
    `idol_id` INT NOT NULL,
    `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY `uq_wish_user_idol` (`user_id`, `idol_id`),
    CONSTRAINT `fk_uwl_idol` FOREIGN KEY (`idol_id`) REFERENCES `idols` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE `user_cart_items` (
    `id` INT AUTO_INCREMENT PRIMARY KEY,
    `user_id` INT NOT NULL,
    `idol_id` INT NOT NULL,
    `quantity` INT NOT NULL DEFAULT 1,
    `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY `uq_cart_user_idol` (`user_id`, `idol_id`),
    CONSTRAINT `fk_uci_idol` FOREIGN KEY (`idol_id`) REFERENCES `idols` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 5. REVIEWS & TESTIMONIALS
CREATE TABLE `reviews` (
    `id` INT AUTO_INCREMENT PRIMARY KEY,
    `customer_name` VARCHAR(150) NOT NULL,
    `idol_id` INT NULL,
    `rating` INT NOT NULL DEFAULT 5,
    `comment` TEXT NOT NULL,
    `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT `fk_reviews_idols` FOREIGN KEY (`idol_id`) REFERENCES `idols` (`id`) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 6. BRANCH STOCK (units held by each branch)
CREATE TABLE `branch_stock` (
    `id` INT AUTO_INCREMENT PRIMARY KEY,
    `branch_id` INT NOT NULL,
    `idol_id` INT NOT NULL,
    `stock_count` INT NOT NULL DEFAULT 0,
    UNIQUE KEY `uq_branch_idol` (`branch_id`, `idol_id`),
    CONSTRAINT `fk_bs_branch` FOREIGN KEY (`branch_id`) REFERENCES `branches` (`id`) ON DELETE CASCADE,
    CONSTRAINT `fk_bs_idol` FOREIGN KEY (`idol_id`) REFERENCES `idols` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 7. RESTOCK ALERTS ("notify me when available")
CREATE TABLE `restock_alerts` (
    `id` INT AUTO_INCREMENT PRIMARY KEY,
    `user_id` INT NOT NULL,
    `idol_id` INT NOT NULL,
    `email` VARCHAR(150) NULL,
    `status` VARCHAR(20) NOT NULL DEFAULT 'Waiting',      -- Waiting / Ready / Notified
    `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY `uq_alert_user_idol` (`user_id`, `idol_id`),
    CONSTRAINT `fk_ra_idol` FOREIGN KEY (`idol_id`) REFERENCES `idols` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ---------------------------------------------------------
-- SEED DATA
-- ---------------------------------------------------------
-- Admin login:  username admin  /  password admin123   (change it after first login)
INSERT INTO `users` (`username`, `email`, `password`, `phone`, `address`, `security_question`, `security_answer`, `role`) VALUES
('admin', 'admin@bappastore.com', 'pbkdf2:sha256:1000000$HgsxCbEVJktW7h3C$2e2ccfd6cb9a65a8cb78f8df144225f84d744668d2c89ac77876ecc91da20882', '9876543210', 'Dadar Workshop, Mumbai', 'What is your favourite sweet?', 'modak', 'admin');

INSERT INTO `idols` (`name`, `category`, `price`, `size`, `material`, `design_type`, `availability`, `stock_count`, `description`, `rating`, `image_url`) VALUES
('Jasvandi Ganpati', 'Ready Ganpati', 8500.00, 21, 'Clay & Shadu Mati', 'Jasvandi Sitting Shringar', 'In Stock', 12, 'Handcrafted traditional Jasvandi throne idol with rich shringar finish.', 4.9, '/static/images/bappa_1.png'),
('Dagdu Sheth Ganpati', 'Ready Ganpati', 9500.00, 21, 'Shadu Mati', 'Royal Dagadusheth Darbar', 'In Stock', 8, 'Majestic Dagadusheth Halwai style idol with royal Mukut & ornate jewellery.', 5.0, '/static/images/bappa_3.png'),
('Asaan Mandi Red', 'Ready Ganpati', 10000.00, 24, 'Shadu Clay', 'Vibrant Red Baithak', 'In Stock', 6, 'Grand 24-inch seated Ganesha adorned with red royal silk drape.', 4.9, '/static/images/bappa_7.png'),
('Bal Ganesh with Load', 'Ready Ganpati', 4000.00, 7, 'Eco Clay', 'Cute Bal Roop with Pillow', 'In Stock', 20, 'Adorable child Ganesha resting on a traditional royal load.', 4.9, '/static/images/bappa_25.png'),
('Bal Ganesh Idol', 'Ready Ganpati', 7500.00, 12, 'Shadu Mati', 'Playful Bal Avatar', 'In Stock', 15, 'Classic 12-inch Bal Ganesh in a playful pose on a decorative chowki.', 4.8, '/static/images/bappa_28.png'),
('Lalbaug Style Grand Idol', 'Ready Ganpati', 8500.00, 22, 'Shadu Mati', 'Lalbaug Darbar Posture', 'In Stock', 10, 'Iconic blessing posture idol with high detailed crown.', 5.0, '/static/images/bappa_17.png'),
('Undir Ganpati (Eco-Friendly)', 'Ecofriendly', 5500.00, 16, '100% Shadu Eco Clay', 'Undir Swari', 'In Stock', 14, 'Natural eco-friendly clay idol on divine Mushak vehicle base.', 4.8, '/static/images/bappa_2.png'),
('Asaan Mandi with Load (Eco)', 'Ecofriendly', 6000.00, 18, 'Natural River Clay', 'Royal Baithak with Pillow', 'In Stock', 12, '100% soluble eco clay idol painted with organic herbal colors.', 4.9, '/static/images/bappa_5.png'),
('SuryaFul Ganpati (Eco)', 'Ecofriendly', 4500.00, 10, 'Natural Shadu Clay', 'Sunflower Halo Design', 'In Stock', 18, 'Artistic clay idol with a golden crown, ideal for compact home sthapana.', 4.7, '/static/images/bappa_26.png'),
('Mandi Ganpati (Eco Clay)', 'Ecofriendly', 5500.00, 7, 'Pure Clay', 'Traditional Chowki Mandi', 'In Stock', 25, 'Environment safe organic clay idol with natural turmeric and geru finish.', 4.9, '/static/images/bappa_29.png'),
('Asaan Mandi Ganpati', 'PoP Ganpati', 9500.00, 22, 'Plaster of Paris (PoP)', 'Classic Mandi Shringar', 'In Stock', 10, 'Lightweight, ultra-durable with high-gloss diamond gemstone work.', 4.8, '/static/images/bappa_4.png'),
('Vitthal Ganpati', 'PoP Ganpati', 6900.00, 18, 'PoP Fine Cast', 'Vitthal Avatar', 'In Stock', 15, 'Unique Pandharpur Vithoba posture with intricate jewellery detail.', 4.9, '/static/images/bappa_27.png'),
('Asaan Mandi White', 'PoP Ganpati', 10000.00, 24, 'PoP Finish', 'Pure Pearl White & Gold', 'In Stock', 7, 'Grand 24-inch pearl white idol with glittering golden borders.', 4.8, '/static/images/bappa_6.png'),
('Shahi Baithak PoP Bappa', 'PoP Ganpati', 7500.00, 18, 'PoP Cast', 'Royal Throne Seated', 'In Stock', 9, 'Vibrant festive colors, lightweight durable frame with diamond mukut.', 4.7, '/static/images/bappa_17.png'),
('Festive Silk Dhoti & Shawl Set', 'Add-Ons', 450.00, 0, 'Banarasi Silk', 'Peethambari Gold Zari', 'In Stock', 50, 'Pure silk yellow-gold Dhoti with embroidered border for Bappa.', 4.8, '/static/images/dhoti.jpg'),
('Royal Pearl Kan-Kundal (Earrings)', 'Add-Ons', 250.00, 0, 'Gold Plated Alloy', 'Kundan Floral Ear Hangings', 'In Stock', 60, 'Set of 2 royal traditional earrings for Ganesha idols (12-24 inch).', 4.9, '/static/images/earrings.jpg'),
('Kolhapuri Shahi Pheta (Turban)', 'Add-Ons', 550.00, 0, 'Velvet & Silk', 'Royal Maratha Pheta with Brooch', 'In Stock', 40, 'Stitched royal turban with pearls, feather brooch and golden lace.', 5.0, '/static/images/pheta.jpg'),
('Pure Brass Modak & Mushak (Mouse)', 'Add-Ons', 850.00, 0, 'Solid Brass', 'Puja Offerings Set', 'In Stock', 35, 'Heavy solid brass Mushak raj idol and engraved Modak prasad bowl.', 4.9, '/static/images/mushak_modak.jpg'),
('Complete Temple Jewellery Set', 'Add-Ons', 1200.00, 0, 'Micro Gold Polish', 'Grand Shringar Set', 'In Stock', 30, 'Includes 2 necklaces, 4 bangles, armlets, and sparkling crown brooch.', 4.9, '/static/images/jewellery.jpg');

INSERT INTO `reviews` (`customer_name`, `idol_id`, `rating`, `comment`) VALUES
('Rohan Patil', (SELECT `id` FROM `idols` WHERE `name` = 'Jasvandi Ganpati' LIMIT 1), 5, 'Beautiful finish and very safe packaging. Bappa arrived without a single scratch. Ganpati Bappa Morya!'),
('Sneha Kulkarni', (SELECT `id` FROM `idols` WHERE `name` = 'Undir Ganpati (Eco-Friendly)' LIMIT 1), 5, 'Loved the eco-friendly clay idol. It dissolved perfectly in our bucket at home.'),
('Amit Deshmukh', NULL, 4, 'Smooth booking and on-time delivery to Thane. Staff was very helpful.');

INSERT INTO `branches` (`branch_name`, `address`, `city`, `phone`, `manager_name`, `status`) VALUES
('Dadar Workshop', 'Shivaji Park Road, Dadar West', 'Mumbai', '9876543210', 'Rajesh Patil', 'Active'),
('Lalbaug Centre', 'Lalbaug Market, Parel', 'Mumbai', '9876501234', 'Suresh Kamble', 'Active'),
('Thane Branch', 'Naupada, Thane West', 'Thane', '9876512345', 'Meena Joshi', 'Active');

-- Split each item's shop stock across the three branches (50% / 30% / the rest)
INSERT INTO `branch_stock` (`branch_id`, `idol_id`, `stock_count`)
SELECT b.`id`, i.`id`,
       CASE b.`id`
           WHEN 1 THEN CEIL(i.`stock_count` / 2)
           WHEN 2 THEN FLOOR(i.`stock_count` * 3 / 10)
           ELSE GREATEST(i.`stock_count` - CEIL(i.`stock_count` / 2) - FLOOR(i.`stock_count` * 3 / 10), 0)
       END
FROM `branches` b CROSS JOIN `idols` i;

-- RECENTLY VIEWED PRODUCTS (per logged-in user)
CREATE TABLE `recently_viewed` (
    `id` INT AUTO_INCREMENT PRIMARY KEY,
    `user_id` INT NOT NULL,
    `idol_id` INT NOT NULL,
    `viewed_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY `uq_rv_user_idol` (`user_id`, `idol_id`),
    CONSTRAINT `fk_rv_idol` FOREIGN KEY (`idol_id`) REFERENCES `idols` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- SECURE PASSWORD RESET (only a SHA-256 hash of the emailed token is stored; single use, 30 min expiry)
CREATE TABLE `password_resets` (
    `id` INT AUTO_INCREMENT PRIMARY KEY,
    `user_id` INT NOT NULL,
    `token_hash` CHAR(64) NOT NULL,
    `expires_at` DATETIME NOT NULL,
    `used` TINYINT(1) NOT NULL DEFAULT 0,
    `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY `uq_pr_token` (`token_hash`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Handy checks
-- SHOW TABLES;
SELECT * FROM users;
SELECT * FROM idols;
SELECT * FROM bookings;
SELECT * FROM reviews;
SELECT * FROM branches;
SELECT * FROM branch_stock;
SELECT * FROM restock_alerts;

