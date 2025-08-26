import os
import time
import requests
from flask import (Flask, request, render_template_string, redirect, url_for, flash, Blueprint, session)
from pymongo import MongoClient, DESCENDING
from bson.objectid import ObjectId
from functools import wraps

# ==============================================================================
# ========= HTML TEMPLATES (সমস্ত টেমপ্লেট এখানে) ============================
# ==============================================================================

# --- ব্যবহারকারীদের জন্য মূল সাইটের টেমপ্লেট ---
PAGE_TEMPLATE = """<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8" /><meta name="viewport" content="width=device-width, initial-scale=1.0" /><title>{{ title or "Movie Zone" }}</title><script src="https://cdn.tailwindcss.com"></script><link rel="icon" href="data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 100 100%22><text y=%22.9em%22 font-size=%2290%22>🎬</text></svg>"><style>body{background-color:#040714;color:#f9f9f9;}.poster-card{transition:all .3s ease}.poster-card:hover{transform:scale(1.05)}.banner-wrapper{display:flex;transition:transform .5s ease-in-out}.scroll-container{scrollbar-width:none;-ms-overflow-style:none}.scroll-container::-webkit-scrollbar{display:none}</style></head><body class="overflow-x-hidden"><header class="sticky top-0 z-50 h-20 px-6 md:px-12 flex items-center justify-between bg-[#090b13]"><a href="{{ url_for('home') }}" class="text-2xl font-extrabold tracking-tight text-white uppercase">Movie<span class="text-blue-500">Zone</span></a><form action="{{ url_for('search') }}" method="get" class="w-full max-w-xs ml-auto"><input name="q" value="{{ query or '' }}" placeholder="Search..." class="bg-gray-800 text-white rounded-full px-4 py-2 text-sm outline-none w-full" /></form></header><main class="pt-6">{% if not query and banners %}<section class="relative mb-12 w-full overflow-hidden md:px-12" id="banner-carousel"><div class="banner-wrapper">{% for banner in banners %}<div class="w-full flex-shrink-0"><a href="{{ url_for('content_detail', content_id=banner.content_id) }}"><div class="relative px-6 md:px-0"><img src="{{ banner.src }}" alt="{{ banner.title }}" class="w-full h-auto object-cover rounded-none md:rounded-lg min-h-[250px] md:min-h-[450px]"><div class="absolute inset-0 bg-gradient-to-r from-[#040714] via-transparent to-transparent rounded-none md:rounded-lg"></div><div class="absolute bottom-10 md:bottom-20 left-10 md:left-12 max-w-lg"><h1 class="text-3xl md:text-5xl font-bold drop-shadow-lg">{{ banner.title }}</h1><p class="text-sm md:text-base mt-4 line-clamp-3 text-gray-300 drop-shadow-md">{{ banner.overview }}</p></div></div></a></div>{% endfor %}</div></section>{% endif %}<div class="px-6 md:px-12 space-y-12">{% if categories %}{% for category in categories %}{% if category.content %}<section><h2 class="text-2xl font-semibold tracking-wide mb-4">{{ category.name }}</h2><div class="flex space-x-6 overflow-x-auto pb-4 scroll-container">{% for item in category.content %}<a href="{{ url_for('content_detail', content_id=item._id) }}" class="poster-card group rounded-lg overflow-hidden border-2 border-gray-800 hover:border-gray-400 shadow-lg flex-shrink-0 w-40 md:w-52"><img src="{{ item.poster }}" alt="{{ item.title }}" class="w-full h-auto object-cover aspect-[2/3]"></a>{% endfor %}</div></section>{% endif %}{% endfor %}{% elif query %}<section><h2 class="text-2xl font-semibold tracking-wide mb-4">Results for “{{ query }}”</h2>{% if content %}<div class="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-6">{% for item in content %}<a href="{{ url_for('content_detail', content_id=item._id) }}" class="poster-card group rounded-lg overflow-hidden border-2 border-gray-800 hover:border-gray-400 shadow-lg"><img src="{{ item.poster }}" alt="{{ item.title }}" class="w-full h-auto object-cover aspect-[2/3]"></a>{% endfor %}</div>{% else %}<p class="text-center py-10 text-gray-400">No content found for your search.</p>{% endif %}</section>{% else %}<div class="text-center py-20 text-gray-400"><h2 class="text-3xl font-bold">Welcome to MovieZone!</h2><p class="mt-2">No content or categories have been added yet. Please add them from the admin panel.</p></div>{% endif %}</div>{% if error_message %}<div class="mt-12 mx-6 md:mx-12 bg-red-900/50 border-red-500/50 text-red-200 rounded-xl p-6 text-center"><h2 class="text-2xl font-bold mb-2">Application Error!</h2><p class="font-mono text-sm">{{ error_message }}</p></div>{% endif %}</main><footer class="text-center text-xs text-gray-500 py-8 mt-12"><div>© {{ year }} Movie Zone</div></footer><script>document.addEventListener('DOMContentLoaded',()=>{const e=document.getElementById("banner-carousel");if(!e)return;const t=e.querySelector(".banner-wrapper"),o=t.children;if(o.length<=1)return;let n=0;function r(e){t.style.transform=`translateX(-${e*100}%)`}function c(){n=(n+1)%o.length,r(n)}let l=setInterval(c,5e3);e.addEventListener("mouseenter",()=>clearInterval(l)),e.addEventListener("mouseleave",()=>l=setInterval(c,5e3))})</script></body></html>"""
CONTENT_DETAIL_TEMPLATE = """<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8" /><meta name="viewport" content="width=device-width, initial-scale=1.0" /><title>{{ content.title }} • Movie Zone</title><script src="https://cdn.tailwindcss.com"></script><link rel="icon" href="data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 100 100%22><text y=%22.9em%22 font-size=%2290%22>🎬</text></svg>"><style>body { background-color: #040714; color: #f9f9f9; }</style></head><body><div class="relative min-h-screen"><div class="absolute inset-0 z-0"><img src="{{ content.backdrop or content.poster }}" alt="{{ content.title }}" class="w-full h-full object-cover opacity-20"></div><div class="absolute inset-0 z-10 bg-gradient-to-t from-[#040714] via-[#040714]/80 to-transparent"></div><main class="relative z-20 max-w-5xl mx-auto px-6 py-12 pt-24"><a href="{{ url_for('home') }}" class="text-sm text-gray-400 hover:text-white mb-8 inline-block">&larr; Back to Home</a><div class="md:flex md:space-x-8"><div class="md:w-1/3 flex-shrink-0"><img src="{{ content.poster }}" alt="{{ content.title }}" class="rounded-lg shadow-2xl w-full"></div><div class="md:w-2/3 mt-8 md:mt-0"><h1 class="text-4xl md:text-5xl font-bold">{{ content.title }} ({{ content.year }})</h1><p class="text-gray-300 mt-4 text-lg">{{ content.overview }}</p><div class="mt-8 flex flex-wrap gap-4">{% if content.watch_link %}<a href="{{ content.watch_link }}" target="_blank" rel="noopener" class="bg-blue-600 hover:bg-blue-700 text-white font-bold py-3 px-8 rounded-lg text-lg transition">▶ Watch Now</a>{% else %}<button class="bg-gray-600 text-white font-bold py-3 px-8 rounded-lg text-lg cursor-not-allowed" disabled>Watch Link Not Available</button>{% endif %}{% if content.download_link %}<a href="{{ content.download_link }}" target="_blank" rel="noopener" class="bg-gray-700 hover:bg-gray-600 text-white font-bold py-3 px-8 rounded-lg text-lg transition">⬇ Download</a>{% else %}<button class="bg-gray-800 text-white font-bold py-3 px-8 rounded-lg text-lg cursor-not-allowed" disabled>Download Link Not Available</button>{% endif %}</div></div></div></main></div></body></html>"""
ADMIN_LOGIN_TEMPLATE = """<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"><title>Admin Login</title><script src="https://cdn.tailwindcss.com"></script><meta name="color-scheme" content="dark"></head><body class="bg-gray-950 text-gray-200 flex items-center justify-center min-h-screen"><div class="w-full max-w-md"><form method="POST" class="bg-gray-900 border border-white/10 shadow-lg rounded-2xl p-8 space-y-6"><h2 class="text-3xl font-bold text-center">Admin Login</h2>{% with messages = get_flashed_messages(with_categories=true) %}{% if messages %}{% for category, message in messages %}<div class="p-3 rounded-lg bg-red-500/20 text-red-300 text-sm">{{ message }}</div>{% endfor %}{% endif %}{% endwith %}<div><label for="username" class="block text-sm font-medium text-gray-400">Username</label><input type="text" name="username" id="username" required class="mt-1 block w-full bg-white/5 border border-white/10 rounded-lg px-3 py-2 outline-none focus:ring-2 focus:ring-blue-500"></div><div><label for="password" class="block text-sm font-medium text-gray-400">Password</label><input type="password" name="password" id="password" required class="mt-1 block w-full bg-white/5 border border-white/10 rounded-lg px-3 py-2 outline-none focus:ring-2 focus:ring-blue-500"></div><button type="submit" class="w-full bg-blue-600 hover:bg-blue-700 text-white font-bold py-2.5 px-4 rounded-lg transition">Login</button></form></div></body></html>"""
ADMIN_BASE_TEMPLATE = """<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"><title>{{ title or "Admin Panel" }} • Movie Zone</title><script src="https://cdn.tailwindcss.com"></script><meta name="color-scheme" content="dark"></head><body class="bg-gray-900 text-gray-200 antialiased"><div class="flex min-h-screen"><aside class="w-64 bg-gray-950 p-6 border-r border-white/10 flex flex-col"><h1 class="text-2xl font-bold mb-8">🎬 Admin Panel</h1><nav class="flex flex-col gap-2"><a href="{{ url_for('admin.dashboard') }}" class="px-4 py-2 rounded-lg hover:bg-white/10">Dashboard</a><a href="{{ url_for('admin.manage_content') }}" class="px-4 py-2 rounded-lg hover:bg-white/10">Manage Content</a><a href="{{ url_for('admin.manage_categories') }}" class="px-4 py-2 rounded-lg hover:bg-white/10">Manage Categories</a></nav><div class="mt-auto"><a href="{{ url_for('home') }}" target="_blank" class="block w-full text-center px-4 py-2 rounded-lg hover:bg-white/10 text-sm mb-2">View Site ↗</a><a href="{{ url_for('admin.logout') }}" class="block w-full text-center px-4 py-2 rounded-lg bg-red-600/50 hover:bg-red-600/80 text-sm">Logout</a></div></aside><main class="flex-1 p-8">{% with messages = get_flashed_messages(with_categories=true) %}{% if messages %}{% for category, message in messages %}<div class="mb-4 p-4 rounded-lg {% if category == 'success' %}bg-green-500/20 text-green-300 border border-green-500/30{% elif category == 'error' %}bg-red-500/20 text-red-300 border border-red-500/30{% else %}bg-blue-500/20 text-blue-300 border border-blue-500/30{% endif %}">{{ message }}</div>{% endfor %}{% endif %}{% endwith %}{{ content | safe }}</main></div></body></html>"""
ADMIN_DASHBOARD_CONTENT = """<h1 class="text-3xl font-bold mb-6">Dashboard</h1><div class="grid grid-cols-1 md:grid-cols-2 gap-6"><div class="bg-gray-950/50 p-6 rounded-xl border border-white/10"><h2 class="text-lg font-semibold text-gray-400">Total Content on Site</h2><p class="text-5xl font-bold mt-2">{{ content_count }}</p></div><div class="bg-gray-950/50 p-6 rounded-xl border border-white/10"><h2 class="text-lg font-semibold text-gray-400">Total Categories</h2><p class="text-5xl font-bold mt-2">{{ category_count }}</p></div></div>"""
ADMIN_CONTENT_TEMPLATE = """<h1 class="text-3xl font-bold mb-6">Manage Content</h1><div class="bg-gray-950/50 p-6 rounded-xl border border-white/10 mb-8"><h2 class="text-xl font-bold mb-4">Add New Content from TMDB</h2><form method="POST"><div class="flex items-center gap-4 mb-4"><label class="text-gray-300">Content Type:</label><div class="flex gap-4"><label class="flex items-center"><input type="radio" name="type" value="movie" checked class="h-4 w-4 bg-gray-700 border-gray-600 text-blue-500 focus:ring-blue-600"><span class="ml-2">Movie</span></label><label class="flex items-center"><input type="radio" name="type" value="tv" class="h-4 w-4 bg-gray-700 border-gray-600 text-blue-500 focus:ring-blue-600"><span class="ml-2">TV Series</span></label></div></div><div class="flex gap-4"><input type="search" name="query" placeholder="Search on TMDB..." required class="flex-grow bg-white/5 border border-white/10 rounded-lg px-4 py-2 outline-none focus:ring-2 focus:ring-blue-500"><button type="submit" class="bg-blue-600 hover:bg-blue-700 text-white font-bold py-2 px-6 rounded-lg">Search</button></div></form>{% if tmdb_results %}<div class="mt-6"><h3 class="font-semibold mb-2">Search Results:</h3><div class="max-h-80 overflow-y-auto space-y-2 pr-2">{% for item in tmdb_results %}<div class="flex items-center gap-4 p-2 bg-white/5 rounded-lg"><img src="{{ item.poster }}" class="w-12 h-auto rounded-md"><div class="flex-grow"><p class="font-bold">{{ item.title }} <span class="text-xs text-gray-400">({{ item.type }})</span></p><p class="text-sm text-gray-400">{{ item.year }}</p></div><form action="{{ url_for('admin.add_content', type=item.type, tmdb_id=item.tmdb_id) }}" method="POST"><button type="submit" class="bg-green-600 hover:bg-green-700 text-white text-sm font-bold py-1 px-3 rounded-md">+</button></form></div>{% endfor %}</div></div>{% endif %}</div><div class="bg-gray-950/50 p-6 rounded-xl border border-white/10"><div class="flex justify-between items-center mb-4"><h2 class="text-xl font-bold">Content on Your Site ({{ site_content|length }})</h2><form action="{{ url_for('admin.delete_all_content') }}" method="POST" onsubmit="return confirm('Are you sure you want to delete ALL content?');"><button type="submit" class="bg-red-800 hover:bg-red-700 text-white text-sm font-bold py-2 px-4 rounded-lg">Delete All</button></form></div><div class="overflow-x-auto"><table class="w-full text-left"><thead><tr class="border-b border-white/10"><th class="p-3">Poster</th><th class="p-3">Title</th><th class="p-3">Type</th><th class="p-3">Categories</th><th class="p-3 text-right">Actions</th></tr></thead><tbody>{% for item in site_content %}<tr class="border-b border-white/5"><td><img src="{{ item.poster }}" class="w-12 h-auto rounded-md"></td><td class="font-semibold">{{ item.title }}</td><td class="text-sm uppercase text-gray-400">{{ item.type }}</td><td><div class="text-xs max-w-xs">{% for cat_id in item.categories %}{% set cat = all_categories.get(cat_id) %}{% if cat %}<span class="bg-gray-700 rounded-full px-2 py-1 mr-1 mb-1 inline-block">{{ cat.name }}</span>{% endif %}{% endfor %}</div></td><td class="text-right"><a href="{{ url_for('admin.edit_content', content_id=item._id) }}" class="text-blue-400 hover:text-blue-300 font-bold mr-4">Edit</a><form action="{{ url_for('admin.delete_content', content_id=item._id) }}" method="POST" class="inline"><button type="submit" class="text-red-400 hover:text-red-300 font-bold">Delete</button></form></td></tr>{% else %}<tr><td colspan="5" class="p-4 text-center text-gray-500">No content found.</td></tr>{% endfor %}</tbody></table></div></div>"""
ADMIN_EDIT_CONTENT_TEMPLATE = """<h1 class="text-3xl font-bold mb-2">Edit Content</h1><p class="text-gray-400 mb-6">Editing: <strong class="text-white">{{ content.title }}</strong></p><form method="POST" class="max-w-xl mx-auto bg-gray-950/50 p-8 rounded-xl border border-white/10 space-y-6"><div><label class="block text-sm font-medium text-gray-300 mb-2">Assign to Categories</label><div class="space-y-2 max-h-40 overflow-y-auto bg-white/5 p-4 rounded-md">{% for category in all_categories %}<label class="flex items-center"><input type="checkbox" name="categories" value="{{ category._id }}" {% if category._id in content.categories %}checked{% endif %} class="h-4 w-4 bg-gray-700 border-gray-600 text-blue-500 rounded focus:ring-blue-600"><span class="ml-3 text-gray-200">{{ category.name }}</span></label>{% else %}<p class="text-sm text-gray-500">No categories created yet.</p>{% endfor %}</div></div><div><label for="watch_link" class="block text-sm font-medium text-gray-300 mb-1">Watch/Streaming Link</label><input type="url" name="watch_link" id="watch_link" value="{{ content.watch_link or '' }}" placeholder="https://..." class="w-full bg-white/5 border border-white/10 rounded-lg px-4 py-2 outline-none focus:ring-2 focus:ring-blue-500"></div><div><label for="download_link" class="block text-sm font-medium text-gray-300 mb-1">Download Link</label><input type="url" name="download_link" id="download_link" value="{{ content.download_link or '' }}" placeholder="https://..." class="w-full bg-white/5 border border-white/10 rounded-lg px-4 py-2 outline-none focus:ring-2 focus:ring-blue-500"></div><div class="flex justify-end gap-4 pt-4"><a href="{{ url_for('admin.manage_content') }}" class="bg-gray-600 hover:bg-gray-700 text-white font-bold py-2 px-6 rounded-lg">Cancel</a><button type="submit" class="bg-blue-600 hover:bg-blue-700 text-white font-bold py-2 px-6 rounded-lg">Save Changes</button></div></form>"""
ADMIN_CATEGORIES_TEMPLATE = """<h1 class="text-3xl font-bold mb-6">Manage Categories</h1><div class="grid grid-cols-1 md:grid-cols-3 gap-8"><div class="md:col-span-1"><div class="bg-gray-950/50 p-6 rounded-xl border border-white/10"><h2 class="text-xl font-bold mb-4">Create New Category</h2><form method="POST" class="space-y-4"><div><label for="name" class="block text-sm font-medium text-gray-300 mb-1">Category Name</label><input type="text" name="name" id="name" required placeholder="e.g., Action, Korean Drama" class="w-full bg-white/5 border border-white/10 rounded-lg px-4 py-2 outline-none focus:ring-2 focus:ring-blue-500"></div><button type="submit" class="w-full bg-blue-600 hover:bg-blue-700 text-white font-bold py-2.5 rounded-lg">Create</button></form></div></div><div class="md:col-span-2"><div class="bg-gray-950/50 p-6 rounded-xl border border-white/10"><h2 class="text-xl font-bold mb-4">Existing Categories</h2><div class="space-y-3">{% for category in categories %}<div class="flex justify-between items-center bg-white/5 p-3 rounded-lg"><span>{{ category.name }}</span><form action="{{ url_for('admin.delete_category', category_id=category._id) }}" method="POST"><button type="submit" class="text-red-500 hover:text-red-400 text-xs font-bold">DELETE</button></form></div>{% else %}<p class="text-gray-500">No categories created yet.</p>{% endfor %}</div></div></div></div>"""

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
IMG_BANNER = "https://image.tmdb.org/t/p/original"

