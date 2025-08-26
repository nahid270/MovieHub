import os
import time
import requests
from flask import (Flask, request, render_template_string, redirect, url_for, flash, Blueprint, session)
from pymongo import MongoClient, DESCENDING
from bson.objectid import ObjectId
from functools import wraps

# ==============================================================================
# ========= HTML TEMPLATES (Disney+ Clone Design) ============================
# ==============================================================================

PAGE_TEMPLATE = """<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8" /><meta name="viewport" content="width=device-width, initial-scale=1.0" /><title>{{ title or "Movie Zone - Disney+ Clone" }}</title><script src="https://cdn.tailwindcss.com"></script><link rel="icon" href="data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 100 100%22><text y=%22.9em%22 font-size=%2290%22>🎬</text></svg>"><link rel="shortcut icon" href="data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 100 100%22><text y=%22.9em%22 font-size=%2290%22>🎬</text></svg>"><style>body { background-color: #040714; color: #f9f9f9; }.brand-card {transition: all 0.3s ease;box-shadow: 0px 26px 30px -10px rgba(0, 0, 0, 0.69), 0px 16px 10px -10px rgba(0, 0, 0, 0.73);}.brand-card:hover {transform: scale(1.05);border-color: rgba(249, 249, 249, 0.8);box-shadow: 0px 40px 58px -16px rgba(0, 0, 0, 0.8), 0px 30px 22px -10px rgba(0, 0, 0, 0.72);}.poster-card { transition: all 0.3s ease; }.poster-card:hover { transform: scale(1.05); }</style></head><body class="overflow-x-hidden"><header class="sticky top-0 z-50 h-20 px-6 md:px-12 flex items-center justify-between bg-[#090b13]"><a href="{{ url_for('home') }}" class="text-2xl font-extrabold tracking-tight text-white uppercase">Movie<span class="text-blue-500">Zone</span></a><nav class="hidden md:flex items-center space-x-8"><a href="{{ url_for('home') }}" class="flex items-center space-x-2 text-sm uppercase font-semibold tracking-wider text-gray-300 hover:text-white"><svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5" viewBox="0 0 20 20" fill="currentColor"><path d="M10.707 2.293a1 1 0 00-1.414 0l-7 7a1 1 0 001.414 1.414L4 10.414V17a1 1 0 001 1h2a1 1 0 001-1v-2a1 1 0 011-1h2a1 1 0 011 1v2a1 1 0 001 1h2a1 1 0 001-1v-6.586l.293.293a1 1 0 001.414-1.414l-7-7z" /></svg><span>Home</span></a><a href="#search-section" onclick="event.preventDefault(); document.getElementById('search-input').focus();" class="flex items-center space-x-2 text-sm uppercase font-semibold tracking-wider text-gray-300 hover:text-white"><svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5" viewBox="0 0 20 20" fill="currentColor"><path fill-rule="evenodd" d="M8 4a4 4 0 100 8 4 4 0 000-8zM2 8a6 6 0 1110.89 3.476l4.817 4.817a1 1 0 01-1.414 1.414l-4.816-4.816A6 6 0 012 8z" clip-rule="evenodd" /></svg><span>Search</span></a></nav><div class="md:hidden"><form action="{{ url_for('search') }}" method="get"><input name="q" value="{{ query or '' }}" placeholder="Search..." class="bg-gray-800 text-white rounded-full px-4 py-1 text-sm outline-none w-32" /></form></div></header><main class="px-6 md:px-12 pt-6">{% if not query %}{% if banners and banners|length > 0 %}<section class="relative mb-8"><div class="rounded-lg overflow-hidden shadow-2xl"><img src="{{ banners[0].src }}" alt="{{ banners[0].title }}" class="w-full h-auto object-cover min-h-[250px] md:min-h-[450px]"><div class="absolute inset-0 bg-gradient-to-r from-[#040714] via-transparent to-transparent"></div></div><div class="absolute bottom-10 md:bottom-20 left-6 md:left-12 max-w-lg"><h1 class="text-3xl md:text-5xl font-bold drop-shadow-lg">{{ banners[0].title }}</h1><p class="text-sm md:text-base mt-4 line-clamp-3 text-gray-300 drop-shadow-md">{{ banners[0].overview }}</p></div></section>{% endif %}<section class="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-5 gap-6 mb-12"><div class="brand-card group bg-gray-900 border-2 border-gray-800 rounded-lg overflow-hidden cursor-pointer"><img src="https://www.logo.wine/a/logo/Disney%2B/Disney%2B-Logo.wine.svg" alt="Disney" class="w-full h-full object-contain p-2 invert"></div><div class="brand-card group bg-gray-900 border-2 border-gray-800 rounded-lg overflow-hidden cursor-pointer"><img src="https://www.logo.wine/a/logo/Pixar/Pixar-Logo.wine.svg" alt="Pixar" class="w-full h-full object-contain p-2 invert"></div><div class="brand-card group bg-gray-900 border-2 border-gray-800 rounded-lg overflow-hidden cursor-pointer"><img src="https://www.logo.wine/a/logo/Marvel_Comics/Marvel_Comics-Logo.wine.svg" alt="Marvel" class="w-full h-full object-contain p-2 invert"></div><div class="brand-card group bg-gray-900 border-2 border-gray-800 rounded-lg overflow-hidden cursor-pointer"><img src="https://www.logo.wine/a/logo/Star_Wars/Star_Wars-Logo.wine.svg" alt="Star Wars" class="w-full h-full object-contain p-2 invert"></div><div class="brand-card group bg-gray-900 border-2 border-gray-800 rounded-lg overflow-hidden cursor-pointer"><img src="https://www.logo.wine/a/logo/National_Geographic/National_Geographic-Logo.wine.svg" alt="Nat Geo" class="w-full h-full object-contain p-2 invert"></div></section>{% endif %}<section id="search-section"><h2 class="text-xl font-semibold tracking-wide mb-4">{% if query %}Results for “{{ query }}”{% else %}Recently Added{% endif %}</h2><div class="mb-8 hidden md:block"><form action="{{ url_for('search') }}" method="get" class="max-w-xl"><input id="search-input" name="q" value="{{ query or '' }}" placeholder="Search for movies..." class="w-full bg-gray-800/50 border border-gray-700 text-white rounded-full px-6 py-3 text-lg outline-none focus:ring-2 focus:ring-blue-500" /></form></div>{% if movies and movies|length > 0 %}<div class="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-6">{% for movie in movies %}<a href="https://www.themoviedb.org/movie/{{ movie.tmdb_id }}" target="_blank" rel="noopener" class="poster-card group rounded-lg overflow-hidden border-2 border-gray-800 hover:border-gray-400 shadow-lg"><img src="{{ movie.poster }}" alt="{{ movie.title }}" class="w-full h-auto object-cover aspect-[2/3]"></a>{% endfor %}</div>{% else %}<div class="text-center py-10 text-gray-400">{% if query %}No movies found for your search.{% else %}No movies added yet. Add some from the admin panel.{% endif %}</div>{% endif %}</section>{% if error_message %}<div class="mt-12 bg-red-900/50 border border-red-500/50 text-red-200 rounded-xl p-6 text-center"><h2 class="text-2xl font-bold mb-2">Configuration Problem!</h2><p class="font-mono text-sm">{{ error_message }}</p></div>{% endif %}</main><footer class="text-center text-xs text-gray-500 py-8 mt-12"><div>© {{ year }} Movie Zone • This is a clone project for educational purposes.</div></footer></body></html>"""
ADMIN_LOGIN_TEMPLATE = """<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"><title>Admin Login</title><script src="https://cdn.tailwindcss.com"></script><meta name="color-scheme" content="dark"></head><body class="bg-gray-950 text-gray-200 flex items-center justify-center min-h-screen"><div class="w-full max-w-md"><form method="POST" class="bg-gray-900 border border-white/10 shadow-lg rounded-2xl p-8 space-y-6"><h2 class="text-3xl font-bold text-center">Admin Login</h2>{% with messages = get_flashed_messages(with_categories=true) %}{% if messages %}{% for category, message in messages %}<div class="p-3 rounded-lg bg-red-500/20 text-red-300 text-sm">{{ message }}</div>{% endfor %}{% endif %}{% endwith %}<div><label for="username" class="block text-sm font-medium text-gray-400">Username</label><input type="text" name="username" id="username" required class="mt-1 block w-full bg-white/5 border border-white/10 rounded-lg px-3 py-2 outline-none focus:ring-2 focus:ring-blue-500"></div><div><label for="password" class="block text-sm font-medium text-gray-400">Password</label><input type="password" name="password" id="password" required class="mt-1 block w-full bg-white/5 border border-white/10 rounded-lg px-3 py-2 outline-none focus:ring-2 focus:ring-blue-500"></div><button type="submit" class="w-full bg-blue-600 hover:bg-blue-700 text-white font-bold py-2.5 px-4 rounded-lg transition">Login</button></form></div></body></html>"""
ADMIN_BASE_TEMPLATE = """<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"><title>{{ title or "Admin Panel" }} • Movie Zone</title><script src="https://cdn.tailwindcss.com"></script><meta name="color-scheme" content="dark"></head><body class="bg-gray-900 text-gray-200 antialiased"><div class="flex min-h-screen"><aside class="w-64 bg-gray-950 p-6 border-r border-white/10 flex flex-col"><h1 class="text-2xl font-bold mb-8">🎬 Admin Panel</h1><nav class="flex flex-col gap-2"><a href="{{ url_for('admin.dashboard') }}" class="px-4 py-2 rounded-lg hover:bg-white/10">Dashboard</a><a href="{{ url_for('admin.manage_movies') }}" class="px-4 py-2 rounded-lg hover:bg-white/10">Manage Movies</a><a href="{{ url_for('admin.manage_ads') }}" class="px-4 py-2 rounded-lg hover:bg-white/10">Manage Ads</a></nav><div class="mt-auto"><a href="{{ url_for('home') }}" target="_blank" class="block w-full text-center px-4 py-2 rounded-lg hover:bg-white/10 text-sm mb-2">View Site ↗</a><a href="{{ url_for('admin.logout') }}" class="block w-full text-center px-4 py-2 rounded-lg bg-red-600/50 hover:bg-red-600/80 text-sm">Logout</a></div></aside><main class="flex-1 p-8">{% with messages = get_flashed_messages(with_categories=true) %}{% if messages %}{% for category, message in messages %}<div class="mb-4 p-4 rounded-lg {% if category == 'success' %}bg-green-500/20 text-green-300 border border-green-500/30{% elif category == 'error' %}bg-red-500/20 text-red-300 border border-red-500/30{% else %}bg-blue-500/20 text-blue-300 border border-blue-500/30{% endif %}">{{ message }}</div>{% endfor %}{% endif %}{% endwith %}{{ content | safe }}</main></div></body></html>"""
ADMIN_DASHBOARD_CONTENT = """<h1 class="text-3xl font-bold mb-6">Dashboard</h1><div class="grid grid-cols-1 md:grid-cols-2 gap-6"><div class="bg-gray-950/50 p-6 rounded-xl border border-white/10"><h2 class="text-lg font-semibold text-gray-400">Total Movies on Site</h2><p class="text-5xl font-bold mt-2">{{ movie_count }}</p></div><div class="bg-gray-950/50 p-6 rounded-xl border border-white/10"><h2 class="text-lg font-semibold text-gray-400">Total Ads Configured</h2><p class="text-5xl font-bold mt-2">{{ ad_count }}</p></div></div>"""
ADMIN_MOVIES_CONTENT = """<h1 class="text-3xl font-bold mb-6">Manage Movies</h1><div class="bg-gray-950/50 p-6 rounded-xl border border-white/10 mb-8"><h2 class="text-xl font-bold mb-4">Add New Movie from TMDB</h2><form method="POST" class="flex gap-4"><input type="search" name="query" placeholder="Search on TMDB..." required class="flex-grow bg-white/5 border border-white/10 rounded-lg px-4 py-2 outline-none focus:ring-2 focus:ring-blue-500"><button type="submit" class="bg-blue-600 hover:bg-blue-700 text-white font-bold py-2 px-6 rounded-lg">Search</button></form>{% if tmdb_results %}<div class="mt-6"><h3 class="font-semibold mb-2">Search Results:</h3><div class="max-h-80 overflow-y-auto space-y-2 pr-2">{% for movie in tmdb_results %}<div class="flex items-center gap-4 p-2 bg-white/5 rounded-lg"><img src="{{ movie.poster }}" class="w-12 h-auto rounded-md"><div class="flex-grow"><p class="font-bold">{{ movie.title }}</p><p class="text-sm text-gray-400">{{ movie.year }}</p></div><form action="{{ url_for('admin.add_movie', tmdb_id=movie.tmdb_id) }}" method="POST"><button type="submit" class="bg-green-600 hover:bg-green-700 text-white text-sm font-bold py-1 px-3 rounded-md">+</button></form></div>{% endfor %}</div></div>{% endif %}</div><div class="bg-gray-950/50 p-6 rounded-xl border border-white/10"><div class="flex justify-between items-center mb-4"><h2 class="text-xl font-bold">Movies on Your Site ({{ site_movies|length }})</h2><form action="{{ url_for('admin.delete_all_movies') }}" method="POST" onsubmit="return confirm('Are you sure you want to delete ALL movies?');"><button type="submit" class="bg-red-800 hover:bg-red-700 text-white text-sm font-bold py-2 px-4 rounded-lg">Delete All</button></form></div><div class="overflow-x-auto"><table class="w-full text-left"><thead><tr class="border-b border-white/10"><th class="p-3">Poster</th><th class="p-3">Title</th><th class="p-3">Year</th><th class="p-3 text-right">Actions</th></tr></thead><tbody>{% for movie in site_movies %}<tr class="border-b border-white/5"><td class="p-2"><img src="{{ movie.poster }}" class="w-12 h-auto rounded-md"></td><td class="p-2 font-semibold">{{ movie.title }}</td><td class="p-2 text-gray-400">{{ movie.year }}</td><td class="p-2 text-right"><form action="{{ url_for('admin.delete_movie', movie_id=movie._id) }}" method="POST" class="inline"><button type="submit" class="text-red-400 hover:text-red-300 text-sm font-bold">Delete</button></form></td></tr>{% else %}<tr><td colspan="4" class="p-4 text-center text-gray-500">No movies found.</td></tr>{% endfor %}</tbody></table></div></div>"""
ADMIN_ADS_CONTENT = """<h1 class="text-3xl font-bold mb-6">Manage Advertisements</h1><div class="grid grid-cols-1 lg:grid-cols-3 gap-8"><div class="lg:col-span-1 bg-gray-950/50 p-6 rounded-xl border border-white/10"><h2 class="text-xl font-bold mb-4">Add / Edit Ad</h2><form method="POST" class="space-y-4"><input type="hidden" name="ad_id" value=""><div><label class="block text-sm font-medium text-gray-400">Ad Name</label><input type="text" name="name" required class="mt-1 w-full bg-white/5 border border-white/10 rounded-lg px-3 py-2"></div><div><label class="block text-sm font-medium text-gray-400">Position</label><select name="position" required class="mt-1 w-full bg-white/5 border border-white/10 rounded-lg px-3 py-2"><option value="header">Header</option><option value="footer">Footer</option></select></div><div><label class="block text-sm font-medium text-gray-400">HTML/JS Code</label><textarea name="html_code" rows="5" required class="mt-1 w-full bg-white/5 border border-white/10 rounded-lg px-3 py-2"></textarea></div><div class="flex items-center"><input type="checkbox" name="is_active" id="is_active" checked class="h-4 w-4 rounded bg-white/10 border-gray-600 text-blue-600 focus:ring-blue-600"><label for="is_active" class="ml-2 block text-sm text-gray-300">Active</label></div><button type="submit" class="w-full bg-blue-600 hover:bg-blue-700 text-white font-bold py-2.5 px-4 rounded-lg">Save Ad</button></form></div><div class="lg:col-span-2 bg-gray-950/50 p-6 rounded-xl border border-white/10"><h2 class="text-xl font-bold mb-4">Existing Ads</h2><div class="space-y-4">{% for ad in ads %}<div class="bg-white/5 p-4 rounded-lg"><div class="flex justify-between items-start"><div><h3 class="font-bold">{{ ad.name }} <span class="text-xs ml-2 px-2 py-0.5 rounded-full {{ 'bg-green-500/30 text-green-300' if ad.is_active else 'bg-red-500/30 text-red-300' }}">{{ 'Active' if ad.is_active else 'Inactive' }}</span></h3><p class="text-sm text-gray-400">Position: <span class="font-mono">{{ ad.position }}</span></p></div><form action="{{ url_for('admin.delete_ad', ad_id=ad._id) }}" method="POST" onsubmit="return confirm('Delete this ad?');"><button type="submit" class="text-red-400 hover:text-red-300 text-xs font-bold">Delete</button></form></div><div class="mt-2 text-xs bg-black/30 p-2 rounded-md font-mono max-w-md overflow-x-auto">{{ ad.html_code|e }}</div></div>{% else %}<p class="text-gray-500">No ads have been created yet.</p>{% endfor %}</div></div></div>"""

