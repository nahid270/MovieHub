""" Single-file Professional Movie Website (Flask)

One-file deploy: index.py

Features: Home, Search, Movie Details, Responsive UI (mobile/desktop), Auth (login/register), Watchlist, Admin Panel (add movie + TMDB import), Simple Analytics (views), SEO-friendly slugs.

DB: MongoDB (recommended). If MONGO_URI not set, uses in-memory store (for demo only).

Player: Video.js via CDN with HLS support (if m3u8 links provided).

Styling: TailwindCSS via CDN; Framer Motion-lite animations (CSS transitions only here).

Ready for Docker/Render/railway.app/Heroku. Vercel note: Python on Vercel requires serverless functions configuration; consider Render/railway for persistent Flask apps.


ENV VARS (set before running):

FLASK_SECRET      : Flask session secret (required for login sessions)

MONGO_URI         : MongoDB connection string (optional; if missing, uses in-memory store)

TMDB_API_KEY      : (optional) for importing movie metadata

ADMIN_USERNAME    : Admin login (default: admin)

ADMIN_PASSWORD    : Admin password (default: admin123)

BASE_URL          : (optional) canonical base URL for SEO (e.g., https://example.com)


RUN LOCALLY

python3 index.py

REQUIREMENTS (pip install)

Flask==3.0.0 pymongo==4.7.2 requests==2.32.3

(If you can't install now, the app still runs with in-memory DB without pymongo.)

""" from future import annotations import os import re import json import time import uuid import math import hashlib from datetime import datetime from urllib.parse import quote_plus, unquote_plus

try: from flask import Flask, request, redirect, url_for, render_template_string, session, abort, jsonify, make_response except Exception as e: raise SystemExit("Flask is required. Install with: pip install Flask")

Optional deps

try: import requests  # for TMDB import except Exception: requests = None

Optional Mongo support

USE_MONGO = False mongo_client = None movies_col = None users_col = None

ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin") ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin123")

app = Flask(name) app.secret_key = os.getenv("FLASK_SECRET", os.urandom(24)) BASE_URL = os.getenv("BASE_URL", "")

--------------------------

Data Layer (Mongo or Memory)

--------------------------

class MemoryCollection: def init(self): self.data = {}

def insert_one(self, doc):
    _id = doc.get("_id") or str(uuid.uuid4())
    doc["_id"] = _id
    self.data[_id] = json.loads(json.dumps(doc))
    return type("InsertResult", (), {"inserted_id": _id})

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
    # return shallow copy
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

def _set_nested(d, path, value): parts = path.split(".") cur = d for p in parts[:-1]: cur = cur.setdefault(p, {}) cur[parts[-1]] = value

def _match(doc, query): # very small subset: {field: value} or {field: {"$regex": pattern, "$options": "i"}} for k, v in (query or {}).items(): if isinstance(v, dict) and "$regex" in v: pattern = v["$regex"] flags = re.IGNORECASE if v.get("$options") == "i" else 0 val = str(doc.get(k, "")) if re.search(pattern, val, flags) is None: return False else: if doc.get(k) != v: return False return True

Initialize DB

MONGO_URI = os.getenv("MONGO_URI") if MONGO_URI: try: from pymongo import MongoClient, ASCENDING, DESCENDING mongo_client = MongoClient(MONGO_URI) db = mongo_client.get_default_database() if "/" in MONGO_URI.split("@")[ -1 ] else mongo_client["movie_site"] movies_col = db["movies"] users_col = db["users"] movies_col.create_index([("slug", 1)], unique=True) movies_col.create_index([("title", 1)]) movies_col.create_index([("year", 1)]) movies_col.create_index([("genres", 1)]) movies_col.create_index([("language", 1)]) movies_col.create_index([("views", -1)]) USE_MONGO = True except Exception as e: print("[WARN] Mongo init failed, falling back to in-memory store:", e)

if not USE_MONGO: movies_col = MemoryCollection() users_col = MemoryCollection()

Seed admin user if missing

if not users_col.find_one({"username": ADMIN_USERNAME}): users_col.insert_one({ "username": ADMIN_USERNAME, "password_hash": hashlib.sha256(ADMIN_PASSWORD.encode()).hexdigest(), "role": "admin", "created_at": datetime.utcnow().isoformat() })