client, db, content_collection, categories_collection, DB_CONNECTION_ERROR = None, None, None, None, None
if MONGO_URI:
    try:
        client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
        client.admin.command('ping')
        print("MongoDB connection successful.")
        db = client["movie_db"]
        content_collection = db.content
        categories_collection = db.categories
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

def search_tmdb(query, type):
    path = f"/search/{type}"
    return tmdb_get(path, params={"query": query, "include_adult": "false"}).get("results", [])

def get_tmdb_details(tmdb_id, type):
    return tmdb_get(f"/{type}/{tmdb_id}")

def map_content_from_tmdb(m, type):
    is_movie = type == 'movie'
    title = m.get("title") if is_movie else m.get("name")
    date = m.get("release_date") if is_movie else m.get("first_air_date")
    return {
        "tmdb_id": m.get("id"),
        "type": type,
        "title": title or "Untitled",
        "year": (date or "")[:4] or "N/A",
        "poster": f"{IMG_POSTER}{m.get('poster_path')}" if m.get('poster_path') else "https://via.placeholder.com/500x750?text=No+Image",
        "backdrop": f"{IMG_BANNER}{m.get('backdrop_path')}" if m.get('backdrop_path') else None,
        "overview": m.get("overview") or "",
        "watch_link": "",
        "download_link": "",
        "categories": []
    }

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
    content_count = content_collection.count_documents({}) if content_collection is not None else 0
    category_count = categories_collection.count_documents({}) if categories_collection is not None else 0
    return render_admin_page(ADMIN_DASHBOARD_CONTENT, title="Dashboard", content_count=content_count, category_count=category_count)

