import os
import hmac
import hashlib
import smtplib
import threading
import getpass
import secrets
import sys
from datetime import datetime, date, timedelta
from email.message import EmailMessage

from flask import (Flask, render_template, request, redirect, url_for,
                   session, flash, jsonify)

import envload  # noqa: F401  (reads backend/.env before anything else)
import database
from database import get_db, scalar, hash_pw, init_db
import common
import mailer
from common import (login_required, safe_next, check_login_password, DELIVERY_OPTIONS,
                    PHONE_RE, EMAIL_RE, validate_payment, amount_collected, PAYMENT_TYPES,
                    PAYMENT_METHODS)
from admin import admin_bp
from assistant import assistant_bp

BASE_DIR = os.path.abspath(os.path.dirname(__file__))

app = Flask(__name__,
            template_folder=os.path.join(BASE_DIR, "templates"),
            static_folder=os.path.join(BASE_DIR, "static"))
# Change this (or set the SECRET_KEY environment variable) before going public.
DEFAULT_SECRET = "ganpati_bappa_morya_divine_store_secret_key_2026"
app.secret_key = os.environ.get("SECRET_KEY", DEFAULT_SECRET)
if app.secret_key == DEFAULT_SECRET and os.environ.get("FLASK_DEBUG", "1") != "1":
    print("[SECURITY WARNING] SECRET_KEY is not set - set a long random SECRET_KEY in .env before going live!")
if os.environ.get("BEHIND_PROXY") == "1":           # running behind nginx / a hosting proxy
    from werkzeug.middleware.proxy_fix import ProxyFix
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)
app.config["MAX_CONTENT_LENGTH"] = 4 * 1024 * 1024          # product photo uploads: 4 MB max
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_HTTPONLY"] = True

app.config["SESSION_COOKIE_SECURE"] = os.environ.get("HTTPS") == "1"     # set HTTPS=1 when deployed with https
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(hours=8)


@app.after_request
def security_headers(resp):
    """Browser-side protections added to every response."""
    resp.headers["X-Content-Type-Options"] = "nosniff"                       # no MIME sniffing
    resp.headers["X-Frame-Options"] = "SAMEORIGIN"                           # blocks clickjacking
    resp.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    resp.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
    return resp


# ---- login brute-force protection: 5 wrong passwords -> 10 minute lock (per name + IP) ----
_login_fails = {}
LOGIN_MAX_FAILS, LOGIN_LOCK_SECONDS = 5, 600


def _login_key(identity):
    return f"{identity.lower()}|{request.remote_addr}"


def _login_locked(key):
    rec = _login_fails.get(key)
    return bool(rec and rec[0] >= LOGIN_MAX_FAILS and datetime.now().timestamp() - rec[1] < LOGIN_LOCK_SECONDS)


def _login_failed(key):
    now = datetime.now().timestamp()
    count, last = _login_fails.get(key, (0, now))
    _login_fails[key] = (1 if now - last > LOGIN_LOCK_SECONDS else count + 1, now)


database.init_app(app)
common.install(app)
app.register_blueprint(admin_bp)
app.register_blueprint(assistant_bp)


