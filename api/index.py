# index.py
"""
Single-file Professional Movie Website (Flask) - Final Vercel-Ready Version
- One file: index.py
- Supports: MongoDB (optional) or in-memory fallback with robust error handling.
- Features: Home, Search, Movie Details, Player links, Auth, Watchlist, Admin (add + TMDB import)
- Exported `app` for Vercel import; also runnable locally.
ENV:
  FLASK_SECRET, MONGO_URI, TMDB_API_KEY, ADMIN_USERNAME, ADMIN_PASSWORD, BASE_URL
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

# Basic logging configuration to see output in Vercel logs
logging.basicConfig(level=logging.INFO, format='[%(levelname)s] %(message)s')

# Flask
try:
    from flask import Flask, request, redirect, url_for, render_template_string, session, abort
except Exception:
    raise SystemExit("Flask is required. Install with: pip install Flask")

# Optional dependencies
try:
    import requests
except Exception:
    requests = None
try:
    from pymongo import MongoClient
    from pymongo.errors import ConnectionFailure, ConfigurationError
    PYMONGO_AVAILABLE = True
except Exception:
    PYMONGO_AVAILABLE = False
    # Define dummy exceptions if pymongo is not installed
    ConnectionFailure = ConfigurationError = Exception

# App config
app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET", "dev_secret_please_change")
BASE_URL = os.getenv("BASE_URL", "")
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin123")

# --------------------------
# In-memory Collection (fallback)
# --------------------------
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
        if sort:
            key, direction = sort[0]; items.sort(key=lambda d: d.get(key, 0), reverse=(direction < 0))
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

# --------------------------
# Database initialization (Final Robust Version)
# --------------------------
MONGO_URI = os.getenv("MONGO_URI", "").strip()
USE_MONGO = False
movies_col, users_col = None, None

def initialize_database():
    global USE_MONGO, movies_col, users_col
    movies_col, users_col = MemoryCollection(), MemoryCollection()
    USE_MONGO = False

    if not MONGO_URI:
        logging.info("[DB] MONGO_URI not set. Using in-memory database.")
        return
    if not PYMONGO_AVAILABLE:
        logging.warning("[DB] MONGO_URI is set, but pymongo is not installed. Using in-memory database.")
        return

    logging.info("[DB] MONGO_URI found. Attempting to connect to MongoDB...")
    try:
        client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=15000)
        client.admin.command('ping')
        db_name = client.get_database().name
        db = client[db_name]
        movies_col, users_col = db["movies"], db["users"]
        movies_col.create_index([("slug", 1)], unique=True)
        USE_MONGO = True
        logging.info(f"[DB] SUCCESS: Connected to MongoDB. Database: '{db_name}'")
    except ConfigurationError as e:
        logging.error(f"[DB] FAILED: MongoDB configuration error. Is your MONGO_URI format correct? Error: {e}")
    except ConnectionFailure as e:
        logging.error(f"[DB] FAILED: MongoDB connection failed. Check your IP Whitelist in Atlas (set to 0.0.0.0/0) and network. Error: {e}")
    except Exception as e:
        logging.error(f"[DB] FAILED: An unexpected error occurred. Error: {e}")
    
    if not USE_MONGO:
        logging.warning("[DB] Falling back to in-memory database.")

initialize_database()

# --------------------------
# Seed admin user
# --------------------------
try:
    if users_col and not users_col.find_one({"username": ADMIN_USERNAME}):
        users_col.insert_one({
            "username": ADMIN_USERNAME,
            "password_hash": hashlib.sha256(ADMIN_PASSWORD.encode()).hexdigest(),
            "role": "admin",
            "created_at": datetime.utcnow().isoformat()
        })
except Exception as e:
    logging.warning(f"Could not seed admin user. Error: {e}")


# --------------------------
# Utilities & Templates
# --------------------------
def slugify(text: str) -> str:
    text = re.sub(r"[^a-zA-Z0-9\s-]", "", text.lower())
    return re.sub(r"\s+", "-", text.strip())

def require_login(role: Optional[str] = None):
    def decorator(fn):
        def wrapper(*args, **kwargs):
            if not session.get("user"): return redirect(url_for("login", next=request.path))
            if role and session["user"].get("role") != role: abort(403)
            return fn(*args, **kwargs)
        wrapper.__name__ = fn.__name__
        return wrapper
    return decorator

# ... (upsert_movie and all templates remain exactly the same as your original)
def upsert_movie(doc: dict) -> str:
    doc.setdefault("title", "Untitled")
    doc.setdefault("year", None)
    doc.setdefault("language", "Unknown")
    doc.setdefault("genres", [])
    doc.setdefault("description", "")
    doc.setdefault("poster_url", "")
    doc.setdefault("trailer_url", "")
    doc.setdefault("stream_links", [])
    doc.setdefault("rating", None)
    doc.setdefault("views", 0)
    slug = doc.get("slug") or slugify(f"{doc['title']} {doc.get('year') or ''}")
    doc["slug"] = slug

    existing = movies_col.find_one({"slug": slug})
    if existing:
        movies_col.update_one({"_id": existing["_id"]}, {"$set": doc})
        return existing["_id"]
    res = movies_col.insert_one(doc)
    return str(res.inserted_id)

BASE_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" /><meta name="viewport" content="width=device-width, initial-scale=1" /><title>{{ meta_title or 'MovieSite' }}</title>{% if base_url %}<link rel="canonical" href="{{ base_url + request.path }}" />{% endif %}<meta name="description" content="{{ meta_desc or 'Watch movies online' }}" /><script src="https://cdn.tailwindcss.com"></script><link href="https://vjs.zencdn.net/8.10.0/video-js.css" rel="stylesheet" /><script src="https://vjs.zencdn.net/8.10.0/video.min.js"></script><style>.container{max-width:1100px;margin:0 auto} .card{transition:transform .15s ease} .card:hover{transform:translateY(-2px)}</style>
</head>
<body class="bg-slate-50 text-slate-900">
  <header class="border-b bg-white/80 sticky top-0 z-40"><div class="container px-4 py-3 flex items-center gap-3"><a href="{{ url_for('home') }}" class="font-bold text-xl">🎬 MovieZone</a><form action="{{ url_for('search') }}" method="get" class="flex-1"><input name="q" value="{{ request.args.get('q','') }}" placeholder="Search movies..." class="w-full rounded-xl border px-4 py-2" /></form>{% if user %}<a class="px-3 py-2 rounded-xl" href="{{ url_for('watchlist') }}">⭐ Watchlist</a>{% if user.role == 'admin' %}<a class="px-3 py-2 rounded-xl" href="{{ url_for('admin') }}">🛠️ Admin</a>{% endif %}<a class="px-3 py-2 rounded-xl" href="{{ url_for('logout') }}">Logout</a>{% else %}<a class="px-3 py-2 rounded-xl" href="{{ url_for('login') }}">Login</a>{% endif %}</div></header>
  <main class="container px-4 py-6">{% block content %}{% endblock %}</main>
  <footer class="border-t py-6 text-center text-sm text-slate-500">© {{ now.year }} MovieZone</footer>
</body>
</html>"""
HOME_TEMPLATE = """{% extends base %}{% block content %}<h1 class="text-2xl font-semibold mb-4">Trending</h1><div class="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-5 gap-4">{% for m in movies %}<a href="{{ url_for('movie_details', slug=m.slug) }}" class="card rounded-2xl overflow-hidden border bg-white"><img src="{{ m.poster_url or 'https://picsum.photos/300/450?blur=2' }}" alt="{{ m.title }}" class="w-full aspect-[2/3] object-cover" /><div class="p-3"><div class="font-medium">{{ m.title }}</div><div class="text-xs text-slate-500">{{ m.year }} • {{ (m.genres or [])|join(', ') }}</div></div></a>{% else %} <p>No movies found. The site may be under maintenance.</p> {% endfor %}</div>{% endblock %}"""
DETAILS_TEMPLATE = """{% extends base %}{% block content %}<div class="grid grid-cols-1 lg:grid-cols-3 gap-6"><div class="lg:col-span-2 space-y-4">{% if movie.trailer_url %}<div class="rounded-2xl overflow-hidden border bg-black"><iframe class="w-full aspect-video" src="{{ movie.trailer_url|replace('watch?v=','embed/') }}" allowfullscreen></iframe></div>{% endif %}{% if movie.stream_links %}<div class="rounded-2xl overflow-hidden border bg-black p-4"><video id="player" class="video-js vjs-default-skin w-full aspect-video" controls preload="auto" poster="{{ movie.poster_url }}"></video><div class="mt-3 flex flex-wrap gap-2">{% for s in movie.stream_links %}<a href="{{ url_for('play', slug=movie.slug, idx=loop.index0) }}" class="px-3 py-1 rounded-xl border bg-white">Play: {{ s.label }}</a>{% endfor %}</div></div>{% endif %}<div class="rounded-2xl overflow-hidden border bg-white p-4"><h1 class="text-2xl font-bold">{{ movie.title }} <span class="text-slate-500">({{ movie.year }})</span></h1><div class="text-sm text-slate-500">{{ movie.language }} • {{ (movie.genres or [])|join(', ') }}</div><p class="mt-3 text-slate-700">{{ movie.description }}</p></div></div><aside class="space-y-4"><img src="{{ movie.poster_url or 'https://picsum.photos/400/600?blur=2' }}" class="w-full rounded-2xl border" /><div class="rounded-2xl overflow-hidden border bg-white p-4 text-sm"><div>Rating: {{ movie.rating or 'N/A' }}</div><div>Views: {{ movie.views or 0 }}</div>{% if user %}<form method="post" action="{{ url_for('toggle_watchlist', slug=movie.slug) }}" class="mt-3"><button class="px-4 py-2 rounded-xl border bg-amber-50">⭐ {{ 'Remove' if in_watchlist else 'Add' }} Watchlist</button></form>{% else %}<a href="{{ url_for('login', next=request.path) }}" class="inline-block mt-3 px-4 py-2 rounded-xl border">Login to add to Watchlist</a>{% endif %}</div></aside></div>{% endblock %}"""
AUTH_TEMPLATE = """{% extends base %}{% block content %}<div class="max-w-md mx-auto bg-white rounded-2xl border p-6"><h1 class="text-xl font-semibold mb-4">{{ mode|title }}</h1>{% if error %}<p class="bg-red-100 text-red-700 p-3 rounded-lg mb-4 text-sm">{{ error }}</p>{% endif %}<form method="post" class="space-y-3"><input name="username" placeholder="Username" class="w-full border rounded-xl px-3 py-2" required /><input name="password" placeholder="Password" type="password" class="w-full border rounded-xl px-3 py-2" required /><button class="w-full px-4 py-2 rounded-xl bg-black text-white">{{ mode|title }}</button></form></div>{% endblock %}"""
ADMIN_TEMPLATE = """{% extends base %}{% block content %}<h1 class="text-2xl font-semibold mb-4">Admin Panel</h1><div class="grid md:grid-cols-2 gap-6"><div class="bg-white border rounded-2xl p-4"><h2 class="font-semibold mb-3">Add / Update Movie</h2><form method="post" action="{{ url_for('admin_add') }}" class="space-y-2"><input class="w-full border rounded-xl px-3 py-2" name="title" placeholder="Title" required><input class="w-full border rounded-xl px-3 py-2" name="year" placeholder="Year"><input class="w-full border rounded-xl px-3 py-2" name="language" placeholder="Language"><input class="w-full border rounded-xl px-3 py-2" name="genres" placeholder="Genres (comma-separated)"><input class="w-full border rounded-xl px-3 py-2" name="poster_url" placeholder="Poster URL"><input class="w-full border rounded-xl px-3 py-2" name="trailer_url" placeholder="Trailer URL (YouTube)"><textarea class="w-full border rounded-xl px-3 py-2" name="description" placeholder="Description"></textarea><textarea class="w-full border rounded-xl px-3 py-2" name="stream_links" placeholder='Stream links JSON (e.g., [{"label":"1080p","url":"...m3u8"}])'></textarea><button class="px-4 py-2 rounded-xl bg-black text-white">Save</button></form></div><div class="bg-white border rounded-2xl p-4"><h2 class="font-semibold mb-3">Import from TMDB</h2><form method="post" action="{{ url_for('admin_tmdb') }}" class="space-y-2"><input class="w-full border rounded-xl px-3 py-2" name="tmdb_id" placeholder="TMDB Movie ID" required><button class="px-4 py-2 rounded-xl bg-black text-white">Import</button></form><p class="text-sm text-slate-500 mt-2">Requires TMDB_API_KEY</p></div></div>{% endblock %}"""
WATCHLIST_TEMPLATE = """{% extends base %}{% block content %}<h1 class="text-xl font-semibold mb-4">My Watchlist</h1>{% if items|length == 0 %}<div class="p-6 bg-white rounded-2xl border">Your watchlist is empty.</div>{% else %}<div class="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-5 gap-4">{% for m in items %}<a href="{{ url_for('movie_details', slug=m.slug) }}" class="card rounded-2xl overflow-hidden border bg-white"><img src="{{ m.poster_url or 'https://picsum.photos/300/450?blur=2' }}" class="w-full aspect-[2/3] object-cover"/><div class="p-3"><div class="font-medium">{{ m.title }}</div><div class="text-xs text-slate-500">{{ m.year }} • {{ (m.genres or [])|join(', ') }}</div></div></a>{% endfor %}</div>{% endif %}{% endblock %}"""