# =======================================================================
# ========= FLASK APPLICATION LOGIC (মূল পাইথন কোড) ===================
# =======================================================================

app = Flask(__name__)
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "a_very_secret_key_for_local_use")

# --- ADMIN CREDENTIALS (সরাসরি কোডে লেখা) ---
ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "password123"

# --- ENV CONFIG (Vercel থেকে এই ভেরিয়েবলগুলো সেট করতে হবে) ---
TMDB_API_KEY = os.getenv("TMDB_API_KEY")
MONGO_URI = os.getenv("MONGO_URI")

# --- TMDB CONFIG ---
TMDB_BASE_URL = "https://api.themoviedb.org/3"
IMG_POSTER = "https://image.tmdb.org/t/p/w500"
IMG_BANNER = "https://image.tmdb.org/t/p/w1280"

# --- DATABASE (MongoDB) with Error Handling and Explicit DB Name ---
client, db, movies_collection, ads_collection, DB_CONNECTION_ERROR = None, None, None, None, None
if MONGO_URI:
    try:
        client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
        client.admin.command('ping')
        print("MongoDB connection successful.")
        db = client["movie_db"]
        movies_collection = db.movies
        ads_collection = db.ads
    except Exception as e:
        DB_CONNECTION_ERROR = f"Database connection failed. Check URI/IP whitelist. Error: {e}"
        print(f"ERROR: Could not connect to MongoDB. Reason: {e}")
