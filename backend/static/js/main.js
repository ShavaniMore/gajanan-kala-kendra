document.addEventListener("DOMContentLoaded", () => {
    /* ---------- left side navigation (mobile drawer) ---------- */
    const menuBtn = document.getElementById("menuBtn");
    const navMenu = document.getElementById("navMenu");
    const siteSide = document.getElementById("siteSide");
    const siteScrim = document.getElementById("siteScrim");
    const drawer = open => { siteSide?.classList.toggle("open", open); siteScrim?.classList.toggle("open", open); };
    menuBtn?.addEventListener("click", () => drawer(!siteSide.classList.contains("open")));
    siteScrim?.addEventListener("click", () => drawer(false));
    navMenu?.querySelectorAll("a").forEach(link => link.addEventListener("click", () => drawer(false)));

    /* ---------- dark / light mode ---------- */
    const root = document.documentElement;
    const paintTheme = () => document.querySelectorAll("[data-theme-toggle] i").forEach(i =>
        i.className = root.getAttribute("data-theme") === "dark" ? "bi bi-sun-fill" : "bi bi-moon-stars-fill");
    paintTheme();
    document.querySelectorAll("[data-theme-toggle]").forEach(btn => btn.addEventListener("click", () => {
        const next = root.getAttribute("data-theme") === "dark" ? "light" : "dark";
        root.setAttribute("data-theme", next);
        try { localStorage.setItem("gkk-theme", next); } catch (_) {}
        paintTheme();
    }));

    /* ---------- intro: colour fills Bappa from the bottom, then flowers shower ---------- */
    const splash = document.getElementById("splash");
    if (splash && root.classList.contains("splash-on")) {
        let finished = false;
        const finish = () => {
            if (finished) return; finished = true;
            try { sessionStorage.setItem("gkk-intro", "1"); } catch (_) {}
            splash.classList.add("hide");
            setTimeout(() => { root.classList.remove("splash-on"); splash.remove(); }, 750);
        };
        const flowers = ["🌸", "🌼", "🏵️", "🌺", "💮", "🌻"];
        const shower = () => {
            const box = document.getElementById("petals");
            const total = window.innerWidth < 600 ? 45 : 85;
            for (let i = 0; i < total; i++) {
                const f = document.createElement("span");
                f.className = "petal";
                f.textContent = flowers[Math.floor(Math.random() * flowers.length)];
                f.style.left = Math.random() * 100 + "%";
                f.style.fontSize = (18 + Math.random() * 24) + "px";
                f.style.setProperty("--dx", (Math.random() * 160 - 80) + "px");
                f.style.setProperty("--rot", (Math.random() * 720 - 360) + "deg");
                f.style.animationDuration = (2.6 + Math.random() * 2.2) + "s";
                f.style.animationDelay = (Math.random() * 1.6) + "s";
                box.appendChild(f);
            }
        };
        const color = splash.querySelector(".g-color");
        color.addEventListener("animationend", () => {
            splash.classList.add("filled");
            shower();
            setTimeout(finish, 4600);
        });
        document.getElementById("splashSkip")?.addEventListener("click", finish);
        setTimeout(finish, 11000);   // safety net
    }

    /* ---------- flash messages: close button + auto hide ---------- */
    document.querySelectorAll(".flash").forEach(flash => {
        flash.querySelector("button")?.addEventListener("click", () => flash.remove());
        setTimeout(() => flash.remove(), 7000);
    });

    /* ---------- festival countdown (date comes from app.py) ---------- */
    const countdown = document.getElementById("countdown");
    if (countdown) {
        const target = new Date(countdown.dataset.festival).getTime();
        const timer = countdown.querySelector(".countdown-timer");
        const over = countdown.querySelector(".countdown-over");
        const pad = n => String(n).padStart(2, "0");
        const set = (id, v) => { const el = document.getElementById(id); if (el) el.textContent = pad(v); };

        const tick = () => {
            const distance = target - Date.now();
            if (distance <= 0) {
                timer?.setAttribute("hidden", "");
                over?.removeAttribute("hidden");
                return false;
            }
            set("days", Math.floor(distance / 86400000));
            set("hours", Math.floor(distance / 3600000) % 24);
            set("minutes", Math.floor(distance / 60000) % 60);
            set("seconds", Math.floor(distance / 1000) % 60);
            return true;
        };
        if (tick()) {
            const id = setInterval(() => { if (!tick()) clearInterval(id); }, 1000);
        }
    }

    /* ---------- catalogue: auto-apply radio / size filters ---------- */
    document.querySelectorAll("[data-autosubmit]").forEach(el =>
        el.addEventListener("change", () => el.form.submit()));

    /* ---------- booking form: live total + delivery address hint ---------- */
    const qty = document.getElementById("quantity");
    const totalEl = document.getElementById("liveTotal");
    if (qty && totalEl) {
        const unit = parseFloat(totalEl.dataset.unit);
        const update = () => {
            const q = Math.max(1, Math.min(parseInt(qty.value) || 1, parseInt(qty.max) || 10));
            totalEl.textContent = "₹" + (unit * q).toLocaleString("en-IN");
        };
        qty.addEventListener("input", update);
        update();
    }
    const delivery = document.getElementById("delivery_option");
    const addrLabel = document.getElementById("addressLabel");
    if (delivery && addrLabel) {
        const sync = () => {
            addrLabel.textContent = delivery.value === "Home Delivery"
                ? "Delivery Address *" : "Pickup Note (optional)";
        };
        delivery.addEventListener("change", sync);
        sync();
    }

    /* ---------- toast + nav counters ---------- */
    const toast = msg => {
        const box = document.getElementById("toastBox");
        if (!box) return;
        const t = document.createElement("div");
        t.className = "toast"; t.textContent = msg; box.appendChild(t);
        setTimeout(() => t.remove(), 2600);
    };
    const setCounts = c => {
        if (!c) return;
        [["[data-wish-count]", c.wish], ["[data-cart-count]", c.cart]].forEach(([sel, n]) =>
            document.querySelectorAll(sel).forEach(el => { el.textContent = n; el.hidden = !n; }));
    };

    /* ---------- wishlist hearts / add-to-cart (no page reload) ---------- */
    document.querySelectorAll("form[data-ajax]").forEach(form =>
        form.addEventListener("submit", async e => {
            e.preventDefault();
            try {
                const res = await fetch(form.action, {method: "POST", body: new FormData(form),
                                        headers: {"X-Requested-With": "XMLHttpRequest"}});
                const data = await res.json();
                if (res.status === 401 && data.login) { window.location = data.login; return; }
                setCounts(data.counts);
                toast(data.message || "Done");
                const heart = form.querySelector("[data-wish-btn]");
                if (heart && data.saved !== undefined) {
                    heart.classList.toggle("on", data.saved);
                    heart.querySelector("i").className = data.saved ? "bi bi-heart-fill" : "bi bi-heart";
                    if (!data.saved && document.body.dataset.page === "wishlist") form.closest(".product-card")?.remove();
                }
            } catch (_) { form.submit(); }
        }));

    /* ---------- demo payment box ---------- */
    const payBox = document.getElementById("payBox");
    if (payBox) {
        const money = n => "\u20B9" + Number(n).toLocaleString("en-IN", {maximumFractionDigits: 2});
        const totalEl = document.getElementById("liveTotal");
        const qtyEl = document.getElementById("quantity");
        const getTotal = () => {
            if (totalEl && qtyEl) {
                const q = Math.max(1, Math.min(parseInt(qtyEl.value) || 1, parseInt(qtyEl.max) || 10));
                return parseFloat(totalEl.dataset.unit) * q;
            }
            return parseFloat(payBox.dataset.total) || 0;
        };
        const refresh = () => {
            const total = getTotal();
            const type = payBox.querySelector("[name=pay_type]:checked")?.value || "full";
            payBox.querySelector("[data-pay-amount=advance]").textContent = money(total * 0.5);
            payBox.querySelector("[data-pay-amount=full]").textContent = money(total);
            document.getElementById("payNowAmount").textContent = money(type === "advance" ? total * 0.5 : total);
            const method = payBox.querySelector("[name=pay_method]:checked")?.value;
            payBox.querySelectorAll(".pay-panel").forEach(p => {
                const on = p.dataset.method === method;
                p.hidden = !on;
                p.querySelectorAll("input,select").forEach(i => i.disabled = !on);
            });
        };
        payBox.addEventListener("change", refresh);
        qtyEl?.addEventListener("input", refresh);
        refresh();
        const exp = document.getElementById("pay_exp");
        exp?.addEventListener("input", () => {
            let v = exp.value.replace(/\D/g, "").slice(0, 4);
            exp.value = v.length > 2 ? v.slice(0, 2) + "/" + v.slice(2) : v;
        });
        const card = document.getElementById("pay_card");
        card?.addEventListener("input", () => {
            card.value = card.value.replace(/\D/g, "").slice(0, 19).replace(/(.{4})/g, "$1 ").trim();
        });
        // required only for the visible method
        const syncRequired = () => {
            const m = payBox.querySelector("[name=pay_method]:checked")?.value;
            const need = {upi: ["pay_upi"], netbanking: ["pay_bank"], card: ["pay_card", "pay_card_name", "pay_exp", "pay_cvv"]}[m] || [];
            payBox.querySelectorAll(".pay-panel input,.pay-panel select").forEach(i => i.required = need.includes(i.id));
        };
        payBox.addEventListener("change", syncRequired);
        syncRequired();
    }

    /* ---------- payment processing animation on the receipt page ---------- */
    const overlay = document.getElementById("payOverlay");
    if (overlay) {
        setTimeout(() => {
            document.getElementById("paySpinner").hidden = true;
            document.getElementById("payTick").hidden = false;
            document.getElementById("payMsg").textContent = "Payment Successful!";
            document.getElementById("paySub").textContent = "Ganpati Bappa Morya \uD83D\uDE4F  Generating your receipt\u2026";
        }, 2200);
        setTimeout(() => { overlay.classList.add("hide"); setTimeout(() => overlay.remove(), 600); }, 3800);
    }
});
