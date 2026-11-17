#!/usr/bin/env python3
"""PageSprint — one-page websites for local businesses, delivered in 24h.
Local control dashboard: leads, outreach pitches, orders, AI site builder, revenue.
Stdlib only. Run: python3 app.py  ->  http://127.0.0.1:8790
"""
import json, os, re, sqlite3, urllib.request, html
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DB = ROOT / "data.db"
SITES = ROOT / "sites"
TEMPLATES = ROOT / "templates"
PUBLIC = ROOT / "public"
CONFIG = ROOT / "config.json"
PORT = int(os.environ.get("PAGESPRINT_PORT", "8790"))
LLM_BASE = "http://127.0.0.1:18900/v1"
LLM_KEY_FILE = Path.home() / ".our-free-model" / "settings.json"

DEFAULT_CONFIG = {
    "brand": "PageSprint",
    "price": 490,
    "currency": "MAD ",
    "payment_link": "",
    "contact_email": "easonjadaklmica@gmail.com",
    "whatsapp": "",
    "payment_note": "Pay by bank transfer (virement) or Cash Plus after you approve your free preview — details on request.",
    "bank_details": "",
    "services": [
        {"name": "Starter One-Page Site", "price": 490,
         "features": ["One clean mobile-friendly page", "Your services, hours and contact",
                      "Free preview before you pay", "Delivered within 24 hours"]},
        {"name": "Business Site", "price": 990,
         "features": ["Everything in Starter", "Contact form + WhatsApp button",
                      "Photo gallery and Google Maps location", "One round of changes included"]},
        {"name": "Full Launch Pack", "price": 1490,
         "features": ["Everything in Business", "We put it online for you (hosting included)",
                      "Help getting found on Google", "Priority 12-hour delivery"]}
    ],
    "models": ["deepseek-v4.1-flash-free", "glm-5.3-flash-free", "big-pickle", "kilo-auto/free"],
}


def cfg():
    c = dict(DEFAULT_CONFIG)
    if CONFIG.exists():
        c.update(json.loads(CONFIG.read_text()))
    return c


def db():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    return con


def init():
    SITES.mkdir(exist_ok=True)
    PUBLIC.mkdir(exist_ok=True)
    if not CONFIG.exists():
        CONFIG.write_text(json.dumps(DEFAULT_CONFIG, indent=2))
    with db() as con:
        con.executescript("""
        create table if not exists leads(id integer primary key, business text, kind text, city text,
          contact text, status text default 'new', pitch text default '', notes text default '',
          created text default current_timestamp);
        create table if not exists orders(id integer primary key, business text, kind text, city text,
          contact text, details text default '', price real default 0, status text default 'unpaid',
          site text default '', created text default current_timestamp);
        """)
        cols = [r[1] for r in con.execute("pragma table_info(orders)")]
        if "template" not in cols:
            con.execute("alter table orders add column template text default ''")
    render_store()


AGENT_MARKERS = ("/home/", "shell tool", "working directory", "paste the relevant",
                 "what would you like me to do", "i'll start by", "explore the repository",
                 "tools are described", "debug or fix")


