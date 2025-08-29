import os
import sys
import requests
from flask import Flask, render_template_string, request, redirect, url_for, Response, jsonify
from pymongo import MongoClient
from bson.objectid import ObjectId
from functools import wraps
from urllib.parse import urlparse, unquote, quote

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

  /* === [START] HERO SLIDER STYLE CHANGES === */
  .hero-slider {
    width: 100%;
    margin-top: var(--nav-height);
    aspect-ratio: 16 / 9; /* This creates the landscape ratio */
    max-height: 600px; /* Optional: limits height on very large screens */
  }
  .hero-slide {
    position: relative;
    display: flex;
    align-items: flex-end; /* Align content to the bottom */
    justify-content: flex-start;
    border-radius: 12px;
    overflow: hidden;
  }
  .hero-bg-img {
    position: absolute;
    top: 0;
    left: 0;
    width: 100%;
    height: 100%;
    object-fit: cover;
    object-position: center;
  }
  .hero-slide::before {
    content: '';
    position: absolute;
    top: 0;
    left: 0;
    width: 100%;
    height: 100%;
    /* New gradient from bottom to top for text readability */
    background: linear-gradient(to top, rgba(0,0,0,0.9) 0%, rgba(0,0,0,0.6) 25%, transparent 60%);
  }
  .hero-content {
    position: relative;
    z-index: 2;
    padding: 20px 40px; /* Adjusted padding */
    width: 100%;
  }
  .hero-title {
    font-size: 2.2rem; /* Adjusted font size */
    font-weight: 600;
    line-height: 1.2;
    margin: 0;
  }
  .hero-meta {
    font-size: 0.9rem;
    color: var(--text-dark);
    margin-top: 5px;
  }
  .slide-type-tag {
    position: absolute;
    top: 20px;
    right: 20px;
    background-color: var(--primary-color);
    color: white;
    padding: 5px 12px;
    border-radius: 5px;
    font-size: 0.8rem;
    font-weight: 600;
    z-index: 3;
    text-transform: uppercase;
  }
  /* === [END] HERO SLIDER STYLE CHANGES === */

  .swiper-pagination-bullet {
    background: rgba(255,255,255,0.5);
  }
  .swiper-pagination-bullet-active {
    background: var(--primary-color);
    width: 20px;
    border-radius: 5px;
  }
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
  .ad-container { margin: 40px 0; display: flex; justify-content: center; align-items: center; }
  
  @media (max-width: 992px) {.nav-links, .search-form { display: none; } .menu-toggle { display: block; } }
  
  @media (max-width: 768px) {
    .container, .full-page-grid-container { padding: 0 20px; } 
    .full-page-grid-container{padding-top:100px;padding-bottom:40px;} 
    .logo { font-size: 1.5rem; } 
    /* Mobile slider adjustments */
    .hero-slider { margin-top: calc(var(--nav-height) + 10px); aspect-ratio: 16 / 10; }
    .hero-content { padding: 15px 20px; }
    .hero-title { font-size: 1.5rem; }
    .hero-meta { font-size: 0.8rem; }
    .slide-type-tag { font-size: 0.7rem; padding: 4px 10px; top: 15px; right: 15px; }

    .category-title { font-size: 1.4rem; } 
    .movie-poster { width: 160px; } 
    .full-page-grid { grid-template-columns: repeat(auto-fill, minmax(140px, 1fr)); } 
  }
