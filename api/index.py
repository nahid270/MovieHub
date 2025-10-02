import os
import sys
import requests
import json
from flask import Flask, render_template_string, request, redirect, url_for, Response, jsonify
from pymongo import MongoClient
from bson.objectid import ObjectId
from functools import wraps
from urllib.parse import unquote, quote
from datetime import datetime, timedelta
import math

# --- Environment Variables ---
MONGO_URI = os.environ.get("MONGO_URI", "mongodb+srv://mewayo8672:mewayo8672@cluster0.ozhvczp.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0")
TMDB_API_KEY = os.environ.get("TMDB_API_KEY", "7dc544d9253bccc3cfecc1c677f69819")
ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "Nahid")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "Nahid270270")
WEBSITE_NAME = os.environ.get("WEBSITE_NAME", "FreeMovieHub")

# --- Telegram Notification Variables (from Vercel Environment Variables) ---
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHANNEL_ID = os.environ.get("TELEGRAM_CHANNEL_ID")
WEBSITE_URL = os.environ.get("WEBSITE_URL") 

# --- Validate Environment Variables ---
if not all([MONGO_URI, TMDB_API_KEY, ADMIN_USERNAME, ADMIN_PASSWORD]):
    print("FATAL: One or more required environment variables are missing.")
    if os.environ.get('VERCEL') != '1':
        sys.exit(1)

# --- App Initialization ---
PLACEHOLDER_POSTER = "https://via.placeholder.com/400x600.png?text=Poster+Not+Found"
ITEMS_PER_PAGE = 20
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
    categories_collection = db["categories"]
    requests_collection = db["requests"]
    print("SUCCESS: Successfully connected to MongoDB!")

    if categories_collection.count_documents({}) == 0:
        default_categories = ["Bangla", "Hindi", "English", "18+ Adult", "Korean", "Dual Audio", "Bangla Dubbed", "Hindi Dubbed", "Indonesian", "Horror", "Action", "Thriller", "Anime", "Romance", "Trending"]
        categories_collection.insert_many([{"name": cat} for cat in default_categories])
        print("SUCCESS: Initialized default categories in the database.")

    try:
        movies.create_index("title")
        movies.create_index("type")
        movies.create_index("categories")
        movies.create_index("updated_at")
        movies.create_index("tmdb_id") # [NEW] TMDB ID-এর জন্য ইনডেক্স
        categories_collection.create_index("name", unique=True)
        requests_collection.create_index("status")
        print("SUCCESS: MongoDB indexes checked/created.")
    except Exception as e:
        print(f"WARNING: Could not create MongoDB indexes: {e}")

    print("INFO: Checking for documents missing 'updated_at' field for migration...")
    result = movies.update_many(
        {"updated_at": {"$exists": False}},
        [{"$set": {"updated_at": "$created_at"}}]
    )
    if result.modified_count > 0:
        print(f"SUCCESS: Migrated {result.modified_count} old documents to include 'updated_at' field.")
    else:
        print("INFO: All documents already have the 'updated_at' field.")

except Exception as e:
    print(f"FATAL: Error connecting to MongoDB: {e}.")
    if os.environ.get('VERCEL') != '1':
        sys.exit(1)

# --- Telegram Notification Function ---
def send_telegram_notification(movie_data, content_id, notification_type='new'):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHANNEL_ID or not WEBSITE_URL:
        print("INFO: Telegram bot token, channel ID, or website URL not configured. Skipping notification.")
        return

    try:
        movie_url = f"{WEBSITE_URL}/movie/{str(content_id)}"
        
        available_qualities = []
        if movie_data.get('links'):
            for link in movie_data['links']:
                if link.get('quality'):
                    available_qualities.append(link['quality'])
        if not available_qualities:
            available_qualities.append("BLU-RAY")
        
        quality_str = ", ".join(sorted(list(set(available_qualities))))
        language_str = movie_data.get('language', 'N/A')
        genres_list = movie_data.get('genres', [])
        genres_str = ", ".join(genres_list) if genres_list else "N/A"
        clean_url = WEBSITE_URL.replace('https://', '').replace('www.', '')

        if notification_type == 'update':
            caption_header = f"🔄 **UPDATED : {movie_data['title']}**\n"
        else:
            caption_header = f"🔥 **NEW ADDED : {movie_data['title']}**\n"
        
        caption = caption_header
        if language_str and not any(char.isdigit() for char in language_str):
             caption += f"**{language_str.upper()}**\n"

        caption += f"\n🎞️ Quality: **{quality_str}**"
        caption += f"\n🌐 Language: **{language_str}**"
        caption += f"\n🎭 Genres: **{genres_str}**"
        caption += f"\n\n🔗 Visit : **{clean_url}**"
        caption += f"\n⚠️ **অবশ্যই লিংকগুলো ক্রোম ব্রাউজারে ওপেন করবেন!!**"

        inline_keyboard = {"inline_keyboard": [[{"text": "📥👇 Download Now 👇📥", "url": movie_url}]]}
        api_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"
        payload = {'chat_id': TELEGRAM_CHANNEL_ID, 'photo': movie_data.get('poster', PLACEHOLDER_POSTER), 'caption': caption, 'parse_mode': 'Markdown', 'reply_markup': json.dumps(inline_keyboard)}
        
        response = requests.post(api_url, data=payload, timeout=15)
        response.raise_for_status()
        
        if response.json().get('ok'):
            print(f"SUCCESS: Telegram notification sent for '{movie_data['title']}' (Type: {notification_type}).")
        else:
            print(f"WARNING: Telegram API error: {response.json().get('description')}")
    except requests.exceptions.RequestException as e:
        print(f"ERROR: Failed to send Telegram notification: {e}")
    except Exception as e:
        print(f"ERROR: Unexpected error in send_telegram_notification: {e}")

# --- Custom Jinja Filter for Relative Time ---
def time_ago(obj_id):
    if not isinstance(obj_id, ObjectId): return ""
    post_time = obj_id.generation_time.replace(tzinfo=None)
    now = datetime.utcnow()
    diff = now - post_time
    seconds = diff.total_seconds()
    
    if seconds < 60: return "just now"
    elif seconds < 3600:
        minutes = int(seconds / 60)
        return f"{minutes} minute{'s' if minutes > 1 else ''} ago"
    elif seconds < 86400:
        hours = int(seconds / 3600)
        return f"{hours} hour{'s' if hours > 1 else ''} ago"
    else:
        days = int(seconds / 86400)
        return f"{days} day{'s' if days > 1 else ''} ago"

app.jinja_env.filters['time_ago'] = time_ago

@app.context_processor
def inject_globals():
    ad_settings = settings.find_one({"_id": "ad_config"})
    all_categories = [cat['name'] for cat in categories_collection.find().sort("name", 1)]
    
    category_icons = {
        "Bangla": "fa-film", "Hindi": "fa-film", "English": "fa-film",
        "18+ Adult": "fa-exclamation-circle", "Korean": "fa-tv", "Dual Audio": "fa-headphones",
        "Bangla Dubbed": "fa-microphone-alt", "Hindi Dubbed": "fa-microphone-alt", "Horror": "fa-ghost",
        "Action": "fa-bolt", "Thriller": "fa-knife-kitchen", "Anime": "fa-dragon", "Romance": "fa-heart",
        "Trending": "fa-fire", "ALL MOVIES": "fa-layer-group", "WEB SERIES & TV SHOWS": "fa-tv-alt", "HOME": "fa-home"
    }
    return dict(website_name=WEBSITE_NAME, ad_settings=ad_settings or {}, predefined_categories=all_categories, quote=quote, datetime=datetime, category_icons=category_icons)

