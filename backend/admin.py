"""
Admin panel for Gajanan Kala Kendra  (all routes live under /admin).

Modules
-------
Dashboard · Products (add / edit / delete / hide) · Stock · Restock alerts
Bookings & order management · Payments · Customers · Reviews · Reports (+CSV)
Branches · Branch stock · Branch sales · Admin profile / change password
"""
import csv
import io
import os
import secrets
from datetime import datetime, timedelta

from flask import (Blueprint, render_template, request, redirect, url_for,
                   session, flash, abort, Response)

import mailer
from database import get_db, scalar, hash_pw, sync_branch_stock
from common import (safe_next, check_login_password, amount_collected, CATEGORY_VALUES,
                    BOOKING_STATUSES, PAYMENT_STATUSES, PHONE_RE, EMAIL_RE, PLACEHOLDER_IMAGE)

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
UPLOAD_DIR = os.path.join(BASE_DIR, "static", "images", "uploads")
UPLOAD_URL = "/static/images/uploads/"
BRANCH_STATUSES = ["Active", "Inactive"]
TABS = {
    "all": None,
    "new": ("Confirmed",),
    "progress": ("Ready for Pickup", "Out for Delivery"),
    "completed": ("Delivered",),
    "cancelled": ("Cancelled",),
}


# ----------------------------------------------------------------------
# ACCESS CONTROL + SIDEBAR BADGES
# ----------------------------------------------------------------------
@admin_bp.before_request
def admin_guard():
    if not session.get("user_id") or session.get("role") != "admin":
        flash("Admin login required.", "warning")
        return redirect(url_for("login", role="admin", next=request.path))
    # Re-check the account on every request (role changed / account deactivated meanwhile).
    row = get_db().execute("SELECT role, is_active FROM users WHERE id = ?", (session["user_id"],)).fetchone()
    if not row or row["role"] != "admin" or not row["is_active"]:
        session.clear()
        flash("Your admin session is no longer valid. Please sign in again.", "warning")
        return redirect(url_for("login", role="admin"))


@admin_bp.context_processor
def admin_badges():
    db = get_db()
    return {
        "nav_new_orders": scalar(db.execute("SELECT COUNT(*) FROM bookings WHERE status = 'Confirmed'")),
        "nav_alerts": scalar(db.execute("SELECT COUNT(*) FROM restock_alerts WHERE status IN ('Waiting','Ready')")),
        "nav_low_stock": scalar(db.execute(
            "SELECT COUNT(*) FROM idols WHERE is_active = 1 AND stock_count <= low_stock_limit")),
        "placeholder_image": PLACEHOLDER_IMAGE,
    }


# ----------------------------------------------------------------------
# SMALL HELPERS
# ----------------------------------------------------------------------
def back_to(default_endpoint, **values):
    """Redirect to the page the form came from (same filters), or to a default page."""
    return redirect(safe_next(request.form.get("next")) or url_for(default_endpoint, **values))


