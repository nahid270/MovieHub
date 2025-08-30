import os
import sys
import requests
from flask import Flask, render_template_string, request, redirect, url_for, Response, jsonify
from pymongo import MongoClient
from bson.objectid import ObjectId
from functools import wraps
from urllib.parse import unquote, quote

# --- Environment Variables ---
MONGO_URI = os.environ.get("MONGO_URI", "mongodb+srv://mewayo8672:mewayo8672@cluster0.ozhvczp.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0")
TMDB_API_KEY = os.environ.get("TMDB_API_KEY", "7dc544d9253bccc3cfecc1c677f69819")
ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "Nahid")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "270")
WEBSITE_NAME = os.environ.get("WEBSITE_NAME", "MovieZonehub")

# --- Validate Environment Variables ---
if not all([MONGO_URI, TMDB_API_KEY, ADMIN_USERNAME, ADMIN_PASSWORD]):
    print("FATAL: One or more required environment variables are missing.")
    if os.environ.get('VERCEL') != '1':
        sys.exit(1)

# --- App Initialization ---
PLACEHOLDER_POSTER = "https://via.placeholder.com/400x600.png?text=Poster+Not+Found"
PREDEFINED_CATEGORIES = ["Bengali", "Hindi", "English", "18+ Adult Zone", "Trending"]
app = Flask(__name__)

# --- Authentication ---
def check_auth(username, password):
    return username == ADMIN_USERNAME and password == ADMIN_PASSWORD

def authenticate():
    return Response('Could not verify your access level.', 401, {'WWW-Authenticate': 'Basic realm="Login Required"'})

def requires_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth = request.authorization
        if not auth or not check_auth(auth.username, auth.password):
            return authenticate()
        return f(*args, **kwargs)
    return decorated

# --- Database Connection ---
try:
    client = MongoClient(MONGO_URI)
    db = client["movie_db"]
    movies = db["movies"]
    settings = db["settings"]
    print("SUCCESS: Successfully connected to MongoDB!")
except Exception as e:
    print(f"FATAL: Error connecting to MongoDB: {e}.")
    if os.environ.get('VERCEL') != '1':
        sys.exit(1)

@app.context_processor
def inject_globals():
    ad_settings = settings.find_one({"_id": "ad_config"})
    return dict(
        website_name=WEBSITE_NAME,
        ad_settings=ad_settings or {},
        predefined_categories=PREDEFINED_CATEGORIES,
        # [FIXED] The 'quote' function is needed by the detail_html template.
        # This was accidentally removed in the previous version.
        quote=quote
    )

