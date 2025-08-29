import os
import sys
import re
import requests
import json
from flask import Flask, render_template_string, request, redirect, url_for, Response, jsonify
from pymongo import MongoClient
from bson.objectid import ObjectId
from functools import wraps
from datetime import datetime, timedelta
from apscheduler.schedulers.background import BackgroundScheduler
from urllib.parse import urlparse, unquote


MONGO_URI = os.environ.get("MONGO_URI", "mongodb+srv://tocewe6727:tocewe6727@cluster0.q4o59lo.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "7880675542:AAHY83itDOUhASDXgaZRodMg5IhGI_dtfEA")
TMDB_API_KEY = os.environ.get("TMDB_API_KEY", "7dc544d9253bccc3cfecc1c677f69819")
ADMIN_CHANNEL_ID = int(os.environ.get("ADMIN_CHANNEL_ID", -1003012555805))
BOT_USERNAME = os.environ.get("BOT_USERNAME", "MovieZoneBDBot")
ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "Moviezonebd")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "Moviezonebd")

MAIN_CHANNEL_LINK = os.environ.get("MAIN_CHANNEL_LINK", "https://t.me/+60goZWp-FpkxNzVl")
UPDATE_CHANNEL_LINK = os.environ.get("UPDATE_CHANNEL_LINK", "https://t.me/AllBotUpdatemy")
DEVELOPER_USER_LINK = os.environ.get("DEVELOPER_USER_LINK", "https://t.me/Ctgmovies23")

NOTIFICATION_CHANNEL_ID = int(os.environ.get("NOTIFICATION_CHANNEL_ID", -1002896064142))

# --- Validate that all required environment variables are set ---
required_vars = {
    "MONGO_URI": MONGO_URI, "BOT_TOKEN": BOT_TOKEN, "TMDB_API_KEY": TMDB_API_KEY,
    "ADMIN_CHANNEL_ID": ADMIN_CHANNEL_ID, "BOT_USERNAME": BOT_USERNAME,
    "ADMIN_USERNAME": ADMIN_USERNAME, "ADMIN_PASSWORD": ADMIN_PASSWORD,
    "MAIN_CHANNEL_LINK": MAIN_CHANNEL_LINK,
    "UPDATE_CHANNEL_LINK": UPDATE_CHANNEL_LINK,
    "DEVELOPER_USER_LINK": DEVELOPER_USER_LINK,
    "NOTIFICATION_CHANNEL_ID": NOTIFICATION_CHANNEL_ID
}

# Avoid crashing the Vercel build process if env vars are not set during build time
is_vercel_build = os.environ.get('VERCEL') == '1'
if not is_vercel_build:
    missing_vars = [name for name, value in required_vars.items() if not value]
    if missing_vars:
        print(f"FATAL: Missing required environment variables: {', '.join(missing_vars)}")
        sys.exit(1)


TELEGRAM_API_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"
PLACEHOLDER_POSTER = "https://via.placeholder.com/400x600.png?text=Poster+Not+Found"
app = Flask(__name__)

# [NEW] Define categories
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
    settings = db["settings"]
    feedback = db["feedback"]
    print("SUCCESS: Successfully connected to MongoDB!")
except Exception as e:
    print(f"FATAL: Error connecting to MongoDB: {e}. Exiting.")
    if not is_vercel_build:
        sys.exit(1)

# --- Template Processor ---
@app.context_processor
def inject_globals():
    ad_codes = settings.find_one()
    return dict(
        ad_settings=(ad_codes or {}),
        bot_username=BOT_USERNAME,
        main_channel_link=MAIN_CHANNEL_LINK
    )


scheduler = BackgroundScheduler(daemon=True)
scheduler.start()

def delete_message_after_delay(chat_id, message_id):
    print(f"Attempting to delete message {message_id} from chat {chat_id}")
    try:
        url = f"{TELEGRAM_API_URL}/deleteMessage"
        payload = {'chat_id': chat_id, 'message_id': message_id}
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print(f"Error in delete_message_after_delay: {e}")

def escape_markdown(text: str) -> str:
    if not isinstance(text, str): return ''
    escape_chars = r'_*[]()~`>#+-=|{}.!'
    return re.sub(f'([{re.escape(escape_chars)}])', r'\\\1', text)

# [NEW] Helper to get YouTube embed key from various URL formats
def get_youtube_embed_key(url):
    if not url or not isinstance(url, str):
        return None
    try:
        # Regex to find YouTube ID in various URL formats
        regex = r'(?:https?:\/\/)?(?:www\.)?(?:youtube\.com\/(?:[^\/\n\s]+\/\S+\/|(?:v|e(?:mbed)?)\/|\S*?[?&]v=)|youtu\.be\/)([a-zA-Z0-9_-]{11})'
        match = re.search(regex, url)
        return match.group(1) if match else None
    except Exception:
        return None

def send_notification_to_channel(movie_data):
    if not NOTIFICATION_CHANNEL_ID:
        print("INFO: NOTIFICATION_CHANNEL_ID is not set. Skipping notification.")
        return

    try:
        with app.app_context():
            # For Vercel, the URL might need to be constructed from environment variables
            host_url = f"https://{os.environ.get('VERCEL_URL')}" if os.environ.get('VERCEL_URL') else 'http://localhost:3000'
            movie_url = f"{host_url}{url_for('movie_detail', movie_id=str(movie_data['_id']))}"

        title = movie_data.get('title', 'N/A')
        poster_url = movie_data.get('poster')
        is_coming_soon = movie_data.get('is_coming_soon', False)

        if not poster_url or not poster_url.startswith('http') or poster_url == PLACEHOLDER_POSTER:
            print(f"WARNING: Invalid or missing poster for '{title}'. Skipping photo notification.")
            return

        caption_parts = []
        keyboard = {}

        if is_coming_soon:
            caption_parts.append(f"⏳ **Coming Soon!** ⏳\n\n🎬 **{title}**\n")
            caption_parts.append("Get ready! This content will be available on our platform very soon. Stay tuned!")
        else:
            year = movie_data.get('release_date', '----').split('-')[0]
            genres = ", ".join(movie_data.get('genres', []))
            rating = movie_data.get('vote_average', 0)

            caption_parts.append(f"✨ **New Content Added!** ✨\n\n🎬 **{title} ({year})**\n")
            if genres: caption_parts.append(f"🎭 **Genre:** {genres}\n")
            if rating > 0: caption_parts.append(f"⭐ **Rating:** {rating:.1f}/10\n")
            caption_parts.append("\n👇 Click the button below to watch or download now from our website!")

            keyboard = {"inline_keyboard": [[{"text": "➡️ Watch / Download on Website", "url": movie_url}]]}

        caption = "".join(caption_parts)
        api_url = f"{TELEGRAM_API_URL}/sendPhoto"
        payload = {
            'chat_id': NOTIFICATION_CHANNEL_ID,
            'photo': poster_url,
            'caption': caption,
            'parse_mode': 'Markdown',
            'reply_markup': json.dumps(keyboard) if keyboard else None
        }

        response = requests.post(api_url, data=payload, timeout=15)
        response.raise_for_status()
        response_data = response.json()

        if response_data.get('ok'):
            print(f"SUCCESS: Notification sent for '{title}'.")
            if "Trending" in movie_data.get('categories', []) and not is_coming_soon:
                message_id = response_data['result']['message_id']
                pin_url = f"{TELEGRAM_API_URL}/pinChatMessage"
                pin_payload = {'chat_id': NOTIFICATION_CHANNEL_ID, 'message_id': message_id}
                pin_response = requests.post(pin_url, json=pin_payload, timeout=10)
                if pin_response.json().get('ok'):
                    print(f"SUCCESS: Message {message_id} pinned in the channel.")
        else:
            print(f"ERROR: Failed to send notification. Telegram API response: {response.text}")

    except Exception as e:
        print(f"FATAL ERROR in send_notification_to_channel: {e}")


