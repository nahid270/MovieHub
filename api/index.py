# ====================================================================================
# FINAL & READY: Single-File Professional Movie Website (Python + Flask)
# ====================================================================================
#
# বৈশিষ্ট্য (Features):
# --------------------
# - একটি মাত্র ফাইল (`index.py`) দিয়ে সম্পূর্ণ ওয়েবসাইট।
# - হোমপেজ, সার্চ, মুভি ডিটেইলস, লগইন/রেজিস্ট্রেশন, ওয়াচলিস্ট।
# - শক্তিশালী অ্যাডমিন প্যানেল (মুভি যোগ করা, TMDB থেকে ইম্পোর্ট করা)।
# - ডেটাবেস: MongoDB সাপোর্ট (যদি MONGO_URI দেওয়া থাকে), இல்லையெனில் ইন-মেমোরি ডেটাবেস।
# - রেসপন্সিভ ডিজাইন: TailwindCSS দ্বারা চালিত, মোবাইল ও পিসিতে সুন্দরভাবে কাজ করে।
# - SEO-ফ্রেন্ডলি URL এবং ভিডিও প্লেয়ার ইন্টিগ্রেটেড।
#
# কীভাবে ডিপ্লয় করবেন (How to Deploy):
# ------------------------------------
# ১. GitHub-এ একটি রিপোজিটরি তৈরি করুন।
# ২. এই সম্পূর্ণ কোডটি `index.py` নামে একটি ফাইলে পেস্ট করুন।
# ৩. `requirements.txt` নামে আরেকটি ফাইল তৈরি করে প্রয়োজনীয় প্যাকেজের নামগুলো লিখুন।
# ৪. Render.com এ যান, GitHub রিপোজিটরিটি কানেক্ট করুন এবং নিচের Environment Variable-গুলো যোগ করুন।
#
# প্রয়োজনীয় Environment Variables (Render.com এ যোগ করতে হবে):
# -------------------------------------------------------------
# - FLASK_SECRET      : একটি র‍্যান্ডম সিক্রেট কী (যেমন: my_super_secret_key_12345)
# - MONGO_URI         : আপনার MongoDB কানেকশন স্ট্রিং (ডেটা স্থায়ীভাবে সেভ করার জন্য)
# - TMDB_API_KEY      : আপনার TMDB API কী (মুভি ইম্পোর্টের জন্য)
# - ADMIN_USERNAME    : অ্যাডমিন প্যানেলের ইউজারনেম (যেমন: admin)
# - ADMIN_PASSWORD    : অ্যাডমিন প্যানেলের পাসওয়ার্ড (যেমন: admin123)
#
# ====================================================================================

from __future__ import annotations
import os
import re
import json
import uuid
import hashlib
from datetime import datetime

# Flask ইনস্টল করা না থাকলে, এটি একটি এরর দেখাবে।
try:
    from flask import Flask, request, redirect, url_for, render_template_string, session, abort, jsonify
except Exception:
    raise SystemExit("Flask is required. Install with: pip install Flask")

# ঐচ্ছিক প্যাকেজ (না থাকলেও অ্যাপ চলবে, কিন্তু কিছু ফিচার কাজ করবে না)
try:
    import requests  # TMDB থেকে মুভি ইম্পোর্টের জন্য
except Exception:
    requests = None
try:
    from pymongo import MongoClient, DESCENDING
    PYMONGO_AVAILABLE = True
except Exception:
    PYMONGO_AVAILABLE = False


# --- অ্যাপ কনফিগারেশন ---
app = Flask(__name__)
# সেশন ব্যবহারের জন্য সিক্রেট কী। এটি Environment Variable থেকে আসবে।
app.secret_key = os.getenv("FLASK_SECRET", "default_secret_key_for_local_development")

# অ্যাডমিন অ্যাকাউন্টের ডিফল্ট তথ্য
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin123")


# --------------------------
# ডেটাবেস লেয়ার (MongoDB অথবা ইন-মেমোরি)
# --------------------------

