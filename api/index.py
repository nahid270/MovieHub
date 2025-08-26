import os
import time
import requests
from flask import (Flask, request, render_template_string, redirect, url_for, flash, Blueprint, session)
from pymongo import MongoClient, DESCENDING
from bson.objectid import ObjectId
from functools import wraps

# ==============================================================================
# ========= HTML TEMPLATES (অপরিবর্তিত) =======================================
# ==============================================================================
PAGE_TEMPLATE = """<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8" /><meta name="viewport" content="width=device-width, initial-scale=1.0" /><title>{{ title or "Movie Zone - Disney+ Clone" }}</title><script src="https://cdn.tailwindcss.com"></script><link rel="icon" href="data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 100 100%22><text y=%22.9em%22 font-size=%2290%22>🎬</text></svg>"><link rel="shortcut icon" href="data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 100 100%22><text y=%22.9em%22 font-size=%2290%22>🎬</text></svg>"><style>body { background-color: #040714; color: #f9f9f9; }.brand-card {transition: all 0.3s ease;box-shadow: 0px 26px 30px -10px rgba(0, 0, 0, 0.69), 0px 16px 10px -10px rgba(0, 0, 0, 0.73);}.brand-card:hover {transform: scale(1.05);border-color: rgba(249, 249, 249, 0.8);box-shadow: 0px 40px 58px -16px rgba(0, 0, 0, 0.8), 0px 30px 22px -10px rgba(0, 0, 0, 0.72);}.poster-card { transition: all 0.3s ease; }.poster-card:hover { transform: scale(1.05); }</style></head><body class="overflow-x-hidden"><header class="sticky top-0 z-50 h-20 px-6 md:px-12 flex items-center justify-between bg-[#090b13]"><a href="{{ url_for('home') }}" class="text-2xl font-extrabold tracking-tight text-white uppercase">Movie<span class="text-blue-500">Zone</span></a><nav class="hidden md:flex items-center space-x-8"><a href="{{ url_for('home') }}" class="flex items-center space-x-2 text-sm uppercase font-semibold tracking-wider text-gray-300 hover:text-white"><svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5" viewBox="0 0 20 20" fill="currentColor"><path d="M10.707 2.293a1 1 0 00-1.414 0l-7 7a1 1 0 001.414 1.414L4 10.414V17a1 1 0 001 1h2a1 1 0 001-1v-2a1 1 0 011-1h2a1 1 0 011 1v2a1 1 0 001 1h2a1 1 0 001-1v-6.586l.293.293a1 1 0 001.414-1.414l-7-7z" /></svg><span>Home</span></a><a href="#search-section" onclick="event.preventDefault(); document.getElementById('search-input').focus();" class="flex items-center space-x-2 text-sm uppercase font-semibold tracking-wider text-gray-300 hover:text-white"><svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5" viewBox="0 0 20 20" fill="currentColor"><path fill-rule="evenodd" d="M8 4a4 4 0 100 8 4 4 0 000-8zM2 8a6 6 0 1110.89 3.476l4.817 4.817a1 1 0 01-1.414 1.414l-4.816-4.816A6 6 0 012 8z" clip-rule="evenodd" /></svg><span>Search</span></a></nav><div class="md:hidden"><form action="{{ url_for('search') }}" method="get"><input name="q" value="{{ query or '' }}" placeholder="Search..." class="bg-gray-800 text-white rounded-full px-4 py-1 text-sm outline-none w-32" /></form></div></header><main class="px-6 md:px-12 pt-6">{% if not query %}{% if banners and banners|length > 0 %}<section class="relative mb-8"><div class="rounded-lg overflow-hidden shadow-2xl"><img src="{{ banners[0].src }}" alt="{{ banners[0].title }}" class="w-full h-auto object-cover min-h-[250px] md:min-h-[450px]"><div class="absolute inset-0 bg-gradient-to-r from-[#040714] via-transparent to-transparent"></div></div><div class="absolute bottom-10 md:bottom-20 left-6 md:left-12 max-w-lg"><h1 class="text-3xl md:text-5xl font-bold drop-shadow-lg">{{ banners[0].title }}</h1><p class="text-sm md:text-base mt-4 line-clamp-3 text-gray-300 drop-shadow-md">{{ banners[0].overview }}</p></div></section>{% endif %}{% endif %}<section id="search-section"><h2 class="text-xl font-semibold tracking-wide mb-4">{% if query %}Results for “{{ query }}”{% else %}Recently Added{% endif %}</h2><div class="mb-8 hidden md:block"><form action="{{ url_for('search') }}" method="get" class="max-w-xl"><input id="search-input" name="q" value="{{ query or '' }}" placeholder="Search for movies..." class="w-full bg-gray-800/50 border border-gray-700 text-white rounded-full px-6 py-3 text-lg outline-none focus:ring-2 focus:ring-blue-500" /></form></div>{% if movies and movies|length > 0 %}<div class="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-6">{% for movie in movies %}<a href="{{ url_for('movie_detail', movie_id=movie._id) }}" class="poster-card group rounded-lg overflow-hidden border-2 border-gray-800 hover:border-gray-400 shadow-lg"><img src="{{ movie.poster }}" alt="{{ movie.title }}" class="w-full h-auto object-cover aspect-[2/3]"></a>{% endfor %}</div>{% else %}<div class="text-center py-10 text-gray-400">{% if query %}No movies found for your search.{% else %}No movies added yet. Add some from the admin panel.{% endif %}</div>{% endif %}</section>{% if error_message %}<div class="mt-12 bg-red-900/50 border-red-500/50 text-red-200 rounded-xl p-6 text-center"><h2 class="text-2xl font-bold mb-2">Application Error!</h2><p class="font-mono text-sm">{{ error_message }}</p></div>{% endif %}</main><footer class="text-center text-xs text-gray-500 py-8 mt-12"><div>© {{ year }} Movie Zone • This is a clone project for educational purposes.</div></footer></body></html>"""
MOVIE_DETAIL_TEMPLATE = """<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8" /><meta name="viewport" content="width=device-width, initial-scale=1.0" /><title>{{ movie.title }} • Movie Zone</title><script src="https://cdn.tailwindcss.com"></script><link rel="icon" href="data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 100 100%22><text y=%22.9em%22 font-size=%2290%22>🎬</text></svg>"><style>body { background-color: #040714; color: #f9f9f9; }</style></head><body><div class="relative min-h-screen"><div class="absolute inset-0 z-0"><img src="{{ movie.backdrop or movie.poster }}" alt="{{ movie.title }}" class="w-full h-full object-cover opacity-20"></div><div class="absolute inset-0 z-10 bg-gradient-to-t from-[#040714] via-[#040714]/80 to-transparent"></div><main class="relative z-20 max-w-5xl mx-auto px-6 py-12 pt-24"><a href="{{ url_for('home') }}" class="text-sm text-gray-400 hover:text-white mb-8 inline-block">&larr; Back to Home</a><div class="md:flex md:space-x-8"><div class="md:w-1/3 flex-shrink-0"><img src="{{ movie.poster }}" alt="{{ movie.title }}" class="rounded-lg shadow-2xl w-full"></div><div class="md:w-2/3 mt-8 md:mt-0"><h1 class="text-4xl md:text-5xl font-bold">{{ movie.title }} ({{ movie.year }})</h1><p class="text-gray-300 mt-4 text-lg">{{ movie.overview }}</p><div class="mt-8 flex flex-wrap gap-4">{% if movie.watch_link %}<a href="{{ movie.watch_link }}" target="_blank" rel="noopener" class="bg-blue-600 hover:bg-blue-700 text-white font-bold py-3 px-8 rounded-lg text-lg transition">▶ Watch Now</a>{% else %}<button class="bg-gray-600 text-white font-bold py-3 px-8 rounded-lg text-lg cursor-not-allowed" disabled>Watch Link Not Available</button>{% endif %}{% if movie.download_link %}<a href="{{ movie.download_link }}" target="_blank" rel="noopener" class="bg-gray-700 hover:bg-gray-600 text-white font-bold py-3 px-8 rounded-lg text-lg transition">⬇ Download</a>{% else %}<button class="bg-gray-800 text-white font-bold py-3 px-8 rounded-lg text-lg cursor-not-allowed" disabled>Download Link Not Available</button>{% endif %}</div></div></div></main></div></body></html>"""
ADMIN_LOGIN_TEMPLATE = """... (অপরিবর্তিত) ..."""
ADMIN_BASE_TEMPLATE = """... (অপরিবর্তিত) ..."""
ADMIN_DASHBOARD_CONTENT = """... (অপরিবর্তিত) ..."""
ADMIN_MOVIES_CONTENT = """... (অপরিবর্তিত) ..."""
ADMIN_EDIT_MOVIE_TEMPLATE = """<h1 class="text-3xl font-bold mb-2">Edit Movie Links</h1><p class="text-gray-400 mb-6">Editing links for: <strong class="text-white">{{ movie.title }}</strong></p><form method="POST" class="max-w-xl mx-auto bg-gray-950/50 p-8 rounded-xl border border-white/10 space-y-6"><div><label for="watch_link" class="block text-sm font-medium text-gray-300 mb-1">Watch/Streaming Link</label><input type="url" name="watch_link" id="watch_link" value="{{ movie.watch_link or '' }}" placeholder="https://..." class="w-full bg-white/5 border border-white/10 rounded-lg px-4 py-2 outline-none focus:ring-2 focus:ring-blue-500"></div><div><label for="download_link" class="block text-sm font-medium text-gray-300 mb-1">Download Link</label><input type="url" name="download_link" id="download_link" value="{{ movie.download_link or '' }}" placeholder="https://..." class="w-full bg-white/5 border border-white/10 rounded-lg px-4 py-2 outline-none focus:ring-2 focus:ring-blue-500"></div><div class="flex justify-end gap-4 pt-4"><a href="{{ url_for('admin.manage_movies') }}" class="bg-gray-600 hover:bg-gray-700 text-white font-bold py-2 px-6 rounded-lg">Cancel</a><button type="submit" class="bg-blue-600 hover:bg-blue-700 text-white font-bold py-2 px-6 rounded-lg">Save Links</button></div></form>"""
ADMIN_ADS_CONTENT = """... (অপরিবর্তিত) ..."""

