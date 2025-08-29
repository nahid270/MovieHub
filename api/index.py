import os
import sys
import re
import requests
import json
from flask import Flask, render_template_string, request, redirect, url_for, Response, jsonify
from pymongo import MongoClient
from bson.objectid import ObjectId
from functools import wraps
from urllib.parse import urlparse, unquote

# --- Environment Variables (শুধু প্রয়োজনীয়গুলো রাখা হয়েছে) ---
MONGO_URI = os.environ.get("MONGO_URI", "mongodb+srv://mewayo8672:mewayo8672@cluster0.ozhvczp.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0")
TMDB_API_KEY = os.environ.get("TMDB_API_KEY", "7dc544d9253bccc3cfecc1c677f69819")
ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "Nahid")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "270")
WEBSITE_NAME = os.environ.get("WEBSITE_NAME", "MovieZonehub")

# --- Validate Environment Variables ---
required_vars = {
    "MONGO_URI": MONGO_URI, "TMDB_API_KEY": TMDB_API_KEY,
    "ADMIN_USERNAME": ADMIN_USERNAME, "ADMIN_PASSWORD": ADMIN_PASSWORD,
}
is_vercel_build = os.environ.get('VERCEL') == '1'
if not is_vercel_build:
    missing_vars = [name for name, value in required_vars.items() if not value]
    if missing_vars:
        print(f"FATAL: Missing required environment variables: {', '.join(missing_vars)}")
        sys.exit(1)

# --- App Initialization ---
PLACEHOLDER_POSTER = "https://via.placeholder.com/400x600.png?text=Poster+Not+Found"
app = Flask(__name__)

CATEGORIES = ["Trending", "Latest Movie", "Latest Series", "Hindi", "Bengali", "English"]

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
    print("SUCCESS: Successfully connected to MongoDB!")
except Exception as e:
    print(f"FATAL: Error connecting to MongoDB: {e}. Exiting.")
    if not is_vercel_build:
        sys.exit(1)

# --- Template Processor (For making website_name available in all templates) ---
@app.context_processor
def inject_globals():
    return dict(website_name=WEBSITE_NAME)