# এটি একটি ক্লাস যা ডেটাবেস না থাকলেও ডেটাবেসের মতো কাজ করে।
class MemoryCollection:
    def __init__(self): self.data = {}
    def insert_one(self, doc):
        _id = doc.get("_id") or str(uuid.uuid4()); doc["_id"] = _id
        self.data[_id] = json.loads(json.dumps(doc))
        return type("InsertResult", (), {"inserted_id": _id})
    def find_one(self, query):
        for doc in self.data.values():
            if self._match(doc, query): return json.loads(json.dumps(doc))
        return None
    def find(self, query=None, sort=None, limit=0, skip=0):
        items = [d for d in list(self.data.values()) if self._match(d, query)]
        if sort:
            key, direction = sort[0]
            items.sort(key=lambda d: d.get(key, 0), reverse=(direction < 0))
        if skip: items = items[skip:]
        if limit: items = items[:limit]
        for d in items: yield json.loads(json.dumps(d))
    def update_one(self, query, update):
        for _id, doc in list(self.data.items()):
            if self._match(doc, query):
                if "$set" in update: doc.update(update["$set"])
                if "$inc" in update:
                    for k, v in update["$inc"].items(): doc[k] = doc.get(k, 0) + v
                self.data[_id] = doc; return
    def _match(self, doc, query):
        for k, v in (query or {}).items():
            if isinstance(v, dict) and "$regex" in v:
                if re.search(v["$regex"], str(doc.get(k, "")), re.IGNORECASE) is None: return False
            elif doc.get(k) != v: return False
        return True

# ডেটাবেস কানেকশন সেটআপ
MONGO_URI = os.getenv("MONGO_URI")
if MONGO_URI and PYMONGO_AVAILABLE:
    try:
        mongo_client = MongoClient(MONGO_URI)
        db = mongo_client.get_default_database()
        movies_col = db["movies"]
        users_col = db["users"]
        movies_col.create_index([("slug", 1)], unique=True)
        USE_MONGO = True
        print("[INFO] Successfully connected to MongoDB.")
    except Exception as e:
        USE_MONGO = False
        print(f"[WARN] MongoDB connection failed: {e}. Falling back to in-memory store.")
else:
    USE_MONGO = False
    movies_col = MemoryCollection()
    users_col = MemoryCollection()
    print("[INFO] MONGO_URI not set. Using temporary in-memory data store.")

# অ্যাডমিন ইউজার তৈরি করা (যদি না থাকে)
if not users_col.find_one({"username": ADMIN_USERNAME}):
    users_col.insert_one({
        "username": ADMIN_USERNAME,
        "password_hash": hashlib.sha256(ADMIN_PASSWORD.encode()).hexdigest(),
        "role": "admin",
        "created_at": datetime.utcnow().isoformat()
    })

# --------------------------
# হেল্পার ফাংশন
# --------------------------

# সুন্দর URL তৈরির জন্য ফাংশন
def slugify(text: str) -> str:
    text = re.sub(r"[^a-zA-Z0-9\s-]", "", text).strip().lower()
    return re.sub(r"\s+", "-", text)

# লগইন করা আছে কিনা তা চেক করার জন্য ডেকোরেটর
def require_login(role: str | None = None):
    def decorator(fn):
        def wrapper(*args, **kwargs):
            if not session.get("user"): return redirect(url_for("login", next=request.path))
            if role and session["user"].get("role") != role: abort(403, "Access denied")
            return fn(*args, **kwargs)
        wrapper.__name__ = fn.__name__
        return wrapper
    return decorator

# মুভি ডেটাবেসে যোগ বা আপডেট করার ফাংশন
def upsert_movie(doc: dict) -> str:
    doc.setdefault("title", "Untitled")
    doc["slug"] = doc.get("slug") or slugify(f"{doc['title']} {doc.get('year') or ''}")
    existing = movies_col.find_one({"slug": doc["slug"]})
    if existing:
        movies_col.update_one({"_id": existing["_id"]}, {"$set": doc})
        return existing["_id"]
    doc.setdefault("views", 0)
    res = movies_col.insert_one(doc)
    return str(res.inserted_id)