else:
    DB_CONNECTION_ERROR = "MONGO_URI environment variable is not set."

# --- LOGIN HELPER (Custom Decorator) ---
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'admin_logged_in' not in session:
            flash("You need to be logged in to access this page.", "error")
            return redirect(url_for('admin.login'))
        return f(*args, **kwargs)
    return decorated_function

# --- OTHER HELPERS ---
def tmdb_get(path, params=None):
    if not TMDB_API_KEY: return {"results": []}
    params = params or {}; params["api_key"] = TMDB_API_KEY
    try: r = requests.get(f"{TMDB_BASE_URL}{path}", params=params, timeout=10); r.raise_for_status(); return r.json()
    except requests.exceptions.RequestException: return {"results": []}

def search_tmdb_movies(q): return tmdb_get("/search/movie", params={"query": q, "include_adult": "false"}).get("results", []) if q else []
def get_tmdb_movie_details(tmdb_id): return tmdb_get(f"/movie/{tmdb_id}")
def map_movie_from_tmdb(m):
    return {"tmdb_id": m.get("id"),"title": m.get("title") or "Untitled","year": (m.get("release_date") or "")[:4] or "N/A","poster": f"{IMG_POSTER}{m.get('poster_path')}" if m.get('poster_path') else "https://via.placeholder.com/500x750?text=No+Image","backdrop": f"{IMG_BANNER}{m.get('backdrop_path')}" if m.get('backdrop_path') else None,"overview": m.get("overview") or ""}

