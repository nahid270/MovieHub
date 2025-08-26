import os
import time
import requests
from flask import Flask, request, render_template_string, redirect, url_for

app = Flask(__name__)

# ========= ENV CONFIG (আপনার দেওয়া মূল কাঠামো অনুযায়ী) =========
TMDB_API_KEY = os.getenv("TMDB_API_KEY", "")
# ভবিষ্যৎ প্রয়োজনে বাকিগুলো রাখা হলো
NOTIFICATION_CHANNEL_ID = os.getenv("NOTIFICATION_CHANNEL_ID", "")
ADMIN_PASSWORD          = os.getenv("ADMIN_PASSWORD", "")
ADMIN_USERNAME          = os.getenv("ADMIN_USERNAME", "")
BOT_USERNAME            = os.getenv("BOT_USERNAME", "")
BOT_TOKEN               = os.getenv("BOT_TOKEN", "")
ADMIN_CHANNEL_ID        = os.getenv("ADMIN_CHANNEL_ID", "")
MONGO_URI               = os.getenv("MONGO_URI", "")

# ========= TMDB CONFIG =========
TMDB_BASE_URL = "https://api.themoviedb.org/3"
IMG_POSTER    = "https://image.tmdb.org/t/p/w500"
IMG_BANNER    = "https://image.tmdb.org/t/p/w1280"

# ========= SIMPLE CACHE (API কল কমানোর জন্য) =========
_cache = {}
def cache_get(key):
    item = _cache.get(key)
    if not item:
        return None
    data, exp = item
    if time.time() > exp:
        _cache.pop(key, None)
        return None
    return data

def cache_set(key, data, ttl=300):
    _cache[key] = (data, time.time() + ttl)

# ========= TMDB HELPERS =========
def tmdb_get(path, params=None, ttl=300, cache_key=None):
    """Generic TMDB GET with simple cache."""
    # API কী না থাকলে প্রথমেই খালি ফলাফল ফেরত দেবে
    if not TMDB_API_KEY:
        return {"results": []}

    params = params or {}
    params["api_key"] = TMDB_API_KEY
    params.setdefault("language", "en-US")

    if cache_key:
        cached = cache_get(cache_key)
        if cached is not None:
            return cached

    url = f"{TMDB_BASE_URL}{path}"
    try:
        r = requests.get(url, params=params, timeout=10)
        r.raise_for_status()
        data = r.json()
        if cache_key:
            cache_set(cache_key, data, ttl)
        return data
    except requests.exceptions.RequestException:
        # নেটওয়ার্ক বা API সংক্রান্ত যেকোনো সমস্যায় খালি ফলাফল দেবে
        return {"results": []}

def get_trending_movies():
    data = tmdb_get("/trending/movie/week", ttl=3600, cache_key="trending_movies") # ক্যাশ সময় বাড়ানো হলো
    return data.get("results", [])

def search_movies(query):
    if not query:
        return []
    data = tmdb_get("/search/movie", params={"query": query, "include_adult": "false"}, ttl=600, cache_key=f"search_{query.lower()}")
    return data.get("results", [])

