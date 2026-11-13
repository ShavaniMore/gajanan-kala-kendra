/* Chat widget for the AI assistant. Sends messages to /assistant/chat (Flask -> Ollama). */
document.addEventListener("DOMContentLoaded", () => {
    const box = document.getElementById("aiBox");
    if (!box) return;
    const toggle = document.getElementById("aiToggle");
    const form = document.getElementById("aiForm");
    const input = document.getElementById("aiInput");
    const log = document.getElementById("aiLog");
    const csrf = box.dataset.csrf;
    let busy = false;                           // only one question at a time
    const history = [];                         // last messages, sent back so the bot remembers

    const add = (text, who) => {
        const div = document.createElement("div");
        div.className = "ai-msg " + who;
        div.textContent = text;                 // textContent (never innerHTML) -> no HTML injection
        log.appendChild(div);
        log.scrollTop = log.scrollHeight;
        return div;
    };
    const open = state => {
        box.classList.toggle("open", state);
        if (state) input.focus();
    };
    toggle.addEventListener("click", () => open(!box.classList.contains("open")));
    document.getElementById("aiClose").addEventListener("click", () => open(false));
    add(box.dataset.hello, "bot");

    box.querySelectorAll("[data-ai-q]").forEach(chip => chip.addEventListener("click", () => {
        input.value = chip.dataset.aiQ; form.requestSubmit();
    }));

    form.addEventListener("submit", async e => {
        e.preventDefault();
        const text = input.value.trim();
        if (!text || busy) return;
        busy = true;
        input.value = "";
        add(text, "user");
        const wait = add("Thinking… (the first answer can take up to a minute)", "bot typing");
        input.disabled = true;
        try {
            const fd = new FormData();
            fd.append("_csrf", csrf);
            fd.append("message", text);
            fd.append("lang", document.documentElement.getAttribute("lang") || "en");
            fd.append("history", JSON.stringify(history));
            const ctl = new AbortController();
            const timer = setTimeout(() => ctl.abort(), 150000);
            const res = await fetch("/assistant/chat", { method: "POST", body: fd, signal: ctl.signal });
            clearTimeout(timer);
            const type = res.headers.get("content-type") || "";
            let answer = "";
            if (type.includes("application/json")) {          // hosted AI, or an error message
                answer = (await res.json()).reply;
                wait.textContent = answer;
            } else {                                          // Ollama: words arrive while it is still writing
                const reader = res.body.getReader();
                const dec = new TextDecoder();
                wait.textContent = "";
                for (;;) {
                    const { done, value } = await reader.read();
                    if (done) break;
                    answer += dec.decode(value, { stream: true });
                    wait.textContent = answer;
                    log.scrollTop = log.scrollHeight;
                }
            }
            wait.classList.remove("typing");
            if (res.ok && answer) {
                history.push({ role: "user", content: text }, { role: "assistant", content: answer });
                if (history.length > 8) history.splice(0, 2);
            }
        } catch (_) {
            wait.textContent = "No answer received. Please check that the AI is running and try again.";
            wait.classList.remove("typing");
        }
        busy = false; input.disabled = false; input.focus();
    });
});
