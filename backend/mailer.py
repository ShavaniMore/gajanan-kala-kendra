"""
Sends e-mails through SMTP (used for welcome / login e-mails and password reset).

Set these environment variables (see README):
    SMTP_HOST   e.g. smtp.gmail.com
    SMTP_PORT   587
    SMTP_USER   your Gmail address
    SMTP_PASS   a Gmail *App Password* (not your normal password)
    SMTP_FROM   optional, defaults to SMTP_USER

Without SMTP_HOST the e-mail is only printed in the terminal and saved in
backend/sent_emails.log, so you can test everything offline.
Mails are sent in a background thread so the website never waits for the mail server.
"""
import os
import smtplib
import threading
from datetime import datetime
from email.message import EmailMessage

BASE_DIR = os.path.abspath(os.path.dirname(__file__))


def send_mail(to_addr, subject, text, html=None):
    if not to_addr:
        return

    host = os.environ.get("SMTP_HOST")
    if not host:
        print(f"[Mail] SMTP not configured. Would send to {to_addr}: {subject}")
        try:
            with open(os.path.join(BASE_DIR, "sent_emails.log"), "a", encoding="utf8") as fh:
                fh.write(f"{datetime.now():%Y-%m-%d %H:%M:%S} | {to_addr} | {subject}\n{text}\n{'-' * 60}\n")
        except OSError:
            pass
        return

    def _send():
        try:
            msg = EmailMessage()
            msg["Subject"] = subject
            msg["From"] = os.environ.get("SMTP_FROM") or os.environ.get("SMTP_USER", "no-reply@localhost")
            msg["To"] = to_addr
            msg.set_content(text)
            if html:
                msg.add_alternative(html, subtype="html")
            with smtplib.SMTP(host, int(os.environ.get("SMTP_PORT", "587")), timeout=15) as s:
                s.starttls()
                if os.environ.get("SMTP_USER"):
                    s.login(os.environ["SMTP_USER"], os.environ.get("SMTP_PASS", ""))
                s.send_message(msg)
        except Exception as exc:                      # never break the website because of mail
            print(f"[Mail] Could not send to {to_addr}: {exc}")

    threading.Thread(target=_send, daemon=True).start()


def _html_wrap(title, lines):
    body = "".join(f"<p style='margin:0 0 12px'>{l}</p>" for l in lines)
    return (f"<div style='font-family:Arial,sans-serif;max-width:520px;margin:auto;border:1px solid #eadfd3;"
            f"border-radius:14px;overflow:hidden'><div style='background:#8f1d14;color:#fff;padding:18px 22px;"
            f"font-size:20px'>🪔 Gajanan Kala Kendra</div><div style='padding:22px;color:#251a17;font-size:15px;"
            f"line-height:1.6'><h2 style='margin:0 0 14px;color:#8f1d14'>{title}</h2>{body}"
            f"<p style='color:#766b65;font-size:12px;margin-top:22px'>Ganpati Bappa Morya 🙏</p></div></div>")


def send_welcome_email(user):
    """Sent right after a new account is created."""
    name = user["username"]
    text = (f"Namaste {name},\n\nWelcome to Gajanan Kala Kendra! Your account is ready.\n"
            "Browse handcrafted Ganpati idols, add shringar, book your Bappa and track your order online.\n\n"
            "Thank you for choosing us.\nGanpati Bappa Morya 🙏")
    html = _html_wrap(f"Welcome, {name}!", [
        "Your account is ready. Browse handcrafted Ganpati idols, add shringar, book your Bappa and track your order online.",
        "Thank you for choosing Gajanan Kala Kendra."])
    send_mail(user["email"], "Welcome to Gajanan Kala Kendra 🙏", text, html)


def send_login_email(user, ip=""):
    """Sent every time a customer logs in (also works as a security alert)."""
    name = user["username"]
    when = datetime.now().strftime("%d %b %Y, %I:%M %p")
    text = (f"Namaste {name},\n\nWelcome back to Gajanan Kala Kendra! Thank you for visiting us again.\n"
            f"You signed in on {when}" + (f" (IP {ip})" if ip else "") + ".\n\n"
            "If this was not you, please reset your password immediately from the Forgot Password page.\n\n"
            "Ganpati Bappa Morya 🙏")
    html = _html_wrap(f"Welcome back, {name}!", [
        "Thank you for visiting Gajanan Kala Kendra again.",
        f"You signed in on <b>{when}</b>" + (f" (IP {ip})" if ip else "") + ".",
        "If this was not you, please reset your password right away from the Forgot Password page."])
    send_mail(user["email"], "Welcome back to Gajanan Kala Kendra 🙏", text, html)