# =======================================================================
# ========= FLASK APPLICATION LOGIC (মূল পাইথন কোড) ===================
# =======================================================================

app = Flask(__name__)
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "a_very_secret_key_for_local_use")

ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "password123"
TMDB_API_KEY = os.getenv("TMDB_API_KEY")
MONGO_URI = os.getenv("MONGO_URI")

TMDB_BASE_URL = "https://api.themoviedb.org/3"
IMG_POSTER = "https://image.tmdb.org/t/p/w500"
IMG_BANNER = "https://image.tmdb.org/t/p/w1280"

client, db, movies_collection, DB_CONNECTION_ERROR = None, None, None, None
if MONGO_URI:
    try:
        client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
        client.admin.command('ping')
        print("MongoDB connection successful.")
        db = client["movie_db"]
        movies_collection = db.movies
    except Exception as e:
        DB_CONNECTION_ERROR = f"Database connection failed. Check URI/IP whitelist. Error: {e}"
        print(f"ERROR: Could not connect to MongoDB. Reason: {e}")
else:
    DB_CONNECTION_ERROR = "MONGO_URI environment variable is not set."

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'admin_logged_in' not in session: return redirect(url_for('admin.login'))
        return f(*args, **kwargs)
    return decorated_function

def tmdb_get(path, params=None):
    if not TMDB_API_KEY: return {}
    params = params or {}; params["api_key"] = TMDB_API_KEY
    try: r = requests.get(f"{TMDB_BASE_URL}{path}", params=params, timeout=10); r.raise_for_status(); return r.json()
    except: return {}