# =========================================================================================
# === [START] HTML TEMPLATES (Admin Panel has been updated) ===============================
# =========================================================================================
index_html = """
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8" /><meta name="viewport" content="width=device-width, initial-scale=1.0" />
<title>{{ website_name }} - Your Entertainment Hub</title>
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin><link href="https://fonts.googleapis.com/css2?family=Poppins:wght@300;400;500;600;700&display=swap" rel="stylesheet">
<link rel="stylesheet" href="https://unpkg.com/swiper/swiper-bundle.min.css"/>
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.2.0/css/all.min.css">
<style>
  :root {--primary-color: #E50914;--bg-color: #0c0c0c;--card-bg: #1a1a1a;--text-light: #ffffff;--text-dark: #a0a0a0;--nav-height: 70px;}
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {font-family: 'Poppins', sans-serif;background-color: var(--bg-color);color: var(--text-light);overflow-x: hidden;}
  a { text-decoration: none; color: inherit; }
  img { max-width: 100%; display: block; }
  .container { max-width: 1400px; margin: 0 auto; padding: 0 40px; }
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
  .menu-toggle { display: none; font-size: 1.5rem; cursor: pointer; }
  .hero-slider { height: 75vh; width: 100%; margin-top: var(--nav-height); }
  .hero-slide { position: relative; display: flex; align-items: center; }
  .hero-bg-img { position: absolute; top: 0; left: 0; width: 100%; height: 100%; object-fit: cover; object-position: center; }
  .hero-slide::before { content: ''; position: absolute; top: 0; left: 0; width: 100%; height: 100%; background: linear-gradient(90deg, var(--bg-color) 0%, rgba(12,12,12,0.8) 30%, rgba(12,12,12,0.2) 60%, transparent 100%), linear-gradient(to top, var(--bg-color) 0%, transparent 20%); }
  .hero-content { position: relative; z-index: 2; padding: 0 40px; max-width: 50%; }
  .hero-title { font-size: 3.5rem; font-weight: 700; margin-bottom: 1rem; line-height: 1.1; }
  .hero-meta { display: flex; align-items: center; gap: 15px; margin-bottom: 1rem; color: var(--text-dark); }
  .hero-meta .rating { color: #f5c518; font-weight: 600; }
  .hero-overview { font-size: 1rem; color: var(--text-dark); line-height: 1.6; margin-bottom: 2rem; display: -webkit-box; -webkit-line-clamp: 3; -webkit-box-orient: vertical; overflow: hidden; }
  .hero-btn { background-color: var(--primary-color); padding: 12px 28px; border-radius: 50px; font-weight: 600; transition: transform 0.2s ease; }
  .hero-btn:hover { transform: scale(1.05); }
  .swiper-pagination-bullet-active { background: var(--primary-color); }
  .category-section { margin: 50px 0; }
  .category-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; }
  .category-title { font-size: 1.8rem; font-weight: 600; }
  .view-all-link { font-size: 0.9rem; color: var(--text-dark); font-weight: 500; }
  .movie-carousel .swiper-slide { width: auto; }
  .movie-card { display: block; }
  .movie-poster { width: 220px; aspect-ratio: 2 / 3; object-fit: cover; border-radius: 8px; margin-bottom: 10px; transition: transform 0.3s ease, box-shadow 0.3s ease; }
  .movie-card:hover .movie-poster { transform: scale(1.05); box-shadow: 0 10px 25px rgba(0,0,0,0.5); }
  .card-title { font-size: 1rem; font-weight: 500; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .card-meta { font-size: 0.8rem; color: var(--text-dark); }
  .swiper-button-next, .swiper-button-prev { color: var(--text-light); }
  .full-page-grid-container { padding: 120px 40px 50px; }
  .full-page-grid-title { font-size: 2.5rem; font-weight: 700; margin-bottom: 30px; }
  .full-page-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 30px 20px; }
  .full-page-grid .movie-poster { width: 100%; }
  .main-footer { background-color: #111; padding: 30px 40px; text-align: center; color: var(--text-dark); margin-top: 50px; }
  .main-footer a { color: var(--primary-color); }
  @media (max-width: 992px) {.nav-links, .search-form { display: none; } .menu-toggle { display: block; } .hero-content { max-width: 80%; } .hero-title { font-size: 2.5rem; } }
  @media (max-width: 768px) {.container, .full-page-grid-container { padding: 0 20px; } .full-page-grid-container{padding-top:100px;padding-bottom:40px;} .logo { font-size: 1.5rem; } .hero-slider { height: 60vh; } .hero-content { padding: 0 20px; max-width: 100%; text-align: center; } .hero-meta { justify-content: center; } .hero-overview { display: none; } .category-title { font-size: 1.4rem; } .movie-poster { width: 160px; } .full-page-grid { grid-template-columns: repeat(auto-fill, minmax(140px, 1fr)); } }
</style>
</head>
<body>
<header class="main-header">
    <div class="container header-content">
        <a href="{{ url_for('home') }}" class="logo">{{ website_name }}</a>
        <nav class="nav-links">
            <a href="{{ url_for('home') }}" class="active">Home</a>
            <a href="{{ url_for('movies_by_category', cat_name='Latest Movie') }}">Movies</a>
            <a href="{{ url_for('movies_by_category', cat_name='Latest Series') }}">Series</a>
            <a href="{{ url_for('genres_page') }}">Genres</a>
        </nav>
        <form method="GET" action="/" class="search-form">
            <input type="search" name="q" class="search-input" placeholder="Search..." value="{{ query|default('') }}">
            <button class="search-btn" type="submit"><i class="fas fa-search"></i></button>
        </form>
        <div class="menu-toggle"><i class="fas fa-bars"></i></div>
    </div>
</header>
<main>
  {% macro render_movie_card(m) %}
    <a href="{{ url_for('movie_detail', movie_id=m._id) }}" class="movie-card">
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
    <div class="swiper hero-slider">
        <div class="swiper-wrapper">
        {% for movie in recently_added %}{% if movie.backdrop %}
            <div class="swiper-slide hero-slide">
                <img src="{{ movie.backdrop }}" alt="" class="hero-bg-img">
                <div class="container hero-content">
                    <h1 class="hero-title">{{ movie.title }}</h1>
                    <div class="hero-meta">
                        {% if movie.vote_average %}<span class="rating"><i class="fas fa-star"></i> {{ "%.1f"|format(movie.vote_average) }}</span>{% endif %}
                        {% if movie.release_date %}<span>{{ movie.release_date.split('-')[0] }}</span>{% endif %}
                        {% if movie.genres %}<span>{{ movie.genres|first }}</span>{% endif %}
                    </div>
                    <p class="hero-overview">{{ movie.overview }}</p>
                    <a href="{{ url_for('movie_detail', movie_id=movie._id) }}" class="hero-btn">More Info <i class="fas fa-play"></i></a>
                </div>
            </div>
        {% endif %}{% endfor %}
        </div>
        <div class="swiper-pagination"></div>
    </div>
    <div class="container">
    {% macro render_carousel_section(title, movies_list, endpoint, cat_name) %}
        {% if movies_list %}
        <section class="category-section">
            <div class="category-header">
                <h2 class="category-title">{{ title }}</h2>
                <a href="{{ url_for(endpoint, cat_name=cat_name) }}" class="view-all-link">View All</a>
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
    {{ render_carousel_section('Trending Now', trending_movies, 'movies_by_category', 'Trending') }}
    {{ render_carousel_section('Latest Movies', latest_movies, 'movies_by_category', 'Latest Movie') }}
    {{ render_carousel_section('Web Series', latest_series, 'movies_by_category', 'Latest Series') }}
    {{ render_carousel_section('Hindi', hindi_movies, 'movies_by_category', 'Hindi') }}
    {{ render_carousel_section('Bengali', bengali_movies, 'movies_by_category', 'Bengali') }}
    {{ render_carousel_section('English & Hollywood', english_movies, 'movies_by_category', 'English') }}
    {{ render_carousel_section('Coming Soon', coming_soon_movies, 'movies_by_category', 'Coming Soon') }}
    </div>
  {% endif %}
</main>
<footer class="main-footer">
    <p>&copy; 2024 {{ website_name }}. All Rights Reserved.</p>
</footer>
<script src="https://unpkg.com/swiper/swiper-bundle.min.js"></script>
<script>
    const header = document.querySelector('.main-header');
    window.addEventListener('scroll', () => { window.scrollY > 50 ? header.classList.add('scrolled') : header.classList.remove('scrolled'); });
    new Swiper('.hero-slider', { loop: true, autoplay: { delay: 5000 }, pagination: { el: '.swiper-pagination', clickable: true }, });
    new Swiper('.movie-carousel', { slidesPerView: 'auto', spaceBetween: 20, navigation: { nextEl: '.swiper-button-next', prevEl: '.swiper-button-prev', }, breakpoints: { 320: { spaceBetween: 15 }, 768: { spaceBetween: 20 }, } });
</script>
</body></html>
"""
detail_html = """
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8" /><meta name="viewport" content="width=device-width, initial-scale=1.0" />
<title>{{ movie.title if movie else "Content Not Found" }} - {{ website_name }}</title>
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin><link href="https://fonts.googleapis.com/css2?family=Poppins:wght@300;400;500;600;700&display=swap" rel="stylesheet">
<link rel="stylesheet" href="https://unpkg.com/swiper/swiper-bundle.min.css"/>
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.2.0/css/all.min.css">
<style>
  :root {--primary-color: #E50914;--bg-color: #0c0c0c;--card-bg: #1a1a1a;--text-light: #ffffff;--text-dark: #a0a0a0;}
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
  .btn-primary { background-color: var(--primary-color); }
  .btn-primary:hover { transform: scale(1.05); }
  .tabs-container { margin: 40px 0; }
  .tabs-nav { display: flex; flex-wrap: wrap; border-bottom: 1px solid #333; }
  .tab-link { padding: 15px 30px; cursor: pointer; font-weight: 500; color: var(--text-dark); position: relative; }
  .tab-link.active { color: var(--text-light); }
  .tab-link.active::after { content: ''; position: absolute; bottom: -1px; left: 0; width: 100%; height: 2px; background-color: var(--primary-color); }
  .tabs-content { padding: 30px 0; }
  .tab-pane { display: none; }
  .tab-pane.active { display: block; }
  .link-group { margin-bottom: 30px; }
  .link-group h3 { font-size: 1.2rem; font-weight: 500; margin-bottom: 15px; }
  .link-buttons { display: flex; flex-wrap: wrap; gap: 15px; }
  .episode-list { display: flex; flex-direction: column; gap: 10px; }
  .episode-item { display: flex; justify-content: space-between; align-items: center; background-color: var(--card-bg); padding: 15px; border-radius: 8px; }
  .episode-name { font-weight: 500; }
  .screenshots-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 15px; }
  .screenshot img { width: 100%; border-radius: 8px; }
  .related-section { padding-bottom: 50px; }
  .section-title { font-size: 1.8rem; font-weight: 600; margin: 40px 0 20px; }
  .movie-carousel .swiper-slide { width: auto; }
  .movie-card { display: block; }
  .movie-poster { width: 220px; aspect-ratio: 2 / 3; object-fit: cover; border-radius: 8px; margin-bottom: 10px; transition: transform 0.3s ease; }
  .movie-card:hover .movie-poster { transform: scale(1.05); }
  .card-title { font-size: 1rem; font-weight: 500; }
  .card-meta { font-size: 0.8rem; color: var(--text-dark); }
  .swiper-button-next, .swiper-button-prev { color: var(--text-light); }
  @media (max-width: 768px) {
    .container { padding: 0 20px; }
    .detail-hero { padding: 100px 0 40px; }
    .detail-content { flex-direction: column; align-items: center; text-align: center; }
    .detail-poster { width: 60%; max-width: 250px; height: auto; }
    .detail-title { font-size: 2rem; }
    .detail-meta { justify-content: center; }
    .tab-link { padding: 12px 15px; font-size: 0.9rem; }
    .movie-poster { width: 160px; }
    .episode-item { flex-direction: column; gap: 10px; align-items: flex-start; }
  }
</style>
</head>
<body>
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
                {% if movie.genres %}<div class="meta-item"><i class="fas fa-tag"></i> {{ movie.genres | join(' / ') }}</div>{% endif %}
            </div>
            <p class="detail-overview">{{ movie.overview }}</p>
        </div>
    </div>
</div>
<div class="container">
    <div class="tabs-container">
        <nav class="tabs-nav">
            <div class="tab-link active" data-tab="downloads"><i class="fas fa-download"></i> Download Links</div>
            {% if movie.screenshots %}<div class="tab-link" data-tab="screenshots"><i class="fas fa-images"></i> Screenshots</div>{% endif %}
            {% if movie.type == 'series' and movie.episodes %}
                {% for season_num in movie.episodes | map(attribute='season') | unique | sort %}
                <div class="tab-link" data-tab="season-{{ season_num }}">Season {{ season_num }}</div>
                {% endfor %}
            {% endif %}
        </nav>
        <div class="tabs-content">
            <div class="tab-pane active" id="downloads">
            {% if movie.type == 'movie' %}
                {% if movie.streaming_links %}<div class="link-group"><h3><i class="fas fa-stream"></i> Stream Online</h3><div class="link-buttons">
                    {% for link_item in movie.streaming_links %}<a href="{{ link_item.url }}" target="_blank" class="action-btn btn-primary">Stream in {{ link_item.name }}</a>{% endfor %}
                </div></div>{% endif %}
                {% if movie.links %}<div class="link-group"><h3><i class="fas fa-download"></i> Direct Download</h3><div class="link-buttons">
                    {% for link_item in movie.links %}<a href="{{ link_item.url }}" target="_blank" class="action-btn btn-primary">Download {{ link_item.quality }}</a>{% endfor %}
                </div></div>{% endif %}
                {% if not movie.streaming_links and not movie.links %}<p>No download or streaming links available yet.</p>{% endif %}
            {% elif movie.type == 'series' %}<p>Please select a season tab to view episode links.</p>
            {% else %}<p>No download links available.</p>{% endif %}
            </div>
            {% if movie.screenshots %}<div class="tab-pane" id="screenshots"><div class="screenshots-grid">
                {% for ss in movie.screenshots %}<a href="{{ ss }}" target="_blank" class="screenshot"><img src="{{ ss }}" alt="Screenshot"></a>{% endfor %}
            </div></div>{% endif %}
            {% if movie.type == 'series' and movie.episodes %}
                {% for season_num in movie.episodes | map(attribute='season') | unique | sort %}
                <div class="tab-pane" id="season-{{ season_num }}"><div class="episode-list">
                    {% for ep in movie.episodes | selectattr('season', 'equalto', season_num) | sort(attribute='episode_number') %}
                    <div class="episode-item">
                        <span class="episode-name"><i class="fas fa-play-circle"></i> Episode {{ ep.episode_number }} {% if ep.title %}- {{ep.title}}{% endif %}</span>
                        {% if ep.watch_link %}<a href="{{ ep.watch_link }}" target="_blank" class="action-btn btn-primary">Download / Watch</a>{% endif %}
                    </div>
                    {% endfor %}
                </div></div>
                {% endfor %}
            {% endif %}
        </div>
    </div>
    {% if related_movies %}<section class="related-section"><h2 class="section-title">You May Also Like</h2><div class="swiper movie-carousel"><div class="swiper-wrapper">
        {% for m in related_movies %}<div class="swiper-slide"><a href="{{ url_for('movie_detail', movie_id=m._id) }}" class="movie-card">
            <img class="movie-poster" loading="lazy" src="{{ m.poster or 'https://via.placeholder.com/400x600.png?text=No+Image' }}" alt="{{ m.title }}">
            <h4 class="card-title">{{ m.title }}</h4><p class="card-meta">{{ m.release_date.split('-')[0] if m.release_date else '' }}</p>
        </a></div>{% endfor %}
    </div><div class="swiper-button-next"></div><div class="swiper-button-prev"></div></div></section>{% endif %}
</div>
{% else %}<div style="display:flex; justify-content:center; align-items:center; height:100vh;"><h2>Content not found.</h2></div>{% endif %}
<script src="https://unpkg.com/swiper/swiper-bundle.min.js"></script>
<script>
    new Swiper('.movie-carousel', { slidesPerView: 'auto', spaceBetween: 20, navigation: { nextEl: '.swiper-button-next', prevEl: '.swiper-button-prev' }});
    const tabLinks = document.querySelectorAll('.tab-link'), tabPanes = document.querySelectorAll('.tab-pane');
    tabLinks.forEach(link => { link.addEventListener('click', () => {
        const tabId = link.getAttribute('data-tab');
        tabLinks.forEach(item => item.classList.remove('active'));
        tabPanes.forEach(pane => pane.classList.remove('active'));
        link.classList.add('active');
        document.getElementById(tabId).classList.add('active');
    }); });
</script>
</body></html>
"""
admin_html = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Admin Panel - {{ website_name }}</title>
    <link href="https://fonts.googleapis.com/css2?family=Bebas+Neue&family=Roboto:wght@400;700&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.2.0/css/all.min.css">
    <style>
        :root { --netflix-red: #E50914; --netflix-red-dark: #B20710; --netflix-black: #141414; --dark-gray: #222; --light-gray: #333; --text-light: #f5f5f5; }
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
        .btn { display: inline-block; text-decoration: none; color: white; font-weight: 700; cursor: pointer; border: none; padding: 12px 25px; border-radius: 4px; font-size: 1rem; }
        .btn-primary { background: var(--netflix-red); } .btn-secondary { background: #555; } .btn-danger { background: #dc3545; }
        .btn-edit { background: #007bff; }
        .table-container { display: block; overflow-x: auto; }
        table { width: 100%; border-collapse: collapse; } th, td { padding: 12px 15px; text-align: left; border-bottom: 1px solid var(--light-gray); }
        .action-buttons { display: flex; gap: 10px; }
        .dynamic-item { border: 1px solid var(--light-gray); padding: 15px; margin-bottom: 15px; border-radius: 5px; position: relative; }
        .dynamic-item .btn-danger { position: absolute; top: 10px; right: 10px; padding: 4px 8px; font-size: 0.8rem; }
        hr { border: 0; height: 1px; background-color: var(--light-gray); margin: 50px 0; }
        .tmdb-fetcher { display: flex; gap: 10px; }
        /* Modal Styles */
        .modal-overlay { position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.8); z-index: 2000; display: none; justify-content: center; align-items: center; }
        .modal-content { background: var(--dark-gray); padding: 30px; border-radius: 8px; width: 90%; max-width: 800px; max-height: 80vh; overflow-y: auto; }
        .modal-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; }
        .modal-close { background: none; border: none; color: #fff; font-size: 2rem; cursor: pointer; }
        #search-results { display: grid; grid-template-columns: repeat(auto-fill, minmax(150px, 1fr)); gap: 20px; }
        .result-item { cursor: pointer; text-align: center; }
        .result-item img { width: 100%; aspect-ratio: 2/3; object-fit: cover; border-radius: 5px; margin-bottom: 10px; transition: transform 0.2s; }
        .result-item:hover img { transform: scale(1.05); border: 2px solid var(--netflix-red); }
        .result-item p { font-size: 0.9rem; }
    </style>
</head>
<body>
<div class="admin-container">
    <header class="admin-header"><h1>Admin Panel</h1><a href="{{ url_for('home') }}" target="_blank">View Site</a></header>
    <h2><i class="fas fa-plus-circle"></i> Add New Content</h2>
    <fieldset><legend>Automatic Method</legend>
        <div class="form-group"><label for="tmdb_search_query">Search by Movie/Series Name</label>
            <div class="tmdb-fetcher">
                <input type="text" id="tmdb_search_query" placeholder="e.g., Avengers Endgame">
                <button type="button" id="tmdb_search_btn" class="btn btn-primary" onclick="searchTmdb()">Search</button>
            </div>
        </div>
    </fieldset>
    <form method="post">
        <input type="hidden" name="tmdb_id" id="tmdb_id">
        <fieldset><legend>Content Details</legend>
            <div class="form-group"><label>Title:</label><input type="text" name="title" id="title" required></div>
            <div class="form-group"><label>Poster URL:</label><input type="url" name="poster" id="poster"></div>
            <div class="form-group"><label>Backdrop URL (Slider Image):</label><input type="url" name="backdrop" id="backdrop"></div>
            <div class="form-group"><label>Overview:</label><textarea name="overview" id="overview"></textarea></div>
            <div class="form-group"><label>Genres (comma-separated):</label><input type="text" name="genres" id="genres"></div>
            <div class="form-group"><label>Content Type:</label><select name="content_type" id="content_type" onchange="toggleFields()"><option value="movie">Movie</option><option value="series">Series</option></select></div>
            <div class="form-group"><label>Screenshots (URLs, one per line):</label><textarea name="screenshots" rows="4"></textarea></div>
        </fieldset>
        <div id="movie_fields">
            <fieldset><legend>Movie Links</legend>
                <p><b>Direct Download Links</b></p>
                <div class="form-group"><label>480p Link:</label><input type="url" name="link_480p"></div>
                <div class="form-group"><label>720p Link:</label><input type="url" name="link_720p"></div>
                <div class="form-group"><label>1080p Link:</label><input type="url" name="link_1080p"></div>
            </fieldset>
        </div>
        <div id="episode_fields" style="display: none;">
            <fieldset><legend>Series Episodes</legend>
                <div id="episodes_container"></div>
                <button type="button" onclick="addEpisodeField()" class="btn btn-secondary"><i class="fas fa-plus"></i> Add Episode</button>
            </fieldset>
        </div>
        <button type="submit" class="btn btn-primary"><i class="fas fa-check"></i> Add Content</button>
    </form>
    <hr>
    <h2><i class="fas fa-tasks"></i> Manage Content</h2>
    <div class="table-container"><table><thead><tr><th>Title</th><th>Type</th><th>Actions</th></tr></thead><tbody>
    {% for movie in content_list %}
    <tr><td>{{ movie.title }}</td><td>{{ movie.type|title }}</td>
        <td class="action-buttons">
            <a href="{{ url_for('edit_movie', movie_id=movie._id) }}" class="btn btn-edit">Edit</a>
            <a href="{{ url_for('delete_movie', movie_id=movie._id) }}" onclick="return confirm('Are you sure you want to delete this item?')" class="btn btn-danger">Delete</a>
        </td>
    </tr>
    {% else %}
    <tr><td colspan="3" style="text-align:center;">No content found.</td></tr>
    {% endfor %}
    </tbody></table></div>
</div>

<!-- Search Results Modal -->
<div class="modal-overlay" id="search-modal">
    <div class="modal-content">
        <div class="modal-header">
            <h2>Select Content</h2>
            <button class="modal-close" onclick="closeModal()">&times;</button>
        </div>
        <div id="search-results"><p>Type a name and click search to see results.</p></div>
    </div>
</div>

<script>
    const modal = document.getElementById('search-modal');
    const searchResultsContainer = document.getElementById('search-results');
    const searchBtn = document.getElementById('tmdb_search_btn');

    function toggleFields() {
        const isSeries = document.getElementById('content_type').value === 'series';
        document.getElementById('episode_fields').style.display = isSeries ? 'block' : 'none';
        document.getElementById('movie_fields').style.display = isSeries ? 'none' : 'block';
    }
    function addEpisodeField() {
        const c = document.getElementById('episodes_container');
        const d = document.createElement('div');
        d.className = 'dynamic-item';
        d.innerHTML = `<button type="button" onclick="this.parentElement.remove()" class="btn btn-danger">X</button>
            <div class="form-group"><label>Season:</label><input type="number" name="episode_season[]" value="1" required></div>
            <div class="form-group"><label>Episode:</label><input type="number" name="episode_number[]" required></div>
            <div class="form-group"><label>Title (Optional):</label><input type="text" name="episode_title[]"></div>
            <div class="form-group"><label>Download/Watch Link:</label><input type="url" name="episode_watch_link[]" required></div>`;
        c.appendChild(d);
    }
    
    // --- New TMDb Search and Fetch Logic ---

    function openModal() { modal.style.display = 'flex'; }
    function closeModal() { modal.style.display = 'none'; }

    async function searchTmdb() {
        const query = document.getElementById('tmdb_search_query').value;
        if (!query) return alert('Please enter a movie or series name to search.');
        
        searchBtn.disabled = true; searchBtn.innerHTML = 'Searching...';
        searchResultsContainer.innerHTML = '<p>Loading results...</p>';
        openModal();

        try {
            const response = await fetch('/admin/api/search_tmdb?query=' + encodeURIComponent(query));
            const results = await response.json();
            if (!response.ok) throw new Error(results.error);

            if (results.length === 0) {
                searchResultsContainer.innerHTML = '<p>No results found.</p>';
                return;
            }

            searchResultsContainer.innerHTML = ''; // Clear previous results
            results.forEach(item => {
                const resultDiv = document.createElement('div');
                resultDiv.className = 'result-item';
                resultDiv.onclick = () => selectResult(item.id, item.media_type);
                resultDiv.innerHTML = `
                    <img src="${item.poster}" alt="${item.title}">
                    <p>${item.title} (${item.year})</p>
                `;
                searchResultsContainer.appendChild(resultDiv);
            });
        } catch (error) {
            searchResultsContainer.innerHTML = `<p style="color:red;">Error: ${error.message}</p>`;
        } finally {
            searchBtn.disabled = false; searchBtn.innerHTML = 'Search';
        }
    }

    function selectResult(tmdbId, mediaType) {
        closeModal();
        // Construct a dummy URL for the existing fetch details function
        const url = `https://www.themoviedb.org/${mediaType}/${tmdbId}`;
        getTmdbDetails(url);
    }

    async function getTmdbDetails(url) {
        const btn = document.getElementById('tmdb_search_btn'); // Use search btn for status
        btn.disabled = true; btn.innerHTML = 'Fetching...';
        try {
            const response = await fetch('/admin/api/fetch_tmdb?url=' + encodeURIComponent(url));
            const data = await response.json();
            if (!response.ok) throw new Error(data.error);
            
            // Populate the form
            document.getElementById('tmdb_id').value = data.tmdb_id || '';
            document.getElementById('title').value = data.title || '';
            document.getElementById('overview').value = data.overview || '';
            document.getElementById('poster').value = data.poster || '';
            document.getElementById('backdrop').value = data.backdrop || '';
            document.getElementById('genres').value = data.genres ? data.genres.join(', ') : '';
            document.getElementById('content_type').value = data.type === 'series' ? 'series' : 'movie';
            
            alert(`'${data.title}' details have been filled. Please add download links and save.`);
            toggleFields();
        } catch (error) {
            alert('Failed to fetch details from TMDB. ' + error.message);
        } finally {
            btn.disabled = false; btn.innerHTML = 'Search';
        }
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
    <link href="https://fonts.googleapis.com/css2?family=Bebas+Neue&family=Roboto:wght@400;700&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.2.0/css/all.min.css">
    <style>
        :root { --netflix-red: #E50914; --netflix-black: #141414; --dark-gray: #222; --light-gray: #333; --text-light: #f5f5f5; }
        body { font-family: 'Roboto', sans-serif; background: var(--netflix-black); color: var(--text-light); padding: 20px; }
        .admin-container { max-width: 800px; margin: 20px auto; }
        .back-link { display: inline-block; margin-bottom: 20px; color: #999; text-decoration: none; }
        h2 { font-family: 'Bebas Neue', sans-serif; color: var(--netflix-red); font-size: 2.5rem; }
        form { background: var(--dark-gray); padding: 25px; border-radius: 8px; }
        fieldset { border: 1px solid var(--light-gray); padding: 20px; margin-bottom: 20px; }
        legend { font-weight: bold; color: var(--netflix-red); padding: 0 10px; font-size: 1.2rem; }
        .form-group { margin-bottom: 15px; } label { display: block; margin-bottom: 8px; }
        input, textarea, select { width: 100%; padding: 12px; border-radius: 4px; border: 1px solid var(--light-gray); font-size: 1rem; background: var(--light-gray); color: var(--text-light); box-sizing: border-box; }
        .btn { display: inline-block; color: white; cursor: pointer; border: none; padding: 12px 25px; border-radius: 4px; font-size: 1rem; }
        .btn-primary { background: var(--netflix-red); } .btn-secondary { background: #555; } .btn-danger { background: #dc3545; }
        .dynamic-item { border: 1px solid var(--light-gray); padding: 15px; margin-bottom: 15px; border-radius: 5px; position: relative; }
        .dynamic-item .btn-danger { position: absolute; top: 10px; right: 10px; padding: 4px 8px; }
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
        <div class="form-group"><label>Genres:</label><input type="text" name="genres" value="{{ movie.genres|join(', ') if movie.genres else '' }}"></div>
        <div class="form-group"><label>Content Type:</label><select name="content_type" id="content_type" onchange="toggleFields()"><option value="movie" {% if movie.type == 'movie' %}selected{% endif %}>Movie</option><option value="series" {% if movie.type == 'series' %}selected{% endif %}>Series</option></select></div>
        <div class="form-group"><label>Screenshots (URLs, one per line):</label><textarea name="screenshots" rows="4">{{ (movie.screenshots or [])|join('\n') }}</textarea></div>
    </fieldset>
    <div id="movie_fields">
        <fieldset><legend>Movie Links</legend>
            <p><b>Download Links</b></p>
            <div class="form-group"><label>480p Link:</label><input type="url" name="link_480p" value="{% for l in movie.links %}{% if l.quality == '480p' %}{{ l.url }}{% endif %}{% endfor %}"></div>
            <div class="form-group"><label>720p Link:</label><input type="url" name="link_720p" value="{% for l in movie.links %}{% if l.quality == '720p' %}{{ l.url }}{% endif %}{% endfor %}"></div>
            <div class="form-group"><label>1080p Link:</label><input type="url" name="link_1080p" value="{% for l in movie.links %}{% if l.quality == '1080p' %}{{ l.url }}{% endif %}{% endfor %}"></div>
        </fieldset>
    </div>
    <div id="episode_fields" style="display: none;">
      <fieldset><legend>Episodes</legend>
        <div id="episodes_container">
        {% if movie.type == 'series' and movie.episodes %}{% for ep in movie.episodes | sort(attribute='episode_number') | sort(attribute='season') %}
        <div class="dynamic-item">
            <button type="button" onclick="this.parentElement.remove()" class="btn btn-danger">X</button>
            <div class="form-group"><label>Season:</label><input type="number" name="episode_season[]" value="{{ ep.season or 1 }}" required></div>
            <div class="form-group"><label>Episode:</label><input type="number" name="episode_number[]" value="{{ ep.episode_number }}" required></div>
            <div class="form-group"><label>Title:</label><input type="text" name="episode_title[]" value="{{ ep.title or '' }}"></div>
            <div class="form-group"><label>Download/Watch Link:</label><input type="url" name="episode_watch_link[]" value="{{ ep.watch_link or '' }}" required></div>
        </div>
        {% endfor %}{% endif %}</div>
        <button type="button" onclick="addEpisodeField()" class="btn btn-secondary"><i class="fas fa-plus"></i> Add Episode</button>
      </fieldset>
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
# =======================================================================================
# === [END] HTML TEMPLATES ==========================================================
# =======================================================================================

# --- TMDB API Functions ---
def get_tmdb_details_from_api(tmdb_id, content_type):
    if not TMDB_API_KEY: return None
    search_type = "tv" if content_type == "series" else "movie"
    try:
        detail_url = f"https://api.themoviedb.org/3/{search_type}/{tmdb_id}?api_key={TMDB_API_KEY}"
        res = requests.get(detail_url, timeout=10)
        res.raise_for_status()
        data = res.json()
        
        details = {
            "tmdb_id": tmdb_id, 
            "title": data.get("title") or data.get("name"), 
            "poster": f"https://image.tmdb.org/t/p/w500{data.get('poster_path')}" if data.get('poster_path') else None,
            "backdrop": f"https://image.tmdb.org/t/p/w1280{data.get('backdrop_path')}" if data.get('backdrop_path') else None,
            "overview": data.get("overview"), 
            "release_date": data.get("release_date") or data.get("first_air_date"), 
            "genres": [g['name'] for g in data.get("genres", [])], 
            "vote_average": data.get("vote_average"), 
            "type": "series" if search_type == "tv" else "movie"
        }
        print(f"SUCCESS: Found TMDb details for '{details['title']}' (ID: {tmdb_id}).")
        return details
    except requests.RequestException as e:
        print(f"ERROR: TMDb API request failed. Reason: {e}")
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
    
    context = {
        "trending_movies": list(movies.find({"categories": "Trending"}).sort('_id', -1).limit(12)),
        "latest_movies": list(movies.find({"type": "movie"}).sort('_id', -1).limit(12)),
        "latest_series": list(movies.find({"type": "series"}).sort('_id', -1).limit(12)),
        "hindi_movies": list(movies.find({"categories": "Hindi"}).sort('_id', -1).limit(12)),
        "bengali_movies": list(movies.find({"categories": "Bengali"}).sort('_id', -1).limit(12)),
        "english_movies": list(movies.find({"categories": "English"}).sort('_id', -1).limit(12)),
        "coming_soon_movies": list(movies.find({"is_coming_soon": True}).sort('_id', -1).limit(12)),
        "recently_added": list(movies.find({"backdrop": {"$ne": None}}).sort('_id', -1).limit(8)),
        "is_full_page_list": False, "query": ""
    }
    return render_template_string(index_html, **context)

@app.route('/movie/<movie_id>')
def movie_detail(movie_id):
    try:
        movie = movies.find_one({"_id": ObjectId(movie_id)})
        if not movie: return "Content not found", 404
        related_movies = []
        if movie.get("genres"):
            related_movies = list(movies.find({"genres": {"$in": movie["genres"]}, "_id": {"$ne": ObjectId(movie_id)}}).limit(12))
        return render_template_string(detail_html, movie=movie, related_movies=related_movies)
    except Exception: return "Content not found", 404

@app.route('/category/<cat_name>')
def movies_by_category(cat_name):
    query = {}
    title = cat_name.replace("_", " ").title()
    if cat_name == "Latest Movie": query = {"type": "movie"}
    elif cat_name == "Latest Series": query = {"type": "series"}
    elif cat_name == "Coming Soon": query = {"is_coming_soon": True}
    else: query = {"categories": title}
    
    content_list = list(movies.find(query).sort('_id', -1))
    return render_template_string(index_html, movies=content_list, query=title, is_full_page_list=True)

@app.route('/genres')
def genres_page():
    return "Genres page coming soon!", 200

@app.route('/genre/<genre_name>')
def movies_by_genre(genre_name):
    content_list = list(movies.find({"genres": genre_name}).sort('_id', -1))
    return render_template_string(index_html, movies=content_list, query=f'Genre: {genre_name}', is_full_page_list=True)

# --- Admin Routes ---
@app.route('/admin', methods=["GET", "POST"])
@requires_auth
def admin():
    if request.method == "POST":
        content_type = request.form.get("content_type", "movie")
        
        movie_data = {
            "title": request.form.get("title").strip(),
            "type": content_type,
            "poster": request.form.get("poster").strip(),
            "backdrop": request.form.get("backdrop").strip(),
            "overview": request.form.get("overview").strip(),
            "genres": [g.strip() for g in request.form.get("genres").split(',') if g.strip()],
            "screenshots": [url.strip() for url in request.form.get("screenshots").splitlines() if url.strip()],
            "episodes": [], "links": [], "streaming_links": [], "categories": []
        }
        
        tmdb_id = request.form.get("tmdb_id")
        if tmdb_id:
            tmdb_details = get_tmdb_details_from_api(tmdb_id, content_type)
            if tmdb_details:
                movie_data['title'] = movie_data['title'] or tmdb_details.get('title')
                movie_data['overview'] = movie_data['overview'] or tmdb_details.get('overview')
                movie_data['poster'] = movie_data['poster'] or tmdb_details.get('poster')
                movie_data['backdrop'] = movie_data['backdrop'] or tmdb_details.get('backdrop')
                if not movie_data['genres']: movie_data['genres'] = tmdb_details.get('genres', [])
                movie_data['release_date'] = tmdb_details.get('release_date')
                movie_data['vote_average'] = tmdb_details.get('vote_average')

        if not movie_data['poster']: movie_data['poster'] = PLACEHOLDER_POSTER
        if not movie_data['backdrop']: movie_data['backdrop'] = None

        if content_type == "movie":
            movie_data["links"] = [{"quality": q, "url": u} for q, u in [("480p", request.form.get("link_480p")), ("720p", request.form.get("link_720p")), ("1080p", request.form.get("link_1080p"))] if u and u.strip()]
        else: # Series
            for s, e, t, w in zip(request.form.getlist('episode_season[]'), request.form.getlist('episode_number[]'), request.form.getlist('episode_title[]'), request.form.getlist('episode_watch_link[]')):
                if s and e and w:
                    movie_data['episodes'].append({"season": int(s), "episode_number": int(e), "title": t.strip(), "watch_link": w.strip()})

        movies.insert_one(movie_data)
        return redirect(url_for('admin'))

    content_list = list(movies.find().sort('_id', -1))
    return render_template_string(admin_html, content_list=content_list)

@app.route('/edit_movie/<movie_id>', methods=["GET", "POST"])
@requires_auth
def edit_movie(movie_id):
    obj_id = ObjectId(movie_id)
    movie_obj = movies.find_one({"_id": obj_id})
    if not movie_obj: return "Movie not found", 404

    if request.method == "POST":
        content_type = request.form.get("content_type")
        update_data = {
            "title": request.form.get("title").strip(), "type": content_type,
            "poster": request.form.get("poster").strip() or PLACEHOLDER_POSTER,
            "backdrop": request.form.get("backdrop").strip() or None,
            "overview": request.form.get("overview").strip(),
            "genres": [g.strip() for g in request.form.get("genres").split(',') if g.strip()],
            "screenshots": [url.strip() for url in request.form.get("screenshots").splitlines() if url.strip()],
        }
        
        if content_type == "movie":
            update_data["links"] = [{"quality": q, "url": u} for q, u in [("480p", request.form.get("link_480p")), ("720p", request.form.get("link_720p")), ("1080p", request.form.get("link_1080p"))] if u and u.strip()]
            movies.update_one({"_id": obj_id}, {"$set": update_data, "$unset": {"episodes": ""}})
        else: # Series
            update_data["episodes"] = [{"season": int(s), "episode_number": int(e), "title": t.strip(), "watch_link": w.strip()} for s, e, t, w in zip(request.form.getlist('episode_season[]'), request.form.getlist('episode_number[]'), request.form.getlist('episode_title[]'), request.form.getlist('episode_watch_link[]')) if s and e and w]
            movies.update_one({"_id": obj_id}, {"$set": update_data, "$unset": {"links": ""}})
        
        return redirect(url_for('admin'))

    return render_template_string(edit_html, movie=movie_obj)

@app.route('/delete_movie/<movie_id>')
@requires_auth
def delete_movie(movie_id):
    movies.delete_one({"_id": ObjectId(movie_id)})
    return redirect(url_for('admin'))

# --- NEW/UPDATED API Routes for Admin Panel ---

@app.route('/admin/api/search_tmdb')
@requires_auth
def search_tmdb():
    query = request.args.get('query')
    if not query:
        return jsonify({"error": "Query parameter is missing"}), 400
    try:
        search_url = f"https://api.themoviedb.org/3/search/multi?api_key={TMDB_API_KEY}&query={query}"
        res = requests.get(search_url, timeout=10)
        res.raise_for_status()
        data = res.json()
        
        results = []
        for item in data.get('results', []):
            if item.get('media_type') in ['movie', 'tv']:
                results.append({
                    "id": item.get('id'),
                    "title": item.get('title') or item.get('name'),
                    "year": (item.get('release_date') or item.get('first_air_date', 'N/A')).split('-')[0],
                    "poster": f"https://image.tmdb.org/t/p/w200{item.get('poster_path')}" if item.get('poster_path') else "https://via.placeholder.com/200x300.png?text=No+Image",
                    "media_type": item.get('media_type')
                })
        return jsonify(results)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/admin/api/fetch_tmdb')
@requires_auth
def fetch_tmdb_data():
    tmdb_url = request.args.get('url')
    if not tmdb_url: return jsonify({"error": "URL parameter is missing"}), 400
    try:
        path_parts = [part for part in urlparse(unquote(tmdb_url)).path.split('/') if part]
        content_type_str = path_parts[0]
        tmdb_id = path_parts[1].split('-')[0]

        if not tmdb_id.isdigit() or content_type_str not in ['movie', 'tv']:
             raise ValueError("Invalid TMDb URL structure.")
        
        content_type = "series" if content_type_str == 'tv' else "movie"
        details = get_tmdb_details_from_api(tmdb_id, content_type)
        return jsonify(details) if details else (jsonify({"error": "Details not found on TMDB"}), 404)
    except Exception as e:
        return jsonify({"error": f"An error occurred while parsing URL: {e}"}), 400


@app.route('/webhook', methods=['POST'])
def telegram_webhook():
    return jsonify(status='ok')

if __name__ == "__main__":
    app.run(debug=True, host='0.0.0.0', port=3000)