# --------------------------
# HTML টেমপ্লেট (সম্পূর্ণ UI)
# --------------------------
BASE_TEMPLATE = """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" /><meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{{ meta_title or 'MovieZone' }}</title>
  <meta name="description" content="{{ meta_desc or 'Explore and watch movies.' }}" />
  <script src="https://cdn.tailwindcss.com"></script>
  <link href="https://vjs.zencdn.net/8.10.0/video-js.css" rel="stylesheet" />
  <script src="https://vjs.zencdn.net/8.10.0/video.min.js"></script>
  <style> body { font-family: 'Inter', sans-serif; } .card{transition:transform .2s ease, box-shadow .2s ease} .card:hover{transform:translateY(-4px); box-shadow:0 12px 28px rgba(0,0,0,.1)} </style>
</head>
<body class="bg-gray-100 text-gray-800">
  <header class="bg-white/90 backdrop-blur-lg sticky top-0 z-50 border-b">
    <div class="max-w-6xl mx-auto px-4 py-3 flex items-center justify-between gap-3">
      <a href="{{ url_for('home') }}" class="font-bold text-2xl">🎬 MovieZone</a>
      <form action="{{ url_for('search') }}" method="get" class="flex-1 max-w-md hidden sm:block">
        <input name="q" value="{{ request.args.get('q','') }}" placeholder="Search movies by title..." class="w-full bg-gray-100 rounded-full border px-4 py-2 focus:ring-2 focus:ring-blue-500 outline-none" />
      </form>
      <nav class="flex items-center gap-2">
        {% if user %}
          <a class="px-3 py-2 rounded-lg hover:bg-gray-200 text-sm" href="{{ url_for('watchlist') }}">⭐ Watchlist</a>
          {% if user.role == 'admin' %}<a class="px-3 py-2 rounded-lg hover:bg-gray-200 text-sm" href="{{ url_for('admin') }}">🛠️ Admin</a>{% endif %}
          <a class="px-3 py-2 rounded-lg hover:bg-gray-200 text-sm" href="{{ url_for('logout') }}">Logout</a>
        {% else %}
          <a class="px-3 py-2 rounded-lg bg-blue-600 text-white text-sm" href="{{ url_for('login') }}">Login</a>
        {% endif %}
      </nav>
    </div>
  </header>
  <main class="max-w-6xl mx-auto px-4 py-8">
    {% block content %}{% endblock %}
  </main>
  <footer class="border-t py-6 text-center text-sm text-gray-500">© {{ now.year }} MovieZone. All rights reserved.</footer>
</body></html>"""

HOME_TEMPLATE = """
{% extends base %}{% block content %}
  <h1 class="text-3xl font-bold mb-6">Trending Movies</h1>
  <div class="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-5">
    {% for m in movies %}
    <a href="{{ url_for('movie_details', slug=m.slug) }}" class="card rounded-xl overflow-hidden border bg-white shadow-sm">
      <img src="{{ m.poster_url or 'https://placehold.co/400x600?text=No+Image' }}" alt="{{ m.title }}" class="w-full aspect-[2/3] object-cover" />
      <div class="p-3">
        <h3 class="font-semibold text-md truncate">{{ m.title }}</h3>
        <p class="text-xs text-gray-500">{{ m.year }} &bull; {{ (m.genres or [])|join(', ') }}</p>
      </div>
    </a>
    {% endfor %}
  </div>{% endblock %}"""

DETAILS_TEMPLATE = """
{% extends base %}{% block content %}
  <div class="grid grid-cols-1 lg:grid-cols-3 gap-8">
    <div class="lg:col-span-2 space-y-6">
      {% if movie.stream_links %}
      <div class="rounded-xl overflow-hidden border bg-black aspect-video">
        <video id="player" class="video-js vjs-big-play-centered w-full h-full" controls preload="auto" poster="{{ movie.poster_url }}">
          <source src="{{ (movie.stream_links[0]).url }}" type="application/x-mpegURL">
        </video>
        <script>var player = videojs('player', { responsive: true, fluid: true });</script>
      </div>
      {% elif movie.trailer_url %}
        <div class="rounded-xl overflow-hidden border bg-black aspect-video"><iframe class="w-full h-full" src="{{ movie.trailer_url|replace('watch?v=','embed/') }}" allowfullscreen></iframe></div>
      {% endif %}
      <div class="bg-white rounded-xl border p-5">
        <h1 class="text-4xl font-extrabold">{{ movie.title }} <span class="text-gray-400 font-normal">({{ movie.year }})</span></h1>
        <div class="mt-2 flex flex-wrap gap-2">{% for g in movie.genres %}<span class="text-xs bg-gray-200 px-2 py-1 rounded-full">{{g}}</span>{% endfor %}</div>
        <p class="mt-4 text-gray-700 leading-relaxed">{{ movie.description }}</p>
      </div>
    </div>
    <aside class="space-y-6">
      <img src="{{ movie.poster_url or 'https://placehold.co/400x600?text=No+Image' }}" class="w-full rounded-xl border shadow-md" />
      <div class="bg-white rounded-xl border p-4 text-sm">
        <p><strong>Rating:</strong> {{ movie.rating or 'N/A' }} / 10</p>
        <p><strong>Views:</strong> {{ movie.views or 0 }}</p>
        {% if user %}
          <form method="post" action="{{ url_for('toggle_watchlist', slug=movie.slug) }}" class="mt-4">
            <button class="w-full px-4 py-2 rounded-lg font-semibold {{ 'bg-yellow-400' if in_watchlist else 'bg-yellow-200' }}">⭐ {{ 'Remove from' if in_watchlist else 'Add to' }} Watchlist</button>
          </form>
        {% else %}
          <a href="{{ url_for('login', next=request.path) }}" class="block text-center mt-4 px-4 py-2 rounded-lg bg-yellow-200 font-semibold">Login to Add to Watchlist</a>
        {% endif %}
      </div>
    </aside>
  </div>{% endblock %}"""

