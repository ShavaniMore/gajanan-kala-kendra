# Gajanan Kala Kendra — Ganpati Shop Management System

One project, two sides:

* **Customer site** — Home, Shop, Booking, Track Order, My Orders, Reviews, Pooja Guide.
* **Admin panel** — dashboard, products, stock, bookings, payments, customers, reviews, reports and branches.

The login page has a **Login as User / Login as Admin** switch. Everything uses the same look
(cream · saffron · deep-red, Playfair Display).

---

## 1. How to run (Windows)

Prerequisites: **Python 3.10+** (tick "Add Python to PATH" when installing). MySQL is optional.

```bat
cd "Ganpati Shop Management System\backend"
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

Mac / Linux: use `source venv/bin/activate` instead of `venv\Scripts\activate`.

Open **http://127.0.0.1:5000**

To stop the server press `Ctrl + C`. Next time you only need: `venv\Scripts\activate` then `python app.py`.

### Logins

| Role | How to sign in | Username | Password |
|---|---|---|---|
| **Admin** | Login page → **Login as Admin** tab | `admin` | `admin123` |
| **Customer** | Register on the site, then **Login as User** tab | your own | your own |

Change the admin password right after the first login (Admin → **My Profile**).
The tab you pick must match the account: an admin cannot sign in through the User tab and a customer
cannot sign in through the Admin tab.

### Database
* The app uses **MySQL** (`root` / `root`, database `ganpati_shop_db`) and **creates the database,
  tables and sample data automatically** on first run.
* If MySQL is not running it falls back to a local SQLite file (`backend/ganpati.db`). The console prints
  which one is in use (`[Database] Using ...`).
* Different MySQL password? Set `MYSQL_USER`, `MYSQL_PASSWORD`, `MYSQL_HOST`, `MYSQL_DB`
  (or edit `MYSQL_CONFIG` in `backend/database.py`).
* **Already ran the earlier version?** Just start the new one. Missing columns and tables are added
  automatically and nothing is deleted — old bookings, users and reviews stay.
* `schema_mysql.sql` is optional (manual setup in Workbench). It **drops and recreates** all tables.
* Force SQLite even when MySQL is installed: set the environment variable `GANPATI_DB=sqlite`.

### Forgot the admin password?
Open a terminal in `backend` (with the venv active) and run:
```bat
python app.py reset-admin
```
It asks for a new password. (The customer "Forgot password" page deliberately cannot reset admin accounts.)

---

## 2. Admin panel guide  (`/admin`)

| Menu | What the admin can do |
|---|---|
| **Dashboard** | Totals (bookings, revenue, items, customers, low stock, restock requests, reviews, branches), latest bookings, orders by status, best sellers, items needing restock with a one-click "Add stock" |
| **Products** | **Add** (with photo upload), **edit**, **delete**, **hide / show** in the shop, search + filter by category / low / out of stock / hidden, export CSV |
| **Stock** | Set exact stock, add or remove units, change each item's low-stock alert level, low / out-of-stock warnings |
| **Restock Alerts** | See customers waiting for out-of-stock items, "Check restocked items", email them (opens your mail app with a ready message), mark notified |
| **Bookings** | Tabs: All · New · In progress · Completed · Cancelled; search, filter by payment / delivery / date, update status; open any booking for full details, payment, status and a **printable invoice** |
| **Payments** | Billed, collected, balance to collect and refunded totals; change each booking's payment status |
| **Customers** | List with order count and total spent, view profile and booking history, edit details, **reset password**, deactivate / re-activate, delete |
| **Reviews** | Read, filter by rating, rating summary, delete inappropriate reviews |
| **Reports** | Revenue, orders, average order, cancellation rate; revenue by month and category; top sellers; by payment / delivery / status; date range; **CSV export** (bookings, inventory, customers) |
| **Branches** | Add / edit / delete branches, **Branch Stock** per item, **Branch Sales** ranking |
| **My Profile** | Change the admin password |

Good to know
* Cancelling a booking returns its units to the shop **and** to the branch that was chosen.
* A product that already has bookings cannot be deleted (it would wipe order history) — use **Hide** instead.
* Hidden products disappear from the shop but stay in all reports and old bookings.
* A restock request turns **Ready** automatically as soon as the admin adds stock.

## 3. Customer site features

| Page | What it does |
|---|---|
| Home | Hero, live Ganesh Chaturthi countdown, categories, trending idols, add-ons, testimonials, About, Contact |
| Shop | Search, category / size / price filters, sorting, stock labels, **Notify me when available** on out-of-stock items |
| Booking | Login required, pre-filled from the account, optional **branch** choice, live total, stock / date validation |
| Track Order | By Booking ID or phone number, progress steps, printable invoice |
| **My Orders** | Booking history with **Buy again**, and the list of items you are waiting for |
| Reviews | Submit and read reviews |
| **Pooja Guide** | Sthapana muhurat note, pooja items, basic steps, aarti, Visarjan and festival tips |

---

## 4. What was added in this version

**New files**
* `backend/admin.py` — the whole admin panel (routes under `/admin`).
* `backend/database.py` — database layer, schema, seed data and automatic upgrade of old databases.
* `backend/common.py` — shared settings, login helpers, CSRF protection, formatting filters.
* `backend/templates/admin/` — 20 admin pages (layout, dashboard, products, stock, bookings, invoice, payments, customers, reviews, reports, branches, restock, profile…).
* `backend/static/css/admin.css`, `backend/static/js/admin.js`, `backend/static/images/placeholder.svg`, `backend/static/images/uploads/` (admin photo uploads).
* `backend/templates/my_orders.html`, `backend/templates/pooja_guide.html`.

**Changed files**
* `backend/app.py` — login role switch, branch-aware booking, My Orders, restock requests, Pooja Guide, `reset-admin` command.
* `backend/templates/login.html` — User / Admin tabs. `base.html` — new menu links. `booking.html`, `booking_status.html`, `_macros.html`, `home.html`, `catalogue.html`, and the form pages — branch field, Notify-me button, security token.
* `schema_mysql.sql` — new tables / columns and seed data. `README.md`, `.gitignore`.

**Brought over from the Feature project** (rebuilt in the shop's design and on the shop's database)
stock management with low-stock alerts · restock alerts · branch management (add / edit / delete) ·
branch-wise stock · branch-wise sales · order history + Buy Again (now **My Orders**) ·
choosing a branch when ordering · Pooja Information (now **Pooja Guide**).

**Not brought over:** the Feature project's own `products / orders / order_items` tables and the
`gajanan_kala_kendra` database (this project's `idols / bookings` tables are used instead — no second
database to set up), its multi-language switcher and dark-mode toggle, and its Gmail settings
(it contained a placeholder password and no code that sent mail).

**Security added:** every form carries a hidden security token (CSRF), admin pages re-check the account on
every request, deactivated accounts cannot log in, uploads are checked by file content (images only, 4 MB max),
CSV exports neutralise spreadsheet formulas, admin accounts cannot be reset through the public reset page.

## 5. Project structure
```
Ganpati Shop Management System/
├── backend/
│   ├── app.py            # customer site, login / register, run + reset-admin command
│   ├── admin.py          # admin panel
│   ├── database.py       # MySQL/SQLite layer, schema, seed data, upgrades
│   ├── common.py         # settings, helpers, CSRF, filters
│   ├── requirements.txt
│   ├── templates/        # site pages + admin/ (admin pages)
│   └── static/           # css (style.css, admin.css), js, images, images/uploads
├── schema_mysql.sql      # optional manual DB setup
├── README.md
└── .gitignore
```

## 6. Settings you may want to change
* `FESTIVAL_DATE` / `FESTIVAL_LABEL` in `backend/common.py` — the home-page countdown date.
* `SECRET_KEY` environment variable — set before deploying publicly.
* `ADVANCE_AMOUNT` in `backend/common.py` — advance counted as "collected" for **Advance Paid** bookings (₹500).
* Add-on photos: replace `dhoti.jpg`, `earrings.jpg`, `pheta.jpg`, `mushak_modak.jpg`, `jewellery.jpg` in
  `static/images/` (they are colour placeholders), or upload real ones from Admin → Products → Edit.
* `FLASK_DEBUG=0` turns off debug mode for a public demo.

---

## New features (latest update)

* **Demo payment** on *Book Now* and checkout: choose **50% advance / full payment**, then **UPI / Net Banking / Cards / Cash**, press **Pay Now** → processing animation → confirmation + printable **receipt**. No real money is charged; card details are never stored.
* **Wishlist** (heart on every product) and **My Cart** buttons beside Login/Logout in the navbar.
* **Cart → Order Summary** (all selected idols + total) → **Proceed to Pay** → payment → receipt → **Continue Shopping** (home).
* Festival countdown now targets **4 September 2027** (edit `FESTIVAL_DATE` in `backend/common.py`).
* New tables `wishlist`, `cart_items` and booking columns are added automatically on first run (existing data is kept).

---

## New in this version

* **Round logo** – `backend/static/images/logo.png` (+ `favicon.png`) is used in the side menu, admin panel, login pages, footer and browser tab.
* **Welcome animation** – on the first visit of each browser session Bappa fills with colour from the bottom like a shutter, then flowers shower down and the shop opens (there is a *Skip* button; it respects "reduce motion"). Code: `base.html` (splash block), `style.css` (INTRO ANIMATION) and `main.js`.
* **Left side navigation** – the shop menu is now a left sidebar, in the same style as the admin panel (slides in from the left on phones).
* **Dark / Light mode** – moon/sun button in the side menu, admin top bar and login pages. Choice is remembered in the browser.
* **Recently viewed products** – every item a logged-in user opens (Book page) is saved in the new `recently_viewed` table and shown on Home, Shop and Book pages.
* **Secure password reset** – the old "security answer" reset was replaced by an e-mailed one-time link: random token (only its SHA-256 hash is stored), expires in 30 minutes, single use, older links die when a new one is requested, same reply whether or not the account exists, rate-limited, and new passwords need 8+ characters with a letter and a number. Admin accounts are still reset only with `python app.py reset-admin`.
  * To send real e-mail set environment variables `SMTP_HOST`, `SMTP_PORT` (587), `SMTP_USER`, `SMTP_PASS`, optional `SMTP_FROM`.
  * Without SMTP (local testing) the link is printed in the terminal and saved in `backend/reset_links.log`. `RESET_SHOW_LINK=1` also shows it on the page (testing only).
  * New tables are created automatically on start (`password_resets`, `recently_viewed`); `schema_mysql.sql` was updated too.
* **Languages** – English, हिन्दी, मराठी, ગુજરાતી from the language box (side menu / admin top bar / login pages). Translations live in `backend/static/js/i18n.js` – add a line to translate more text. Names/descriptions of products typed in the admin panel stay as written.
* Small fix: the admin dashboard "Catalogue Items" box showed a Python object instead of the number.

---

## AI assistant, e-mails, security and going live

### 1. Settings file (.env)
Copy `backend/.env.example` to `backend/.env` and fill it in. All secrets (SECRET_KEY, e-mail password, AI key, database password) live there – never upload `.env` anywhere (it is already in `.gitignore`).

### 2. AI assistant "Bappa Helper" (chat button at the bottom-right of every page)
Files: `backend/assistant.py`, `backend/static/js/assistant.js`, `backend/templates/_assistant.html`.
It answers from the shop facts + the live product list (prices / stock) and replies in the language chosen on the site.

| Where | `.env` settings |
|---|---|
| **On your laptop (free)** – install Ollama, run `ollama pull llama3.2`, keep Ollama open | `AI_PROVIDER=ollama` and `AI_MODEL=llama3.2` |
| **Live website (recommended)** – hosted Claude API | `AI_PROVIDER=anthropic`, `AI_API_KEY=your key`, `AI_MODEL=claude-haiku-5-5` |
| Any OpenAI-compatible service | `AI_PROVIDER=openai`, `AI_API_KEY=...`, `AI_BASE_URL=...`, `AI_MODEL=...` |

Going live = change only `.env`; no code change. Protections: CSRF check, 12 messages / 5 min per visitor, `AI_DAILY_LIMIT` for the whole site (stops a surprise bill), 400-character messages, the API key never reaches the browser, replies are shown as plain text, the bot cannot read orders/users/admin data, and it refuses off-topic or "ignore your rules" requests. If the AI is down the visitor sees a polite message.

### 3. E-mails
`backend/mailer.py` sends: welcome mail after registration, "welcome back / thank you" mail after every customer login (with time + a security note), and the password-reset link. Set `SMTP_*` in `.env` (for Gmail use an *App Password*). Without SMTP the mails are saved in `backend/sent_emails.log` so you can test offline.

### 4. Security added
Login lock after 5 wrong passwords (10 min), security headers, 8-hour sessions, secure cookies when `HTTPS=1`, CSRF on every form, hashed passwords, hashed one-time reset tokens, rate limits, warning if `SECRET_KEY` is left at the default.

### 5. Going live checklist
1. Hosting with Python + MySQL (e.g. a VPS, Render, Railway, PythonAnywhere). Upload the project, `pip install -r requirements.txt`.
2. Create `.env` on the server: strong `SECRET_KEY`, `FLASK_DEBUG=0`, `HTTPS=1`, `BEHIND_PROXY=1`, MySQL details, `SMTP_*`, `AI_PROVIDER=anthropic` + `AI_API_KEY`.
3. Start with a real server instead of `python app.py`:
   * Linux: `gunicorn -w 2 -b 0.0.0.0:8000 wsgi:app`
   * Windows: `waitress-serve --port=8000 wsgi:app`
4. Put HTTPS in front (the host's SSL option, or nginx + Let's Encrypt).
5. Change the admin password (default `admin123`) and keep `backend/static/images/uploads` on persistent storage.
6. Replace the demo payment with a real gateway (e.g. Razorpay) before taking real money.