@admin_bp.route('/content', methods=['GET', 'POST'])
@login_required
def manage_content():
    tmdb_results = []
    if request.method == 'POST':
        query = request.form.get('query')
        content_type = request.form.get('type', 'movie')
        if query:
            tmdb_results = [map_content_from_tmdb(m, content_type) for m in search_tmdb(query, content_type)]
    site_content = list(content_collection.find().sort('_id', DESCENDING)) if content_collection is not None else []
    all_categories = {cat['_id']: cat for cat in categories_collection.find()} if categories_collection is not None else {}
    return render_admin_page(ADMIN_CONTENT_TEMPLATE, title="Manage Content", site_content=site_content, tmdb_results=tmdb_results, all_categories=all_categories)

@admin_bp.route('/content/add/<string:type>/<int:tmdb_id>', methods=['POST'])
@login_required
def add_content(type, tmdb_id):
    if content_collection is None:
        flash('Database connection is not available.', 'error')
        return redirect(url_for('admin.manage_content'))
    try:
        if content_collection.find_one({"tmdb_id": tmdb_id, "type": type}):
            flash('This content already exists.', 'warning')
        else:
            details = get_tmdb_details(tmdb_id, type)
            if details:
                content_collection.insert_one(map_content_from_tmdb(details, type))
                flash('Content added successfully! Now edit it to add links and categories.', 'success')
            else:
                flash('Could not fetch details from TMDB.', 'error')
    except Exception as e:
        flash(f"Failed to add content. Check DB user permissions. Error: {e}", 'error')
    return redirect(url_for('admin.manage_content'))