def search_tmdb_movies(q): return tmdb_get("/search/movie", params={"query": q, "include_adult": "false"}).get("results", []) if q else []
def get_tmdb_movie_details(tmdb_id): return tmdb_get(f"/movie/{tmdb_id}")
def map_movie_from_tmdb(m):
    return {"tmdb_id": m.get("id"), "title": m.get("title") or "Untitled", "year": (m.get("release_date") or "")[:4] or "N/A", "poster": f"{IMG_POSTER}{m.get('poster_path')}" if m.get('poster_path') else "https://via.placeholder.com/500x750?text=No+Image", "backdrop": f"{IMG_BANNER}{m.get('backdrop_path')}" if m.get('backdrop_path') else None, "overview": m.get("overview") or "", "watch_link": "", "download_link": ""}

@app.context_processor
def inject_globals(): return dict(year=time.strftime("%Y"))
def render_admin_page(content_template, **kwargs): return render_template_string(ADMIN_BASE_TEMPLATE, content=render_template_string(content_template, **kwargs), **kwargs)

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')

@admin_bp.route('/login', methods=['GET', 'POST'])
def login():
    if 'admin_logged_in' in session: return redirect(url_for('admin.dashboard'))
    if request.method == 'POST':
        if request.form.get('username') == ADMIN_USERNAME and request.form.get('password') == ADMIN_PASSWORD:
            session['admin_logged_in'] = True
            return redirect(url_for('admin.dashboard'))
        flash('Invalid username or password.', 'error')
    return render_template_string(ADMIN_LOGIN_TEMPLATE)

@admin_bp.route('/logout')
def logout():
    session.pop('admin_logged_in', None)
    return redirect(url_for('admin.login'))

@admin_bp.route('/')
@login_required
def dashboard():
    movie_count = movies_collection.count_documents({}) if movies_collection is not None else 0
    return render_admin_page(ADMIN_DASHBOARD_CONTENT, title="Dashboard", movie_count=movie_count)

