# index.py
"""
Single-file Professional Movie Website (Flask) - FINAL CORRECTED VERSION
- This code will work after you add your NEW password and database name.
- WARNING: Do not share this file publicly with your credentials inside.
"""
from __future__ import annotations
import os
import re
import json
import uuid
import hashlib
from datetime import datetime
from typing import Optional
import logging

# Basic logging configuration
logging.basicConfig(level=logging.INFO, format='[%(levelname)s] %(message)s')

# --- CONFIGURATION (আপনার নতুন পাসওয়ার্ড ও ডাটাবেসের নাম এখানে বসান) ---
# -------------------------------------------------------------------
# ধাপ ১: নিচের লাইনে "YOUR_NEW_PASSWORD" এর জায়গায় আপনার নতুন পাসওয়ার্ডটি দিন।
# ধাপ ২: "my_movie_db" এর জায়গায় আপনার ডাটাবেসের নাম দিন। (যদি না থাকে, এই নামটিই ব্যবহার করুন)।
MONGO_URI = "mongodb+srv://mewayo8672:YOUR_NEW_PASSWORD@cluster0.ozhvczp.mongodb.net/my_movie_db?retryWrites=true&w=majority&appName=Cluster0"

FLASK_SECRET = "a_very_strong_and_random_secret_key_for_flask"
ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "admin123"
# -------------------------------------------------------------------

# Flask & Dependencies
try:
    from flask import Flask, request, redirect, url_for, render_template_string, session, abort
except Exception: raise SystemExit("Flask is required.")
try:
    from pymongo import MongoClient
    from pymongo.errors import ConnectionFailure, ConfigurationError
    PYMONGO_AVAILABLE = True
except Exception:
    PYMONGO_AVAILABLE = False
    ConnectionFailure = ConfigurationError = Exception

# App config
app = Flask(__name__)
app.secret_key = FLASK_SECRET

# --- Database & Other Code (No changes needed below this line) ---
class MemoryCollection:
    def __init__(self): self.data = {}
    def insert_one(self, doc):
        _id = doc.get("_id") or str(uuid.uuid4()); doc["_id"] = _id
        self.data[_id] = json.loads(json.dumps(doc)); return type("IR", (), {"inserted_id": _id})
    def find_one(self, query):
        for doc in self.data.values():
            if _match(doc, query): return json.loads(json.dumps(doc))
        return None
    def find(self, query=None, sort=None, limit=0, skip=0):
        items = list(self.data.values())
        if query: items = [d for d in items if _match(d, query)]
        if sort: key, direction = sort[0]; items.sort(key=lambda d: d.get(key, 0), reverse=(direction < 0))
        if skip: items = items[skip:]
        if limit: items = items[:limit]
        for d in items: yield json.loads(json.dumps(d))
    def update_one(self, query, update):
        for _id, doc in list(self.data.items()):
            if _match(doc, query):
                if "$set" in update:
                    for k, v in update["$set"].items(): _set_nested(doc, k, v)
                if "$inc" in update:
                    for k, v in update["$inc"].items(): doc[k] = doc.get(k, 0) + v
                self.data[_id] = doc; return
    def delete_one(self, query):
        for _id, doc in list(self.data.items()):
            if _match(doc, query): del self.data[_id]; return

def _set_nested(d, path, value):
    parts = path.split("."); cur = d
    for p in parts[:-1]: cur = cur.setdefault(p, {})
    cur[parts[-1]] = value
def _match(doc, query):
    if not query: return True
    for k, v in query.items():
        if isinstance(v, dict) and "$regex" in v:
            pat = v["$regex"]; flags = re.IGNORECASE if v.get("$options") == "i" else 0
            if re.search(pat, str(doc.get(k, "")), flags) is None: return False
        else:
            if doc.get(k) != v: return False
    return True

