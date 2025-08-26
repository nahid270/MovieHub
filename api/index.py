import os
import time
import requests
from flask import (Flask, request, render_template_string, redirect, url_for, flash, Blueprint)
from pymongo import MongoClient, DESCENDING
from bson.objectid import ObjectId
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import (LoginManager, UserMixin, login_user, logout_user, login_required, current_user)

# ==============================================================================
# ========= HTML TEMPLATES (সমস্ত HTML কোড এখানে স্ট্রিং হিসেবে রাখা হয়েছে) =========
# ==============================================================================

# --- সাধারণ ব্যবহারকারীদের জন্য মূল সাইটের টেমপ্লেট ---
PAGE_TEMPLATE = """
<!DOCTYPE html>
<html lang="bn">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width,initial-scale=1" />
  <title>{{ title or "Movie Zone" }}</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <meta name="color-scheme" content="dark light" />
</head>
<body class="bg-gray-950 text-gray-100">
  {% if ads.header %}<div class="header-ad text-center py-2 bg-gray-900">{{ ads.header | safe }}</div>{% endif %}
  <header class="sticky top-0 z-50 border-b border-white/10 bg-black/50 backdrop-blur">
    <div class="max-w-7xl mx-auto px-4 py-3 flex items-center gap-3">
      <a href="{{ url_for('home') }}" class="text-xl font-extrabold tracking-tight">🎬 Movie Zone</a>
      <form action="{{ url_for('search') }}" method="get" class="ml-auto w-full max-w-md">
        <label class="relative block">
          <input name="q" value="{{ query or '' }}" placeholder="Search for new movies..."
                 class="w-full bg-white/5 border border-white/10 rounded-xl py-2.5 pl-10 pr-3 outline-none focus:ring-2 focus:ring-white/20" />
          <span class="absolute left-3 top-2.5 opacity-70">🔎</span>
        </label>
      </form>
    </div>
  </header>

  <main class="max-w-7xl mx-auto px-4 py-6">
    {% if error_message %}
      <div class="bg-red-900/50 border border-red-500/50 text-red-200 rounded-xl p-6 text-center">
        <h2 class="text-2xl font-bold mb-2">কনফিগারেশন সমস্যা!</h2>
        <p>{{ error_message }}</p>
      </div>
    {% else %}
      {% if banners and banners|length > 0 %}
      <section class="grid grid-cols-1 md:grid-cols-2 gap-4 mb-8">
        {% for banner in banners %}
        <div class="relative rounded-2xl overflow-hidden shadow-[0_10px_30px_-10px_rgba(0,0,0,0.8)]">
          <img src="{{ banner.src }}" alt="{{ banner.title or 'Banner' }}" class="w-full aspect-video object-cover" />
          <div class="absolute inset-0 bg-gradient-to-t from-black/70 via-black/10 to-transparent"></div>
          {% if banner.title %}
          <div class="absolute bottom-3 left-4 right-4">
            <h2 class="text-lg md:text-2xl font-bold line-clamp-2">{{ banner.title }}</h2>
            {% if banner.overview %}
            <p class="text-xs md:text-sm text-white/80 line-clamp-2 mt-1">{{ banner.overview }}</p>
            {% endif %}
          </div>
          {% endif %}
        </div>
        {% endfor %}
      </section>
      {% endif %}

      <section class="mb-4">
        <h3 class="text-xl md:text-2xl font-bold">
          {% if query %}Results for “{{ query }}”{% else %}Recently Added Movies{% endif %}
        </h3>
      </section>
      
      {% if movies and movies|length > 0 %}
      <section class="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-5 lg:grid-cols-6 gap-4">
        {% for m in movies %}
        <a href="https://www.themoviedb.org/movie/{{ m.tmdb_id }}" target="_blank" rel="noopener"
           class="group rounded-2xl overflow-hidden bg-white/5 border border-white/10 hover:border-white/20 hover:bg-white/10 transition">
          <div class="relative"><img src="{{ m.poster }}" alt="{{ m.title }}" class="w-full aspect-[2/3] object-cover" /></div>
          <div class="p-2">
            <p class="text-sm font-semibold line-clamp-2">{{ m.title }}</p>
            <p class="text-xs text-white/60 mt-0.5">{{ m.year }}</p>
          </div>
        </a>
        {% endfor %}
      </section>
      {% else %}
        <div class="text-center py-10 text-white/70">
            {% if query %}No movies found for your search.{% else %}No movies have been added to the site yet. Please add some from the admin panel.{% endif %}
        </div>
      {% endif %}
    {% endif %}
  </main>

  <footer class="max-w-7xl mx-auto px-4 py-8 text-center text-xs text-white/50">
    {% if ads.footer %}<div class="footer-ad mb-4">{{ ads.footer | safe }}</div>{% endif %}
    <div>© {{ year }} Movie Zone • Powered by The Movie Database (TMDB)</div>
  </footer>
</body>
</html>
"""

