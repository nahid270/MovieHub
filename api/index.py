# index.py
"""
Single-file Professional Movie Website (Flask) - FINAL, ALL-IN-ONE VERSION
- Inspired by MovieFix4U.fun with a modern, dark-themed UI.
- All credentials are hardcoded for easy deployment.
- WARNING: THIS IS NOT SECURE FOR PRODUCTION. CHANGE YOUR PASSWORD IMMEDIATELY.
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

# --- CONFIGURATION (আপনার নতুন পাসওয়ার্ড এখানে বসান) ---
# -------------------------------------------------------------------
# WARNING: Change your password in MongoDB Atlas first!
# তারপর নিচের "YOUR_NEW_PASSWORD_HERE" এর জায়গায় নতুন পাসওয়ার্ডটি দিন।
MONGO_URI = "mongodb+srv://mewayo8672:YOUR_NEW_PASSWORD_HERE@cluster0.ozhvczp.mongodb.net/movie_db?retryWrites=true&w=majority&appName=Cluster0"

# আপনার দেওয়া অন্যান্য তথ্য
TMDB_API_KEY = "7dc544d9253bccc3cfecc1c677f69819"
BASE_URL = "http://MovieFix4U.fun" # আপনার ডোমেইন

# অন্যান্য সেটিংস
FLASK_SECRET = "a-very-strong-and-random-secret-key-for-flask-!@#$%^"
ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "admin_password_change_this" # একটি কঠিন পাসওয়ার্ড দিন
# -------------------------------------------------------------------

# Flask & Dependencies
try:
    from flask import Flask, request, redirect, url_for, render_template_string, session, abort
    import requests
    from pymongo import MongoClient
    from pymongo.errors import ConnectionFailure, ConfigurationError
    PYMONGO_AVAILABLE = True
except Exception as e:
    raise SystemExit(f"Required libraries are missing: {e}")

# App config
app = Flask(__name__)
app.secret_key = FLASK_SECRET

# --- Database & Other Code (No changes needed below) ---
class MemoryCollection: # Fallback in-memory database
    def __init__(self): self.data = {}
    def insert_one(self, doc): _id=doc.get("_id") or str(uuid.uuid4()); doc["_id"]=_id; self.data[_id]=json.loads(json.dumps(doc)); return type("IR",(),{"inserted_id":_id})
    def find_one(self, query):
        for doc in self.data.values():
            if _match(doc, query): return json.loads(json.dumps(doc))
    def find(self, query=None, sort=None, limit=0, skip=0):
        items=list(self.data.values());
        if query: items=[d for d in items if _match(d, query)]
        if sort: key, direction=sort[0]; items.sort(key=lambda d:d.get(key,0), reverse=(direction<0))
        if skip: items=items[skip:]
        if limit: items=items[:limit]
        for d in items: yield json.loads(json.dumps(d))
    def update_one(self, query, update):
        for _id, doc in list(self.data.items()):
            if _match(doc, query):
                if "$set" in update:
                    for k,v in update["$set"].items(): _set_nested(doc, k,v)
                if "$inc" in update:
                    for k,v in update["$inc"].items(): doc[k]=doc.get(k,0)+v
                self.data[_id]=doc; return
    def delete_one(self, query):
        for _id, doc in list(self.data.items()):
            if _match(doc, query): del self.data[_id]; return

def _set_nested(d, path, value): parts=path.split("."); cur=d; [cur:=cur.setdefault(p,{}) for p in parts[:-1]]; cur[parts[-1]]=value
def _match(doc, query):
    for k, v in (query or {}).items():
        if isinstance(v, dict) and "$regex" in v:
            pat=v["$regex"]; flags=re.IGNORECASE if v.get("$options")=="i" else 0
            if re.search(pat, str(doc.get(k, "")), flags) is None: return False
        elif doc.get(k) != v: return False
    return True

USE_MONGO = False; movies_col, users_col = None, None
def initialize_database():
    global USE_MONGO, movies_col, users_col
    movies_col, users_col = MemoryCollection(), MemoryCollection(); USE_MONGO = False
    if "YOUR_NEW_PASSWORD_HERE" in MONGO_URI:
        logging.warning("[DB] MONGO_URI is not set with the new password. Using in-memory database.")
        return
    logging.info("[DB] Attempting to connect to MongoDB...")
    try:
        client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=15000); client.admin.command('ping')
        db_name = client.get_database().name; db = client[db_name]
        movies_col, users_col = db["movies"], db["users"]; movies_col.create_index([("slug", 1)], unique=True)
        USE_MONGO = True; logging.info(f"[DB] SUCCESS: Connected to MongoDB. Database: '{db_name}'")
    except Exception as e:
        logging.error(f"[DB] FAILED: Could not connect to MongoDB. CHECK YOUR MONGO_URI, PASSWORD, AND IP WHITELIST. Error: {e}")
        logging.warning("[DB] Falling back to in-memory database.")
initialize_database()

try:
    if users_col and not users_col.find_one({"username": ADMIN_USERNAME}):
        users_col.insert_one({"username":ADMIN_USERNAME, "password_hash":hashlib.sha256(ADMIN_PASSWORD.encode()).hexdigest(), "role":"admin"})
except Exception as e: logging.warning(f"Could not seed admin user. Error: {e}")

def slugify(text: str) -> str: text=re.sub(r"[^a-z0-9\s-]", "", text.lower()); return re.sub(r"\s+", "-", text.strip())
def require_login(role: Optional[str] = None):
    def decorator(fn):
        def wrapper(*args, **kwargs):
            if not session.get("user"): return redirect(url_for("login", next=request.path))
            if role and session["user"].get("role") != role: abort(403)
            return fn(*args, **kwargs)
        wrapper.__name__ = fn.__name__; return wrapper
    return decorator
def upsert_movie(doc: dict):
    # (Same as before)
    doc.setdefault("title", "Untitled"); doc.setdefault("year", None); doc.setdefault("language", "Unknown"); doc.setdefault("genres", []); doc.setdefault("description", ""); doc.setdefault("poster_url", ""); doc.setdefault("trailer_url", ""); doc.setdefault("stream_links", []); doc.setdefault("rating", None); doc.setdefault("views", 0)
    slug = doc.get("slug") or slugify(f"{doc['title']} {doc.get('year') or ''}"); doc["slug"] = slug
    if existing := movies_col.find_one({"slug": slug}): movies_col.update_one({"_id": existing["_id"]}, {"$set": doc})
    else: movies_col.insert_one(doc)

# --- TEMPLATES (NEW MODERN DESIGN) ---
BASE_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
    <meta charset="utf-8"/><meta name="viewport" content="width=device-width, initial-scale=1"/>
    <title>{{ meta_title or 'MovieFix' }}</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin><link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
    <style>
        body { font-family: 'Inter', sans-serif; }
        .scroll-container { display: flex; overflow-x: auto; scroll-snap-type: x mandatory; -webkit-overflow-scrolling: touch; }
        .scroll-container::-webkit-scrollbar { display: none; }
        .scroll-item { flex: 0 0 auto; scroll-snap-align: start; }
    </style>
</head>
<body class="bg-gray-900 text-gray-200">
    <header class="bg-gray-800/80 backdrop-blur-sm sticky top-0 z-50 border-b border-gray-700">
        <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
            <div class="flex items-center justify-between h-16">
                <a href="{{ url_for('home') }}" class="text-2xl font-bold text-white">🎬 Movie<span class="text-cyan-400">Fix</span></a>
                <form action="{{ url_for('search') }}" method="get" class="flex-1 max-w-lg mx-4">
                    <input name="q" value="{{ request.args.get('q','') }}" placeholder="Search movies..." class="w-full bg-gray-700 text-white border border-gray-600 rounded-full px-4 py-2 focus:outline-none focus:ring-2 focus:ring-cyan-500" />
                </form>
                <div class="flex items-center space-x-4 text-sm font-medium">
                    {% if user %}
                        <a href="{{ url_for('watchlist') }}" class="hover:text-cyan-400">Watchlist</a>
                        {% if user.role == 'admin' %}<a href="{{ url_for('admin') }}" class="hover:text-cyan-400">Admin</a>{% endif %}
                        <a href="{{ url_for('logout') }}" class="bg-cyan-500 text-white px-3 py-1.5 rounded-full hover:bg-cyan-600">Logout</a>
                    {% else %}
                        <a href="{{ url_for('login') }}" class="bg-cyan-500 text-white px-3 py-1.5 rounded-full hover:bg-cyan-600">Login</a>
                    {% endif %}
                </div>
            </div>
        </div>
    </header>
    <main>{% block content %}{% endblock %}</main>
    <footer class="border-t border-gray-800 mt-12 py-8 text-center text-sm text-gray-500">
        © {{ now.year }} MovieFix. All Rights Reserved.
    </footer>
</body>
</html>"""