# --------------------------
# Routes
# --------------------------
@app.context_processor
def inject_globals():
    return {"base": BASE_TEMPLATE, "user": session.get("user"), "now": datetime.utcnow(), "base_url": BASE_URL}

@app.route("/health")
def health_check():
    return "OK: Flask app is running.", 200

@app.route('/favicon.ico')
def favicon():
    return '', 204

@app.route("/")
def home():
    movies = []
    try:
        movies = list(movies_col.find({}, sort=[("views", -1)], limit=20))
    except Exception as e:
        logging.error(f"CRITICAL: Failed to fetch movies from database for home page. Error: {e}")
    return render_template_string(HOME_TEMPLATE, movies=movies, meta_title="Home • MovieZone")

@app.route("/search")
def search():
    q = request.args.get("q", "").strip()
    if not q: return redirect(url_for("home"))
    regex = {"$regex": re.escape(q), "$options": "i"}
    movies = []
    try:
        movies = list(movies_col.find({"title": regex}, sort=[("views", -1)], limit=60))
    except Exception as e:
        logging.error(f"Error during search: {e}")
    return render_template_string(HOME_TEMPLATE, movies=movies, meta_title=f"Search: {q}")

# ... (All other routes: movie_details, play, login, register, etc. can remain the same)
@app.route("/movie/<slug>")
def movie_details(slug):
    movie = movies_col.find_one({"slug": slug})
    if not movie: abort(404)
    movies_col.update_one({"_id": movie["_id"]}, {"$inc": {"views": 1}})
    in_watch = False
    if session.get("user"):
        ud = users_col.find_one({"username": session["user"]["username"]})
        if ud and slug in ud.get("watchlist", []): in_watch = True
    return render_template_string(DETAILS_TEMPLATE, movie=movie, in_watchlist=in_watch, meta_title=f"{movie['title']} • MovieZone", meta_desc=(movie.get("description") or "")[:150])

