# ====================================================================================
# FINAL & GUARANTEED: Single-File Professional Movie Website (Vercel-Optimized)
# Version 3.0: Refactored database connection for Vercel's serverless environment.
# This version uses a lazy-loading pattern for the database to ensure stability.
# ====================================================================================

from __future__ import annotations
import os, re, json, uuid, hashlib
from datetime import datetime

try:
    from flask import Flask, request, redirect, url_for, render_template_string, session, abort, jsonify
except Exception:
    raise SystemExit("Flask is required. Please add it to requirements.txt")

try:
    import requests
except Exception:
    requests = None
try:
    from pymongo import MongoClient, DESCENDING
    PYMONGO_AVAILABLE = True
except Exception:
    PYMONGO_AVAILABLE = False

# --- App Configuration ---
app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET", "a_strong_default_secret_key_for_safety")
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin123")
MONGO_URI = os.getenv("MONGO_URI")

# --------------------------
# Vercel-Optimized Database Layer
# --------------------------
db_connection = None # গ্লোবাল ভ্যারিয়েবল কানেকশন ক্যাশ করার জন্য

class MemoryCollection:
    # ... (এই ক্লাসের কোড অপরিবর্তিত) ...
    def __init__(self): self.data = {}
    def insert_one(self, doc):
        _id = doc.get("_id") or str(uuid.uuid4()); doc["_id"] = _id
        self.data[_id] = json.loads(json.dumps(doc)); return type("R", (), {"inserted_id": _id})
    def find_one(self, query):
        for doc in self.data.values():
            if self._match(doc, query): return json.loads(json.dumps(doc))
        return None
    def find(self, query=None, sort=None, limit=0, skip=0):
        items = [d for d in list(self.data.values()) if self._match(d, query)]
        if sort:
            key, direction = sort[0]; items.sort(key=lambda d: d.get(key,0), reverse=(direction<0))
        if skip: items=items[skip:]
        if limit: items=items[:limit]
        for d in items: yield json.loads(json.dumps(d))
    def update_one(self, query, update):
        for _id, doc in list(self.data.items()):
            if self._match(doc, query):
                if "$set" in update: doc.update(update["$set"])
                if "$inc" in update:
                    for k,v in update["$inc"].items(): doc[k]=doc.get(k,0)+v
                self.data[_id]=doc; return
    def _match(self, doc, query):
        for k, v in (query or {}).items():
            if isinstance(v, dict) and "$regex" in v:
                if re.search(v["$regex"],str(doc.get(k,"")),re.IGNORECASE) is None: return False
            elif doc.get(k) != v: return False
        return True

def get_db():
    """
    এই ফাংশনটি ডেটাবেস কানেকশন তৈরি করে এবং রিটার্ন করে।
    এটি Vercel-এর জন্য অপটিমাইজ করা। কানেকশন শুধু जरूरतের সময় তৈরি হবে।
    """
    global db_connection
    if db_connection:
        return db_connection

    if MONGO_URI and PYMONGO_AVAILABLE:
        try:
            client = MongoClient(MONGO_URI)
            db_name = MONGO_URI.split('/')[-1].split('?')[0]
            if not db_name: raise ValueError("No database name in MONGO_URI")
            db = client[db_name]
            movies = db["movies"]
            users = db["users"]
            movies.create_index([("slug", 1)], unique=True)
            print("[INFO] MongoDB connection successful.")
            db_connection = (movies, users)
            return db_connection
        except Exception as e:
            print(f"[WARN] MongoDB connection failed: {e}. Falling back to memory store.")

    # ফলব্যাক: ইন-মেমোরি ডেটাবেস
    print("[INFO] Using temporary in-memory data store.")
    movies_mem = MemoryCollection()
    users_mem = MemoryCollection()
    # অ্যাডমিন এবং ডেমো ডেটা যোগ করা হচ্ছে
    if not users_mem.find_one({"username": ADMIN_USERNAME}):
        users_mem.insert_one({"username": ADMIN_USERNAME, "password_hash": hashlib.sha256(ADMIN_PASSWORD.encode()).hexdigest(), "role": "admin"})
    if not list(movies_mem.find()):
        sample_movies = [
            {"title": "Inception", "year": 2010, "genres": ["Sci-Fi"], "description": "A thief who steals corporate secrets...", "poster_url": "https://image.tmdb.org/t/p/w500/oYuLEt3zVCKq27gApcjBJUuNXa6.jpg", "rating": 8.8, "slug": "inception-2010", "views": 0},
            {"title": "Interstellar", "year": 2014, "genres": ["Sci-Fi"], "description": "A team of explorers travel through a wormhole...", "poster_url": "https://image.tmdb.org/t/p/w500/gEU2QniE6E77NI6lCU6MxlNBvIx.jpg", "rating": 8.6, "slug": "interstellar-2014", "views": 0}
        ]
        for movie in sample_movies: movies_mem.insert_one(movie)
    db_connection = (movies_mem, users_mem)
    return db_connection