@app.context_processor
def inject_globals(): return dict(year=time.strftime("%Y"))
def render_admin_page(content_template, **kwargs): return render_template_string(ADMIN_BASE_TEMPLATE, content=render_template_string(content_template, **kwargs), **kwargs)

# --- ADMIN BLUEPRINT ---
admin_bp = Blueprint('admin', __name__, url_prefix='/admin')

@admin_bp.route('/login', methods=['GET', 'POST'])
def login():
    if 'admin_logged_in' in session: return redirect(url_for('admin.dashboard'))
    if request.method == 'POST':
        if request.form.get('username') == ADMIN_USERNAME and request.form.get('password') == ADMIN_PASSWORD:
            session['admin_logged_in'] = True
            return redirect(url_for('admin.dashboard'))
        else:
            flash('Invalid username or password.', 'error')
    return render_template_string(ADMIN_LOGIN_TEMPLATE)

@admin_bp.route('/logout')
def logout():
    session.pop('admin_logged_in', None)
    flash('You have been logged out.', 'success')
    return redirect(url_for('admin.login'))

@admin_bp.route('/')
@login_required
def dashboard():
    movie_count = movies_collection.count_documents({}) if movies_collection else 0
    ad_count = ads_collection.count_documents({}) if ads_collection else 0
    return render_admin_page(ADMIN_DASHBOARD_CONTENT, title="Dashboard", movie_count=movie_count, ad_count=ad_count)