# --- অ্যাডমিন লগইন পেজের টেমপ্লেট ---
ADMIN_LOGIN_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Admin Login</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <meta name="color-scheme" content="dark">
</head>
<body class="bg-gray-950 text-gray-200 flex items-center justify-center min-h-screen">
    <div class="w-full max-w-md">
        <form method="POST" class="bg-gray-900 border border-white/10 shadow-lg rounded-2xl p-8 space-y-6">
            <h2 class="text-3xl font-bold text-center">Admin Login</h2>
            {% with messages = get_flashed_messages(with_categories=true) %}
                {% if messages %}
                    {% for category, message in messages %}
                        <div class="p-3 rounded-lg bg-red-500/20 text-red-300 text-sm">{{ message }}</div>
                    {% endfor %}
                {% endif %}
            {% endwith %}
            <div>
                <label for="username" class="block text-sm font-medium text-gray-400">Username</label>
                <input type="text" name="username" id="username" required
                       class="mt-1 block w-full bg-white/5 border border-white/10 rounded-lg px-3 py-2 outline-none focus:ring-2 focus:ring-blue-500">
            </div>
            <div>
                <label for="password" class="block text-sm font-medium text-gray-400">Password</label>
                <input type="password" name="password" id="password" required
                       class="mt-1 block w-full bg-white/5 border border-white/10 rounded-lg px-3 py-2 outline-none focus:ring-2 focus:ring-blue-500">
            </div>
            <button type="submit"
                    class="w-full bg-blue-600 hover:bg-blue-700 text-white font-bold py-2.5 px-4 rounded-lg transition">
                Login
            </button>
        </form>
    </div>
</body>
</html>
"""

# --- অ্যাডমিন প্যানেলের বেস লেআউট টেমপ্লেট ---
ADMIN_BASE_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{{ title or "Admin Panel" }} • Movie Zone</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <meta name="color-scheme" content="dark">
</head>
<body class="bg-gray-900 text-gray-200 antialiased">
    <div class="flex min-h-screen">
        <aside class="w-64 bg-gray-950 p-6 border-r border-white/10 flex flex-col">
            <h1 class="text-2xl font-bold mb-8">🎬 Admin Panel</h1>
            <nav class="flex flex-col gap-2">
                <a href="{{ url_for('admin.dashboard') }}" class="px-4 py-2 rounded-lg {% if request.endpoint == 'admin.dashboard' %}bg-blue-600{% else %}hover:bg-white/10{% endif %}">Dashboard</a>
                <a href="{{ url_for('admin.manage_movies') }}" class="px-4 py-2 rounded-lg {% if 'movie' in request.endpoint %}bg-blue-600{% else %}hover:bg-white/10{% endif %}">Manage Movies</a>
                <a href="{{ url_for('admin.manage_ads') }}" class="px-4 py-2 rounded-lg {% if 'ad' in request.endpoint %}bg-blue-600{% else %}hover:bg-white/10{% endif %}">Manage Ads</a>
            </nav>
            <div class="mt-auto">
                <a href="{{ url_for('home') }}" target="_blank" class="block w-full text-center px-4 py-2 rounded-lg hover:bg-white/10 text-sm mb-2">View Site ↗</a>
                <a href="{{ url_for('admin.logout') }}" class="block w-full text-center px-4 py-2 rounded-lg bg-red-600/50 hover:bg-red-600/80 text-sm">Logout</a>
            </div>
        </aside>
        <main class="flex-1 p-8">
            {% with messages = get_flashed_messages(with_categories=true) %}
                {% if messages %}
                    {% for category, message in messages %}
                        <div class="mb-4 p-4 rounded-lg 
                            {% if category == 'success' %}bg-green-500/20 text-green-300 border border-green-500/30
                            {% elif category == 'error' %}bg-red-500/20 text-red-300 border border-red-500/30
                            {% elif category == 'warning' %}bg-yellow-500/20 text-yellow-300 border border-yellow-500/30
                            {% else %}bg-blue-500/20 text-blue-300 border border-blue-500/30
                            {% endif %}">
                            {{ message }}
                        </div>
                    {% endfor %}
                {% endif %}
            {% endwith %}
            {{ content | safe }}
        </main>
    </div>
</body>
</html>
"""