--------------------------

Utilities

--------------------------

def slugify(text: str) -> str: text = re.sub(r"[^a-zA-Z0-9\s-]", "", text) text = re.sub(r"\s+", "-", text.strip()) return text.lower()

def require_login(role: str | None = None): def decorator(fn): def wrapper(*args, **kwargs): user = session.get("user") if not user: return redirect(url_for("login", next=request.path)) if role and user.get("role") != role: abort(403) return fn(*args, **kwargs) wrapper.name = fn.name return wrapper return decorator

def get_user(): return session.get("user")

def upsert_movie(doc: dict) -> str: # ensure fields doc.setdefault("title", "Untitled") doc.setdefault("year", None) doc.setdefault("language", "Unknown") doc.setdefault("genres", []) doc.setdefault("description", "") doc.setdefault("poster_url", "") doc.setdefault("trailer_url", "") doc.setdefault("stream_links", [])  # list of dict: {label, url} doc.setdefault("rating", None) doc.setdefault("views", 0)

slug = doc.get("slug") or slugify(f"{doc['title']} {doc.get('year') or ''}")
doc["slug"] = slug

existing = movies_col.find_one({"slug": slug})
if existing:
    movies_col.update_one({"_id": existing["_id"]}, {"$set": doc})
    return existing["_id"]
res = movies_col.insert_one(doc)
return str(res.inserted_id)

--------------------------

TEMPLATES (render_template_string)

--------------------------