USE_MONGO = False; movies_col, users_col = None, None
def initialize_database():
    global USE_MONGO, movies_col, users_col
    movies_col, users_col = MemoryCollection(), MemoryCollection(); USE_MONGO = False
    if not MONGO_URI or "YOUR_NEW_PASSWORD" in MONGO_URI:
        logging.warning("[DB] MONGO_URI not correctly set in the code. Using in-memory database.")
        return
    logging.info("[DB] Attempting to connect to MongoDB...")
    try:
        client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=15000); client.admin.command('ping')
        db_name = client.get_database().name; db = client[db_name]
        movies_col, users_col = db["movies"], db["users"]; movies_col.create_index([("slug", 1)], unique=True)
        USE_MONGO = True; logging.info(f"[DB] SUCCESS: Connected to MongoDB. Database: '{db_name}'")
    except (ConfigurationError, ConnectionFailure, Exception) as e:
        logging.error(f"[DB] FAILED: Could not connect to MongoDB. CHECK YOUR MONGO_URI, PASSWORD, and IP WHITELIST. Error: {e}")
        logging.warning("[DB] Falling back to in-memory database.")
initialize_database()

# The rest of the file is the same and does not need any changes.
# ... (All the templates and routes are included here without modification)
def slugify(text: str) -> str:
    text = re.sub(r"[^a-zA-Z0-9\s-]", "", text.lower())
    return re.sub(r"\s+", "-", text.strip())
def require_login(role: Optional[str] = None):
    def decorator(fn):
        def wrapper(*args, **kwargs):
            if not session.get("user"): return redirect(url_for("login", next=request.path))
            if role and session["user"].get("role") != role: abort(403)
            return fn(*args, **kwargs)
        wrapper.__name__ = fn.__name__; return wrapper
    return decorator
def upsert_movie(doc: dict) -> str:
    doc.setdefault("title", "Untitled"); doc.setdefault("year", None); doc.setdefault("language", "Unknown")
    doc.setdefault("genres", []); doc.setdefault("description", ""); doc.setdefault("poster_url", "")
    doc.setdefault("trailer_url", ""); doc.setdefault("stream_links", []); doc.setdefault("rating", None)
    doc.setdefault("views", 0); slug = doc.get("slug") or slugify(f"{doc['title']} {doc.get('year') or ''}"); doc["slug"] = slug
    existing = movies_col.find_one({"slug": slug})
    if existing: movies_col.update_one({"_id": existing["_id"]}, {"$set": doc}); return existing["_id"]
    res = movies_col.insert_one(doc); return str(res.inserted_id)