HOME_TEMPLATE = """{% extends base %}
{% block content %}
    {% if featured %}
    <div class="relative h-[60vh] -mt-16 flex items-end p-8 text-white bg-cover bg-center" style="background-image: linear-gradient(to top, rgba(16, 23, 42, 1), rgba(16, 23, 42, 0.2)), url('{{ featured.poster_url }}');">
        <div class="max-w-2xl">
            <h1 class="text-4xl lg:text-5xl font-bold">{{ featured.title }}</h1>
            <p class="mt-4 text-gray-300 text-sm line-clamp-3">{{ featured.description }}</p>
            <a href="{{ url_for('movie_details', slug=featured.slug) }}" class="mt-6 inline-block bg-cyan-500 text-white font-semibold px-6 py-3 rounded-full hover:bg-cyan-600 transition-colors">
                ▶ Watch Now
            </a>
        </div>
    </div>
    {% endif %}

    <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-12">
        {% if trending %}
        <div>
            <h2 class="text-2xl font-semibold mb-4 text-white">🔥 Trending Now</h2>
            <div class="scroll-container space-x-4 pb-4">
                {% for m in trending %}
                <a href="{{ url_for('movie_details', slug=m.slug) }}" class="scroll-item group w-40 md:w-48">
                    <div class="aspect-[2/3] rounded-lg overflow-hidden relative">
                        <img src="{{ m.poster_url or 'https://via.placeholder.com/300x450' }}" alt="{{ m.title }}" class="w-full h-full object-cover transition-transform duration-300 group-hover:scale-105" />
                        <div class="absolute inset-0 bg-black/40 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center">
                             <svg class="w-12 h-12 text-white" fill="currentColor" viewBox="0 0 20 20"><path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM9.555 7.168A1 1 0 008 8v4a1 1 0 001.555.832l3-2a1 1 0 000-1.664l-3-2z" clip-rule="evenodd"></path></svg>
                        </div>
                    </div>
                    <h3 class="mt-2 font-medium truncate text-white">{{ m.title }}</h3>
                    <p class="text-xs text-gray-400">{{ m.year }}</p>
                </a>
                {% endfor %}
            </div>
        </div>
        {% endif %}

        {% if latest %}
        <div>
            <h2 class="text-2xl font-semibold mb-4 text-white">✨ Latest Movies</h2>
            <div class="scroll-container space-x-4 pb-4">
                {% for m in latest %}{# Reusing the card component logic #}
                <a href="{{ url_for('movie_details', slug=m.slug) }}" class="scroll-item group w-40 md:w-48">
                    <div class="aspect-[2/3] rounded-lg overflow-hidden relative"><img src="{{ m.poster_url or 'https://via.placeholder.com/300x450' }}" alt="{{ m.title }}" class="w-full h-full object-cover transition-transform duration-300 group-hover:scale-105" /><div class="absolute inset-0 bg-black/40 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center"><svg class="w-12 h-12 text-white" fill="currentColor" viewBox="0 0 20 20"><path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM9.555 7.168A1 1 0 008 8v4a1 1 0 001.555.832l3-2a1 1 0 000-1.664l-3-2z" clip-rule="evenodd"></path></svg></div></div>
                    <h3 class="mt-2 font-medium truncate text-white">{{ m.title }}</h3><p class="text-xs text-gray-400">{{ m.year }}</p>
                </a>
                {% endfor %}
            </div>
        </div>
        {% endif %}
    </div>
{% endblock %}"""