# =========================================================================================
# === [START] HTML TEMPLATES ============================================================
# =========================================================================================
index_html = """
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8" /><meta name="viewport" content="width=device-width, initial-scale=1.0" />
<title>{{ website_name }} - Your Entertainment Hub</title>
<link rel="icon" href="https://img.icons8.com/fluency/48/cinema-.png" type="image/png">
<meta name="description" content="Watch and download the latest movies and series on {{ website_name }}. Your ultimate entertainment hub.">
<meta name="keywords" content="movies, series, download, watch online, {{ website_name }}, bengali movies, hindi movies, english movies">
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin><link href="https://fonts.googleapis.com/css2?family=Poppins:wght@300;400;500;600;700&display=swap" rel="stylesheet">
<link rel="stylesheet" href="https://unpkg.com/swiper/swiper-bundle.min.css"/>
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.2.0/css/all.min.css">
{{ ad_settings.ad_header | safe }}
<style>
  :root {--primary-color: #E50914;--bg-color: #0c0c0c;--card-bg: #1a1a1a;--text-light: #ffffff;--text-dark: #a0a0a0;--nav-height: 70px;}
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {font-family: 'Poppins', sans-serif;background-color: var(--bg-color);color: var(--text-light);overflow-x: hidden;}
  a { text-decoration: none; color: inherit; }
  img { max-width: 100%; display: block; }
  .container { max-width: 1400px; margin: 0 auto; padding: 0 20px; }
  ::-webkit-scrollbar { width: 8px; } ::-webkit-scrollbar-track { background: #222; } ::-webkit-scrollbar-thumb { background: #555; border-radius: 4px; } ::-webkit-scrollbar-thumb:hover { background: var(--primary-color); }
  .main-header { position: fixed; top: 0; left: 0; width: 100%; height: var(--nav-height); display: flex; align-items: center; z-index: 1000; transition: background-color 0.3s ease; background: linear-gradient(to bottom, rgba(0,0,0,0.8), transparent); }
  .main-header.scrolled { background-color: var(--bg-color); }
  .header-content { display: flex; justify-content: space-between; align-items: center; width: 100%; }
  .logo { font-size: 2rem; font-weight: 700; color: var(--primary-color); }
  .nav-links { display: flex; gap: 30px; }
  .nav-links a { font-weight: 500; transition: color 0.2s ease; }
  .nav-links a:hover, .nav-links a.active { color: var(--primary-color); }
  .search-form { display: flex; align-items: center; background-color: rgba(255,255,255,0.1); border-radius: 50px; padding: 5px; }
  .search-input { background: transparent; border: none; color: var(--text-light); padding: 5px 10px; width: 220px; font-size: 0.9rem; }
  .search-input:focus { outline: none; }
  .search-btn { background: var(--primary-color); border: none; color: var(--text-light); border-radius: 50%; width: 30px; height: 30px; cursor: pointer; display:grid; place-items:center; }
  .menu-toggle { display: none; font-size: 1.8rem; cursor: pointer; background: none; border: none; color: white; z-index: 1001;}
  .hero-slider {width: 100%;margin-top: var(--nav-height);aspect-ratio: 16 / 9; max-height: 600px; border-radius: 12px; overflow: hidden; }
  .hero-slide {position: relative;display: flex;align-items: flex-end;justify-content: flex-start;}
  .hero-bg-img {position: absolute;top: 0;left: 0;width: 100%;height: 100%;object-fit: cover;object-position: center;}
  .hero-slide::before {content: '';position: absolute;top: 0;left: 0;width: 100%;height: 100%;background: linear-gradient(to top, rgba(0,0,0,0.9) 0%, rgba(0,0,0,0.6) 25%, transparent 60%);}
  .hero-content {position: relative;z-index: 2;padding: 20px 40px;width: 100%;}
  .hero-title {font-size: 2.2rem;font-weight: 600;line-height: 1.2;margin: 0;}
  .hero-meta {font-size: 0.9rem;color: var(--text-dark);margin-top: 5px;}
  .slide-type-tag {position: absolute;top: 20px;right: 20px;background-color: var(--primary-color);color: white;padding: 5px 12px;border-radius: 5px;font-size: 0.8rem;font-weight: 600;z-index: 3;text-transform: uppercase;}
  .swiper-pagination-bullet {background: rgba(255,255,255,0.5);}
  .swiper-pagination-bullet-active {background: var(--primary-color);width: 20px;border-radius: 5px;}
  .category-section { margin: 50px 0; }
  .category-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; }
  .category-title { font-size: 1.8rem; font-weight: 600; }
  .view-all-link { font-size: 0.9rem; color: var(--text-dark); font-weight: 500; }
  .movie-carousel .swiper-slide { width: auto; }
  .movie-card { display: block; position: relative; }
  .movie-poster { width: 220px; aspect-ratio: 2 / 3; object-fit: cover; border-radius: 8px; margin-bottom: 10px; transition: transform 0.3s ease, box-shadow 0.3s ease; }
  .movie-card:hover .movie-poster { transform: scale(1.05); box-shadow: 0 10px 25px rgba(0,0,0,0.5); }
  .card-title { font-size: 1rem; font-weight: 500; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .card-meta { font-size: 0.8rem; color: var(--text-dark); }
  .language-tag { position: absolute; top: 10px; left: 10px; background-color: var(--primary-color); color: white; padding: 4px 10px; border-radius: 5px; font-size: 0.75rem; font-weight: 600; z-index: 2; text-transform: uppercase; }
  .swiper-button-next, .swiper-button-prev { color: var(--text-light); }
  .full-page-grid-container { padding: 120px 40px 50px; }
  .full-page-grid-title { font-size: 2.5rem; font-weight: 700; margin-bottom: 30px; }
  .full-page-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 30px 20px; }
  .full-page-grid .movie-poster { width: 100%; }
  .main-footer { background-color: #111; padding: 30px 40px; text-align: center; color: var(--text-dark); margin-top: 50px; }
  .ad-container { margin: 20px auto; width: 100%; max-width: 100%; display: flex; justify-content: center; align-items: center; overflow: hidden; min-height: 50px; text-align: center; }
  .ad-container > * { max-width: 100% !important; }
  .mobile-nav-menu {position: fixed;top: 0;left: 0;width: 100%;height: 100%;background-color: var(--bg-color);z-index: 9999;display: flex;flex-direction: column;align-items: center;justify-content: center;transform: translateX(-100%);transition: transform 0.3s ease-in-out;}
  .mobile-nav-menu.active {transform: translateX(0);}
  .mobile-nav-menu .close-btn {position: absolute;top: 20px;right: 20px;font-size: 2.5rem;color: white;background: none;border: none;cursor: pointer;}
  .mobile-links {display: flex;flex-direction: column;text-align: center;gap: 25px;}
  .mobile-links a {font-size: 1.5rem;font-weight: 500;color: var(--text-light);transition: color 0.2s;}
  .mobile-links a:hover {color: var(--primary-color);}
  .mobile-links hr {width: 50%;border-color: #333;margin: 10px auto;}
  .bottom-nav {display: none; position: fixed; bottom: 0; left: 0; right: 0; height: 60px; background-color: #181818; box-shadow: 0 -2px 10px rgba(0,0,0,0.5); z-index: 1000; display: flex; justify-content: space-around; align-items: center;}
  .bottom-nav .nav-item { display: flex; flex-direction: column; align-items: center; justify-content: center; color: var(--text-dark); background: none; border: none; font-size: 10px; flex-grow: 1; }
  .bottom-nav .nav-item i { font-size: 20px; margin-bottom: 4px; }
  .bottom-nav .nav-item.active, .bottom-nav .nav-item:hover { color: var(--primary-color); }
  .search-overlay { position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.95); z-index: 10000; display: none; flex-direction: column; padding: 20px; }
  .search-overlay.active { display: flex; }
  .search-container { width: 100%; max-width: 800px; margin: 0 auto; }
  .close-search-btn { position: absolute; top: 20px; right: 20px; font-size: 2.5rem; color: white; background: none; border: none; cursor: pointer; }
  #search-input-live { width: 100%; padding: 15px; font-size: 1.2rem; border-radius: 8px; border: 2px solid var(--primary-color); background: var(--card-bg); color: white; margin-top: 60px; }
  #search-results-live { margin-top: 20px; max-height: calc(100vh - 150px); overflow-y: auto; display: grid; grid-template-columns: repeat(auto-fill, minmax(120px, 1fr)); gap: 15px; }
  .search-result-item { color: white; text-align: center; }
  .search-result-item img { width: 100%; aspect-ratio: 2/3; object-fit: cover; border-radius: 5px; margin-bottom: 5px; }
  @media (max-width: 992px) {.nav-links, .search-form { display: none; } .menu-toggle { display: block; } .container { padding: 0 20px; } }
  @media (max-width: 768px) {
    body { padding-bottom: 60px; }
    .main-header .search-form, .main-header .nav-links { display: none; }
    .bottom-nav { display: flex; }
    .full-page-grid-container{padding-top:100px;padding-bottom:40px;} 
    .logo { font-size: 1.5rem; } 
    .hero-slider { margin-top: calc(var(--nav-height) + 10px); aspect-ratio: 16 / 10; }
    .hero-content { padding: 15px 20px; } .hero-title { font-size: 1.5rem; } .hero-meta { font-size: 0.8rem; }
    .slide-type-tag { font-size: 0.7rem; padding: 4px 10px; top: 15px; right: 15px; }
    .category-title { font-size: 1.4rem; } .movie-poster { width: 160px; } 
    .full-page-grid { grid-template-columns: repeat(auto-fill, minmax(140px, 1fr)); } 
  }
  @media (min-width: 769px) { .bottom-nav { display: none; } }
</style>
</head>
<body>
{{ ad_settings.ad_body_top | safe }}
<header class="main-header">
    <div class="container header-content">
        <a href="{{ url_for('home') }}" class="logo">{{ website_name }}</a>
        <nav class="nav-links">
            <a href="{{ url_for('home') }}" class="active">Home</a>
            <a href="{{ url_for('all_movies') }}">Movies</a>
            <a href="{{ url_for('all_series') }}">Series</a>
        </nav>
        <form method="GET" action="/" class="search-form">
            <input type="search" name="q" class="search-input" placeholder="Search..." value="{{ query|default('') }}">
            <button class="search-btn" type="submit"><i class="fas fa-search"></i></button>
        </form>
        <button class="menu-toggle"><i class="fas fa-bars"></i></button>
    </div>
</header>
<div class="mobile-nav-menu">
    <button class="close-btn">&times;</button>
    <div class="mobile-links">
        <a href="{{ url_for('home') }}">Home</a>
        <a href="{{ url_for('all_movies') }}">All Movies</a>
        <a href="{{ url_for('all_series') }}">All Series</a>
        <hr>
        <!-- [FIXED] Changed to use query parameter `name` for robust linking -->
        {% for cat in predefined_categories %}<a href="{{ url_for('movies_by_category', name=cat) }}">{{ cat }}</a>{% endfor %}
    </div>
</div>
<main>
  {% macro render_movie_card(m) %}
    <a href="{{ url_for('movie_detail', movie_id=m._id) }}" class="movie-card">
      {% if m.language %}<span class="language-tag">{{ m.language }}</span>{% endif %}
      <img class="movie-poster" loading="lazy" src="{{ m.poster or 'https://via.placeholder.com/400x600.png?text=No+Image' }}" alt="{{ m.title }}">
      <h4 class="card-title">{{ m.title }}</h4>
      <p class="card-meta">{{ m.release_date.split('-')[0] if m.release_date else '' }}</p>
    </a>
  {% endmacro %}
  {% if is_full_page_list %}
    <div class="full-page-grid-container">
        <h2 class="full-page-grid-title">{{ query }}</h2>
        {% if movies|length == 0 %}<p>No content found.</p>
        {% else %}<div class="full-page-grid">{% for m in movies %}{{ render_movie_card(m) }}{% endfor %}</div>{% endif %}
    </div>
  {% else %}
    <div class="container">
      <div class="swiper hero-slider">
          <div class="swiper-wrapper">
          {% for movie in recently_added %}{% if movie.backdrop %}
              <div class="swiper-slide hero-slide">
                  <a href="{{ url_for('movie_detail', movie_id=movie._id) }}" style="position:absolute; width:100%; height:100%; z-index:2;"></a>
                  <img src="{{ movie.backdrop }}" alt="{{ movie.title }}" class="hero-bg-img">
                  <div class="slide-type-tag">{{ movie.type | title }}</div>
                  <div class="hero-content">
                      <h2 class="hero-title">{{ movie.title }} {% if movie.language %} [{{ movie.language }}] {% endif %}</h2>
                      {% if movie.release_date %}<p class="hero-meta">{{ movie.release_date.split('-')[0] }}</p>{% endif %}
                  </div>
              </div>
          {% endif %}{% endfor %}
          </div>
          <div class="swiper-pagination"></div>
      </div>
    </div>
    <div class="container">
    {% macro render_carousel_section(title, movies_list, cat_name) %}
        {% if movies_list %}
        <section class="category-section">
            <div class="category-header">
                <h2 class="category-title">{{ title }}</h2>
                <!-- [FIXED] Changed to use query parameter `name` for robust linking -->
                <a href="{{ url_for('movies_by_category', name=cat_name) }}" class="view-all-link">View All</a>
            </div>
            <div class="swiper movie-carousel">
                <div class="swiper-wrapper">
                    {% for m in movies_list %}<div class="swiper-slide">{{ render_movie_card(m) }}</div>{% endfor %}
                </div>
                <div class="swiper-button-next"></div><div class="swiper-button-prev"></div>
            </div>
        </section>
        {% endif %}
    {% endmacro %}
    {{ render_carousel_section('Trending Now', categorized_content['Trending'], 'Trending') }}
    {{ render_carousel_section('Latest Movies', latest_movies, 'Latest Movies') }}
    {{ render_carousel_section('Latest Series', latest_series, 'Latest Series') }}
    {% if ad_settings.ad_list_page %}<div class="ad-container">{{ ad_settings.ad_list_page | safe }}</div>{% endif %}
    {% for cat_name, movies_list in categorized_content.items() %}
        {% if cat_name != 'Trending' %}{{ render_carousel_section(cat_name, movies_list, cat_name) }}{% endif %}
    {% endfor %}
    </div>
  {% endif %}
</main>
<footer class="main-footer">
    <p>&copy; 2024 {{ website_name }}. All Rights Reserved.</p>
</footer>
<nav class="bottom-nav">
  <a href="{{ url_for('home') }}" class="nav-item active"><i class="fas fa-home"></i><span>Home</span></a>
  <a href="{{ url_for('all_movies') }}" class="nav-item"><i class="fas fa-film"></i><span>Movies</span></a>
  <button id="live-search-btn" class="nav-item"><i class="fas fa-search"></i><span>Search</span></button>
  <a href="{{ url_for('all_series') }}" class="nav-item"><i class="fas fa-tv"></i><span>Series</span></a>
  <a href="https://t.me/Movie_Request_Group_23" target="_blank" class="nav-item"><i class="fab fa-telegram-plane"></i><span>Join Us</span></a>
</nav>
<div id="search-overlay" class="search-overlay">
  <button id="close-search-btn" class="close-search-btn">&times;</button>
  <div class="search-container">
    <input type="text" id="search-input-live" placeholder="Type to search for movies or series..." autocomplete="off">
    <div id="search-results-live"><p style="color: #555; text-align: center;">Start typing to see results</p></div>
  </div>
</div>
<script src="https://unpkg.com/swiper/swiper-bundle.min.js"></script>
<script>
    const header = document.querySelector('.main-header');
    window.addEventListener('scroll', () => { window.scrollY > 50 ? header.classList.add('scrolled') : header.classList.remove('scrolled'); });
    new Swiper('.hero-slider', { loop: true, autoplay: { delay: 4000 }, pagination: { el: '.swiper-pagination', clickable: true }, });
    new Swiper('.movie-carousel', { slidesPerView: 'auto', spaceBetween: 20, navigation: { nextEl: '.swiper-button-next', prevEl: '.swiper-button-prev', }, breakpoints: { 320: { spaceBetween: 15 }, 768: { spaceBetween: 20 }, } });
    const menuToggle = document.querySelector('.menu-toggle');
    const mobileMenu = document.querySelector('.mobile-nav-menu');
    const closeBtn = document.querySelector('.close-btn');
    if (menuToggle && mobileMenu && closeBtn) {
        menuToggle.addEventListener('click', () => { mobileMenu.classList.add('active'); });
        closeBtn.addEventListener('click', () => { mobileMenu.classList.remove('active'); });
        const mobileLinks = document.querySelectorAll('.mobile-links a');
        mobileLinks.forEach(link => { link.addEventListener('click', () => { mobileMenu.classList.remove('active'); }); });
    }
    const liveSearchBtn = document.getElementById('live-search-btn');
    const searchOverlay = document.getElementById('search-overlay');
    const closeSearchBtn = document.getElementById('close-search-btn');
    const searchInputLive = document.getElementById('search-input-live');
    const searchResultsLive = document.getElementById('search-results-live');
    let debounceTimer;
    liveSearchBtn.addEventListener('click', () => { searchOverlay.classList.add('active'); searchInputLive.focus(); });
    closeSearchBtn.addEventListener('click', () => { searchOverlay.classList.remove('active'); });
    searchInputLive.addEventListener('input', () => {
        clearTimeout(debounceTimer);
        debounceTimer = setTimeout(() => {
            const query = searchInputLive.value.trim();
            if (query.length > 1) {
                searchResultsLive.innerHTML = '<p style="color: #555; text-align: center;">Searching...</p>';
                fetch(`/api/search?q=${encodeURIComponent(query)}`)
                    .then(response => response.json())
                    .then(data => {
                        let html = '';
                        if (data.length > 0) {
                            data.forEach(item => {
                                html += `<a href="/movie/${item._id}" class="search-result-item"><img src="${item.poster}" alt="${item.title}"><span>${item.title}</span></a>`;
                            });
                        } else {
                            html = '<p style="color: #555; text-align: center;">No results found.</p>';
                        }
                        searchResultsLive.innerHTML = html;
                    });
            } else {
                searchResultsLive.innerHTML = '<p style="color: #555; text-align: center;">Start typing to see results</p>';
            }
        }, 300);
    });
</script>
{{ ad_settings.ad_footer | safe }}
</body></html>
"""
detail_html = """
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8" /><meta name="viewport" content="width=device-width, initial-scale=1.0" />
<title>{{ movie.title if movie else "Content Not Found" }} - {{ website_name }}</title>
<link rel="icon" href="https://img.icons8.com/fluency/48/cinema-.png" type="image/png">
<meta name="description" content="{{ movie.overview|striptags|truncate(160) }}">
<meta name="keywords" content="{{ movie.title }}, movie details, download {{ movie.title }}, {{ website_name }}">
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin><link href="https://fonts.googleapis.com/css2?family=Poppins:wght@300;400;500;600;700&display=swap" rel="stylesheet">
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.2.0/css/all.min.css">
{{ ad_settings.ad_header | safe }}
<style>
  :root {--primary-color: #E50914; --watch-color: #007bff; --bg-color: #0c0c0c;--card-bg: #1a1a1a;--text-light: #ffffff;--text-dark: #a0a0a0;}
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: 'Poppins', sans-serif; background-color: var(--bg-color); color: var(--text-light); }
  a { text-decoration: none; color: inherit; }
  .container { max-width: 1200px; margin: 0 auto; padding: 0 40px; }
  .detail-hero { position: relative; padding: 120px 0 60px; min-height: 70vh; display: flex; align-items: center; }
  .hero-background { position: absolute; top: 0; left: 0; width: 100%; height: 100%; object-fit: cover; filter: blur(15px) brightness(0.3); transform: scale(1.1); }
  .detail-hero::after { content: ''; position: absolute; top: 0; left: 0; width: 100%; height: 100%; background: linear-gradient(to top, var(--bg-color) 0%, rgba(12,12,12,0.7) 40%, transparent 100%); }
  .detail-content { position: relative; z-index: 2; display: flex; gap: 40px; }
  .detail-poster { width: 300px; height: 450px; flex-shrink: 0; border-radius: 12px; object-fit: cover; box-shadow: 0 10px 30px rgba(0,0,0,0.5); }
  .detail-info { max-width: 700px; }
  .detail-title { font-size: 3rem; font-weight: 700; line-height: 1.2; margin-bottom: 15px; }
  .detail-meta { display: flex; flex-wrap: wrap; gap: 10px 20px; color: var(--text-dark); margin-bottom: 20px; font-size: 0.9rem; }
  .meta-item { display: flex; align-items: center; gap: 8px; }
  .meta-item.rating { color: #f5c518; font-weight: 600; }
  .detail-overview { font-size: 1rem; line-height: 1.7; color: var(--text-dark); margin-bottom: 30px; }
  .action-btn { display: inline-flex; align-items: center; justify-content: center; gap: 10px; padding: 12px 25px; border-radius: 50px; font-weight: 600; transition: all 0.2s ease; text-align: center; }
  .btn-download { background-color: var(--primary-color); } .btn-download:hover { transform: scale(1.05); }
  .btn-watch { background-color: var(--watch-color); } .btn-watch:hover { transform: scale(1.05); }
  .tabs-container { margin: 40px 0; }
  .tabs-nav { display: flex; flex-wrap: wrap; border-bottom: 1px solid #333; }
  .tab-link { padding: 15px 30px; cursor: pointer; font-weight: 500; color: var(--text-dark); position: relative; }
  .tab-link.active { color: var(--text-light); }
  .tab-link.active::after { content: ''; position: absolute; bottom: -1px; left: 0; width: 100%; height: 2px; background-color: var(--primary-color); }
  .tabs-content { padding: 30px 0; }
  .tab-pane { display: none; }
  .tab-pane.active { display: block; }
  .link-group { margin-bottom: 30px; text-align: center; }
  .link-group h3 { font-size: 1.2rem; font-weight: 500; margin-bottom: 20px; }
  .link-buttons { display: inline-flex; flex-wrap: wrap; gap: 15px; justify-content: center;}
  .quality-group { margin-bottom: 20px; }
  .quality-group h4 { margin-bottom: 10px; color: var(--text-dark); }
  .episode-list { display: flex; flex-direction: column; gap: 10px; }
  .episode-item { display: flex; justify-content: space-between; align-items: center; background-color: var(--card-bg); padding: 15px; border-radius: 8px; }
  .episode-name { font-weight: 500; }
  .ad-container { margin: 20px auto; width: 100%; max-width: 100%; display: flex; justify-content: center; align-items: center; overflow: hidden; min-height: 50px; text-align: center; }
  .ad-container > * { max-width: 100% !important; }
  @media (max-width: 768px) {
    .container { padding: 0 20px; }
    .detail-hero { padding: 100px 0 40px; }
    .detail-content { flex-direction: column; align-items: center; text-align: center; }
    .detail-poster { width: 60%; max-width: 250px; height: auto; }
    .detail-title { font-size: 2rem; }
    .detail-meta { justify-content: center; }
    .tab-link { padding: 12px 15px; font-size: 0.9rem; }
    .episode-item { flex-direction: column; gap: 10px; align-items: flex-start; }
  }
</style>
</head>
<body>
{{ ad_settings.ad_body_top | safe }}
{% if movie %}
<div class="detail-hero">
    <img src="{{ movie.backdrop or movie.poster }}" class="hero-background" alt="">
    <div class="container detail-content">
        <img src="{{ movie.poster or 'https://via.placeholder.com/400x600.png?text=No+Image' }}" alt="{{ movie.title }}" class="detail-poster">
        <div class="detail-info">
            <h1 class="detail-title">{{ movie.title }}</h1>
            <div class="detail-meta">
                {% if movie.vote_average %}<div class="meta-item rating"><i class="fas fa-star"></i> {{ "%.1f"|format(movie.vote_average) }}</div>{% endif %}
                {% if movie.release_date %}<div class="meta-item"><i class="fas fa-calendar-alt"></i> {{ movie.release_date.split('-')[0] }}</div>{% endif %}
                {% if movie.language %}<div class="meta-item"><i class="fas fa-language"></i> {{ movie.language }}</div>{% endif %}
                {% if movie.genres %}<div class="meta-item"><i class="fas fa-tag"></i> {{ movie.genres | join(' / ') }}</div>{% endif %}
            </div>
            <p class="detail-overview">{{ movie.overview }}</p>
        </div>
    </div>
</div>
<div class="container">
    <div class="tabs-container">
        <nav class="tabs-nav">
            <div class="tab-link active" data-tab="downloads"><i class="fas fa-download"></i> Links</div>
            {% if movie.type == 'series' and movie.episodes %}
                {% for season_num in movie.episodes | map(attribute='season') | unique | sort %}
                <div class="tab-link" data-tab="season-{{ season_num }}">Season {{ season_num }}</div>
                {% endfor %}
            {% endif %}
        </nav>
        <div class="tabs-content">
            <div class="tab-pane active" id="downloads">
                {% if ad_settings.ad_detail_page %}<div class="ad-container">{{ ad_settings.ad_detail_page | safe }}</div>{% endif %}
                {% if movie.type == 'movie' %}
                    {% if movie.links %}
                    <div class="link-group">
                        <h3>Watch & Download Links</h3>
                        {% for link_item in movie.links %}
                        <div class="quality-group">
                            <h4>{{ link_item.quality }}</h4>
                            <div class="link-buttons">
                                {% if link_item.watch_url %}<a href="{{ url_for('wait_page', target=quote(link_item.watch_url)) }}" class="action-btn btn-watch"><i class="fas fa-play"></i> Watch Now</a>{% endif %}
                                {% if link_item.download_url %}<a href="{{ url_for('wait_page', target=quote(link_item.download_url)) }}" class="action-btn btn-download"><i class="fas fa-download"></i> Download</a>{% endif %}
                            </div>
                        </div>
                        {% endfor %}
                    </div>
                    {% else %}<p style="text-align:center;">No links available yet.</p>
                    {% endif %}
                {% elif movie.type == 'series' %}<p style="text-align:center;">Please select a season tab to view episode links.</p>
                {% else %}<p style="text-align:center;">No links available.</p>
                {% endif %}
            </div>
            {% if movie.type == 'series' and movie.episodes %}
                {% for season_num in movie.episodes | map(attribute='season') | unique | sort %}
                <div class="tab-pane" id="season-{{ season_num }}"><div class="episode-list">
                    {% for ep in movie.episodes | selectattr('season', 'equalto', season_num) | sort(attribute='episode_number') %}
                    <div class="episode-item">
                        <span class="episode-name"><i class="fas fa-play-circle"></i> Episode {{ ep.episode_number }} {% if ep.title %}- {{ep.title}}{% endif %}</span>
                        {% if ep.watch_link %}<a href="{{ url_for('wait_page', target=quote(ep.watch_link)) }}" class="action-btn btn-download">Download / Watch</a>{% endif %}
                    </div>
                    {% endfor %}
                </div></div>
                {% endfor %}
            {% endif %}
        </div>
    </div>
</div>
{% else %}<div style="display:flex; justify-content:center; align-items:center; height:100vh;"><h2>Content not found.</h2></div>{% endif %}
<script>
    const tabLinks = document.querySelectorAll('.tab-link'), tabPanes = document.querySelectorAll('.tab-pane');
    tabLinks.forEach(link => { link.addEventListener('click', () => {
        const tabId = link.getAttribute('data-tab');
        tabLinks.forEach(item => item.classList.remove('active'));
        tabPanes.forEach(pane => pane.classList.remove('active'));
        link.classList.add('active');
        document.getElementById(tabId).classList.add('active');
    }); });
</script>
{{ ad_settings.ad_footer | safe }}
</body></html>
"""
wait_page_html = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Generating Link... - {{ website_name }}</title>
    <link rel="icon" href="https://img.icons8.com/fluency/48/cinema-.png" type="image/png">
    <meta name="robots" content="noindex, nofollow">
    <link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin><link href="https://fonts.googleapis.com/css2?family=Poppins:wght@400;500;700&display=swap" rel="stylesheet">
    {{ ad_settings.ad_header | safe }}
    <style>
        :root {--primary-color: #E50914; --bg-color: #0c0c0c; --text-light: #ffffff; --text-dark: #a0a0a0;}
        body { font-family: 'Poppins', sans-serif; background-color: var(--bg-color); color: var(--text-light); display: flex; flex-direction: column; justify-content: center; align-items: center; min-height: 100vh; text-align: center; margin: 0; padding: 20px;}
        .wait-container { background-color: #1a1a1a; padding: 40px; border-radius: 12px; max-width: 500px; width: 100%; box-shadow: 0 10px 30px rgba(0,0,0,0.5); }
        h1 { font-size: 1.8rem; color: var(--primary-color); margin-bottom: 20px; }
        p { color: var(--text-dark); margin-bottom: 30px; font-size: 1rem; }
        .timer { font-size: 2.5rem; font-weight: 700; color: var(--text-light); margin-bottom: 30px; }
        .get-link-btn { display: inline-block; text-decoration: none; color: white; font-weight: 600; cursor: pointer; border: none; padding: 12px 30px; border-radius: 50px; font-size: 1rem; background-color: #555; transition: background-color 0.2s; }
        .get-link-btn.ready { background-color: var(--primary-color); }
        .ad-container { margin: 30px auto 0; width: 100%; max-width: 100%; display: flex; justify-content: center; align-items: center; overflow: hidden; min-height: 50px; text-align: center; }
        .ad-container > * { max-width: 100% !important; }
    </style>
</head>
<body>
    {{ ad_settings.ad_body_top | safe }}
    <div class="wait-container">
        <h1>Please Wait</h1>
        <p>Your download link is being generated. You will be redirected automatically.</p>
        <div class="timer">Please wait <span id="countdown">5</span> seconds...</div>
        <a id="get-link-btn" class="get-link-btn" href="#">Generating Link...</a>
        {% if ad_settings.ad_wait_page %}<div class="ad-container">{{ ad_settings.ad_wait_page | safe }}</div>{% endif %}
    </div>
    <script>
        (function() {
            let timeLeft = 5;
            const countdownElement = document.getElementById('countdown');
            const linkButton = document.getElementById('get-link-btn');
            const targetUrl = "{{ target_url | safe }}";
            const timer = setInterval(() => {
                if (timeLeft <= 0) {
                    clearInterval(timer);
                    countdownElement.parentElement.textContent = "Your link is ready!";
                    linkButton.classList.add('ready');
                    linkButton.textContent = 'Click Here to Proceed';
                    linkButton.href = targetUrl;
                    window.location.href = targetUrl;
                } else {
                    countdownElement.textContent = timeLeft;
                }
                timeLeft--;
            }, 1000);
        })();
    </script>
    {{ ad_settings.ad_footer | safe }}
</body>
</html>
"""
admin_html = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Admin Panel - {{ website_name }}</title>
    <link rel="icon" href="https://img.icons8.com/fluency/48/cinema-.png" type="image/png">
    <meta name="robots" content="noindex, nofollow">
    <link href="https://fonts.googleapis.com/css2?family=Bebas+Neue&family=Roboto:wght@400;700&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.2.0/css/all.min.css">
    <style>
        :root { --netflix-red: #E50914; --netflix-black: #141414; --dark-gray: #222; --light-gray: #333; --text-light: #f5f5f5; }
        body { font-family: 'Roboto', sans-serif; background: var(--netflix-black); color: var(--text-light); margin: 0; padding: 20px; }
        .admin-container { max-width: 1000px; margin: 20px auto; }
        .admin-header { display: flex; align-items: center; justify-content: space-between; border-bottom: 2px solid var(--netflix-red); padding-bottom: 10px; margin-bottom: 30px; }
        .admin-header h1 { font-family: 'Bebas Neue', sans-serif; font-size: 3rem; color: var(--netflix-red); margin: 0; }
        h2 { font-family: 'Bebas Neue', sans-serif; color: var(--netflix-red); font-size: 2.2rem; margin-top: 40px; margin-bottom: 20px; border-left: 4px solid var(--netflix-red); padding-left: 15px; }
        form { background: var(--dark-gray); padding: 25px; border-radius: 8px; }
        fieldset { border: 1px solid var(--light-gray); border-radius: 5px; padding: 20px; margin-bottom: 20px; }
        legend { font-weight: bold; color: var(--netflix-red); padding: 0 10px; font-size: 1.2rem; }
        .form-group { margin-bottom: 15px; } label { display: block; margin-bottom: 8px; font-weight: bold; }
        input, textarea, select { width: 100%; padding: 12px; border-radius: 4px; border: 1px solid var(--light-gray); font-size: 1rem; background: var(--light-gray); color: var(--text-light); box-sizing: border-box; }
        textarea { resize: vertical; min-height: 100px;}
        .btn { display: inline-block; text-decoration: none; color: white; font-weight: 700; cursor: pointer; border: none; padding: 12px 25px; border-radius: 4px; font-size: 1rem; transition: background-color 0.2s; }
        .btn:disabled { background-color: #555; cursor: not-allowed; }
        .btn-primary { background: var(--netflix-red); } .btn-primary:hover:not(:disabled) { background-color: #B20710; }
        .btn-secondary { background: #555; } .btn-danger { background: #dc3545; }
        .btn-edit { background: #007bff; }
        .table-container { display: block; overflow-x: auto; }
        table { width: 100%; border-collapse: collapse; } th, td { padding: 12px 15px; text-align: left; border-bottom: 1px solid var(--light-gray); }
        .action-buttons { display: flex; gap: 10px; }
        .dynamic-item { border: 1px solid var(--light-gray); padding: 15px; margin-bottom: 15px; border-radius: 5px; position: relative; }
        .dynamic-item .btn-danger { position: absolute; top: 10px; right: 10px; padding: 4px 8px; font-size: 0.8rem; }
        hr { border: 0; height: 1px; background-color: var(--light-gray); margin: 50px 0; }
        .tmdb-fetcher { display: flex; gap: 10px; }
        .checkbox-group { display: flex; flex-wrap: wrap; gap: 15px; padding: 10px 0; } .checkbox-group label { display: flex; align-items: center; gap: 8px; font-weight: normal; cursor: pointer;}
        .checkbox-group input { width: auto; }
        .link-pair { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-bottom: 10px; }
        .modal-overlay { position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.85); z-index: 2000; display: none; justify-content: center; align-items: center; padding: 20px; }
        .modal-content { background: var(--dark-gray); padding: 30px; border-radius: 8px; width: 100%; max-width: 900px; max-height: 90vh; display: flex; flex-direction: column; }
        .modal-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; flex-shrink: 0; }
        .modal-body { overflow-y: auto; }
        .modal-close { background: none; border: none; color: #fff; font-size: 2rem; cursor: pointer; }
        #search-results { display: grid; grid-template-columns: repeat(auto-fill, minmax(150px, 1fr)); gap: 20px; }
        .result-item { cursor: pointer; text-align: center; }
        .result-item img { width: 100%; aspect-ratio: 2/3; object-fit: cover; border-radius: 5px; margin-bottom: 10px; border: 2px solid transparent; transition: all 0.2s; }
        .result-item:hover img { transform: scale(1.05); border-color: var(--netflix-red); }
        .result-item p { font-size: 0.9rem; }
    </style>
</head>
<body>
<div class="admin-container">
    <header class="admin-header"><h1>Admin Panel</h1><a href="{{ url_for('home') }}" target="_blank">View Site</a></header>
    <h2><i class="fas fa-bullhorn"></i> Advertisement Management</h2>
    <form method="post">
        <input type="hidden" name="form_action" value="update_ads">
        <fieldset><legend>Global Ad Codes (Ezoic/Adsterra)</legend>
            <div class="form-group"><label>Header Script (in &lt;head&gt;):</label><textarea name="ad_header" rows="4" placeholder="Adsterra/Ezoic verification script">{{ ad_settings.ad_header or '' }}</textarea></div>
            <div class="form-group"><label>Body Top Script (after &lt;body&gt;):</label><textarea name="ad_body_top" rows="4" placeholder="Pop-up or other body scripts">{{ ad_settings.ad_body_top or '' }}</textarea></div>
            <div class="form-group"><label>Footer Script (before &lt;/body&gt;):</label><textarea name="ad_footer" rows="4">{{ ad_settings.ad_footer or '' }}</textarea></div>
        </fieldset>
        <fieldset><legend>In-Page Ad Units</legend>
             <div class="form-group"><label>Homepage Ad (Between Sections):</label><textarea name="ad_list_page" rows="4">{{ ad_settings.ad_list_page or '' }}</textarea></div>
             <div class="form-group"><label>Details Page Ad (Below Title):</label><textarea name="ad_detail_page" rows="4">{{ ad_settings.ad_detail_page or '' }}</textarea></div>
             <div class="form-group"><label>Wait Page Ad (Countdown Page):</label><textarea name="ad_wait_page" rows="4">{{ ad_settings.ad_wait_page or '' }}</textarea></div>
        </fieldset>
        <button type="submit" class="btn btn-primary"><i class="fas fa-save"></i> Save Ad Settings</button>
    </form>
    <hr>
    <h2><i class="fas fa-plus-circle"></i> Add New Content</h2>
    <fieldset><legend>Automatic Method (Search TMDB)</legend><div class="form-group"><div class="tmdb-fetcher"><input type="text" id="tmdb_search_query" placeholder="e.g., Avengers Endgame"><button type="button" id="tmdb_search_btn" class="btn btn-primary" onclick="searchTmdb()">Search</button></div></div></fieldset>
    <form method="post">
        <input type="hidden" name="form_action" value="add_content"><input type="hidden" name="tmdb_id" id="tmdb_id">
        <fieldset><legend>Core Details</legend>
            <div class="form-group"><label>Title:</label><input type="text" name="title" id="title" required></div>
            <div class="form-group"><label>Poster URL:</label><input type="url" name="poster" id="poster"></div>
            <div class="form-group"><label>Backdrop URL (Slider Image):</label><input type="url" name="backdrop" id="backdrop"></div>
            <div class="form-group"><label>Overview:</label><textarea name="overview" id="overview"></textarea></div>
            <div class="form-group"><label>Language (for poster tag):</label><input type="text" name="language" id="language" placeholder="e.g., Hindi"></div>
            <div class="form-group"><label>Genres (comma-separated):</label><input type="text" name="genres" id="genres"></div>
            <div class="form-group"><label>Categories:</label><div class="checkbox-group">{% for cat in predefined_categories %}<label><input type="checkbox" name="categories" value="{{ cat }}"> {{ cat }}</label>{% endfor %}</div></div>
            <div class="form-group"><label>Content Type:</label><select name="content_type" id="content_type" onchange="toggleFields()"><option value="movie">Movie</option><option value="series">Series</option></select></div>
        </fieldset>
        <div id="movie_fields">
            <fieldset><legend>Movie Links</legend>
                <div class="link-pair"><label>480p Watch Link:<input type="url" name="watch_link_480p"></label><label>480p Download Link:<input type="url" name="download_link_480p"></label></div>
                <div class="link-pair"><label>720p Watch Link:<input type="url" name="watch_link_720p"></label><label>720p Download Link:<input type="url" name="download_link_720p"></label></div>
                <div class="link-pair"><label>1080p Watch Link:<input type="url" name="watch_link_1080p"></label><label>1080p Download Link:<input type="url" name="download_link_1080p"></label></div>
            </fieldset>
        </div>
        <div id="episode_fields" style="display: none;">
            <fieldset><legend>Series Episodes</legend><div id="episodes_container"></div><button type="button" onclick="addEpisodeField()" class="btn btn-secondary"><i class="fas fa-plus"></i> Add Episode</button></fieldset>
        </div>
        <button type="submit" class="btn btn-primary"><i class="fas fa-check"></i> Add Content</button>
    </form>
    <hr>
    <h2><i class="fas fa-tasks"></i> Manage Content</h2>
    <div class="table-container"><table><thead><tr><th>Title</th><th>Type</th><th>Actions</th></tr></thead><tbody>
    {% for movie in content_list %}<tr><td>{{ movie.title }}</td><td>{{ movie.type|title }}</td><td class="action-buttons"><a href="{{ url_for('edit_movie', movie_id=movie._id) }}" class="btn btn-edit">Edit</a><a href="{{ url_for('delete_movie', movie_id=movie._id) }}" onclick="return confirm('Are you sure?')" class="btn btn-danger">Delete</a></td></tr>{% else %}<tr><td colspan="3" style="text-align:center;">No content found.</td></tr>{% endfor %}
    </tbody></table></div>
</div>
<div class="modal-overlay" id="search-modal">
    <div class="modal-content"><div class="modal-header"><h2>Select Content</h2><button class="modal-close" onclick="closeModal()">&times;</button></div><div class="modal-body" id="search-results"><p>Type a name and click search to see results.</p></div></div>
</div>
<script>
    const modal = document.getElementById('search-modal');
    const searchResultsContainer = document.getElementById('search-results');
    const searchBtn = document.getElementById('tmdb_search_btn');
    function toggleFields() { const isSeries = document.getElementById('content_type').value === 'series'; document.getElementById('episode_fields').style.display = isSeries ? 'block' : 'none'; document.getElementById('movie_fields').style.display = isSeries ? 'none' : 'block'; }
    function addEpisodeField() { const c = document.getElementById('episodes_container'); const d = document.createElement('div'); d.className = 'dynamic-item'; d.innerHTML = `<button type="button" onclick="this.parentElement.remove()" class="btn btn-danger">X</button><div class="form-group"><label>Season:</label><input type="number" name="episode_season[]" value="1" required></div><div class="form-group"><label>Episode:</label><input type="number" name="episode_number[]" required></div><div class="form-group"><label>Title:</label><input type="text" name="episode_title[]"></div><div class="form-group"><label>Download/Watch Link:</label><input type="url" name="episode_watch_link[]" required></div>`; c.appendChild(d); }
    function openModal() { modal.style.display = 'flex'; }
    function closeModal() { modal.style.display = 'none'; }
    async function searchTmdb() {
        const query = document.getElementById('tmdb_search_query').value.trim();
        if (!query) return alert('Please enter a movie or series name.');
        searchBtn.disabled = true; searchBtn.innerHTML = 'Searching...';
        searchResultsContainer.innerHTML = '<p>Loading results...</p>';
        openModal();
        try {
            const response = await fetch('/admin/api/search?query=' + encodeURIComponent(query));
            const results = await response.json();
            if (!response.ok) throw new Error(results.error || 'Unknown error');
            if (results.length === 0) { searchResultsContainer.innerHTML = '<p>No results found.</p>'; return; }
            searchResultsContainer.innerHTML = '';
            results.forEach(item => { const resultDiv = document.createElement('div'); resultDiv.className = 'result-item'; resultDiv.onclick = () => selectResult(item.id, item.media_type); resultDiv.innerHTML = `<img src="${item.poster}" alt="${item.title}"><p><strong>${item.title}</strong> (${item.year})</p>`; searchResultsContainer.appendChild(resultDiv); });
        } catch (error) { searchResultsContainer.innerHTML = `<p style="color:red;">Error: ${error.message}</p>`; } finally { searchBtn.disabled = false; searchBtn.innerHTML = 'Search'; }
    }
    async function selectResult(tmdbId, mediaType) {
        closeModal();
        searchBtn.disabled = true; searchBtn.innerHTML = 'Fetching...';
        try {
            const response = await fetch(`/admin/api/details?id=${tmdbId}&type=${mediaType}`);
            const data = await response.json();
            if (!response.ok) throw new Error(data.error || 'Failed to fetch details');
            document.getElementById('tmdb_id').value = data.tmdb_id || '';
            document.getElementById('title').value = data.title || '';
            document.getElementById('overview').value = data.overview || '';
            document.getElementById('poster').value = data.poster || '';
            document.getElementById('backdrop').value = data.backdrop || '';
            document.getElementById('genres').value = data.genres ? data.genres.join(', ') : '';
            document.getElementById('content_type').value = data.type === 'series' ? 'series' : 'movie';
            document.querySelectorAll('input[name="categories"]').forEach(checkbox => checkbox.checked = false);
            toggleFields();
            alert(`'${data.title}' details have been filled. Please select categories, add links and click 'Add Content'.`);
        } catch (error) { alert('Error fetching details: ' + error.message); } finally { searchBtn.disabled = false; searchBtn.innerHTML = 'Search'; }
    }
    document.addEventListener('DOMContentLoaded', toggleFields);
</script>
</body></html>
"""
edit_html = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Edit Content - {{ website_name }}</title>
    <link rel="icon" href="https://img.icons8.com/fluency/48/cinema-.png" type="image/png">
    <meta name="robots" content="noindex, nofollow">
    <link href="https://fonts.googleapis.com/css2?family=Bebas+Neue&family=Roboto:wght@400;700&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.2.0/css/all.min.css">
    <style>
        :root { --netflix-red: #E50914; --netflix-black: #141414; --dark-gray: #222; --light-gray: #333; --text-light: #f5f5f5; }
        body { font-family: 'Roboto', sans-serif; background: var(--netflix-black); color: var(--text-light); padding: 20px; }
        .admin-container { max-width: 800px; margin: 20px auto; }
        .back-link { display: inline-block; margin-bottom: 20px; color: #999; text-decoration: none; }
        h2 { font-family: 'Bebas Neue', sans-serif; color: var(--netflix-red); font-size: 2.5rem; }
        form { background: var(--dark-gray); padding: 25px; border-radius: 8px; }
        fieldset { border: 1px solid var(--light-gray); padding: 20px; margin-bottom: 20px; border-radius: 5px;}
        legend { font-weight: bold; color: var(--netflix-red); padding: 0 10px; font-size: 1.2rem; }
        .form-group { margin-bottom: 15px; } label { display: block; margin-bottom: 8px; font-weight: bold;}
        input, textarea, select { width: 100%; padding: 12px; border-radius: 4px; border: 1px solid var(--light-gray); font-size: 1rem; background: var(--light-gray); color: var(--text-light); box-sizing: border-box; }
        .btn { display: inline-block; color: white; cursor: pointer; border: none; padding: 12px 25px; border-radius: 4px; font-size: 1rem; }
        .btn-primary { background: var(--netflix-red); } .btn-secondary { background: #555; } .btn-danger { background: #dc3545; }
        .dynamic-item { border: 1px solid var(--light-gray); padding: 15px; margin-bottom: 15px; border-radius: 5px; position: relative; }
        .checkbox-group { display: flex; flex-wrap: wrap; gap: 15px; } .checkbox-group label { display: flex; align-items: center; gap: 5px; font-weight: normal; }
        .checkbox-group input { width: auto; }
        .link-pair { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-bottom: 10px; }
    </style>
</head>
<body>
<div class="admin-container">
  <a href="{{ url_for('admin') }}" class="back-link"><i class="fas fa-arrow-left"></i> Back to Admin Panel</a>
  <h2>Edit: {{ movie.title }}</h2>
  <form method="post">
    <fieldset><legend>Core Details</legend>
        <div class="form-group"><label>Title:</label><input type="text" name="title" value="{{ movie.title }}" required></div>
        <div class="form-group"><label>Poster URL:</label><input type="url" name="poster" value="{{ movie.poster or '' }}"></div>
        <div class="form-group"><label>Backdrop URL:</label><input type="url" name="backdrop" value="{{ movie.backdrop or '' }}"></div>
        <div class="form-group"><label>Overview:</label><textarea name="overview">{{ movie.overview or '' }}</textarea></div>
        <div class="form-group"><label>Language:</label><input type="text" name="language" value="{{ movie.language or '' }}"></div>
        <div class="form-group"><label>Genres:</label><input type="text" name="genres" value="{{ movie.genres|join(', ') if movie.genres else '' }}"></div>
        <div class="form-group"><label>Categories:</label><div class="checkbox-group">{% for cat in predefined_categories %}<label><input type="checkbox" name="categories" value="{{ cat }}" {% if movie.categories and cat in movie.categories %}checked{% endif %}> {{ cat }}</label>{% endfor %}</div></div>
        <div class="form-group"><label>Content Type:</label><select name="content_type" id="content_type" onchange="toggleFields()"><option value="movie" {% if movie.type == 'movie' %}selected{% endif %}>Movie</option><option value="series" {% if movie.type == 'series' %}selected{% endif %}>Series</option></select></div>
    </fieldset>
    <div id="movie_fields">
        <fieldset><legend>Movie Links</legend>
            {% set links_480p = movie.links|selectattr('quality', 'equalto', '480p')|first if movie.links else None %}
            {% set links_720p = movie.links|selectattr('quality', 'equalto', '720p')|first if movie.links else None %}
            {% set links_1080p = movie.links|selectattr('quality', 'equalto', '1080p')|first if movie.links else None %}
            <div class="link-pair"><label>480p Watch Link:<input type="url" name="watch_link_480p" value="{{ links_480p.watch_url if links_480p else '' }}"></label><label>480p Download Link:<input type="url" name="download_link_480p" value="{{ links_480p.download_url if links_480p else '' }}"></label></div>
            <div class="link-pair"><label>720p Watch Link:<input type="url" name="watch_link_720p" value="{{ links_720p.watch_url if links_720p else '' }}"></label><label>720p Download Link:<input type="url" name="download_link_720p" value="{{ links_720p.download_url if links_720p else '' }}"></label></div>
            <div class="link-pair"><label>1080p Watch Link:<input type="url" name="watch_link_1080p" value="{{ links_1080p.watch_url if links_1080p else '' }}"></label><label>1080p Download Link:<input type="url" name="download_link_1080p" value="{{ links_1080p.download_url if links_1080p else '' }}"></label></div>
        </fieldset>
    </div>
    <div id="episode_fields" style="display: none;">
      <fieldset><legend>Episodes</legend><div id="episodes_container">
        {% if movie.type == 'series' and movie.episodes %}{% for ep in movie.episodes|sort(attribute='episode_number')|sort(attribute='season') %}
        <div class="dynamic-item"><button type="button" onclick="this.parentElement.remove()" class="btn btn-danger">X</button><div class="form-group"><label>Season:</label><input type="number" name="episode_season[]" value="{{ ep.season or 1 }}" required></div><div class="form-group"><label>Episode:</label><input type="number" name="episode_number[]" value="{{ ep.episode_number }}" required></div><div class="form-group"><label>Title:</label><input type="text" name="episode_title[]" value="{{ ep.title or '' }}"></div><div class="form-group"><label>Download/Watch Link:</label><input type="url" name="episode_watch_link[]" value="{{ ep.watch_link or '' }}" required></div></div>
        {% endfor %}{% endif %}</div><button type="button" onclick="addEpisodeField()" class="btn btn-secondary"><i class="fas fa-plus"></i> Add Episode</button></fieldset>
    </div>
    <button type="submit" class="btn btn-primary"><i class="fas fa-save"></i> Update Content</button>
  </form>
</div>
<script>
    function toggleFields() { var isSeries = document.getElementById('content_type').value === 'series'; document.getElementById('episode_fields').style.display = isSeries ? 'block' : 'none'; document.getElementById('movie_fields').style.display = isSeries ? 'none' : 'block'; }
    function addEpisodeField() { const c = document.getElementById('episodes_container'); const d = document.createElement('div'); d.className = 'dynamic-item'; d.innerHTML = `<button type="button" onclick="this.parentElement.remove()" class="btn btn-danger">X</button><div class="form-group"><label>Season:</label><input type="number" name="episode_season[]" value="1" required></div><div class="form-group"><label>Episode:</label><input type="number" name="episode_number[]" required></div><div class="form-group"><label>Title (Optional):</label><input type="text" name="episode_title[]"></div><div class="form-group"><label>Download/Watch Link:</label><input type="url" name="episode_watch_link[]" required></div>`; c.appendChild(d); }
    document.addEventListener('DOMContentLoaded', toggleFields);
</script>
</body></html>
"""

# --- TMDB API Helper Function ---
def get_tmdb_details(tmdb_id, media_type):
    if not TMDB_API_KEY: return None
    search_type = "tv" if media_type == "tv" else "movie"
    try:
        detail_url = f"https://api.themoviedb.org/3/{search_type}/{tmdb_id}?api_key={TMDB_API_KEY}"
        res = requests.get(detail_url, timeout=10)
        res.raise_for_status()
        data = res.json()
        details = {"tmdb_id": tmdb_id, "title": data.get("title") or data.get("name"), "poster": f"https://image.tmdb.org/t/p/w500{data.get('poster_path')}" if data.get('poster_path') else None,"backdrop": f"https://image.tmdb.org/t/p/w1280{data.get('backdrop_path')}" if data.get('backdrop_path') else None,"overview": data.get("overview"), "release_date": data.get("release_date") or data.get("first_air_date"), "genres": [g['name'] for g in data.get("genres", [])], "vote_average": data.get("vote_average"), "type": "series" if search_type == "tv" else "movie"}
        return details
    except requests.RequestException as e:
        print(f"ERROR: TMDb API request failed for ID {tmdb_id}. Reason: {e}")
        return None

# =======================================================================================
# === [START] FLASK ROUTES ==============================================================
# =======================================================================================
@app.route('/')
def home():
    query = request.args.get('q', '').strip()
    if query:
        movies_list = list(movies.find({"title": {"$regex": query, "$options": "i"}}).sort('_id', -1))
        return render_template_string(index_html, movies=movies_list, query=f'Results for "{query}"', is_full_page_list=True)
    
    categorized_content = {}
    for category in PREDEFINED_CATEGORIES:
        categorized_content[category] = list(movies.find({"categories": category}).sort('_id', -1).limit(12))

    latest_movies_for_carousel = list(movies.find({"type": "movie"}).sort('_id', -1).limit(12))
    latest_series_for_carousel = list(movies.find({"type": "series"}).sort('_id', -1).limit(12))

    context = {
        "latest_movies": latest_movies_for_carousel,
        "latest_series": latest_series_for_carousel,
        "recently_added": list(movies.find({"backdrop": {"$ne": None}}).sort('_id', -1).limit(8)),
        "categorized_content": categorized_content,
        "is_full_page_list": False
    }
    return render_template_string(index_html, **context)

@app.route('/movie/<movie_id>')
def movie_detail(movie_id):
    try:
        movie = movies.find_one({"_id": ObjectId(movie_id)})
        if not movie: 
            return "Content not found", 404
        return render_template_string(detail_html, movie=movie)
    except Exception as e:
        # For debugging, it's helpful to see the actual error in the server logs
        print(f"Error rendering detail page for ID {movie_id}: {e}")
        return "Content not found", 404

@app.route('/movies')
def all_movies():
    all_movie_content = list(movies.find({"type": "movie"}).sort('_id', -1))
    return render_template_string(
        index_html, 
        movies=all_movie_content, 
        query="All Movies", 
        is_full_page_list=True
    )

@app.route('/series')
def all_series():
    all_series_content = list(movies.find({"type": "series"}).sort('_id', -1))
    return render_template_string(
        index_html, 
        movies=all_series_content, 
        query="All Series", 
        is_full_page_list=True
    )

# === [FINAL, ROBUST FIX] Using query parameter `name` which is safer for special characters ===
@app.route('/category')
def movies_by_category():
    title = request.args.get('name')
    if not title:
        # If no category name is provided, redirect to home
        return redirect(url_for('home'))

    # Special handling for "Latest Movies" and "Latest Series" virtual categories
    if title == "Latest Movies":
        return redirect(url_for('all_movies'))
    if title == "Latest Series":
        return redirect(url_for('all_series'))
        
    # Standard query for all other real categories like "18+ Adult Zone", "Bengali", etc.
    query = {"categories": title}
    content_list = list(movies.find(query).sort('_id', -1))
    
    return render_template_string(
        index_html, 
        movies=content_list, 
        query=title, 
        is_full_page_list=True
    )

@app.route('/wait')
def wait_page():
    encoded_target_url = request.args.get('target')
    if not encoded_target_url:
        return redirect(url_for('home'))
    
    decoded_target_url = unquote(encoded_target_url)
    return render_template_string(wait_page_html, target_url=decoded_target_url)

@app.route('/admin', methods=["GET", "POST"])
@requires_auth
def admin():
    if request.method == "POST":
        form_action = request.form.get("form_action")

        if form_action == "update_ads":
            ad_settings_data = {
                "ad_header": request.form.get("ad_header"),
                "ad_body_top": request.form.get("ad_body_top"),
                "ad_footer": request.form.get("ad_footer"),
                "ad_list_page": request.form.get("ad_list_page"),
                "ad_detail_page": request.form.get("ad_detail_page"),
                "ad_wait_page": request.form.get("ad_wait_page"),
            }
            settings.update_one({"_id": "ad_config"}, {"$set": ad_settings_data}, upsert=True)
        
        elif form_action == "add_content":
            content_type = request.form.get("content_type", "movie")
            movie_data = {
                "title": request.form.get("title").strip(), "type": content_type,
                "poster": request.form.get("poster").strip() or PLACEHOLDER_POSTER,
                "backdrop": request.form.get("backdrop").strip() or None,
                "overview": request.form.get("overview").strip(),
                "language": request.form.get("language").strip() or None,
                "genres": [g.strip() for g in request.form.get("genres", "").split(',') if g.strip()],
                "categories": request.form.getlist("categories"),
                "episodes": [], "links": []
            }
            
            tmdb_id = request.form.get("tmdb_id")
            if tmdb_id:
                media_type = "tv" if content_type == "series" else "movie"
                tmdb_details = get_tmdb_details(tmdb_id, media_type)
                if tmdb_details: movie_data.update({'release_date': tmdb_details.get('release_date'),'vote_average': tmdb_details.get('vote_average')})

            if content_type == "movie":
                movie_links = []
                for quality in ["480p", "720p", "1080p"]:
                    watch_url = request.form.get(f"watch_link_{quality}")
                    download_url = request.form.get(f"download_link_{quality}")
                    if watch_url or download_url:
                        movie_links.append({"quality": quality, "watch_url": watch_url, "download_url": download_url})
                movie_data["links"] = movie_links
            else: # Series
                seasons = request.form.getlist('episode_season[]')
                numbers = request.form.getlist('episode_number[]')
                titles = request.form.getlist('episode_title[]')
                links = request.form.getlist('episode_watch_link[]')
                for i in range(len(seasons)):
                    if seasons[i] and numbers[i] and links[i]:
                        movie_data['episodes'].append({"season": int(seasons[i]), "episode_number": int(numbers[i]), "title": titles[i].strip(), "watch_link": links[i].strip()})
            movies.insert_one(movie_data)
        return redirect(url_for('admin'))
    
    content_list = list(movies.find().sort('_id', -1))
    return render_template_string(admin_html, content_list=content_list)

@app.route('/edit_movie/<movie_id>', methods=["GET", "POST"])
@requires_auth
def edit_movie(movie_id):
    try: obj_id = ObjectId(movie_id)
    except: return "Invalid ID", 400
    movie_obj = movies.find_one({"_id": obj_id})
    if not movie_obj: return "Movie not found", 404

    if request.method == "POST":
        content_type = request.form.get("content_type")
        update_data = {
            "title": request.form.get("title").strip(), "type": content_type,
            "poster": request.form.get("poster").strip() or PLACEHOLDER_POSTER,
            "backdrop": request.form.get("backdrop").strip() or None,
            "overview": request.form.get("overview").strip(),
            "language": request.form.get("language").strip() or None,
            "genres": [g.strip() for g in request.form.get("genres").split(',') if g.strip()],
            "categories": request.form.getlist("categories")
        }
        
        if content_type == "movie":
            movie_links = []
            for quality in ["480p", "720p", "1080p"]:
                watch_url = request.form.get(f"watch_link_{quality}")
                download_url = request.form.get(f"download_link_{quality}")
                if watch_url or download_url:
                    movie_links.append({"quality": quality, "watch_url": watch_url, "download_url": download_url})
            update_data["links"] = movie_links
            movies.update_one({"_id": obj_id}, {"$set": update_data, "$unset": {"episodes": ""}})
        else: # Series
            update_data["episodes"] = []
            seasons = request.form.getlist('episode_season[]')
            numbers = request.form.getlist('episode_number[]')
            titles = request.form.getlist('episode_title[]')
            links = request.form.getlist('episode_watch_link[]')
            for i in range(len(seasons)):
                if seasons[i] and numbers[i] and links[i]:
                     update_data["episodes"].append({"season": int(seasons[i]), "episode_number": int(numbers[i]), "title": titles[i].strip(), "watch_link": links[i].strip()})
            movies.update_one({"_id": obj_id}, {"$set": update_data, "$unset": {"links": ""}})
        return redirect(url_for('admin'))
    return render_template_string(edit_html, movie=movie_obj)

@app.route('/delete_movie/<movie_id>')
@requires_auth
def delete_movie(movie_id):
    try: movies.delete_one({"_id": ObjectId(movie_id)})
    except: return "Invalid ID", 400
    return redirect(url_for('admin'))

# --- API Routes for Admin Panel ---
@app.route('/admin/api/search')
@requires_auth
def api_search_tmdb():
    query = request.args.get('query')
    if not query: return jsonify({"error": "Query parameter is missing"}), 400
    try:
        search_url = f"https://api.themoviedb.org/3/search/multi?api_key={TMDB_API_KEY}&query={quote(query)}"
        res = requests.get(search_url, timeout=10)
        res.raise_for_status()
        data = res.json()
        results = []
        for item in data.get('results', []):
            if item.get('media_type') in ['movie', 'tv'] and item.get('poster_path'):
                results.append({"id": item.get('id'),"title": item.get('title') or item.get('name'),"year": (item.get('release_date') or item.get('first_air_date', 'N/A')).split('-')[0],"poster": f"https://image.tmdb.org/t/p/w200{item.get('poster_path')}","media_type": item.get('media_type')})
        return jsonify(results)
    except Exception as e: return jsonify({"error": str(e)}), 500

@app.route('/admin/api/details')
@requires_auth
def api_get_details():
    tmdb_id, media_type = request.args.get('id'), request.args.get('type')
    if not tmdb_id or not media_type: return jsonify({"error": "ID and type parameters are required"}), 400
    details = get_tmdb_details(tmdb_id, media_type)
    if details: return jsonify(details)
    else: return jsonify({"error": "Details not found on TMDb"}), 404

# --- API Route for Live Search ---
@app.route('/api/search')
def api_search():
    query = request.args.get('q', '').strip()
    if not query:
        return jsonify([])
    try:
        results = list(movies.find(
            {"title": {"$regex": query, "$options": "i"}},
            {"_id": 1, "title": 1, "poster": 1}
        ).limit(10))
        for item in results:
            item['_id'] = str(item['_id'])
        return jsonify(results)
    except Exception as e:
        print(f"API Search Error: {e}")
        return jsonify({"error": "An error occurred during search"}), 500

if __name__ == "__main__":
    app.run(debug=True, host='0.0.0.0', port=int(os.environ.get('PORT', 3000)))