# ----------------------------------------------------------------------
# RECENTLY VIEWED PRODUCTS (stored per logged-in user)
# ----------------------------------------------------------------------
def record_view(db, user_id, idol_id):
    db.execute("DELETE FROM recently_viewed WHERE user_id = ? AND idol_id = ?", (user_id, idol_id))
    db.execute("INSERT INTO recently_viewed (user_id, idol_id, viewed_at) VALUES (?,?,?)",
               (user_id, idol_id, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    # keep only the latest 20 per user
    old = db.execute("SELECT id FROM recently_viewed WHERE user_id = ? ORDER BY viewed_at DESC, id DESC",
                     (user_id,)).fetchall()[20:]
    for r in old:
        db.execute("DELETE FROM recently_viewed WHERE id = ?", (r["id"],))
    db.commit()


def get_recently_viewed(db, limit=4, exclude_id=None):
    uid = session.get("user_id")
    if not uid:
        return []
    sql = ("SELECT i.* FROM recently_viewed v JOIN idols i ON i.id = v.idol_id "
           "WHERE v.user_id = ? AND i.is_active = 1")
    params = [uid]
    if exclude_id:
        sql += " AND i.id != ?"
        params.append(exclude_id)
    sql += " ORDER BY v.viewed_at DESC, v.id DESC LIMIT ?"
    params.append(limit)
    return db.execute(sql, params).fetchall()


# ----------------------------------------------------------------------
# PUBLIC PAGES
# ----------------------------------------------------------------------
@app.route("/")
def home():
    db = get_db()
    featured_idols = db.execute(
        "SELECT * FROM idols WHERE category != 'Add-Ons' AND is_active = 1 "
        "ORDER BY rating DESC, id ASC LIMIT 4").fetchall()
    featured_addons = db.execute(
        "SELECT * FROM idols WHERE category = 'Add-Ons' AND is_active = 1 ORDER BY id ASC LIMIT 4").fetchall()
    recent_reviews = db.execute(
        "SELECT r.*, i.name AS idol_name FROM reviews r LEFT JOIN idols i ON r.idol_id = i.id "
        "ORDER BY r.id DESC LIMIT 3").fetchall()
    return render_template("home.html", featured_idols=featured_idols,
                           featured_addons=featured_addons, recent_reviews=recent_reviews,
                           recently_viewed=get_recently_viewed(db, 4))


@app.route("/catalogue")
def catalogue():
    category = request.args.get("category", "all")
    sort_by = request.args.get("sort", "default")
    min_price = request.args.get("min_price", type=float)
    max_price = request.args.get("max_price", type=float)
    size_filter = request.args.get("size", type=int)
    search_query = request.args.get("q", "").strip()

    query, params = "SELECT * FROM idols WHERE is_active = 1", []
    if category != "all":
        query += " AND category = ?"
        params.append(category)
    if search_query:
        query += " AND (name LIKE ? OR description LIKE ? OR material LIKE ? OR design_type LIKE ?)"
        params.extend([f"%{search_query}%"] * 4)
    if min_price is not None:
        query += " AND price >= ?"
        params.append(min_price)
    if max_price is not None:
        query += " AND price <= ?"
        params.append(max_price)
    if size_filter:
        query += " AND size = ?"
        params.append(size_filter)

    order = {
        "price_low_high": "price ASC", "price_high_low": "price DESC",
        "size_small_large": "size ASC", "size_large_small": "size DESC",
        "rating": "rating DESC",
    }.get(sort_by, "id ASC")
    query += f" ORDER BY {order}"

    idols = get_db().execute(query, params).fetchall()
    return render_template("catalogue.html", idols=idols, current_category=category,
                           current_sort=sort_by, search_query=search_query,
                           selected_size=size_filter, min_price=min_price, max_price=max_price,
                           recently_viewed=get_recently_viewed(get_db(), 4))


def branches_with_stock(db, idol_id):
    """Active branches that currently hold stock of this item (for the booking form)."""
    return db.execute(
        "SELECT b.id, b.branch_name, b.city, s.stock_count FROM branch_stock s "
        "JOIN branches b ON s.branch_id = b.id "
        "WHERE s.idol_id = ? AND b.status = 'Active' AND s.stock_count > 0 ORDER BY b.branch_name",
        (idol_id,)).fetchall()


@app.route("/book/<int:idol_id>", methods=["GET", "POST"])
@login_required
def book_idol(idol_id):
    db = get_db()
    idol = db.execute("SELECT * FROM idols WHERE id = ? AND is_active = 1", (idol_id,)).fetchone()
    if not idol:
        flash("Selected item was not found.", "danger")
        return redirect(url_for("catalogue"))

    user = db.execute("SELECT * FROM users WHERE id = ?", (session["user_id"],)).fetchone()
    if request.method == "GET":
        record_view(db, session["user_id"], idol_id)
    form = {
        "customer_name": user["username"] if user else "",
        "contact_number": (user["phone"] or "") if user else "",
        "email": user["email"] if user else "",
        "quantity": max(1, request.args.get("qty", type=int) or 1),
        "booking_date": "", "delivery_option": "Store Pickup",
        "delivery_address": (user["address"] or "") if user else "",
        "branch_id": 0,
    }
    today = date.today().isoformat()
    branches = branches_with_stock(db, idol_id)

    if request.method == "POST":
        form.update({k: request.form.get(k, "").strip() for k in
                     ("customer_name", "contact_number", "email", "booking_date",
                      "delivery_option", "delivery_address")})
        form["quantity"] = request.form.get("quantity", type=int) or 0
        form["branch_id"] = request.form.get("branch_id", type=int) or 0

        error = None
        if not form["customer_name"]:
            error = "Please enter your full name."
        elif not PHONE_RE.match(form["contact_number"]):
            error = "Enter a valid 10-digit contact number."
        elif form["email"] and not EMAIL_RE.match(form["email"]):
            error = "Enter a valid email address."
        elif not 1 <= form["quantity"] <= 10:
            error = "Quantity must be between 1 and 10."
        elif form["delivery_option"] not in DELIVERY_OPTIONS:
            error = "Choose a pickup or delivery option."
        elif form["delivery_option"] == "Home Delivery" and not form["delivery_address"]:
            error = "Please enter a delivery address for home delivery."
        elif form["branch_id"] and form["branch_id"] not in [b["id"] for b in branches]:
            error = "That branch does not have this item available."
        else:
            try:
                chosen = datetime.strptime(form["booking_date"], "%Y-%m-%d").date()
                if chosen < date.today():
                    error = "Booking date cannot be in the past."
            except ValueError:
                error = "Please choose a valid booking date."

        pay = None
        if not error:
            pay, error = validate_payment(request.form, float(idol["price"]) * form["quantity"])

        if error:
            flash(error, "danger")
        else:
            qty = form["quantity"]
            # Reserve stock first; rowcount == 0 means not enough stock left.
            cur = db.execute(
                "UPDATE idols SET stock_count = stock_count - ? WHERE id = ? AND stock_count >= ?",
                (qty, idol_id, qty))
            if cur.rowcount == 0:
                flash("Sorry, not enough stock available for that quantity.", "danger")
            else:
                branch_ok = True
                if form["branch_id"]:
                    cur = db.execute(
                        "UPDATE branch_stock SET stock_count = stock_count - ? "
                        "WHERE branch_id = ? AND idol_id = ? AND stock_count >= ?",
                        (qty, form["branch_id"], idol_id, qty))
                    if cur.rowcount == 0:
                        branch_ok = False
                        db.execute("UPDATE idols SET stock_count = stock_count + ? WHERE id = ?", (qty, idol_id))
                        flash("That branch does not have enough stock for this quantity.", "danger")
                if branch_ok:
                    db.execute("UPDATE idols SET availability = 'Out of Stock' WHERE id = ? AND stock_count <= 0",
                               (idol_id,))
                    address = form["delivery_address"] or "Workshop Direct Pickup (Dadar / Lalbaug Centre)"
                    booking_id = f"BAPPA-{datetime.now():%Y%m%d%H%M%S}{secrets.token_hex(1).upper()}"
                    db.execute(
                        "INSERT INTO bookings (booking_id, user_id, branch_id, customer_name, contact_number, "
                        "email, idol_id, quantity, total_price, booking_date, delivery_option, "
                        "delivery_address, status, payment_status, payment_type, payment_method, receipt_no, txn_id) "
                        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,'Confirmed',?,?,?,?,?)",
                        (booking_id, session["user_id"], form["branch_id"] or None, form["customer_name"],
                         form["contact_number"], form["email"], idol_id, qty,
                         float(idol["price"]) * qty, form["booking_date"],
                         form["delivery_option"], address, pay["status"], pay["type"], pay["method"],
                         pay["receipt_no"], pay["txn_id"]))
                    db.commit()
                    mailer.notify_low_stock(db, idol_id, stock_before=idol["stock_count"])
                    return redirect(url_for("receipt", receipt_no=pay["receipt_no"], new=1))
        # The page is re-shown: refresh the branch list in case stock changed.
        branches = branches_with_stock(db, idol_id)
        idol = db.execute("SELECT * FROM idols WHERE id = ?", (idol_id,)).fetchone()

    return render_template("booking.html", idol=idol, form=form, today=today, branches=branches,
                           recently_viewed=get_recently_viewed(db, 4, exclude_id=idol_id))


@app.route("/booking/status/<booking_id>")
def booking_status(booking_id):
    booking = get_db().execute(
        "SELECT b.*, i.name AS idol_name, i.size AS idol_size, i.material, i.image_url, i.category, "
        "i.design_type, br.branch_name FROM bookings b JOIN idols i ON b.idol_id = i.id "
        "LEFT JOIN branches br ON b.branch_id = br.id WHERE b.booking_id = ?", (booking_id,)).fetchone()
    if not booking:
        flash("Booking ID not found!", "danger")
        return redirect(url_for("catalogue"))
    return render_template("booking_status.html", booking=booking)


# ----------------------------------------------------------------------
# WISHLIST, CART, CHECKOUT, DEMO PAYMENT & RECEIPT
# ----------------------------------------------------------------------
def wants_json():
    return request.headers.get("X-Requested-With") == "XMLHttpRequest"


def counts(db, uid):
    return {"wish": int(scalar(db.execute("SELECT COUNT(*) FROM user_wishlist WHERE user_id = ?", (uid,))) or 0),
            "cart": int(scalar(db.execute("SELECT COALESCE(SUM(quantity),0) FROM user_cart_items WHERE user_id = ?", (uid,))) or 0)}


def login_for_action(message):
    """Used by the heart / add-to-cart buttons when the visitor is not logged in."""
    target = safe_next(request.form.get("next")) or url_for("catalogue")
    login_url = url_for("login", next=target)
    if wants_json():
        return jsonify(ok=False, login=login_url, message=message), 401
    flash(message, "warning")
    return redirect(login_url)


def after_action(target, **payload):
    if wants_json():
        return jsonify(ok=True, **payload)
    return redirect(target)


@app.route("/wishlist")
@login_required
def wishlist():
    items = get_db().execute(
        "SELECT i.* FROM user_wishlist w JOIN idols i ON w.idol_id = i.id "
        "WHERE w.user_id = ? AND i.is_active = 1 ORDER BY w.id DESC", (session["user_id"],)).fetchall()
    return render_template("wishlist.html", items=items)


@app.route("/wishlist/toggle/<int:idol_id>", methods=["POST"])
def wishlist_toggle(idol_id):
    if not session.get("user_id"):
        return login_for_action("Please login to save items to your wishlist.")
    db, uid = get_db(), session["user_id"]
    target = safe_next(request.form.get("next")) or url_for("wishlist")
    if not db.execute("SELECT id FROM idols WHERE id = ? AND is_active = 1", (idol_id,)).fetchone():
        flash("Item not found.", "danger")
        return redirect(target)
    if db.execute("SELECT id FROM user_wishlist WHERE user_id = ? AND idol_id = ?", (uid, idol_id)).fetchone():
        db.execute("DELETE FROM user_wishlist WHERE user_id = ? AND idol_id = ?", (uid, idol_id))
        saved, msg = False, "Removed from your wishlist."
    else:
        db.execute("INSERT INTO user_wishlist (user_id, idol_id) VALUES (?,?)", (uid, idol_id))
        saved, msg = True, "Added to your wishlist."
    db.commit()
    if not wants_json():
        flash(msg, "success" if saved else "info")
    return after_action(target, saved=saved, message=msg, counts=counts(db, uid))


@app.route("/cart")
@login_required
def cart():
    items, total = cart_lines(get_db(), session["user_id"])
    return render_template("cart.html", items=items, total=total)


def cart_lines(db, uid):
    rows = db.execute(
        "SELECT c.quantity, i.* FROM user_cart_items c JOIN idols i ON c.idol_id = i.id "
        "WHERE c.user_id = ? AND i.is_active = 1 ORDER BY c.id", (uid,)).fetchall()
    lines = [{"idol": r, "qty": r["quantity"], "line_total": float(r["price"]) * r["quantity"]} for r in rows]
    return lines, sum(l["line_total"] for l in lines)


@app.route("/cart/add/<int:idol_id>", methods=["POST"])
def cart_add(idol_id):
    if not session.get("user_id"):
        return login_for_action("Please login to add items to your cart.")
    db, uid = get_db(), session["user_id"]
    target = safe_next(request.form.get("next")) or url_for("cart")
    idol = db.execute("SELECT * FROM idols WHERE id = ? AND is_active = 1", (idol_id,)).fetchone()
    if not idol or idol["stock_count"] <= 0:
        msg, ok = "Sorry, this item is not available right now.", False
    else:
        limit = min(idol["stock_count"], 10)
        row = db.execute("SELECT quantity FROM user_cart_items WHERE user_id = ? AND idol_id = ?", (uid, idol_id)).fetchone()
        if row:
            new_qty = min(row["quantity"] + 1, limit)
            db.execute("UPDATE user_cart_items SET quantity = ? WHERE user_id = ? AND idol_id = ?", (new_qty, uid, idol_id))
        else:
            db.execute("INSERT INTO user_cart_items (user_id, idol_id, quantity) VALUES (?,?,1)", (uid, idol_id))
        db.commit()
        msg, ok = f"{idol['name']} added to your cart.", True
    if wants_json():
        return jsonify(ok=ok, message=msg, counts=counts(db, uid))
    flash(msg, "success" if ok else "danger")
    return redirect(target)


@app.route("/cart/update/<int:idol_id>", methods=["POST"])
@login_required
def cart_update(idol_id):
    db, uid = get_db(), session["user_id"]
    idol = db.execute("SELECT stock_count FROM idols WHERE id = ?", (idol_id,)).fetchone()
    qty = request.form.get("quantity", type=int) or 0
    if not idol or qty < 1:
        db.execute("DELETE FROM user_cart_items WHERE user_id = ? AND idol_id = ?", (uid, idol_id))
    else:
        db.execute("UPDATE user_cart_items SET quantity = ? WHERE user_id = ? AND idol_id = ?",
                   (min(qty, max(min(idol["stock_count"], 10), 1)), uid, idol_id))
    db.commit()
    return redirect(url_for("cart"))


@app.route("/cart/remove/<int:idol_id>", methods=["POST"])
@login_required
def cart_remove(idol_id):
    db = get_db()
    db.execute("DELETE FROM user_cart_items WHERE user_id = ? AND idol_id = ?", (session["user_id"], idol_id))
    db.commit()
    flash("Item removed from your cart.", "info")
    return redirect(url_for("cart"))


@app.route("/checkout", methods=["GET", "POST"])
@login_required
def checkout():
    db, uid = get_db(), session["user_id"]
    items, total = cart_lines(db, uid)
    if not items:
        flash("Your cart is empty. Add some idols first.", "info")
        return redirect(url_for("catalogue"))
    user = db.execute("SELECT * FROM users WHERE id = ?", (uid,)).fetchone()
    form = {"customer_name": user["username"] if user else "",
            "contact_number": (user["phone"] or "") if user else "",
            "email": user["email"] if user else "", "booking_date": "",
            "delivery_option": "Store Pickup", "delivery_address": (user["address"] or "") if user else ""}

    if request.method == "POST":
        form.update({k: request.form.get(k, "").strip() for k in form})
        error = None
        if not form["customer_name"]:
            error = "Please enter your full name."
        elif not PHONE_RE.match(form["contact_number"]):
            error = "Enter a valid 10-digit contact number."
        elif form["email"] and not EMAIL_RE.match(form["email"]):
            error = "Enter a valid email address."
        elif form["delivery_option"] not in DELIVERY_OPTIONS:
            error = "Choose a pickup or delivery option."
        elif form["delivery_option"] == "Home Delivery" and not form["delivery_address"]:
            error = "Please enter a delivery address for home delivery."
        else:
            try:
                if datetime.strptime(form["booking_date"], "%Y-%m-%d").date() < date.today():
                    error = "Booking date cannot be in the past."
            except ValueError:
                error = "Please choose a valid booking date."
        pay = None
        if not error:
            pay, error = validate_payment(request.form, total)
        if error:
            flash(error, "danger")
        else:
            reserved = []
            failed = None
            for l in items:
                cur = db.execute("UPDATE idols SET stock_count = stock_count - ? WHERE id = ? AND stock_count >= ?",
                                 (l["qty"], l["idol"]["id"], l["qty"]))
                if cur.rowcount == 0:
                    failed = l["idol"]["name"]
                    break
                reserved.append(l)
            if failed:
                for l in reserved:   # give back anything already reserved
                    db.execute("UPDATE idols SET stock_count = stock_count + ? WHERE id = ?", (l["qty"], l["idol"]["id"]))
                db.commit()
                flash(f"Sorry, not enough stock left for {failed}. Please adjust your cart.", "danger")
                return redirect(url_for("cart"))
            address = form["delivery_address"] or "Workshop Direct Pickup (Dadar / Lalbaug Centre)"
            stamp = f"{datetime.now():%Y%m%d%H%M%S}"
            for n, l in enumerate(items, 1):
                db.execute("UPDATE idols SET availability = 'Out of Stock' WHERE id = ? AND stock_count <= 0",
                           (l["idol"]["id"],))
                db.execute(
                    "INSERT INTO bookings (booking_id, user_id, branch_id, customer_name, contact_number, "
                    "email, idol_id, quantity, total_price, booking_date, delivery_option, delivery_address, "
                    "status, payment_status, payment_type, payment_method, receipt_no, txn_id) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,'Confirmed',?,?,?,?,?)",
                    (f"BAPPA-{stamp}{n}{secrets.token_hex(2).upper()}", uid, None, form["customer_name"],
                     form["contact_number"], form["email"], l["idol"]["id"], l["qty"], l["line_total"],
                     form["booking_date"], form["delivery_option"], address, pay["status"], pay["type"],
                     pay["method"], pay["receipt_no"], pay["txn_id"]))
            db.execute("DELETE FROM user_cart_items WHERE user_id = ?", (uid,))
            db.commit()
            for l in items:
                mailer.notify_low_stock(db, l["idol"]["id"], stock_before=l["idol"]["stock_count"])
            return redirect(url_for("receipt", receipt_no=pay["receipt_no"], new=1))

    return render_template("checkout.html", items=items, total=total, form=form, today=date.today().isoformat())


@app.route("/receipt/<receipt_no>")
def receipt(receipt_no):
    rows = get_db().execute(
        "SELECT b.*, i.name AS idol_name, i.image_url, i.category, i.price AS unit_price, br.branch_name "
        "FROM bookings b JOIN idols i ON b.idol_id = i.id LEFT JOIN branches br ON b.branch_id = br.id "
        "WHERE b.receipt_no = ? ORDER BY b.id", (receipt_no,)).fetchall()
    if not rows:
        flash("Receipt not found.", "danger")
        return redirect(url_for("home"))
    first = rows[0]
    total = sum(float(r["total_price"]) for r in rows)
    ptype = first["payment_type"] or "full"
    payable = round(total * 0.5, 2) if ptype == "advance" else total
    paid = sum(amount_collected(r["total_price"], r["payment_status"], r["status"]) for r in rows)
    return render_template("receipt.html", rows=rows, first=first, total=total, paid=paid,
                           balance=max(total - paid, 0), payable=payable,
                           type_label=PAYMENT_TYPES.get(ptype, "Full Payment"),
                           method_label=PAYMENT_METHODS.get(first["payment_method"], "—"),
                           is_cash=first["payment_method"] == "cash", is_new=bool(request.args.get("new")))


@app.route("/track", methods=["GET", "POST"])
def track_order():
    bookings, searched, query = [], False, ""
    if request.method == "POST":
        query = request.form.get("track_query", "").strip()
        searched = True
        if query:
            bookings = get_db().execute(
                "SELECT b.*, i.name AS idol_name, i.size AS idol_size, i.material, i.image_url, i.category "
                "FROM bookings b JOIN idols i ON b.idol_id = i.id "
                "WHERE b.booking_id = ? OR b.contact_number = ? ORDER BY b.id DESC LIMIT 10",
                (query, query)).fetchall()
    return render_template("track.html", bookings=bookings, searched=searched, query=query)


@app.route("/my-orders")
@login_required
def my_orders():
    db = get_db()
    user = db.execute("SELECT * FROM users WHERE id = ?", (session["user_id"],)).fetchone()
    email = (user["email"] or "").lower() if user else ""
    orders = db.execute(
        "SELECT b.*, i.name AS idol_name, i.image_url, i.category, i.stock_count, i.is_active "
        "FROM bookings b JOIN idols i ON b.idol_id = i.id "
        "WHERE b.user_id = ? OR (b.user_id IS NULL AND LOWER(b.email) = ?) ORDER BY b.id DESC",
        (session["user_id"], email)).fetchall()
    alerts = db.execute(
        "SELECT a.*, i.name AS idol_name, i.stock_count, i.image_url FROM restock_alerts a "
        "JOIN idols i ON a.idol_id = i.id WHERE a.user_id = ? ORDER BY a.id DESC",
        (session["user_id"],)).fetchall()
    return render_template("my_orders.html", orders=orders, alerts=alerts)


@app.route("/notify/<int:idol_id>", methods=["POST"])
@login_required
def notify_me(idol_id):
    """Customer asks to be told when an out-of-stock item is available again."""
    db = get_db()
    idol = db.execute("SELECT * FROM idols WHERE id = ? AND is_active = 1", (idol_id,)).fetchone()
    target = safe_next(request.form.get("next")) or url_for("catalogue")
    if not idol:
        flash("Item not found.", "danger")
    elif idol["stock_count"] > 0:
        flash("Good news - this item is available right now!", "info")
    elif db.execute("SELECT id FROM restock_alerts WHERE user_id = ? AND idol_id = ?",
                    (session["user_id"], idol_id)).fetchone():
        flash("You are already on the restock list for this item.", "info")
    else:
        user = db.execute("SELECT email FROM users WHERE id = ?", (session["user_id"],)).fetchone()
        db.execute("INSERT INTO restock_alerts (user_id, idol_id, email, status) VALUES (?,?,?, 'Waiting')",
                   (session["user_id"], idol_id, user["email"] if user else None))
        db.commit()
        flash("Done! We will let you know as soon as this item is back in stock.", "success")
    return redirect(target)


@app.route("/pooja-guide")
def pooja_guide():
    return render_template("pooja_guide.html")


@app.route("/reviews", methods=["GET", "POST"])
def reviews():
    db = get_db()
    if request.method == "POST":
        name = request.form.get("customer_name", "").strip()
        comment = request.form.get("comment", "").strip()
        idol_id = request.form.get("idol_id", type=int)
        rating = request.form.get("rating", type=int, default=5)
        if not name or not comment:
            flash("Please enter your name and your review.", "danger")
        elif not 1 <= rating <= 5:
            flash("Rating must be between 1 and 5.", "danger")
        else:
            db.execute("INSERT INTO reviews (customer_name, idol_id, rating, comment) VALUES (?,?,?,?)",
                       (name, idol_id, rating, comment))
            db.commit()
            flash("Thank you for sharing your review & experience!", "success")
            return redirect(url_for("reviews"))

    all_reviews = db.execute(
        "SELECT r.*, i.name AS idol_name FROM reviews r LEFT JOIN idols i ON r.idol_id = i.id "
        "ORDER BY r.id DESC").fetchall()
    idols = db.execute("SELECT id, name FROM idols WHERE category != 'Add-Ons' ORDER BY name").fetchall()
    return render_template("reviews.html", reviews=all_reviews, idols=idols)


# ----------------------------------------------------------------------
# AUTHENTICATION  (login has a "User / Admin" switch)
# ----------------------------------------------------------------------
@app.route("/login", methods=["GET", "POST"])
def login():
    next_url = safe_next(request.values.get("next"))
    login_as = request.values.get("login_as", request.args.get("role", "user"))
    login_as = "admin" if login_as == "admin" else "user"

    if session.get("user_id") and request.method == "GET":
        if session.get("role") == "admin" and login_as == "admin":
            return redirect(next_url or url_for("admin.dashboard"))
        if session.get("role") != "admin" and login_as == "user":
            return redirect(next_url or url_for("home"))

    if request.method == "POST":
        identity = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        db = get_db()
        lock_key = _login_key(identity)
        if _login_locked(lock_key):
            flash("Too many failed attempts. Please wait 10 minutes or use Forgot Password.", "danger")
            return render_template("login.html", next_url=next_url or "", login_as=login_as)
        user = db.execute("SELECT * FROM users WHERE username = ? OR LOWER(email) = ?",
                          (identity, identity.lower())).fetchone()
        if user and check_login_password(db, user, password):
            _login_fails.pop(lock_key, None)
            if not user["is_active"]:
                flash("This account has been deactivated. Please contact the shop.", "danger")
            elif login_as == "admin" and user["role"] != "admin":
                flash("This account does not have admin access. Use the User tab to sign in.", "danger")
            elif login_as == "user" and user["role"] == "admin":
                flash("This is an admin account. Please choose the Admin tab to sign in.", "warning")
                login_as = "admin"
            else:
                session.clear()
                session["user_id"] = user["id"]
                session["username"] = user["username"]
                session["role"] = user["role"]
                flash(f"Welcome, {user['username']}! Ganpati Bappa Morya 🙏", "success")
                if user["role"] != "admin":
                    mailer.send_login_email(user, request.remote_addr or "")
                if user["role"] == "admin":
                    return redirect(next_url or url_for("admin.dashboard"))
                return redirect(next_url or url_for("home"))
        else:
            _login_failed(lock_key)
            flash("Invalid username/email or password.", "danger")
    return render_template("login.html", next_url=next_url or "", login_as=login_as)


@app.route("/register", methods=["GET", "POST"])
def register():
    form = {}
    if request.method == "POST":
        form = {k: request.form.get(k, "").strip() for k in
                ("username", "email", "phone", "address", "security_answer")}
        password = request.form.get("password", "")
        confirm = request.form.get("confirm_password", "")
        form["email"] = form["email"].lower()

        error = None
        if not all([form["username"], form["email"], form["phone"], password]):
            error = "All required fields must be filled."
        elif not EMAIL_RE.match(form["email"]):
            error = "Enter a valid email address."
        elif not PHONE_RE.match(form["phone"]):
            error = "Enter a valid 10-digit mobile number."
        elif len(password) < 6:
            error = "Password must be at least 6 characters."
        elif password != confirm:
            error = "Passwords do not match."

        if not error:
            db = get_db()
            taken = db.execute("SELECT id FROM users WHERE username = ? OR LOWER(email) = ?",
                               (form["username"], form["email"])).fetchone()
            if taken:
                error = "An account with this name or email already exists."
            else:
                db.execute(
                    "INSERT INTO users (username, email, password, phone, address, security_question, "
                    "security_answer, role) VALUES (?,?,?,?,?,?,?,'user')",
                    (form["username"], form["email"], hash_pw(password), form["phone"], form["address"],
                     "What is your favourite sweet?", form["security_answer"].lower()))
                db.commit()
                mailer.send_welcome_email({"username": form["username"], "email": form["email"]})
                flash("Account created successfully! Please login to continue.", "success")
                return redirect(url_for("login"))
        flash(error, "danger")
    return render_template("register.html", form=form)


# ----------------------------------------------------------------------
# SECURE PASSWORD RESET
#   1. user asks for a link (same reply whether or not the account exists)
#   2. a random one-time token is e-mailed; only its SHA-256 hash is stored
#   3. link works once, expires in 30 minutes, and old links die when a new one is issued
# E-mail is sent through SMTP when SMTP_HOST / SMTP_USER / SMTP_PASS (and optionally
# SMTP_PORT, SMTP_FROM) are set. Without SMTP the link is printed in the server console
# and saved to reset_links.log (local testing). Set RESET_SHOW_LINK=1 to also show it on screen.
# ----------------------------------------------------------------------
RESET_MINUTES = 30
_reset_hits = {}          # ip -> [timestamps]  (simple rate limit)


def _hash_token(token):
    return hashlib.sha256(token.encode()).hexdigest()


def _rate_limited(key, limit=5, window=3600):
    now = datetime.now().timestamp()
    hits = [t for t in _reset_hits.get(key, []) if now - t < window]
    if len(hits) >= limit:
        _reset_hits[key] = hits
        return True
    hits.append(now)
    _reset_hits[key] = hits
    return False


def _send_reset_email(to_addr, username, link):
    body = (f"Namaste {username},\n\nWe received a request to reset your Gajanan Kala Kendra password.\n"
            f"Open this link within {RESET_MINUTES} minutes to choose a new password:\n\n{link}\n\n"
            "If you did not ask for this, ignore this email - your password stays unchanged.\n\n"
            "Ganpati Bappa Morya")
    host = os.environ.get("SMTP_HOST")
    if not host:
        print(f"[Password reset] SMTP not configured. Reset link for {to_addr}: {link}")
        try:
            with open(os.path.join(BASE_DIR, "reset_links.log"), "a", encoding="utf8") as fh:
                fh.write(f"{datetime.now():%Y-%m-%d %H:%M:%S}  {to_addr}  {link}\n")
        except OSError:
            pass
        return

    def _send():
        try:
            msg = EmailMessage()
            msg["Subject"] = "Reset your Gajanan Kala Kendra password"
            msg["From"] = os.environ.get("SMTP_FROM") or os.environ.get("SMTP_USER", "no-reply@localhost")
            msg["To"] = to_addr
            msg.set_content(body)
            with smtplib.SMTP(host, int(os.environ.get("SMTP_PORT", "587")), timeout=15) as s:
                s.starttls()
                if os.environ.get("SMTP_USER"):
                    s.login(os.environ["SMTP_USER"], os.environ.get("SMTP_PASS", ""))
                s.send_message(msg)
        except Exception as exc:
            print(f"[Password reset] Could not send e-mail: {exc}")
    threading.Thread(target=_send, daemon=True).start()


def _valid_reset(db, token):
    """Return the password_resets row for a usable token, else None."""
    row = db.execute("SELECT * FROM password_resets WHERE token_hash = ? AND used = 0",
                     (_hash_token(token),)).fetchone()
    if not row:
        return None
    exp = row["expires_at"]
    if not hasattr(exp, "strftime"):
        exp = datetime.strptime(str(exp)[:19], "%Y-%m-%d %H:%M:%S")
    return row if exp > datetime.now() else None


@app.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    shown_link = None
    if request.method == "POST":
        identity = request.form.get("identity", "").strip()
        db = get_db()
        generic = ("If an account matches, a password reset link has been sent to its email address. "
                   f"The link works once and expires in {RESET_MINUTES} minutes.")
        if _rate_limited(request.remote_addr or "ip") or (identity and _rate_limited("id:" + identity.lower(), 3)):
            flash("Too many reset requests. Please try again after an hour.", "warning")
            return render_template("forgot_password.html")
        user = db.execute("SELECT * FROM users WHERE username = ? OR LOWER(email) = ?",
                          (identity, identity.lower())).fetchone() if identity else None
        # Admin accounts are never reset on the web (use: python app.py reset-admin).
        if user and user["role"] != "admin" and user["is_active"]:
            db.execute("UPDATE password_resets SET used = 1 WHERE user_id = ? AND used = 0", (user["id"],))
            token = secrets.token_urlsafe(32)
            expires = (datetime.now() + timedelta(minutes=RESET_MINUTES)).strftime("%Y-%m-%d %H:%M:%S")
            db.execute("INSERT INTO password_resets (user_id, token_hash, expires_at) VALUES (?,?,?)",
                       (user["id"], _hash_token(token), expires))
            db.commit()
            link = url_for("reset_password", token=token, _external=True)
            _send_reset_email(user["email"], user["username"], link)
            if os.environ.get("RESET_SHOW_LINK") == "1":
                shown_link = link
        flash(generic, "success")
    return render_template("forgot_password.html", shown_link=shown_link)


@app.route("/reset-password/<token>", methods=["GET", "POST"])
def reset_password(token):
    db = get_db()
    row = _valid_reset(db, token)
    if not row:
        flash("This reset link is invalid or has expired. Please request a new one.", "danger")
        return redirect(url_for("forgot_password"))
    if request.method == "POST":
        pw = request.form.get("new_password", "")
        confirm = request.form.get("confirm_password", "")
        if len(pw) < 8 or not any(c.isalpha() for c in pw) or not any(c.isdigit() for c in pw):
            flash("Password must be at least 8 characters and include a letter and a number.", "danger")
        elif pw != confirm:
            flash("Passwords do not match.", "danger")
        else:
            db.execute("UPDATE users SET password = ? WHERE id = ?", (hash_pw(pw), row["user_id"]))
            db.execute("UPDATE password_resets SET used = 1 WHERE user_id = ?", (row["user_id"],))
            db.commit()
            flash("Password updated! You can now log in with your new password.", "success")
            return redirect(url_for("login"))
    return render_template("reset_password.html", token=token)


@app.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.", "info")
    return redirect(url_for("home"))


# ----------------------------------------------------------------------
# COMMAND LINE:  python app.py reset-admin   (recover a forgotten admin password)
# ----------------------------------------------------------------------
def reset_admin_password():
    init_db()
    new_pw = getpass.getpass("New admin password (min 6 characters): ")
    if len(new_pw) < 6:
        print("Password too short - nothing changed.")
        return
    if new_pw != getpass.getpass("Repeat password: "):
        print("Passwords do not match - nothing changed.")
        return
    db = database.open_connection()
    db.execute("UPDATE users SET password = ?, is_active = 1 WHERE username = 'admin'", (hash_pw(new_pw),))
    db.commit()
    db.close()
    print("Admin password updated. You can now log in as admin.")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "reset-admin":
        reset_admin_password()
    else:
        init_db()
        app.run(debug=os.environ.get("FLASK_DEBUG", "1") == "1", host="127.0.0.1", port=5000)