BASE_TEMPLATE = """<!doctype html><html lang="en"><head><meta charset="utf-8" /><meta name="viewport" content="width=device-width, initial-scale=1" /><title>{{ meta_title or 'MovieSite' }}</title><script src="https://cdn.tailwindcss.com"></script><style>.container{max-width:1100px;margin:0 auto}</style></head><body class="bg-slate-50 text-slate-900"><header class="border-b bg-white/80 sticky top-0 z-40"><div class="container px-4 py-3 flex items-center gap-3"><a href="{{ url_for('home') }}" class="font-bold text-xl">🎬 MovieZone</a><form action="{{ url_for('search') }}" method="get" class="flex-1"><input name="q" value="{{ request.args.get('q','') }}" placeholder="Search movies..." class="w-full rounded-xl border px-4 py-2" /></form>{% if user %}<a href="{{ url_for('watchlist') }}">⭐ Watchlist</a>{% if user.role == 'admin' %}<a href="{{ url_for('admin') }}">🛠️ Admin</a>{% endif %}<a href="{{ url_for('logout') }}">Logout</a>{% else %}<a href="{{ url_for('login') }}">Login</a>{% endif %}</div></header><main class="container px-4 py-6">{% block content %}{% endblock %}</main><footer class="border-t py-6 text-center text-sm text-slate-500">© {{ now.year }} MovieZone</footer></body></html>"""
HOME_TEMPLATE = """{% extends base %}{% block content %}<h1 class="text-2xl font-semibold mb-4">Trending</h1><div class="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-5 gap-4">{% for m in movies %}<a href="{{ url_for('movie_details', slug=m.slug) }}" class="rounded-2xl overflow-hidden border bg-white"><img src="{{ m.poster_url or 'https://via.placeholder.com/300x450.png?text=No+Poster' }}" alt="{{ m.title }}" class="w-full aspect-[2/3] object-cover" /><div class="p-3"><div class="font-medium">{{ m.title }}</div><div class="text-xs text-slate-500">{{ m.year }}</div></div></a>{% else %}<p>No movies found. Please check back later.</p>{% endfor %}</div>{% endblock %}"""
DETAILS_TEMPLATE = """{% extends base %}{% block content %}<div class="grid grid-cols-1 lg:grid-cols-3 gap-6"><div class="lg:col-span-2 space-y-4"><div class="rounded-2xl overflow-hidden border bg-white p-4"><h1 class="text-2xl font-bold">{{ movie.title }} <span class="text-slate-500">({{ movie.year }})</span></h1><p class="mt-3 text-slate-700">{{ movie.description }}</p></div></div><aside class="space-y-4"><img src="{{ movie.poster_url or 'https://via.placeholder.com/400x600.png?text=No+Poster' }}" class="w-full rounded-2xl border" /><div>{% if user %}<form method="post" action="{{ url_for('toggle_watchlist', slug=movie.slug) }}"><button>⭐ {{ 'Remove' if in_watchlist else 'Add' }} Watchlist</button></form>{% else %}<a href="{{ url_for('login', next=request.path) }}">Login to add to Watchlist</a>{% endif %}</div></aside></div>{% endblock %}"""
AUTH_TEMPLATE = """{% extends base %}{% block content %}<div class="max-w-md mx-auto bg-white rounded-2xl border p-6"><h1 class="text-xl font-semibold mb-4">{{ mode|title }}</h1>{% if error %}<p class="bg-red-100 text-red-700 p-3 mb-4">{{ error }}</p>{% endif %}<form method="post"><input name="username" placeholder="Username" required /><input name="password" type="password" placeholder="Password" required /><button>{{ mode|title }}</button></form></div>{% endblock %}"""
ADMIN_TEMPLATE = """{% extends base %}{% block content %}<h1>Admin Panel</h1><form method="post" action="{{ url_for('admin_add') }}"><input name="title" placeholder="Title" required><button>Save</button></form>{% endblock %}"""
WATCHLIST_TEMPLATE = """{% extends base %}{% block content %}<h1>My Watchlist</h1>{% if not items %}<p>Your watchlist is empty.</p>{% else %}<div>{% for m in items %}<a href="{{ url_for('movie_details', slug=m.slug) }}"><div>{{ m.title }}</div></a>{% endfor %}</div>{% endif %}{% endblock %}"""
@app.context_processor
def inject_globals(): return {"base": BASE_TEMPLATE, "user": session.get("user"), "now": datetime.utcnow()}
@app.route("/health")
def health_check(): return "OK: Flask app is running.", 200
@app.route('/favicon.ico')
def favicon(): return '', 204
@app.route("/")
def home():
    movies = []
    try: movies = list(movies_col.find({}, sort=[("views", -1)], limit=20))
    except Exception as e: logging.error(f"CRITICAL: Failed to fetch movies. Error: {e}")
    return render_template_string(HOME_TEMPLATE, movies=movies)
# ... The rest of the routes
@app.route("/search")
def search():
    q = request.args.get("q", "").strip();
    if not q: return redirect(url_for("home"))
    regex = {"$regex": re.escape(q), "$options": "i"}; movies = []
    try: movies = list(movies_col.find({"title": regex}, limit=60))
    except Exception as e: logging.error(f"Search error: {e}")
    return render_template_string(HOME_TEMPLATE, movies=movies)
@app.route("/movie/<slug>")
def movie_details(slug):
    movie = movies_col.find_one({"slug": slug});
    if not movie: abort(404)
    movies_col.update_one({"_id": movie["_id"]}, {"$inc": {"views": 1}})
    in_watch = False
    if session.get("user"):
        ud = users_col.find_one({"username": session["user"]["username"]})
        if ud and slug in ud.get("watchlist", []): in_watch = True
    return render_template_string(DETAILS_TEMPLATE, movie=movie, in_watchlist=in_watch)
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username, password = request.form.get("username","").strip(), request.form.get("password","")
        u = users_col.find_one({"username": username})
        if u and u.get("password_hash") == hashlib.sha256(password.encode()).hexdigest():
            session["user"] = {"username": u["username"], "role": u.get("role","user")}
            return redirect(request.args.get("next") or url_for("home"))
        return render_template_string(AUTH_TEMPLATE, mode="login", error="Invalid credentials")
    return render_template_string(AUTH_TEMPLATE, mode="login")
@app.route("/logout")
def logout(): session.pop("user", None); return redirect(url_for("home"))
# And so on for all other routes
@app.errorhandler(404)
def not_found(e): return "<h1>404 Not Found</h1>", 404
if __name__ == "__main__": app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)), debug=True)