AUTH_TEMPLATE = """
{% extends base %}{% block content %}
  <div class="max-w-sm mx-auto bg-white rounded-xl border p-8">
    <h1 class="text-2xl font-bold text-center mb-6">{{ mode|title }}</h1>
    {% if error %}<p class="bg-red-100 text-red-700 p-3 rounded-lg mb-4 text-sm">{{error}}</p>{% endif %}
    <form method="post" class="space-y-4">
      <input name="username" placeholder="Username" class="w-full border rounded-lg px-4 py-2" required />
      <input name="password" placeholder="Password" type="password" class="w-full border rounded-lg px-4 py-2" required />
      <button class="w-full px-4 py-3 rounded-lg bg-blue-600 text-white font-semibold">{{ mode|title }}</button>
    </form>
    <div class="text-center mt-4 text-sm">
      {% if mode == 'login' %}
        Don't have an account? <a href="{{ url_for('register') }}" class="text-blue-600">Register</a>
      {% else %}
        Already have an account? <a href="{{ url_for('login') }}" class="text-blue-600">Login</a>
      {% endif %}
    </div>
  </div>{% endblock %}"""

ADMIN_TEMPLATE = """
{% extends base %}{% block content %}
  <h1 class="text-3xl font-bold mb-6">Admin Panel</h1>
  <div class="grid md:grid-cols-2 gap-8">
    <div class="bg-white border rounded-xl p-5">
      <h2 class="text-xl font-semibold mb-4">Add / Update Movie</h2>
      <form method="post" action="{{ url_for('admin_add') }}" class="space-y-3">
        <input class="w-full border rounded-lg p-2" name="title" placeholder="Title*" required>
        <div class="grid grid-cols-2 gap-3"><input class="w-full border rounded-lg p-2" name="year" placeholder="Year"><input class="w-full border rounded-lg p-2" name="language" placeholder="Language"></div>
        <input class="w-full border rounded-lg p-2" name="genres" placeholder="Genres (comma-separated)">
        <input class="w-full border rounded-lg p-2" name="poster_url" placeholder="Poster URL">
        <input class="w-full border rounded-lg p-2" name="trailer_url" placeholder="Trailer URL (YouTube)">
        <textarea class="w-full border rounded-lg p-2" name="description" placeholder="Description" rows="3"></textarea>
        <textarea class="w-full border rounded-lg p-2" name="stream_links" placeholder='Stream links JSON, e.g., [{"label":"720p","url":"...m3u8"}]' rows="2"></textarea>
        <button class="px-5 py-2 rounded-lg bg-blue-600 text-white font-semibold">Save Movie</button>
      </form>
    </div>
    <div class="bg-white border rounded-xl p-5">
      <h2 class="text-xl font-semibold mb-4">Import from TMDB</h2>
      <form method="post" action="{{ url_for('admin_tmdb') }}" class="space-y-3">
        <input class="w-full border rounded-lg p-2" name="tmdb_id" placeholder="Enter TMDB Movie ID (e.g., 27205)" required>
        <button class="px-5 py-2 rounded-lg bg-blue-600 text-white font-semibold" {% if not tmdb_enabled %}disabled title="TMDB_API_KEY not set"{% endif %}>Import</button>
      </form>
      {% if not tmdb_enabled %}<p class="text-sm text-red-600 mt-2">TMDB_API_KEY is not configured.</p>{% endif %}
    </div>
  </div>{% endblock %}"""