# ----------------------------------------------------------------------
# LOW STOCK ALERT  (e-mail to the shop admin)
# ----------------------------------------------------------------------
def admin_emails(db):
    """ADMIN_ALERT_EMAIL (comma separated) if set in .env, otherwise the e-mail of every active admin account."""
    env = os.environ.get("ADMIN_ALERT_EMAIL", "").strip()
    if env:
        return [e.strip() for e in env.split(",") if e.strip()]
    rows = db.execute("SELECT email FROM users WHERE role = 'admin' AND is_active = 1").fetchall()
    return [r["email"] for r in rows if r["email"]]


def notify_low_stock(db, idol_id, stock_before):
    """
    Call right after a sale reduced the stock of one item (stock_before = stock before that sale).
    Sends ONE mail when the stock falls to / below its low-stock limit, and ONE when it reaches zero,
    so the admin is not spammed on every following sale.
    """
    try:
        item = db.execute("SELECT name, stock_count, low_stock_limit FROM idols WHERE id = ?", (idol_id,)).fetchone()
        if not item:
            return
        now, limit = int(item["stock_count"] or 0), int(item["low_stock_limit"] or 0)
        out_now = now <= 0 < stock_before
        low_now = now <= limit < stock_before
        if not (out_now or low_now):
            return
        name = item["name"]
        if now <= 0:
            subject = f"OUT OF STOCK: {name}"
            headline = f"{name} is now OUT OF STOCK."
        else:
            subject = f"Low stock alert: {name} (only {now} left)"
            headline = f"{name} is running low: only {now} left (alert level is {limit})."
        when = datetime.now().strftime("%d %b %Y, %I:%M %p")
        text = (f"Namaste Admin,\n\n{headline}\nTime: {when}\n\n"
                "Please restock it from Admin Panel > Stock.\n\nGajanan Kala Kendra - Ganpati Shop")
        html = _html_wrap(subject, [headline, f"Time: {when}",
                                    "Please restock it from <b>Admin Panel → Stock</b>."])
        for addr in admin_emails(db):
            send_mail(addr, subject, text, html)
    except Exception as exc:                       # an alert problem must never break a customer's booking
        print(f"[Mail] low-stock alert failed: {exc}")


def send_low_stock_report(db):
    """E-mail the admin a list of every active product that is low or out of stock. Returns (count, recipients)."""
    rows = db.execute("SELECT name, stock_count, low_stock_limit FROM idols "
                      "WHERE is_active = 1 AND stock_count <= low_stock_limit ORDER BY stock_count, name").fetchall()
    if not rows:
        return 0, []
    out = [r for r in rows if int(r["stock_count"] or 0) <= 0]
    low = [r for r in rows if int(r["stock_count"] or 0) > 0]
    lines = []
    if out:
        lines.append("OUT OF STOCK:")
        lines += [f"  - {r['name']}" for r in out]
    if low:
        lines.append("LOW STOCK:")
        lines += [f"  - {r['name']}: {r['stock_count']} left (alert level {r['low_stock_limit']})" for r in low]
    when = datetime.now().strftime("%d %b %Y, %I:%M %p")
    subject = f"Stock report: {len(out)} out of stock, {len(low)} low"
    text = (f"Namaste Admin,\n\nStock report ({when}):\n\n" + "\n".join(lines) +
            "\n\nPlease restock from Admin Panel > Stock.\n\nGajanan Kala Kendra - Ganpati Shop")
    html = _html_wrap(subject, [f"Stock report ({when})"] + [l.replace("  - ", "• ") for l in lines] +
                      ["Please restock from <b>Admin Panel → Stock</b>."])
    to = admin_emails(db)
    for addr in to:
        send_mail(addr, subject, text, html)
    return len(rows), to
