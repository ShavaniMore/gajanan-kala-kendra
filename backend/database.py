import os
import sqlite3
import envload  # noqa: F401  (loads backend/.env)
from flask import g
from werkzeug.security import generate_password_hash

try:
    import pymysql
    import pymysql.cursors
    PYMYSQL_AVAILABLE = True
except ImportError:  # pragma: no cover
    PYMYSQL_AVAILABLE = False

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
SQLITE_PATH = os.path.join(BASE_DIR, "ganpati.db")

MYSQL_CONFIG = {
    "host": os.environ.get("MYSQL_HOST", "localhost"),
    "user": os.environ.get("MYSQL_USER", "root"),
    "password": os.environ.get("MYSQL_PASSWORD", "root"),
    "database": os.environ.get("MYSQL_DB", "ganpati_shop_db").strip().strip("`'\"").strip(),
    "port": int(os.environ.get("MYSQL_PORT", 3306)),
    "autocommit": True,
    "charset": "utf8mb4",
}
if PYMYSQL_AVAILABLE:
    MYSQL_CONFIG["cursorclass"] = pymysql.cursors.DictCursor

# Decided once at start-up by init_db(): True = MySQL, False = SQLite.
USE_MYSQL = False


# ----------------------------------------------------------------------
# CONNECTION HELPERS
# ----------------------------------------------------------------------
class DBWrapper:
    """Same API for MySQL and SQLite. Write queries with '?' placeholders."""

    def __init__(self, conn, is_mysql):
        self.conn = conn
        self.is_mysql = is_mysql

    def execute(self, query, params=None):
        cur = self.conn.cursor()
        if self.is_mysql:
            query = query.replace("?", "%s")
        cur.execute(query, params)
        return cur

    def executemany(self, query, params_list):
        cur = self.conn.cursor()
        if self.is_mysql:
            query = query.replace("?", "%s")
        cur.executemany(query, params_list)
        return cur

    def commit(self):
        self.conn.commit()

    def close(self):
        self.conn.close()


def _connect_mysql():
    """Connect to MySQL, creating the database first if it does not exist."""
    try:
        return pymysql.connect(**MYSQL_CONFIG)
    except pymysql.err.OperationalError as exc:
        if exc.args and exc.args[0] == 1049:  # unknown database
            cfg = {k: v for k, v in MYSQL_CONFIG.items() if k != "database"}
            server = pymysql.connect(**cfg)
            with server.cursor() as cur:
                cur.execute("CREATE DATABASE IF NOT EXISTS `%s` DEFAULT CHARACTER SET "
                            "utf8mb4 COLLATE utf8mb4_unicode_ci" % MYSQL_CONFIG["database"])
            server.close()
            return pymysql.connect(**MYSQL_CONFIG)
        raise


def open_connection():
    if USE_MYSQL:
        return DBWrapper(_connect_mysql(), True)
    conn = sqlite3.connect(SQLITE_PATH)
    conn.row_factory = sqlite3.Row
    return DBWrapper(conn, False)


def get_db():
    """One connection per request, closed automatically afterwards."""
    if "db" not in g:
        g.db = open_connection()
    return g.db


def close_db(_exc):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_app(app):
    app.teardown_appcontext(close_db)


def scalar(cur):
    row = cur.fetchone()
    if row is None:
        return 0
    return list(row.values())[0] if isinstance(row, dict) else row[0]


def hash_pw(password):
    return generate_password_hash(password, method="pbkdf2:sha256")