def parse_date(text):
    try:
        return datetime.strptime(text, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None


def date_filter(column, start, end):
    """SQL fragment + params restricting `column` to start..end (inclusive dates)."""
    sql, params = "", []
    if start:
        sql += f" AND {column} >= ?"
        params.append(start.isoformat())
    if end:
        sql += f" AND {column} < ?"
        params.append((end + timedelta(days=1)).isoformat())
    return sql, params


def csv_safe(value):
    """Stop spreadsheet formulas from user-entered text (CSV injection)."""
    if isinstance(value, str) and value[:1] in ("=", "+", "-", "@"):
        return "'" + value
    return value


def csv_response(filename, header, rows):
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(header)
    for row in rows:
        writer.writerow([csv_safe(cell) for cell in row])
    return Response("\ufeff" + buf.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": f"attachment; filename={filename}"})


def set_stock(db, idol_id, qty):
    """Set shop stock, keep the availability label right and flag waiting restock alerts."""
    qty = max(0, int(qty))
    db.execute("UPDATE idols SET stock_count = ?, availability = ? WHERE id = ?",
               (qty, "In Stock" if qty > 0 else "Out of Stock", idol_id))
    if qty > 0:
        db.execute("UPDATE restock_alerts SET status = 'Ready' WHERE idol_id = ? AND status = 'Waiting'", (idol_id,))


def save_image(file):
    """Validate + store an uploaded product photo. Returns its URL, or None if no file chosen."""
    if not file or not file.filename:
        return None
    ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
    head = file.stream.read(16)
    file.stream.seek(0)
    kind = None
    if head.startswith(b"\x89PNG"):
        kind = "png"
    elif head.startswith(b"\xff\xd8"):
        kind = "jpg"
    elif head.startswith(b"GIF8"):
        kind = "gif"
    elif head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        kind = "webp"
    if ext not in ("png", "jpg", "jpeg", "gif", "webp") or kind is None:
        raise ValueError("Please upload a PNG, JPG, GIF or WEBP image.")
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    name = f"{secrets.token_hex(8)}.{kind}"
    file.save(os.path.join(UPLOAD_DIR, name))
    return UPLOAD_URL + name


def remove_uploaded_image(url):
    """Only ever deletes files inside the uploads folder."""
    if url and url.startswith(UPLOAD_URL):
        path = os.path.join(UPLOAD_DIR, os.path.basename(url))
        if os.path.isfile(path):
            os.remove(path)


def restore_booking_stock(db, booking):
    """Give a cancelled booking's units back to the shop (and branch) stock."""
    db.execute("UPDATE idols SET stock_count = stock_count + ?, availability = 'In Stock' WHERE id = ?",
               (booking["quantity"], booking["idol_id"]))
    if booking["branch_id"]:
        db.execute("UPDATE branch_stock SET stock_count = stock_count + ? WHERE branch_id = ? AND idol_id = ?",
                   (booking["quantity"], booking["branch_id"], booking["idol_id"]))
    db.execute("UPDATE restock_alerts SET status = 'Ready' WHERE idol_id = ? AND status = 'Waiting'",
               (booking["idol_id"],))


# ----------------------------------------------------------------------
# DASHBOARD
# ----------------------------------------------------------------------
@admin_bp.route("/")
def dashboard():
    db = get_db()
    stats = {
        "bookings": scalar(db.execute("SELECT COUNT(*) FROM bookings")),
        "new_orders": scalar(db.execute("SELECT COUNT(*) FROM bookings WHERE status = 'Confirmed'")),
        "revenue": scalar(db.execute("SELECT COALESCE(SUM(total_price),0) FROM bookings WHERE status != 'Cancelled'")),
        "items": scalar(db.execute("SELECT COUNT(*) FROM idols")),
        "customers": scalar(db.execute("SELECT COUNT(*) FROM users WHERE role = 'user'")),
        "low_stock": scalar(db.execute(
            "SELECT COUNT(*) FROM idols WHERE stock_count > 0 AND stock_count <= low_stock_limit")),
        "out_of_stock": scalar(db.execute("SELECT COUNT(*) FROM idols WHERE stock_count <= 0")),
        "reviews": scalar(db.execute("SELECT COUNT(*) FROM reviews")),
        "avg_rating": scalar(db.execute("SELECT COALESCE(AVG(rating),0) FROM reviews")),
        "alerts": scalar(db.execute("SELECT COUNT(*) FROM restock_alerts WHERE status IN ('Waiting','Ready')")),
        "branches": scalar(db.execute("SELECT COUNT(*) FROM branches WHERE status = 'Active'")),
    }
    pay_rows = db.execute(
        "SELECT total_price, payment_status, status FROM bookings WHERE status != 'Cancelled'").fetchall()
    stats["pending_balance"] = sum(
        float(r["total_price"]) - amount_collected(r["total_price"], r["payment_status"], r["status"])
        for r in pay_rows if r["payment_status"] != "Refunded")

    recent = db.execute(
        "SELECT b.*, i.name AS idol_name FROM bookings b JOIN idols i ON b.idol_id = i.id "
        "ORDER BY b.id DESC LIMIT 8").fetchall()
    low_items = db.execute(
        "SELECT * FROM idols WHERE is_active = 1 AND stock_count <= low_stock_limit "
        "ORDER BY stock_count ASC, name LIMIT 6").fetchall()
    by_status = {r["status"]: r["c"] for r in db.execute(
        "SELECT status, COUNT(*) AS c FROM bookings GROUP BY status").fetchall()}
    status_rows = [(s, by_status.get(s, 0)) for s in BOOKING_STATUSES]
    top_items = db.execute(
        "SELECT i.name, SUM(b.quantity) AS units FROM bookings b JOIN idols i ON b.idol_id = i.id "
        "WHERE b.status != 'Cancelled' GROUP BY i.id, i.name ORDER BY units DESC LIMIT 5").fetchall()
    return render_template("admin/dashboard.html", stats=stats, recent=recent, low_items=low_items,
                           status_rows=status_rows, status_max=max([c for _, c in status_rows] + [1]),
                           top_items=top_items, top_max=max([int(t["units"]) for t in top_items] + [1]))


# ----------------------------------------------------------------------
# PRODUCTS  (add / update / delete / hide)
# ----------------------------------------------------------------------
@admin_bp.route("/products")
def products():
    q = request.args.get("q", "").strip()
    category = request.args.get("category", "all")
    show = request.args.get("show", "all")
    sql, params = "SELECT * FROM idols WHERE 1=1", []
    if q:
        sql += " AND (name LIKE ? OR material LIKE ? OR design_type LIKE ?)"
        params += [f"%{q}%"] * 3
    if category in CATEGORY_VALUES:
        sql += " AND category = ?"
        params.append(category)
    if show == "low":
        sql += " AND stock_count > 0 AND stock_count <= low_stock_limit"
    elif show == "out":
        sql += " AND stock_count <= 0"
    elif show == "hidden":
        sql += " AND is_active = 0"
    items = get_db().execute(sql + " ORDER BY id DESC", params).fetchall()
    return render_template("admin/products.html", items=items, q=q, category=category, show=show,
                           category_values=CATEGORY_VALUES)


def read_product_form(existing=None):
    """Validate the add/edit product form. Returns (data, error)."""
    f = request.form
    data = {k: f.get(k, "").strip() for k in ("name", "category", "material", "design_type", "description")}
    data["is_active"] = 1 if f.get("is_active") else 0
    data["image_url"] = existing["image_url"] if existing else PLACEHOLDER_IMAGE
    try:
        data["price"] = float(f.get("price", ""))
        data["size"] = int(f.get("size", "0") or 0)
        data["stock_count"] = int(f.get("stock_count", "0") or 0)
        data["low_stock_limit"] = int(f.get("low_stock_limit", "5") or 0)
        data["rating"] = float(f.get("rating", "") or (existing["rating"] if existing else 4.9))
    except ValueError:
        return data, "Price, size, stock and rating must be valid numbers."
    if not data["name"] or not data["material"] or not data["design_type"]:
        return data, "Name, material and design style are required."
    if data["category"] not in CATEGORY_VALUES:
        return data, "Please choose a category."
    if data["price"] <= 0:
        return data, "Price must be greater than zero."
    if data["size"] < 0 or data["stock_count"] < 0 or data["low_stock_limit"] < 0:
        return data, "Size, stock and low-stock limit cannot be negative."
    if not 0 <= data["rating"] <= 5:
        return data, "Rating must be between 0 and 5."
    try:
        new_image = save_image(request.files.get("image"))
    except ValueError as exc:
        return data, str(exc)
    if new_image:
        data["new_image"] = new_image
        data["image_url"] = new_image
    return data, None


@admin_bp.route("/products/new", methods=["GET", "POST"])
def product_new():
    db = get_db()
    item = {"name": "", "category": CATEGORY_VALUES[0], "price": "", "size": 0, "material": "",
            "design_type": "", "stock_count": 10, "low_stock_limit": 5, "description": "",
            "rating": 4.9, "is_active": 1, "image_url": PLACEHOLDER_IMAGE}
    if request.method == "POST":
        data, error = read_product_form()
        if error:
            flash(error, "danger")
            item.update(data)
        else:
            cur = db.execute(
                "INSERT INTO idols (name, category, price, size, material, design_type, availability, "
                "stock_count, low_stock_limit, is_active, description, rating, image_url) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (data["name"], data["category"], data["price"], data["size"], data["material"],
                 data["design_type"], "In Stock" if data["stock_count"] > 0 else "Out of Stock",
                 data["stock_count"], data["low_stock_limit"], data["is_active"], data["description"],
                 data["rating"], data["image_url"]))
            db.commit()
            sync_branch_stock(db)  # give every branch a (0) stock row for the new item
            flash(f"'{data['name']}' was added to the catalogue.", "success")
            return redirect(url_for("admin.products"))
    return render_template("admin/product_form.html", item=item, is_new=True, category_values=CATEGORY_VALUES)


@admin_bp.route("/products/<int:idol_id>/edit", methods=["GET", "POST"])
def product_edit(idol_id):
    db = get_db()
    item = db.execute("SELECT * FROM idols WHERE id = ?", (idol_id,)).fetchone()
    if not item:
        flash("Product not found.", "danger")
        return redirect(url_for("admin.products"))
    if request.method == "POST":
        data, error = read_product_form(item)
        if error:
            flash(error, "danger")
            item = {**dict(item), **data, "id": idol_id}
        else:
            db.execute(
                "UPDATE idols SET name=?, category=?, price=?, size=?, material=?, design_type=?, "
                "stock_count=?, low_stock_limit=?, is_active=?, description=?, rating=?, image_url=? WHERE id=?",
                (data["name"], data["category"], data["price"], data["size"], data["material"],
                 data["design_type"], data["stock_count"], data["low_stock_limit"], data["is_active"],
                 data["description"], data["rating"], data["image_url"], idol_id))
            set_stock(db, idol_id, data["stock_count"])
            db.commit()
            if data.get("new_image"):
                remove_uploaded_image(item["image_url"])
            flash(f"'{data['name']}' was updated.", "success")
            return redirect(url_for("admin.products"))
    return render_template("admin/product_form.html", item=item, is_new=False, category_values=CATEGORY_VALUES)


@admin_bp.route("/products/<int:idol_id>/toggle", methods=["POST"])
def product_toggle(idol_id):
    db = get_db()
    item = db.execute("SELECT name, is_active FROM idols WHERE id = ?", (idol_id,)).fetchone()
    if item:
        new_value = 0 if item["is_active"] else 1
        db.execute("UPDATE idols SET is_active = ? WHERE id = ?", (new_value, idol_id))
        db.commit()
        flash(f"'{item['name']}' is now {'visible in' if new_value else 'hidden from'} the shop.", "success")
    return back_to("admin.products")


@admin_bp.route("/products/<int:idol_id>/delete", methods=["POST"])
def product_delete(idol_id):
    db = get_db()
    item = db.execute("SELECT * FROM idols WHERE id = ?", (idol_id,)).fetchone()
    if not item:
        flash("Product not found.", "danger")
    elif scalar(db.execute("SELECT COUNT(*) FROM bookings WHERE idol_id = ?", (idol_id,))) > 0:
        flash(f"'{item['name']}' has bookings, so it cannot be deleted (that would erase order history). "
              "Use Hide instead to remove it from the shop.", "warning")
    else:
        db.execute("DELETE FROM branch_stock WHERE idol_id = ?", (idol_id,))
        db.execute("DELETE FROM restock_alerts WHERE idol_id = ?", (idol_id,))
        db.execute("UPDATE reviews SET idol_id = NULL WHERE idol_id = ?", (idol_id,))
        db.execute("DELETE FROM idols WHERE id = ?", (idol_id,))
        db.commit()
        remove_uploaded_image(item["image_url"])
        flash(f"'{item['name']}' was deleted.", "success")
    return back_to("admin.products")


# ----------------------------------------------------------------------
# STOCK MANAGEMENT
# ----------------------------------------------------------------------
@admin_bp.route("/stock")
def stock():
    db = get_db()
    show = request.args.get("show", "all")
    q = request.args.get("q", "").strip()
    sql, params = "SELECT * FROM idols WHERE 1=1", []
    if q:
        sql += " AND name LIKE ?"
        params.append(f"%{q}%")
    if show == "low":
        sql += " AND stock_count > 0 AND stock_count <= low_stock_limit"
    elif show == "out":
        sql += " AND stock_count <= 0"
    items = db.execute(sql + " ORDER BY stock_count ASC, name", params).fetchall()
    totals = {
        "total": scalar(db.execute("SELECT COUNT(*) FROM idols")),
        "low": scalar(db.execute("SELECT COUNT(*) FROM idols WHERE stock_count > 0 AND stock_count <= low_stock_limit")),
        "out": scalar(db.execute("SELECT COUNT(*) FROM idols WHERE stock_count <= 0")),
        "units": scalar(db.execute("SELECT COALESCE(SUM(stock_count),0) FROM idols")),
    }
    return render_template("admin/stock.html", items=items, totals=totals, show=show, q=q)


@admin_bp.route("/stock/email-report", methods=["POST"])
def stock_email_report():
    count, to = mailer.send_low_stock_report(get_db())
    if not count:
        flash("Nothing to report - no product is low or out of stock.", "success")
    else:
        flash(f"Low-stock report for {count} product(s) emailed to {', '.join(to)}.", "success")
    return back_to("admin.stock")


@admin_bp.route("/stock/<int:idol_id>", methods=["POST"])
def stock_update(idol_id):
    db = get_db()
    item = db.execute("SELECT name, stock_count FROM idols WHERE id = ?", (idol_id,)).fetchone()
    if not item:
        flash("Product not found.", "danger")
        return back_to("admin.stock")
    mode = request.form.get("mode", "set")
    try:
        amount = int(request.form.get("stock_count", ""))
        limit = request.form.get("low_stock_limit", "")
        limit = int(limit) if limit != "" else None
    except ValueError:
        flash("Please enter whole numbers only.", "danger")
        return back_to("admin.stock")
    new_qty = item["stock_count"] + amount if mode == "add" else amount
    if new_qty < 0 or (limit is not None and limit < 0):
        flash("Stock and the low-stock limit cannot be negative.", "danger")
        return back_to("admin.stock")
    set_stock(db, idol_id, new_qty)
    if limit is not None:
        db.execute("UPDATE idols SET low_stock_limit = ? WHERE id = ?", (limit, idol_id))
    db.commit()
    mailer.notify_low_stock(db, idol_id, stock_before=item["stock_count"])
    flash(f"Stock for '{item['name']}' is now {new_qty}.", "success")
    return back_to("admin.stock")


# ----------------------------------------------------------------------
# BOOKINGS / ORDER MANAGEMENT
# ----------------------------------------------------------------------
@admin_bp.route("/bookings")
def bookings():
    db = get_db()
    tab = request.args.get("tab", "all")
    if tab not in TABS:
        tab = "all"
    q = request.args.get("q", "").strip()
    payment = request.args.get("payment", "")
    delivery = request.args.get("delivery", "")
    start, end = parse_date(request.args.get("from")), parse_date(request.args.get("to"))

    sql, params = ("SELECT b.*, i.name AS idol_name, i.category, br.branch_name FROM bookings b "
                   "JOIN idols i ON b.idol_id = i.id LEFT JOIN branches br ON b.branch_id = br.id WHERE 1=1"), []
    if TABS[tab]:
        sql += " AND b.status IN (%s)" % ",".join("?" * len(TABS[tab]))
        params += list(TABS[tab])
    if q:
        sql += " AND (b.booking_id LIKE ? OR b.customer_name LIKE ? OR b.contact_number LIKE ? OR i.name LIKE ?)"
        params += [f"%{q}%"] * 4
    if payment in PAYMENT_STATUSES:
        sql += " AND b.payment_status = ?"
        params.append(payment)
    if delivery in ("Store Pickup", "Home Delivery"):
        sql += " AND b.delivery_option = ?"
        params.append(delivery)
    frag, frag_params = date_filter("b.created_at", start, end)
    sql += frag
    params += frag_params
    rows = db.execute(sql + " ORDER BY b.id DESC LIMIT 500", params).fetchall()

    counts = {r["status"]: r["c"] for r in db.execute("SELECT status, COUNT(*) AS c FROM bookings GROUP BY status").fetchall()}
    tab_counts = {"all": sum(counts.values())}
    for key, statuses in TABS.items():
        if statuses:
            tab_counts[key] = sum(counts.get(s, 0) for s in statuses)
    return render_template("admin/bookings.html", rows=rows, tab=tab, tab_counts=tab_counts, q=q,
                           payment=payment, delivery=delivery,
                           date_from=start.isoformat() if start else "", date_to=end.isoformat() if end else "")


def fetch_booking(db, booking_id):
    return db.execute(
        "SELECT b.*, i.name AS idol_name, i.size AS idol_size, i.material, i.image_url, i.category, "
        "i.design_type, i.price AS unit_price, br.branch_name, br.city AS branch_city "
        "FROM bookings b JOIN idols i ON b.idol_id = i.id LEFT JOIN branches br ON b.branch_id = br.id "
        "WHERE b.booking_id = ?", (booking_id,)).fetchone()


@admin_bp.route("/bookings/<booking_id>")
def booking_detail(booking_id):
    db = get_db()
    booking = fetch_booking(db, booking_id)
    if not booking:
        flash("Booking not found.", "danger")
        return redirect(url_for("admin.bookings"))
    customer = None
    if booking["user_id"]:
        customer = db.execute("SELECT id, username FROM users WHERE id = ?", (booking["user_id"],)).fetchone()
    paid = amount_collected(booking["total_price"], booking["payment_status"], booking["status"])
    return render_template("admin/booking_detail.html", b=booking, customer=customer, paid=paid,
                           balance=max(float(booking["total_price"]) - paid, 0))


@admin_bp.route("/bookings/<booking_id>/invoice")
def booking_invoice(booking_id):
    booking = fetch_booking(get_db(), booking_id)
    if not booking:
        abort(404)
    paid = amount_collected(booking["total_price"], booking["payment_status"], booking["status"])
    return render_template("admin/invoice.html", b=booking, paid=paid,
                           balance=max(float(booking["total_price"]) - paid, 0))


@admin_bp.route("/bookings/<booking_id>/status", methods=["POST"])
def booking_status_update(booking_id):
    new_status = request.form.get("status", "")
    if new_status not in BOOKING_STATUSES:
        abort(400)
    db = get_db()
    booking = db.execute("SELECT * FROM bookings WHERE booking_id = ?", (booking_id,)).fetchone()
    if not booking:
        flash("Booking not found.", "danger")
    elif booking["status"] == "Cancelled" and new_status != "Cancelled":
        flash("A cancelled booking cannot be re-activated. Ask the customer to book again.", "warning")
    elif booking["status"] == new_status:
        flash("The booking already has that status.", "info")
    else:
        if new_status == "Cancelled":
            restore_booking_stock(db, booking)
        db.execute("UPDATE bookings SET status = ? WHERE booking_id = ?", (new_status, booking_id))
        db.commit()
        extra = " Stock was returned to the shop." if new_status == "Cancelled" else ""
        flash(f"Booking {booking_id} is now '{new_status}'.{extra}", "success")
    return back_to("admin.booking_detail", booking_id=booking_id)


@admin_bp.route("/bookings/<booking_id>/payment", methods=["POST"])
def booking_payment_update(booking_id):
    new_payment = request.form.get("payment_status", "")
    if new_payment not in PAYMENT_STATUSES:
        abort(400)
    db = get_db()
    booking = db.execute("SELECT * FROM bookings WHERE booking_id = ?", (booking_id,)).fetchone()
    if not booking:
        flash("Booking not found.", "danger")
    elif booking["status"] == "Cancelled" and new_payment in ("Paid in Full", "Advance Paid (₹500)", "Advance Paid (50%)"):
        flash("This booking is cancelled - mark the payment as Refunded or Pending instead.", "warning")
    else:
        db.execute("UPDATE bookings SET payment_status = ? WHERE booking_id = ?", (new_payment, booking_id))
        db.commit()
        flash(f"Payment for {booking_id} set to '{new_payment}'.", "success")
    return back_to("admin.booking_detail", booking_id=booking_id)


# ----------------------------------------------------------------------
# PAYMENTS
# ----------------------------------------------------------------------
@admin_bp.route("/payments")
def payments():
    db = get_db()
    status = request.args.get("status", "all")
    q = request.args.get("q", "").strip()
    sql, params = ("SELECT b.*, i.name AS idol_name FROM bookings b JOIN idols i ON b.idol_id = i.id WHERE 1=1"), []
    if status in PAYMENT_STATUSES:
        sql += " AND b.payment_status = ?"
        params.append(status)
    if q:
        sql += " AND (b.booking_id LIKE ? OR b.customer_name LIKE ? OR b.contact_number LIKE ?)"
        params += [f"%{q}%"] * 3
    rows = db.execute(sql + " ORDER BY b.id DESC LIMIT 500", params).fetchall()

    everything = db.execute("SELECT total_price, payment_status, status FROM bookings").fetchall()
    billed = collected = refunded = 0.0
    for r in everything:
        if r["status"] != "Cancelled" and r["payment_status"] != "Refunded":
            billed += float(r["total_price"])
            collected += amount_collected(r["total_price"], r["payment_status"], r["status"])
        if r["payment_status"] == "Refunded":
            refunded += float(r["total_price"])
    summary = {"billed": billed, "collected": collected, "balance": billed - collected, "refunded": refunded}
    items = [{"row": r, "paid": amount_collected(r["total_price"], r["payment_status"], r["status"])} for r in rows]
    return render_template("admin/payments.html", items=items, summary=summary, status=status, q=q)


# ----------------------------------------------------------------------
# CUSTOMERS
# ----------------------------------------------------------------------
MATCH_USER_BOOKINGS = "(b.user_id = u.id OR (b.user_id IS NULL AND LOWER(b.email) = LOWER(u.email)))"


@admin_bp.route("/customers")
def customers():
    q = request.args.get("q", "").strip()
    sql = ("SELECT u.id, u.username, u.email, u.phone, u.is_active, u.created_at, "
           "COUNT(b.id) AS booking_count, "
           "COALESCE(SUM(CASE WHEN b.status != 'Cancelled' THEN b.total_price ELSE 0 END),0) AS spent "
           f"FROM users u LEFT JOIN bookings b ON {MATCH_USER_BOOKINGS} WHERE u.role = 'user'")
    params = []
    if q:
        sql += " AND (u.username LIKE ? OR u.email LIKE ? OR u.phone LIKE ?)"
        params = [f"%{q}%"] * 3
    sql += " GROUP BY u.id, u.username, u.email, u.phone, u.is_active, u.created_at ORDER BY u.id DESC"
    return render_template("admin/customers.html", customers=get_db().execute(sql, params).fetchall(), q=q)


def get_customer(db, user_id):
    return db.execute("SELECT * FROM users WHERE id = ? AND role = 'user'", (user_id,)).fetchone()


@admin_bp.route("/customers/<int:user_id>")
def customer_detail(user_id):
    db = get_db()
    user = get_customer(db, user_id)
    if not user:
        flash("Customer not found.", "danger")
        return redirect(url_for("admin.customers"))
    orders = db.execute(
        "SELECT b.*, i.name AS idol_name FROM bookings b JOIN idols i ON b.idol_id = i.id, users u "
        f"WHERE u.id = ? AND {MATCH_USER_BOOKINGS} ORDER BY b.id DESC", (user_id,)).fetchall()
    alerts = db.execute(
        "SELECT a.*, i.name AS idol_name FROM restock_alerts a JOIN idols i ON a.idol_id = i.id "
        "WHERE a.user_id = ? ORDER BY a.id DESC", (user_id,)).fetchall()
    spent = sum(float(o["total_price"]) for o in orders if o["status"] != "Cancelled")
    return render_template("admin/customer_detail.html", u=user, orders=orders, alerts=alerts, spent=spent)


@admin_bp.route("/customers/<int:user_id>/edit", methods=["GET", "POST"])
def customer_edit(user_id):
    db = get_db()
    user = get_customer(db, user_id)
    if not user:
        flash("Customer not found.", "danger")
        return redirect(url_for("admin.customers"))
    form = {k: user[k] or "" for k in ("username", "email", "phone", "address")}
    if request.method == "POST":
        form = {k: request.form.get(k, "").strip() for k in ("username", "email", "phone", "address")}
        form["email"] = form["email"].lower()
        error = None
        if not form["username"] or not form["email"]:
            error = "Name and email are required."
        elif not EMAIL_RE.match(form["email"]):
            error = "Enter a valid email address."
        elif form["phone"] and not PHONE_RE.match(form["phone"]):
            error = "Phone must be a 10-digit number."
        elif db.execute("SELECT id FROM users WHERE (username = ? OR LOWER(email) = ?) AND id != ?",
                        (form["username"], form["email"], user_id)).fetchone():
            error = "Another account already uses that name or email."
        if error:
            flash(error, "danger")
        else:
            db.execute("UPDATE users SET username=?, email=?, phone=?, address=? WHERE id=?",
                       (form["username"], form["email"], form["phone"], form["address"], user_id))
            db.commit()
            flash("Customer details updated.", "success")
            return redirect(url_for("admin.customer_detail", user_id=user_id))
    return render_template("admin/customer_form.html", u=user, form=form)


@admin_bp.route("/customers/<int:user_id>/toggle", methods=["POST"])
def customer_toggle(user_id):
    db = get_db()
    user = get_customer(db, user_id)
    if user:
        new_value = 0 if user["is_active"] else 1
        db.execute("UPDATE users SET is_active = ? WHERE id = ?", (new_value, user_id))
        db.commit()
        flash(f"{user['username']}'s account is now {'active' if new_value else 'deactivated'}.", "success")
    return back_to("admin.customers")


@admin_bp.route("/customers/<int:user_id>/password", methods=["POST"])
def customer_password(user_id):
    db = get_db()
    user = get_customer(db, user_id)
    new_password = request.form.get("new_password", "")
    if not user:
        flash("Customer not found.", "danger")
    elif len(new_password) < 6:
        flash("The new password must be at least 6 characters.", "danger")
    else:
        db.execute("UPDATE users SET password = ? WHERE id = ?", (hash_pw(new_password), user_id))
        db.commit()
        flash(f"Password for {user['username']} was reset.", "success")
    return back_to("admin.customer_detail", user_id=user_id)


@admin_bp.route("/customers/<int:user_id>/delete", methods=["POST"])
def customer_delete(user_id):
    db = get_db()
    user = get_customer(db, user_id)
    if not user:
        flash("Customer not found.", "danger")
    else:
        # Bookings are kept for the shop's records; they just lose the account link.
        db.execute("UPDATE bookings SET user_id = NULL WHERE user_id = ?", (user_id,))
        db.execute("DELETE FROM restock_alerts WHERE user_id = ?", (user_id,))
        db.execute("DELETE FROM users WHERE id = ?", (user_id,))
        db.commit()
        flash(f"Customer '{user['username']}' was deleted. Their past bookings were kept.", "success")
    return redirect(url_for("admin.customers"))


# ----------------------------------------------------------------------
# REVIEWS
# ----------------------------------------------------------------------
@admin_bp.route("/reviews")
def reviews():
    db = get_db()
    rating = request.args.get("rating", type=int)
    q = request.args.get("q", "").strip()
    sql, params = ("SELECT r.*, i.name AS idol_name FROM reviews r LEFT JOIN idols i ON r.idol_id = i.id WHERE 1=1"), []
    if rating in (1, 2, 3, 4, 5):
        sql += " AND r.rating = ?"
        params.append(rating)
    if q:
        sql += " AND (r.customer_name LIKE ? OR r.comment LIKE ?)"
        params += [f"%{q}%"] * 2
    rows = db.execute(sql + " ORDER BY r.id DESC", params).fetchall()
    dist = {r["rating"]: r["c"] for r in db.execute("SELECT rating, COUNT(*) AS c FROM reviews GROUP BY rating").fetchall()}
    total = sum(dist.values())
    average = (sum(k * v for k, v in dist.items()) / total) if total else 0
    return render_template("admin/reviews.html", rows=rows, rating=rating, q=q, dist=dist, total=total,
                           average=average, dist_max=max(list(dist.values()) + [1]))


@admin_bp.route("/reviews/<int:review_id>/delete", methods=["POST"])
def review_delete(review_id):
    db = get_db()
    db.execute("DELETE FROM reviews WHERE id = ?", (review_id,))
    db.commit()
    flash("Review deleted.", "success")
    return back_to("admin.reviews")


# ----------------------------------------------------------------------
# REPORTS
# ----------------------------------------------------------------------
@admin_bp.route("/reports")
def reports():
    db = get_db()
    start, end = parse_date(request.args.get("from")), parse_date(request.args.get("to"))
    frag, fp = date_filter("b.created_at", start, end)

    def run(sql_tail, extra=""):
        return db.execute(sql_tail.format(w=f"b.status != 'Cancelled'{extra}{frag}"), fp)

    revenue = scalar(run("SELECT COALESCE(SUM(b.total_price),0) FROM bookings b WHERE {w}"))
    orders = scalar(run("SELECT COUNT(*) FROM bookings b WHERE {w}"))
    units = scalar(run("SELECT COALESCE(SUM(b.quantity),0) FROM bookings b WHERE {w}"))
    cancelled = scalar(db.execute("SELECT COUNT(*) FROM bookings b WHERE b.status = 'Cancelled'" + frag, fp))
    all_in_range = scalar(db.execute("SELECT COUNT(*) FROM bookings b WHERE 1=1" + frag, fp))

    by_category = run("SELECT i.category AS label, COUNT(b.id) AS orders, COALESCE(SUM(b.quantity),0) AS units, "
                      "COALESCE(SUM(b.total_price),0) AS revenue FROM bookings b JOIN idols i ON b.idol_id = i.id "
                      "WHERE {w} GROUP BY i.category ORDER BY revenue DESC").fetchall()
    top_items = run("SELECT i.name AS label, SUM(b.quantity) AS units, SUM(b.total_price) AS revenue "
                    "FROM bookings b JOIN idols i ON b.idol_id = i.id WHERE {w} "
                    "GROUP BY i.id, i.name ORDER BY units DESC, revenue DESC LIMIT 8").fetchall()
    by_payment = run("SELECT b.payment_status AS label, COUNT(b.id) AS orders, SUM(b.total_price) AS revenue "
                     "FROM bookings b WHERE {w} GROUP BY b.payment_status ORDER BY orders DESC").fetchall()
    by_delivery = run("SELECT b.delivery_option AS label, COUNT(b.id) AS orders, SUM(b.total_price) AS revenue "
                      "FROM bookings b WHERE {w} GROUP BY b.delivery_option ORDER BY orders DESC").fetchall()
    by_status = db.execute("SELECT b.status AS label, COUNT(b.id) AS orders FROM bookings b WHERE 1=1" + frag +
                           " GROUP BY b.status", fp).fetchall()

    monthly = {}
    for r in run("SELECT b.created_at, b.total_price FROM bookings b WHERE {w}").fetchall():
        key = str(r["created_at"])[:7]
        monthly[key] = monthly.get(key, 0.0) + float(r["total_price"])
    months = [(datetime.strptime(k, "%Y-%m").strftime("%b %Y"), v) for k, v in sorted(monthly.items())][-12:]

    return render_template(
        "admin/reports.html", revenue=revenue, orders=orders, units=units, cancelled=cancelled,
        avg_order=(float(revenue) / orders if orders else 0),
        cancel_rate=(cancelled * 100.0 / all_in_range if all_in_range else 0),
        by_category=by_category, top_items=top_items, by_payment=by_payment, by_delivery=by_delivery,
        by_status=by_status, months=months, month_max=max([v for _, v in months] + [1]),
        cat_max=max([float(r["revenue"]) for r in by_category] + [1]),
        top_max=max([int(r["units"]) for r in top_items] + [1]),
        date_from=start.isoformat() if start else "", date_to=end.isoformat() if end else "")


@admin_bp.route("/reports/export/<kind>")
def report_export(kind):
    db = get_db()
    stamp = datetime.now().strftime("%Y%m%d")
    if kind == "bookings":
        start, end = parse_date(request.args.get("from")), parse_date(request.args.get("to"))
        frag, fp = date_filter("b.created_at", start, end)
        rows = db.execute(
            "SELECT b.booking_id, b.created_at, b.customer_name, b.contact_number, b.email, i.name AS idol_name, "
            "i.category, b.quantity, b.total_price, b.booking_date, b.delivery_option, b.delivery_address, "
            "br.branch_name, b.payment_status, b.status FROM bookings b JOIN idols i ON b.idol_id = i.id "
            "LEFT JOIN branches br ON b.branch_id = br.id WHERE 1=1" + frag + " ORDER BY b.id DESC", fp).fetchall()
        return csv_response(f"bookings_{stamp}.csv",
                            ["Booking ID", "Booked On", "Customer", "Phone", "Email", "Item", "Category", "Qty",
                             "Total (INR)", "Event Date", "Delivery", "Address", "Branch", "Payment", "Status"],
                            [[r["booking_id"], str(r["created_at"])[:19], r["customer_name"], r["contact_number"],
                              r["email"], r["idol_name"], r["category"], r["quantity"], float(r["total_price"]),
                              str(r["booking_date"])[:10], r["delivery_option"], r["delivery_address"],
                              r["branch_name"] or "", r["payment_status"], r["status"]] for r in rows])
    if kind == "inventory":
        rows = db.execute("SELECT * FROM idols ORDER BY category, name").fetchall()
        return csv_response(f"inventory_{stamp}.csv",
                            ["ID", "Name", "Category", "Price (INR)", "Size (in)", "Stock", "Low-stock limit", "Visible"],
                            [[r["id"], r["name"], r["category"], float(r["price"]), r["size"], r["stock_count"],
                              r["low_stock_limit"], "Yes" if r["is_active"] else "No"] for r in rows])
    if kind == "customers":
        rows = db.execute("SELECT username, email, phone, address, is_active, created_at FROM users "
                          "WHERE role = 'user' ORDER BY id DESC").fetchall()
        return csv_response(f"customers_{stamp}.csv",
                            ["Name", "Email", "Phone", "Address", "Active", "Joined"],
                            [[r["username"], r["email"], r["phone"], r["address"],
                              "Yes" if r["is_active"] else "No", str(r["created_at"])[:19]] for r in rows])
    abort(404)


# ----------------------------------------------------------------------
# BRANCHES  (from the Feature project: branch management, stock, sales)
# ----------------------------------------------------------------------
@admin_bp.route("/branches")
def branches():
    rows = get_db().execute(
        "SELECT br.*, COALESCE((SELECT SUM(s.stock_count) FROM branch_stock s WHERE s.branch_id = br.id),0) AS units "
        "FROM branches br ORDER BY br.id DESC").fetchall()
    return render_template("admin/branches.html", branches=rows)


def read_branch_form():
    form = {k: request.form.get(k, "").strip() for k in ("branch_name", "address", "city", "phone", "manager_name", "status")}
    if not form["status"]:
        form["status"] = "Active"
    if not all([form["branch_name"], form["address"], form["city"], form["manager_name"]]):
        return form, "Branch name, address, city and manager are required."
    if not PHONE_RE.match(form["phone"]):
        return form, "Enter a valid 10-digit phone number."
    if form["status"] not in BRANCH_STATUSES:
        return form, "Choose a valid status."
    return form, None


@admin_bp.route("/branches/new", methods=["GET", "POST"])
def branch_new():
    form = {"branch_name": "", "address": "", "city": "", "phone": "", "manager_name": "", "status": "Active"}
    if request.method == "POST":
        form, error = read_branch_form()
        if error:
            flash(error, "danger")
        else:
            db = get_db()
            db.execute("INSERT INTO branches (branch_name, address, city, phone, manager_name, status) "
                       "VALUES (?,?,?,?,?,?)", tuple(form[k] for k in
                                                     ("branch_name", "address", "city", "phone", "manager_name", "status")))
            db.commit()
            sync_branch_stock(db)
            flash(f"Branch '{form['branch_name']}' was added. Set its stock on the Branch Stock page.", "success")
            return redirect(url_for("admin.branches"))
    return render_template("admin/branch_form.html", form=form, is_new=True, branch=None)


@admin_bp.route("/branches/<int:branch_id>/edit", methods=["GET", "POST"])
def branch_edit(branch_id):
    db = get_db()
    branch = db.execute("SELECT * FROM branches WHERE id = ?", (branch_id,)).fetchone()
    if not branch:
        flash("Branch not found.", "danger")
        return redirect(url_for("admin.branches"))
    form = {k: branch[k] for k in ("branch_name", "address", "city", "phone", "manager_name", "status")}
    if request.method == "POST":
        form, error = read_branch_form()
        if error:
            flash(error, "danger")
        else:
            db.execute("UPDATE branches SET branch_name=?, address=?, city=?, phone=?, manager_name=?, status=? "
                       "WHERE id=?", (*[form[k] for k in ("branch_name", "address", "city", "phone",
                                                          "manager_name", "status")], branch_id))
            db.commit()
            flash("Branch updated.", "success")
            return redirect(url_for("admin.branches"))
    return render_template("admin/branch_form.html", form=form, is_new=False, branch=branch)


@admin_bp.route("/branches/<int:branch_id>/delete", methods=["POST"])
def branch_delete(branch_id):
    db = get_db()
    branch = db.execute("SELECT * FROM branches WHERE id = ?", (branch_id,)).fetchone()
    if branch:
        db.execute("UPDATE bookings SET branch_id = NULL WHERE branch_id = ?", (branch_id,))
        db.execute("DELETE FROM branch_stock WHERE branch_id = ?", (branch_id,))
        db.execute("DELETE FROM branches WHERE id = ?", (branch_id,))
        db.commit()
        flash(f"Branch '{branch['branch_name']}' was deleted. Its past bookings were kept.", "success")
    return redirect(url_for("admin.branches"))


@admin_bp.route("/branches/stock")
def branch_stock():
    db = get_db()
    branch_id = request.args.get("branch", type=int)
    q = request.args.get("q", "").strip()
    sql = ("SELECT s.id, s.stock_count, b.id AS branch_id, b.branch_name, b.status AS branch_status, "
           "i.name AS idol_name, i.category, i.stock_count AS shop_stock FROM branch_stock s "
           "JOIN branches b ON s.branch_id = b.id JOIN idols i ON s.idol_id = i.id WHERE 1=1")
    params = []
    if branch_id:
        sql += " AND b.id = ?"
        params.append(branch_id)
    if q:
        sql += " AND i.name LIKE ?"
        params.append(f"%{q}%")
    rows = db.execute(sql + " ORDER BY b.branch_name, i.category, i.name", params).fetchall()
    all_branches = db.execute("SELECT id, branch_name FROM branches ORDER BY branch_name").fetchall()
    totals = db.execute("SELECT b.id, b.branch_name, COALESCE(SUM(s.stock_count),0) AS units FROM branches b "
                        "LEFT JOIN branch_stock s ON s.branch_id = b.id GROUP BY b.id, b.branch_name "
                        "ORDER BY b.branch_name").fetchall()
    return render_template("admin/branch_stock.html", rows=rows, all_branches=all_branches, totals=totals,
                           branch_id=branch_id, q=q)


@admin_bp.route("/branches/stock/<int:stock_id>", methods=["POST"])
def branch_stock_update(stock_id):
    try:
        qty = int(request.form.get("stock_count", ""))
    except ValueError:
        qty = -1
    if qty < 0:
        flash("Enter a stock number of 0 or more.", "danger")
    else:
        db = get_db()
        db.execute("UPDATE branch_stock SET stock_count = ? WHERE id = ?", (qty, stock_id))
        db.commit()
        flash("Branch stock updated.", "success")
    return back_to("admin.branch_stock")


@admin_bp.route("/branches/sales")
def branch_sales():
    db = get_db()
    rows = db.execute(
        "SELECT br.id, br.branch_name, br.city, br.status, COUNT(b.id) AS total_orders, "
        "COALESCE(SUM(b.total_price),0) AS total_sales FROM branches br "
        "LEFT JOIN bookings b ON b.branch_id = br.id AND b.status != 'Cancelled' "
        "GROUP BY br.id, br.branch_name, br.city, br.status ORDER BY total_sales DESC").fetchall()
    unassigned = db.execute("SELECT COUNT(*) AS c, COALESCE(SUM(total_price),0) AS s FROM bookings "
                            "WHERE branch_id IS NULL AND status != 'Cancelled'").fetchone()
    top = max([float(r["total_sales"]) for r in rows] + [1])
    return render_template("admin/branch_sales.html", rows=rows, unassigned=unassigned, top=top)


# ----------------------------------------------------------------------
# RESTOCK ALERTS  (from the Feature project)
# ----------------------------------------------------------------------
@admin_bp.route("/restock")
def restock():
    db = get_db()
    status = request.args.get("status", "all")
    sql = ("SELECT a.*, i.name AS idol_name, i.stock_count, u.username FROM restock_alerts a "
           "JOIN idols i ON a.idol_id = i.id LEFT JOIN users u ON a.user_id = u.id WHERE 1=1")
    params = []
    if status in ("Waiting", "Ready", "Notified"):
        sql += " AND a.status = ?"
        params.append(status)
    rows = db.execute(sql + " ORDER BY a.id DESC", params).fetchall()
    counts = {r["status"]: r["c"] for r in db.execute(
        "SELECT status, COUNT(*) AS c FROM restock_alerts GROUP BY status").fetchall()}
    return render_template("admin/restock.html", rows=rows, status=status, counts=counts)


@admin_bp.route("/restock/check", methods=["POST"])
def restock_check():
    db = get_db()
    cur = db.execute(
        "UPDATE restock_alerts SET status = 'Ready' WHERE status = 'Waiting' AND idol_id IN "
        "(SELECT id FROM idols WHERE stock_count > 0)")
    db.commit()
    n = cur.rowcount
    flash(f"{n} alert(s) are now ready to notify." if n else "No waiting item has been restocked yet.",
          "success" if n else "info")
    return redirect(url_for("admin.restock"))


@admin_bp.route("/restock/<int:alert_id>/notified", methods=["POST"])
def restock_notified(alert_id):
    db = get_db()
    db.execute("UPDATE restock_alerts SET status = 'Notified' WHERE id = ?", (alert_id,))
    db.commit()
    flash("Marked as notified.", "success")
    return back_to("admin.restock")


@admin_bp.route("/restock/<int:alert_id>/delete", methods=["POST"])
def restock_delete(alert_id):
    db = get_db()
    db.execute("DELETE FROM restock_alerts WHERE id = ?", (alert_id,))
    db.commit()
    flash("Alert removed.", "success")
    return back_to("admin.restock")


# ----------------------------------------------------------------------
# ADMIN PROFILE
# ----------------------------------------------------------------------
@admin_bp.route("/profile", methods=["GET", "POST"])
def profile():
    db = get_db()
    user = db.execute("SELECT * FROM users WHERE id = ?", (session["user_id"],)).fetchone()
    if request.method == "POST":
        current = request.form.get("current_password", "")
        new = request.form.get("new_password", "")
        confirm = request.form.get("confirm_password", "")
        if not check_login_password(db, user, current):
            flash("Your current password is incorrect.", "danger")
        elif len(new) < 6:
            flash("The new password must be at least 6 characters.", "danger")
        elif new != confirm:
            flash("The new passwords do not match.", "danger")
        elif new == current:
            flash("Choose a password different from the current one.", "warning")
        else:
            db.execute("UPDATE users SET password = ? WHERE id = ?", (hash_pw(new), user["id"]))
            db.commit()
            flash("Password changed successfully.", "success")
            return redirect(url_for("admin.profile"))
    return render_template("admin/profile.html", user=user)