@admin_bp.route('/movies', methods=['GET', 'POST'])
@login_required
def manage_movies():
    tmdb_results = [map_movie_from_tmdb(m) for m in search_tmdb_movies(request.form.get('query'))] if request.method == 'POST' else []
    site_movies = list(movies_collection.find().sort('_id', DESCENDING)) if movies_collection is not None else []
    return render_admin_page(ADMIN_MOVIES_CONTENT, title="Manage Movies", site_movies=site_movies, tmdb_results=tmdb_results)

# --- START: add_movie ফাংশনে পরিবর্তন ---
@admin_bp.route('/movies/add/<int:tmdb_id>', methods=['POST'])
@login_required
def add_movie(tmdb_id):
    if movies_collection is None:
        flash('Database connection is not available.', 'error')
        return redirect(url_for('admin.manage_movies'))
    
    try:
        if movies_collection.find_one({"tmdb_id": tmdb_id}):
            flash('Movie already exists in the database.', 'warning')
        else:
            movie_details = get_tmdb_movie_details(tmdb_id)
            if movie_details:
                movies_collection.insert_one(map_movie_from_tmdb(movie_details))
                flash('Movie added successfully!', 'success')
            else:
                flash('Could not fetch movie details from TMDB.', 'error')
    except Exception as e:
        print(f"ERROR during movie insertion: {e}")
        flash(f"Failed to add movie. A database error occurred. Check user permissions. Error: {e}", 'error')
        
    return redirect(url_for('admin.manage_movies'))
# --- END: add_movie ফাংশনে পরিবর্তন ---

@admin_bp.route('/movies/edit/<movie_id>', methods=['GET', 'POST'])
@login_required
def edit_movie(movie_id):
    if movies_collection is None: return redirect(url_for('admin.manage_movies'))
    movie = movies_collection.find_one({"_id": ObjectId(movie_id)})
    if not movie: flash('Movie not found.', 'error'); return redirect(url_for('admin.manage_movies'))
    
    if request.method == 'POST':
        watch_link = request.form.get('watch_link', '').strip()
        download_link = request.form.get('download_link', '').strip()
        movies_collection.update_one({"_id": ObjectId(movie_id)}, {"$set": {"watch_link": watch_link, "download_link": download_link}})
        flash('Movie links updated successfully.', 'success')
        return redirect(url_for('admin.manage_movies'))
        
    return render_admin_page(ADMIN_EDIT_MOVIE_TEMPLATE, title="Edit Movie", movie=movie)

@admin_bp.route('/movies/delete/<movie_id>', methods=['POST'])
@login_required
def delete_movie(movie_id):
    if movies_collection is not None: movies_collection.delete_one({"_id": ObjectId(movie_id)}); flash('Movie deleted.', 'success')
    return redirect(url_for('admin.manage_movies'))

@admin_bp.route('/movies/delete_all', methods=['POST'])
@login_required
def delete_all_movies():
    if movies_collection is not None: movies_collection.delete_many({}); flash('All movies deleted!', 'danger')
    return redirect(url_for('admin.manage_movies'))

app.register_blueprint(admin_bp)

def pick_banners(movie_list, need=1):
    banners = [m for m in movie_list if m.get("backdrop")][:need]
    if not banners: banners.append({ "src": "https://via.placeholder.com/1280x720/040714/f9f9f9?text=Welcome+to+MovieZone", "title": "Welcome to Movie Zone", "overview": "Add movies from the admin panel."})
    return banners

@app.route("/")
def home():
    if DB_CONNECTION_ERROR: return render_template_string(PAGE_TEMPLATE, error_message=DB_CONNECTION_ERROR)
    movies = []
    try:
        if movies_collection is not None: movies = list(movies_collection.find().sort('_id', DESCENDING).limit(15))
    except Exception as e:
        return render_template_string(PAGE_TEMPLATE, error_message=f"Could not fetch movies. Error: {e}")
    return render_template_string(PAGE_TEMPLATE, title="Movie Zone", banners=pick_banners(movies), movies=movies)

@app.route("/movie/<movie_id>")
def movie_detail(movie_id):
    if DB_CONNECTION_ERROR: return redirect(url_for("home"))
    movie = movies_collection.find_one({"_id": ObjectId(movie_id)}) if movies_collection is not None else None
    if not movie: return "Movie not found", 404
    return render_template_string(MOVIE_DETAIL_TEMPLATE, movie=movie)

@app.route("/search")
def search():
    if DB_CONNECTION_ERROR: return redirect(url_for("home"))
    q = (request.args.get("q") or "").strip()
    if not q: return redirect(url_for("home"))
    results = [map_movie_from_tmdb(m) for m in search_tmdb_movies(q)]
    return render_template_string(PAGE_TEMPLATE, title=f"Search • {q}", movies=results, query=q)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)), debug=True)