</style>
</head>
<body>
{{ ad_settings.ad_body_top | safe }}
<header class="main-header">
    <div class="container header-content">
        <a href="{{ url_for('home') }}" class="logo">{{ website_name }}</a>
        <nav class="nav-links">
            <a href="{{ url_for('home') }}" class="active">Home</a>
            <a href="{{ url_for('movies_by_category', cat_name='Latest Movie') }}">Movies</a>
            <a href="{{ url_for('movies_by_category', cat_name='Latest Series') }}">Series</a>
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
    <!-- [START] HERO SLIDER HTML CHANGES -->
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
    <!-- [END] HERO SLIDER HTML CHANGES -->

    <div class="container">
    {% macro render_carousel_section(title, movies_list, cat_name) %}
        {% if movies_list %}
        <section class="category-section">
            <div class="category-header">
                <h2 class="category-title">{{ title }}</h2>
                <a href="{{ url_for('movies_by_category', cat_name=cat_name) }}" class="view-all-link">View All</a>
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
    {{ render_carousel_section('Latest Movies', latest_movies, 'Latest Movie') }}
    {{ render_carousel_section('Latest Series', latest_series, 'Latest Series') }}
    {% if ad_settings.ad_list_page %}<div class="ad-container">{{ ad_settings.ad_list_page | safe }}</div>{% endif %}
    {% for cat_name, movies_list in categorized_content.items() %}
        {% if cat_name != 'Trending' %}
             {{ render_carousel_section(cat_name, movies_list, cat_name) }}
        {% endif %}
    {% endfor %}
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
    new Swiper('.hero-slider', { 
        loop: true, 
        autoplay: { delay: 4000 }, 
        pagination: { el: '.swiper-pagination', clickable: true }, 
    });
    new Swiper('.movie-carousel', { slidesPerView: 'auto', spaceBetween: 20, navigation: { nextEl: '.swiper-button-next', prevEl: '.swiper-button-prev', }, breakpoints: { 320: { spaceBetween: 15 }, 768: { spaceBetween: 20 }, } });
</script>
{{ ad_settings.ad_footer | safe }}
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
# =======================================================================================
# === [END] HTML TEMPLATES ============================================================
# =======================================================================================

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

    context = {
        "latest_movies": list(movies.find({"type": "movie"}).sort('_id', -1).limit(12)),
        "latest_series": list(movies.find({"type": "series"}).sort('_id', -1).limit(12)),
        "recently_added": list(movies.find({"backdrop": {"$ne": None}}).sort('_id', -1).limit(8)),
        "categorized_content": categorized_content,
        "is_full_page_list": False
    }
    return render_template_string(index_html, **context)

@app.route('/movie/<movie_id>')
def movie_detail(movie_id):
    try:
        movie = movies.find_one({"_id": ObjectId(movie_id)})
        if not movie: return "Content not found", 404
        return render_template_string(detail_html, movie=movie)
    except Exception: return "Content not found", 404

@app.route('/category/<cat_name>')
def movies_by_category(cat_name):
    query = {}
    title = cat_name.replace("_", " ").title()
    if cat_name == "Latest Movie": query = {"type": "movie"}
    elif cat_name == "Latest Series": query = {"type": "series"}
    else: query = {"categories": title}
    
    content_list = list(movies.find(query).sort('_id', -1))
    return render_template_string(index_html, movies=content_list, query=title, is_full_page_list=True)

@app.route('/wait')
def wait_page():
    encoded_target_url = request.args.get('target')
    if not encoded_target_url:
        return redirect(url_for('home'))
    
    # *** THIS IS THE FIX ***
    # Decode the URL before passing it to the template
    decoded_target_url = unquote(encoded_target_url)
    
    return render_template_string(wait_page_html, target_url=decoded_target_url)

@app.route('/admin', methods=["GET", "POST"])
@requires_auth
def admin():
    if request.method == "POST":
        form_action = request.form.get("form_action")

        if form_action == "update_ads":
            ad_settings = {
                "ad_header": request.form.get("ad_header"),
                "ad_body_top": request.form.get("ad_body_top"),
                "ad_footer": request.form.get("ad_footer"),
                "ad_list_page": request.form.get("ad_list_page"),
                "ad_detail_page": request.form.get("ad_detail_page"),
                "ad_wait_page": request.form.get("ad_wait_page"),
            }
            settings.update_one({"_id": "ad_config"}, {"$set": ad_settings}, upsert=True)
        
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
                seasons, numbers, titles, links = request.form.getlist('episode_season[]'), request.form.getlist('episode_number[]'), request.form.getlist('episode_title[]'), request.form.getlist('episode_watch_link[]')
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
            update_data["episodes"] = [{"season": int(s), "episode_number": int(e), "title": t.strip(), "watch_link": w.strip()} for s, e, t, w in zip(request.form.getlist('episode_season[]'), request.form.getlist('episode_number[]'), request.form.getlist('episode_title[]'), request.form.getlist('episode_watch_link[]')) if s and e and w]
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
        search_url = f"https://api.themoviedb.org/3/search/multi?api_key={TMDB_API_KEY}&query={query}"
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

if __name__ == "__main__":
    app.run(debug=True, host='0.0.0.0', port=int(os.environ.get('PORT', 3000)))