@admin_bp.route('/movies', methods=['GET', 'POST'])
@login_required
def manage_movies():
    tmdb_results = [map_movie_from_tmdb(m) for m in search_tmdb_movies(request.form.get('query'))] if request.method == 'POST' else []
    site_movies = list(movies_collection.find().sort('_id', DESCENDING)) if movies_collection else []
    return render_admin_page(ADMIN_MOVIES_CONTENT, title="Manage Movies", site_movies=site_movies, tmdb_results=tmdb_results)

@admin_bp.route('/movies/add/<int:tmdb_id>', methods=['POST'])
@login_required
def add_movie(tmdb_id):
    if movies_collection is not None:
        if movies_collection.find_one({"tmdb_id": tmdb_id}):
            flash('Movie already exists in the database.', 'warning')
        else:
            movie_details = get_tmdb_movie_details(tmdb_id)
            if movie_details:
                movies_collection.insert_one(map_movie_from_tmdb(movie_details))
                flash('Movie added successfully.', 'success')
            else:
                flash('Could not fetch movie details from TMDB.', 'error')
    else:
        flash('Database connection is not available.', 'error')
    return redirect(url_for('admin.manage_movies'))

@admin_bp.route('/movies/delete/<movie_id>', methods=['POST'])
@login_required
def delete_movie(movie_id):
    if movies_collection: movies_collection.delete_one({"_id": ObjectId(movie_id)}); flash('Movie deleted.', 'success')
    return redirect(url_for('admin.manage_movies'))