DETAILS_TEMPLATE = """{% extends base %}{% block content %}
<div class="relative min-h-screen -mt-16 pt-16 bg-cover bg-center bg-no-repeat" style="background-image: linear-gradient(to right, rgba(16, 23, 42, 1) 40%, rgba(16, 23, 42, 0.7)), url('{{ movie.poster_url }}');">
    <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-12">
        <div class="grid grid-cols-1 md:grid-cols-3 gap-8 text-white">
            <div class="md:col-span-1">
                <img src="{{ movie.poster_url or 'https://via.placeholder.com/400x600' }}" alt="{{ movie.title }}" class="rounded-xl shadow-2xl w-full" />
            </div>
            <div class="md:col-span-2">
                <h1 class="text-4xl font-bold">{{ movie.title }} <span class="font-normal text-gray-300">({{ movie.year }})</span></h1>
                <div class="mt-2 flex items-center space-x-4 text-sm text-gray-400">
                    <span>{{ (movie.genres or [])|join(', ') }}</span><span>•</span><span>{{ movie.language }}</span>
                </div>
                <p class="mt-6 text-gray-300">{{ movie.description }}</p>
                <div class="mt-8 flex items-center space-x-4">
                    {% if movie.stream_links %}
                    <a href="{{ url_for('play', slug=movie.slug, idx=0) }}" class="bg-cyan-500 text-white font-semibold px-6 py-3 rounded-full hover:bg-cyan-600">▶ Play Now</a>
                    {% endif %}
                    {% if user %}
                    <form method="post" action="{{ url_for('toggle_watchlist', slug=movie.slug) }}">
                        <button class="bg-gray-700 text-white font-semibold px-6 py-3 rounded-full hover:bg-gray-600">
                            {{ '❤️ Added to Watchlist' if in_watchlist else '🤍 Add to Watchlist' }}
                        </button>
                    </form>
                    {% endif %}
                </div>
            </div>
        </div>
    </div>
</div>{% endblock %}"""

