# index.py
"""
Single-file Professional Movie Website (Flask) - Vercel Optimized
- One file: index.py
- Supports: MongoDB (optional) or in-memory fallback
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

# Flask
try:
    from flask import Flask, request, redirect, url_for, render_template_string, session, abort
except Exception:
    raise SystemExit("Flask is required. Install with: pip install Flask")

# optional requests
try:
    import requests
except Exception:
    requests = None

# optional pymongo
try:
    from pymongo import MongoClient
    from pymongo.errors import ConnectionFailure
    PYMONGO_AVAILABLE = True
except Exception:
    PYMONGO_AVAILABLE = False
    ConnectionFailure = None

# Setup basic logging
logging.basicConfig(level=logging.INFO)

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
    def __init__(self):
        self.data = {}

    def insert_one(self, doc):
        _id = doc.get("_id") or str(uuid.uuid4())
        doc["_id"] = _id
        self.data[_id] = json.loads(json.dumps(doc))
        return type("IR", (), {"inserted_id": _id})

    def find_one(self, query):
        for doc in self.data.values():
            if _match(doc, query):
                return json.loads(json.dumps(doc))
        return None

    def find(self, query=None, sort=None, limit=0, skip=0):
        items = list(self.data.values())
        if query:
            items = [d for d in items if _match(d, query)]
        if sort:
            key, direction = sort[0]
            items.sort(key=lambda d: d.get(key, 0), reverse=(direction < 0))
        if skip:
            items = items[skip:]
        if limit:
            items = items[:limit]
        for d in items:
            yield json.loads(json.dumps(d))

    def update_one(self, query, update):
        for _id, doc in list(self.data.items()):
            if _match(doc, query):
                if "$set" in update:
                    for k, v in update["$set"].items():
                        _set_nested(doc, k, v)
                if "$inc" in update:
                    for k, v in update["$inc"].items():
                        doc[k] = doc.get(k, 0) + v
                self.data[_id] = doc
                return

    def delete_one(self, query):
        for _id, doc in list(self.data.items()):
            if _match(doc, query):
                del self.data[_id]
                return

def _set_nested(d, path, value):
    parts = path.split(".")
    cur = d
    for p in parts[:-1]:
        cur = cur.setdefault(p, {})
    cur[parts[-1]] = value

def _match(doc, query):
    if not query:
        return True
    for k, v in query.items():
        if isinstance(v, dict) and "$regex" in v:
            pat = v["$regex"]
            flags = re.IGNORECASE if v.get("$options") == "i" else 0
            if re.search(pat, str(doc.get(k, "")), flags) is None:
                return False
        else:
            if doc.get(k) != v:
                return False
    return True

# --------------------------
# Database initialization (robust)
# --------------------------
MONGO_URI = os.getenv("MONGO_URI", "").strip()
USE_MONGO = False
movies_col = None
users_col = None

def initialize_database():
    global USE_MONGO, movies_col, users_col
    movies_col = MemoryCollection()
    users_col = MemoryCollection()
    USE_MONGO = False

    if MONGO_URI and PYMONGO_AVAILABLE:
        logging.info("[DB] MONGO_URI is set. Attempting to connect...")
        try:
            # Increased timeout for Vercel cold starts
            client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=10000)
            client.admin.command('ping') # Recommended way to check connection
            db_name = client.get_database().name
            
            db = client[db_name]
            movies = db["movies"]
            users = db["users"]
            try:
                movies.create_index([("slug", 1)], unique=True)
                movies.create_index([("views", -1)])
            except Exception as idx_e:
                logging.warning(f"[DB] Could not create indexes: {idx_e}")
            
            movies_col = movies
            users_col = users
            USE_MONGO = True
            logging.info(f"[DB] Successfully connected to MongoDB. DB: {db_name}")
        except ConnectionFailure as e:
            logging.error(f"[DB] MongoDB connection failed: Server not available. Error: {e}")
            logging.warning("[DB] Falling back to in-memory database.")
        except Exception as e:
            logging.error(f"[DB] An unexpected error occurred during MongoDB connection. Error: {e}")
            logging.warning("[DB] Falling back to in-memory database.")
    elif not MONGO_URI:
        logging.info("[DB] MONGO_URI not set. Using in-memory database.")
    else: # MONGO_URI is set but PYMONGO is not available
        logging.info("[DB] pymongo library not available. Using in-memory database.")

initialize_database()

# --------------------------
# Seed admin user if missing
# --------------------------
def seed_admin():
    try:
        if not users_col.find_one({"username": ADMIN_USERNAME}):
            users_col.insert_one({
                "username": ADMIN_USERNAME,
                "password_hash": hashlib.sha256(ADMIN_PASSWORD.encode()).hexdigest(),
                "role": "admin",
                "created_at": datetime.utcnow().isoformat()
            })
            logging.info(f"Admin user '{ADMIN_USERNAME}' created/verified.")
    except Exception as e:
        logging.warning(f"Could not seed admin user. Error: {e}")

seed_admin()

# --------------------------
# Utilities
# --------------------------
def slugify(text: str) -> str:
    text = re.sub(r"[^a-zA-Z0-9\s-]", "", text)
    text = re.sub(r"\s+", "-", text.strip())
    return text.lower()

def require_login(role: Optional[str] = None):
    def decorator(fn):
        def wrapper(*args, **kwargs):
            u = session.get("user")
            if not u:
                return redirect(url_for("login", next=request.path))
            if role and u.get("role") != role:
                abort(403)
            return fn(*args, **kwargs)
        wrapper.__name__ = fn.__name__
        return wrapper
    return decorator

def upsert_movie(doc: dict) -> str:
    doc.setdefault("title", "Untitled")
    # ... (rest of the function is fine, no changes needed)
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

# --------------------------
# Templates (kept inline for single-file)
# --------------------------
BASE_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{{ meta_title or 'MovieSite' }}</title>
  {% if base_url %}<link rel="canonical" href="{{ base_url + request.path }}" />{% endif %}
  <meta name="description" content="{{ meta_desc or 'Watch movies online' }}" />
  <script src="https://cdn.tailwindcss.com"></script>
  <link href="https://vjs.zencdn.net/8.10.0/video-js.css" rel="stylesheet" />
  <script src="https://vjs.zencdn.net/8.10.0/video.min.js"></script>
  <style>.container{max-width:1100px;margin:0 auto} .card{transition:transform .15s ease} .card:hover{transform:translateY(-2px)}</style>
</head>
<body class="bg-slate-50 text-slate-900">
  <header class="border-b bg-white/80 sticky top-0 z-40">
    <div class="container px-4 py-3 flex items-center gap-3">
      <a href="{{ url_for('home') }}" class="font-bold text-xl">🎬 MovieZone</a>
      <form action="{{ url_for('search') }}" method="get" class="flex-1">
        <input name="q" value="{{ request.args.get('q','') }}" placeholder="Search movies..." class="w-full rounded-xl border px-4 py-2" />
      </form>
      {% if user %}
        <a class="px-3 py-2 rounded-xl" href="{{ url_for('watchlist') }}">⭐ Watchlist</a>
        {% if user.role == 'admin' %}<a class="px-3 py-2 rounded-xl" href="{{ url_for('admin') }}">🛠️ Admin</a>{% endif %}
        <a class="px-3 py-2 rounded-xl" href="{{ url_for('logout') }}">Logout</a>
      {% else %}
        <a class="px-3 py-2 rounded-xl" href="{{ url_for('login') }}">Login</a>
      {% endif %}
    </div>
  </header>
  <main class="container px-4 py-6">
    {% block content %}{% endblock %}
  </main>
  <footer class="border-t py-6 text-center text-sm text-slate-500">© {{ now.year }} MovieZone</footer>
</body>
</html>"""