@admin_bp.route('/content/edit/<content_id>', methods=['GET', 'POST'])
@login_required
def edit_content(content_id):
    if content_collection is None: return redirect(url_for('admin.manage_content'))
    try:
        item = content_collection.find_one({"_id": ObjectId(content_id)})
        if not item:
            flash('Content not found.', 'error')
            return redirect(url_for('admin.manage_content'))
        if request.method == 'POST':
            updated_data = {
                "watch_link": request.form.get('watch_link', '').strip(),
                "download_link": request.form.get('download_link', '').strip(),
                "categories": [ObjectId(cat_id) for cat_id in request.form.getlist('categories')]
            }
            content_collection.update_one({"_id": ObjectId(content_id)}, {"$set": updated_data})
            flash('Content updated successfully.', 'success')
            return redirect(url_for('admin.manage_content'))
        
        all_categories = list(categories_collection.find()) if categories_collection is not None else []
        return render_admin_page(ADMIN_EDIT_CONTENT_TEMPLATE, title="Edit Content", content=item, all_categories=all_categories)
    except Exception as e:
        flash(f"An error occurred: {e}", "error")
        return redirect(url_for('admin.manage_content'))

@admin_bp.route('/content/delete/<content_id>', methods=['POST'])
@login_required
def delete_content(content_id):
    if content_collection is not None: content_collection.delete_one({"_id": ObjectId(content_id)}); flash('Content deleted.', 'success')
    return redirect(url_for('admin.manage_content'))