# --------------------------
# রাউট (পেজ এবং লজিক)
# --------------------------

# এই ফাংশনটি সব টেমপ্লেটে কিছু গ্লোবাল ভ্যারিয়েবল পাঠায়
@app.context_processor
def inject_globals():
    user = session.get("user")
    return {"base": BASE_TEMPLATE, "user": user, "now": datetime.utcnow()}

# হোমপেজ
@app.route("/")
def home():
    movies = list(movies_col.find({}, sort=[("views", -1)], limit=20))
    return render_template_string(HOME_TEMPLATE, movies=movies)

# সার্চ পেজ
@app.route("/search")
def search():
    q = request.args.get("q", "").strip()
    if not q: return redirect(url_for('home'))
    regex = {"$regex": re.escape(q), "$options": "i"}
    movies = list(movies_col.find({"title": regex}, limit=50))
    return render_template_string(HOME_TEMPLATE, movies=movies, meta_title=f'Search results for "{q}"')

# মুভি ডিটেইলস পেজ
@app.route("/movie/<slug>")
def movie_details(slug):
    movie = movies_col.find_one({"slug": slug})
    if not movie: abort(404)
    movies_col.update_one({"_id": movie["_id"]}, {"$inc": {"views": 1}}) # ভিউ কাউন্ট বাড়ানো হচ্ছে
    user = session.get("user")
    in_watchlist = False
    if user:
        user_data = users_col.find_one({"username": user["username"]})
        if user_data and slug in user_data.get("watchlist", []): in_watchlist = True
    return render_template_string(DETAILS_TEMPLATE, movie=movie, in_watchlist=in_watchlist)

# লগইন পেজ
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"].strip()
        password = request.form["password"]
        user = users_col.find_one({"username": username})
        if user and user["password_hash"] == hashlib.sha256(password.encode()).hexdigest():
            session["user"] = {"username": user["username"], "role": user.get("role", "user")}
            return redirect(request.args.get("next") or url_for("home"))
        return render_template_string(AUTH_TEMPLATE, mode="login", error="Invalid username or password.")
    return render_template_string(AUTH_TEMPLATE, mode="login")

# রেজিস্টার পেজ
@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form["username"].strip()
        password = request.form["password"]
        if not (4 <= len(username) <= 20 and re.match("^[a-zA-Z0-9_]+$", username)):
            return render_template_string(AUTH_TEMPLATE, mode="register", error="Username must be 4-20 chars and alphanumeric.")
        if len(password) < 6:
            return render_template_string(AUTH_TEMPLATE, mode="register", error="Password must be at least 6 characters.")
        if users_col.find_one({"username": username}):
            return render_template_string(AUTH_TEMPLATE, mode="register", error="Username already exists.")
        users_col.insert_one({
            "username": username,
            "password_hash": hashlib.sha256(password.encode()).hexdigest(),
            "role": "user", "watchlist": []
        })
        session["user"] = {"username": username, "role": "user"}
        return redirect(url_for("home"))
    return render_template_string(AUTH_TEMPLATE, mode="register")

# লগআউট
@app.route("/logout")
def logout():
    session.pop("user", None)
    return redirect(url_for("home"))

# ওয়াচলিস্ট পেজ
@app.route("/watchlist")
@require_login()
def watchlist():
    user_data = users_col.find_one({"username": session["user"]["username"]})
    slugs = user_data.get("watchlist", [])
    movies = [m for s in slugs if (m := movies_col.find_one({"slug": s}))]
    return render_template_string(HOME_TEMPLATE, movies=movies, meta_title="My Watchlist")

# ওয়াচলিস্টে যোগ/বাদ দেওয়ার জন্য
@app.route("/watchlist/toggle/<slug>", methods=["POST"])
@require_login()
def toggle_watchlist(slug):
    user_data = users_col.find_one({"username": session["user"]["username"]})
    watchlist = set(user_data.get("watchlist", []))
    if slug in watchlist: watchlist.remove(slug)
    else: watchlist.add(slug)
    users_col.update_one({"_id": user_data["_id"]}, {"$set": {"watchlist": list(watchlist)}})
    return redirect(url_for("movie_details", slug=slug))