@app.route("/play/<slug>/<int:idx>")
def play(slug, idx):
    movie = movies_col.find_one({"slug": slug}); links = (movie or {}).get("stream_links") or []
    if not (movie and 0 <= idx < len(links)): abort(404)
    return redirect(links[idx]["url"])

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

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username, password = request.form.get("username","").strip(), request.form.get("password","")
        if not (4 <= len(username) <= 20 and re.match(r"^[a-zA-Z0-9_]+$", username)):
            return render_template_string(AUTH_TEMPLATE, mode="register", error="Username must be 4-20 chars and alphanumeric.")
        if len(password) < 6:
            return render_template_string(AUTH_TEMPLATE, mode="register", error="Password must be at least 6 characters.")
        if users_col.find_one({"username": username}):
            return render_template_string(AUTH_TEMPLATE, mode="register", error="Username already exists.")
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
    u = users_col.find_one({"username": session["user"]["username"]}); slugs = (u or {}).get("watchlist", [])
    movies = [m for s in slugs if (m := movies_col.find_one({"slug": s}))]
    return render_template_string(WATCHLIST_TEMPLATE, items=movies, meta_title="My Watchlist")

@app.route("/watchlist/toggle/<slug>", methods=["POST"])
@require_login()
def toggle_watchlist(slug):
    u = users_col.find_one({"username": session["user"]["username"]}); wl = set(u.get("watchlist", []))
    if slug in wl: wl.remove(slug)
    else: wl.add(slug)
    users_col.update_one({"_id": u["_id"]}, {"$set": {"watchlist": list(wl)}})
    return redirect(url_for("movie_details", slug=slug))