# --- অ্যাডমিন প্যানেলের বিভিন্ন পেজের কন্টেন্ট ---
ADMIN_DASHBOARD_CONTENT = """
<h1 class="text-3xl font-bold mb-6">Dashboard</h1>
<div class="grid grid-cols-1 md:grid-cols-2 gap-6">
    <div class="bg-gray-950/50 p-6 rounded-xl border border-white/10">
        <h2 class="text-lg font-semibold text-gray-400">Total Movies on Site</h2>
        <p class="text-5xl font-bold mt-2">{{ movie_count }}</p>
    </div>
    <div class="bg-gray-950/50 p-6 rounded-xl border border-white/10">
        <h2 class="text-lg font-semibold text-gray-400">Total Ads Configured</h2>
        <p class="text-5xl font-bold mt-2">{{ ad_count }}</p>
    </div>
</div>
"""

ADMIN_MOVIES_CONTENT = """
<h1 class="text-3xl font-bold mb-6">Manage Movies</h1>
<div class="bg-gray-950/50 p-6 rounded-xl border border-white/10 mb-8">
    <h2 class="text-xl font-bold mb-4">Add New Movie from TMDB</h2>
    <form method="POST" class="flex gap-4">
        <input type="search" name="query" placeholder="Search on TMDB..." required
               class="flex-grow bg-white/5 border border-white/10 rounded-lg px-4 py-2 outline-none focus:ring-2 focus:ring-blue-500">
        <button type="submit" class="bg-blue-600 hover:bg-blue-700 text-white font-bold py-2 px-6 rounded-lg">Search</button>
    </form>
    {% if tmdb_results %}
    <div class="mt-6">
        <h3 class="font-semibold mb-2">Search Results:</h3>
        <div class="max-h-80 overflow-y-auto space-y-2 pr-2">
            {% for movie in tmdb_results %}
            <div class="flex items-center gap-4 p-2 bg-white/5 rounded-lg">
                <img src="{{ movie.poster }}" class="w-12 h-auto rounded-md">
                <div class="flex-grow">
                    <p class="font-bold">{{ movie.title }}</p>
                    <p class="text-sm text-gray-400">{{ movie.year }}</p>
                </div>
                <form action="{{ url_for('admin.add_movie', tmdb_id=movie.tmdb_id) }}" method="POST">
                    <button type="submit" class="bg-green-600 hover:bg-green-700 text-white text-sm font-bold py-1 px-3 rounded-md">+</button>
                </form>
            </div>
            {% endfor %}
        </div>
    </div>
    {% endif %}
</div>
<div class="bg-gray-950/50 p-6 rounded-xl border border-white/10">
    <div class="flex justify-between items-center mb-4">
        <h2 class="text-xl font-bold">Movies on Your Site ({{ site_movies|length }})</h2>
        <form action="{{ url_for('admin.delete_all_movies') }}" method="POST" onsubmit="return confirm('Are you absolutely sure you want to delete ALL movies? This cannot be undone.');">
            <button type="submit" class="bg-red-800 hover:bg-red-700 text-white text-sm font-bold py-2 px-4 rounded-lg">Delete All</button>
        </form>
    </div>
    <div class="overflow-x-auto">
        <table class="w-full text-left">
            <thead><tr class="border-b border-white/10"><th class="p-3">Poster</th><th class="p-3">Title</th><th class="p-3">Year</th><th class="p-3 text-right">Actions</th></tr></thead>
            <tbody>
                {% for movie in site_movies %}
                <tr class="border-b border-white/5">
                    <td class="p-2"><img src="{{ movie.poster }}" class="w-12 h-auto rounded-md"></td>
                    <td class="p-2 font-semibold">{{ movie.title }}</td>
                    <td class="p-2 text-gray-400">{{ movie.year }}</td>
                    <td class="p-2 text-right">
                        <form action="{{ url_for('admin.delete_movie', movie_id=movie._id) }}" method="POST" class="inline">
                            <button type="submit" class="text-red-400 hover:text-red-300 text-sm font-bold">Delete</button>
                        </form>
                    </td>
                </tr>
                {% else %}
                <tr><td colspan="4" class="p-4 text-center text-gray-500">No movies found.</td></tr>
                {% endfor %}
            </tbody>
        </table>
    </div>
</div>
"""