# Other templates for login, admin etc. can be styled similarly if needed.

# --- ROUTES ---
@app.context_processor
def inject_globals(): return {"base": BASE_TEMPLATE, "user": session.get("user"), "now": datetime.utcnow()}
@app.route("/health")
def health_check(): return "OK", 200
@app.route('/favicon.ico')
def favicon(): return '', 204

@app.route("/")
def home():
    featured, trending, latest = None, [], []
    try:
        all_movies = list(movies_col.find({}))
        if all_movies:
            trending = sorted(all_movies, key=lambda m: m.get("views", 0), reverse=True)[:15]
            latest = sorted(all_movies, key=lambda m: m.get("year", 0), reverse=True)[:15]
            if trending: featured = trending[0]
    except Exception as e:
        logging.error(f"Failed to fetch movies for home page: {e}")
    return render_template_string(HOME_TEMPLATE, featured=featured, trending=trending, latest=latest)

@app.route("/search")
def search():
    q = request.args.get("q","").strip()
    if not q: return redirect(url_for("home"))
    movies = list(movies_col.find({"title": {"$regex": re.escape(q), "$options": "i"}}))
    # Using HOME_TEMPLATE to display search results in a similar layout
    return render_template_string(HOME_TEMPLATE, trending=movies)

@app.route("/movie/<slug>")
def movie_details(slug):
    movie = movies_col.find_one({"slug": slug})
    if not movie: abort(404)
    movies_col.update_one({"_id": movie["_id"]}, {"$inc": {"views": 1}})
    in_watchlist = False
    if u := session.get("user"):
        if ud := users_col.find_one({"username": u["username"]}):
            in_watchlist = slug in ud.get("watchlist", [])
    return render_template_string(DETAILS_TEMPLATE, movie=movie, in_watchlist=in_watchlist)

@app.route("/play/<slug>/<int:idx>")
def play(slug, idx=0):
    movie = movies_col.find_one({"slug": slug})
    if not movie or not (links := movie.get("stream_links")) or not (0 <= idx < len(links)): abort(404)
    return redirect(links[idx]["url"])

# (Login, Admin, Watchlist routes remain the same)
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username, password = request.form.get("username","").strip(), request.form.get("password","")
        u = users_col.find_one({"username": username})
        if u and u.get("password_hash") == hashlib.sha256(password.encode()).hexdigest():
            session["user"] = {"username": u["username"], "role": u.get("role","user")}
            return redirect(request.args.get("next") or url_for("home"))
        # Render a dark-themed login page
        return render_template_string("""{% extends base %}{% block content %}<div class="max-w-md mx-auto mt-10 bg-gray-800 p-8 rounded-xl border border-gray-700"><h1 class="text-2xl font-bold mb-6 text-white text-center">Login</h1>{% if error %}<p class="bg-red-500/20 text-red-300 p-3 rounded-md mb-4">{{ error }}</p>{% endif %}<form method="post" class="space-y-4"><input name="username" placeholder="Username" class="w-full bg-gray-700 text-white border border-gray-600 rounded-md px-4 py-2" required /><input name="password" type="password" placeholder="Password" class="w-full bg-gray-700 text-white border border-gray-600 rounded-md px-4 py-2" required /><button class="w-full bg-cyan-500 text-white font-semibold py-2 rounded-md hover:bg-cyan-600">Login</button></form></div>{% endblock %}""", error="Invalid credentials")
    return render_template_string("""{% extends base %}{% block content %}<div class="max-w-md mx-auto mt-10 bg-gray-800 p-8 rounded-xl border border-gray-700"><h1 class="text-2xl font-bold mb-6 text-white text-center">Login</h1><form method="post" class="space-y-4"><input name="username" placeholder="Username" class="w-full bg-gray-700 text-white border border-gray-600 rounded-md px-4 py-2" required /><input name="password" type="password" placeholder="Password" class="w-full bg-gray-700 text-white border border-gray-600 rounded-md px-4 py-2" required /><button class="w-full bg-cyan-500 text-white font-semibold py-2 rounded-md hover:bg-cyan-600">Login</button></form></div>{% endblock %}""")