@app.route("/admin")
@require_login("admin")
def admin():
    items = list(movies_col.find({}, sort=[("_id", -1)], limit=24))
    return render_template_string(ADMIN_TEMPLATE, movies=items)

@app.route("/admin/add", methods=["POST"])
@require_login("admin")
def admin_add():
    form = request.form; stream_links_str = form.get("stream_links", "").strip()
    try: stream_links = json.loads(stream_links_str) if stream_links_str else []
    except: stream_links = []
    doc = {
        "title": form.get("title", "Untitled").strip(), "year": int(y) if (y:=form.get("year")) and y.isdigit() else None,
        "language": form.get("language","").strip() or None, "genres": [g.strip() for g in form.get("genres","").split(",") if g.strip()],
        "poster_url": form.get("poster_url","").strip(), "trailer_url": form.get("trailer_url","").strip(),
        "description": form.get("description","").strip(), "stream_links": stream_links,
    }
    upsert_movie(doc); return redirect(url_for("admin"))

@app.route("/admin/tmdb", methods=["POST"])
@require_login("admin")
def admin_tmdb():
    api_key, tmdb_id = os.getenv("TMDB_API_KEY"), request.form.get("tmdb_id")
    if not (requests and api_key and tmdb_id): return redirect(url_for("admin"))
    try:
        mv = requests.get(f"https://api.themoviedb.org/3/movie/{tmdb_id}", params={"api_key": api_key}, timeout=10).json()
        upsert_movie({
            "title": mv.get("title"), "year": int(y) if (y:=(mv.get("release_date") or "")[:4]).isdigit() else None,
            "language": (mv.get("original_language") or "").upper(), "genres": [g["name"] for g in mv.get("genres", [])],
            "poster_url": f"https://image.tmdb.org/t/p/w500{p}" if (p:=mv.get("poster_path")) else "",
            "description": mv.get("overview"), "rating": mv.get("vote_average"),
        })
    except Exception as e: logging.error(f"TMDB import failed: {e}")
    return redirect(url_for("admin"))