ADMIN_ADS_CONTENT = """
<h1 class="text-3xl font-bold mb-6">Manage Advertisements</h1>
<div class="grid grid-cols-1 lg:grid-cols-3 gap-8">
    <div class="lg:col-span-1 bg-gray-950/50 p-6 rounded-xl border border-white/10">
        <h2 class="text-xl font-bold mb-4">Add / Edit Ad</h2>
        <form method="POST" class="space-y-4">
            <input type="hidden" name="ad_id" value="">
            <div><label class="block text-sm font-medium text-gray-400">Ad Name</label><input type="text" name="name" required class="mt-1 w-full bg-white/5 border border-white/10 rounded-lg px-3 py-2"></div>
            <div><label class="block text-sm font-medium text-gray-400">Position</label><select name="position" required class="mt-1 w-full bg-white/5 border border-white/10 rounded-lg px-3 py-2"><option value="header">Header</option><option value="footer">Footer</option></select></div>
            <div><label class="block text-sm font-medium text-gray-400">HTML/JS Code</label><textarea name="html_code" rows="5" required class="mt-1 w-full bg-white/5 border border-white/10 rounded-lg px-3 py-2"></textarea></div>
            <div class="flex items-center"><input type="checkbox" name="is_active" id="is_active" checked class="h-4 w-4 rounded bg-white/10 border-gray-600 text-blue-600 focus:ring-blue-600"><label for="is_active" class="ml-2 block text-sm text-gray-300">Active</label></div>
            <button type="submit" class="w-full bg-blue-600 hover:bg-blue-700 text-white font-bold py-2.5 px-4 rounded-lg">Save Ad</button>
        </form>
    </div>
    <div class="lg:col-span-2 bg-gray-950/50 p-6 rounded-xl border border-white/10">
        <h2 class="text-xl font-bold mb-4">Existing Ads</h2>
        <div class="space-y-4">
        {% for ad in ads %}
            <div class="bg-white/5 p-4 rounded-lg">
                <div class="flex justify-between items-start">
                    <div>
                        <h3 class="font-bold">{{ ad.name }} <span class="text-xs ml-2 px-2 py-0.5 rounded-full {{ 'bg-green-500/30 text-green-300' if ad.is_active else 'bg-red-500/30 text-red-300' }}">{{ 'Active' if ad.is_active else 'Inactive' }}</span></h3>
                        <p class="text-sm text-gray-400">Position: <span class="font-mono">{{ ad.position }}</span></p>
                    </div>
                    <form action="{{ url_for('admin.delete_ad', ad_id=ad._id) }}" method="POST" onsubmit="return confirm('Delete this ad?');"><button type="submit" class="text-red-400 hover:text-red-300 text-xs font-bold">Delete</button></form>
                </div>
                <div class="mt-2 text-xs bg-black/30 p-2 rounded-md font-mono max-w-md overflow-x-auto">{{ ad.html_code|e }}</div>
            </div>
        {% else %}
            <p class="text-gray-500">No ads have been created yet.</p>
        {% endfor %}
        </div>
    </div>
</div>
"""

# =======================================================================
# ========= FLASK APPLICATION LOGIC (মূল পাইথন কোড) =========
# =======================================================================

app = Flask(__name__)
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "dev_secret_key")

# --- ENV CONFIG (Vercel থেকে এই ভেরিয়েবলগুলো সেট করতে হবে) ---
TMDB_API_KEY = os.getenv("TMDB_API_KEY")
MONGO_URI = os.getenv("MONGO_URI")
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "password")

# --- TMDB CONFIG ---
TMDB_BASE_URL = "https://api.themoviedb.org/3"
IMG_POSTER = "https://image.tmdb.org/t/p/w500"
IMG_BANNER = "https://image.tmdb.org/t/p/w1280"