def llm(prompt, max_tokens=6000, reject=()):
    messages = prompt if isinstance(prompt, list) else [{"role": "user", "content": prompt}]
    key = json.loads(LLM_KEY_FILE.read_text())["forwardKey"]
    last = "no model tried"
    for model in cfg()["models"]:
        body = json.dumps({"model": model, "max_tokens": max_tokens,
                           "messages": messages}).encode()
        req = urllib.request.Request(LLM_BASE + "/chat/completions", data=body, headers={
            "Authorization": "Bearer " + key, "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=180) as r:
                text = json.load(r)["choices"][0]["message"].get("content") or ""
            low = text.strip().lower()
            if text.strip() and not any(m in low for m in reject):
                return text.strip()
            last = f"{model}: {'agent-style reply rejected' if text.strip() else 'empty reply'}"
        except Exception as e:  # try the next free model
            last = f"{model}: {e}"
    raise RuntimeError("all models failed (" + last + ")")


def make_pitch(lead):
    c = cfg()
    return llm(
        f"Write a short, friendly, honest first-contact message (max 90 words, no emojis, no hype, "
        f"no invented facts or statistics) to the owner of '{lead['business']}', a {lead['kind']} in "
        f"{lead['city']}. Offer: {c['brand']} builds a clean one-page mobile-friendly website for "
        f"their business within 24 hours for a flat {c['currency']}{c['price']}, and they see a free "
        f"preview before paying anything. End by asking if they'd like to see a free preview. "
        f"Output only the message text.", 400)


def templates():
    return sorted(d.name for d in TEMPLATES.iterdir()
                  if d.is_dir() and (d / "index.html").exists()) if TEMPLATES.exists() else []


def make_site(order):
    import shutil
    tpl = (order["template"] or "").strip()
    d = SITES / str(order["id"])
    base_prompt = (
        "Business name: {business}\nType: {kind}\nCity: {city}\n"
        "Contact: {contact}\nDetails from owner: {details}\n\n"
    ).format(**dict(order))
    if tpl and (TEMPLATES / tpl / "index.html").exists():
        if d.exists():
            shutil.rmtree(d)
        shutil.copytree(TEMPLATES / tpl, d)
        html_in = (d / "index.html").read_text()
        out = llm(
            "Below is an open-source one-page website template (MIT licensed). Rewrite it as the "
            "website for the client described afterwards: replace every placeholder text, business "
            "name, headline, paragraph, menu/service item, address, phone, email and footer with "
            "content for this client, in their language if their details are not in English. Keep ALL "
            "HTML structure, CSS classes, ids, scripts and image paths exactly as they are; only "
            "change text content (you may delete sections that do not apply). Use ONLY the facts "
            "given; where a fact is missing put a clearly marked placeholder like [PHONE] rather "
            "than inventing it. Do not invent testimonials, awards or reviews.\n\n"
            "=== TEMPLATE START ===\n" + html_in + "\n=== TEMPLATE END ===\n\nCLIENT:\n" + base_prompt +
            "Output only the complete rewritten HTML document.", 12000)
        m = re.search(r"<!DOCTYPE html>.*</html>", out, re.S | re.I)
        if not m:
            raise RuntimeError("model did not return a complete HTML document")
        (d / "index.html").write_text(m.group(0))
    else:
        out = llm(
            "Create a complete, production-quality single-file one-page website (HTML with inline CSS, "
            "no external scripts, no external images; use CSS gradients/emoji for visuals). Mobile-first, "
            "modern, fast. Sections: hero with call-to-action, about, services/menu, opening hours, "
            "contact/location, footer. Use ONLY the facts given below; where a fact is missing put a "
            "clearly marked placeholder like [PHONE] rather than inventing it. Do not invent "
            "testimonials, awards or reviews.\n\n"
            + base_prompt +
            "Output only the HTML document, starting with <!DOCTYPE html>.")
        m = re.search(r"<!DOCTYPE html>.*</html>", out, re.S | re.I)
        if not m:
            raise RuntimeError("model did not return a complete HTML document")
        d.mkdir(exist_ok=True)
        (d / "index.html").write_text(m.group(0))
    return f"/sites/{order['id']}/index.html"


def render_store():
    c = cfg()
    e = html.escape
    if c["payment_link"]:
        cta = f'<a class="btn" href="{e(c["payment_link"])}">Order now — {e(c["currency"])}{c["price"]}</a>'
    elif c["contact_email"]:
        cta = f'<a class="btn" href="mailto:{e(c["contact_email"])}?subject=Free%20website%20preview">Get a free preview</a>'
    else:
        cta = '<span class="btn off">Ordering opens soon</span>'
    contact = ""
    paynote = f'<span class="sub">{e(c["payment_note"])}</span>' if c.get("payment_note") else ""
    if c.get("bank_details"):
        paynote += (f'<div class="bankbox"><b>Paiement / Payment:</b><br>{e(c["bank_details"])}</div>')
    if c["contact_email"]:
        contact += f'<a href="mailto:{e(c["contact_email"])}">{e(c["contact_email"])}</a> '
    if c["whatsapp"]:
        contact += f'· <a href="https://wa.me/{e(re.sub(r"[^0-9]", "", c["whatsapp"]))}">WhatsApp</a>'
    tiers = ""
    for s in c.get("services", []):
        lis = "".join(f"<li>{e(f)}" for f in s.get("features", []))
        tcta = cta if not c["contact_email"] else \
            f'<a class="btn" href="mailto:{e(c["contact_email"])}?subject=Order:%20{e(s["name"])}">Order this</a>'
        tiers += (f'<div class="tier"><h3>{e(s["name"])}</h3>'
                  f'<div class="p">{e(c["currency"])}{int(s["price"])}</div>'
                  f'<ul>{lis}</ul>{tcta}</div>')
    page = (ROOT / "store.template.html").read_text()
    for k, v in {"BRAND": e(c["brand"]), "PRICE": f'{e(c["currency"])}{c["price"]}', "CTA": cta,
                 "CONTACT": contact or "Contact details coming soon", "PAYNOTE": paynote,
                 "TIERS": tiers or ""}.items():
        page = page.replace("{{" + k + "}}", v)
    (PUBLIC / "index.html").write_text(page)


def state():
    with db() as con:
        leads = [dict(r) for r in con.execute("select * from leads order by id desc")]
        orders = [dict(r) for r in con.execute("select * from orders order by id desc")]
    paid = [o for o in orders if o["status"] in ("paid", "delivered")]
    return {"config": cfg(), "leads": leads, "orders": orders, "templates": templates(), "stats": {
        "revenue": sum(o["price"] for o in paid), "paid_orders": len(paid),
        "unpaid": len([o for o in orders if o["status"] == "unpaid"]),
        "leads": len(leads), "contacted": len([l for l in leads if l["status"] != "new"]),
        "costs": 0}}


RESTAURANT_BOT_SYSTEM = (
    "You are 'Amal', the AI assistant for Pizza Amal, a wood-fired pizzeria in Marrakech "
    "that delivers. Facts you may use: open daily 11:00-00:00; menu: pizza margherita 40 MAD, "
    "pizza vegetarienne 50 MAD, pizza frutti di mare 70 MAD, burger 45 MAD, sandwich 30 MAD; "
    "delivery free in Marrakech center, 10 MAD outside; phone [PHONE]. "
    "Reply in the same language/dialect the customer writes in (darija, Arabic, French or "
    "English), friendly and concise (max 60 words). You may take simple orders and confirm "
    "them. If asked something you do not know, say you will check with the team — never "
    "invent facts.")


LEAD_F = ("business", "kind", "city", "contact", "status", "pitch", "notes")
ORDER_F = ("business", "kind", "city", "contact", "details", "price", "status", "site", "template")


def api(path, d):
    if path == "/api/chat":
        msgs = d.get("messages") or []
        if not msgs:
            raise ValueError("no messages")
        reply = llm([{"role": "system", "content": RESTAURANT_BOT_SYSTEM}] + msgs, 300,
                    reject=AGENT_MARKERS)
        return {"reply": reply}
    with db() as con:
        if path == "/api/lead":
            con.execute("insert into leads(business,kind,city,contact) values(?,?,?,?)",
                        (d["business"], d.get("kind", ""), d.get("city", ""), d.get("contact", "")))
        elif path == "/api/order":
            con.execute("insert into orders(business,kind,city,contact,details,price,template) values(?,?,?,?,?,?,?)",
                        (d["business"], d.get("kind", ""), d.get("city", ""), d.get("contact", ""),
                         d.get("details", ""), float(d.get("price") or cfg()["price"]), d.get("template", "")))
        elif path == "/api/update":
            table, fields = ("leads", LEAD_F) if d["table"] == "leads" else ("orders", ORDER_F)
            for k, v in d["set"].items():
                if k in fields:
                    con.execute(f"update {table} set {k}=? where id=?", (v, d["id"]))
        elif path == "/api/delete":
            table = "leads" if d["table"] == "leads" else "orders"
            con.execute(f"delete from {table} where id=?", (d["id"],))
        elif path == "/api/convert":
            l = con.execute("select * from leads where id=?", (d["id"],)).fetchone()
            con.execute("insert into orders(business,kind,city,contact,price) values(?,?,?,?,?)",
                        (l["business"], l["kind"], l["city"], l["contact"], cfg()["price"]))
            con.execute("update leads set status='converted' where id=?", (d["id"],))
        elif path == "/api/pitch":
            l = con.execute("select * from leads where id=?", (d["id"],)).fetchone()
            con.execute("update leads set pitch=? where id=?", (make_pitch(l), d["id"]))
        elif path == "/api/build":
            o = con.execute("select * from orders where id=?", (d["id"],)).fetchone()
            con.execute("update orders set site=? where id=?", (make_site(o), d["id"]))
        elif path == "/api/config":
            c = cfg()
            for k in ("brand", "price", "currency", "payment_link", "contact_email", "whatsapp", "payment_note", "bank_details"):
                if k in d:
                    c[k] = float(d[k]) if k == "price" else d[k]
            if "services" in d:
                try:
                    s = json.loads(d["services"] if isinstance(d["services"], str) else json.dumps(d["services"]))
                    if isinstance(s, list) and all(isinstance(x, dict) and "name" in x and "price" in x for x in s):
                        c["services"] = s
                except (ValueError, TypeError):
                    pass
            if c["price"] == int(c["price"]):
                c["price"] = int(c["price"])
            CONFIG.write_text(json.dumps(c, indent=2))
            render_store()
        else:
            raise KeyError("unknown endpoint")
    return state()


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def send(self, code, body, ctype="application/json"):
        if not isinstance(body, bytes):
            body = (body if isinstance(body, str) else json.dumps(body)).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype + "; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        p = self.path.split("?")[0]
        if p == "/":
            return self.send(200, (PUBLIC / "index.html").read_bytes(), "text/html")
        if p == "/dashboard":
            return self.send(200, (ROOT / "dashboard.html").read_bytes(), "text/html")
        if p == "/api/state":
            return self.send(200, state())
        if p == "/store":
            return self.send(200, (PUBLIC / "index.html").read_bytes(), "text/html")
        if p == "/chatbot":
            return self.send(200, (ROOT / "chatbot.html").read_bytes(), "text/html")
        m = re.fullmatch(r"/sites/(\d+)/([\w./-]+)", p)
        if m and (SITES / m.group(1)).exists():
            f = (SITES / m.group(1) / m.group(2)).resolve()
            if f.is_file() and str(f).startswith(str((SITES / m.group(1)).resolve()) + os.sep):
                ctype = {"css": "text/css", "js": "text/javascript", "svg": "image/svg+xml",
                         "png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg",
                         "ico": "image/x-icon", "woff": "font/woff", "woff2": "font/woff2"}.get(
                             f.suffix.lstrip(".").lower(), "application/octet-stream")
                return self.send(200, f.read_bytes(), ctype)
        self.send(404, {"error": "not found"})

    def do_POST(self):
        try:
            d = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
            self.send(200, api(self.path, d))
        except Exception as e:
            self.send(400, {"error": str(e)})


if __name__ == "__main__":
    init()
    print(f"PageSprint dashboard: http://127.0.0.1:{PORT}")
    ThreadingHTTPServer(("127.0.0.1", PORT), H).serve_forever()