# ... (All other templates remain unchanged) ...
HOME_TEMPLATE = """{% extends base %}
{% block content %}
  <h1 class="text-2xl font-semibold mb-4">Trending</h1>
  <div class="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-5 gap-4">
    {% for m in movies %}
    <a href="{{ url_for('movie_details', slug=m.slug) }}" class="card rounded-2xl overflow-hidden border bg-white">
      <img src="{{ m.poster_url or 'https://picsum.photos/300/450?blur=2' }}" alt="{{ m.title }}" class="w-full aspect-[2/3] object-cover" />
      <div class="p-3">
        <div class="font-medium">{{ m.title }}</div>
        <div class="text-xs text-slate-500">{{ m.year }} • {{ (m.genres or [])|join(', ') }}</div>
      </div>
    </a>
    {% endfor %}
  </div>
{% endblock %}"""

DETAILS_TEMPLATE = """{% extends base %}
{% block content %}
  <div class="grid grid-cols-1 lg:grid-cols-3 gap-6">
    <div class="lg:col-span-2 space-y-4">
      {% if movie.trailer_url %}
      <div class="rounded-2xl overflow-hidden border bg-black">
        <iframe class="w-full aspect-video" src="{{ movie.trailer_url|replace('watch?v=','embed/') }}" allowfullscreen></iframe>
      </div>
      {% endif %}
      {% if movie.stream_links %}
      <div class="rounded-2xl overflow-hidden border bg-black p-4">
        <video id="player" class="video-js vjs-default-skin w-full aspect-video" controls preload="auto" poster="{{ movie.poster_url }}"></video>
        <div class="mt-3 flex flex-wrap gap-2">
          {% for s in movie.stream_links %}
            <a href="{{ url_for('play', slug=movie.slug, idx=loop.index0) }}" class="px-3 py-1 rounded-xl border bg-white">Play: {{ s.label }}</a>
          {% endfor %}
        </div>
      </div>
      {% endif %}
      <div class="rounded-2xl overflow-hidden border bg-white p-4">
        <h1 class="text-2xl font-bold">{{ movie.title }} <span class="text-slate-500">({{ movie.year }})</span></h1>
        <div class="text-sm text-slate-500">{{ movie.language }} • {{ (movie.genres or [])|join(', ') }}</div>
        <p class="mt-3 text-slate-700">{{ movie.description }}</p>
      </div>
    </div>
    <aside class="space-y-4">
      <img src="{{ movie.poster_url or 'https://picsum.photos/400/600?blur=2' }}" class="w-full rounded-2xl border" />
      <div class="rounded-2xl overflow-hidden border bg-white p-4 text-sm">
        <div>Rating: {{ movie.rating or 'N/A' }}</div>
        <div>Views: {{ movie.views or 0 }}</div>
        {% if user %}
          <form method="post" action="{{ url_for('toggle_watchlist', slug=movie.slug) }}" class="mt-3">
            <button class="px-4 py-2 rounded-xl border bg-amber-50">⭐ {{ 'Remove' if in_watchlist else 'Add' }} Watchlist</button>
          </form>
        {% else %}
          <a href="{{ url_for('login', next=request.path) }}" class="inline-block mt-3 px-4 py-2 rounded-xl border">Login to add to Watchlist</a>
        {% endif %}
      </div>
    </aside>
  </div>
{% endblock %}"""