# --- DATABASE (MongoDB) with Error Handling ---
client = None
db = None
users_collection = None
movies_collection = None
ads_collection = None
DB_CONNECTION_ERROR = None

if MONGO_URI:
    try:
        client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
        client.admin.command('ping') # কানেকশন চেক করার জন্য পিং পাঠানো হচ্ছে
        print("MongoDB connection successful.")
        db = client.get_database()
        users_collection = db.users
        movies_collection = db.movies
        ads_collection = db.ads
        movies_collection.create_index("tmdb_id", unique=True)
    except Exception as e:
        print(f"ERROR: Could not connect to MongoDB. Reason: {e}")
        DB_CONNECTION_ERROR = f"Database connection failed. Please check credentials and network access. Error: {e}"
else:
    DB_CONNECTION_ERROR = "MONGO_URI environment variable is not set. Please configure it in Vercel."

# --- LOGIN MANAGER ---
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "admin.login"

class User(UserMixin):
    def __init__(self, user_data):
        self.id = str(user_data["_id"])
        self.username = user_data["username"]
        self.password_hash = user_data["password"]

@login_manager.user_loader
def load_user(user_id):
    if users_collection:
        user_data = users_collection.find_one({"_id": ObjectId(user_id)})
        if user_data: return User(user_data)
    return None

# --- TMDB HELPERS ---
def tmdb_get(path, params=None):
    if not TMDB_API_KEY: return {"results": []}
    params = params or {}
    params["api_key"] = TMDB_API_KEY
    url = f"{TMDB_BASE_URL}{path}"
    try:
        r = requests.get(url, params=params, timeout=10)
        r.raise_for_status()
        return r.json()
    except requests.exceptions.RequestException:
        return {"results": []}

def search_tmdb_movies(query):
    if not query: return []
    return tmdb_get("/search/movie", params={"query": query, "include_adult": "false"}).get("results", [])

def get_tmdb_movie_details(tmdb_id):
    return tmdb_get(f"/movie/{tmdb_id}")

# --- DATA MAPPING HELPER ---
def map_movie_from_tmdb(m):
    poster = m.get("poster_path")
    backdrop = m.get("backdrop_path")
    date = m.get("release_date") or ""
    return { "tmdb_id": m.get("id"), "title": m.get("title") or "Untitled", "year": date[:4] if date else "N/A", "poster": f"{IMG_POSTER}{poster}" if poster else "https://via.placeholder.com/500x750?text=No+Image", "backdrop": f"{IMG_BANNER}{backdrop}" if backdrop else None, "overview": m.get("overview") or ""}

# --- CONTEXT PROCESSOR ---
@app.context_processor
def inject_globals():
    ads = {}
    if ads_collection:
        active_ads = {ad['position']: ad['html_code'] for ad in ads_collection.find({"is_active": True})}
        ads.update(active_ads)
    return dict(year=time.strftime("%Y"), ads=ads)

# --- ADMIN HELPER ---
def render_admin_page(content_template, **kwargs):
    content_html = render_template_string(content_template, **kwargs)
    return render_template_string(ADMIN_BASE_TEMPLATE, content=content_html, **kwargs)

# --- ADMIN BLUEPRINT ---
admin_bp = Blueprint('admin', __name__, url_prefix='/admin')

@admin_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated: return redirect(url_for('admin.dashboard'))
    if request.method == 'POST':
        username, password = request.form.get('username'), request.form.get('password')
        if users_collection:
            user_data = users_collection.find_one({"username": username})
            if user_data and check_password_hash(user_data['password'], password):
                login_user(User(user_data))
                return redirect(url_for('admin.dashboard'))
        flash('Invalid username or password.', 'error')
    return render_template_string(ADMIN_LOGIN_TEMPLATE)

@admin_bp.route('/logout')
@login_required
def logout():
    logout_user()
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
    tmdb_results = []
    if request.method == 'POST' and 'query' in request.form:
        query = request.form.get('query')
        if query: tmdb_results = [map_movie_from_tmdb(m) for m in search_tmdb_movies(query)]
    site_movies = list(movies_collection.find().sort('_id', DESCENDING)) if movies_collection else []
    return render_admin_page(ADMIN_MOVIES_CONTENT, title="Manage Movies", site_movies=site_movies, tmdb_results=tmdb_results)