# ----------------------------------------------------------------------
# SEED DATA
# ----------------------------------------------------------------------
SEED_IDOLS = [
    ("Jasvandi Ganpati", "Ready Ganpati", 8500, 21, "Clay & Shadu Mati", "Jasvandi Sitting Shringar", "In Stock", 12, "Handcrafted traditional Jasvandi throne idol with rich shringar finish.", 4.9, "/static/images/bappa_1.png"),
    ("Dagdu Sheth Ganpati", "Ready Ganpati", 9500, 21, "Shadu Mati", "Royal Dagadusheth Darbar", "In Stock", 8, "Majestic Dagadusheth Halwai style idol with royal Mukut & ornate jewellery.", 5.0, "/static/images/bappa_3.png"),
    ("Asaan Mandi Red", "Ready Ganpati", 10000, 24, "Shadu Clay", "Vibrant Red Baithak", "In Stock", 6, "Grand 24-inch seated Ganesha adorned with red royal silk drape.", 4.9, "/static/images/bappa_7.png"),
    ("Bal Ganesh with Load", "Ready Ganpati", 4000, 7, "Eco Clay", "Cute Bal Roop with Pillow", "In Stock", 20, "Adorable child Ganesha resting on a traditional royal load.", 4.9, "/static/images/bappa_25.png"),
    ("Bal Ganesh Idol", "Ready Ganpati", 7500, 12, "Shadu Mati", "Playful Bal Avatar", "In Stock", 15, "Classic 12-inch Bal Ganesh in a playful pose on a decorative chowki.", 4.8, "/static/images/bappa_28.png"),
    ("Lalbaug Style Grand Idol", "Ready Ganpati", 8500, 22, "Shadu Mati", "Lalbaug Darbar Posture", "In Stock", 10, "Iconic blessing posture idol with high detailed crown.", 5.0, "/static/images/bappa_17.png"),
    ("Undir Ganpati (Eco-Friendly)", "Ecofriendly", 5500, 16, "100% Shadu Eco Clay", "Undir Swari", "In Stock", 14, "Natural eco-friendly clay idol on divine Mushak vehicle base.", 4.8, "/static/images/bappa_2.png"),
    ("Asaan Mandi with Load (Eco)", "Ecofriendly", 6000, 18, "Natural River Clay", "Royal Baithak with Pillow", "In Stock", 12, "100% soluble eco clay idol painted with organic herbal colors.", 4.9, "/static/images/bappa_5.png"),
    ("SuryaFul Ganpati (Eco)", "Ecofriendly", 4500, 10, "Natural Shadu Clay", "Sunflower Halo Design", "In Stock", 18, "Artistic clay idol with a golden crown, ideal for compact home sthapana.", 4.7, "/static/images/bappa_26.png"),
    ("Mandi Ganpati (Eco Clay)", "Ecofriendly", 5500, 7, "Pure Clay", "Traditional Chowki Mandi", "In Stock", 25, "Environment safe organic clay idol with natural turmeric and geru finish.", 4.9, "/static/images/bappa_29.png"),
    ("Asaan Mandi Ganpati", "PoP Ganpati", 9500, 22, "Plaster of Paris (PoP)", "Classic Mandi Shringar", "In Stock", 10, "Lightweight, ultra-durable with high-gloss diamond gemstone work.", 4.8, "/static/images/bappa_4.png"),
    ("Vitthal Ganpati", "PoP Ganpati", 6900, 18, "PoP Fine Cast", "Vitthal Avatar", "In Stock", 15, "Unique Pandharpur Vithoba posture with intricate jewellery detail.", 4.9, "/static/images/bappa_27.png"),
    ("Asaan Mandi White", "PoP Ganpati", 10000, 24, "PoP Finish", "Pure Pearl White & Gold", "In Stock", 7, "Grand 24-inch pearl white idol with glittering golden borders.", 4.8, "/static/images/bappa_6.png"),
    ("Shahi Baithak PoP Bappa", "PoP Ganpati", 7500, 18, "PoP Cast", "Royal Throne Seated", "In Stock", 9, "Vibrant festive colors, lightweight durable frame with diamond mukut.", 4.7, "/static/images/bappa_17.png"),
    ("Festive Silk Dhoti & Shawl Set", "Add-Ons", 450, 0, "Banarasi Silk", "Peethambari Gold Zari", "In Stock", 50, "Pure silk yellow-gold Dhoti with embroidered border for Bappa.", 4.8, "/static/images/dhoti.jpg"),
    ("Royal Pearl Kan-Kundal (Earrings)", "Add-Ons", 250, 0, "Gold Plated Alloy", "Kundan Floral Ear Hangings", "In Stock", 60, "Set of 2 royal traditional earrings for Ganesha idols (12-24 inch).", 4.9, "/static/images/earrings.jpg"),
    ("Kolhapuri Shahi Pheta (Turban)", "Add-Ons", 550, 0, "Velvet & Silk", "Royal Maratha Pheta with Brooch", "In Stock", 40, "Stitched royal turban with pearls, feather brooch and golden lace.", 5.0, "/static/images/pheta.jpg"),
    ("Pure Brass Modak & Mushak (Mouse)", "Add-Ons", 850, 0, "Solid Brass", "Puja Offerings Set", "In Stock", 35, "Heavy solid brass Mushak raj idol and engraved Modak prasad bowl.", 4.9, "/static/images/mushak_modak.jpg"),
    ("Complete Temple Jewellery Set", "Add-Ons", 1200, 0, "Micro Gold Polish", "Grand Shringar Set", "In Stock", 30, "Includes 2 necklaces, 4 bangles, armlets, and sparkling crown brooch.", 4.9, "/static/images/jewellery.jpg"),
]
# Old broken image paths that may exist in a database created by the old project.
OLD_BROKEN_IMAGES = ["/static/images/bappa_%d.png" % n for n in (8, 9, 10, 11, 12, 13, 14)]