AUTH_TEMPLATE = """{% extends base %}
{% block content %}
  <div class="max-w-md mx-auto bg-white rounded-2xl border p-6">
    <h1 class="text-xl font-semibold mb-4">{{ mode|title }}</h1>
    {% if error %}<p class="bg-red-100 text-red-700 p-3 rounded-lg mb-4 text-sm">{{ error }}</p>{% endif %}
    <form method="post" class="space-y-3">
      <input name="username" placeholder="Username" class="w-full border rounded-xl px-3 py-2" required />
      <input name="password" placeholder="Password" type="password" class="w-full border rounded-xl px-3 py-2" required />
      <button class="w-full px-4 py-2 rounded-xl bg-black text-white">{{ mode|title }}</button>
    </form>
  </div>
{% endblock %}"""

ADMIN_TEMPLATE = """{% extends base %}
{% block content %}
  <h1 class="text-2xl font-semibold mb-4">Admin Panel</h1>
  <div class="grid md:grid-cols-2 gap-6">
    <div class="bg-white border rounded-2xl p-4">
      <h2 class="font-semibold mb-3">Add / Update Movie</h2>
      <form method="post" action="{{ url_for('admin_add') }}" class="space-y-2">
        <input class="w-full border rounded-xl px-3 py-2" name="title" placeholder="Title" required>
        <input class="w-full border rounded-xl px-3 py-2" name="year" placeholder="Year">
        <input class="w-full border rounded-xl px-3 py-2" name="language" placeholder="Language">
        <input class="w-full border rounded-xl px-3 py-2" name="genres" placeholder="Genres (comma-separated)">
        <input class="w-full border rounded-xl px-3 py-2" name="poster_url" placeholder="Poster URL">
        <input class="w-full border rounded-xl px-3 py-2" name="trailer_url" placeholder="Trailer URL (YouTube)">
        <textarea class="w-full border rounded-xl px-3 py-2" name="description" placeholder="Description"></textarea>
        <textarea class="w-full border rounded-xl px-3 py-2" name="stream_links" placeholder='Stream links JSON (e.g., [{"label":"1080p","url":"...m3u8"}])'></textarea>
        <button class="px-4 py-2 rounded-xl bg-black text-white">Save</button>
      </form>
    </div>
    <div class="bg-white border rounded-2xl p-4">
      <h2 class="font-semibold mb-3">Import from TMDB</h2>
      <form method="post" action="{{ url_for('admin_tmdb') }}" class="space-y-2">
        <input class="w-full border rounded-xl px-3 py-2" name="tmdb_id" placeholder="TMDB Movie ID" required>
        <button class="px-4 py-2 rounded-xl bg-black text-white">Import</button>
      </form>
      <p class="text-sm text-slate-500 mt-2">Requires TMDB_API_KEY</p>
    </div>
  </div>
{% endblock %}"""