# --------------------------
# Helper Functions & Templates (No changes here)
# --------------------------
def slugify(text: str) -> str:
    text = re.sub(r"[^a-zA-Z0-9\s-]", "", text).strip().lower()
    return re.sub(r"\s+", "-", text)

def require_login(role: str | None = None):
    def decorator(fn):
        def wrapper(*args, **kwargs):
            if not session.get("user"): return redirect(url_for("login", next=request.path))
            if role and session["user"].get("role") != role: abort(403)
            return fn(*args, **kwargs)
        wrapper.__name__ = fn.__name__
        return wrapper
    return decorator

BASE_TEMPLATE = """<!doctype html><html lang="en"><head><meta charset="utf-8"/><meta name="viewport" content="width=device-width, initial-scale=1"/><title>{{ meta_title or 'MovieZone' }}</title><script src="https://cdn.tailwindcss.com"></script><style>body{font-family: 'Inter', sans-serif;}.card{transition:all .2s ease}.card:hover{transform:translateY(-4px);box-shadow:0 12px 28px rgba(0,0,0,.1)}</style></head><body class="bg-gray-100 text-gray-800"><header class="bg-white/90 backdrop-blur-lg sticky top-0 z-50 border-b"><div class="max-w-6xl mx-auto px-4 py-3 flex items-center justify-between gap-3"><a href="{{ url_for('home') }}" class="font-bold text-2xl">🎬 MovieZone</a><nav class="flex items-center gap-2">{% if user %}<a class="px-3 py-2 rounded-lg hover:bg-gray-200 text-sm" href="{{ url_for('watchlist') }}">⭐ Watchlist</a>{% if user.role == 'admin' %}<a class="px-3 py-2 rounded-lg hover:bg-gray-200 text-sm" href="{{ url_for('admin') }}">🛠️ Admin</a>{% endif %}<a class="px-3 py-2 rounded-lg hover:bg-gray-200 text-sm" href="{{ url_for('logout') }}">Logout</a>{% else %}<a class="px-3 py-2 rounded-lg bg-blue-600 text-white text-sm" href="{{ url_for('login') }}">Login</a>{% endif %}</nav></div></header><main class="max-w-6xl mx-auto px-4 py-8">{% block content %}{% endblock %}</main><footer class="border-t py-6 text-center text-sm text-gray-500">© {{ now.year }} MovieZone</footer></body></html>"""
HOME_TEMPLATE = """{% extends base %}{% block content %}<h1 class="text-3xl font-bold mb-6">{{ page_title or 'Trending Movies' }}</h1><div class="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-5">{% for m in movies %}<a href="{{ url_for('movie_details', slug=m.slug) }}" class="card rounded-xl overflow-hidden border bg-white shadow-sm"><img src="{{ m.poster_url or 'https://placehold.co/400x600?text=No+Image' }}" alt="{{ m.title }}" class="w-full aspect-[2/3] object-cover" /><div class="p-3"><h3 class="font-semibold text-md truncate">{{ m.title }}</h3><p class="text-xs text-gray-500">{{ m.year }}</p></div></a>{% endfor %}</div>{% if movies|length == 0 %}<div class="bg-white p-6 rounded-xl border">No movies found.</div>{% endif %}{% endblock %}"""
DETAILS_TEMPLATE = """{% extends base %}{% block content %}<div class="grid grid-cols-1 lg:grid-cols-3 gap-8"><div class="lg:col-span-2 bg-white rounded-xl border p-5"><h1 class="text-4xl font-extrabold">{{ movie.title }} <span class="text-gray-400 font-normal">({{ movie.year }})</span></h1><div class="mt-2 flex flex-wrap gap-2">{% for g in movie.genres %}<span class="text-xs bg-gray-200 px-2 py-1 rounded-full">{{g}}</span>{% endfor %}</div><p class="mt-4 text-gray-700 leading-relaxed">{{ movie.description }}</p></div><aside class="space-y-6"><img src="{{ movie.poster_url or 'https://placehold.co/400x600?text=No+Image' }}" class="w-full rounded-xl border shadow-md" /><div class="bg-white rounded-xl border p-4 text-sm"><p><strong>Rating:</strong> {{ movie.rating or 'N/A' }}</p><p><strong>Views:</strong> {{ movie.views or 0 }}</p>{% if user %}<form method="post" action="{{ url_for('toggle_watchlist', slug=movie.slug) }}" class="mt-4"><button class="w-full px-4 py-2 rounded-lg font-semibold {{ 'bg-yellow-400' if in_watchlist else 'bg-yellow-200' }}">⭐ {{ 'Remove from' if in_watchlist else 'Add to' }} Watchlist</button></form>{% else %}<a href="{{ url_for('login', next=request.path) }}" class="block text-center mt-4 px-4 py-2 rounded-lg bg-yellow-200 font-semibold">Login to Add</a>{% endif %}</div></aside></div>{% endblock %}"""
AUTH_TEMPLATE = """{% extends base %}{% block content %}<div class="max-w-sm mx-auto bg-white rounded-xl border p-8"><h1 class="text-2xl font-bold text-center mb-6">{{ mode|title }}</h1>{% if error %}<p class="bg-red-100 text-red-700 p-3 rounded-lg mb-4 text-sm">{{error}}</p>{% endif %}<form method="post" class="space-y-4"><input name="username" placeholder="Username" class="w-full border rounded-lg px-4 py-2" required /><input name="password" placeholder="Password" type="password" class="w-full border rounded-lg px-4 py-2" required /><button class="w-full px-4 py-3 rounded-lg bg-blue-600 text-white font-semibold">{{ mode|title }}</button></form><div class="text-center mt-4 text-sm">{% if mode == 'login' %}Don't have an account? <a href="{{ url_for('register') }}" class="text-blue-600">Register</a>{% else %}Already have an account? <a href="{{ url_for('login') }}" class="text-blue-600">Login</a>{% endif %}</div></div>{% endblock %}"""
ADMIN_TEMPLATE = """{% extends base %}{% block content %}<h1 class="text-3xl font-bold mb-6">Admin Panel</h1><div class="grid md:grid-cols-2 gap-8"><div class="bg-white border rounded-xl p-5"><h2 class="text-xl font-semibold mb-4">Add / Update Movie</h2><form method="post" action="{{ url_for('admin_add') }}" class="space-y-3"><input class="w-full border rounded-lg p-2" name="title" placeholder="Title*" required><input class="w-full border rounded-lg p-2" name="year" placeholder="Year"><input class="w-full border rounded-lg p-2" name="genres" placeholder="Genres (comma-separated)"><input class="w-full border rounded-lg p-2" name="poster_url" placeholder="Poster URL"><textarea class="w-full border rounded-lg p-2" name="description" placeholder="Description" rows="3"></textarea><button class="px-5 py-2 rounded-lg bg-blue-600 text-white font-semibold">Save Movie</button></form></div><div class="bg-white border rounded-xl p-5"><h2 class="text-xl font-semibold mb-4">Import from TMDB</h2><form method="post" action="{{ url_for('admin_tmdb') }}" class="space-y-3"><input class="w-full border rounded-lg p-2" name="tmdb_id" placeholder="TMDB ID" required><button class="px-5 py-2 rounded-lg bg-blue-600 text-white font-semibold" {% if not tmdb_enabled %}disabled{% endif %}>Import</button></form>{% if not tmdb_enabled %}<p class="text-sm text-red-600 mt-2">TMDB_API_KEY not set.</p>{% endif %}</div></div>{% endblock %}"""