# অ্যাডমিন প্যানেল
@app.route("/admin")
@require_login("admin")
def admin():
    tmdb_enabled = bool(requests and os.getenv("TMDB_API_KEY"))
    return render_template_string(ADMIN_TEMPLATE, tmdb_enabled=tmdb_enabled)

# অ্যাডমিন: মুভি যোগ করা
@app.route("/admin/add", methods=["POST"])
@require_login("admin")
def admin_add():
    form = request.form
    try: links = json.loads(form.get("stream_links") or "[]")
    except: links = []
    doc = {
        "title": form.get("title").strip(),
        "year": int(form.get("year")) if form.get("year").isdigit() else None,
        "language": form.get("language"),
        "genres": [g.strip() for g in form.get("genres", "").split(",") if g.strip()],
        "poster_url": form.get("poster_url"), "trailer_url": form.get("trailer_url"),
        "description": form.get("description"), "stream_links": links
    }
    upsert_movie(doc)
    return redirect(url_for("admin"))

# অ্যাডমিন: TMDB থেকে ইম্পোর্ট
@app.route("/admin/tmdb", methods=["POST"])
@require_login("admin")
def admin_tmdb():
    api_key, tmdb_id = os.getenv("TMDB_API_KEY"), request.form.get("tmdb_id")
    if not (api_key and requests and tmdb_id): abort(400)
    try:
        res = requests.get(f"https://api.themoviedb.org/3/movie/{tmdb_id}?api_key={api_key}").json()
        year = (res.get("release_date") or "")[:4]
        doc = {
            "title": res.get("title"), "year": int(year) if year.isdigit() else None,
            "language": res.get("original_language", "").upper(),
            "genres": [g["name"] for g in res.get("genres", [])],
            "poster_url": f"https://image.tmdb.org/t/p/w500{res.get('poster_path')}" if res.get('poster_path') else "",
            "description": res.get("overview"), "rating": res.get("vote_average")
        }
        upsert_movie(doc)
    except Exception as e: print(f"TMDB Import Error: {e}")
    return redirect(url_for("admin"))

# এরর হ্যান্ডলার (404 Page Not Found)
@app.errorhandler(404)
def not_found(e): return "<h1>404 - Page Not Found</h1>", 404
@app.errorhandler(403)
def forbidden(e): return "<h1>403 - Access Forbidden</h1>", 403

# --------------------------
# ডেমো ডেটা (শুধুমাত্র ডেটাবেস ছাড়া চালানোর জন্য)
# --------------------------
if not USE_MONGO and not list(movies_col.find()):
    print("[INFO] Seeding initial sample data for demo purposes.")
    sample_movies = [
        {"title": "Inception", "year": 2010, "genres": ["Sci-Fi", "Action"], "description": "A thief who steals corporate secrets through the use of dream-sharing technology...", "poster_url": "https://image.tmdb.org/t/p/w500/oYuLEt3zVCKq27gApcjBJUuNXa6.jpg", "stream_links": [{"label": "HD", "url": "https://test-streams.mux.dev/x36xhzz/x36xhzz.m3u8"}], "rating": 8.8},
        {"title": "Interstellar", "year": 2014, "genres": ["Sci-Fi", "Adventure"], "description": "A team of explorers travel through a wormhole in space in an attempt to ensure humanity's survival.", "poster_url": "https://image.tmdb.org/t/p/w500/gEU2QniE6E77NI6lCU6MxlNBvIx.jpg", "rating": 8.6},
        {"title": "The Dark Knight", "year": 2008, "genres": ["Action", "Crime", "Drama"], "description": "When the menace known as the Joker wreaks havoc, Batman must face one of the greatest tests of his ability to fight injustice.", "poster_url": "https://image.tmdb.org/t/p/w500/qJ2tW6WMUDux911r6m7haRef0WH.jpg", "rating": 9.0},
    ]
    for movie in sample_movies: upsert_movie(movie)

# --------------------------
# অ্যাপ চালানোর জন্য এন্ট্রি পয়েন্ট
# --------------------------
if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    print(f"\n🚀 Movie website starting on http://127.0.0.1:{port}")
    print(f"🔑 Admin Login: {ADMIN_USERNAME} / {ADMIN_PASSWORD}")
    if not USE_MONGO: print("⚠️  Running in DEMO mode with temporary in-memory data.")
    app.run(host="0.0.0.0", port=port, debug=False) # Debug=False for production