WATCHLIST_TEMPLATE = """{% extends base %}
{% block content %}
  <h1 class="text-xl font-semibold mb-4">My Watchlist</h1>
  {% if items|length == 0 %}
    <div class="p-6 bg-white rounded-2xl border">Your watchlist is empty.</div>
  {% else %}
    <div class="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-5 gap-4">
      {% for m in items %}
      <a href="{{ url_for('movie_details', slug=m.slug) }}" class="card rounded-2xl overflow-hidden border bg-white">
        <img src="{{ m.poster_url or 'https://picsum.photos/300/450?blur=2' }}" class="w-full aspect-[2/3] object-cover"/>
        <div class="p-3">
          <div class="font-medium">{{ m.title }}</div>
          <div class="text-xs text-slate-500">{{ m.year }} • {{ (m.genres or [])|join(', ') }}</div>
        </div>
      </a>
      {% endfor %}
    </div>
  {% endif %}
{% endblock %}"""


# --------------------------
# Routes
# --------------------------
@app.context_processor
def inject_globals():
    u = session.get("user")
    class UserWrap:
        def __init__(self, raw):
            self.username = raw.get("username")
            self.role = raw.get("role", "user")
    return {"base": BASE_TEMPLATE, "user": UserWrap(u) if u else None, "now": datetime.utcnow(), "base_url": BASE_URL}

# NEW: Health check route for debugging
@app.route("/health")
def health_check():
    return "OK", 200

# NEW: Explicitly handle favicon requests to reduce log noise
@app.route('/favicon.ico')
def favicon():
    return '', 204 # No Content

@app.route("/")
def home():
    items = []
    try:
        # Added more specific exception handling for debugging
        items = list(movies_col.find({}, sort=[("views", -1)], limit=20))
    except Exception as e:
        logging.error(f"Error fetching movies for home page: {e}")
        # In case of error, you might want to render the template with an empty list
        # or show an error message. We'll proceed with an empty list for now.
    return render_template_string(HOME_TEMPLATE, movies=items, meta_title="Home • MovieZone")

# ... (rest of the routes are fine, no changes needed) ...
@app.route("/search")
def search():
    q = request.args.get("q", "").strip()
    if not q:
        return redirect(url_for("home"))
    regex = {"$regex": re.escape(q), "$options": "i"}
    try:
        movies = list(movies_col.find({"title": regex}, sort=[("views", -1)], limit=60))
    except Exception:
        movies = [m for m in movies_col.find() if re.search(re.escape(q), m.get("title",""), re.IGNORECASE)]
    return render_template_string(HOME_TEMPLATE, movies=movies, meta_title=f"Search: {q} • MovieZone")