# --------------------------
# Routes (All routes now use get_db())
# --------------------------
@app.context_processor
def inject_globals():
    return {"base": BASE_TEMPLATE, "user": session.get("user"), "now": datetime.utcnow()}

@app.route("/")
def home():
    movies_col, _ = get_db()
    movies = list(movies_col.find({}, sort=[("views", -1)], limit=20))
    return render_template_string(HOME_TEMPLATE, movies=movies)

@app.route("/movie/<slug>")
def movie_details(slug):
    movies_col, users_col = get_db()
    movie = movies_col.find_one({"slug": slug})
    if not movie: abort(404)
    movies_col.update_one({"_id": movie["_id"]}, {"$inc": {"views": 1}})
    user = session.get("user")
    in_watchlist = False
    if user:
        user_data = users_col.find_one({"username": user["username"]})
        if user_data and slug in user_data.get("watchlist", []): in_watchlist = True
    return render_template_string(DETAILS_TEMPLATE, movie=movie, in_watchlist=in_watchlist)

@app.route("/login", methods=["GET", "POST"])
def login():
    _, users_col = get_db()
    if request.method == "POST":
        username, password = request.form["username"].strip(), request.form["password"]
        user = users_col.find_one({"username": username})
        if user and user["password_hash"] == hashlib.sha256(password.encode()).hexdigest():
            session["user"] = {"username": user["username"], "role": user.get("role", "user")}
            return redirect(request.args.get("next") or url_for("home"))
        return render_template_string(AUTH_TEMPLATE, mode="login", error="Invalid credentials.")
    return render_template_string(AUTH_TEMPLATE, mode="login")