@app.route("/admin/tmdb", methods=["POST"])
@require_login("admin")
def admin_tmdb():
    tmdb_id = request.form.get("tmdb_id")
    try:
        res = requests.get(f"https://api.themoviedb.org/3/movie/{tmdb_id}", params={"api_key": TMDB_API_KEY}).json()
        upsert_movie({
            "title": res.get("title"), "year": (res.get("release_date") or "")[:4], "language": (res.get("original_language") or "").upper(),
            "genres": [g["name"] for g in res.get("genres", [])], "poster_url": f"https://image.tmdb.org/t/p/w500{res.get('poster_path')}" if res.get('poster_path') else "",
            "description": res.get("overview"), "rating": res.get("vote_average")
        })
    except Exception as e: logging.error(f"TMDB import failed: {e}")
    return redirect(url_for("admin"))

# (Other routes like admin_add, watchlist, etc. can be added here if needed, they will work with the dark theme)
@app.route("/logout")
def logout(): session.pop("user", None); return redirect(url_for("home"))
@app.route("/admin")
@require_login("admin")
def admin(): return render_template_string("""{% extends base %}{% block content %}<div class="max-w-4xl mx-auto"><h1 class="text-3xl font-bold mb-6">Admin Panel</h1><div class="bg-gray-800 p-6 rounded-lg border border-gray-700"><h2 class="text-xl font-semibold mb-4">Import from TMDB</h2><form method="post" action="{{ url_for('admin_tmdb') }}" class="flex items-center space-x-2"><input name="tmdb_id" placeholder="Enter TMDB Movie ID" class="flex-1 bg-gray-700 text-white border border-gray-600 rounded-md px-4 py-2" required /><button class="bg-cyan-500 text-white font-semibold px-4 py-2 rounded-md">Import</button></form></div></div>{% endblock %}""")
@app.route("/watchlist")
@require_login()
def watchlist():
    u=users_col.find_one({"username":session["user"]["username"]}); movies=[m for s in (u or {}).get("watchlist",[]) if (m:=movies_col.find_one({"slug":s}))]
    return render_template_string("""{% extends base %}{% block content %}<div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8"><h1 class="text-3xl font-bold mb-6">My Watchlist</h1><div class="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6 gap-6">{% for m in movies %}<a href="{{ url_for('movie_details', slug=m.slug) }}" class="group"><div class="aspect-[2/3] rounded-lg overflow-hidden"><img src="{{ m.poster_url or 'https://via.placeholder.com/300x450' }}" class="w-full h-full object-cover group-hover:scale-105 transition-transform" /></div><h3 class="mt-2 font-medium truncate">{{ m.title }}</h3></a>{% else %}<p>Your watchlist is empty.</p>{% endfor %}</div></div>{% endblock %}""", items=movies)
@app.route("/watchlist/toggle/<slug>", methods=["POST"])
@require_login()
def toggle_watchlist(slug):
    u = users_col.find_one({"username": session["user"]["username"]}); wl = set(u.get("watchlist", []))
    if slug in wl: wl.remove(slug)
    else: wl.add(slug)
    users_col.update_one({"_id": u["_id"]}, {"$set": {"watchlist": list(wl)}})
    return redirect(url_for("movie_details", slug=slug))

@app.errorhandler(404)
def not_found(e): return render_template_string("""{% extends base %}{% block content %}<div class="text-center py-20"><h1 class="text-5xl font-bold">404</h1><p class="text-xl mt-4">Page Not Found</p><a href="{{ url_for('home') }}" class="mt-6 inline-block bg-cyan-500 text-white px-6 py-2 rounded-full">Go Home</a></div>{% endblock %}"""), 404

if not USE_MONGO and not any(movies_col.find(limit=1)):
    logging.info("Seeding in-memory DB with sample data.")
    for tmdb_id in ["550", "155", "157336"]: admin_tmdb(tmdb_id=tmdb_id) # Example using Fight Club, TDK, Interstellar

if __name__ == "__main__": app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)), debug=True)