@admin_bp.route('/movies/add/<int:tmdb_id>', methods=['POST'])
@login_required
def add_movie(tmdb_id):
    if movies_collection.find_one({"tmdb_id": tmdb_id}):
        flash('This movie is already in your database.', 'warning')
    else:
        movie_details = get_tmdb_movie_details(tmdb_id)
        if movie_details:
            movies_collection.insert_one(map_movie_from_tmdb(movie_details))
            flash(f"Movie has been added.", 'success')
        else: flash('Could not fetch movie details.', 'error')
    return redirect(url_for('admin.manage_movies'))

@admin_bp.route('/movies/delete/<movie_id>', methods=['POST'])
@login_required
def delete_movie(movie_id):
    movies_collection.delete_one({"_id": ObjectId(movie_id)})
    flash('Movie has been deleted.', 'success')
    return redirect(url_for('admin.manage_movies'))

@admin_bp.route('/movies/delete_all', methods=['POST'])
@login_required
def delete_all_movies():
    movies_collection.delete_many({})
    flash('All movies have been deleted!', 'danger')
    return redirect(url_for('admin.manage_movies'))

@admin_bp.route('/ads', methods=['GET', 'POST'])
@login_required
def manage_ads():
    if request.method == 'POST':
        data = { "name": request.form.get('name'), "position": request.form.get('position'), "html_code": request.form.get('html_code'), "is_active": 'is_active' in request.form }
        ads_collection.insert_one(data)
        flash('Ad created successfully.', 'success')
        return redirect(url_for('admin.manage_ads'))
    all_ads = list(ads_collection.find()) if ads_collection else []
    return render_admin_page(ADMIN_ADS_CONTENT, title="Manage Ads", ads=all_ads)

@admin_bp.route('/ads/delete/<ad_id>', methods=['POST'])
@login_required
def delete_ad(ad_id):
    ads_collection.delete_one({"_id": ObjectId(ad_id)})
    flash('Ad deleted.', 'success')
    return redirect(url_for('admin.manage_ads'))

app.register_blueprint(admin_bp)

# --- PUBLIC ROUTES ---
def pick_banners(movie_list, need=2):
    banners = [m for m in movie_list if m.get("backdrop")][:need]
    while len(banners) < min(need, 2):
        banners.append({ "src": "https://via.placeholder.com/1280x720/111827/FFFFFF?text=Movie+Zone", "title": "Welcome to Movie Zone", "overview": "Add movies from the admin panel."})
    return banners

@app.route("/")
def home():
    if DB_CONNECTION_ERROR: return render_template_string(PAGE_TEMPLATE, title="Config Error", error_message=DB_CONNECTION_ERROR)
    if not TMDB_API_KEY: return render_template_string(PAGE_TEMPLATE, title="Config Error", error_message="TMDB_API_KEY is not configured.")
    
    movies = list(movies_collection.find().sort('_id', DESCENDING).limit(18))
    banners = pick_banners(movies)
    return render_template_string(PAGE_TEMPLATE, title="Movie Zone • Home", banners=banners, movies=movies)

@app.route("/search")
def search():
    if DB_CONNECTION_ERROR: return redirect(url_for("home"))
    q = (request.args.get("q") or "").strip()
    if not q: return redirect(url_for("home"))
    results = [map_movie_from_tmdb(m) for m in search_tmdb_movies(q)]
    banners = pick_banners(results)
    return render_template_string(PAGE_TEMPLATE, title=f"Search • {q}", banners=banners, movies=results, query=q)

# --- INITIAL ADMIN USER SETUP (শুধু লোকাল মেশিনে চালানোর জন্য) ---
def setup_initial_user():
    if db and users_collection and not users_collection.find_one({"username": ADMIN_USERNAME}):
        hashed_password = generate_password_hash(ADMIN_PASSWORD)
        users_collection.insert_one({ "username": ADMIN_USERNAME, "password": hashed_password })
        print(f"Admin user '{ADMIN_USERNAME}' created.")

if __name__ == "__main__":
    if not MONGO_URI: print("WARNING: MONGO_URI is not set.")
    setup_initial_user() # লোকাল মেশিনে অ্যাডমিন ইউজার তৈরি করবে
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