@app.route("/register", methods=["GET", "POST"])
def register():
    _, users_col = get_db()
    if request.method == "POST":
        username, password = request.form["username"].strip(), request.form["password"]
        if users_col.find_one({"username": username}):
            return render_template_string(AUTH_TEMPLATE, mode="register", error="Username exists.")
        users_col.insert_one({"username": username, "password_hash": hashlib.sha256(password.encode()).hexdigest(), "role": "user", "watchlist": []})
        session["user"] = {"username": username, "role": "user"}
        return redirect(url_for("home"))
    return render_template_string(AUTH_TEMPLATE, mode="register")

@app.route("/logout")
def logout():
    session.pop("user", None); return redirect(url_for("home"))

@app.route("/watchlist")
@require_login()
def watchlist():
    movies_col, users_col = get_db()
    user_data = users_col.find_one({"username": session["user"]["username"]})
    slugs = user_data.get("watchlist", [])
    movies = [m for s in slugs if (m := movies_col.find_one({"slug": s}))]
    return render_template_string(HOME_TEMPLATE, movies=movies, page_title="My Watchlist")

@app.route("/watchlist/toggle/<slug>", methods=["POST"])
@require_login()
def toggle_watchlist(slug):
    _, users_col = get_db()
    user_data = users_col.find_one({"username": session["user"]["username"]})
    watchlist = set(user_data.get("watchlist", []))
    if slug in watchlist: watchlist.remove(slug)
    else: watchlist.add(slug)
    users_col.update_one({"_id": user_data["_id"]}, {"$set": {"watchlist": list(watchlist)}})
    return redirect(url_for("movie_details", slug=slug))

@app.route("/admin")
@require_login("admin")
def admin():
    return render_template_string(ADMIN_TEMPLATE, tmdb_enabled=bool(requests and os.getenv("TMDB_API_KEY")))

@app.route("/admin/add", methods=["POST"])
@require_login("admin")
def admin_add():
    movies_col, _ = get_db()
    form = request.form
    doc = {
        "title": form.get("title").strip(),
        "year": int(form.get("year")) if form.get("year").isdigit() else None,
        "genres": [g.strip() for g in form.get("genres", "").split(",") if g.strip()],
        "poster_url": form.get("poster_url"), "description": form.get("description")
    }
    slug = slugify(f"{doc['title']} {doc.get('year') or ''}")
    existing = movies_col.find_one({"slug": slug})
    if existing: movies_col.update_one({"slug": slug}, {"$set": doc})
    else: doc["slug"] = slug; doc["views"] = 0; movies_col.insert_one(doc)
    return redirect(url_for("admin"))

@app.route("/admin/tmdb", methods=["POST"])
@require_login("admin")
def admin_tmdb():
    movies_col, _ = get_db()
    api_key, tmdb_id = os.getenv("TMDB_API_KEY"), request.form.get("tmdb_id")
    if not (api_key and requests and tmdb_id): abort(400)
    try:
        res = requests.get(f"https://api.themoviedb.org/3/movie/{tmdb_id}?api_key={api_key}").json()
        year = (res.get("release_date") or "")[:4]
        doc = {
            "title": res.get("title"), "year": int(year) if year.isdigit() else None,
            "genres": [g["name"] for g in res.get("genres", [])],
            "poster_url": f"https://image.tmdb.org/t/p/w500{res.get('poster_path')}" if res.get('poster_path') else "",
            "description": res.get("overview"), "rating": res.get("vote_average")
        }
        slug = slugify(f"{doc['title']} {doc.get('year') or ''}")
        doc["slug"] = slug
        if movies_col.find_one({"slug": slug}): movies_col.update_one({"slug": slug}, {"$set": doc})
        else: doc["views"] = 0; movies_col.insert_one(doc)
    except Exception as e: print(f"TMDB Import Error: {e}")
    return redirect(url_for("admin"))