@admin_bp.route('/content/delete_all', methods=['POST'])
@login_required
def delete_all_content():
    if content_collection is not None: content_collection.delete_many({}); flash('All content deleted!', 'danger')
    return redirect(url_for('admin.manage_content'))

@admin_bp.route('/categories', methods=['GET', 'POST'])
@login_required
def manage_categories():
    if request.method == 'POST' and categories_collection is not None:
        cat_name = request.form.get('name', '').strip()
        if cat_name:
            if categories_collection.find_one({"name": cat_name}): flash("Category already exists.", "warning")
            else: categories_collection.insert_one({"name": cat_name}); flash("Category created.", "success")
        else: flash("Category name cannot be empty.", "error")
        return redirect(url_for('admin.manage_categories'))
    
    all_categories = list(categories_collection.find()) if categories_collection is not None else []
    return render_admin_page(ADMIN_CATEGORIES_TEMPLATE, title="Manage Categories", categories=all_categories)

@admin_bp.route('/categories/delete/<category_id>', methods=['POST'])
@login_required
def delete_category(category_id):
    if categories_collection is not None and content_collection is not None:
        content_collection.update_many({}, {"$pull": {"categories": ObjectId(category_id)}})
        categories_collection.delete_one({"_id": ObjectId(category_id)})
        flash("Category deleted.", "success")
    return redirect(url_for('admin.manage_categories'))