# ========= HTML (TailwindCDN) - চূড়ান্ত সংস্করণ =========
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
  <!-- Navbar -->
  <header class="sticky top-0 z-50 border-b border-white/10 bg-black/50 backdrop-blur">
    <div class="max-w-7xl mx-auto px-4 py-3 flex items-center gap-3">
      <a href="{{ url_for('home') }}" class="text-xl font-extrabold tracking-tight">🎬 Movie Zone</a>
      <form action="{{ url_for('search') }}" method="get" class="ml-auto w-full max-w-md">
        <label class="relative block">
          <input name="q" value="{{ query or '' }}" placeholder="Search movies…"
                 class="w-full bg-white/5 border border-white/10 rounded-xl py-2.5 pl-10 pr-3 outline-none focus:ring-2 focus:ring-white/20" />
          <span class="absolute left-3 top-2.5 opacity-70">🔎</span>
        </label>
      </form>
    </div>
  </header>

  <main class="max-w-7xl mx-auto px-4 py-6">
    {% if error_message %}
      <!-- Error Message Block -->
      <div class="bg-red-900/50 border border-red-500/50 text-red-200 rounded-xl p-6 text-center">
        <h2 class="text-2xl font-bold mb-2">কনফিগারেশন সমস্যা!</h2>
        <p>{{ error_message }}</p>
      </div>
    {% else %}
      <!-- Banners -->
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

      <!-- Section Title -->
      <section class="mb-4 flex items-center justify-between">
        <h3 class="text-xl md:text-2xl font-bold">
          {% if query %}Results for “{{ query }}”{% else %}Trending This Week{% endif %}
        </h3>
        {% if not query %}
        <a href="{{ url_for('search') }}" class="text-sm underline decoration-dotted opacity-80 hover:opacity-100">Try a search</a>
        {% endif %}
      </section>

      <!-- Poster Grid -->
      {% if movies and movies|length > 0 %}
      <section class="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-5 lg:grid-cols-6 gap-4">
        {% for m in movies %}
        <a href="https://www.themoviedb.org/movie/{{ m.tmdb_id }}" target="_blank" rel="noopener"
           class="group rounded-2xl overflow-hidden bg-white/5 border border-white/10 hover:border-white/20 hover:bg-white/10 transition">
          <div class="relative">
            <img src="{{ m.poster }}" alt="{{ m.title }}" class="w-full aspect-[2/3] object-cover" />
            <div class="absolute inset-0 opacity-0 group-hover:opacity-100 transition bg-black/40"></div>
          </div>
          <div class="p-2">
            <p class="text-sm font-semibold line-clamp-2">{{ m.title }}</p>
            <p class="text-xs text-white/60 mt-0.5">{{ m.year }}</p>
          </div>
        </a>
        {% endfor %}
      </section>
      {% else %}
        <div class="text-center py-10 text-white/70">No movies found. Please try a different search.</div>
      {% endif %}
    {% endif %}
  </main>

  <footer class="max-w-7xl mx-auto px-4 py-8 text-center text-xs text-white/50">
    <div>© {{ year }} Movie Zone • Powered by The Movie Database (TMDB)</div>
  </footer>
</body>
</html>
"""

# ========= DATA MAPPING HELPERS =========
def map_movies(items):
    mapped = []
    for m in items or []:
        poster_path = m.get("poster_path")
        bd_path = m.get("backdrop_path")
        title = m.get("title") or m.get("name") or "Untitled"
        date  = m.get("release_date") or m.get("first_air_date") or ""
        mapped.append({
            "tmdb_id": m.get("id"),
            "title": title,
            "year": date[:4] if date else "N/A",
            "poster": f"{IMG_POSTER}{poster_path}" if poster_path else "https://via.placeholder.com/500x750?text=No+Image",
            "backdrop": f"{IMG_BANNER}{bd_path}" if bd_path else None,
            "overview": m.get("overview") or "",
        })
    return mapped

def pick_banners(movie_list, need=2):
    banners = []
    for m in movie_list:
        if m.get("backdrop"):
            banners.append({
                "src": m["backdrop"],
                "title": m["title"],
                "overview": m["overview"]
            })
        if len(banners) >= need:
            break
    # Placeholder যুক্ত করা হয়েছে
    while len(banners) < need and len(banners) < 2:
        banners.append({
            "src": "https://via.placeholder.com/1280x720/111827/FFFFFF?text=Movie+Zone",
            "title": "Welcome to Movie Zone",
            "overview": "Find your next favorite movie."
        })
    return banners

# ========= ROUTES =========
@app.route("/")
def home():
    # API কী সেট করা না থাকলে ইউজারকে একটি এরর মেসেজ দেখানো হবে
    if not TMDB_API_KEY:
        return render_template_string(
            PAGE_TEMPLATE,
            title="Configuration Error",
            error_message="TMDB API Key is not configured. Please set the TMDB_API_KEY environment variable.",
            year=time.strftime("%Y")
        )
        
    trending = map_movies(get_trending_movies())
    banners = pick_banners(trending, need=2)
    movies = trending

    return render_template_string(
        PAGE_TEMPLATE,
        title="Movie Zone • Home",
        banners=banners,
        movies=movies,
        query=None,
        year=time.strftime("%Y")
    )

@app.route("/search")
def search():
    q = (request.args.get("q") or "").strip()
    if not q:
        return redirect(url_for("home"))

    # এখানেও API কী চেক করা হচ্ছে, যদিও tmdb_get() এটি সামলাতে পারে
    if not TMDB_API_KEY:
        return redirect(url_for('home')) # সরাসরি হোমে পাঠিয়ে দেওয়া হচ্ছে

    results = map_movies(search_movies(q))
    banners = pick_banners(results, need=2)

    return render_template_string(
        PAGE_TEMPLATE,
        title=f"Search • {q}",
        banners=banners,
        movies=results,
        query=q,
        year=time.strftime("%Y")
    )

# ========= MAIN =========
if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