@admin_bp.route('/movies/delete_all', methods=['POST'])
@login_required
def delete_all_movies():
    if movies_collection: movies_collection.delete_many({}); flash('All movies deleted!', 'danger')
    return redirect(url_for('admin.manage_movies'))

@admin_bp.route('/ads', methods=['GET', 'POST'])
@login_required
def manage_ads():
    if request.method == 'POST' and ads_collection is not None:
        ads_collection.insert_one({ "name": request.form.get('name'), "position": request.form.get('position'), "html_code": request.form.get('html_code'), "is_active": 'is_active' in request.form })
        flash('Ad created.', 'success')
    elif request.method == 'POST':
        flash('Database connection is not available.', 'error')
    all_ads = list(ads_collection.find()) if ads_collection else []
    return render_admin_page(ADMIN_ADS_CONTENT, title="Manage Ads", ads=all_ads)

@admin_bp.route('/ads/delete/<ad_id>', methods=['POST'])
@login_required
def delete_ad(ad_id):
    if ads_collection: ads_collection.delete_one({"_id": ObjectId(ad_id)}); flash('Ad deleted.', 'success')
    return redirect(url_for('admin.manage_ads'))

app.register_blueprint(admin_bp)

# --- PUBLIC ROUTES ---
def pick_banners(movie_list, need=1):
    banners = [m for m in movie_list if m.get("backdrop")][:need]
    if not banners: banners.append({ "src": "https://via.placeholder.com/1280x720/040714/f9f9f9?text=Welcome+to+MovieZone", "title": "Welcome to Movie Zone", "overview": "Add movies from the admin panel to see them featured here."})
    return banners

@app.route("/")
def home():
    if DB_CONNECTION_ERROR: return render_template_string(PAGE_TEMPLATE, title="Config Error", error_message=DB_CONNECTION_ERROR)
    if not TMDB_API_KEY: return render_template_string(PAGE_TEMPLATE, title="Config Error", error_message="TMDB_API_KEY is not set.")
    movies = list(movies_collection.find().sort('_id', DESCENDING).limit(15)) if movies_collection else []
    return render_template_string(PAGE_TEMPLATE, title="Movie Zone", banners=pick_banners(movies), movies=movies)

@app.route("/search")
def search():
    if DB_CONNECTION_ERROR: return redirect(url_for("home"))
    q = (request.args.get("q") or "").strip()
    if not q: return redirect(url_for("home"))
    results = [map_movie_from_tmdb(m) for m in search_tmdb_movies(q)]
    return render_template_string(PAGE_TEMPLATE, title=f"Search • {q}", movies=results, query=q)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)), debug=True)