BASE_TEMPLATE = """ <!doctype html>

<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{{ meta_title or 'Movie Site' }}</title>
  {% if base_url %}<link rel="canonical" href="{{ base_url + request.path }}" />{% endif %}
  <meta name="description" content="{{ meta_desc or 'Watch movies, search, and explore details.' }}" />
  <script src="https://cdn.tailwindcss.com"></script>
  <link href="https://vjs.zencdn.net/8.10.0/video-js.css" rel="stylesheet" />
  <script src="https://vjs.zencdn.net/8.10.0/video.min.js"></script>
  <link rel="icon" href="https://fav.farm/🎬" />
  <style>
    .container{max-width:1100px;margin:0 auto}
    .card{transition:transform .15s ease, box-shadow .15s ease}
    .card:hover{transform:translateY(-2px); box-shadow:0 10px 25px rgba(0,0,0,.08)}
  </style>
</head>
<body class="bg-slate-50 text-slate-900">
  <header class="border-b bg-white/80 backdrop-blur sticky top-0 z-40">
    <div class="container px-4 py-3 flex items-center gap-3">
      <a href="{{ url_for('home') }}" class="font-bold text-xl">🎬 MovieZone</a>
      <form action="{{ url_for('search') }}" method="get" class="flex-1">
        <input name="q" value="{{ request.args.get('q','') }}" placeholder="Search movies..." class="w-full rounded-xl border px-4 py-2" />
      </form>
      {% if user %}
        <a class="px-3 py-2 rounded-xl hover:bg-slate-100" href="{{ url_for('watchlist') }}">⭐ Watchlist</a>
        {% if user.role == 'admin' %}
          <a class="px-3 py-2 rounded-xl hover:bg-slate-100" href="{{ url_for('admin') }}">🛠️ Admin</a>
        {% endif %}
        <a class="px-3 py-2 rounded-xl hover:bg-slate-100" href="{{ url_for('logout') }}">Logout</a>
      {% else %}
        <a class="px-3 py-2 rounded-xl hover:bg-slate-100" href="{{ url_for('login') }}">Login</a>
      {% endif %}
    </div>
  </header>  <main class="container px-4 py-6">
    {% block content %}{% endblock %}
  </main>  <footer class="border-t py-6 text-center text-sm text-slate-500">© {{ now.year }} MovieZone</footer>
</body>
</html>
"""HOME_TEMPLATE = """ {% extends base %} {% block content %}

  <h1 class="text-2xl font-semibold mb-4">Trending</h1>
  <div class="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-5 gap-4">
    {% for m in movies %}
    <a href="{{ url_for('movie_details', slug=m.slug) }}" class="card rounded-2xl overflow-hidden border bg-white">
      <img src="{{ m.poster_url or 'https://picsum.photos/300/450?blur=2' }}" alt="{{ m.title }}" class="w-full aspect-[2/3] object-cover" />
      <div class="p-3">
        <div class="font-medium line-clamp-1">{{ m.title }}</div>
        <div class="text-xs text-slate-500">{{ m.year }} • {{ (m.genres or [])|join(', ') }}</div>
      </div>
    </a>
    {% endfor %}
  </div>
{% endblock %}
"""SEARCH_TEMPLATE = """ {% extends base %} {% block content %}

  <h1 class="text-xl font-semibold mb-4">Search results for "{{ q }}"</h1>
  {% if movies|length == 0 %}
    <div class="p-6 bg-white rounded-2xl border">No results found.</div>
  {% else %}
    <div class="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-5 gap-4">
      {% for m in movies %}
      <a href="{{ url_for('movie_details', slug=m.slug) }}" class="card rounded-2xl overflow-hidden border bg-white">
        <img src="{{ m.poster_url or 'https://picsum.photos/300/450?blur=2' }}" alt="{{ m.title }}" class="w-full aspect-[2/3] object-cover" />
        <div class="p-3">
          <div class="font-medium line-clamp-1">{{ m.title }}</div>
          <div class="text-xs text-slate-500">{{ m.year }} • {{ (m.genres or [])|join(', ') }}</div>
        </div>
      </a>
      {% endfor %}
    </div>
  {% endif %}
{% endblock %}
"""DETAILS_TEMPLATE = """ {% extends base %} {% block content %}

  <div class="grid grid-cols-1 lg:grid-cols-3 gap-6">
    <div class="lg:col-span-2 space-y-4">
      {% if movie.trailer_url %}
      <div class="rounded-2xl overflow-hidden border bg-black">
        <iframe class="w-full aspect-video" src="{{ movie.trailer_url|replace('watch?v=','embed/') }}" allowfullscreen></iframe>
      </div>
      {% endif %}{% if movie.stream_links %}
  <div class="rounded-2xl overflow-hidden border bg-black p-4">
    <video id="player" class="video-js vjs-default-skin w-full aspect-video" controls preload="auto"></video>
    <div class="mt-3 flex flex-wrap gap-2">
      {% for s in movie.stream_links %}
        <a href="{{ url_for('play', slug=movie.slug, idx=loop.index0) }}" class="px-3 py-1 rounded-xl border bg-white">Play: {{ s.label }}</a>
      {% endfor %}
    </div>
  </div>
  {% endif %}

  <div class="rounded-2xl overflow-hidden border bg-white p-4">
    <h1 class="text-2xl font-bold">{{ movie.title }} <span class="text-slate-500 font-normal">({{ movie.year }})</span></h1>
    <div class="text-sm text-slate-500">{{ movie.language }} • {{ (movie.genres or [])|join(', ') }}</div>
    <p class="mt-3 text-slate-700">{{ movie.description }}</p>
  </div>

  {% if related|length %}
  <div class="rounded-2xl overflow-hidden border bg-white p-4">
    <h2 class="text-lg font-semibold mb-3">Related</h2>
    <div class="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-5 gap-4">
      {% for m in related %}
      <a href="{{ url_for('movie_details', slug=m.slug) }}" class="card rounded-2xl overflow-hidden border bg-white">
        <img src="{{ m.poster_url or 'https://picsum.photos/300/450?blur=2' }}" class="w-full aspect-[2/3] object-cover"/>
        <div class="p-3">
          <div class="font-medium line-clamp-1">{{ m.title }}</div>
          <div class="text-xs text-slate-500">{{ m.year }} • {{ (m.genres or [])|join(', ') }}</div>
        </div>
      </a>
      {% endfor %}
    </div>
  </div>
  {% endif %}
</div>

<aside class="space-y-4">
  <img src="{{ movie.poster_url or 'https://picsum.photos/400/600?blur=2' }}" class="w-full rounded-2xl border" />
  <div class="rounded-2xl overflow-hidden border bg-white p-4 text-sm">
    <div>Rating: {{ movie.rating or 'N/A' }}</div>
    <div>Views: {{ movie.views or 0 }}</div>
    {% if user %}
      <form method="post" action="{{ url_for('toggle_watchlist', slug=movie.slug) }}" class="mt-3">
        <button class="px-4 py-2 rounded-xl border bg-amber-50">⭐ {{ 'Remove from' if in_watchlist else 'Add to' }} Watchlist</button>
      </form>
    {% else %}
      <a href="{{ url_for('login', next=request.path) }}" class="inline-block mt-3 px-4 py-2 rounded-xl border">Login to add to Watchlist</a>
    {% endif %}
  </div>
</aside>

  </div>
{% endblock %}
"""AUTH_TEMPLATE = """ {% extends base %} {% block content %}

  <div class="max-w-md mx-auto bg-white rounded-2xl border p-6">
    <h1 class="text-xl font-semibold mb-4">{{ mode|title }}</h1>
    <form method="post" class="space-y-3">
      <input name="username" placeholder="Username" class="w-full border rounded-xl px-3 py-2" required />
      <input name="password" placeholder="Password" type="password" class="w-full border rounded-xl px-3 py-2" required />
      <button class="w-full px-4 py-2 rounded-xl bg-black text-white">{{ mode|title }}</button>
    </form>
  </div>
{% endblock %}
"""ADMIN_TEMPLATE = """ {% extends base %} {% block content %}

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
        <textarea class="w-full border rounded-xl px-3 py-2" name="stream_links" placeholder='Stream links JSON (e.g., [{"label":"1080p","url":"https://...m3u8"}])'></textarea>
        <button class="px-4 py-2 rounded-xl bg-black text-white">Save</button>
      </form>
    </div><div class="bg-white border rounded-2xl p-4">
  <h2 class="font-semibold mb-3">Import from TMDB</h2>
  <form method="post" action="{{ url_for('admin_tmdb') }}" class="space-y-2">
    <input class="w-full border rounded-xl px-3 py-2" name="tmdb_id" placeholder="TMDB Movie ID" required>
    <button class="px-4 py-2 rounded-xl bg-black text-white">Import</button>
  </form>
  <p class="text-sm text-slate-500 mt-2">Requires TMDB_API_KEY</p>
</div>

  </div>  <h2 class="text-xl font-semibold mt-8 mb-4">Recent Movies</h2>
  <div class="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-4">
    {% for m in movies %}
    <a href="{{ url_for('movie_details', slug=m.slug) }}" class="card rounded-2xl overflow-hidden border bg-white">
      <img src="{{ m.poster_url or 'https://picsum.photos/300/450?blur=2' }}" class="w-full aspect-[2/3] object-cover"/>
      <div class="p-2 text-xs">
        <div class="font-medium line-clamp-1">{{ m.title }}</div>
        <div class="text-slate-500">{{ m.year }}</div>
      </div>
    </a>
    {% endfor %}
  </div>
{% endblock %}
"""WATCHLIST_TEMPLATE = """ {% extends base %} {% block content %}

  <h1 class="text-xl font-semibold mb-4">My Watchlist</h1>
  {% if items|length == 0 %}
    <div class="p-6 bg-white rounded-2xl border">Your watchlist is empty.</div>
  {% else %}
    <div class="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-5 gap-4">
      {% for m in items %}
      <a href="{{ url_for('movie_details', slug=m.slug) }}" class="card rounded-2xl overflow-hidden border bg-white">
        <img src="{{ m.poster_url or 'https://picsum.photos/300/450?blur=2' }}" class="w-full aspect-[2/3] object-cover"/>
        <div class="p-3">
          <div class="font-medium line-clamp-1">{{ m.title }}</div>
          <div class="text-xs text-slate-500">{{ m.year }} • {{ (m.genres or [])|join(', ') }}</div>
        </div>
      </a>
      {% endfor %}
    </div>
  {% endif %}
{% endblock %}
"""--------------------------

