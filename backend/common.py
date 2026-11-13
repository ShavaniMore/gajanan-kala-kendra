import re
from urllib.parse import quote_plus
import hmac
import secrets
from datetime import datetime
from functools import wraps

from flask import session, request, redirect, url_for, flash, abort
from werkzeug.security import check_password_hash

from database import get_db, hash_pw, scalar

# ----------------------------------------------------------------------
# SETTINGS  (edit here)
# ----------------------------------------------------------------------
# Ganesh Chaturthi date shown in the home page countdown (IST).
FESTIVAL_NAME = "Ganesh Chaturthi"
FESTIVAL_DATE = "2027-09-04T00:00:00+05:30"
FESTIVAL_LABEL = "4 September 2027"

# ---- shop contact details (change them here ONCE - footer and Contact section use these) ----
SHOP_PHONE = "+91 98765 43210"
SHOP_WHATSAPP = "919876543210"                  # country code + number, digits only (no + or spaces)
SHOP_INSTAGRAM = "https://www.instagram.com/gajanan_kala_kendra/"     # <- put your real Instagram link
SHOP_EMAIL = "gajanankalakendra19@gmail.com"
SHOP_ADDRESS = "Dadar & Lalbaug Workshop, Mumbai"
# clicking the e-mail opens a new Gmail "compose" window addressed to the shop (works even if the PC has no mail app)
SHOP_EMAIL_LINK = ("https://mail.google.com/mail/?view=cm&fs=1&to=" + SHOP_EMAIL +
                   "&su=" + quote_plus("Enquiry about Ganpati idols"))
# opens Google Maps with the address searched (use your exact address / shop name for a better pin)
SHOP_MAPS_URL = "https://www.google.com/maps/search/?api=1&query=" + quote_plus("Dadar Lalbaug Workshop Mumbai")

CATEGORIES = [
    ("Ready Ganpati", "Ready Ganpati", "Hand-sculpted, ready-to-worship classical idols."),
    ("Ecofriendly", "Eco-Friendly Clay", "100% natural Shadu clay idols with organic colours."),
    ("PoP Ganpati", "PoP Ganpati", "Durable, vibrant, lightweight designer idols."),
    ("Add-Ons", "Add-Ons & Jewellery", "Dhoti, Pheta, Modak, Mushak and ornaments."),
]
CATEGORY_VALUES = [c[0] for c in CATEGORIES]

BOOKING_STATUSES = ["Confirmed", "Ready for Pickup", "Out for Delivery", "Delivered", "Cancelled"]
PAYMENT_STATUSES = ["Pending", "Advance Paid (₹500)", "Advance Paid (50%)", "Paid in Full", "Refunded"]
DELIVERY_OPTIONS = ["Store Pickup", "Home Delivery"]
ADVANCE_AMOUNT = 500  # matches the default "Advance Paid (₹500)" payment status

PLACEHOLDER_IMAGE = "/static/images/placeholder.svg"

PHONE_RE = re.compile(r"^\d{10}$")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


# ----------------------------------------------------------------------
# AUTH HELPERS
# ----------------------------------------------------------------------
def safe_next(target):
    """Only allow redirects to paths inside this site."""
    if target and target.startswith("/") and not target.startswith("//"):
        return target
    return None