app.register_blueprint(admin_bp)

def pick_banners(content_list, need=5):
    banners = []
    for m in content_list:
        if m.get("_id"):
            banners.append({"src": m.get("backdrop") or m.get("poster"), "title": m.get("title"), "overview": m.get("overview"), "content_id": str(m.get("_id"))})
        if len(banners) >= need: break
    if not banners:
        banners.append({ "src": "https://via.placeholder.com/1280x720/040714/f9f9f9?text=Welcome", "title": "Welcome to Movie Zone", "overview": "Add content from the admin panel.", "content_id": "#"})
    return banners

@app.route("/")
def home():
    if DB_CONNECTION_ERROR: return render_template_string(PAGE_TEMPLATE, error_message=DB_CONNECTION_ERROR)
    categories_with_content = []
    banner_content = []
    try:
        if categories_collection is not None and content_collection is not None:
            banner_content = list(content_collection.find().sort('_id', DESCENDING).limit(5))
            all_categories = list(categories_collection.find())
            for cat in all_categories:
                content_in_cat = list(content_collection.find({"categories": cat['_id']}).sort('_id', DESCENDING).limit(10))
                if content_in_cat:
                    cat['content'] = content_in_cat
                    categories_with_content.append(cat)
    except Exception as e:
        return render_template_string(PAGE_TEMPLATE, error_message=f"Could not fetch data. Error: {e}")
    return render_template_string(PAGE_TEMPLATE, title="Movie Zone", banners=pick_banners(banner_content), categories=categories_with_content)

@app.route("/content/<content_id>")
def content_detail(content_id):
    if DB_CONNECTION_ERROR: return redirect(url_for("home"))
    try:
        content = content_collection.find_one({"_id": ObjectId(content_id)}) if content_collection is not None else None
        if not content: return "Content not found", 404
        return render_template_string(CONTENT_DETAIL_TEMPLATE, content=content)
    except Exception as e:
        return f"Invalid Content ID or database error: {e}", 400

@app.route("/search")
def search():
    if DB_CONNECTION_ERROR: return redirect(url_for("home"))
    q = (request.args.get("q") or "").strip()
    search_results = []
    if q and content_collection is not None:
        search_results = list(content_collection.find({"title": {"$regex": q, "$options": "i"}}).limit(20))
    elif not q:
        return redirect(url_for('home'))
    return render_template_string(PAGE_TEMPLATE, title=f"Search • {q}", content=search_results, query=q, banners=None)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)), debug=True)