Routes

--------------------------

@app.context_processor def inject_globals(): class UserWrap: def init(self, u): self.username = u.get("username") self.role = u.get("role", "user") u = session.get("user") return { "base": BASE_TEMPLATE, "user": UserWrap(u) if u else None, "now": datetime.utcnow(), "base_url": BASE_URL, }

@app.route("/") def home(): # top by views items = list(movies_col.find({}, sort=[("views", -1)], limit=20)) return render_template_string(HOME_TEMPLATE, movies=items, meta_title="Home • MovieZone")

@app.route("/search") def search(): q = request.args.get("q", "").strip() items = [] if q: regex = {"$regex": re.escape(q), "$options": "i"} items = list(movies_col.find({"title": regex}, sort=[("views", -1)], limit=60)) return render_template_string(SEARCH_TEMPLATE, movies=items, q=q, meta_title=f"Search: {q} • MovieZone")

@app.route("/movie/<slug>") def movie_details(slug): m = movies_col.find_one({"slug": slug}) if not m: abort(404) # increment views movies_col.update_one({"_id": m["_id"]}, {"$inc": {"views": 1}}) # related by first genre g0 = (m.get("genres") or [None])[0] related = list(movies_col.find({"genres": g0}, sort=[("views", -1)], limit=10)) if g0 else []