@app.errorhandler(404)
def not_found(e): return render_template_string("""{% extends base %}{% block content %}<div class='bg-white border rounded-2xl p-8 text-center'><div class='text-6xl'>🧐</div><h1 class='text-2xl font-semibold mt-3'>Page not found</h1><a href='{{ url_for('home') }}' class='inline-block mt-4 px-4 py-2 rounded-xl border'>Go Home</a></div>{% endblock %}"""), 404
@app.errorhandler(403)
def forbidden(e): return "<h1>403 - Forbidden</h1>", 403

# --------------------------
# Seed sample data if in-memory
# --------------------------
if not USE_MONGO:
    if not any(movies_col.find(limit=1)):
        logging.info("In-memory DB is empty. Seeding sample data.")
        for m in [
            {"title": "Inception", "year": 2010, "genres": ["Sci-Fi","Thriller"], "poster_url": "https://image.tmdb.org/t/p/w500/qmDpIHrmpJINaRKAfWQfftjCdyi.jpg", "stream_links":[{"label":"720p","url":"https://test-streams.mux.dev/x36xhzz/x36xhzz.m3u8"}]},
            {"title": "Interstellar", "year": 2014, "genres": ["Sci-Fi","Adventure"], "poster_url": "https://image.tmdb.org/t/p/w500/rAiYTfKGqDCRIIqo664sY9XZIvQ.jpg"},
        ]: upsert_movie(m)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)), debug=True)