SEED_REVIEWS = [
    ("Rohan Patil", "Jasvandi Ganpati", 5, "Beautiful finish and very safe packaging. Bappa arrived without a single scratch. Ganpati Bappa Morya!"),
    ("Sneha Kulkarni", "Undir Ganpati (Eco-Friendly)", 5, "Loved the eco-friendly clay idol. It dissolved perfectly in our bucket at home."),
    ("Amit Deshmukh", None, 4, "Smooth booking and on-time delivery to Thane. Staff was very helpful."),
]



SEED_BRANCHES = [
    ("Dadar Workshop", "Shivaji Park Road, Dadar West", "Mumbai", "9876543210", "Rajesh Patil"),
    ("Lalbaug Centre", "Lalbaug Market, Parel", "Mumbai", "9876501234", "Suresh Kamble"),
    ("Thane Branch", "Naupada, Thane West", "Thane", "9876512345", "Meena Joshi"),
]


# ----------------------------------------------------------------------
# SCHEMA
# ----------------------------------------------------------------------
MYSQL_SCHEMA = [
    """CREATE TABLE IF NOT EXISTS `users` (
        `id` INT AUTO_INCREMENT PRIMARY KEY,
        `username` VARCHAR(100) NOT NULL UNIQUE,
        `email` VARCHAR(150) NOT NULL UNIQUE,
        `password` VARCHAR(255) NOT NULL,
        `phone` VARCHAR(20) NULL,
        `address` TEXT NULL,
        `security_question` VARCHAR(255) DEFAULT 'What is your favourite sweet?',
        `security_answer` VARCHAR(255) DEFAULT 'modak',
        `role` ENUM('user','admin') DEFAULT 'user',
        `is_active` TINYINT(1) NOT NULL DEFAULT 1,
        `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",
    """CREATE TABLE IF NOT EXISTS `idols` (
        `id` INT AUTO_INCREMENT PRIMARY KEY,
        `name` VARCHAR(150) NOT NULL,
        `category` VARCHAR(100) NOT NULL,
        `price` DECIMAL(10,2) NOT NULL,
        `size` INT NOT NULL DEFAULT 0,
        `material` VARCHAR(100) NOT NULL,
        `design_type` VARCHAR(150) NOT NULL,
        `availability` VARCHAR(50) DEFAULT 'In Stock',
        `stock_count` INT DEFAULT 15,
        `low_stock_limit` INT NOT NULL DEFAULT 5,
        `is_active` TINYINT(1) NOT NULL DEFAULT 1,
        `description` TEXT,
        `rating` DECIMAL(2,1) DEFAULT 4.9,
        `image_url` VARCHAR(255) NOT NULL
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",
    """CREATE TABLE IF NOT EXISTS `branches` (
        `id` INT AUTO_INCREMENT PRIMARY KEY,
        `branch_name` VARCHAR(150) NOT NULL,
        `address` VARCHAR(255) NOT NULL,
        `city` VARCHAR(100) NOT NULL,
        `phone` VARCHAR(20) NOT NULL,
        `manager_name` VARCHAR(150) NOT NULL,
        `status` VARCHAR(20) NOT NULL DEFAULT 'Active',
        `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",
    """CREATE TABLE IF NOT EXISTS `bookings` (
        `id` INT AUTO_INCREMENT PRIMARY KEY,
        `booking_id` VARCHAR(50) NOT NULL UNIQUE,
        `user_id` INT NULL,
        `branch_id` INT NULL,
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
        `status` ENUM('Confirmed','Ready for Pickup','Out for Delivery','Delivered','Cancelled') DEFAULT 'Confirmed',
        `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        CONSTRAINT `fk_bookings_idols` FOREIGN KEY (`idol_id`) REFERENCES `idols` (`id`) ON DELETE CASCADE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",
    """CREATE TABLE IF NOT EXISTS `reviews` (
        `id` INT AUTO_INCREMENT PRIMARY KEY,
        `customer_name` VARCHAR(150) NOT NULL,
        `idol_id` INT NULL,
        `rating` INT NOT NULL DEFAULT 5,
        `comment` TEXT NOT NULL,
        `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        CONSTRAINT `fk_reviews_idols` FOREIGN KEY (`idol_id`) REFERENCES `idols` (`id`) ON DELETE SET NULL
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",
    """CREATE TABLE IF NOT EXISTS `branch_stock` (
        `id` INT AUTO_INCREMENT PRIMARY KEY,
        `branch_id` INT NOT NULL,
        `idol_id` INT NOT NULL,
        `stock_count` INT NOT NULL DEFAULT 0,
        UNIQUE KEY `uq_branch_idol` (`branch_id`, `idol_id`),
        CONSTRAINT `fk_bs_branch` FOREIGN KEY (`branch_id`) REFERENCES `branches` (`id`) ON DELETE CASCADE,
        CONSTRAINT `fk_bs_idol` FOREIGN KEY (`idol_id`) REFERENCES `idols` (`id`) ON DELETE CASCADE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",
    """CREATE TABLE IF NOT EXISTS `restock_alerts` (
        `id` INT AUTO_INCREMENT PRIMARY KEY,
        `user_id` INT NOT NULL,
        `idol_id` INT NOT NULL,
        `email` VARCHAR(150) NULL,
        `status` VARCHAR(20) NOT NULL DEFAULT 'Waiting',
        `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE KEY `uq_alert_user_idol` (`user_id`, `idol_id`),
        CONSTRAINT `fk_ra_idol` FOREIGN KEY (`idol_id`) REFERENCES `idols` (`id`) ON DELETE CASCADE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",
    """CREATE TABLE IF NOT EXISTS `user_wishlist` (
        `id` INT AUTO_INCREMENT PRIMARY KEY,
        `user_id` INT NOT NULL,
        `idol_id` INT NOT NULL,
        `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE KEY `uq_wish_user_idol` (`user_id`, `idol_id`),
        CONSTRAINT `fk_uwl_idol` FOREIGN KEY (`idol_id`) REFERENCES `idols` (`id`) ON DELETE CASCADE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",
    """CREATE TABLE IF NOT EXISTS `user_cart_items` (
        `id` INT AUTO_INCREMENT PRIMARY KEY,
        `user_id` INT NOT NULL,
        `idol_id` INT NOT NULL,
        `quantity` INT NOT NULL DEFAULT 1,
        `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE KEY `uq_cart_user_idol` (`user_id`, `idol_id`),
        CONSTRAINT `fk_uci_idol` FOREIGN KEY (`idol_id`) REFERENCES `idols` (`id`) ON DELETE CASCADE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",
    """CREATE TABLE IF NOT EXISTS `recently_viewed` (
        `id` INT AUTO_INCREMENT PRIMARY KEY,
        `user_id` INT NOT NULL,
        `idol_id` INT NOT NULL,
        `viewed_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE KEY `uq_rv_user_idol` (`user_id`, `idol_id`),
        CONSTRAINT `fk_rv_idol` FOREIGN KEY (`idol_id`) REFERENCES `idols` (`id`) ON DELETE CASCADE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",
    """CREATE TABLE IF NOT EXISTS `password_resets` (
        `id` INT AUTO_INCREMENT PRIMARY KEY,
        `user_id` INT NOT NULL,
        `token_hash` CHAR(64) NOT NULL,
        `expires_at` DATETIME NOT NULL,
        `used` TINYINT(1) NOT NULL DEFAULT 0,
        `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE KEY `uq_pr_token` (`token_hash`)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",
]

SQLITE_SCHEMA = [
    """CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        email TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL,
        phone TEXT, address TEXT,
        security_question TEXT DEFAULT 'What is your favourite sweet?',
        security_answer TEXT DEFAULT 'modak',
        role TEXT DEFAULT 'user',
        is_active INTEGER NOT NULL DEFAULT 1,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""",
    """CREATE TABLE IF NOT EXISTS idols (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL, category TEXT NOT NULL, price REAL NOT NULL,
        size INTEGER NOT NULL DEFAULT 0, material TEXT NOT NULL, design_type TEXT NOT NULL,
        availability TEXT NOT NULL DEFAULT 'In Stock', stock_count INTEGER DEFAULT 15,
        low_stock_limit INTEGER NOT NULL DEFAULT 5, is_active INTEGER NOT NULL DEFAULT 1,
        description TEXT, rating REAL DEFAULT 4.9, image_url TEXT NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS branches (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        branch_name TEXT NOT NULL, address TEXT NOT NULL, city TEXT NOT NULL,
        phone TEXT NOT NULL, manager_name TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'Active',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""",
    """CREATE TABLE IF NOT EXISTS bookings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        booking_id TEXT UNIQUE NOT NULL, user_id INTEGER, branch_id INTEGER,
        customer_name TEXT NOT NULL,
        contact_number TEXT NOT NULL, email TEXT,
        idol_id INTEGER NOT NULL, quantity INTEGER NOT NULL DEFAULT 1,
        total_price REAL NOT NULL, booking_date TEXT NOT NULL,
        delivery_option TEXT NOT NULL, delivery_address TEXT,
        payment_status TEXT NOT NULL DEFAULT 'Advance Paid (₹500)',
        status TEXT NOT NULL DEFAULT 'Confirmed',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""",
    """CREATE TABLE IF NOT EXISTS reviews (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        customer_name TEXT NOT NULL, idol_id INTEGER,
        rating INTEGER NOT NULL DEFAULT 5, comment TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""",
    """CREATE TABLE IF NOT EXISTS branch_stock (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        branch_id INTEGER NOT NULL, idol_id INTEGER NOT NULL,
        stock_count INTEGER NOT NULL DEFAULT 0,
        UNIQUE (branch_id, idol_id))""",
    """CREATE TABLE IF NOT EXISTS restock_alerts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL, idol_id INTEGER NOT NULL, email TEXT,
        status TEXT NOT NULL DEFAULT 'Waiting',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE (user_id, idol_id))""",
    """CREATE TABLE IF NOT EXISTS user_wishlist (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL, idol_id INTEGER NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE (user_id, idol_id))""",
    """CREATE TABLE IF NOT EXISTS user_cart_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL, idol_id INTEGER NOT NULL,
        quantity INTEGER NOT NULL DEFAULT 1,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE (user_id, idol_id))""",
    """CREATE TABLE IF NOT EXISTS recently_viewed (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL, idol_id INTEGER NOT NULL,
        viewed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE (user_id, idol_id))""",
    """CREATE TABLE IF NOT EXISTS password_resets (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL, token_hash TEXT NOT NULL UNIQUE,
        expires_at TEXT NOT NULL, used INTEGER NOT NULL DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""",
]

# Columns added by the admin upgrade: (table, column, MySQL DDL, SQLite DDL)
MIGRATIONS = [
    ("users", "is_active", "TINYINT(1) NOT NULL DEFAULT 1", "INTEGER NOT NULL DEFAULT 1"),
    ("idols", "low_stock_limit", "INT NOT NULL DEFAULT 5", "INTEGER NOT NULL DEFAULT 5"),
    ("idols", "is_active", "TINYINT(1) NOT NULL DEFAULT 1", "INTEGER NOT NULL DEFAULT 1"),
    ("bookings", "user_id", "INT NULL", "INTEGER"),
    ("bookings", "branch_id", "INT NULL", "INTEGER"),
    # demo payment details
    ("bookings", "payment_type", "VARCHAR(30) NULL", "TEXT"),
    ("bookings", "payment_method", "VARCHAR(30) NULL", "TEXT"),
    ("bookings", "receipt_no", "VARCHAR(40) NULL", "TEXT"),
    ("bookings", "txn_id", "VARCHAR(40) NULL", "TEXT"),
]


def column_exists(db, table, column):
    if USE_MYSQL:
        row = db.execute(
            "SELECT COUNT(*) AS c FROM information_schema.columns "
            "WHERE table_schema = DATABASE() AND table_name = ? AND column_name = ?",
            (table, column)).fetchone()
        return list(row.values())[0] > 0
    return any(r["name"] == column for r in db.execute(f"PRAGMA table_info({table})").fetchall())


def sync_branch_stock(db):
    """Make sure every (branch, item) pair has a stock row (missing ones start at 0)."""
    db.execute(
        "INSERT INTO branch_stock (branch_id, idol_id, stock_count) "
        "SELECT b.id, i.id, 0 FROM branches b CROSS JOIN idols i "
        "WHERE NOT EXISTS (SELECT 1 FROM branch_stock s WHERE s.branch_id = b.id AND s.idol_id = i.id)")
    db.commit()


def init_db():
    """Pick MySQL/SQLite once, create tables, seed data, run small migrations."""
    global USE_MYSQL
    USE_MYSQL = False
    if PYMYSQL_AVAILABLE and os.environ.get("GANPATI_DB", "").lower() != "sqlite":
        try:
            _connect_mysql().close()
            USE_MYSQL = True
        except Exception as exc:
            print(f"[MySQL notice] Could not connect to MySQL ({exc}). Using local SQLite instead.")

    db = open_connection()
    for stmt in (MYSQL_SCHEMA if USE_MYSQL else SQLITE_SCHEMA):
        db.execute(stmt)
    db.commit()

    # Upgrade databases created by the earlier (pre-admin) version.
    for table, column, ddl_mysql, ddl_sqlite in MIGRATIONS:
        if not column_exists(db, table, column):
            db.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl_mysql if USE_MYSQL else ddl_sqlite}")
    db.commit()

    if scalar(db.execute("SELECT COUNT(*) FROM idols")) == 0:
        db.executemany(
            "INSERT INTO idols (name, category, price, size, material, design_type, availability, "
            "stock_count, description, rating, image_url) VALUES (?,?,?,?,?,?,?,?,?,?,?)", SEED_IDOLS)
        db.commit()
    else:
        # Databases created by the old project: replace the broken slivers with real photos.
        marks = ",".join("?" * len(OLD_BROKEN_IMAGES))
        for item in SEED_IDOLS:
            db.execute(f"UPDATE idols SET image_url = ? WHERE name = ? AND image_url IN ({marks})",
                       (item[10], item[0], *OLD_BROKEN_IMAGES))
        db.commit()

    if db.execute("SELECT id FROM users WHERE username = ?", ("admin",)).fetchone() is None:
        db.execute(
            "INSERT INTO users (username, email, password, phone, address, security_question, "
            "security_answer, role) VALUES (?,?,?,?,?,?,?,?)",
            ("admin", "admin@bappastore.com", hash_pw("admin123"), "9876543210",
             "Dadar Workshop, Mumbai", "What is your favourite sweet?", "modak", "admin"))
        db.commit()

    if scalar(db.execute("SELECT COUNT(*) FROM reviews")) == 0:
        for name, idol_name, rating, comment in SEED_REVIEWS:
            idol = db.execute("SELECT id FROM idols WHERE name = ?", (idol_name,)).fetchone() if idol_name else None
            idol_id = (idol["id"] if idol else None)
            db.execute("INSERT INTO reviews (customer_name, idol_id, rating, comment) VALUES (?,?,?,?)",
                       (name, idol_id, rating, comment))
        db.commit()

    # Branches + a starting per-branch split of the current shop stock.
    if scalar(db.execute("SELECT COUNT(*) FROM branches")) == 0:
        db.executemany("INSERT INTO branches (branch_name, address, city, phone, manager_name, status) "
                       "VALUES (?,?,?,?,?, 'Active')", SEED_BRANCHES)
        db.commit()
        sync_branch_stock(db)
        branch_ids = [r["id"] for r in db.execute("SELECT id FROM branches ORDER BY id").fetchall()]
        for idol in db.execute("SELECT id, stock_count FROM idols").fetchall():
            total = max(int(idol["stock_count"] or 0), 0)
            first, second = (total + 1) // 2, (total * 3) // 10
            parts = [first, second, max(total - first - second, 0)]
            for bid, qty in zip(branch_ids, parts):
                db.execute("UPDATE branch_stock SET stock_count = ? WHERE branch_id = ? AND idol_id = ?",
                           (qty, bid, idol["id"]))
        db.commit()
    else:
        sync_branch_stock(db)

    db.close()
    print("[Database] Using", "MySQL" if USE_MYSQL else "SQLite (" + SQLITE_PATH + ")")