# =========================================================================================
# === [START] HTML TEMPLATES ==============================================================
# =========================================================================================
# (index_html, detail_html, wait_page_html, request_html - কোনো পরিবর্তন নেই, তাই এখানে অন্তর্ভুক্ত করা হলো না)
index_html = """
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no" />
<title>{{ website_name }} - Your Entertainment Hub</title>
<link rel="icon" href="https://img.icons8.com/fluency/48/cinema-.png" type="image/png">
<meta name="description" content="Watch and download the latest movies and series on {{ website_name }}. Your ultimate entertainment hub.">
<meta name="keywords" content="movies, series, download, watch online, {{ website_name }}, bengali movies, hindi movies, english movies">
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin><link href="https://fonts.googleapis.com/css2?family=Poppins:wght@400;500;600;700&display=swap" rel="stylesheet">
<link rel="stylesheet" href="https://unpkg.com/swiper/swiper-bundle.min.css"/>
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.2.0/css/all.min.css">
{{ ad_settings.ad_header | safe }}
<style>
  :root {
    --primary-color: #E50914; --bg-color: #141414; --card-bg: #1a1a1a;
    --text-light: #ffffff; --text-dark: #a0a0a0; --nav-height: 60px;
    --cyan-accent: #00FFFF; --yellow-accent: #FFFF00; --trending-color: #F83D61;
    --type-color: #00E599; --new-color: #ffc107;
    --search-accent-color: #00bfff; /* Color for the new search bar */
  }
  @keyframes rgb-glow {
    0%   { border-color: #ff00de; box-shadow: 0 0 5px #ff00de, 0 0 10px #ff00de inset; }
    25%  { border-color: #00ffff; box-shadow: 0 0 7px #00ffff, 0 0 12px #00ffff inset; }
    50%  { border-color: #00ff7f; box-shadow: 0 0 5px #00ff7f, 0 0 10px #00ff7f inset; }
    75%  { border-color: #f83d61; box-shadow: 0 0 7px #f83d61, 0 0 12px #f83d61 inset; }
    100% { border-color: #ff00de; box-shadow: 0 0 5px #ff00de, 0 0 10px #ff00de inset; }
  }
  @keyframes pulse-glow {
    0%, 100% { color: var(--text-dark); text-shadow: none; }
    50% { color: var(--text-light); text-shadow: 0 0 10px var(--cyan-accent); }
  }
  html { box-sizing: border-box; } *, *:before, *:after { box-sizing: inherit; }
  body {font-family: 'Poppins', sans-serif;background-color: var(--bg-color);color: var(--text-light);overflow-x: hidden; padding-bottom: 70px;}
  a { text-decoration: none; color: inherit; } img { max-width: 100%; display: block; }
  .container { max-width: 1400px; margin: 0 auto; padding: 0 10px; }
  
  .main-header { position: fixed; top: 0; left: 0; width: 100%; height: var(--nav-height); display: flex; align-items: center; z-index: 1000; transition: background-color 0.3s ease; background-color: rgba(0,0,0,0.7); backdrop-filter: blur(5px); }
  .header-content { display: flex; justify-content: space-between; align-items: center; width: 100%; }
  .logo { font-size: 1.8rem; font-weight: 700; color: var(--primary-color); }
  .menu-toggle { display: block; font-size: 1.8rem; cursor: pointer; background: none; border: none; color: white; z-index: 1001;}
  
  .nav-grid-container { padding: 15px 0; }
  .nav-grid { display: flex; flex-wrap: wrap; justify-content: center; gap: 8px; }
  .nav-grid-item {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    color: white;
    padding: 6px 12px;
    border-radius: 6px;
    font-size: 0.75rem;
    font-weight: 500;
    text-transform: uppercase;
    text-decoration: none;
    transition: all 0.3s ease;
    background: linear-gradient(145deg, #d40a0a, #a00000);
    border: 1px solid #ff4b4b;
    box-shadow: 0 2px 8px -3px rgba(229, 9, 20, 0.6);
  }
  .nav-grid-item:hover {
    transform: translateY(-2px);
    box-shadow: 0 4px 12px -4px rgba(229, 9, 20, 0.9);
    filter: brightness(1.1);
  }
  .nav-grid-item i {
    margin-right: 6px;
    font-size: 1em;
    line-height: 1;
  }
  .icon-18 {
    font-family: sans-serif;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    border: 1.5px solid white;
    border-radius: 50%;
    width: 16px;
    height: 16px;
    font-size: 10px;
    line-height: 1;
    margin-right: 6px;
    font-weight: bold;
  }

  .home-search-section {
      padding: 10px 0 20px 0;
  }
  .home-search-form {
      display: flex;
      width: 100%;
      max-width: 800px;
      margin: 0 auto;
      border: 2px solid var(--search-accent-color);
      border-radius: 8px;
      overflow: hidden;
      background-color: var(--card-bg);
  }
  .home-search-input {
      flex-grow: 1;
      border: none;
      background-color: transparent;
      color: var(--text-light);
      padding: 12px 20px;
      font-size: 1rem;
      outline: none;
  }
  .home-search-input::placeholder {
      color: var(--text-dark);
  }
  .home-search-button {
      background-color: var(--search-accent-color);
      border: none;
      color: white;
      padding: 0 25px;
      cursor: pointer;
      font-size: 1.2rem;
      display: flex;
      align-items: center;
      justify-content: center;
      transition: background-color 0.2s ease;
  }
  .home-search-button:hover {
      filter: brightness(1.1);
  }

  @keyframes cyan-glow {
      0% { box-shadow: 0 0 15px 2px #00D1FF; } 50% { box-shadow: 0 0 25px 6px #00D1FF; } 100% { box-shadow: 0 0 15px 2px #00D1FF; }
  }
  .hero-slider-section { margin-bottom: 30px; }
  .hero-slider { width: 100%; aspect-ratio: 16 / 9; background-color: var(--card-bg); border-radius: 12px; overflow: hidden; animation: cyan-glow 5s infinite linear; }
  .hero-slider .swiper-slide { position: relative; display: block; }
  .hero-slider .hero-bg-img { position: absolute; top: 0; left: 0; width: 100%; height: 100%; object-fit: cover; z-index: 1; }
  .hero-slider .hero-slide-overlay { position: absolute; top: 0; left: 0; width: 100%; height: 100%; background: linear-gradient(to top, rgba(0,0,0,0.8) 0%, rgba(0,0,0,0.5) 40%, transparent 70%); z-index: 2; }
  .hero-slider .hero-slide-content { position: absolute; bottom: 0; left: 0; width: 100%; padding: 20px; z-index: 3; color: white; }
  .hero-slider .hero-title { font-size: 1.5rem; font-weight: 700; margin: 0 0 5px 0; text-shadow: 2px 2px 4px rgba(0,0,0,0.7); }
  .hero-slider .hero-meta { font-size: 0.9rem; margin: 0; color: var(--text-dark); }
  .hero-slide-content .hero-type-tag { position: absolute; bottom: 20px; right: 20px; background: linear-gradient(45deg, #00FFA3, #00D1FF); color: black; padding: 5px 15px; border-radius: 50px; font-size: 0.75rem; font-weight: 700; z-index: 4; text-transform: uppercase; box-shadow: 0 4px 10px rgba(0, 255, 163, 0.2); }
  .hero-slider .swiper-pagination { position: absolute; bottom: 10px !important; left: 20px !important; width: auto !important; }
  .hero-slider .swiper-pagination-bullet { background: rgba(255, 255, 255, 0.5); width: 8px; height: 8px; opacity: 0.7; transition: all 0.2s ease; }
  .hero-slider .swiper-pagination-bullet-active { background: var(--text-light); width: 24px; border-radius: 5px; opacity: 1; }

  .category-section { margin: 30px 0; }
  .category-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; }
  .category-title { font-size: 1.5rem; font-weight: 600; display: inline-block; padding: 8px 20px; background-color: rgba(26, 26, 26, 0.8); border: 2px solid; border-radius: 50px; animation: rgb-glow 4s linear infinite; backdrop-filter: blur(3px); }
  .view-all-link { font-size: 0.9rem; color: var(--text-dark); font-weight: 500; padding: 6px 15px; border-radius: 20px; background-color: #222; transition: all 0.3s ease; animation: pulse-glow 2.5s ease-in-out infinite; }
  .category-grid, .full-page-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 15px; }

  .movie-card {
    display: flex;
    flex-direction: column;
    border-radius: 8px;
    overflow: hidden;
    background-color: var(--card-bg);
    border: 2px solid transparent;
    transition: transform 0.2s ease, box-shadow 0.2s ease;
  }
  .movie-card:hover {
      transform: translateY(-5px);
      box-shadow: 0 8px 20px rgba(0, 255, 255, 0.2);
  }
  .poster-wrapper { position: relative; }
  .movie-poster { width: 100%; aspect-ratio: 2 / 3; object-fit: cover; display: block; }
  .card-info { padding: 10px; background-color: var(--card-bg); }
  .card-title {
    font-size: 0.9rem; font-weight: 500; color: var(--text-light);
    margin: 0 0 5px 0; line-height: 1.4; min-height: 2.8em;
    display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden;
  }
  
  .card-meta { 
    font-size: 0.75rem; 
    color: var(--text-dark); 
    display: flex; 
    align-items: center; 
    justify-content: space-between;
  }
  .card-meta span {
      display: flex;
      align-items: center;
      gap: 5px;
  }
  .card-meta i { 
      color: var(--cyan-accent); 
  }

  .type-tag, .language-tag {
    position: absolute; color: white; padding: 2px 8px; font-size: 0.65rem; font-weight: 600; z-index: 2; text-transform: uppercase; border-radius: 4px;
  }
  .language-tag { padding: 2px 6px; font-size: 0.6rem; top: 8px; right: 8px; background-color: rgba(0,0,0,0.6); }
  .type-tag { bottom: 8px; right: 8px; background-color: var(--type-color); }
  .new-badge {
    position: absolute; top: 0; left: 0; background-color: var(--primary-color);
    color: white; padding: 4px 12px 4px 8px; font-size: 0.7rem; font-weight: 700;
    z-index: 3; clip-path: polygon(0 0, 100% 0, 85% 100%, 0 100%);
  }

  .full-page-grid-container { padding: 80px 10px 20px; }
  .full-page-grid-title { font-size: 1.8rem; font-weight: 700; margin-bottom: 20px; text-align: center; }
  .main-footer { background-color: #111; padding: 20px; text-align: center; color: var(--text-dark); margin-top: 30px; font-size: 0.8rem; }
  .ad-container { margin: 20px auto; width: 100%; max-width: 100%; display: flex; justify-content: center; align-items: center; overflow: hidden; min-height: 50px; text-align: center; }
  .ad-container > * { max-width: 100% !important; }
  .mobile-nav-menu {position: fixed;top: 0;left: 0;width: 100%;height: 100%;background-color: var(--bg-color);z-index: 9999;display: flex;flex-direction: column;align-items: center;justify-content: center;transform: translateX(-100%);transition: transform 0.3s ease-in-out;}
  .mobile-nav-menu.active {transform: translateX(0);}
  .mobile-nav-menu .close-btn {position: absolute;top: 20px;right: 20px;font-size: 2.5rem;color: white;background: none;border: none;cursor: pointer;}
  .mobile-links {display: flex;flex-direction: column;text-align: center;gap: 25px;}
  .mobile-links a {font-size: 1.5rem;font-weight: 500;color: var(--text-light);transition: color 0.2s;}
  .mobile-links a:hover {color: var(--primary-color);}
  .mobile-links hr {width: 50%;border-color: #333;margin: 10px auto;}
  .bottom-nav { display: flex; position: fixed; bottom: 0; left: 0; right: 0; height: 65px; background-color: #181818; box-shadow: 0 -2px 10px rgba(0,0,0,0.5); z-index: 1000; justify-content: space-around; align-items: center; padding-top: 5px; }
  .bottom-nav .nav-item { display: flex; flex-direction: column; align-items: center; justify-content: center; color: var(--text-dark); background: none; border: none; font-size: 12px; flex-grow: 1; font-weight: 500; }
  .bottom-nav .nav-item i { font-size: 22px; margin-bottom: 5px; }
  .bottom-nav .nav-item.active, .bottom-nav .nav-item:hover { color: var(--primary-color); }
  .search-overlay { position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.95); z-index: 10000; display: none; flex-direction: column; padding: 20px; }
  .search-overlay.active { display: flex; }
  .search-container { width: 100%; max-width: 800px; margin: 0 auto; }
  .close-search-btn { position: absolute; top: 20px; right: 20px; font-size: 2.5rem; color: white; background: none; border: none; cursor: pointer; }
  #search-input-live { width: 100%; padding: 15px; font-size: 1.2rem; border-radius: 8px; border: 2px solid var(--primary-color); background: var(--card-bg); color: white; margin-top: 60px; }
  #search-results-live { margin-top: 20px; max-height: calc(100vh - 150px); overflow-y: auto; display: grid; grid-template-columns: repeat(auto-fill, minmax(120px, 1fr)); gap: 15px; }
  .search-result-item { color: white; text-align: center; }
  .search-result-item img { width: 100%; aspect-ratio: 2 / 3; object-fit: cover; border-radius: 5px; margin-bottom: 5px; }
  .pagination { display: flex; justify-content: center; align-items: center; gap: 10px; margin: 30px 0; }
  .pagination a, .pagination span { padding: 8px 15px; border-radius: 5px; background-color: var(--card-bg); color: var(--text-dark); font-weight: 500; }
  .pagination a:hover { background-color: #333; }
  .pagination .current { background-color: var(--primary-color); color: white; }

  @media (min-width: 769px) { 
    .container { padding: 0 40px; } .main-header { padding: 0 40px; }
    body { padding-bottom: 0; } .bottom-nav { display: none; }
    .hero-slider .hero-title { font-size: 2.2rem; }
    .hero-slider .hero-slide-content { padding: 40px; }
    .category-grid { grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); }
    .full-page-grid { grid-template-columns: repeat(auto-fill, minmax(180px, 1fr)); }
    .full-page-grid-container { padding: 120px 40px 20px; }
  }
</style>
</head>
<body>
{{ ad_settings.ad_body_top | safe }}
<header class="main-header">
    <div class="container header-content">
        <a href="{{ url_for('home') }}" class="logo">{{ website_name }}</a>
        <button class="menu-toggle"><i class="fas fa-bars"></i></button>
    </div>
</header>
<div class="mobile-nav-menu">
    <button class="close-btn">&times;</button>
    <div class="mobile-links">
        <a href="{{ url_for('home') }}">Home</a>
        <a href="{{ url_for('all_movies') }}">All Movies</a>
        <a href="{{ url_for('all_series') }}">All Series</a>
        <a href="{{ url_for('request_content') }}">Request Content</a>
        <hr>
        {% for cat in predefined_categories %}<a href="{{ url_for('movies_by_category', name=cat) }}">{{ cat }}</a>{% endfor %}
    </div>
</div>
<main>
  {% macro render_movie_card(m) %}
    <a href="{{ url_for('movie_detail', movie_id=m._id) }}" class="movie-card">
      <div class="poster-wrapper">
        {% if (datetime.utcnow() - m._id.generation_time.replace(tzinfo=None)).days < 7 %}
            <span class="new-badge">NEW</span>
        {% endif %}
        {% if m.language %}<span class="language-tag">{{ m.language }}</span>{% endif %}
        <img class="movie-poster" loading="lazy" src="{{ m.poster or 'https://via.placeholder.com/400x600.png?text=No+Image' }}" alt="{{ m.title }}">
        <span class="type-tag">{{ m.type | title }}</span>
      </div>
      <div class="card-info">
        <h4 class="card-title">
          {{ m.title }}
          {% if m.release_date %} ({{ m.release_date.split('-')[0] }}){% endif %}
        </h4>
        <p class="card-meta">
          <span><i class="fas fa-clock"></i> {{ m._id | time_ago }}</span>
          <span><i class="fas fa-eye"></i> {{ '{:,.0f}'.format(m.view_count or 0) }}</span>
        </p>
      </div>
    </a>
  {% endmacro %}

  {% if is_full_page_list %}
    <div class="full-page-grid-container">
        <h2 class="full-page-grid-title">{{ query }}</h2>
        {% if movies|length == 0 %}<p style="text-align:center;">No content found.</p>
        {% else %}
        <div class="full-page-grid">{% for m in movies %}{{ render_movie_card(m) }}{% endfor %}</div>
        {% if pagination and pagination.total_pages > 1 %}
        <div class="pagination">
            {% if pagination.has_prev %}<a href="{{ url_for(request.endpoint, page=pagination.prev_num, name=query if 'category' in request.endpoint else None) }}">&laquo; Prev</a>{% endif %}
            <span class="current">Page {{ pagination.page }} of {{ pagination.total_pages }}</span>
            {% if pagination.has_next %}<a href="{{ url_for(request.endpoint, page=pagination.next_num, name=query if 'category' in request.endpoint else None) }}">Next &raquo;</a>{% endif %}
        </div>
        {% endif %}
        {% endif %}
    </div>
  {% else %}
    <div style="height: var(--nav-height);"></div>
    
    <section class="nav-grid-container container">
        <div class="nav-grid">
            <a href="{{ url_for('home') }}" class="nav-grid-item">
                <i class="fas {{ category_icons.get('HOME', 'fa-tag') }}"></i> HOME
            </a>
            {% for cat in predefined_categories %}
                <a href="{{ url_for('movies_by_category', name=cat) }}" class="nav-grid-item">
                    {% if '18+' in cat %}
                        <span class="icon-18">18</span>
                    {% else %}
                        <i class="fas {{ category_icons.get(cat, 'fa-tag') }}"></i>
                    {% endif %}
                    {{ cat }}
                </a>
            {% endfor %}
            <a href="{{ url_for('all_movies') }}" class="nav-grid-item">
                <i class="fas {{ category_icons.get('ALL MOVIES', 'fa-tag') }}"></i> ALL MOVIES
            </a>
            <a href="{{ url_for('all_series') }}" class="nav-grid-item">
                <i class="fas {{ category_icons.get('WEB SERIES & TV SHOWS', 'fa-tag') }}"></i> WEB SERIES & TV SHOWS
            </a>
        </div>
    </section>

    <section class="home-search-section container">
        <form action="{{ url_for('home') }}" method="get" class="home-search-form">
            <input type="text" name="q" class="home-search-input" placeholder="সার্চ করে খুঁজে নিন আপনার পছন্দের ...">
            <button type="submit" class="home-search-button" aria-label="Search">
                <i class="fas fa-search"></i>
            </button>
        </form>
    </section>

    {% if slider_content %}
    <section class="hero-slider-section container">
        <div class="swiper hero-slider">
            <div class="swiper-wrapper">
                {% for item in slider_content %}
                <div class="swiper-slide">
                    <a href="{{ url_for('movie_detail', movie_id=item._id) }}">
                        <img src="{{ item.backdrop or item.poster }}" class="hero-bg-img" alt="{{ item.title }}">
                        <div class="hero-slide-overlay"></div>
                        <div class="hero-slide-content">
                            <h2 class="hero-title">{{ item.title }}</h2>
                            <p class="hero-meta">
                                {% if item.release_date %}{{ item.release_date.split('-')[0] }}{% endif %}
                            </p>
                            <span class="hero-type-tag">{{ item.type | title }}</span>
                        </div>
                    </a>
                </div>
                {% endfor %}
            </div>
            <div class="swiper-pagination"></div>
        </div>
    </section>
    {% endif %}

    <div class="container">
      {% macro render_grid_section(title, movies_list, cat_name) %}
          {% if movies_list %}
          <section class="category-section">
              <div class="category-header">
                  <h2 class="category-title">{{ title }}</h2>
                  <a href="{{ url_for('movies_by_category', name=cat_name) }}" class="view-all-link">View All &rarr;</a>
              </div>
              <div class="category-grid">
                  {% for m in movies_list %}
                      {{ render_movie_card(m) }}
                  {% endfor %}
              </div>
          </section>
          {% endif %}
      {% endmacro %}
      
      {% if categorized_content['Trending'] %}
      {{ render_grid_section('Trending Now', categorized_content['Trending'], 'Trending') }}
      {% endif %}

      {% if latest_content %}
      <section class="category-section">
          <div class="category-header">
              <h2 class="category-title">Recently Added</h2>
              <a href="{{ url_for('all_movies') }}" class="view-all-link">View All &rarr;</a>
          </div>
          <div class="category-grid">
              {% for m in latest_content %}
                  {{ render_movie_card(m) }}
              {% endfor %}
          </div>
      </section>
      {% endif %}

      {% if ad_settings.ad_list_page %}<div class="ad-container">{{ ad_settings.ad_list_page | safe }}</div>{% endif %}
      
      {% for cat_name, movies_list in categorized_content.items() %}
          {% if cat_name != 'Trending' %}
            {{ render_grid_section(cat_name, movies_list, cat_name) }}
          {% endif %}
      {% endfor %}
    </div>
  {% endif %}
</main>
<footer class="main-footer">
    <p>&copy; 2024 {{ website_name }}. All Rights Reserved.</p>
</footer>
<nav class="bottom-nav">
  <a href="{{ url_for('home') }}" class="nav-item active"><i class="fas fa-home"></i><span>Home</span></a>
  <a href="{{ url_for('all_movies') }}" class="nav-item"><i class="fas fa-layer-group"></i><span>Content</span></a>
  <a href="{{ url_for('request_content') }}" class="nav-item"><i class="fas fa-plus-circle"></i><span>Request</span></a>
  <button id="live-search-btn" class="nav-item"><i class="fas fa-search"></i><span>Search</span></button>
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
    window.addEventListener('scroll', () => { window.scrollY > 10 ? header.classList.add('scrolled') : header.classList.remove('scrolled'); });
    const menuToggle = document.querySelector('.menu-toggle');
    const mobileMenu = document.querySelector('.mobile-nav-menu');
    const closeBtn = document.querySelector('.close-btn');
    if (menuToggle && mobileMenu && closeBtn) {
        menuToggle.addEventListener('click', () => { mobileMenu.classList.add('active'); });
        closeBtn.addEventListener('click', () => { mobileMenu.classList.remove('active'); });
        document.querySelectorAll('.mobile-links a').forEach(link => { link.addEventListener('click', () => { mobileMenu.classList.remove('active'); }); });
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
                fetch(`/api/search?q=${encodeURIComponent(query)}`).then(response => response.json()).then(data => {
                    let html = '';
                    if (data.length > 0) {
                        data.forEach(item => { html += `<a href="/movie/${item._id}" class="search-result-item"><img src="${item.poster}" alt="${item.title}"><span>${item.title}</span></a>`; });
                    } else { html = '<p style="color: #555; text-align: center;">No results found.</p>'; }
                    searchResultsLive.innerHTML = html;
                });
            } else { searchResultsLive.innerHTML = '<p style="color: #555; text-align: center;">Start typing to see results</p>'; }
        }, 300);
    });
    new Swiper('.hero-slider', {
        loop: true, autoplay: { delay: 5000, disableOnInteraction: false },
        pagination: { el: '.swiper-pagination', clickable: true },
        effect: 'fade', fadeEffect: { crossFade: true },
    });
</script>
{{ ad_settings.ad_footer | safe }}
</body></html>
"""
detail_html = """
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no" />
<title>{{ movie.title if movie else "Content Not Found" }} - {{ website_name }}</title>
<link rel="icon" href="https://img.icons8.com/fluency/48/cinema-.png" type="image/png">
<meta name="description" content="{{ movie.overview|striptags|truncate(160) }}">
<meta name="keywords" content="{{ movie.title }}, movie details, download {{ movie.title }}, {{ website_name }}">
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin><link href="https://fonts.googleapis.com/css2?family=Poppins:wght@300;400;500;600;700&display=swap" rel="stylesheet">
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.2.0/css/all.min.css">
<link rel="stylesheet" href="https://unpkg.com/swiper/swiper-bundle.min.css"/>
{{ ad_settings.ad_header | safe }}
<style>
  :root {--primary-color: #E50914; --watch-color: #007bff; --bg-color: #000000;--card-bg: #1a1a1a;--text-light: #ffffff;--text-dark: #a0a0a0;}
  html { box-sizing: border-box; } *, *:before, *:after { box-sizing: inherit; }
  body { font-family: 'Poppins', sans-serif; background-color: var(--bg-color); color: var(--text-light); overflow-x: hidden;}
  a { text-decoration: none; color: inherit; }
  .container { max-width: 1200px; margin: 0 auto; padding: 0 15px; }
  .detail-hero { position: relative; padding: 100px 0 50px; min-height: 60vh; display: flex; align-items: center; }
  .hero-background { position: absolute; top: 0; left: 0; width: 100%; height: 100%; object-fit: cover; filter: blur(15px) brightness(0.3); transform: scale(1.1); }
  .detail-hero::after { content: ''; position: absolute; top: 0; left: 0; width: 100%; height: 100%; background: linear-gradient(to top, var(--bg-color) 0%, rgba(12,12,12,0.7) 40%, transparent 100%); }
  .detail-content { position: relative; z-index: 2; display: flex; flex-direction: column; align-items: center; text-align: center; gap: 20px; }
  .detail-poster { width: 60%; max-width: 250px; height: auto; flex-shrink: 0; border-radius: 12px; object-fit: cover; box-shadow: 0 10px 30px rgba(0,0,0,0.5); }
  .detail-info { max-width: 700px; }
  .detail-title { font-size: 2rem; font-weight: 700; line-height: 1.2; margin-bottom: 15px; }
  .detail-meta { display: flex; flex-wrap: wrap; gap: 10px 20px; color: var(--text-dark); margin-bottom: 20px; font-size: 0.9rem; justify-content: center;}
  .meta-item { display: flex; align-items: center; gap: 8px; }
  .meta-item.rating { color: #f5c518; font-weight: 600; }
  .detail-overview { font-size: 1rem; line-height: 1.7; color: var(--text-dark); margin-bottom: 30px; }
  .action-btn { display: inline-flex; align-items: center; justify-content: center; gap: 10px; padding: 12px 25px; border-radius: 50px; font-weight: 600; transition: all 0.2s ease; text-align: center; }
  .btn-download { background-color: var(--primary-color); } .btn-download:hover { transform: scale(1.05); }
  .btn-watch { background-color: var(--watch-color); } .btn-watch:hover { transform: scale(1.05); }
  .tabs-container { margin: 40px 0; }
  .tabs-nav { display: flex; flex-wrap: wrap; border-bottom: 1px solid #333; justify-content: center; }
  .tab-link { padding: 12px 15px; cursor: pointer; font-weight: 500; color: var(--text-dark); position: relative; font-size: 0.9rem;}
  .tab-link.active { color: var(--text-light); }
  .tab-link.active::after { content: ''; position: absolute; bottom: -1px; left: 0; width: 100%; height: 2px; background-color: var(--primary-color); }
  .tabs-content { padding: 30px 0; }
  .tab-pane { display: none; }
  .tab-pane.active { display: block; }
  .link-group { margin-bottom: 30px; text-align: center; border-bottom: 1px solid #222; padding-bottom: 30px;}
  .link-group:last-child { border-bottom: none; }
  .link-group h3 { font-size: 1.2rem; font-weight: 500; margin-bottom: 20px; }
  .link-buttons { display: inline-flex; flex-wrap: wrap; gap: 15px; justify-content: center;}
  .quality-group { margin-bottom: 20px; }
  .quality-group h4 { margin-bottom: 10px; color: var(--text-dark); }
  .episode-list { display: flex; flex-direction: column; gap: 10px; }
  .episode-item { display: flex; flex-direction: column; gap: 10px; align-items: flex-start; background-color: var(--card-bg); padding: 15px; border-radius: 8px; }
  .episode-name { font-weight: 500; }
  .ad-container { margin: 20px auto; width: 100%; max-width: 100%; display: flex; justify-content: center; align-items: center; overflow: hidden; min-height: 50px; text-align: center; }
  .ad-container > * { max-width: 100% !important; }
  .category-section { margin: 50px 0; }
  .category-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; }
  .category-title { font-size: 1.5rem; font-weight: 600; }
  .movie-carousel .swiper-slide { width: 150px; }
  .movie-card { display: block; position: relative; }
  .movie-poster { width: 100%; aspect-ratio: 2 / 3; object-fit: cover; border-radius: 8px; margin-bottom: 10px; }
  .card-title { font-size: 0.9rem; font-weight: 500; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .card-meta { font-size: 0.8rem; color: var(--text-dark); }
  .swiper-button-next, .swiper-button-prev { color: var(--text-light); display: none; }

  .screenshots-section { margin: 40px 0; }
  .screenshots-section h2 { font-size: 1.5rem; font-weight: 600; margin-bottom: 20px; display: flex; align-items: center; gap: 10px; }
  .gallery-top { border-radius: 10px; margin-bottom: 10px; background: #111; }
  .gallery-top .swiper-slide { background-size: cover; background-position: center; }
  .gallery-top .swiper-slide img { display: block; width: 100%; height: auto; object-fit: contain; }
  .gallery-thumbs { height: 100px; }
  .gallery-thumbs .swiper-slide { width: 25%; height: 100%; opacity: 0.5; transition: opacity 0.3s; }
  .gallery-thumbs .swiper-slide-thumb-active { opacity: 1; border: 2px solid var(--primary-color); border-radius: 5px; }
  .gallery-thumbs .swiper-slide img { display: block; width: 100%; height: 100%; object-fit: cover; border-radius: 5px; }

  @media (min-width: 768px) {
    .container { padding: 0 40px; }
    .detail-hero { padding: 120px 0 60px; }
    .detail-content { flex-direction: row; text-align: left; }
    .detail-poster { width: 300px; height: 450px; }
    .detail-title { font-size: 3rem; }
    .detail-meta { justify-content: flex-start; }
    .tabs-nav { justify-content: flex-start; }
    .episode-item { flex-direction: row; justify-content: space-between; align-items: center; }
    .movie-carousel .swiper-slide { width: 220px; }
    .swiper-button-next, .swiper-button-prev { display: flex; }
    .gallery-thumbs { height: 150px; }
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
        {% set episode_seasons = movie.episodes | map(attribute='season') | list if movie.episodes else [] %}
        {% set pack_seasons = movie.season_packs | map(attribute='season_number') | list if movie.season_packs else [] %}
        {% set all_seasons = (episode_seasons + pack_seasons) | unique | sort %}
        <nav class="tabs-nav">
            {% if movie.type == 'movie' %}
                <div class="tab-link active" data-tab="downloads"><i class="fas fa-download"></i> Download Links</div>
            {% elif all_seasons %}
                {% for season_num in all_seasons %}
                    <div class="tab-link {% if loop.first %}active{% endif %}" data-tab="season-{{ season_num }}">Season {{ season_num }}</div>
                {% endfor %}
            {% else %}
                 <div class="tab-link active" data-tab="no-links">Links</div>
            {% endif %}
        </nav>
        <div class="tabs-content">
            {% if movie.type == 'movie' %}
            <div class="tab-pane active" id="downloads">
                {% if ad_settings.ad_detail_page %}<div class="ad-container">{{ ad_settings.ad_detail_page | safe }}</div>{% endif %}
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
                {% endif %}
                {% if movie.manual_links %}
                <div class="link-group">
                    <h3>Custom Download Links</h3>
                    <div class="link-buttons">
                        {% for link in movie.manual_links %}
                            <a href="{{ url_for('wait_page', target=quote(link.url)) }}" class="action-btn btn-download">{{ link.name }}</a>
                        {% endfor %}
                    </div>
                </div>
                {% endif %}
                {% if not movie.links and not movie.manual_links %}
                    <p style="text-align:center;">No links available yet.</p>
                {% endif %}
            </div>
            {% elif all_seasons %}
                {% for season_num in all_seasons %}
                <div class="tab-pane {% if loop.first %}active{% endif %}" id="season-{{ season_num }}">
                    {% set season_pack = (movie.season_packs | selectattr('season_number', 'equalto', season_num) | first) if movie.season_packs else None %}
                    {% if loop.first and movie.manual_links %}
                    <div class="link-group">
                        <h3>Custom Download Links</h3>
                        <div class="link-buttons">
                            {% for link in movie.manual_links %}
                                <a href="{{ url_for('wait_page', target=quote(link.url)) }}" class="action-btn btn-download">{{ link.name }}</a>
                            {% endfor %}
                        </div>
                    </div>
                    {% endif %}
                    {% if season_pack and (season_pack.watch_link or season_pack.download_link) %}
                    <div class="link-group">
                        <h3>Complete Season {{ season_num }} Links</h3>
                        <div class="link-buttons">
                            {% if season_pack.watch_link %}
                                <a href="{{ url_for('wait_page', target=quote(season_pack.watch_link)) }}" class="action-btn btn-watch"><i class="fas fa-play-circle"></i> Watch All Episodes</a>
                            {% endif %}
                            {% if season_pack.download_link %}
                                <a href="{{ url_for('wait_page', target=quote(season_pack.download_link)) }}" class="action-btn btn-download"><i class="fas fa-cloud-download-alt"></i> Download All Episodes</a>
                            {% endif %}
                        </div>
                    </div>
                    {% endif %}
                    {% set episodes_for_season = movie.episodes | selectattr('season', 'equalto', season_num) | list %}
                    {% if episodes_for_season %}
                    <div class="episode-list">
                        {% for ep in episodes_for_season | sort(attribute='episode_number') %}
                        <div class="episode-item">
                            <span class="episode-name"><i class="fas fa-play-circle"></i> Episode {{ ep.episode_number }} {% if ep.title %}- {{ep.title}}{% endif %}</span>
                            {% if ep.watch_link %}<a href="{{ url_for('wait_page', target=quote(ep.watch_link)) }}" class="action-btn btn-download">Download / Watch</a>{% endif %}
                        </div>
                        {% endfor %}
                    </div>
                    {% elif not season_pack and not (loop.first and movie.manual_links) %}
                        <p style="text-align:center;">No links or episodes available for this season yet.</p>
                    {% endif %}
                </div>
                {% endfor %}
            {% else %}
                <div class="tab-pane active" id="no-links">
                    {% if movie.manual_links %}
                    <div class="link-group">
                        <h3>Custom Download Links</h3>
                        <div class="link-buttons">
                            {% for link in movie.manual_links %}
                                <a href="{{ url_for('wait_page', target=quote(link.url)) }}" class="action-btn btn-download">{{ link.name }}</a>
                            {% endfor %}
                        </div>
                    </div>
                    {% else %}
                    <p style="text-align:center;">No links or episodes available yet.</p>
                    {% endif %}
                </div>
            {% endif %}
        </div>
    </div>
    
    {% if movie.screenshots %}
    <section class="screenshots-section">
        <h2><i class="fas fa-images"></i> Screenshots</h2>
        <div class="swiper gallery-top">
            <div class="swiper-wrapper">
                {% for ss in movie.screenshots %}
                <div class="swiper-slide">
                    <img src="{{ ss }}" loading="lazy" alt="Screenshot of {{ movie.title }}">
                </div>
                {% endfor %}
            </div>
            <div class="swiper-button-next"></div>
            <div class="swiper-button-prev"></div>
        </div>
        <div class="swiper gallery-thumbs">
            <div class="swiper-wrapper">
                {% for ss in movie.screenshots %}
                <div class="swiper-slide">
                    <img src="{{ ss }}" loading="lazy" alt="Thumbnail of {{ movie.title }}">
                </div>
                {% endfor %}
            </div>
        </div>
    </section>
    {% endif %}

    {% if related_content %}
    <section class="category-section">
        <div class="category-header">
            <h2 class="category-title">You Might Also Like</h2>
        </div>
        <div class="swiper movie-carousel">
            <div class="swiper-wrapper">
                {% for m in related_content %}
                <div class="swiper-slide">
                    <a href="{{ url_for('movie_detail', movie_id=m._id) }}" class="movie-card">
                        <img class="movie-poster" loading="lazy" src="{{ m.poster or 'https://via.placeholder.com/400x600.png?text=No+Image' }}" alt="{{ m.title }}">
                        <h4 class="card-title">{{ m.title }}</h4>
                        <p class="card-meta">{{ m.release_date.split('-')[0] if m.release_date else '' }}</p>
                    </a>
                </div>
                {% endfor %}
            </div>
            <div class="swiper-button-next"></div><div class="swiper-button-prev"></div>
        </div>
    </section>
    {% endif %}
</div>
{% else %}<div style="display:flex; justify-content:center; align-items:center; height:100vh;"><h2>Content not found.</h2></div>{% endif %}
<script src="https://unpkg.com/swiper/swiper-bundle.min.js"></script>
<script>
    const tabLinks = document.querySelectorAll('.tab-link'), tabPanes = document.querySelectorAll('.tab-pane');
    tabLinks.forEach(link => { link.addEventListener('click', () => {
        const tabId = link.getAttribute('data-tab');
        tabLinks.forEach(item => item.classList.remove('active'));
        tabPanes.forEach(pane => pane.classList.remove('active'));
        link.classList.add('active');
        const targetPane = document.getElementById(tabId);
        if(targetPane) targetPane.classList.add('active');
    }); });

    new Swiper('.movie-carousel', {
        slidesPerView: 'auto',
        spaceBetween: 15,
        navigation: {
            nextEl: '.swiper-button-next',
            prevEl: '.swiper-button-prev',
        }
    });

    if (document.querySelector('.gallery-thumbs')) {
        var galleryThumbs = new Swiper('.gallery-thumbs', {
            spaceBetween: 10,
            slidesPerView: 4,
            freeMode: true,
            watchSlidesVisibility: true,
            watchSlidesProgress: true,
        });
        var galleryTop = new Swiper('.gallery-top', {
            spaceBetween: 10,
            navigation: {
                nextEl: '.swiper-button-next',
                prevEl: '.swiper-button-prev',
            },
            thumbs: {
                swiper: galleryThumbs
            }
        });
    }
</script>
{{ ad_settings.ad_footer | safe }}
</body></html>
"""
wait_page_html = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>Generating Link... - {{ website_name }}</title>
    <link rel="icon" href="https://img.icons8.com/fluency/48/cinema-.png" type="image/png">
    <meta name="robots" content="noindex, nofollow">
    <link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin><link href="https://fonts.googleapis.com/css2?family=Poppins:wght@400;500;700&display=swap" rel="stylesheet">
    {{ ad_settings.ad_header | safe }}
    <style>
        :root {--primary-color: #E50914; --bg-color: #000000; --text-light: #ffffff; --text-dark: #a0a0a0;}
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
request_html = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>Request Content - {{ website_name }}</title>
    <link rel="icon" href="https://img.icons8.com/fluency/48/cinema-.png" type="image/png">
    <meta name="robots" content="noindex, nofollow">
    <link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin><link href="https://fonts.googleapis.com/css2?family=Poppins:wght@400;500;700&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.2.0/css/all.min.css">
    {{ ad_settings.ad_header | safe }}
    <style>
        :root { --primary-color: #E50914; --bg-color: #000000; --card-bg: #1a1a1a; --text-light: #ffffff; --text-dark: #a0a0a0; }
        body { font-family: 'Poppins', sans-serif; background-color: var(--bg-color); color: var(--text-light); display: flex; flex-direction: column; align-items: center; min-height: 100vh; margin: 0; padding: 20px; }
        .container { max-width: 600px; width: 100%; padding: 0 15px; }
        .back-link { align-self: flex-start; margin-bottom: 20px; color: var(--text-dark); text-decoration: none; font-size: 0.9rem;}
        .request-container { background-color: var(--card-bg); padding: 30px; border-radius: 12px; box-shadow: 0 10px 30px rgba(0,0,0,0.5); }
        h1 { font-size: 2rem; color: var(--primary-color); margin-bottom: 10px; text-align: center; }
        p { text-align: center; color: var(--text-dark); margin-bottom: 30px; }
        .form-group { margin-bottom: 20px; }
        label { display: block; margin-bottom: 8px; font-weight: 500; }
        input, textarea { width: 100%; padding: 12px; border-radius: 5px; border: 1px solid #333; font-size: 1rem; background: #222; color: var(--text-light); box-sizing: border-box; }
        textarea { resize: vertical; min-height: 80px; }
        .btn-submit { display: block; width: 100%; text-decoration: none; color: white; font-weight: 600; cursor: pointer; border: none; padding: 14px; border-radius: 5px; font-size: 1.1rem; background-color: var(--primary-color); transition: background-color 0.2s; }
        .btn-submit:hover { background-color: #B20710; }
        .flash-message { padding: 15px; border-radius: 5px; margin-bottom: 20px; text-align: center; }
        .flash-success { background-color: #28a745; color: white; }
        .flash-error { background-color: #dc3545; color: white; }
    </style>
</head>
<body>
    {{ ad_settings.ad_body_top | safe }}
    <div class="container">
        <a href="{{ url_for('home') }}" class="back-link"><i class="fas fa-arrow-left"></i> Back to Home</a>
        <div class="request-container">
            <h1>Request Content</h1>
            <p>Can't find what you're looking for? Let us know!</p>
            {% with messages = get_flashed_messages(with_categories=true) %}
                {% if messages %}
                    {% for category, message in messages %}
                        <div class="flash-message flash-{{ category }}">{{ message }}</div>
                    {% endfor %}
                {% endif %}
            {% endwith %}
            <form method="post">
                <div class="form-group">
                    <label for="content_name">Movie/Series Name</label>
                    <input type="text" id="content_name" name="content_name" required>
                </div>
                <div class="form-group">
                    <label for="extra_info">Additional Information (Optional)</label>
                    <textarea id="extra_info" name="extra_info" placeholder="e.g., Release year, language, specific season..."></textarea>
                </div>
                <button type="submit" class="btn-submit">Submit Request</button>
            </form>
        </div>
    </div>
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
        .admin-container { max-width: 1200px; margin: 20px auto; }
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
        .btn-edit { background: #007bff; } .btn-success { background: #28a745; }
        .table-container { display: block; overflow-x: auto; white-space: nowrap; }
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
        .season-pack-item { display: grid; grid-template-columns: 100px 1fr 1fr; gap: 10px; align-items: flex-end; }
        .manage-content-header { display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 20px; margin-bottom: 20px; }
        .search-form { display: flex; gap: 10px; flex-grow: 1; max-width: 500px; }
        .search-form input { flex-grow: 1; }
        .search-form .btn { padding: 12px 20px; }
        .dashboard-stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 20px; margin-bottom: 30px; }
        .stat-card { background: var(--dark-gray); padding: 20px; border-radius: 8px; text-align: center; border-left: 5px solid var(--netflix-red); }
        .stat-card h3 { margin: 0 0 10px; font-size: 1.2rem; color: var(--text-light); }
        .stat-card p { font-size: 2.5rem; font-weight: 700; margin: 0; color: var(--netflix-red); }
        .category-management { display: flex; flex-wrap: wrap; gap: 30px; align-items: flex-start; }
        .category-list { flex: 1; min-width: 250px; }
        .category-item { display: flex; justify-content: space-between; align-items: center; background: var(--dark-gray); padding: 10px 15px; border-radius: 4px; margin-bottom: 10px; }
        .status-badge { padding: 4px 8px; border-radius: 4px; color: white; font-size: 0.8rem; font-weight: bold; }
        .status-pending { background-color: #ffc107; color: black; }
        .status-fulfilled { background-color: #28a745; }
        .status-rejected { background-color: #6c757d; }
    </style>
</head>
<body>
<div class="admin-container">
    <header class="admin-header"><h1>Admin Panel</h1><a href="{{ url_for('home') }}" target="_blank">View Site</a></header>
    
    <!-- ================== START: TOP SECTION (DAILY USE) ================== -->
    <h2><i class="fas fa-tachometer-alt"></i> At a Glance</h2>
    <div class="dashboard-stats">
        <div class="stat-card"><h3>Total Content</h3><p>{{ stats.total_content }}</p></div>
        <div class="stat-card"><h3>Total Movies</h3><p>{{ stats.total_movies }}</p></div>
        <div class="stat-card"><h3>Total Series</h3><p>{{ stats.total_series }}</p></div>
        <div class="stat-card"><h3>Pending Requests</h3><p>{{ stats.pending_requests }}</p></div>
    </div>
    <hr>
    
    <h2><i class="fas fa-plus-circle"></i> Add New Content</h2>
    <fieldset><legend>Automatic Method (Search TMDB)</legend><div class="form-group"><div class="tmdb-fetcher"><input type="text" id="tmdb_search_query" placeholder="e.g., Avengers Endgame"><button type="button" id="tmdb_search_btn" class="btn btn-primary" onclick="searchTmdb()">Search</button></div></div></fieldset>
    <form method="post">
        <input type="hidden" name="form_action" value="add_content"><input type="hidden" name="tmdb_id" id="tmdb_id">
        <fieldset><legend>Core Details</legend>
            <div class="form-group"><label>Title:</label><input type="text" name="title" id="title" required></div>
            <div class="form-group"><label>Poster URL:</label><input type="url" name="poster" id="poster"></div>
            <div class="form-group"><label>Backdrop URL:</label><input type="url" name="backdrop" id="backdrop"></div>
            <div class="form-group"><label>Overview:</label><textarea name="overview" id="overview"></textarea></div>
            <div class="form-group">
                <label>Screenshots (Paste one URL per line):</label>
                <textarea name="screenshots" rows="5"></textarea>
            </div>
            <div class="form-group"><label>Language:</label><input type="text" name="language" id="language" placeholder="e.g., Hindi, English, Dual Audio"></div>
            <div class="form-group"><label>Genres (comma-separated):</label><input type="text" name="genres" id="genres"></div>
            <div class="form-group"><label>Categories:</label><div class="checkbox-group">{% for cat in categories_list %}<label><input type="checkbox" name="categories" value="{{ cat.name }}"> {{ cat.name }}</label>{% endfor %}</div></div>
            <div class="form-group"><label>Content Type:</label><select name="content_type" id="content_type" onchange="toggleFields()"><option value="movie">Movie</option><option value="series">Series</option></select></div>
        </fieldset>
        <div id="movie_fields">
            <fieldset><legend>Movie Links</legend>
                <div class="link-pair"><label>480p Watch Link:<input type="url" name="watch_link_480p"></label><label>480p Download Link:<input type="url" name="download_link_480p"></label></div>
                <div class="link-pair"><label>720p Watch Link:<input type="url" name="watch_link_720p"></label><label>720p Download Link:<input type="url" name="download_link_720p"></label></div>
                <div class="link-pair"><label>1080p Watch Link:<input type="url" name="watch_link_1080p"></label><label>1080p Download Link:<input type="url" name="download_link_1080p"></label></div>
                 <div class="link-pair"><label>BLU-RAY Watch Link:<input type="url" name="watch_link_BLU-RAY"></label><label>BLU-RAY Download Link:<input type="url" name="download_link_BLU-RAY"></label></div>
            </fieldset>
        </div>
        <div id="episode_fields" style="display: none;">
            <fieldset><legend>Series Links</legend>
                <label>Complete Season Packs:</label><div id="season_packs_container"></div><button type="button" onclick="addSeasonPackField()" class="btn btn-secondary"><i class="fas fa-plus"></i> Add Season Pack</button><hr style="margin: 20px 0;"><label>Individual Episodes:</label><div id="episodes_container"></div><button type="button" onclick="addEpisodeField()" class="btn btn-secondary"><i class="fas fa-plus"></i> Add Episode</button>
            </fieldset>
        </div>
        <fieldset><legend>Manual Download Buttons</legend><div id="manual_links_container"></div><button type="button" onclick="addManualLinkField()" class="btn btn-secondary"><i class="fas fa-plus"></i> Add Manual Button</button></fieldset>
        <button type="submit" class="btn btn-primary"><i class="fas fa-check"></i> Add Content</button>
    </form>
    <hr>
    
    <div class="manage-content-header">
        <h2><i class="fas fa-tasks"></i> Manage Content</h2>
        <div class="search-form">
            <input type="search" id="admin-live-search" placeholder="Type to search content live..." autocomplete="off">
        </div>
    </div>
    <form method="post" id="bulk-action-form">
        <input type="hidden" name="form_action" value="bulk_delete">
        <div class="table-container"><table>
            <thead><tr><th><input type="checkbox" id="select-all"></th><th>Title</th><th>Type</th><th>Actions</th></tr></thead>
            <tbody id="content-table-body">
            {% for movie in content_list %}
            <tr>
                <td><input type="checkbox" name="selected_ids" value="{{ movie._id }}" class="row-checkbox"></td>
                <td>{{ movie.title }}</td>
                <td>{{ movie.type|title }}</td>
                <td class="action-buttons">
                    <a href="{{ url_for('edit_movie', movie_id=movie._id) }}" class="btn btn-edit">Edit</a>
                    <a href="{{ url_for('delete_movie', movie_id=movie._id) }}" onclick="return confirm('Are you sure?')" class="btn btn-danger">Delete</a>
                </td>
            </tr>
            {% else %}
            <tr><td colspan="4" style="text-align:center;">No content found.</td></tr>
            {% endfor %}
            </tbody>
        </table></div>
        <button type="submit" class="btn btn-danger" style="margin-top: 15px;" onclick="return confirm('Are you sure you want to delete all selected items?')"><i class="fas fa-trash-alt"></i> Delete Selected</button>
    </form>
    <hr>

    <h2><i class="fas fa-inbox"></i> Manage Requests</h2>
    <div class="table-container">
        <table>
            <thead><tr><th>Content Name</th><th>Extra Info</th><th>Status</th><th>Actions</th></tr></thead>
            <tbody>
            {% for req in requests_list %}
            <tr>
                <td>{{ req.name }}</td>
                <td style="white-space: pre-wrap; min-width: 200px;">{{ req.info }}</td>
                <td><span class="status-badge status-{{ req.status|lower }}">{{ req.status }}</span></td>
                <td class="action-buttons">
                    <a href="{{ url_for('update_request_status', req_id=req._id, status='Fulfilled') }}" class="btn btn-success" style="padding: 5px 10px;">Fulfilled</a>
                    <a href="{{ url_for('update_request_status', req_id=req._id, status='Rejected') }}" class="btn btn-secondary" style="padding: 5px 10px;">Rejected</a>
                    <a href="{{ url_for('delete_request', req_id=req._id) }}" class="btn btn-danger" style="padding: 5px 10px;" onclick="return confirm('Are you sure?')">Delete</a>
                </td>
            </tr>
            {% else %}
            <tr><td colspan="4" style="text-align:center;">No pending requests.</td></tr>
            {% endfor %}
            </tbody>
        </table>
    </div>
    <hr>
    <!-- ================== END: TOP SECTION (DAILY USE) ================== -->

    <!-- ================== START: BOTTOM SECTION (LESS FREQUENT USE) ================== -->
    <h2><i class="fas fa-tags"></i> Category Management</h2>
    <div class="category-management">
        <form method="post" style="flex: 1; min-width: 300px;">
            <input type="hidden" name="form_action" value="add_category">
            <fieldset><legend>Add New Category</legend>
                <div class="form-group"><label>Category Name:</label><input type="text" name="category_name" required></div>
                <button type="submit" class="btn btn-primary"><i class="fas fa-plus"></i> Add Category</button>
            </fieldset>
        </form>
        <div class="category-list">
            <h3>Existing Categories</h3>
            {% for cat in categories_list %}<div class="category-item"><span>{{ cat.name }}</span><a href="{{ url_for('delete_category', cat_id=cat._id) }}" onclick="return confirm('Are you sure?')" class="btn btn-danger" style="padding: 5px 10px; font-size: 0.8rem;">Delete</a></div>{% endfor %}
        </div>
    </div>
    <hr>

    <h2><i class="fas fa-bullhorn"></i> Advertisement Management</h2>
    <form method="post">
        <input type="hidden" name="form_action" value="update_ads">
        <fieldset><legend>Global Ad Codes</legend>
            <div class="form-group"><label>Header Script:</label><textarea name="ad_header" rows="4">{{ ad_settings.ad_header or '' }}</textarea></div>
            <div class="form-group"><label>Body Top Script:</label><textarea name="ad_body_top" rows="4">{{ ad_settings.ad_body_top or '' }}</textarea></div>
            <div class="form-group"><label>Footer Script:</label><textarea name="ad_footer" rows="4">{{ ad_settings.ad_footer or '' }}</textarea></div>
        </fieldset>
        <fieldset><legend>In-Page Ad Units</legend>
             <div class="form-group"><label>Homepage Ad:</label><textarea name="ad_list_page" rows="4">{{ ad_settings.ad_list_page or '' }}</textarea></div>
             <div class="form-group"><label>Details Page Ad:</label><textarea name="ad_detail_page" rows="4">{{ ad_settings.ad_detail_page or '' }}</textarea></div>
             <div class="form-group"><label>Wait Page Ad:</label><textarea name="ad_wait_page" rows="4">{{ ad_settings.ad_wait_page or '' }}</textarea></div>
        </fieldset>
        <button type="submit" class="btn btn-primary"><i class="fas fa-save"></i> Save Ad Settings</button>
    </form>
    <hr>
    <!-- ================== END: BOTTOM SECTION (LESS FREQUENT USE) ================== -->

</div>
<div class="modal-overlay" id="search-modal"><div class="modal-content"><div class="modal-header"><h2>Select Content</h2><button class="modal-close" onclick="closeModal()">&times;</button></div><div class="modal-body" id="search-results"></div></div></div>
<script>
    function toggleFields() { const isSeries = document.getElementById('content_type').value === 'series'; document.getElementById('episode_fields').style.display = isSeries ? 'block' : 'none'; document.getElementById('movie_fields').style.display = isSeries ? 'none' : 'block'; }
    function addEpisodeField() { const c = document.getElementById('episodes_container'); const d = document.createElement('div'); d.className = 'dynamic-item'; d.innerHTML = `<button type="button" onclick="this.parentElement.remove()" class="btn btn-danger">X</button><div class="form-group"><label>Season:</label><input type="number" name="episode_season[]" value="1" required></div><div class="form-group"><label>Episode:</label><input type="number" name="episode_number[]" required></div><div class="form-group"><label>Title:</label><input type="text" name="episode_title[]"></div><div class="form-group"><label>Download/Watch Link:</label><input type="url" name="episode_watch_link[]" required></div>`; c.appendChild(d); }
    function addSeasonPackField() { const container = document.getElementById('season_packs_container'); const newItem = document.createElement('div'); newItem.className = 'dynamic-item'; newItem.innerHTML = `<button type="button" onclick="this.parentElement.remove()" class="btn btn-danger">X</button><div class="season-pack-item"><div class="form-group"><label>Season No.</label><input type="number" name="season_pack_number[]" value="1" required></div><div class="form-group"><label>Complete Watch Link</label><input type="url" name="season_pack_watch_link[]"></div><div class="form-group"><label>Complete Download Link</label><input type="url" name="season_pack_download_link[]"></div></div>`; container.appendChild(newItem); }
    function addManualLinkField() { const container = document.getElementById('manual_links_container'); const newItem = document.createElement('div'); newItem.className = 'dynamic-item'; newItem.innerHTML = `<button type="button" onclick="this.parentElement.remove()" class="btn btn-danger">X</button><div class="link-pair"><div class="form-group"><label>Button Name</label><input type="text" name="manual_link_name[]" placeholder="e.g., 480p G-Drive" required></div><div class="form-group"><label>Link URL</label><input type="url" name="manual_link_url[]" placeholder="https://..." required></div></div>`; container.appendChild(newItem); }
    function openModal() { document.getElementById('search-modal').style.display = 'flex'; }
    function closeModal() { document.getElementById('search-modal').style.display = 'none'; }
    async function searchTmdb() { const query = document.getElementById('tmdb_search_query').value.trim(); if (!query) return; const searchBtn = document.getElementById('tmdb_search_btn'); searchBtn.disabled = true; searchBtn.innerHTML = 'Searching...'; openModal(); try { const response = await fetch('/admin/api/search?query=' + encodeURIComponent(query)); const results = await response.json(); const container = document.getElementById('search-results'); container.innerHTML = ''; if(results.length > 0) { results.forEach(item => { const resultDiv = document.createElement('div'); resultDiv.className = 'result-item'; resultDiv.onclick = () => selectResult(item.id, item.media_type); resultDiv.innerHTML = `<img src="${item.poster}" alt="${item.title}"><p><strong>${item.title}</strong> (${item.year})</p>`; container.appendChild(resultDiv); }); } else { container.innerHTML = '<p>No results found.</p>'; } } catch (e) { console.error(e); } finally { searchBtn.disabled = false; searchBtn.innerHTML = 'Search'; } }
    async function selectResult(tmdbId, mediaType) { closeModal(); try { const response = await fetch(`/admin/api/details?id=${tmdbId}&type=${mediaType}`); const data = await response.json(); document.getElementById('tmdb_id').value = data.tmdb_id || ''; document.getElementById('title').value = data.title || ''; document.getElementById('overview').value = data.overview || ''; document.getElementById('poster').value = data.poster || ''; document.getElementById('backdrop').value = data.backdrop || ''; document.getElementById('genres').value = data.genres ? data.genres.join(', ') : ''; document.getElementById('content_type').value = data.type === 'series' ? 'series' : 'movie'; toggleFields(); } catch (e) { console.error(e); } }
    let debounceTimer;
    const searchInput = document.getElementById('admin-live-search');
    const tableBody = document.getElementById('content-table-body');
    searchInput.addEventListener('input', () => {
        clearTimeout(debounceTimer);
        debounceTimer = setTimeout(() => {
            const query = searchInput.value.trim();
            tableBody.innerHTML = '<tr><td colspan="4" style="text-align:center;">Loading...</td></tr>';
            fetch(`/admin/api/live_search?q=${encodeURIComponent(query)}`)
                .then(response => response.json())
                .then(data => {
                    tableBody.innerHTML = '';
                    if (data.length > 0) {
                        data.forEach(movie => {
                            const row = `
                                <tr>
                                    <td><input type="checkbox" name="selected_ids" value="${movie._id}" class="row-checkbox"></td>
                                    <td>${movie.title}</td>
                                    <td>${movie.type.charAt(0).toUpperCase() + movie.type.slice(1)}</td>
                                    <td class="action-buttons">
                                        <a href="/edit_movie/${movie._id}" class="btn btn-edit">Edit</a>
                                        <a href="/delete_movie/${movie._id}" onclick="return confirm('Are you sure?')" class="btn btn-danger">Delete</a>
                                    </td>
                                </tr>
                            `;
                            tableBody.innerHTML += row;
                        });
                    } else { tableBody.innerHTML = '<tr><td colspan="4" style="text-align:center;">No content found.</td></tr>'; }
                })
                .catch(error => { console.error('Error fetching search results:', error); tableBody.innerHTML = '<tr><td colspan="4" style="text-align:center;">Error loading results.</td></tr>'; });
        }, 400);
    });
    document.addEventListener('DOMContentLoaded', function() { toggleFields(); const selectAll = document.getElementById('select-all'); if(selectAll) { selectAll.addEventListener('change', e => document.querySelectorAll('.row-checkbox').forEach(c => c.checked = e.target.checked)); } });
</script>
</body></html>
"""
# --- [START CHANGE] edit_html টেমপ্লেট আপডেট করা হয়েছে ---
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
        .page-header { display: flex; justify-content: space-between; align-items: center; gap: 15px; flex-wrap: wrap; margin-bottom: 10px; }
        h2 { font-family: 'Bebas Neue', sans-serif; color: var(--netflix-red); font-size: 2.5rem; margin: 0; }
        form { background: var(--dark-gray); padding: 25px; border-radius: 8px; }
        fieldset { border: 1px solid var(--light-gray); padding: 20px; margin-bottom: 20px; border-radius: 5px;}
        legend { font-weight: bold; color: var(--netflix-red); padding: 0 10px; font-size: 1.2rem; }
        .form-group { margin-bottom: 15px; } label { display: block; margin-bottom: 8px; font-weight: bold;}
        input, textarea, select { width: 100%; padding: 12px; border-radius: 4px; border: 1px solid var(--light-gray); font-size: 1rem; background: var(--light-gray); color: var(--text-light); box-sizing: border-box; }
        .btn { display: inline-block; text-decoration: none; color: white; font-weight: 700; cursor: pointer; border: none; padding: 12px 25px; border-radius: 4px; font-size: 1rem; }
        .btn-primary { background: var(--netflix-red); } .btn-secondary { background: #555; } .btn-danger { background: #dc3545; }
        .btn-sync { background: #17a2b8; }
        .dynamic-item { border: 1px solid var(--light-gray); padding: 15px; margin-bottom: 15px; border-radius: 5px; position: relative; }
        .dynamic-item .btn-danger { position: absolute; top: 10px; right: 10px; padding: 4px 8px; font-size: 0.8rem; }
        .checkbox-group { display: flex; flex-wrap: wrap; gap: 15px; } .checkbox-group label { display: flex; align-items: center; gap: 5px; font-weight: normal; cursor: pointer; }
        .checkbox-group input { width: auto; }
        .link-pair { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-bottom: 10px; }
        .season-pack-item { display: grid; grid-template-columns: 100px 1fr 1fr; gap: 10px; align-items: flex-end; }
        .update-options { margin-top: 20px; padding: 15px; background: var(--light-gray); border-radius: 5px; display: flex; flex-direction: column; gap: 15px; }
    </style>
</head>
<body>
<div class="admin-container">
  <a href="{{ url_for('admin') }}" class="back-link"><i class="fas fa-arrow-left"></i> Back to Admin Panel</a>
  <div class="page-header">
    <h2>Edit: {{ movie.title }}</h2>
    {% if movie.tmdb_id %}
    <button type="button" class="btn btn-sync" id="resync-btn" onclick="resyncTmdb('{{ movie.tmdb_id }}', '{{ movie.type }}')">
        <i class="fas fa-sync-alt"></i> Re-sync with TMDB
    </button>
    {% endif %}
  </div>
  <form method="post">
    <fieldset><legend>Core Details</legend>
        <div class="form-group"><label>Title:</label><input type="text" name="title" id="title" value="{{ movie.title }}" required></div>
        <div class="form-group"><label>Poster URL:</label><input type="url" name="poster" id="poster" value="{{ movie.poster or '' }}"></div>
        <div class="form-group"><label>Backdrop URL:</label><input type="url" name="backdrop" id="backdrop" value="{{ movie.backdrop or '' }}"></div>
        <div class="form-group"><label>Overview:</label><textarea name="overview" id="overview">{{ movie.overview or '' }}</textarea></div>
        <div class="form-group">
            <label>Screenshots (Paste one URL per line):</label>
            <textarea name="screenshots" rows="5">{{ movie.screenshots|join('\n') if movie.screenshots }}</textarea>
        </div>
        <div class="form-group"><label>Language:</label><input type="text" name="language" value="{{ movie.language or '' }}"></div>
        <div class="form-group"><label>Genres:</label><input type="text" name="genres" id="genres" value="{{ movie.genres|join(', ') if movie.genres else '' }}"></div>
        <div class="form-group"><label>Categories:</label><div class="checkbox-group">{% for cat in categories_list %}<label><input type="checkbox" name="categories" value="{{ cat.name }}" {% if movie.categories and cat.name in movie.categories %}checked{% endif %}> {{ cat.name }}</label>{% endfor %}</div></div>
        <div class="form-group"><label>Content Type:</label><select name="content_type" id="content_type" onchange="toggleFields()"><option value="movie" {% if movie.type == 'movie' %}selected{% endif %}>Movie</option><option value="series" {% if movie.type == 'series' %}selected{% endif %}>Series</option></select></div>
    </fieldset>
    <div id="movie_fields">
        <fieldset><legend>Movie Links</legend>
            {% set links_480p = movie.links|selectattr('quality', 'equalto', '480p')|first if movie.links else None %}
            {% set links_720p = movie.links|selectattr('quality', 'equalto', '720p')|first if movie.links else None %}
            {% set links_1080p = movie.links|selectattr('quality', 'equalto', '1080p')|first if movie.links else None %}
            {% set links_bluray = movie.links|selectattr('quality', 'equalto', 'BLU-RAY')|first if movie.links else None %}
            <div class="link-pair"><label>480p Watch Link:<input type="url" name="watch_link_480p" value="{{ links_480p.watch_url if links_480p else '' }}"></label><label>480p Download Link:<input type="url" name="download_link_480p" value="{{ links_480p.download_url if links_480p else '' }}"></label></div>
            <div class="link-pair"><label>720p Watch Link:<input type="url" name="watch_link_720p" value="{{ links_720p.watch_url if links_720p else '' }}"></label><label>720p Download Link:<input type="url" name="download_link_720p" value="{{ links_720p.download_url if links_720p else '' }}"></label></div>
            <div class="link-pair"><label>1080p Watch Link:<input type="url" name="watch_link_1080p" value="{{ links_1080p.watch_url if links_1080p else '' }}"></label><label>1080p Download Link:<input type="url" name="download_link_1080p" value="{{ links_1080p.download_url if links_1080p else '' }}"></label></div>
            <div class="link-pair"><label>BLU-RAY Watch Link:<input type="url" name="watch_link_BLU-RAY" value="{{ links_bluray.watch_url if links_bluray else '' }}"></label><label>BLU-RAY Download Link:<input type="url" name="download_link_BLU-RAY" value="{{ links_bluray.download_url if links_bluray else '' }}"></label></div>
        </fieldset>
    </div>
    <div id="episode_fields" style="display: none;">
      <fieldset><legend>Series Links</legend>
        <label>Complete Season Packs:</label><div id="season_packs_container">
        {% if movie.type == 'series' and movie.season_packs %}{% for pack in movie.season_packs|sort(attribute='season_number') %}<div class="dynamic-item"><button type="button" onclick="this.parentElement.remove()" class="btn btn-danger">X</button><div class="season-pack-item"><div class="form-group"><label>Season No.</label><input type="number" name="season_pack_number[]" value="{{ pack.season_number }}" required></div><div class="form-group"><label>Watch Link</label><input type="url" name="season_pack_watch_link[]" value="{{ pack.watch_link or '' }}"></div><div class="form-group"><label>Download Link</label><input type="url" name="season_pack_download_link[]" value="{{ pack.download_link or '' }}"></div></div></div>{% endfor %}{% endif %}
        </div><button type="button" onclick="addSeasonPackField()" class="btn btn-secondary"><i class="fas fa-plus"></i> Add Season</button><hr style="margin: 20px 0;"><label>Individual Episodes:</label>
        <div id="episodes_container">
        {% if movie.type == 'series' and movie.episodes %}{% for ep in movie.episodes|sort(attribute='episode_number')|sort(attribute='season') %}<div class="dynamic-item"><button type="button" onclick="this.parentElement.remove()" class="btn btn-danger">X</button><div class="form-group"><label>Season:</label><input type="number" name="episode_season[]" value="{{ ep.season or 1 }}" required></div><div class="form-group"><label>Episode:</label><input type="number" name="episode_number[]" value="{{ ep.episode_number }}" required></div><div class="form-group"><label>Title:</label><input type="text" name="episode_title[]" value="{{ ep.title or '' }}"></div><div class="form-group"><label>Download/Watch Link:</label><input type="url" name="episode_watch_link[]" value="{{ ep.watch_link or '' }}" required></div></div>{% endfor %}{% endif %}</div><button type="button" onclick="addEpisodeField()" class="btn btn-secondary"><i class="fas fa-plus"></i> Add Episode</button></fieldset>
    </div>
    <fieldset><legend>Manual Download Buttons</legend><div id="manual_links_container">
        {% if movie.manual_links %}{% for link in movie.manual_links %}<div class="dynamic-item"><button type="button" onclick="this.parentElement.remove()" class="btn btn-danger">X</button><div class="link-pair"><div class="form-group"><label>Button Name</label><input type="text" name="manual_link_name[]" value="{{ link.name }}" required></div><div class="form-group"><label>Link URL</label><input type="url" name="manual_link_url[]" value="{{ link.url }}" required></div></div></div>{% endfor %}{% endif %}
    </div><button type="button" onclick="addManualLinkField()" class="btn btn-secondary"><i class="fas fa-plus"></i> Add Manual Button</button></fieldset>
    
    <div class="update-options">
        <div class="checkbox-group">
            <label>
                <input type="checkbox" name="send_notification" checked>
                Send Update Notification to Telegram?
            </label>
        </div>
        <button type="submit" class="btn btn-primary"><i class="fas fa-save"></i> Update Content</button>
    </div>
  </form>
</div>
<script>
    function toggleFields() { var isSeries = document.getElementById('content_type').value === 'series'; document.getElementById('episode_fields').style.display = isSeries ? 'block' : 'none'; document.getElementById('movie_fields').style.display = isSeries ? 'none' : 'block'; }
    function addEpisodeField() { const c = document.getElementById('episodes_container'); const d = document.createElement('div'); d.className = 'dynamic-item'; d.innerHTML = `<button type="button" onclick="this.parentElement.remove()" class="btn btn-danger">X</button><div class="form-group"><label>Season:</label><input type="number" name="episode_season[]" value="1" required></div><div class="form-group"><label>Episode:</label><input type="number" name="episode_number[]" required></div><div class="form-group"><label>Title:</label><input type="text" name="episode_title[]"></div><div class="form-group"><label>Download/Watch Link:</label><input type="url" name="episode_watch_link[]" required></div>`; c.appendChild(d); }
    function addSeasonPackField() { const container = document.getElementById('season_packs_container'); const newItem = document.createElement('div'); newItem.className = 'dynamic-item'; newItem.innerHTML = `<button type="button" onclick="this.parentElement.remove()" class="btn btn-danger">X</button><div class="season-pack-item"><div class="form-group"><label>Season No.</label><input type="number" name="season_pack_number[]" value="1" required></div><div class="form-group"><label>Watch Link</label><input type="url" name="season_pack_watch_link[]"></div><div class="form-group"><label>Download Link</label><input type="url" name="season_pack_download_link[]"></div></div>`; container.appendChild(newItem); }
    function addManualLinkField() { const container = document.getElementById('manual_links_container'); const newItem = document.createElement('div'); newItem.className = 'dynamic-item'; newItem.innerHTML = `<button type="button" onclick="this.parentElement.remove()" class="btn btn-danger">X</button><div class="link-pair"><div class="form-group"><label>Button Name</label><input type="text" name="manual_link_name[]" placeholder="e.g., 480p G-Drive" required></div><div class="form-group"><label>Link URL</label><input type="url" name="manual_link_url[]" placeholder="https://..." required></div></div>`; container.appendChild(newItem); }
    
    async function resyncTmdb(tmdbId, mediaType) {
        const btn = document.getElementById('resync-btn');
        btn.disabled = true;
        btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Syncing...';
        try {
            const response = await fetch(`/admin/api/resync_tmdb?id=${tmdbId}&type=${mediaType}`);
            if (!response.ok) throw new Error('Failed to fetch data');
            const data = await response.json();
            document.getElementById('title').value = data.title || '';
            document.getElementById('overview').value = data.overview || '';
            document.getElementById('poster').value = data.poster || '';
            document.getElementById('backdrop').value = data.backdrop || '';
            document.getElementById('genres').value = data.genres ? data.genres.join(', ') : '';
            alert('Data synced successfully from TMDB! Please review and save.');
        } catch (e) {
            console.error(e);
            alert('Error syncing data from TMDB.');
        } finally {
            btn.disabled = false;
            btn.innerHTML = '<i class="fas fa-sync-alt"></i> Re-sync with TMDB';
        }
    }

    document.addEventListener('DOMContentLoaded', toggleFields);
</script>
</body></html>
"""
# --- [END CHANGE] ---


# =========================================================================================
# === [START] PYTHON FUNCTIONS & FLASK ROUTES =============================================
# =========================================================================================

# --- TMDB API Helper Function ---
def get_tmdb_details(tmdb_id, media_type):
    if not TMDB_API_KEY: return None
    # [FIX] media_type is 'series' or 'movie' from our app, map to 'tv' for TMDB
    search_type = "tv" if media_type == "series" else "movie"
    try:
        detail_url = f"https://api.themoviedb.org/3/{search_type}/{tmdb_id}?api_key={TMDB_API_KEY}"
        res = requests.get(detail_url, timeout=10)
        res.raise_for_status()
        data = res.json()
        details = { "tmdb_id": tmdb_id, "title": data.get("title") or data.get("name"), "poster": f"https://image.tmdb.org/t/p/w500{data.get('poster_path')}" if data.get('poster_path') else None, "backdrop": f"https://image.tmdb.org/t/p/w1280{data.get('backdrop_path')}" if data.get('backdrop_path') else None, "overview": data.get("overview"), "release_date": data.get("release_date") or data.get("first_air_date"), "genres": [g['name'] for g in data.get("genres", [])], "vote_average": data.get("vote_average"), "type": "series" if search_type == "tv" else "movie" }
        return details
    except requests.RequestException as e:
        print(f"ERROR: TMDb API request failed: {e}")
        return None

# --- Pagination Helper Class ---
class Pagination:
    def __init__(self, page, per_page, total_count):
        self.page = page
        self.per_page = per_page
        self.total_count = total_count
    @property
    def total_pages(self): return math.ceil(self.total_count / self.per_page)
    @property
    def has_prev(self): return self.page > 1
    @property
    def has_next(self): return self.page < self.total_pages
    @property
    def prev_num(self): return self.page - 1
    @property
    def next_num(self): return self.page + 1

# --- Flask Routes ---
@app.route('/')
def home():
    query = request.args.get('q', '').strip()
    if query:
        movies_list = list(movies.find({"title": {"$regex": query, "$options": "i"}}).sort('updated_at', -1))
        total_results = movies.count_documents({"title": {"$regex": query, "$options": "i"}})
        pagination = Pagination(1, ITEMS_PER_PAGE, total_results)
        return render_template_string(index_html, movies=movies_list, query=f'Results for "{query}"', is_full_page_list=True, pagination=pagination)

    slider_content = list(movies.find({}).sort('updated_at', -1).limit(10))
    latest_content = list(movies.find({}).sort('updated_at', -1).limit(10))
    
    home_categories = [cat['name'] for cat in categories_collection.find().sort("name", 1)]
    categorized_content = {cat: list(movies.find({"categories": cat}).sort('updated_at', -1).limit(10)) for cat in home_categories}
    
    categorized_content = {k: v for k, v in categorized_content.items() if v}

    context = {
        "slider_content": slider_content, "latest_content": latest_content,
        "categorized_content": categorized_content, "is_full_page_list": False
    }
    return render_template_string(index_html, **context)

@app.route('/movie/<movie_id>')
def movie_detail(movie_id):
    try:
        movie = movies.find_one_and_update(
            {"_id": ObjectId(movie_id)},
            {"$inc": {"view_count": 1}},
            return_document=True
        )
        if not movie: return "Content not found", 404
        related_content = list(movies.find({"type": movie.get('type'), "_id": {"$ne": movie['_id']}}).sort('updated_at', -1).limit(10))
        return render_template_string(detail_html, movie=movie, related_content=related_content)
    except: return "Content not found", 404

def get_paginated_content(query_filter, page):
    skip = (page - 1) * ITEMS_PER_PAGE
    total_count = movies.count_documents(query_filter)
    content_list = list(movies.find(query_filter).sort('updated_at', -1).skip(skip).limit(ITEMS_PER_PAGE))
    pagination = Pagination(page, ITEMS_PER_PAGE, total_count)
    return content_list, pagination

@app.route('/movies')
def all_movies():
    page = request.args.get('page', 1, type=int)
    all_movie_content, pagination = get_paginated_content({"type": "movie"}, page)
    return render_template_string(index_html, movies=all_movie_content, query="All Movies", is_full_page_list=True, pagination=pagination)

@app.route('/series')
def all_series():
    page = request.args.get('page', 1, type=int)
    all_series_content, pagination = get_paginated_content({"type": "series"}, page)
    return render_template_string(index_html, movies=all_series_content, query="Web Series & TV Shows", is_full_page_list=True, pagination=pagination)

@app.route('/category')
def movies_by_category():
    title = request.args.get('name')
    if not title: return redirect(url_for('home'))
    page = request.args.get('page', 1, type=int)
    
    query_filter = {}
    if title == "Latest Movies": query_filter = {"type": "movie"}
    elif title == "Latest Series": query_filter = {"type": "series"}
    else: query_filter = {"categories": title}
    
    content_list, pagination = get_paginated_content(query_filter, page)
    return render_template_string(index_html, movies=content_list, query=title, is_full_page_list=True, pagination=pagination)

@app.route('/request', methods=['GET', 'POST'])
def request_content():
    if request.method == 'POST':
        content_name = request.form.get('content_name', '').strip()
        extra_info = request.form.get('extra_info', '').strip()
        if content_name:
            requests_collection.insert_one({"name": content_name, "info": extra_info, "status": "Pending", "created_at": datetime.utcnow()})
        return redirect(url_for('request_content'))
    return render_template_string(request_html)

@app.route('/wait')
def wait_page():
    encoded_target_url = request.args.get('target')
    if not encoded_target_url: return redirect(url_for('home'))
    return render_template_string(wait_page_html, target_url=unquote(encoded_target_url))

@app.route('/admin', methods=["GET", "POST"])
@requires_auth
def admin():
    if request.method == "POST":
        form_action = request.form.get("form_action")
        if form_action == "update_ads":
            ad_settings_data = {"ad_header": request.form.get("ad_header"), "ad_body_top": request.form.get("ad_body_top"), "ad_footer": request.form.get("ad_footer"), "ad_list_page": request.form.get("ad_list_page"), "ad_detail_page": request.form.get("ad_detail_page"), "ad_wait_page": request.form.get("ad_wait_page")}
            settings.update_one({"_id": "ad_config"}, {"$set": ad_settings_data}, upsert=True)
        elif form_action == "add_category":
            category_name = request.form.get("category_name", "").strip()
            if category_name: categories_collection.update_one({"name": category_name}, {"$set": {"name": category_name}}, upsert=True)
        elif form_action == "bulk_delete":
            ids_to_delete = request.form.getlist("selected_ids")
            if ids_to_delete: movies.delete_many({"_id": {"$in": [ObjectId(id_str) for id_str in ids_to_delete]}})
        elif form_action == "add_content":
            content_type = request.form.get("content_type", "movie")
            screenshots_text = request.form.get("screenshots", "").strip()
            screenshots_list = [url.strip() for url in screenshots_text.splitlines() if url.strip()]
            
            # [NEW] TMDB ID সংরক্ষণ করা
            tmdb_id = request.form.get("tmdb_id")
            
            movie_data = {
                "title": request.form.get("title").strip(), "type": content_type,
                "poster": request.form.get("poster").strip() or PLACEHOLDER_POSTER,
                "backdrop": request.form.get("backdrop").strip() or None,
                "overview": request.form.get("overview").strip(), 
                "screenshots": screenshots_list,
                "language": request.form.get("language").strip() or None,
                "genres": [g.strip() for g in request.form.get("genres", "").split(',') if g.strip()],
                "categories": request.form.getlist("categories"), "episodes": [], "links": [], "season_packs": [], "manual_links": [],
                "created_at": datetime.utcnow(), "updated_at": datetime.utcnow(), "view_count": 0,
                "tmdb_id": tmdb_id if tmdb_id else None # [NEW]
            }

            if tmdb_id:
                # [CHANGE] Use 'series' or 'movie' for media type
                tmdb_details = get_tmdb_details(tmdb_id, "series" if content_type == "series" else "movie")
                if tmdb_details: movie_data.update({'release_date': tmdb_details.get('release_date'),'vote_average': tmdb_details.get('vote_average')})
            
            if content_type == "movie":
                qualities = ["480p", "720p", "1080p", "BLU-RAY"]
                movie_data["links"] = [{"quality": q, "watch_url": request.form.get(f"watch_link_{q}"), "download_url": request.form.get(f"download_link_{q}")} for q in qualities if request.form.get(f"watch_link_{q}") or request.form.get(f"download_link_{q}")]
            else:
                sp_nums, sp_w, sp_d = request.form.getlist('season_pack_number[]'), request.form.getlist('season_pack_watch_link[]'), request.form.getlist('season_pack_download_link[]')
                movie_data['season_packs'] = [{"season_number": int(sp_nums[i]), "watch_link": sp_w[i].strip() or None, "download_link": sp_d[i].strip() or None} for i in range(len(sp_nums)) if sp_nums[i]]
                s, n, t, l = request.form.getlist('episode_season[]'), request.form.getlist('episode_number[]'), request.form.getlist('episode_title[]'), request.form.getlist('episode_watch_link[]')
                movie_data['episodes'] = [{"season": int(s[i]), "episode_number": int(n[i]), "title": t[i].strip(), "watch_link": l[i].strip()} for i in range(len(s)) if s[i] and n[i] and l[i]]
            
            names, urls = request.form.getlist('manual_link_name[]'), request.form.getlist('manual_link_url[]')
            movie_data["manual_links"] = [{"name": names[i].strip(), "url": urls[i].strip()} for i in range(len(names)) if names[i] and urls[i]]
            
            result = movies.insert_one(movie_data)
            if result.inserted_id:
                send_telegram_notification(movie_data, result.inserted_id)

        return redirect(url_for('admin'))
    
    content_list = list(movies.find({}).sort('updated_at', -1))
    stats = {"total_content": movies.count_documents({}), "total_movies": movies.count_documents({"type": "movie"}), "total_series": movies.count_documents({"type": "series"}), "pending_requests": requests_collection.count_documents({"status": "Pending"})}
    requests_list = list(requests_collection.find().sort("created_at", -1))
    categories_list = list(categories_collection.find().sort("name", 1))
    ad_settings_data = settings.find_one({"_id": "ad_config"}) or {}
    return render_template_string(admin_html, content_list=content_list, stats=stats, requests_list=requests_list, ad_settings=ad_settings_data, categories_list=categories_list)

@app.route('/admin/category/delete/<cat_id>')
@requires_auth
def delete_category(cat_id):
    try: categories_collection.delete_one({"_id": ObjectId(cat_id)})
    except: pass
    return redirect(url_for('admin'))

@app.route('/admin/request/update/<req_id>/<status>')
@requires_auth
def update_request_status(req_id, status):
    if status in ['Fulfilled', 'Rejected', 'Pending']:
        try: requests_collection.update_one({"_id": ObjectId(req_id)}, {"$set": {"status": status}})
        except: pass
    return redirect(url_for('admin'))

@app.route('/admin/request/delete/<req_id>')
@requires_auth
def delete_request(req_id):
    try: requests_collection.delete_one({"_id": ObjectId(req_id)})
    except: pass
    return redirect(url_for('admin'))

@app.route('/edit_movie/<movie_id>', methods=["GET", "POST"])
@requires_auth
def edit_movie(movie_id):
    try: obj_id = ObjectId(movie_id)
    except: return "Invalid ID", 400
    movie_obj = movies.find_one({"_id": obj_id})
    if not movie_obj: return "Movie not found", 404
    
    if request.method == "POST":
        content_type = request.form.get("content_type")
        screenshots_text = request.form.get("screenshots", "").strip()
        screenshots_list = [url.strip() for url in screenshots_text.splitlines() if url.strip()]
        update_data = {
            "title": request.form.get("title").strip(), "type": content_type,
            "poster": request.form.get("poster").strip() or PLACEHOLDER_POSTER,
            "backdrop": request.form.get("backdrop").strip() or None,
            "overview": request.form.get("overview").strip(), 
            "screenshots": screenshots_list,
            "language": request.form.get("language").strip() or None,
            "genres": [g.strip() for g in request.form.get("genres").split(',') if g.strip()],
            "categories": request.form.getlist("categories"), "updated_at": datetime.utcnow()
        }
        names, urls = request.form.getlist('manual_link_name[]'), request.form.getlist('manual_link_url[]')
        update_data["manual_links"] = [{"name": names[i].strip(), "url": urls[i].strip()} for i in range(len(names)) if names[i] and urls[i]]
        if content_type == "movie":
            qualities = ["480p", "720p", "1080p", "BLU-RAY"]
            update_data["links"] = [{"quality": q, "watch_url": request.form.get(f"watch_link_{q}"), "download_url": request.form.get(f"download_link_{q}")} for q in qualities if request.form.get(f"watch_link_{q}") or request.form.get(f"download_link_{q}")]
            movies.update_one({"_id": obj_id}, {"$set": update_data, "$unset": {"episodes": "", "season_packs": ""}})
        else:
            sp_nums, sp_w, sp_d = request.form.getlist('season_pack_number[]'), request.form.getlist('season_pack_watch_link[]'), request.form.getlist('season_pack_download_link[]')
            update_data['season_packs'] = [{"season_number": int(sp_nums[i]), "watch_link": sp_w[i].strip() or None, "download_link": sp_d[i].strip() or None} for i in range(len(sp_nums)) if sp_nums[i]]
            s, n, t, l = request.form.getlist('episode_season[]'), request.form.getlist('episode_number[]'), request.form.getlist('episode_title[]'), request.form.getlist('episode_watch_link[]')
            update_data["episodes"] = [{"season": int(s[i]), "episode_number": int(n[i]), "title": t[i].strip(), "watch_link": l[i].strip()} for i in range(len(s)) if s[i] and n[i] and l[i]]
            movies.update_one({"_id": obj_id}, {"$set": update_data, "$unset": {"links": ""}})
        
        # --- [START CHANGE] নোটিফিকেশন পাঠানোর শর্ত চেক করা ---
        send_notification = request.form.get('send_notification')
        if send_notification:
            notification_data = movie_obj.copy()
            notification_data.update(update_data)
            send_telegram_notification(notification_data, obj_id, notification_type='update')
        # --- [END CHANGE] ---
        
        return redirect(url_for('admin'))
    
    categories_list = list(categories_collection.find().sort("name", 1))
    return render_template_string(edit_html, movie=movie_obj, categories_list=categories_list)

@app.route('/delete_movie/<movie_id>')
@requires_auth
def delete_movie(movie_id):
    try: movies.delete_one({"_id": ObjectId(movie_id)})
    except: return "Invalid ID", 400
    return redirect(url_for('admin'))

@app.route('/admin/api/live_search')
@requires_auth
def admin_api_live_search():
    query = request.args.get('q', '').strip()
    try:
        results = list(movies.find({"title": {"$regex": query, "$options": "i"} if query else {}}, {"_id": 1, "title": 1, "type": 1}).sort('updated_at', -1))
        for item in results: item['_id'] = str(item['_id'])
        return jsonify(results)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

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
        results = [{"id": item.get('id'),"title": item.get('title') or item.get('name'),"year": (item.get('release_date') or item.get('first_air_date', 'N/A')).split('-')[0],"poster": f"https://image.tmdb.org/t/p/w200{item.get('poster_path')}","media_type": item.get('media_type')} for item in data.get('results', []) if item.get('media_type') in ['movie', 'tv'] and item.get('poster_path')]
        return jsonify(results)
    except Exception as e: return jsonify({"error": str(e)}), 500

@app.route('/admin/api/details')
@requires_auth
def api_get_details():
    tmdb_id, media_type = request.args.get('id'), request.args.get('type')
    if not tmdb_id or not media_type: return jsonify({"error": "ID and type are required"}), 400
    # [CHANGE] Use 'series' or 'movie' from our app
    details = get_tmdb_details(tmdb_id, "series" if media_type == "tv" else "movie")
    if details: return jsonify(details)
    else: return jsonify({"error": "Details not found on TMDb"}), 404

# --- [START NEW ROUTE] TMDB থেকে তথ্য Re-sync করার জন্য নতুন API রুট ---
@app.route('/admin/api/resync_tmdb')
@requires_auth
def api_resync_tmdb():
    tmdb_id = request.args.get('id')
    media_type = request.args.get('type') # 'series' or 'movie'
    if not tmdb_id or not media_type:
        return jsonify({"error": "TMDB ID and media type are required"}), 400
    
    details = get_tmdb_details(tmdb_id, media_type)
    if details:
        return jsonify(details)
    else:
        return jsonify({"error": "Could not fetch details from TMDB"}), 404
# --- [END NEW ROUTE] ---

@app.route('/api/search')
def api_search():
    query = request.args.get('q', '').strip()
    if not query: return jsonify([])
    try:
        results = list(movies.find({"title": {"$regex": query, "$options": "i"}}, {"_id": 1, "title": 1, "poster": 1}).limit(10))
        for item in results: item['_id'] = str(item['_id'])
        return jsonify(results)
    except Exception as e:
        print(f"API Search Error: {e}")
        return jsonify({"error": "An error occurred"}), 500

if __name__ == "__main__":
    port = int(os.environ.get('PORT', 3000))
    app.run(debug=True, host='0.0.0.0', port=port)