@app.route("/movie/<slug>")
def movie_details(slug):
    movie = movies_col.find_one({"slug": slug})
    if not movie:
        abort(404)
    # increment views
    movies_col.update_one({"_id": movie["_id"]}, {"$inc": {"views": 1}})
    g0 = (movie.get("genres") or [None])[0]
    related = []
    if g0:
        try:
            related = list(movies_col.find({"genres": g0}, sort=[("views", -1)], limit=10))
        except Exception:
            related = [m for m in movies_col.find() if g0 in (m.get("genres") or [])]
    user = session.get("user")
    in_watch = False
    if user:
        ud = users_col.find_one({"username": user["username"]})
        if ud and slug in ud.get("watchlist", []):
            in_watch = True
    return render_template_string(DETAILS_TEMPLATE, movie=movie, related=[r for r in related if r.get("slug") != slug][:10], in_watchlist=in_watch, meta_title=f"{movie['title']} • MovieZone", meta_desc=(movie.get("description") or "")[:150])

@app.route("/play/<slug>/<int:idx>")
def play(slug, idx):
    movie = movies_col.find_one({"slug": slug})
    if not movie:
        abort(404)
    links = movie.get("stream_links") or []
    if not (0 <= idx < len(links)):
        abort(404)
    return redirect(links[idx]["url"])

@app.route("/login", methods=["GET", "POST"])
def login():
    next_url = request.args.get("next") or url_for("home")
    if request.method == "POST":
        username = request.form.get("username","").strip()
        password = request.form.get("password","")
        u = users_col.find_one({"username": username})
        if u and u.get("password_hash") == hashlib.sha256(password.encode()).hexdigest():
            session["user"] = {"username": u["username"], "role": u.get("role","user")}
            return redirect(next_url)
        return render_template_string(AUTH_TEMPLATE, mode="login", error="Invalid credentials")
    return render_template_string(AUTH_TEMPLATE, mode="login")

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form.get("username","").strip()
        password = request.form.get("password","")
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
    session.pop("user", None)
    return redirect(url_for("home"))

@app.route("/watchlist")
@require_login()
def watchlist():
    u = users_col.find_one({"username": session["user"]["username"]})
    slugs = u.get("watchlist", [])
    movies = []
    for s in slugs:
        m = movies_col.find_one({"slug": s})
        if m:
            movies.append(m)
    return render_template_string(WATCHLIST_TEMPLATE, items=movies, meta_title="My Watchlist")

@app.route("/watchlist/toggle/<slug>", methods=["POST"])
@require_login()
def toggle_watchlist(slug):
    u = users_col.find_one({"username": session["user"]["username"]})
    wl = set(u.get("watchlist", []))
    if slug in wl:
        wl.remove(slug)
    else:
        wl.add(slug)
    users_col.update_one({"_id": u["_id"]}, {"$set": {"watchlist": list(wl)}})
    return redirect(url_for("movie_details", slug=slug))

@app.route("/admin")
@require_login("admin")
def admin():
    try:
        items = list(movies_col.find({}, sort=[("_id", -1)], limit=24))
    except Exception:
        items = list(movies_col.find())
    tmdb_enabled = bool(requests and os.getenv("TMDB_API_KEY"))
    return render_template_string(ADMIN_TEMPLATE, movies=items, tmdb_enabled=tmdb_enabled)

@app.route("/admin/add", methods=["POST"])
@require_login("admin")
def admin_add():
    form = request.form
    stream_links = form.get("stream_links", "").strip()
    try:
        stream_links = json.loads(stream_links) if stream_links else []
    except Exception:
        stream_links = []
    doc = {
        "title": form.get("title", "Untitled").strip(),
        "year": int(form.get("year")) if (form.get("year") and form.get("year").isdigit()) else None,
        "language": form.get("language","").strip() or None,
        "genres": [g.strip() for g in (form.get("genres","").split(",") if form.get("genres") else []) if g.strip()],
        "poster_url": form.get("poster_url","").strip(),
        "trailer_url": form.get("trailer_url","").strip(),
        "description": form.get("description","").strip(),
        "stream_links": stream_links,
    }
    upsert_movie(doc)
    return redirect(url_for("admin"))