index_html = """
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0, user-scalable=no" />
<title>PmwBD - Your Entertainment Hub</title>
<style>
  @import url('https://fonts.googleapis.com/css2?family=Bebas+Neue&family=Roboto:wght@400;500;700&display=swap');
  :root { --netflix-red: #E50914; --netflix-black: #141414; --text-light: #f5f5f5; --text-dark: #a0a0a0; --nav-height: 60px; }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: 'Roboto', sans-serif; background-color: var(--netflix-black); color: var(--text-light); overflow-x: hidden; }
  a { text-decoration: none; color: inherit; }
  ::-webkit-scrollbar { width: 8px; } ::-webkit-scrollbar-track { background: #222; } ::-webkit-scrollbar-thumb { background: #555; } ::-webkit-scrollbar-thumb:hover { background: var(--netflix-red); }
  
  /* [MODIFIED] Main Nav for Centered Logo & Menu */
  .main-nav { position: fixed; top: 0; left: 0; width: 100%; padding: 10px 20px; display: flex; justify-content: space-between; align-items: center; z-index: 1000; transition: background-color 0.3s ease; background: linear-gradient(to bottom, rgba(0,0,0,0.8) 10%, rgba(0,0,0,0)); }
  .main-nav.scrolled { background-color: var(--netflix-black); }
  .nav-left, .nav-right { display: flex; align-items: center; flex: 1; }
  .nav-right { justify-content: flex-end; }
  .logo { font-family: 'Bebas Neue', sans-serif; font-size: 32px; color: var(--netflix-red); font-weight: 700; letter-spacing: 1px; margin: 0 auto; }
  .menu-toggle { font-size: 24px; cursor: pointer; color: var(--text-light); z-index: 1002;}
  
  /* [NEW] Drawer Menu */
  .drawer-menu { position: fixed; top: 0; left: -280px; width: 280px; height: 100%; background-color: #181818; z-index: 1001; transition: left 0.3s ease; padding-top: 80px; }
  .drawer-menu.open { left: 0; }
  .drawer-menu a { display: block; padding: 15px 25px; color: var(--text-light); font-size: 1.1rem; font-weight: 500; border-bottom: 1px solid #282828; }
  .drawer-menu a:hover { background-color: var(--netflix-red); }
  .overlay { position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.6); z-index: 1000; opacity: 0; visibility: hidden; transition: opacity 0.3s ease; }
  .overlay.open { opacity: 1; visibility: visible; }
  
  .nav-links { display: flex; gap: 20px; align-items: center; }
  .nav-links a { font-weight: 500; font-size: 0.9rem; transition: color 0.2s ease; }
  .nav-links a:hover { color: var(--netflix-red); }
  .search-container { }
  .search-input { background-color: rgba(0,0,0,0.7); border: 1px solid #777; color: var(--text-light); padding: 8px 15px; border-radius: 4px; transition: width 0.3s ease, background-color 0.3s ease; width: 250px; }
  .search-input:focus { background-color: rgba(0,0,0,0.9); border-color: var(--text-light); outline: none; }
  
  /* [MODIFIED] Hero Section Height */
  .hero-section { height: 65vh; position: relative; color: white; overflow: hidden; margin-top: var(--nav-height); }
  .hero-slide { position: absolute; top: 0; left: 0; width: 100%; height: 100%; background-size: cover; background-position: center top; display: flex; align-items: flex-end; padding: 50px; opacity: 0; transition: opacity 1.5s ease-in-out; z-index: 1; }
  .hero-slide.active { opacity: 1; z-index: 2; }
  .hero-slide::before { content: ''; position: absolute; top: 0; left: 0; right: 0; bottom: 0; background: linear-gradient(to top, var(--netflix-black) 10%, transparent 50%), linear-gradient(to right, rgba(0,0,0,0.8) 0%, transparent 60%); }
  .hero-content { position: relative; z-index: 3; max-width: 50%; }
  .hero-title { font-family: 'Bebas Neue', sans-serif; font-size: 5rem; font-weight: 700; margin-bottom: 1rem; line-height: 1; }
  .hero-overview { font-size: 1.1rem; line-height: 1.5; margin-bottom: 1.5rem; max-width: 600px; display: -webkit-box; -webkit-line-clamp: 3; -webkit-box-orient: vertical; overflow: hidden; }
  .hero-buttons .btn { padding: 8px 20px; margin-right: 0.8rem; border: none; border-radius: 4px; font-size: 0.9rem; font-weight: 700; cursor: pointer; transition: opacity 0.3s ease; display: inline-flex; align-items: center; gap: 8px; }
  .btn.btn-primary { background-color: var(--netflix-red); color: white; } .btn.btn-secondary { background-color: rgba(109, 109, 110, 0.7); color: white; } .btn:hover { opacity: 0.8; }
  main { padding: 0 50px; }

  /* [NEW] Category Buttons Section */
  .category-buttons { padding: 20px 0; display: flex; justify-content: center; flex-wrap: wrap; gap: 15px; }
  .cat-btn { padding: 10px 25px; background-color: #222; border: 1px solid #444; color: var(--text-light); border-radius: 20px; font-size: 1rem; font-weight: 500; transition: all 0.2s ease; }
  .cat-btn:hover { background-color: var(--netflix-red); border-color: var(--netflix-red); transform: translateY(-2px); }

  .movie-card { display: block; cursor: pointer; transition: transform 0.3s ease; }
  .poster-wrapper { position: relative; width: 100%; border-radius: 6px; overflow: hidden; background-color: #222; display: flex; flex-direction: column; }
  .movie-poster-container { position: relative; overflow: hidden; width:100%; flex-grow:1; aspect-ratio: 2 / 3; }
  .movie-poster { width: 100%; height: 100%; object-fit: cover; display: block; transition: transform 0.4s ease; }
  .poster-badge { position: absolute; top: 10px; left: 10px; background-color: var(--netflix-red); color: white; padding: 4px 8px; border-radius: 3px; font-size: 0.75rem; font-weight: 700; z-index: 4; }
  .rating-badge { position: absolute; bottom: 10px; right: 10px; background-color: transparent; color: white; padding: 5px; font-size: 0.8rem; font-weight: 700; z-index: 3; display: flex; align-items: center; gap: 5px; text-shadow: 1px 1px 3px rgba(0,0,0,0.8); }
  .rating-badge .fa-star { color: #f5c518; }
  .card-info-static { padding: 10px 8px; background-color: #1a1a1a; text-align: left; width: 100%; flex-shrink: 0; }
  .card-info-title { font-size: 0.9rem; font-weight: 500; color: var(--text-light); margin: 0 0 4px 0; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .card-info-meta { font-size: 0.75rem; color: var(--text-dark); margin: 0; }
  @media (hover: hover) { .movie-card:hover { transform: scale(1.05); z-index: 10; box-shadow: 0 0 20px rgba(229, 9, 20, 0.5); } .movie-card:hover .movie-poster { transform: scale(1.1); } }
  .full-page-grid-container { padding-top: 100px; padding-bottom: 50px; }
  .full-page-grid-title { font-size: 2.5rem; font-weight: 700; margin-bottom: 30px; }
  .category-grid, .full-page-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 20px 15px; }
  .category-section { margin: 40px 0; }
  .category-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 15px; }
  .category-title { font-family: 'Roboto', sans-serif; font-weight: 700; font-size: 1.6rem; margin: 0; }
  .see-all-link { color: var(--text-dark); font-weight: 700; font-size: 0.9rem; }
  .bottom-nav { display: none; position: fixed; bottom: 0; left: 0; right: 0; height: var(--nav-height); background-color: #181818; border-top: 1px solid #282828; justify-content: space-around; align-items: center; z-index: 200; }
  .nav-item { display: flex; flex-direction: column; align-items: center; color: var(--text-dark); font-size: 10px; flex-grow: 1; padding: 5px 0; transition: color 0.2s ease; }
  .nav-item i { font-size: 20px; margin-bottom: 4px; } .nav-item.active { color: var(--text-light); } .nav-item.active i { color: var(--netflix-red); }
  .ad-container { margin: 40px 0; display: flex; justify-content: center; align-items: center; }
  .telegram-join-section { background-color: #181818; padding: 40px 20px; text-align: center; margin: 50px -50px 0 -50px; }
  .telegram-join-section .telegram-icon { font-size: 4rem; color: #2AABEE; margin-bottom: 15px; } .telegram-join-section h2 { font-family: 'Bebas Neue', sans-serif; font-size: 2.5rem; color: var(--text-light); margin-bottom: 10px; }
  .telegram-join-section p { font-size: 1.1rem; color: var(--text-dark); max-width: 600px; margin: 0 auto 25px auto; }
  .telegram-join-button { display: inline-flex; align-items: center; gap: 10px; background-color: #2AABEE; color: white; padding: 12px 30px; border-radius: 50px; font-size: 1.1rem; font-weight: 700; transition: all 0.2s ease; }
  .telegram-join-button:hover { transform: scale(1.05); background-color: #1e96d1; } .telegram-join-button i { font-size: 1.3rem; }
  /* [NEW] Footer */
  .main-footer { padding: 20px 50px; text-align: center; background-color: #181818; color: var(--text-dark); font-size: 0.9rem; }
  .main-footer a { color: var(--text-dark); transition: color 0.2s ease; } .main-footer a:hover { color: var(--netflix-red); }
  
  @media (max-width: 992px) { .nav-links { display: none; } }
  @media (max-width: 768px) {
      body { padding-bottom: var(--nav-height); } .main-nav { padding: 10px 15px; } main { padding: 0 15px; } .logo { font-size: 24px; }
      .search-container { flex: 2; text-align: right; }
      .search-input { width: 150px; }
      /* [MODIFIED] Hero Section Height for Mobile */
      .hero-section { height: 50vh; margin: 0 -15px;}
      .hero-slide { padding: 15px; align-items: center; } .hero-content { max-width: 90%; text-align: center; } .hero-title { font-size: 2.8rem; } .hero-overview { display: none; }
      .category-section { margin: 25px 0; } .category-title { font-size: 1.2rem; }
      .category-grid, .full-page-grid { grid-template-columns: repeat(auto-fill, minmax(110px, 1fr)); gap: 15px 10px; }
      .full-page-grid-container { padding-top: 80px; } .full-page-grid-title { font-size: 1.8rem; }
      .bottom-nav { display: flex; } .ad-container { margin: 25px 0; }
      .telegram-join-section { margin: 50px -15px 0 -15px; }
      .telegram-join-section h2 { font-size: 2rem; } .telegram-join-section p { font-size: 1rem; }
      .main-footer { padding: 20px 15px; }
  }
</style>
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.2.0/css/all.min.css">
</head>
<body>
<!-- [MODIFIED] Main navigation with new structure -->
<header class="main-nav">
    <div class="nav-left">
        <div class="menu-toggle"><i class="fas fa-bars"></i></div>
    </div>
    <a href="{{ url_for('home') }}" class="logo">PmwBD</a>
    <div class="nav-right">
        <div class="search-container">
            <form method="GET" action="/" class="search-form">
                <input type="search" name="q" class="search-input" placeholder="Search..." value="{{ query|default('') }}" />
            </form>
        </div>
    </div>
</header>

<!-- [NEW] Drawer Menu -->
<div class="overlay"></div>
<nav class="drawer-menu">
    <a href="{{ url_for('home') }}">Home</a>
    <a href="{{ url_for('movies_by_category', cat_name='Latest Movie') }}">Movies</a>
    <a href="{{ url_for('movies_by_category', cat_name='Latest Series') }}">Web Series</a>
    <a href="{{ url_for('genres_page') }}">Genres</a>
    <a href="{{ url_for('contact') }}">Request/Contact</a>
    <a href="{{ url_for('disclaimer') }}">Disclaimer</a>
    <a href="{{ url_for('dmca') }}">DMCA</a>
</nav>

<main>
  {% macro render_movie_card(m) %}
    <a href="{{ url_for('movie_detail', movie_id=m._id) }}" class="movie-card">
      <div class="poster-wrapper">
        <div class="movie-poster-container">
           <img class="movie-poster" loading="lazy" src="{{ m.poster or 'https://via.placeholder.com/400x600.png?text=No+Image' }}" alt="{{ m.title }}">
           {% if m.poster_badge %}<div class="poster-badge">{{ m.poster_badge }}</div>{% endif %}
           {% if m.vote_average and m.vote_average > 0 %}<div class="rating-badge"><i class="fas fa-star"></i> {{ "%.1f"|format(m.vote_average) }}</div>{% endif %}
        </div>
        <div class="card-info-static">
          <h4 class="card-info-title">{{ m.title }}</h4>
          {% if m.release_date %}<p class="card-info-meta">{{ m.release_date.split('-')[0] }}</p>{% endif %}
        </div>
      </div>
    </a>
  {% endmacro %}

  {% if is_full_page_list %}
    <div class="full-page-grid-container">
        <h2 class="full-page-grid-title">{{ query }}</h2>
        {% if movies|length == 0 %}
            <p style="text-align:center; color: var(--text-dark); margin-top: 40px;">No content found.</p>
        {% else %}
            <div class="full-page-grid">
                {% for m in movies %}
                    {{ render_movie_card(m) }}
                {% endfor %}
            </div>
        {% endif %}
    </div>
  {% else %}
    {% if recently_added %}<div class="hero-section">{% for movie in recently_added %}<div class="hero-slide {% if loop.first %}active{% endif %}" style="background-image: url('{{ movie.poster or '' }}');"><div class="hero-content"><h1 class="hero-title">{{ movie.title }}</h1><p class="hero-overview">{{ movie.overview }}</p><div class="hero-buttons">{% if movie.watch_link and not movie.is_coming_soon %}<a href="{{ url_for('watch_movie', movie_id=movie._id) }}" class="btn btn-primary"><i class="fas fa-play"></i> Watch Now</a>{% endif %}<a href="{{ url_for('movie_detail', movie_id=movie._id) }}" class="btn btn-secondary"><i class="fas fa-info-circle"></i> More Info</a></div></div></div>{% endfor %}</div>{% endif %}

    <!-- [NEW] Category buttons -->
    <div class="category-buttons">
        <a href="{{ url_for('movies_by_category', cat_name='Hindi') }}" class="cat-btn">Hindi</a>
        <a href="{{ url_for('movies_by_category', cat_name='Bengali') }}" class="cat-btn">Bengali</a>
        <a href="{{ url_for('movies_by_category', cat_name='Latest Series') }}" class="cat-btn">Web Series</a>
        <a href="{{ url_for('movies_by_category', cat_name='English') }}" class="cat-btn">English & Hollywood</a>
    </div>

    {% macro render_grid_section(title, movies_list, endpoint, cat_name) %}
        {% if movies_list %}
        <div class="category-section">
            <div class="category-header">
                <h2 class="category-title">{{ title }}</h2>
                <a href="{{ url_for(endpoint, cat_name=cat_name) }}" class="see-all-link">See All ></a>
            </div>
            <div class="category-grid">
                {% for m in movies_list %}
                    {{ render_movie_card(m) }}
                {% endfor %}
            </div>
        </div>
        {% endif %}
    {% endmacro %}

    <!-- [MODIFIED] New category sections -->
    {{ render_grid_section('Trending Now', trending_movies, 'movies_by_category', 'Trending') }}
    {% if ad_settings.banner_ad_code %}<div class="ad-container">{{ ad_settings.banner_ad_code|safe }}</div>{% endif %}
    {{ render_grid_section('Latest Movies', latest_movies, 'movies_by_category', 'Latest Movie') }}
    {{ render_grid_section('Web Series', latest_series, 'movies_by_category', 'Latest Series') }}
    {% if ad_settings.native_banner_code %}<div class="ad-container">{{ ad_settings.native_banner_code|safe }}</div>{% endif %}
    {{ render_grid_section('Hindi', hindi_movies, 'movies_by_category', 'Hindi') }}
    {{ render_grid_section('Bengali', bengali_movies, 'movies_by_category', 'Bengali') }}
    {{ render_grid_section('English & Hollywood', english_movies, 'movies_by_category', 'English') }}
    {{ render_grid_section('Coming Soon', coming_soon_movies, 'coming_soon', '') }}
    
    <div class="telegram-join-section">
        <i class="fa-brands fa-telegram telegram-icon"></i>
        <h2>Join Our Telegram Channel</h2>
        <p>Get the latest movie updates, news, and direct download links right on your phone!</p>
        <a href="{{ main_channel_link or '#' }}" target="_blank" class="telegram-join-button"><i class="fa-brands fa-telegram"></i> Join Main Channel</a>
    </div>
  {% endif %}
</main>
<nav class="bottom-nav">
    <a href="{{ url_for('home') }}" class="nav-item {% if request.endpoint == 'home' %}active{% endif %}">
        <i class="fas fa-home"></i><span>Home</span>
    </a>
    <a href="{{ url_for('movies_by_category', cat_name='Latest Movie') }}" class="nav-item">
        <i class="fas fa-film"></i><span>Movies</span>
    </a>
    <a href="{{ url_for('movies_by_category', cat_name='Latest Series') }}" class="nav-item">
        <i class="fas fa-tv"></i><span>Series</span>
    </a>
    <a href="{{ url_for('genres_page') }}" class="nav-item {% if request.endpoint == 'genres_page' %}active{% endif %}">
        <i class="fas fa-layer-group"></i><span>Genres</span>
    </a>
    <a href="{{ url_for('contact') }}" class="nav-item {% if request.endpoint == 'contact' %}active{% endif %}">
        <i class="fas fa-envelope"></i><span>Request</span>
    </a>
</nav>
<!-- [NEW] Footer -->
<footer class="main-footer">
    <a href="https://t.me/PrimeCineZone" target="_blank" rel="noopener">&copy; ALL RIGHTS RESERVED PMWBD</a>
</footer>
<script>
    const nav = document.querySelector('.main-nav');
    window.addEventListener('scroll', () => { window.scrollY > 50 ? nav.classList.add('scrolled') : nav.classList.remove('scrolled'); });
    document.addEventListener('DOMContentLoaded', function() { 
        const slides = document.querySelectorAll('.hero-slide'); 
        if (slides.length > 1) { 
            let currentSlide = 0; 
            const showSlide = (index) => slides.forEach((s, i) => s.classList.toggle('active', i === index)); 
            setInterval(() => { currentSlide = (currentSlide + 1) % slides.length; showSlide(currentSlide); }, 5000); 
        }
        
        // [NEW] Drawer Menu Logic
        const menuToggle = document.querySelector('.menu-toggle');
        const drawerMenu = document.querySelector('.drawer-menu');
        const overlay = document.querySelector('.overlay');
        menuToggle.addEventListener('click', () => {
            drawerMenu.classList.toggle('open');
            overlay.classList.toggle('open');
        });
        overlay.addEventListener('click', () => {
            drawerMenu.classList.remove('open');
            overlay.classList.remove('open');
        });
    });
</script>
{% if ad_settings.popunder_code %}{{ ad_settings.popunder_code|safe }}{% endif %}
{% if ad_settings.social_bar_code %}{{ ad_settings.social_bar_code|safe }}{% endif %}
</body>
</html>
"""
detail_html = """
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0, user-scalable=no" />
<title>{{ movie.title if movie else "Content Not Found" }} - PmwBD</title>
<style>
  @import url('https://fonts.googleapis.com/css2?family=Bebas+Neue&family=Roboto:wght@400;500;700&display=swap');
  :root { --netflix-red: #E50914; --netflix-black: #141414; --text-light: #f5f5f5; --text-dark: #a0a0a0; }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: 'Roboto', sans-serif; background: var(--netflix-black); color: var(--text-light); }
  .detail-header { position: absolute; top: 0; left: 0; right: 0; padding: 20px 50px; z-index: 100; }
  .back-button { color: var(--text-light); font-size: 1.2rem; font-weight: 700; text-decoration: none; display: flex; align-items: center; gap: 10px; transition: color 0.3s ease; }
  .back-button:hover { color: var(--netflix-red); }
  .detail-hero { position: relative; width: 100%; display: flex; align-items: center; justify-content: center; padding: 100px 0; }
  .detail-hero-background { position: absolute; top: 0; left: 0; right: 0; bottom: 0; background-size: cover; background-position: center; filter: blur(20px) brightness(0.4); transform: scale(1.1); }
  .detail-hero::after { content: ''; position: absolute; top: 0; left: 0; right: 0; bottom: 0; background: linear-gradient(to top, rgba(20,20,20,1) 0%, rgba(20,20,20,0.6) 50%, rgba(20,20,20,1) 100%); }
  .detail-content-wrapper { position: relative; z-index: 2; display: flex; gap: 40px; max-width: 1200px; padding: 0 50px; width: 100%; }
  .detail-poster { width: 300px; height: 450px; flex-shrink: 0; border-radius: 8px; box-shadow: 0 10px 30px rgba(0,0,0,0.5); object-fit: cover; }
  .detail-info { flex-grow: 1; max-width: 65%; }
  .detail-title { font-family: 'Bebas Neue', sans-serif; font-size: 4.5rem; font-weight: 700; line-height: 1.1; margin-bottom: 20px; }
  .detail-meta { display: flex; flex-wrap: wrap; gap: 20px; margin-bottom: 25px; font-size: 1rem; color: var(--text-dark); }
  .detail-meta span { font-weight: 700; color: var(--text-light); }
  .detail-meta span i { margin-right: 5px; color: var(--text-dark); }
  .detail-overview { font-size: 1.1rem; line-height: 1.6; margin-bottom: 30px; }
  .action-btn { background-color: var(--netflix-red); color: white; padding: 15px 30px; font-size: 1.2rem; font-weight: 700; border: none; border-radius: 5px; cursor: pointer; display: inline-flex; align-items: center; gap: 10px; text-decoration: none; margin-bottom: 15px; transition: all 0.2s ease; }
  .action-btn:hover { transform: scale(1.05); background-color: #f61f29; }
  .section-title { font-size: 1.5rem; font-weight: 700; margin: 30px 0 20px 0; padding-bottom: 5px; border-bottom: 2px solid var(--netflix-red); display: inline-block; }
  .video-container { position: relative; padding-bottom: 56.25%; height: 0; overflow: hidden; max-width: 100%; background: #000; border-radius: 8px; }
  .video-container iframe { position: absolute; top: 0; left: 0; width: 100%; height: 100%; }
  
  .links-wrapper { margin-top: 10px; }
  .links-container { display: flex; gap: 40px; align-items: flex-start; }
  .link-section { flex: 1; min-width: 250px; }
  .download-button, .episode-button { display: block; width: 100%; padding: 12px 20px; color: white; text-decoration: none; border-radius: 4px; font-weight: 700; transition: background-color 0.3s ease; margin-bottom: 10px; text-align: center; }
  .download-button { background-color: var(--netflix-red); }
  .download-button:hover { background-color: #f61f29; }
  
  .episode-item { display: flex; justify-content: space-between; align-items: center; margin-bottom: 15px; padding: 15px; border-radius: 5px; background-color: #1a1a1a; border-left: 4px solid var(--netflix-red); }
  .episode-title { font-size: 1.1rem; font-weight: 500; color: #fff; }
  .ad-container { margin: 30px 0; text-align: center; }
  .related-section-container { padding: 40px 0; background-color: #181818; }
  .related-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 20px 15px; padding: 0 50px; }
  .movie-card { display: block; cursor: pointer; transition: transform 0.3s ease; }
  .poster-wrapper { position: relative; width: 100%; border-radius: 6px; overflow: hidden; background-color: #222; display: flex; flex-direction: column; }
  .movie-poster-container { position: relative; overflow: hidden; width:100%; flex-grow:1; aspect-ratio: 2 / 3; }
  .movie-poster { width: 100%; height: 100%; object-fit: cover; display: block; transition: transform 0.4s ease; }
  .poster-badge { position: absolute; top: 10px; left: 10px; background-color: var(--netflix-red); color: white; padding: 4px 8px; border-radius: 3px; font-size: 0.75rem; font-weight: 700; z-index: 4; }
  .rating-badge { position: absolute; bottom: 10px; right: 10px; background-color: transparent; color: white; padding: 5px; font-size: 0.8rem; font-weight: 700; z-index: 3; display: flex; align-items: center; gap: 5px; text-shadow: 1px 1px 3px rgba(0,0,0,0.8); }
  .rating-badge .fa-star { color: #f5c518; }
  .card-info-static { padding: 10px 8px; background-color: #1a1a1a; text-align: left; width: 100%; flex-shrink: 0; }
  .card-info-title { font-size: 0.9rem; font-weight: 500; color: var(--text-light); margin: 0 0 4px 0; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .card-info-meta { font-size: 0.75rem; color: var(--text-dark); margin: 0; }
  /* [NEW] Footer */
  .main-footer { padding: 20px 50px; text-align: center; background-color: #181818; color: var(--text-dark); font-size: 0.9rem; }
  .main-footer a { color: var(--text-dark); transition: color 0.2s ease; } .main-footer a:hover { color: var(--netflix-red); }
  
  @media (hover: hover) { .movie-card:hover { transform: scale(1.05); z-index: 10; box-shadow: 0 0 20px rgba(229, 9, 20, 0.5); } .movie-card:hover .movie-poster { transform: scale(1.1); } }
  
  @media (max-width: 992px) { 
    .detail-content-wrapper { flex-direction: column; align-items: center; text-align: center; } 
    .detail-info { max-width: 100%; } .detail-title { font-size: 3.5rem; } 
  }
  @media (max-width: 768px) { 
    .detail-header { padding: 20px; } .detail-hero { padding: 80px 20px 40px; } .detail-poster { width: 60%; max-width: 220px; height: auto; } .detail-title { font-size: 2.2rem; }
    .action-btn, .download-button { display: block; width: 100%; max-width: 320px; margin: 0 auto 10px auto; }
    .episode-item { flex-direction: column; align-items: flex-start; gap: 10px; } .episode-button { width: 100%; }
    .section-title { margin-left: 15px !important; } .related-section-container { padding: 20px 0; }
    .related-grid { grid-template-columns: repeat(auto-fill, minmax(110px, 1fr)); gap: 15px 10px; padding: 0 15px; }
    .links-container { flex-direction: column; gap: 20px; }
    .main-footer { padding: 20px 15px; }
  }
</style>
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.2.0/css/all.min.css">
</head>
<body>
{% macro render_movie_card(m) %}
  <a href="{{ url_for('movie_detail', movie_id=m._id) }}" class="movie-card">
    <div class="poster-wrapper">
      <div class="movie-poster-container">
        <img class="movie-poster" loading="lazy" src="{{ m.poster or 'https://via.placeholder.com/400x600.png?text=No+Image' }}" alt="{{ m.title }}">
        {% if m.poster_badge %}<div class="poster-badge">{{ m.poster_badge }}</div>{% endif %}
        {% if m.vote_average and m.vote_average > 0 %}<div class="rating-badge"><i class="fas fa-star"></i> {{ "%.1f"|format(m.vote_average) }}</div>{% endif %}
      </div>
      <div class="card-info-static">
        <h4 class="card-info-title">{{ m.title }}</h4>
        {% if m.release_date %}<p class="card-info-meta">{{ m.release_date.split('-')[0] }}</p>{% endif %}
      </div>
    </div>
  </a>
{% endmacro %}
<header class="detail-header"><a href="{{ url_for('home') }}" class="back-button"><i class="fas fa-arrow-left"></i> Back to Home</a></header>
{% if movie %}
<div class="detail-hero" style="min-height: auto; padding-bottom: 60px;">
  <div class="detail-hero-background" style="background-image: url('{{ movie.poster }}');"></div>
  <div class="detail-content-wrapper"><img class="detail-poster" src="{{ movie.poster or 'https://via.placeholder.com/400x600.png?text=No+Image' }}" alt="{{ movie.title }}">
    <div class="detail-info">
      <h1 class="detail-title">{{ movie.title }}</h1>
      <div class="detail-meta">
        {% if movie.release_date %}<span>{{ movie.release_date.split('-')[0] }}</span>{% endif %}
        {% if movie.vote_average %}<span><i class="fas fa-star" style="color:#f5c518;"></i> {{ "%.1f"|format(movie.vote_average) }}</span>{% endif %}
        {% if movie.languages %}<span><i class="fas fa-language"></i> {{ movie.languages | join(' • ') }}</span>{% endif %}
        {% if movie.genres %}<span>{{ movie.genres | join(' • ') }}</span>{% endif %}
      </div>
      <p class="detail-overview">{{ movie.overview }}</p>
      {% if movie.type == 'movie' and movie.watch_link %}<a href="{{ url_for('watch_movie', movie_id=movie._id) }}" class="action-btn"><i class="fas fa-play"></i> Watch Now</a>{% endif %}
      
      {% if ad_settings.banner_ad_code %}<div class="ad-container">{{ ad_settings.banner_ad_code|safe }}</div>{% endif %}
      
      {% if trailer_embed_key %}
      <div class="trailer-section">
          <h3 class="section-title">Watch Trailer</h3>
          <div class="video-container">
              <iframe src="https://www.youtube.com/embed/{{ trailer_embed_key }}" frameborder="0" allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture" allowfullscreen></iframe>
          </div>
      </div>
      {% endif %}

      <div style="margin: 20px 0;"><a href="{{ url_for('contact', report_id=movie._id, title=movie.title) }}" class="action-btn" style="background-color:#5a5a5a; text-align:center; width: 100%;"><i class="fas fa-flag"></i> Report a Problem</a></div>
      
      {% if movie.is_coming_soon %}<h3 class="section-title">Coming Soon</h3>
      {% elif movie.type == 'movie' %}
        <div class="links-wrapper">
            <div class="links-container">
                <!-- [REVERTED] Streaming Links Column -->
                {% if movie.streaming_links %}
                <div class="link-section">
                    <h3 class="section-title" style="margin-top:0;">Streaming Links</h3>
                    {% for link_item in movie.streaming_links %}
                        <a class="download-button" href="{{ link_item.url }}" target="_blank" rel="noopener" style="background-color: #007bff;">
                            <i class="fas fa-play-circle"></i> Stream and Watch online in {{ link_item.name }}
                        </a>
                    {% endfor %}
                </div>
                {% endif %}
                
                <!-- Download Links Column -->
                {% if movie.links %}
                <div class="link-section">
                    <h3 class="section-title" style="margin-top:0;">Download Links</h3>
                    {% for link_item in movie.links %}
                        <a class="download-button" href="{{ link_item.url }}" target="_blank" rel="noopener">
                            <i class="fas fa-download"></i> Download the file in {{ link_item.quality }}
                        </a>
                    {% endfor %}
                </div>
                {% endif %}
            </div>

            {% if movie.files %}
            <div class="link-section" style="margin-top: 30px;">
                <h3 class="section-title">Get from Telegram</h3>
                {% for file in movie.files | sort(attribute='quality') %}
                    <a href="https://t.me/{{ bot_username }}?start={{ movie._id }}_{{ file.quality }}" class="action-btn" style="background-color: #2AABEE; display: block; text-align:center; margin-top:10px; margin-bottom: 0;">
                        <i class="fa-brands fa-telegram"></i> Get {{ file.quality }}
                    </a>
                {% endfor %}
            </div>
            {% endif %}
        </div>
      {% elif movie.type == 'series' %}
        <div class="episode-section">
          <h3 class="section-title">Episodes & Seasons</h3>
          {% if movie.season_packs %}
            {% for pack in movie.season_packs | sort(attribute='quality') | sort(attribute='season') %}
              <div class="episode-item" style="background-color: #3e1a1a;">
                <span class="episode-title">Complete Season {{ pack.season }} Pack ({{ pack.quality }})</span>
                <a href="https://t.me/{{ bot_username }}?start={{ movie._id }}_S{{ pack.season }}_{{ pack.quality }}" class="episode-button" style="background-color: var(--netflix-red);"><i class="fas fa-box-open"></i> Get Season Pack</a>
              </div>
            {% endfor %}
          {% endif %}
          {% if movie.episodes %}
            {% for ep in movie.episodes | sort(attribute='episode_number') | sort(attribute='season') %}
              <div class="episode-item">
                <span class="episode-title">Season {{ ep.season }} - Episode {{ ep.episode_number }}</span>
                <a href="https://t.me/{{ bot_username }}?start={{ movie._id }}_{{ ep.season }}_{{ ep.episode_number }}" class="episode-button" style="background-color: #2AABEE;"><i class="fa-brands fa-telegram"></i> Get Episode</a>
              </div>
            {% endfor %}
          {% endif %}
          {% if not movie.episodes and not movie.season_packs %}
             <p>No episodes or season packs available yet.</p>
          {% endif %}
        </div>
      {% endif %}
    </div>
  </div>
</div>
{% if related_movies %}<div class="related-section-container"><h3 class="section-title" style="margin-left: 50px; color: white;">You Might Also Like</h3><div class="related-grid">{% for m in related_movies %}{{ render_movie_card(m) }}{% endfor %}</div></div>{% endif %}
{% else %}<div style="display:flex; justify-content:center; align-items:center; height:100vh;"><h2>Content not found.</h2></div>{% endif %}

<!-- [NEW] Footer -->
<footer class="main-footer">
    <a href="https://t.me/PrimeCineZone" target="_blank" rel="noopener">&copy; ALL RIGHTS RESERVED PMWBD</a>
</footer>
{% if ad_settings.popunder_code %}{{ ad_settings.popunder_code|safe }}{% endif %}
{% if ad_settings.social_bar_code %}{{ ad_settings.social_bar_code|safe }}{% endif %}
</body>
</html>
"""
            