user = session.get("user")
in_watch = False
if user:
    u = users_col.find_one({"username": user["username"]})
    wl = set(u.get("watchlist", []))
    in_watch = m["slug"] in wl

return render_template_string(DETAILS_TEMPLATE,
    movie=m,
    related=[r for r in related if r.get("slug") != slug][:10],
    in_watchlist=in_watch,
    meta_title=f"{m['title']} ({m.get('year') or ''}) • MovieZone",
    meta_desc=(m.get('description') or '')[:150]
)

@app.route("/play/<slug>/int:idx") def play(slug, idx): m = movies_col.find_one({"slug": slug}) if not m: abort(404) links = m.get("stream_links") or [] if not (0 <= idx < len(links)): abort(404) # simple redirect to the actual stream link (lets browser/player handle it) return redirect(links[idx]["url"])  # you can embed signed links logic here

@app.route("/login", methods=["GET", "POST"]) def login(): next_url = request.args.get("next") or url_for("home") if request.method == "POST": username = request.form.get("username", "").strip() password = request.form.get("password", "") user = users_col.find_one({"username": username}) if user: if user.get("password_hash") == hashlib.sha256(password.encode()).hexdigest(): session["user"] = {"username": user["username"], "role": user.get("role", "user")} return redirect(next_url) return render_template_string(AUTH_TEMPLATE, mode="login", error="Invalid credentials") return render_template_string(AUTH_TEMPLATE, mode="login")

@app.route("/register", methods=["GET", "POST"]) def register(): if request.method == "POST": username = request.form.get("username", "").strip() password = request.form.get("password", "") if users_col.find_one({"username": username}): return render_template_string(AUTH_TEMPLATE, mode="register", error="Username exists") users_col.insert_one({ "username": username, "password_hash": hashlib.sha256(password.encode()).hexdigest(), "role": "user", "watchlist": [], "created_at": datetime.utcnow().isoformat() }) session["user"] = {"username": username, "role": "user"} return redirect(url_for("home")) return render_template_string(AUTH_TEMPLATE, mode="register")

@app.route("/logout") def logout(): session.pop("user", None) return redirect(url_for("home"))

@app.route("/watchlist") @require_login() def watchlist(): u = users_col.find_one({"username": session["user"]["username"]}) slugs = u.get("watchlist", []) items = [] for s in slugs: m = movies_col.find_one({"slug": s}) if m: items.append(m) return render_template_string(WATCHLIST_TEMPLATE, items=items, meta_title="My Watchlist • MovieZone")

@app.route("/watchlist/toggle/<slug>", methods=["POST"]) @require_login() def toggle_watchlist(slug): u = users_col.find_one({"username": session["user"]["username"]}) wl = set(u.get("watchlist", [])) if slug in wl: wl.remove(slug) else: wl.add(slug) users_col.update_one({"_id": u["_id"]}, {"$set": {"watchlist": list(wl)}}) return redirect(url_for("movie_details", slug=slug))

@app.route("/admin") @require_login("admin") def admin(): items = list(movies_col.find({}, sort=[("_id", -1)], limit=24)) return render_template_string(ADMIN_TEMPLATE, movies=items, meta_title="Admin • MovieZone")