@app.route("/admin/tmdb", methods=["POST"])
@require_login("admin")
def admin_tmdb():
    if not requests:
        return "requests lib not available", 500
    api_key = os.getenv("TMDB_API_KEY")
    if not api_key:
        return "TMDB_API_KEY not set", 400
    tmdb_id = request.form.get("tmdb_id")
    try:
        r = requests.get(f"https://api.themoviedb.org/3/movie/{tmdb_id}", params={"api_key": api_key, "language": "en-US"}, timeout=10)
        r.raise_for_status()
        mv = r.json()
        title = mv.get("title") or mv.get("name")
        year = (mv.get("release_date") or "")[:4]
        poster = mv.get("poster_path")
        poster_url = f"https://image.tmdb.org/t/p/w500{poster}" if poster else ""
        genres = [g.get("name") for g in (mv.get("genres") or [])]
        doc = {
            "title": title,
            "year": int(year) if year.isdigit() else None,
            "language": (mv.get("original_language") or "").upper(),
            "genres": genres,
            "poster_url": poster_url,
            "trailer_url": "",
            "description": mv.get("overview") or "",
            "stream_links": [],
            "rating": mv.get("vote_average"),
        }
        upsert_movie(doc)
    except Exception as e:
        logging.error(f"TMDB import failed: {e}")
    return redirect(url_for("admin"))


# simple error handlers
@app.errorhandler(404)
def not_found(e):
    return render_template_string("""{% extends base %}{% block content %}
      <div class='bg-white border rounded-2xl p-8 text-center'>
        <div class='text-6xl'>🧐</div>
        <h1 class='text-2xl font-semibold mt-3'>Page not found</h1>
        <a href='{{ url_for('home') }}' class='inline-block mt-4 px-4 py-2 rounded-xl border'>Go Home</a>
      </div>{% endblock %}"""), 404

@app.errorhandler(403)
def forbidden(e):
    return "<h1>403 - Forbidden</h1>", 403

# --------------------------
# Seed sample data (if memory and empty)
# --------------------------
if not USE_MONGO:
    try:
        has_any = bool(next(movies_col.find(limit=1), None))
    except Exception:
        has_any = False
    if not has_any:
        logging.info("In-memory database is empty. Seeding sample data.")
        sample = [
            {"title": "Inception", "year": 2010, "language": "EN", "genres": ["Sci-Fi","Thriller"], "description": "A thief who steals corporate secrets through dream-sharing technology…", "poster_url": "https://image.tmdb.org/t/p/w500/qmDpIHrmpJINaRKAfWQfftjCdyi.jpg", "trailer_url": "https://www.youtube.com/watch?v=YoHD9XEInc0", "stream_links":[{"label":"720p","url":"https://test-streams.mux.dev/x36xhzz/x36xhzz.m3u8"}], "rating":8.8},
            {"title": "Interstellar", "year": 2014, "language": "EN", "genres": ["Sci-Fi","Adventure"], "description": "A team travels through a wormhole...", "poster_url": "https://image.tmdb.org/t/p/w500/rAiYTfKGqDCRIIqo664sY9XZIvQ.jpg", "trailer_url": "https://www.youtube.com/watch?v=zSWdZVtXT7E", "rating":8.6},
            {"title": "The Dark Knight", "year": 2008, "language": "EN", "genres": ["Action","Crime"], "description": "Batman vs Joker...", "poster_url": "https://image.tmdb.org/t/p/w500/qJ2tW6WMUDux911r6m7haRef0WH.jpg", "rating":9.0},
        ]
        for m in sample:
            upsert_movie(m)

# Entrypoint for local dev
if __name__ == "__main__":
    port = int(os.getenv("PORT", "5000"))
    logging.info(f"Starting locally at http://127.0.0.1:{port}  (admin: {ADMIN_USERNAME})")
    app.run(host="0.0.0.0", port=port, debug=True)

# `app` is exported for Vercel / other serverless imports