genres_html = """
<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8" /><meta name="viewport" content="width=device-width, initial-scale=1.0, user-scalable=no" /><title>{{ title }} - MovieZone</title>
<style>
  @import url('https://fonts.googleapis.com/css2?family=Bebas+Neue&family=Roboto:wght@400;500;700&display=swap');
  :root { --netflix-red: #E50914; --netflix-black: #141414; --text-light: #f5f5f5; }
  * { box-sizing: border-box; margin: 0; padding: 0; } body { font-family: 'Roboto', sans-serif; background-color: var(--netflix-black); color: var(--text-light); } a { text-decoration: none; color: inherit; }
  .main-container { padding: 100px 50px 50px; } .page-title { font-family: 'Bebas Neue', sans-serif; font-size: 3rem; color: var(--netflix-red); margin-bottom: 30px; }
  .back-button { color: var(--text-light); font-size: 1rem; margin-bottom: 20px; display: inline-block; } .back-button:hover { color: var(--netflix-red); }
  .genre-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 20px; }
  .genre-card { background: linear-gradient(45deg, #2c2c2c, #1a1a1a); border-radius: 8px; padding: 30px 20px; text-align: center; font-size: 1.4rem; font-weight: 700; transition: all 0.3s ease; border: 1px solid #444; }
  .genre-card:hover { transform: translateY(-5px) scale(1.03); background: linear-gradient(45deg, var(--netflix-red), #b00710); border-color: var(--netflix-red); }
  /* [NEW] Footer */
  .main-footer { padding: 20px 50px; text-align: center; background-color: var(--netflix-black); border-top: 1px solid #222; color: #a0a0a0; font-size: 0.9rem; }
  .main-footer a { color: #a0a0a0; transition: color 0.2s ease; } .main-footer a:hover { color: var(--netflix-red); }
  @media (max-width: 768px) { 
      .main-container { padding: 80px 15px 30px; } .page-title { font-size: 2.2rem; } .genre-grid { grid-template-columns: repeat(2, 1fr); gap: 15px; } .genre-card { font-size: 1.1rem; padding: 25px 15px; } 
      .main-footer { padding: 20px 15px; }
  }
</style><link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.2.0/css/all.min.css"></head>
<body>
<div class="main-container"><a href="{{ url_for('home') }}" class="back-button"><i class="fas fa-arrow-left"></i> Back to Home</a><h1 class="page-title">{{ title }}</h1>
<div class="genre-grid">{% for genre in genres %}<a href="{{ url_for('movies_by_genre', genre_name=genre) }}" class="genre-card"><span>{{ genre }}</span></a>{% endfor %}</div></div>
<!-- [NEW] Footer -->
<footer class="main-footer">
    <a href="https://t.me/PrimeCineZone" target="_blank" rel="noopener">&copy; ALL RIGHTS RESERVED PMWBD</a>
</footer>
{% if ad_settings.popunder_code %}{{ ad_settings.popunder_code|safe }}{% endif %}
{% if ad_settings.social_bar_code %}{{ ad_settings.social_bar_code|safe }}{% endif %}
</body></html>
"""
watch_html = """
<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"><title>Watching: {{ title }}</title>
<style> 
    body, html { margin: 0; padding: 0; height: 100%; overflow: hidden; background-color: #000; } 
    .player-container { width: 100%; height: 100%; display: flex; flex-direction: column; } 
    .player-container iframe { width: 100%; height: 100%; border: 0; flex-grow: 1; }
    /* [NEW] Footer */
    .main-footer { padding: 10px; text-align: center; background-color: #000; color: #a0a0a0; font-size: 0.8rem; flex-shrink: 0; }
    .main-footer a { color: #a0a0a0; text-decoration: none; transition: color 0.2s ease; } .main-footer a:hover { color: #E50914; }
</style></head>
<body>
<div class="player-container">
    <iframe src="{{ watch_link }}" allowfullscreen allowtransparency allow="autoplay" scrolling="no" frameborder="0"></iframe>
    <!-- [NEW] Footer -->
    <footer class="main-footer">
        <a href="https://t.me/PrimeCineZone" target="_blank" rel="noopener">&copy; ALL RIGHTS RESERVED PMWBD</a>
    </footer>
</div>
{% if ad_settings.popunder_code %}{{ ad_settings.popunder_code|safe }}{% endif %}
{% if ad_settings.social_bar_code %}{{ ad_settings.social_bar_code|safe }}{% endif %}
</body></html>
"""
admin_html = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Admin Panel - MovieZone</title>
    <link href="https://fonts.googleapis.com/css2?family=Bebas+Neue&family=Roboto:wght@400;700&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.2.0/css/all.min.css">
    <style>
        :root { --netflix-red: #E50914; --netflix-red-dark: #B20710; --netflix-black: #141414; --dark-gray: #222; --light-gray: #333; --text-light: #f5f5f5; --text-medium: #999; }
        body { font-family: 'Roboto', sans-serif; background: var(--netflix-black); color: var(--text-light); margin: 0; padding: 20px; }
        .admin-container { max-width: 1000px; margin: 20px auto; }
        .admin-header { display: flex; align-items: center; justify-content: space-between; border-bottom: 2px solid var(--netflix-red); padding-bottom: 10px; margin-bottom: 30px; }
        .admin-header h1 { font-family: 'Bebas Neue', sans-serif; font-size: 3rem; color: var(--netflix-red); margin: 0; }
        .admin-header a { color: var(--text-medium); text-decoration: none; font-weight: bold; } .admin-header a:hover { color: var(--text-light); }
        h2 { font-family: 'Bebas Neue', sans-serif; color: var(--netflix-red); font-size: 2.2rem; margin-top: 40px; margin-bottom: 20px; border-left: 4px solid var(--netflix-red); padding-left: 15px; }
        form { background: var(--dark-gray); padding: 25px; border-radius: 8px; border: 1px solid var(--light-gray); }
        fieldset { border: 1px solid var(--light-gray); border-radius: 5px; padding: 20px; margin-bottom: 20px; }
        legend { font-weight: bold; color: var(--netflix-red); padding: 0 10px; font-size: 1.2rem; }
        .form-group { margin-bottom: 15px; }
        .form-group label { display: block; margin-bottom: 8px; font-weight: bold; color: var(--text-medium); }
        input[type="text"], input[type="url"], input[type="search"], textarea, select, input[type="number"], input[type="email"] {
            width: 100%; padding: 12px; border-radius: 4px; border: 1px solid var(--light-gray); font-size: 1rem; background: var(--light-gray); color: var(--text-light); box-sizing: border-box; transition: border-color 0.3s;
        }
        input:focus, textarea:focus, select:focus { border-color: var(--netflix-red); outline: none; }
        input[type="checkbox"] { width: auto; margin-right: 10px; transform: scale(1.2); }
        textarea { resize: vertical; min-height: 100px; }
        .btn { display: inline-block; text-decoration: none; color: white; font-weight: 700; cursor: pointer; border: none; padding: 12px 25px; border-radius: 4px; font-size: 1rem; transition: background 0.3s ease; }
        .btn-primary { background: var(--netflix-red); } .btn-primary:hover { background: var(--netflix-red-dark); }
        .btn-secondary { background: #555; } .btn-secondary:hover { background: #444; }
        .btn-danger { background: #dc3545; } .btn-danger:hover { background: #c82333; }
        .btn-info { background: #17a2b8; } .btn-info:hover { background: #138496; }
        .btn-edit { background: #007bff; } .btn-edit:hover { background: #0069d9; }
        .table-container { display: block; overflow-x: auto; white-space: nowrap; border: 1px solid var(--light-gray); border-radius: 5px; }
        table { width: 100%; border-collapse: collapse; }
        th, td { padding: 12px 15px; text-align: left; border-bottom: 1px solid var(--light-gray); }
        th { background: #252525; font-weight: bold; } td { background: var(--dark-gray); vertical-align: middle; }
        .action-buttons { display: flex; gap: 10px; }
        .action-buttons a, .action-buttons button { padding: 6px 12px; border-radius: 4px; font-size: 0.9rem; }
        .dynamic-item { border: 1px solid var(--light-gray); padding: 15px; margin-bottom: 15px; border-radius: 5px; position: relative; }
        .dynamic-item .btn-danger { position: absolute; top: 10px; right: 10px; padding: 4px 8px; font-size: 0.8rem; }
        hr.section-divider { border: 0; height: 1px; background-color: var(--light-gray); margin: 50px 0; }
        hr { border: 0; height: 1px; background-color: var(--light-gray); margin: 20px 0; }
        .danger-zone { border: 2px solid var(--netflix-red); padding: 20px; border-radius: 8px; margin-top: 30px; text-align: center; background: rgba(229, 9, 20, 0.1); }
        .tmdb-fetcher { display: flex; gap: 10px; align-items: center; margin-bottom: 20px; }
        .tmdb-fetcher input { flex-grow: 1; }
        .checkbox-group { display: flex; flex-wrap: wrap; gap: 15px; }
        .checkbox-group label { display: inline-flex; align-items: center; font-weight: normal; color: var(--text-light); }
    </style>
</head>
<body>
<div class="admin-container">
    <header class="admin-header">
        <h1>Admin Panel</h1>
        <a href="{{ url_for('home') }}" target="_blank">View Site <i class="fa-solid fa-arrow-up-right-from-square"></i></a>
    </header>

    <h2><i class="fas fa-ad"></i> Ad Management</h2>
    <form action="{{ url_for('save_ads') }}" method="post">
        <div class="form-group"><label>Pop-Under / OnClick Ad Code</label><textarea name="popunder_code" rows="3">{{ ad_settings.popunder_code or '' }}</textarea></div>
        <div class="form-group"><label>Social Bar / Sticky Ad Code</label><textarea name="social_bar_code" rows="3">{{ ad_settings.social_bar_code or '' }}</textarea></div>
        <div class="form-group"><label>Banner Ad Code</label><textarea name="banner_ad_code" rows="3">{{ ad_settings.banner_ad_code or '' }}</textarea></div>
        <div class="form-group"><label>Native Banner Ad Code</label><textarea name="native_banner_code" rows="3">{{ ad_settings.native_banner_code or '' }}</textarea></div>
        <button type="submit" class="btn btn-primary">Save Ad Codes</button>
    </form>

    <hr class="section-divider">
    
    <h2><i class="fas fa-plus-circle"></i> Add New Content</h2>
    
    <fieldset>
        <legend>Automatic Method</legend>
        <div class="form-group">
            <label for="tmdb_url_input">Fetch from TMDB (Paste Movie/Series URL)</label>
            <div class="tmdb-fetcher">
                <input type="url" id="tmdb_url_input" placeholder="https://www.themoviedb.org/movie/xxxxx-movie-title">
                <button type="button" id="tmdb_find_btn" class="btn btn-primary" onclick="fetchFromTmdb()">Find</button>
            </div>
        </div>
    </fieldset>

    <form method="post" action="{{ url_for('admin') }}">
        <fieldset>
            <legend>Manual Method</legend>
            <div class="form-group"><label for="title">Title (Required):</label><input type="text" name="title" id="title" required /></div>
            <div class="form-group"><label for="poster">Poster URL:</label><input type="url" name="poster" id="poster" /></div>
            <div class="form-group"><label for="overview">Overview:</label><textarea name="overview" id="overview"></textarea></div>
            <div class="form-group"><label for="genres">Genres (comma separated):</label><input type="text" name="genres" id="genres" /></div>
            <div class="form-group"><label for="trailer_link">Trailer Link (YouTube):</label><input type="url" name="trailer_link" id="trailer_link" placeholder="https://www.youtube.com/watch?v=..."/></div>
            <div class="form-group"><label for="poster_badge">Poster Badge (Optional):</label><input type="text" name="poster_badge" id="poster_badge" placeholder="e.g., WEB-DL, Dual Audio" /></div>
            <div class="form-group"><label for="content_type">Content Type:</label><select name="content_type" id="content_type" onchange="toggleFields()"><option value="movie">Movie</option><option value="series">TV/Web Series</option></select></div>
        </fieldset>
        
        <fieldset><legend>Categories</legend>
            <div class="form-group checkbox-group">
                {% for cat in categories %}
                <label><input type="checkbox" name="categories" value="{{ cat }}"> {{ cat }}</label>
                {% endfor %}
                <label><input type="checkbox" name="is_coming_soon" value="true"> Is Coming Soon?</label>
            </div>
        </fieldset>
        
        <div id="movie_fields">
            <fieldset><legend>Movie Links</legend>
                <div class="form-group"><label>Watch Link (Main Embed URL):</label><input type="url" name="watch_link" placeholder="https://..."/></div><hr>
                
                <!-- [REVERTED] Streaming Links -->
                <p><b>Streaming Links (Optional)</b></p>
                <div class="form-group"><label>Streaming Link 1 (Server 1):</label><input type="url" name="streaming_link_1" /></div>
                <div class="form-group"><label>Streaming Link 2 (Server 2):</label><input type="url" name="streaming_link_2" /></div>
                <div class="form-group"><label>Streaming Link 3 (Server 3):</label><input type="url" name="streaming_link_3" /></div><hr>

                <p><b>Direct Download Links</b></p>
                <div class="form-group"><label>480p Link:</label><input type="url" name="link_480p" /></div>
                <div class="form-group"><label>720p Link:</label><input type="url" name="link_720p" /></div>
                <div class="form-group"><label>1080p Link:</label><input type="url" name="link_1080p" /></div><hr>
                
                <p><b>Get from Telegram</b></p>
                <div id="telegram_files_container"></div><button type="button" onclick="addTelegramFileField()" class="btn btn-secondary"><i class="fas fa-plus"></i> Add Telegram File</button>
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
    
    <hr class="section-divider">

    <h2><i class="fas fa-tasks"></i> Manage Content</h2>
    <form method="GET" action="{{ url_for('admin') }}" style="display: flex; gap: 10px; align-items: center; background:none; padding:0; border:none; margin-bottom:20px;">
        <input type="search" name="search" placeholder="Search by title..." value="{{ search_query or '' }}" style="flex-grow: 1;">
        <button type="submit" class="btn btn-primary">Search</button>
        {% if search_query %}<a href="{{ url_for('admin') }}" class="btn btn-secondary">Clear</a>{% endif %}
    </form>
    <div class="table-container">
    <table><thead><tr><th>Title</th><th>Type</th><th>Categories</th><th>Actions</th></tr></thead><tbody>
    {% for movie in content_list %}
    <tr>
        <td>{{ movie.title }}</td>
        <td>{{ movie.type | title }}</td>
        <td>{{ (movie.categories or []) | join(', ') }}</td>
        <td class="action-buttons">
            <a href="{{ url_for('edit_movie', movie_id=movie._id) }}" class="btn btn-edit"><i class="fas fa-edit"></i> Edit</a>
            <a href="{{ url_for('send_manual_notification', movie_id=movie._id) }}" class="btn btn-info" onclick="return confirm('Send a channel notification for \\'{{ movie.title }}\\'?')"><i class="fas fa-paper-plane"></i> Notify</a>
            <button class="btn btn-danger" onclick="confirmDelete('{{ movie._id }}', '{{ movie.title }}')"><i class="fas fa-trash"></i> Delete</button>
        </td>
    </tr>
    {% else %}
    <tr><td colspan="4" style="text-align: center; padding: 20px;">No content found.</td></tr>
    {% endfor %}
    </tbody></table>
    </div>

    <div class="danger-zone">
      <h3><i class="fas fa-exclamation-triangle"></i> DANGER ZONE</h3>
      <p>This will permanently delete all movies and series. This action cannot be undone.</p>
      <a href="{{ url_for('delete_all_movies') }}" class="btn btn-danger" onclick="return confirm('ARE YOU ABSOLUTELY SURE? This will delete ALL content permanently.');">Delete All Content</a>
    </div>

    <hr class="section-divider">

    <h2><i class="fas fa-comment-alt"></i> User Feedback / Reports</h2>
    {% if feedback_list %}
    <div class="table-container">
    <table><thead><tr><th>Date</th><th>Type</th><th>Title</th><th>Message</th><th>Email</th><th>Action</th></tr></thead><tbody>
    {% for item in feedback_list %}
    <tr>
        <td style="min-width: 150px;">{{ item.timestamp.strftime('%Y-%m-%d %H:%M') }}</td>
        <td>{{ item.type }}</td>
        <td>{{ item.content_title }}</td>
        <td style="white-space: pre-wrap; min-width: 300px;">{{ item.message }}</td>
        <td>{{ item.email or 'N/A' }}</td>
        <td><a href="{{ url_for('delete_feedback', feedback_id=item._id) }}" class="btn btn-danger" onclick="return confirm('Delete this feedback?');"><i class="fas fa-trash"></i></a></td>
    </tr>
    {% endfor %}
    </tbody></table>
    </div>
    {% else %}
    <p>No new feedback or reports.</p>
    {% endif %}

</div>
<script>
    function confirmDelete(id, title) { if (confirm('Delete "' + title + '"? This is permanent.')) window.location.href = '/delete_movie/' + id; }
    function toggleFields() { var isSeries = document.getElementById('content_type').value === 'series'; document.getElementById('episode_fields').style.display = isSeries ? 'block' : 'none'; document.getElementById('movie_fields').style.display = isSeries ? 'none' : 'block'; }
    function addTelegramFileField() { const c = document.getElementById('telegram_files_container'); const d = document.createElement('div'); d.className = 'dynamic-item'; d.innerHTML = `<button type="button" onclick="this.parentElement.remove()" class="btn btn-danger"><i class="fas fa-times"></i></button><div class="form-group"><label>Quality (e.g., 720p):</label><input type="text" name="telegram_quality[]" required /></div><div class="form-group"><label>Message ID:</label><input type="number" name="telegram_message_id[]" required /></div>`; c.appendChild(d); }
    function addEpisodeField() { const c = document.getElementById('episodes_container'); const d = document.createElement('div'); d.className = 'dynamic-item'; d.innerHTML = `<button type="button" onclick="this.parentElement.remove()" class="btn btn-danger">Remove Episode</button><div class="form-group"><label>Season Number:</label><input type="number" name="episode_season[]" value="1" required /></div><div class="form-group"><label>Episode Number:</label><input type="number" name="episode_number[]" required /></div><div class="form-group"><label>Episode Title:</label><input type="text" name="episode_title[]" /></div><hr><p><b>Provide ONE of the following:</b></p><div class="form-group"><label>Telegram Message ID:</label><input type="number" name="episode_message_id[]" /></div><p><b>OR</b> Watch Link:</p><div class="form-group"><label>Watch Link (Embed):</label><input type="url" name="episode_watch_link[]" /></div>`; c.appendChild(d); }
    
    async function fetchFromTmdb() {
        const url = document.getElementById('tmdb_url_input').value;
        if (!url) { alert('Please enter a TMDb URL.'); return; }
        const findButton = document.getElementById('tmdb_find_btn');
        findButton.disabled = true;
        findButton.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Finding...';

        try {
            const response = await fetch(`/admin/api/fetch_tmdb?url=${encodeURIComponent(url)}`);
            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(errorData.error || 'Failed to fetch data. Check the URL and try again.');
            }
            const data = await response.json();

            document.querySelector('form [name="title"]').value = data.title || '';
            document.querySelector('form [name="overview"]').value = data.overview || '';
            document.querySelector('form [name="poster"]').value = data.poster || '';
            document.querySelector('form [name="genres"]').value = data.genres ? data.genres.join(', ') : '';
            
            const contentTypeSelect = document.querySelector('form [name="content_type"]');
            contentTypeSelect.value = data.type === 'series' ? 'series' : 'movie';
            toggleFields();
            
            if (data.trailer_link) {
                document.querySelector('form [name="trailer_link"]').value = data.trailer_link;
            }

        } catch (error) {
            alert(error.message);
        } finally {
            findButton.disabled = false;
            findButton.innerHTML = 'Find';
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
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Edit Content - MovieZone</title>
    <link href="https://fonts.googleapis.com/css2?family=Bebas+Neue&family=Roboto:wght@400;700&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.2.0/css/all.min.css">
    <style>
        :root { --netflix-red: #E50914; --netflix-red-dark: #B20710; --netflix-black: #141414; --dark-gray: #222; --light-gray: #333; --text-light: #f5f5f5; --text-medium: #999; }
        body { font-family: 'Roboto', sans-serif; background: var(--netflix-black); color: var(--text-light); padding: 20px; }
        .admin-container { max-width: 800px; margin: 20px auto; }
        .back-link { display: inline-block; margin-bottom: 20px; color: var(--text-medium); text-decoration: none; font-weight: bold; } .back-link:hover { color: var(--text-light); }
        h2 { font-family: 'Bebas Neue', sans-serif; color: var(--netflix-red); font-size: 2.5rem; margin-bottom: 20px; }
        form { background: var(--dark-gray); padding: 25px; border-radius: 8px; border: 1px solid var(--light-gray); }
        fieldset { border: 1px solid var(--light-gray); border-radius: 5px; padding: 20px; margin-bottom: 20px; }
        legend { font-weight: bold; color: var(--netflix-red); padding: 0 10px; font-size: 1.2rem; }
        .form-group { margin-bottom: 15px; }
        .form-group label { display: block; margin-bottom: 8px; font-weight: bold; color: var(--text-medium); }
        input, textarea, select { width: 100%; padding: 12px; border-radius: 4px; border: 1px solid var(--light-gray); font-size: 1rem; background: var(--light-gray); color: var(--text-light); box-sizing: border-box; }
        input:focus, textarea:focus, select:focus { border-color: var(--netflix-red); outline: none; }
        input[type="checkbox"] { width: auto; margin-right: 10px; transform: scale(1.2); }
        textarea { resize: vertical; min-height: 100px; }
        .btn { display: inline-block; text-decoration: none; color: white; font-weight: 700; cursor: pointer; border: none; padding: 12px 25px; border-radius: 4px; font-size: 1rem; transition: background 0.3s ease; }
        .btn-primary { background: var(--netflix-red); } .btn-primary:hover { background: var(--netflix-red-dark); }
        .btn-secondary { background: #555; } .btn-secondary:hover { background: #444; }
        .btn-danger { background: #dc3545; } .btn-danger:hover { background: #c82333; }
        .dynamic-item { border: 1px solid var(--light-gray); padding: 15px; margin-bottom: 15px; border-radius: 5px; position: relative; }
        .dynamic-item .btn-danger { position: absolute; top: 10px; right: 10px; padding: 4px 8px; font-size: 0.8rem; }
        hr { border: 0; height: 1px; background-color: var(--light-gray); margin: 20px 0; }
        .checkbox-group { display: flex; flex-wrap: wrap; gap: 15px; }
        .checkbox-group label { display: inline-flex; align-items: center; font-weight: normal; color: var(--text-light); }
    </style>
</head>
<body>
<div class="admin-container">
  <a href="{{ url_for('admin') }}" class="back-link"><i class="fas fa-arrow-left"></i> Back to Admin Panel</a>
  <h2>Edit: {{ movie.title }}</h2>
  <form method="post">
    <fieldset>
        <legend>Core Details</legend>
        <div class="form-group"><label>Title:</label><input type="text" name="title" value="{{ movie.title }}" required /></div>
        <div class="form-group"><label>Poster URL:</label><input type="url" name="poster" value="{{ movie.poster or '' }}" /></div>
        <div class="form-group"><label>Overview:</label><textarea name="overview">{{ movie.overview or '' }}</textarea></div>
        <div class="form-group"><label>Genres (comma separated):</label><input type="text" name="genres" value="{{ movie.genres|join(', ') if movie.genres else '' }}" /></div>
        <div class="form-group"><label>Languages (comma separated):</label><input type="text" name="languages" value="{{ movie.languages|join(', ') if movie.languages else '' }}" placeholder="e.g. Hindi, English, Bangla" /></div>
        <div class="form-group"><label>Trailer Link (YouTube):</label><input type="url" name="trailer_link" value="{{ movie.trailer_link or '' }}" /></div>
        <div class="form-group"><label>Poster Badge:</label><input type="text" name="poster_badge" value="{{ movie.poster_badge or '' }}" /></div>
        <div class="form-group"><label>Content Type:</label><select name="content_type" id="content_type" onchange="toggleFields()"><option value="movie" {% if movie.type == 'movie' %}selected{% endif %}>Movie</option><option value="series" {% if movie.type == 'series' %}selected{% endif %}>TV/Web Series</option></select></div>
    </fieldset>

    <fieldset><legend>Categories</legend>
        <div class="form-group checkbox-group">
            {% set movie_cats = movie.categories or [] %}
            {% for cat in categories %}
            <label><input type="checkbox" name="categories" value="{{ cat }}" {% if cat in movie_cats %}checked{% endif %}> {{ cat }}</label>
            {% endfor %}
            <label><input type="checkbox" name="is_coming_soon" value="true" {% if movie.is_coming_soon %}checked{% endif %}> Is Coming Soon?</label>
        </div>
    </fieldset>
    
    <div id="movie_fields">
        <fieldset><legend>Movie Links</legend>
            <div class="form-group"><label>Watch Link (Main Embed):</label><input type="url" name="watch_link" value="{{ movie.watch_link or '' }}" /></div><hr>
            
            <!-- [REVERTED] Streaming Links -->
            {% set stream_link_1 = (movie.streaming_links | selectattr('name', 'equalto', '480p') | map(attribute='url') | first) or '' %}
            {% set stream_link_2 = (movie.streaming_links | selectattr('name', 'equalto', '720p') | map(attribute='url') | first) or '' %}
            {% set stream_link_3 = (movie.streaming_links | selectattr('name', 'equalto', '1080p') | map(attribute='url') | first) or '' %}
            <p><b>Streaming Links (Optional)</b></p>
            <div class="form-group"><label>Streaming Link 1 (480p):</label><input type="url" name="streaming_link_1" value="{{ stream_link_1 }}" /></div>
            <div class="form-group"><label>Streaming Link 2 (720p):</label><input type="url" name="streaming_link_2" value="{{ stream_link_2 }}" /></div>
            <div class="form-group"><label>Streaming Link 3 (1080p):</label><input type="url" name="streaming_link_3" value="{{ stream_link_3 }}" /></div><hr>
            
            <p><b>Download Links (Manual)</b></p>
            <div class="form-group"><label>480p Link:</label><input type="url" name="link_480p" value="{% for l in movie.links %}{% if l.quality == '480p' %}{{ l.url }}{% endif %}{% endfor %}" /></div>
            <div class="form-group"><label>720p Link:</label><input type="url" name="link_720p" value="{% for l in movie.links %}{% if l.quality == '720p' %}{{ l.url }}{% endif %}{% endfor %}" /></div>
            <div class="form-group"><label>1080p Link:</label><input type="url" name="link_1080p" value="{% for l in movie.links %}{% if l.quality == '1080p' %}{{ l.url }}{% endif %}{% endfor %}" /></div><hr><p><b>OR</b> Get from Telegram</p>
            <div id="telegram_files_container">
                {% if movie.type == 'movie' and movie.files %}{% for file in movie.files %}
                <div class="dynamic-item">
                    <button type="button" onclick="this.parentElement.remove()" class="btn btn-danger"><i class="fas fa-times"></i></button>
                    <div class="form-group"><label>Quality:</label><input type="text" name="telegram_quality[]" value="{{ file.quality }}" required /></div>
                    <div class="form-group"><label>Message ID:</label><input type="number" name="telegram_message_id[]" value="{{ file.message_id }}" required /></div>
                </div>
                {% endfor %}{% endif %}
            </div><button type="button" onclick="addTelegramFileField()" class="btn btn-secondary"><i class="fas fa-plus"></i> Add Telegram File</button>
        </fieldset>
    </div>

    <div id="episode_fields" style="display: none;">
      <fieldset><legend>Season Packs</legend>
        <div id="season_packs_container">
          {% if movie.type == 'series' and movie.season_packs %}{% for pack in movie.season_packs | sort(attribute='season') %}
          <div class="dynamic-item">
            <button type="button" onclick="this.parentElement.remove()" class="btn btn-danger">Remove Pack</button>
            <div class="form-group"><label>Season Number:</label><input type="number" name="pack_season[]" value="{{ pack.season }}" required /></div>
            <div class="form-group"><label>Quality (e.g., 720p):</label><input type="text" name="pack_quality[]" value="{{ pack.quality }}" required /></div>
            <div class="form-group"><label>Telegram Message ID:</label><input type="number" name="pack_message_id[]" value="{{ pack.message_id }}" required /></div>
          </div>
          {% endfor %}{% endif %}
        </div>
        <button type="button" onclick="addSeasonPackField()" class="btn btn-secondary"><i class="fas fa-plus"></i> Add Season Pack</button>
      </fieldset>
      
      <fieldset><legend>Individual Episodes</legend>
        <div id="episodes_container">
        {% if movie.type == 'series' and movie.episodes %}{% for ep in movie.episodes | sort(attribute='episode_number') | sort(attribute='season') %}<div class="dynamic-item">
            <button type="button" onclick="this.parentElement.remove()" class="btn btn-danger">Remove Episode</button>
            <div class="form-group"><label>Season Number:</label><input type="number" name="episode_season[]" value="{{ ep.season or 1 }}" required /></div>
            <div class="form-group"><label>Episode Number:</label><input type="number" name="episode_number[]" value="{{ ep.episode_number }}" required /></div>
            <div class="form-group"><label>Episode Title:</label><input type="text" name="episode_title[]" value="{{ ep.title or '' }}" /></div>
            <hr><p><b>Provide ONE of the following:</b></p>
            <div class="form-group"><label>Telegram Message ID:</label><input type="number" name="episode_message_id[]" value="{{ ep.message_id or '' }}" /></div>
            <p><b>OR</b> Watch Link:</p>
            <div class="form-group"><label>Watch Link (Embed):</label><input type="url" name="episode_watch_link[]" value="{{ ep.watch_link or '' }}" /></div>
        </div>{% endfor %}{% endif %}</div><button type="button" onclick="addEpisodeField()" class="btn btn-secondary"><i class="fas fa-plus"></i> Add Episode</button>
      </fieldset>
    </div>

    <button type="submit" class="btn btn-primary"><i class="fas fa-save"></i> Update Content</button>
  </form>
</div>
<script>
    function toggleFields() { var isSeries = document.getElementById('content_type').value === 'series'; document.getElementById('episode_fields').style.display = isSeries ? 'block' : 'none'; document.getElementById('movie_fields').style.display = isSeries ? 'none' : 'block'; }
    function addTelegramFileField() { const c = document.getElementById('telegram_files_container'); const d = document.createElement('div'); d.className = 'dynamic-item'; d.innerHTML = `<button type="button" onclick="this.parentElement.remove()" class="btn btn-danger"><i class="fas fa-times"></i></button><div class="form-group"><label>Quality (e.g., 720p):</label><input type="text" name="telegram_quality[]" required /></div><div class="form-group"><label>Message ID:</label><input type="number" name="telegram_message_id[]" required /></div>`; c.appendChild(d); }
    function addEpisodeField() { const c = document.getElementById('episodes_container'); const d = document.createElement('div'); d.className = 'dynamic-item'; d.innerHTML = `<button type="button" onclick="this.parentElement.remove()" class="btn btn-danger">Remove</button><div class="form-group"><label>Season Number:</label><input type="number" name="episode_season[]" value="1" required /></div><div class="form-group"><label>Episode Number:</label><input type="number" name="episode_number[]" required /></div><div class="form-group"><label>Episode Title:</label><input type="text" name="episode_title[]" /></div><hr><p><b>Provide ONE of the following:</b></p><div class="form-group"><label>Telegram Message ID:</label><input type="number" name="episode_message_id[]" /></div><p><b>OR</b> Watch Link:</p><div class="form-group"><label>Watch Link (Embed):</label><input type="url" name="episode_watch_link[]" /></div>`; c.appendChild(d); }
    function addSeasonPackField() { const c = document.getElementById('season_packs_container'); const d = document.createElement('div'); d.className = 'dynamic-item'; d.innerHTML = `<button type="button" onclick="this.parentElement.remove()" class="btn btn-danger">Remove</button><div class="form-group"><label>Season Number:</label><input type="number" name="pack_season[]" required /></div><div class="form-group"><label>Quality (e.g., 720p):</label><input type="text" name="pack_quality[]" required /></div><div class="form-group"><label>Telegram Message ID:</label><input type="number" name="pack_message_id[]" required /></div>`; c.appendChild(d); }
    document.addEventListener('DOMContentLoaded', toggleFields);
</script>
</body></html>
"""
contact_html = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Contact Us / Report - MovieZone</title>
    <link href="https://fonts.googleapis.com/css2?family=Bebas+Neue&family=Roboto:wght@400;700&display=swap" rel="stylesheet">
    <style>
        :root { --netflix-red: #E50914; --netflix-black: #141414; --dark-gray: #222; --light-gray: #333; --text-light: #f5f5f5; }
        body { font-family: 'Roboto', sans-serif; background: var(--netflix-black); color: var(--text-light); padding: 20px; display: flex; flex-direction: column; justify-content: center; align-items: center; min-height: 100vh; }
        .contact-container { max-width: 600px; width: 100%; background: var(--dark-gray); padding: 30px; border-radius: 8px; }
        h2 { font-family: 'Bebas Neue', sans-serif; color: var(--netflix-red); font-size: 2.5rem; text-align: center; margin-bottom: 25px; }
        .form-group { margin-bottom: 20px; } label { display: block; margin-bottom: 8px; font-weight: bold; }
        input, select, textarea { width: 100%; padding: 12px; border-radius: 4px; border: 1px solid var(--light-gray); font-size: 1rem; background: var(--light-gray); color: var(--text-light); box-sizing: border-box; }
        textarea { resize: vertical; min-height: 120px; } button[type="submit"] { background: var(--netflix-red); color: white; font-weight: 700; cursor: pointer; border: none; padding: 12px 25px; border-radius: 4px; font-size: 1.1rem; width: 100%; }
        .success-message { text-align: center; padding: 20px; background-color: #1f4e2c; color: #d4edda; border-radius: 5px; margin-bottom: 20px; }
        .back-link { display: block; text-align: center; margin-top: 20px; color: var(--netflix-red); text-decoration: none; font-weight: bold; }
        /* [NEW] Footer */
        .main-footer { padding: 20px; text-align: center; color: #a0a0a0; font-size: 0.9rem; width: 100%; }
        .main-footer a { color: #a0a0a0; transition: color 0.2s ease; } .main-footer a:hover { color: var(--netflix-red); }
    </style>
</head>
<body>
<div class="contact-container">
    <h2>Contact Us</h2>
    {% if message_sent %}
        <div class="success-message"><p>Your message has been sent successfully. Thank you!</p></div>
        <a href="{{ url_for('home') }}" class="back-link">← Back to Home</a>
    {% else %}
        <form method="post">
            <div class="form-group"><label for="type">Subject:</label><select name="type" id="type"><option value="Movie Request" {% if prefill_type == 'Problem Report' %}disabled{% endif %}>Movie/Series Request</option><option value="Problem Report" {% if prefill_type == 'Problem Report' %}selected{% endif %}>Report a Problem</option><option value="General Feedback">General Feedback</option></select></div>
            <div class="form-group"><label for="content_title">Movie/Series Title:</label><input type="text" name="content_title" id="content_title" value="{{ prefill_title }}" required></div>
            <div class="form-group"><label for="message">Your Message:</label><textarea name="message" id="message" required></textarea></div>
            <div class="form-group"><label for="email">Your Email (Optional):</label><input type="email" name="email" id="email"></div>
            <input type="hidden" name="reported_content_id" value="{{ prefill_id }}">
            <button type="submit">Submit</button>
        </form>
        <a href="{{ url_for('home') }}" class="back-link">← Cancel</a>
    {% endif %}
</div>
<!-- [NEW] Footer -->
<footer class="main-footer">
    <a href="https://t.me/PrimeCineZone" target="_blank" rel="noopener">&copy; ALL RIGHTS RESERVED PMWBD</a>
</footer>
</body>
</html>
"""

# [NEW] HTML template for the Disclaimer page
disclaimer_html = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Disclaimer - PmwBD</title>
    <style>
        :root { --netflix-red: #E50914; --netflix-black: #141414; --text-light: #f5f5f5; --text-dark: #a0a0a0; }
        body { font-family: 'Roboto', sans-serif; background: var(--netflix-black); color: var(--text-light); padding: 40px 20px; line-height: 1.6; }
        .container { max-width: 800px; margin: 0 auto; background: #1a1a1a; padding: 30px; border-radius: 8px; }
        h1 { font-family: 'Bebas Neue', sans-serif; color: var(--netflix-red); font-size: 2.8rem; margin-bottom: 20px; text-align: center; }
        p { margin-bottom: 15px; color: var(--text-dark); }
        strong { color: var(--text-light); }
        a { color: var(--netflix-red); text-decoration: none; }
        a:hover { text-decoration: underline; }
        .back-link { display: block; text-align: center; margin-top: 30px; font-weight: bold; }
        .main-footer { padding: 20px; text-align: center; color: #a0a0a0; font-size: 0.9rem; width: 100%; }
        .main-footer a { color: #a0a0a0; transition: color 0.2s ease; } .main-footer a:hover { color: var(--netflix-red); }
    </style>
</head>
<body>
    <div class="container">
        <h1>Disclaimer</h1>
        <p><strong>PmwBD.com</strong> does not host, store, or upload any video, films, or media files. Our site does not own any of the content displayed. We are not responsible for the accuracy, compliance, copyright, legality, decency, or any other aspect of the content of other linked sites.</p>
        <p>The content available on this website is collected from various publicly available sources on the internet. We act as a search engine that indexes and displays hyperlinks to content that is freely available online. We do not exercise any control over the content of these external websites.</p>
        <p>All content is the copyright of their respective owners. We encourage all copyright owners to recognize that the links contained within this site are located elsewhere on the web. The embedded links are from other sites such as (but not limited to) YouTube, Dailymotion, Google Drive, etc. If you have any legal issues please contact the appropriate media file owners or host sites.</p>
        <p>If you believe that any content on our website infringes upon your copyright, please visit our <a href="{{ url_for('dmca') }}">DMCA page</a> for instructions on how to submit a takedown request.</p>
        <a href="{{ url_for('home') }}" class="back-link">&larr; Back to Home</a>
    </div>
    <footer class="main-footer">
        <a href="https://t.me/PrimeCineZone" target="_blank" rel="noopener">&copy; ALL RIGHTS RESERVED PMWBD</a>
    </footer>
</body>
</html>
"""

# [NEW] HTML template for the DMCA page
dmca_html = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>DMCA Policy - PmwBD</title>
    <style>
        :root { --netflix-red: #E50914; --netflix-black: #141414; --text-light: #f5f5f5; --text-dark: #a0a0a0; }
        body { font-family: 'Roboto', sans-serif; background: var(--netflix-black); color: var(--text-light); padding: 40px 20px; line-height: 1.6; }
        .container { max-width: 800px; margin: 0 auto; background: #1a1a1a; padding: 30px; border-radius: 8px; }
        h1 { font-family: 'Bebas Neue', sans-serif; color: var(--netflix-red); font-size: 2.8rem; margin-bottom: 20px; text-align: center; }
        h2 { font-family: 'Bebas Neue', sans-serif; color: var(--text-light); font-size: 1.8rem; margin-top: 25px; margin-bottom: 10px; border-bottom: 2px solid var(--netflix-red); padding-bottom: 5px; }
        p, li { margin-bottom: 15px; color: var(--text-dark); }
        ul { padding-left: 20px; }
        a { color: var(--netflix-red); text-decoration: none; }
        a:hover { text-decoration: underline; }
        .back-link { display: block; text-align: center; margin-top: 30px; font-weight: bold; }
        .main-footer { padding: 20px; text-align: center; color: #a0a0a0; font-size: 0.9rem; width: 100%; }
        .main-footer a { color: #a0a0a0; transition: color 0.2s ease; } .main-footer a:hover { color: var(--netflix-red); }
    </style>
</head>
<body>
    <div class="container">
        <h1>DMCA Copyright Infringement Notification</h1>
        <p>PmwBD.com respects the intellectual property rights of others and expects its users to do the same. In accordance with the Digital Millennium Copyright Act (DMCA), we will respond promptly to notices of alleged copyright infringement.</p>
        <p>As stated in our disclaimer, this website does not host any files on its servers. All content is provided by non-affiliated third parties from publicly available sources.</p>
        
        <h2>Procedure for Reporting Copyright Infringement:</h2>
        <p>If you are a copyright owner or an agent thereof and believe that any content on our website infringes upon your copyrights, you may submit a notification by providing our Copyright Agent with the following information in writing:</p>
        <ul>
            <li>A physical or electronic signature of a person authorized to act on behalf of the owner of an exclusive right that is allegedly infringed.</li>
            <li>Identification of the copyrighted work claimed to have been infringed, or, if multiple copyrighted works are covered by a single notification, a representative list of such works.</li>
            <li>Identification of the material that is claimed to be infringing or to be the subject of infringing activity and that is to be removed or access to which is to be disabled, and information reasonably sufficient to permit us to locate the material (please provide the exact URL(s)).</li>
            <li>Information reasonably sufficient to permit us to contact you, such as an address, telephone number, and, if available, an electronic mail address.</li>
            <li>A statement that you have a good faith belief that use of the material in the manner complained of is not authorized by the copyright owner, its agent, or the law.</li>
            <li>A statement that the information in the notification is accurate, and under penalty of perjury, that you are authorized to act on behalf of the owner of an exclusive right that is allegedly infringed.</li>
        </ul>

        <h2>Where to Send a Takedown Notice:</h2>
        <p>Please send your DMCA takedown notice to us via our contact page. We recommend using the "Problem Report" subject for faster processing.</p>
        <p><a href="{{ url_for('contact') }}"><strong>Click here to go to the Contact Page</strong></a></p>
        <p>We will review your request and remove the infringing content within 48-72 hours.</p>

        <a href="{{ url_for('home') }}" class="back-link">&larr; Back to Home</a>
    </div>
    <footer class="main-footer">
        <a href="https://t.me/PrimeCineZone" target="_blank" rel="noopener">&copy; ALL RIGHTS RESERVED PMWBD</a>
    </footer>
</body>
</html>
"""

def parse_filename(filename):
    LANGUAGE_MAP = {
        'hindi': 'Hindi', 'hin': 'Hindi', 'english': 'English', 'eng': 'English',
        'bengali': 'Bengali', 'bangla': 'Bangla', 'ben': 'Bengali',
        'tamil': 'Tamil', 'tam': 'Tamil', 'telugu': 'Telugu', 'tel': 'Telugu',
        'kannada': 'Kannada', 'kan': 'Kannada', 'malayalam': 'Malayalam', 'mal': 'Malayalam',
        'korean': 'Korean', 'kor': 'Korean', 'chinese': 'Chinese', 'chi': 'Chinese',
        'japanese': 'Japanese', 'jap': 'Japanese',
        'dual audio': ['Hindi', 'English'], 'dual': ['Hindi', 'English'],
        'multi audio': ['Multi Audio']
    }
    JUNK_KEYWORDS = [
        '1080p', '720p', '480p', '2160p', '4k', 'uhd', 'web-dl', 'webdl', 'webrip',
        'brrip', 'bluray', 'dvdrip', 'hdrip', 'hdcam', 'camrip', 'hdts', 'x264',
        'x265', 'hevc', 'avc', 'aac', 'ac3', 'dts', '5.1', '7.1', 'final', 'uncut',
        'extended', 'remastered', 'unrated', 'nf', 'www', 'com', 'net', 'org', 'psa'
    ]
    SEASON_PACK_KEYWORDS = ['complete', 'season', 'pack', 'all episodes', 'zip']

    base_name, _ = os.path.splitext(filename)
    processed_name = re.sub(r'[\._\[\]\(\)\{\}-]', ' ', base_name)
    
    found_languages = []
    temp_name_for_lang = processed_name.lower()
    for keyword, lang_name in LANGUAGE_MAP.items():
        if re.search(r'\b' + re.escape(keyword) + r'\b', temp_name_for_lang):
            if isinstance(lang_name, list):
                found_languages.extend(lang_name)
            else:
                found_languages.append(lang_name)
    languages = sorted(list(set(found_languages))) if found_languages else []

    quality_match = re.search(r'\b(\d{3,4}p)\b', processed_name, re.I)
    quality = quality_match.group(1) if quality_match else "HD"

    season_pack_match = re.search(r'^(.*?)[\s\.]*(?:S|Season)[\s\.]?(\d{1,2})', processed_name, re.I)
    if season_pack_match:
        text_after_season = processed_name[season_pack_match.end():].lower()
        is_pack = any(keyword in text_after_season for keyword in SEASON_PACK_KEYWORDS) or not re.search(r'\be\d', text_after_season)

        if is_pack:
            title = season_pack_match.group(1).strip()
            season_num = int(season_pack_match.group(2))
            
            for junk in JUNK_KEYWORDS + SEASON_PACK_KEYWORDS:
                title = re.sub(r'\b' + re.escape(junk) + r'\b', '', title, flags=re.I)
            final_title = ' '.join(title.split()).title()
            
            if final_title:
                return {'type': 'series_pack', 'title': final_title, 'season': season_num, 'quality': quality, 'languages': languages}

    series_patterns = [
        re.compile(r'^(.*?)[\s\.]*(?:S|Season)[\s\.]?(\d{1,2})[\s\.]*(?:E|Ep|Episode)[\s\.]?(\d{1,3})', re.I),
        re.compile(r'^(.*?)[\s\.]*(?:E|Ep|Episode)[\s\.]?(\d{1,3})', re.I)
    ]
    for i, pattern in enumerate(series_patterns):
        match = pattern.search(processed_name)
        if match:
            title = match.group(1).strip()
            season_num = int(match.group(2)) if i == 0 else 1
            episode_num = int(match.group(3)) if i == 0 else int(match.group(2))

            for junk in JUNK_KEYWORDS:
                title = re.sub(r'\b' + re.escape(junk) + r'\b', '', title, flags=re.I)
            final_title = ' '.join(title.split()).title()
            
            if final_title:
                return {'type': 'series', 'title': final_title, 'season': season_num, 'episode': episode_num, 'languages': languages}

    year_match = re.search(r'\b(19[5-9]\d|20\d{2})\b', processed_name)
    year = year_match.group(1) if year_match else None
    title_part = processed_name[:year_match.start()] if year_match else processed_name
    
    temp_title = title_part
    for lang_key in LANGUAGE_MAP.keys():
        temp_title = re.sub(r'\b' + lang_key + r'\b', '', temp_title, flags=re.I)
    for junk in JUNK_KEYWORDS:
        temp_title = re.sub(r'\b' + re.escape(junk) + r'\b', '', temp_title, flags=re.I)
    final_title = ' '.join(temp_title.split()).title()
    
    return {'type': 'movie', 'title': final_title, 'year': year, 'quality': quality, 'languages': languages} if final_title else None

def get_tmdb_details_from_api(tmdb_id, content_type):
    if not TMDB_API_KEY:
        print("ERROR: TMDB_API_KEY is not set.")
        return None
    
    search_type = "tv" if content_type == "series" else "movie"
    
    print(f"INFO: Fetching TMDb details for ID: '{tmdb_id}' (Type: {search_type})")
    try:
        detail_url = f"https://api.themoviedb.org/3/{search_type}/{tmdb_id}?api_key={TMDB_API_KEY}&append_to_response=videos"
        detail_res = requests.get(detail_url, timeout=10)
        detail_res.raise_for_status()
        res_json = detail_res.json()

        trailer_key = next((v['key'] for v in res_json.get("videos", {}).get("results", []) if v.get('type') == 'Trailer' and v.get('site') == 'YouTube'), None)
        trailer_link = f"https://www.youtube.com/watch?v={trailer_key}" if trailer_key else None
        
        details = {
            "tmdb_id": tmdb_id, 
            "title": res_json.get("title") or res_json.get("name"), 
            "poster": f"https://image.tmdb.org/t/p/w500{res_json.get('poster_path')}" if res_json.get('poster_path') else None, 
            "overview": res_json.get("overview"), 
            "release_date": res_json.get("release_date") or res_json.get("first_air_date"), 
            "genres": [g['name'] for g in res_json.get("genres", [])], 
            "vote_average": res_json.get("vote_average"), 
            "trailer_link": trailer_link,
            "type": "series" if search_type == "tv" else "movie"
        }
        print(f"SUCCESS: Found TMDb details for '{details['title']}' (ID: {tmdb_id}).")
        return details
    except requests.RequestException as e:
        print(f"ERROR: TMDb API request failed for ID '{tmdb_id}'. Reason: {e}")
        return None


def get_tmdb_details_from_title(title, content_type, year=None):
    if not TMDB_API_KEY: return None
    search_type = "tv" if content_type in ["series", "series_pack"] else "movie"
    try:
        search_url = f"https://api.themoviedb.org/3/search/{search_type}?api_key={TMDB_API_KEY}&query={requests.utils.quote(title)}"
        if year and search_type == "movie": search_url += f"&primary_release_year={year}"
        search_res = requests.get(search_url, timeout=10).json()
        if not search_res.get("results"): return None
        tmdb_id = search_res["results"][0].get("id")
        return get_tmdb_details_from_api(tmdb_id, "series" if search_type == "tv" else "movie")
    except Exception as e:
        print(f"Error searching TMDB by title '{title}': {e}")
        return None

def process_movie_list(movie_list):
    return [{**item, '_id': str(item['_id'])} for item in movie_list]



@app.route('/')
def home():
    try:
        query = request.args.get('q', '').strip()
        if query:
            movies_list = list(movies.find({"title": {"$regex": query, "$options": "i"}}).sort('_id', -1))
            return render_template_string(index_html, movies=process_movie_list(movies_list), query=f'Results for "{query}"', is_full_page_list=True)
        
        limit = 12
        context = {
            "trending_movies": process_movie_list(list(movies.find({"categories": "Trending", "is_coming_soon": {"$ne": True}}).sort('_id', -1).limit(limit))),
            "latest_movies": process_movie_list(list(movies.find({"categories": "Latest Movie", "is_coming_soon": {"$ne": True}}).sort('_id', -1).limit(limit))),
            "latest_series": process_movie_list(list(movies.find({"categories": "Latest Series", "is_coming_soon": {"$ne": True}}).sort('_id', -1).limit(limit))),
            "hindi_movies": process_movie_list(list(movies.find({"categories": "Hindi", "is_coming_soon": {"$ne": True}}).sort('_id', -1).limit(limit))),
            "bengali_movies": process_movie_list(list(movies.find({"categories": "Bengali", "is_coming_soon": {"$ne": True}}).sort('_id', -1).limit(limit))),
            "english_movies": process_movie_list(list(movies.find({"categories": "English", "is_coming_soon": {"$ne": True}}).sort('_id', -1).limit(limit))),
            "coming_soon_movies": process_movie_list(list(movies.find({"is_coming_soon": True}).sort('_id', -1).limit(limit))),
            "recently_added": process_movie_list(list(movies.find({"is_coming_soon": {"$ne": True}}).sort('_id', -1).limit(6))),
            "is_full_page_list": False, 
            "query": ""
        }
        return render_template_string(index_html, **context)
    except Exception as e:
        print(f"FATAL ERROR on home page: {e}")
        return "<h1>Something went wrong. Please try again later.</h1> <p>Error details have been logged.</p>", 500

@app.route('/movie/<movie_id>')
def movie_detail(movie_id):
    try:
        movie = movies.find_one({"_id": ObjectId(movie_id)})
        if not movie: return "Content not found", 404
        related_movies = []
        if movie.get("genres"):
            related_movies = list(movies.find({"genres": {"$in": movie["genres"]}, "_id": {"$ne": ObjectId(movie_id)}}).limit(12))
        
        trailer_link = movie.get("trailer_link")
        trailer_embed_key = get_youtube_embed_key(trailer_link)

        return render_template_string(detail_html, movie=movie, trailer_embed_key=trailer_embed_key, related_movies=process_movie_list(related_movies))
    except Exception: return "Content not found", 404

@app.route('/watch/<movie_id>')
def watch_movie(movie_id):
    try:
        movie = movies.find_one({"_id": ObjectId(movie_id)})
        if not movie or not movie.get("watch_link"): return "Content not found.", 404
        return render_template_string(watch_html, watch_link=movie["watch_link"], title=movie["title"])
    except Exception: return "An error occurred.", 500

def render_full_list(content_list, title):
    return render_template_string(index_html, movies=process_movie_list(content_list), query=title, is_full_page_list=True)

@app.route('/genres')
def genres_page(): return render_template_string(genres_html, genres=sorted([g for g in movies.distinct("genres") if g]), title="Browse by Genre")

@app.route('/genre/<genre_name>')
def movies_by_genre(genre_name): return render_full_list(list(movies.find({"genres": genre_name}).sort('_id', -1)), f'Genre: {genre_name}')

@app.route('/category/<cat_name>')
def movies_by_category(cat_name):
    title = cat_name.replace("_", " ").title()
    return render_full_list(list(movies.find({"categories": title, "is_coming_soon": {"$ne": True}}).sort('_id', -1)), title)

@app.route('/coming_soon')
def coming_soon(): return render_full_list(list(movies.find({"is_coming_soon": True}).sort('_id', -1)), "Coming Soon")

# [NEW] Routes for Disclaimer and DMCA pages
@app.route('/disclaimer')
def disclaimer():
    return render_template_string(disclaimer_html)

@app.route('/dmca')
def dmca():
    return render_template_string(dmca_html)


@app.route('/admin', methods=["GET", "POST"])
@requires_auth
def admin():
    if request.method == "POST":
        movie_data = {
            "title": request.form.get("title", "").strip(),
            "type": request.form.get("content_type", "movie"),
            "poster": request.form.get("poster", "").strip() or PLACEHOLDER_POSTER,
            "overview": request.form.get("overview", "").strip(),
            "genres": [g.strip() for g in request.form.get("genres", "").split(',') if g.strip()],
            "trailer_link": request.form.get("trailer_link", "").strip() or None,
            "poster_badge": request.form.get("poster_badge", "").strip() or None,
            "categories": request.form.getlist("categories"),
            "is_coming_soon": request.form.get("is_coming_soon") == "true",
            "links": [], "files": [], "episodes": [], "season_packs": [], "languages": [], "streaming_links": []
        }
        
        if not movie_data.get('tmdb_id'):
            tmdb_details = get_tmdb_details_from_title(movie_data['title'], movie_data['type'])
            if tmdb_details:
                tmdb_data_copy = tmdb_details.copy()
                tmdb_data_copy.update(movie_data)
                movie_data = tmdb_data_copy

        if movie_data['type'] == "movie":
            watch_link = request.form.get("watch_link", "").strip()
            if watch_link: movie_data['watch_link'] = watch_link

            # [REVERTED] Handle Fixed Streaming Links
            streaming_links = [
                ("480p", request.form.get("streaming_link_1", "").strip()),
                ("720p", request.form.get("streaming_link_2", "").strip()),
                ("1080p", request.form.get("streaming_link_3", "").strip()),
            ]
            movie_data['streaming_links'] = [{"name": name, "url": url} for name, url in streaming_links if url]

            links_480 = request.form.get("link_480p", "").strip()
            links_720 = request.form.get("link_720p", "").strip()
            links_1080 = request.form.get("link_1080p", "").strip()
            if links_480: movie_data['links'].append({"quality": "480p", "url": links_480})
            if links_720: movie_data['links'].append({"quality": "720p", "url": links_720})
            if links_1080: movie_data['links'].append({"quality": "1080p", "url": links_1080})

            tg_qualities = request.form.getlist('telegram_quality[]')
            tg_message_ids = request.form.getlist('telegram_message_id[]')
            for q, mid in zip(tg_qualities, tg_message_ids):
                if q.strip() and mid.strip():
                    try: movie_data['files'].append({"quality": q.strip(), "message_id": int(mid)})
                    except (ValueError, TypeError): print(f"WARN: Invalid message_id '{mid}' for quality '{q}'.")

        else: # series
            seasons = request.form.getlist('episode_season[]')
            ep_nums = request.form.getlist('episode_number[]')
            ep_titles = request.form.getlist('episode_title[]')
            ep_msg_ids = request.form.getlist('episode_message_id[]')
            ep_watch_links = request.form.getlist('episode_watch_link[]')

            for s, e, t, m, w in zip(seasons, ep_nums, ep_titles, ep_msg_ids, ep_watch_links):
                if s.strip() and e.strip() and (m.strip() or w.strip()):
                    try:
                        episode = {"season": int(s), "episode_number": int(e), "title": t.strip(), "watch_link": w.strip() or None, "message_id": int(m) if m.strip() else None}
                        movie_data['episodes'].append(episode)
                    except (ValueError, TypeError): print(f"WARN: Invalid episode data for S{s}E{e}.")

        movies.insert_one(movie_data)
        return redirect(url_for('admin'))

    search_query = request.args.get('search', '').strip()
    query_filter = {}
    if search_query: query_filter = {"title": {"$regex": search_query, "$options": "i"}}
    
    ad_settings = settings.find_one() or {}
    content_list = process_movie_list(list(movies.find(query_filter).sort('_id', -1)))
    feedback_list = process_movie_list(list(feedback.find().sort('timestamp', -1)))
    
    return render_template_string(admin_html, content_list=content_list, ad_settings=ad_settings, feedback_list=feedback_list, search_query=search_query, categories=CATEGORIES)


@app.route('/admin/api/fetch_tmdb')
@requires_auth
def fetch_tmdb_data():
    tmdb_url = request.args.get('url')
    if not tmdb_url:
        return jsonify({"error": "URL parameter is missing"}), 400

    try:
        parsed_url = urlparse(unquote(tmdb_url))
        path_parts = [part for part in parsed_url.path.split('/') if part]

        if len(path_parts) < 2 or path_parts[0] not in ['movie', 'tv']:
            raise ValueError("Invalid TMDB URL format. Must be /movie/ID-title or /tv/ID-title.")

        content_type = "series" if path_parts[0] == 'tv' else "movie"
        tmdb_id = path_parts[1].split('-')[0]

        if not tmdb_id.isdigit():
            raise ValueError("Could not extract a valid numeric ID from the URL.")
            
        details = get_tmdb_details_from_api(tmdb_id, content_type)
        if details:
            return jsonify(details)
        else:
            return jsonify({"error": "Could not find details for this ID on TMDb."}), 404
            
    except (ValueError, IndexError) as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        return jsonify({"error": f"An unexpected error occurred: {str(e)}"}), 500

@app.route('/admin/save_ads', methods=['POST'])
@requires_auth
def save_ads():
    ad_codes = {
        "popunder_code": request.form.get("popunder_code", ""), 
        "social_bar_code": request.form.get("social_bar_code", ""),
        "banner_ad_code": request.form.get("banner_ad_code", ""), 
        "native_banner_code": request.form.get("native_banner_code", "")
    }
    settings.update_one({}, {"$set": ad_codes}, upsert=True)
    return redirect(url_for('admin'))

@app.route('/edit_movie/<movie_id>', methods=["GET", "POST"])
@requires_auth
def edit_movie(movie_id):
    try: obj_id = ObjectId(movie_id)
    except Exception: return "Invalid Movie ID", 400
    
    movie_obj = movies.find_one({"_id": obj_id})
    if not movie_obj: return "Movie not found", 404

    if request.method == "POST":
        content_type = request.form.get("content_type", "movie")
        update_data = {
            "title": request.form.get("title", "").strip(), 
            "type": content_type,
            "poster": request.form.get("poster", "").strip() or PLACEHOLDER_POSTER, 
            "overview": request.form.get("overview", "").strip(),
            "genres": [g.strip() for g in request.form.get("genres", "").split(',') if g.strip()],
            "languages": [lang.strip() for lang in request.form.get("languages", "").split(',') if lang.strip()],
            "trailer_link": request.form.get("trailer_link", "").strip() or None,
            "poster_badge": request.form.get("poster_badge", "").strip() or None,
            "categories": request.form.getlist("categories"),
            "is_coming_soon": request.form.get("is_coming_soon") == "true",
        }
        
        if content_type == "movie":
            update_data["watch_link"] = request.form.get("watch_link", "").strip() or None
            
            # [REVERTED] Handle Fixed Streaming Links
            streaming_links_data = [
                ("480p", request.form.get("streaming_link_1", "").strip()),
                ("720p", request.form.get("streaming_link_2", "").strip()),
                ("1080p", request.form.get("streaming_link_3", "").strip()),
            ]
            update_data["streaming_links"] = [{"name": name, "url": url} for name, url in streaming_links_data if url]

            update_data["links"] = [{"quality": q, "url": u} for q, u in [("480p", request.form.get("link_480p")), ("720p", request.form.get("link_720p")), ("1080p", request.form.get("link_1080p"))] if u and u.strip()]
            update_data["files"] = [{"quality": q.strip(), "message_id": int(mid)} for q, mid in zip(request.form.getlist('telegram_quality[]'), request.form.getlist('telegram_message_id[]')) if q.strip() and mid.strip()]
            movies.update_one({"_id": obj_id}, {"$set": update_data, "$unset": {"episodes": "", "season_packs": ""}})
        else: # series
            update_data["episodes"] = [{"season": int(s), "episode_number": int(e), "title": t.strip(), "watch_link": w.strip() or None, "message_id": int(m) if m.strip() else None} for s, e, t, w, m in zip(request.form.getlist('episode_season[]'), request.form.getlist('episode_number[]'), request.form.getlist('episode_title[]'), request.form.getlist('episode_watch_link[]'), request.form.getlist('episode_message_id[]')) if s.strip() and e.strip()]
            update_data["season_packs"] = [{"season": int(s), "quality": q.strip(), "message_id": int(mid)} for s, q, mid in zip(request.form.getlist('pack_season[]'), request.form.getlist('pack_quality[]'), request.form.getlist('pack_message_id[]')) if s.strip() and q.strip() and mid.strip()]
            movies.update_one({"_id": obj_id}, {"$set": update_data, "$unset": {"links": "", "watch_link": "", "files": "", "streaming_links": ""}})
        
        return redirect(url_for('admin'))

    return render_template_string(edit_html, movie=movie_obj, categories=CATEGORIES)

@app.route('/delete_movie/<movie_id>')
@requires_auth
def delete_movie(movie_id):
    movies.delete_one({"_id": ObjectId(movie_id)})
    return redirect(url_for('admin'))


@app.route('/admin/delete_all_movies')
@requires_auth
def delete_all_movies():
    try:
        result = movies.delete_many({})
        print(f"DELETED: {result.deleted_count} documents from the 'movies' collection by admin.")
    except Exception as e:
        print(f"ERROR: Could not delete all movies. Reason: {e}")
    return redirect(url_for('admin'))


@app.route('/contact', methods=['GET', 'POST'])
def contact():
    if request.method == 'POST':
        feedback_data = {
            "type": request.form.get("type"), "content_title": request.form.get("content_title"),
            "message": request.form.get("message"), "email": request.form.get("email", "").strip(),
            "reported_content_id": request.form.get("reported_content_id"), "timestamp": datetime.utcnow()
        }
        feedback.insert_one(feedback_data)
        return render_template_string(contact_html, message_sent=True)
    prefill_title, prefill_id = request.args.get('title', ''), request.args.get('report_id', '')
    prefill_type = 'Problem Report' if prefill_id else 'Movie Request'
    return render_template_string(contact_html, message_sent=False, prefill_title=prefill_title, prefill_id=prefill_id, prefill_type=prefill_type)


@app.route('/delete_feedback/<feedback_id>')
@requires_auth
def delete_feedback(feedback_id):
    feedback.delete_one({"_id": ObjectId(feedback_id)})
    return redirect(url_for('admin'))


@app.route('/webhook', methods=['POST'])
def telegram_webhook():
    data = request.get_json()
    if 'channel_post' in data:
        post = data['channel_post']
        if str(post.get('chat', {}).get('id')) != ADMIN_CHANNEL_ID: 
            return jsonify(status='ok', reason='not_admin_channel')
        
        file = post.get('video') or post.get('document')
        if not (file and file.get('file_name')): 
            return jsonify(status='ok', reason='no_file_in_post')
        
        filename = file.get('file_name')
        print(f"\n--- [WEBHOOK] PROCESSING NEW FILE: {filename} ---")
        parsed_info = parse_filename(filename)
        
        if not parsed_info or not parsed_info.get('title'):
            print(f"FAILED: Could not parse title from filename: {filename}")
            return jsonify(status='ok', reason='parsing_failed')
        
        print(f"PARSED INFO: {parsed_info}")

        tmdb_data = get_tmdb_details_from_title(parsed_info['title'], parsed_info['type'], parsed_info.get('year'))

        def get_or_create_content_entry(tmdb_details, parsed_details):
            if tmdb_details and tmdb_details.get("tmdb_id"):
                print(f"INFO: TMDb data found for '{tmdb_details['title']}'. Processing with full details.")
                tmdb_id = tmdb_details.get("tmdb_id")
                existing_entry = movies.find_one({"tmdb_id": tmdb_id})
                if not existing_entry:
                    base_doc = {
                        **tmdb_details, "type": "movie" if parsed_details['type'] == 'movie' else "series",
                        "languages": [], "episodes": [], "season_packs": [], "files": [], "categories": [],
                        "is_coming_soon": False, "streaming_links": []
                    }
                    movies.insert_one(base_doc)
                    newly_created_doc = movies.find_one({"tmdb_id": tmdb_id})
                    send_notification_to_channel(newly_created_doc)
                    return newly_created_doc
                return existing_entry
            else:
                print(f"WARNING: TMDb data not found for '{parsed_details['title']}'. Using/Creating a placeholder.")
                existing_entry = movies.find_one({
                    "title": {"$regex": f"^{re.escape(parsed_details['title'])}$", "$options": "i"}, 
                    "tmdb_id": None
                })
                if not existing_entry:
                    shell_doc = {
                        "title": parsed_details['title'], "type": "movie" if parsed_details['type'] == 'movie' else "series",
                        "poster": PLACEHOLDER_POSTER, "overview": "Details will be updated soon.",
                        "release_date": None, "genres": [], "vote_average": 0, "trailer_link": None, "tmdb_id": None,
                        "languages": [], "episodes": [], "season_packs": [], "files": [], "categories": [],
                        "is_coming_soon": False, "streaming_links": []
                    }
                    movies.insert_one(shell_doc)
                    newly_created_doc = movies.find_one({"_id": shell_doc['_id']})
                    send_notification_to_channel(newly_created_doc)
                    return newly_created_doc
                return existing_entry

        content_entry = get_or_create_content_entry(tmdb_data, parsed_info)
        if not content_entry:
            print("FATAL: Could not get or create a content entry.")
            return jsonify(status="error", reason="db_entry_failed")

        update_op = {}
        if parsed_info.get('languages'):
            update_op["$addToSet"] = {"languages": {"$each": parsed_info['languages']}}

        if parsed_info['type'] == 'movie':
            new_file = {"quality": parsed_info.get('quality', 'HD'), "message_id": post['message_id']}
            movies.update_one({"_id": content_entry['_id']}, {"$pull": {"files": {"quality": new_file['quality']}}})
            update_op.setdefault("$push", {})["files"] = new_file
        
        elif parsed_info['type'] == 'series_pack':
            new_pack = {"season": parsed_info['season'], "quality": parsed_info['quality'], "message_id": post['message_id']}
            movies.update_one({"_id": content_entry['_id']}, {"$pull": {"season_packs": {"season": new_pack['season'], "quality": new_pack['quality']}}})
            update_op.setdefault("$push", {})["season_packs"] = new_pack

        elif parsed_info['type'] == 'series':
            new_episode = {"season": parsed_info['season'], "episode_number": parsed_info['episode'], "message_id": post['message_id']}
            movies.update_one({"_id": content_entry['_id']}, {"$pull": {"episodes": {"season": new_episode['season'], "episode_number": new_episode['episode_number']}}})
            update_op.setdefault("$push", {})["episodes"] = new_episode

        if update_op:
            movies.update_one({"_id": content_entry['_id']}, update_op)
            print(f"SUCCESS: Entry for '{content_entry['title']}' has been updated.")

    elif 'message' in data:
        message = data['message']
        chat_id = message['chat']['id']
        text = message.get('text', '')

        # --- [DEBUG] কোড এখানে যুক্ত করা হয়েছে ---
        print("\n--- [DEBUG] INCOMING MESSAGE ---")
        print(f"CHAT ID: {chat_id}")
        print(f"MESSAGE TEXT: {text}")
        # --- [DEBUG] কোড শেষ ---

        if text.startswith('/start'):
            parts = text.split()
            if len(parts) > 1:
                try:
                    payload_parts = parts[1].split('_')
                    doc_id_str = payload_parts[0]
                    
                    # --- [DEBUG] কোড এখানে যুক্ত করা হয়েছে ---
                    print(f"[DEBUG] Payload Parts: {payload_parts}")
                    print(f"[DEBUG] Document ID String: {doc_id_str}")
                    # --- [DEBUG] কোড শেষ ---
                    
                    content = movies.find_one({"_id": ObjectId(doc_id_str)})
                    
                    # --- [DEBUG] কোড এখানে যুক্ত করা হয়েছে ---
                    if not content:
                        print(f"[DEBUG] ERROR: Content not found in DB for ID: {doc_id_str}")
                        requests.get(f"{TELEGRAM_API_URL}/sendMessage", params={'chat_id': chat_id, 'text': f"Error: Could not find content with ID {doc_id_str}."})
                        return jsonify(status='ok')
                    print(f"[DEBUG] Found content in DB: {content.get('title')}")
                    # --- [DEBUG] কোড শেষ ---

                    message_to_copy_id = None
                    file_info_text = ""
                    
                    if len(payload_parts) == 3 and payload_parts[1].startswith('S'):
                        season_num = int(payload_parts[1][1:])
                        quality = payload_parts[2]
                        pack = next((p for p in content.get('season_packs', []) if p.get('season') == season_num and p.get('quality') == quality), None)
                        if pack:
                            message_to_copy_id = pack.get('message_id')
                            file_info_text = f"Complete Season {season_num} ({quality})"

                    elif content.get('type') == 'series' and len(payload_parts) == 3:
                        s_num, e_num = int(payload_parts[1]), int(payload_parts[2])
                        episode = next((ep for ep in content.get('episodes', []) if ep.get('season') == s_num and ep.get('episode_number') == e_num), None)
                        if episode: 
                            message_to_copy_id = episode.get('message_id')
                            file_info_text = f"S{s_num:02d}E{e_num:02d}"

                    elif content.get('type') == 'movie' and len(payload_parts) == 2:
                        quality = payload_parts[1]
                        file = next((f for f in content.get('files', []) if f.get('quality') == quality), None)
                        if file: 
                            message_to_copy_id = file.get('message_id')
                            file_info_text = f"({quality})"
                    
                    # --- [DEBUG] কোড এখানে যুক্ত করা হয়েছে ---
                    print(f"[DEBUG] Final message_id to copy: {message_to_copy_id}")
                    # --- [DEBUG] কোড শেষ ---

                    if message_to_copy_id:
                        caption_text = (
                            f"🎬 *{escape_markdown(content['title'])}* {escape_markdown(file_info_text)}\n\n"
                            f"✅ *Successfully Sent To Your PM*\n\n"
                            f"🔰 Join Our Main Channel\n➡️ [{escape_markdown(BOT_USERNAME)} Main]({MAIN_CHANNEL_LINK})\n\n"
                            f"📢 Join Our Update Channel\n➡️ [{escape_markdown(BOT_USERNAME)} Official]({UPDATE_CHANNEL_LINK})\n\n"
                            f"💬 For Any Help or Request\n➡️ [Contact Developer]({DEVELOPER_USER_LINK})"
                        )
                        payload = {'chat_id': chat_id, 'from_chat_id': ADMIN_CHANNEL_ID, 'message_id': message_to_copy_id, 'caption': caption_text, 'parse_mode': 'MarkdownV2'}
                        response = requests.post(f"{TELEGRAM_API_URL}/copyMessage", json=payload)
                        res = response.json()
                        
                        # --- [DEBUG] কোড এখানে যুক্ত করা হয়েছে ---
                        print(f"[DEBUG] Telegram API Response for copyMessage: {res}")
                        # --- [DEBUG] কোড শেষ ---
                        
                        if res.get('ok'):
                            new_msg_id = res['result']['message_id']
                            scheduler.add_job(func=delete_message_after_delay, trigger='date', run_date=datetime.now() + timedelta(minutes=30), args=[chat_id, new_msg_id], id=f'del_{chat_id}_{new_msg_id}', replace_existing=True)
                        else: 
                            requests.get(f"{TELEGRAM_API_URL}/sendMessage", params={'chat_id': chat_id, 'text': "Error sending file. It might have been deleted from the channel."})
                    else: 
                        requests.get(f"{TELEGRAM_API_URL}/sendMessage", params={'chat_id': chat_id, 'text': "Requested file/season not found."})
                except Exception as e:
                    print(f"Error processing /start command: {e}")
                    requests.get(f"{TELEGRAM_API_URL}/sendMessage", params={'chat_id': chat_id, 'text': "An unexpected error occurred."})
            else: 
                welcome_message = (f"👋 Welcome to {BOT_USERNAME}!\n\nBrowse all our content on our website.")
                try:
                    with app.app_context():
                        root_url = url_for('home', _external=True)
                    keyboard = {"inline_keyboard": [[{"text": "🎬 Visit Website", "url": root_url}]]}
                    requests.get(f"{TELEGRAM_API_URL}/sendMessage", params={'chat_id': chat_id, 'text': welcome_message, 'reply_markup': json.dumps(keyboard)})
                except Exception as e:
                     print(f"Error sending welcome message: {e}")
                     requests.get(f"{TELEGRAM_API_URL}/sendMessage", params={'chat_id': chat_id, 'text': welcome_message})

    return jsonify(status='ok')


@app.route('/notify/<movie_id>')
@requires_auth
def send_manual_notification(movie_id):
    try:
        obj_id = ObjectId(movie_id)
        movie_obj = movies.find_one({"_id": obj_id})
        
        if movie_obj:
            print(f"ADMIN_ACTION: Manually triggering notification for '{movie_obj.get('title')}'")
            send_notification_to_channel(movie_obj)
        else:
            print(f"ADMIN_ACTION_FAIL: Could not find movie with ID {movie_id} to send notification.")
            
    except Exception as e:
        print(f"ERROR in send_manual_notification for ID {movie_id}: {e}")
        
    return redirect(url_for('admin'))