@app.route("/admin/add", methods=["POST"]) @require_login("admin") def admin_add(): form = request.form stream_links = form.get("stream_links", "").strip() try: stream_links = json.loads(stream_links) if stream_links else [] except Exception: stream_links = [] doc = { "title": form.get("title", "Untitled").strip(), "year": int(form.get("year") or 0) or None, "language": form.get("language", "").strip() or None, "genres": [g.strip() for g in (form.get("genres", "").split(",") if form.get("genres") else []) if g.strip()], "poster_url": form.get("poster_url", "").strip(), "trailer_url": form.get("trailer_url", "").strip(), "description": form.get("description", "").strip(), "stream_links": stream_links, } upsert_movie(doc) return redirect(url_for("admin"))

@app.route("/admin/tmdb", methods=["POST"]) @require_login("admin") def admin_tmdb(): if not requests: return "requests lib not available", 500 api_key = os.getenv("TMDB_API_KEY") if not api_key: return "TMDB_API_KEY not set", 400 tmdb_id = request.form.get("tmdb_id") try: r = requests.get(f"https://api.themoviedb.org/3/movie/{tmdb_id}", params={"api_key": api_key, "language": "en-US"}, timeout=10) r.raise_for_status() mv = r.json() title = mv.get("title") or mv.get("name") year = (mv.get("release_date") or "")[:4] poster = mv.get("poster_path") poster_url = f"https://image.tmdb.org/t/p/w500{poster}" if poster else "" genres = [g.get("name") for g in (mv.get("genres") or [])] doc = { "title": title, "year": int(year) if year.isdigit() else None, "language": (mv.get("original_language") or "").upper(), "genres": genres, "poster_url": poster_url, "trailer_url": "", "description": mv.get("overview") or "", "stream_links": [], "rating": mv.get("vote_average"), } upsert_movie(doc) return redirect(url_for("admin")) except Exception as e: return f"TMDB import failed: {e}", 500

--------------------------

Error Handlers

--------------------------

@app.errorhandler(404) def not_found(e): return render_template_string(""" {% extends base %} {% block content %} <div class='bg-white border rounded-2xl p-8 text-center'> <div class='text-6xl'>🧐</div> <h1 class='text-2xl font-semibold mt-3'>Page not found</h1> <p class='text-slate-500 mt-2'>The page you are looking for does not exist.</p> <a href='{{ url_for('home') }}' class='inline-block mt-4 px-4 py-2 rounded-xl border'>Go Home</a> </div> {% endblock %} """), 404

--------------------------

Seed sample data (only for memory mode)

--------------------------

if not USE_MONGO: sample = [ { "title": "Inception", "year": 2010, "language": "EN", "genres": ["Sci-Fi", "Thriller"], "description": "A thief who steals corporate secrets through dream-sharing technology…", "poster_url": "https://image.tmdb.org/t/p/w500/qmDpIHrmpJINaRKAfWQfftjCdyi.jpg", "trailer_url": "https://www.youtube.com/watch?v=YoHD9XEInc0", "stream_links": [{"label": "720p", "url": "https://test-streams.mux.dev/x36xhzz/x36xhzz.m3u8"}], "rating": 8.8, }, { "title": "Interstellar", "year": 2014, "language": "EN", "genres": ["Sci-Fi", "Adventure"], "description": "A team travels through a wormhole in space in an attempt to ensure humanity's survival.", "poster_url": "https://image.tmdb.org/t/p/w500/rAiYTfKGqDCRIIqo664sY9XZIvQ.jpg", "trailer_url": "https://www.youtube.com/watch?v=zSWdZVtXT7E", "stream_links": [{"label": "1080p", "url": "https://test-streams.mux.dev/x36xhzz/x36xhzz.m3u8"}], "rating": 8.6, }, ] for s in sample: upsert_movie(s)

--------------------------

App Entrypoint

--------------------------

if name == "main": port = int(os.getenv("PORT", "5000")) print(f"\n🚀 Movie website running on http://127.0.0.1:{port}\nAdmin Login: {ADMIN_USERNAME} / {ADMIN_PASSWORD}\n") app.run(host="0.0.0.0", port=port, debug=True)