def login_required(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        if not session.get("user_id"):
            flash("Please login to continue.", "warning")
            return redirect(url_for("login", next=request.full_path.rstrip("?")))
        return view(*args, **kwargs)
    return wrapper


def check_login_password(db, user, password):
    """Verify a password. Old plain-text passwords are accepted once, then upgraded to a hash."""
    stored = user["password"] or ""
    if stored.startswith(("pbkdf2:", "scrypt:")):
        return check_password_hash(stored, password)
    if hmac.compare_digest(stored.encode(), password.encode()):
        db.execute("UPDATE users SET password = ? WHERE id = ?", (hash_pw(password), user["id"]))
        db.commit()
        return True
    return False


# ----------------------------------------------------------------------
# MONEY HELPERS (payments)
# ----------------------------------------------------------------------
def amount_collected(total, payment_status, status):
    """How much money has actually been received for a booking."""
    total = float(total or 0)
    if payment_status == "Paid in Full":
        return total
    if payment_status == "Advance Paid (50%)":
        return round(total * 0.5, 2)
    if payment_status and payment_status.startswith("Advance Paid"):
        return min(float(ADVANCE_AMOUNT), total)
    return 0.0


# ----------------------------------------------------------------------
# DEMO PAYMENT (no real money moves - nothing is charged, card details are never stored)
# ----------------------------------------------------------------------
PAYMENT_TYPES = {"full": "Full Payment", "advance": "50% Advance"}
PAYMENT_METHODS = {"upi": "UPI", "netbanking": "Net Banking", "card": "Credit / Debit Card", "cash": "Cash (pay at shop)"}
DEMO_BANKS = ["State Bank of India", "HDFC Bank", "ICICI Bank", "Axis Bank", "Kotak Mahindra Bank",
              "Bank of Baroda", "Punjab National Bank"]


def validate_payment(form, total):
    """Check the demo payment fields. Returns (payment dict, error message)."""
    ptype = form.get("pay_type", "full")
    method = form.get("pay_method", "")
    if ptype not in PAYMENT_TYPES:
        return None, "Choose 50% advance or full payment."
    if method not in PAYMENT_METHODS:
        return None, "Choose a payment method."
    if method == "upi" and not re.match(r"^[\w.\-]{2,}@[\w.\-]{2,}$", form.get("pay_upi", "").strip()):
        return None, "Enter a valid UPI ID (for example name@upi)."
    if method == "netbanking" and form.get("pay_bank", "") not in DEMO_BANKS:
        return None, "Select your bank for net banking."
    if method == "card":
        number = re.sub(r"\s+", "", form.get("pay_card", ""))
        if not re.match(r"^\d{12,19}$", number):
            return None, "Enter a valid card number."
        if not form.get("pay_card_name", "").strip():
            return None, "Enter the name on the card."
        if not re.match(r"^(0[1-9]|1[0-2])\s*/\s*\d{2}$", form.get("pay_exp", "").strip()):
            return None, "Enter the card expiry as MM/YY."
        if not re.match(r"^\d{3,4}$", form.get("pay_cvv", "").strip()):
            return None, "Enter the card CVV."
    total = float(total)
    payable = round(total * 0.5, 2) if ptype == "advance" else total
    if method == "cash":
        status = "Pending"                       # money is collected at the counter
    else:
        status = "Advance Paid (50%)" if ptype == "advance" else "Paid in Full"
    return {"type": ptype, "method": method, "payable": payable, "status": status,
            "txn_id": "TXN" + secrets.token_hex(5).upper(),
            "receipt_no": f"RCPT-{datetime.now():%y%m%d}-{secrets.token_hex(3).upper()}"}, None


# ----------------------------------------------------------------------
# CSRF PROTECTION (all POST forms carry a hidden _csrf field)
# ----------------------------------------------------------------------
def csrf_token():
    if "_csrf" not in session:
        session["_csrf"] = secrets.token_hex(16)
    return session["_csrf"]


def install(app):
    """Register filters, template globals, CSRF check and error pages on the app."""

    @app.before_request
    def csrf_protect():
        if request.method == "POST":
            sent = request.form.get("_csrf", "")
            if not sent or not hmac.compare_digest(sent, session.get("_csrf", "")):
                abort(400)

    @app.errorhandler(400)
    def bad_request(_err):
        flash("Your session expired or the form was invalid. Please try again.", "warning")
        return redirect(request.referrer or url_for("home"))

    @app.errorhandler(413)
    def too_large(_err):
        flash("That file is too large (maximum 4 MB).", "danger")
        return redirect(request.referrer or url_for("home"))

    @app.context_processor
    def inject_globals():
        wish_count = cart_count = 0
        wish_ids = set()
        uid = session.get("user_id")
        if uid:
            try:
                db = get_db()
                wish_count = scalar(db.execute("SELECT COUNT(*) FROM user_wishlist WHERE user_id = ?", (uid,)))
                wish_ids = {r["idol_id"] for r in db.execute("SELECT idol_id FROM user_wishlist WHERE user_id = ?", (uid,)).fetchall()}
                cart_count = scalar(db.execute("SELECT COALESCE(SUM(quantity),0) FROM user_cart_items WHERE user_id = ?", (uid,)))
            except Exception:
                pass
        return {
            "wish_ids": wish_ids,
            "wish_count": int(wish_count or 0),
            "cart_count": int(cart_count or 0),
            "payment_types": PAYMENT_TYPES,
            "payment_methods": PAYMENT_METHODS,
            "demo_banks": DEMO_BANKS,
            "shop": {"phone": SHOP_PHONE, "whatsapp": SHOP_WHATSAPP, "instagram": SHOP_INSTAGRAM,
                     "email": SHOP_EMAIL, "email_link": SHOP_EMAIL_LINK, "address": SHOP_ADDRESS, "maps": SHOP_MAPS_URL},
            "festival_name": FESTIVAL_NAME,
            "festival_date": FESTIVAL_DATE,
            "festival_label": FESTIVAL_LABEL,
            "categories": CATEGORIES,
            "booking_statuses": BOOKING_STATUSES,
            "payment_statuses": PAYMENT_STATUSES,
            "current_year": datetime.now().year,
            "csrf_token": csrf_token,
        }

    @app.template_filter("inr")
    def inr_filter(value):
        value = float(value or 0)
        return f"₹{value:,.0f}" if value == int(value) else f"₹{value:,.2f}"

    @app.template_filter("fdate")
    def fdate_filter(value):
        if value is None:
            return ""
        if hasattr(value, "strftime"):
            return value.strftime("%d %b %Y")
        try:
            return datetime.strptime(str(value)[:10], "%Y-%m-%d").strftime("%d %b %Y")
        except ValueError:
            return str(value)

    @app.template_filter("fdatetime")
    def fdatetime_filter(value):
        if value is None:
            return ""
        if hasattr(value, "strftime"):
            return value.strftime("%d %b %Y, %I:%M %p")
        try:
            return datetime.strptime(str(value)[:19], "%Y-%m-%d %H:%M:%S").strftime("%d %b %Y, %I:%M %p")
        except ValueError:
            return str(value)
