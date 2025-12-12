import os
import sys
import requests
from flask import Flask, render_template_string, request, redirect, url_for, Response, jsonify
from pymongo import MongoClient
from bson.objectid import ObjectId
from functools import wraps
from urllib.parse import unquote, quote, unquote_plus
from datetime import datetime, timedelta # Added timedelta for NEW badge calculation
import math # Added for pagination calculation
import json # <--- এই লাইনটি যোগ করুন

# --- Environment Variables ---
MONGO_URI = os.environ.get("MONGO_URI", "mongodb+srv://mesohas358:mesohas358@cluster0.6kxy1vc.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0")
TMDB_API_KEY = os.environ.get("TMDB_API_KEY", "7dc544d9253bccc3cfecc1c677f69819")
ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "Nahid270")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "Nahid270")
WEBSITE_NAME = os.environ.get("WEBSITE_NAME", "CineZoneBD")

# --- START: NEW TELEGRAM SETTINGS (এই অংশটি যোগ করুন) ---
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "7995209759:AAFqir3wFLcW5WODmM6DfqSsivMq3X_ibH4")
TELEGRAM_CHANNEL_ID = os.environ.get("TELEGRAM_CHANNEL_ID", "-1002847575327") # যেমন: "@yourchannelname" বা "-100123456789"
HOW_TO_DOWNLOAD_URL = os.environ.get("HOW_TO_DOWNLOAD_URL", "https://t.me/HowtoDowlnoad/29") # আপনার "How to Download" গাইডের লিংক
# --- END: NEW TELEGRAM SETTINGS ---

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
    ott_platforms_collection = db["ott_platforms"]
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
    ott_platform_logos = {
        "Netflix": "https://i.postimg.cc/GtHdbb5h/images-3.png",
        "Amazon Prime": "https://i.postimg.cc/XvLvzbxp/Amazon-Prime-Logo-Transparent.png",
        "AppleTV": "https://i.postimg.cc/0jWWWbKm/Apple-TV-logo.png",
        "Bongo": "https://i.ibb.co.com/wFHM61sz/KV0.jpg",
        "Chorki": "https://i.ibb.co.com/PZh6wWNQ/Chorki-Logo.png",
        "Hoichoi": "https://i.postimg.cc/fTsQHjwz/images-4.png",
        "SonyLIV": "https://i.postimg.cc/gjLmmXFy/sony-liv-logo.webp",
        "ZEE5": "https://i.postimg.cc/CMBMpt4D/images.png",
        "Disney+": "https://i.postimg.cc/9Xx6c5VM/images-2.png",
        "iScreen": "https://i.postimg.cc/ncVV786p/IMG-20251031-200605-353.jpg",
        "JioCinema": "https://i.postimg.cc/wMyC5VcJ/IMG-20251031-201544-410.jpg",
    }
    
    
    # Dictionary to hold icons for each category
    category_icons = {
        "Bangla": "fa-clapperboard",
        "Hindi": "fa-theater-masks",
        "English": "fa-video",
        "18+ Adult": "fa-exclamation-triangle",
        "Korean": "fa-tv",
        "Dual Audio": "fa-headphones",
        "Bangla Dubbed": "fa-comment",
        "Hindi Dubbed": "fa-comments",
        "Horror": "fa-skull",
        "Action": "fa-fist-raised",
        "Thriller": "fa-eye",
        "Anime": "fa-ghost",
        "Romance": "fa-heart",
        "Trending": "fa-fire",
        "ALL MOVIES": "fa-film",
        "WEB SERIES & TV SHOWS": "fa-play-circle",
        "HOME": "fa-home"
    }

    return dict(
        website_name=WEBSITE_NAME,
        ad_settings=ad_settings or {},
        predefined_categories=all_categories,
        quote=quote,
        datetime=datetime,
        category_icons=category_icons,
        ott_platform_logos=ott_platform_logos # Pass logos to all templates
    )

# =========================================================================================
# === [START] HTML TEMPLATES ==============================================================
# =========================================================================================
index_html = """
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no" />
<title>{{ website_name }} - Your Entertainment Hub</title>
<!-- Updated Favicon -->
<link rel="icon" href="https://i.postimg.cc/L4kGt56P/1000018917-removebg-preview.png" type="image/png">
<a name="description" content="Watch and download the latest movies and series on {{ website_name }}. Your ultimate entertainment hub.">
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

  /* START: New Home Page Search Bar Styles */
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
  /* END: New Home Page Search Bar Styles */
  /* === [NEW] STAR ANIMATION FOR "CREATE WEBSITE" LINK === */
  .glowing-link {
    position: relative;
    color: #fff;
    text-shadow: 0 0 5px #ffc107, 0 0 10px #ffc107, 0 0 15px #ffc107;
    animation: pulsate 2s infinite;
  }
  @keyframes pulsate {
    0% { text-shadow: 0 0 5px #ffc107, 0 0 10px #ffc107; }
    50% { text-shadow: 0 0 10px #ffc107, 0 0 20px #ffc107, 0 0 25px #ffc107; }
    100% { text-shadow: 0 0 5px #ffc107, 0 0 10px #ffc107; }
  }
  .glowing-link::before, .glowing-link::after {
    content: '★';
    position: absolute;
    color: #ffeb3b;
    font-size: 14px;
    opacity: 0;
    animation: sparkle 3s infinite;
  }
  .glowing-link::before { top: -5px; left: -20px; animation-delay: 0.5s; }
  .glowing-link::after { bottom: -5px; right: -20px; animation-delay: 1.5s; }
  @keyframes sparkle {
    0%, 100% { transform: scale(0.5); opacity: 0; }
    25%, 75% { transform: scale(1.2); opacity: 1; }
    50% { transform: scale(0.8); opacity: 0.5; }
  }
  /* === END OF ANIMATION STYLE === */
  .create-website-section {
    text-align: center;
    padding: 50px 20px;
    margin-top: 40px;
    background-color: var(--card-bg);
}
.create-website-section h2 {
    font-size: 2rem;
    font-weight: 700;
    margin-bottom: 20px;
}
.create-website-section .glowing-link {
    display: inline-block;
    padding: 15px 35px;
    border: 2px solid #ffc107;
    border-radius: 50px;
    font-size: 1.3rem;
    font-weight: 600;
    transition: all 0.3s ease;
}
.create-website-section .glowing-link:hover {
    background-color: #ffc107;
    color: var(--bg-color);
    text-shadow: none;
    transform: scale(1.05);
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
  .category-title {
    font-size: 1.8rem; 
    font-weight: 700; 
    margin-bottom: 20px;
    padding-left: 15px;
    border-left: 5px solid var(--primary-color);
    line-height: 1.2;
    /* পুরনো ডিজাইন (যেমন বর্ডার, অ্যানিমেশন) মুছে ফেলা হয়েছে */
  }
  //.category-title { font-size: 1.5rem; font-weight: 600; display: inline-block; padding: 8px 20px; background-color: rgba(26, 26, 26, 0.8); border: 2px solid; border-radius: 50px; animation: rgb-glow 4s linear infinite; backdrop-filter: blur(3px); }
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
  /* প্রতিটি কার্ডের ভেতরের লোডারের জন্য স্টাইল */
  .card-preloader {
    position: absolute;
    top: 0;
    left: 0;
    width: 100%;
    height: 100%;
    background-color: rgba(0, 0, 0, 0.75);
    z-index: 5;
    display: none; /* ডিফল্টভাবে লুকানো থাকবে */
    justify-content: center;
    align-items: center;
    backdrop-filter: blur(4px);
    border-radius: 8px; /* কার্ডের বর্ডারের সাথে মিলিয়ে */
    transition: opacity 0.2s;
  }
  .card-preloader.active {
    display: flex; /* 'active' ক্লাস যোগ হলে লোডারটি দেখা যাবে */
  }
  .play-button-loader-small {
    width: 60px;
    height: 60px;
    border: 4px solid rgba(255, 255, 255, 0.4);
    border-top-color: #fff; /* উপরের বর্ডারটি সাদা করে স্পিনিং ইফেক্ট স্পষ্ট করা হলো */
    border-radius: 50%;
    position: relative;
    animation: spin 1s ease-in-out infinite;
  }
  .play-button-loader-small::after {
    content: '';
    position: absolute;
    top: 50%;
    left: 50%;
    transform: translate(-50%, -50%);
    width: 0;
    height: 0;
    border-style: solid;
    border-width: 15px 0 15px 25px; /* প্লে বাটনের ত্রিভুজ */
    border-color: transparent transparent transparent white;
    margin-left: 4px; /* ত্রিভুজটিকে মাঝখানে আনার জন্য */
  }
  @keyframes spin {
    to { transform: rotate(360deg); }
  }
  .card-info { padding: 10px; background-color: var(--card-bg); }
  .card-title {
    font-size: 0.9rem; font-weight: 500; color: var(--text-light);
    margin: 0 0 5px 0; line-height: 1.4; min-height: 2.8em;
    display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden;
  }
  .card-meta { font-size: 0.75rem; color: var(--text-dark); display: flex; align-items: center; gap: 5px; }
  .card-meta i { color: var(--cyan-accent); }
  .type-tag, .language-tag {
    position: absolute; color: white; padding: 2px 8px; font-size: 0.65rem; font-weight: 600; z-index: 2; text-transform: uppercase; border-radius: 4px;
  }
  .language-tag { padding: 2px 6px; font-size: 0.6rem; top: 8px; right: 8px; background-color: rgba(0,0,0,0.6); }
  .type-tag { bottom: 8px; right: 8px; background-color: var(--type-color); }
  .rating-tag {
    position: absolute;
    bottom: 8px;
    left: 8px;
    background-color: rgba(245, 197, 24, 0.9); /* Gold color */
    color: #000;
    padding: 2px 8px;
    font-size: 0.7rem;
    font-weight: 700;
    z-index: 2;
    border-radius: 4px;
    display: flex;
    align-items: center;
  }
  .rating-tag i {
    margin-right: 4px;
  }
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
  /* ... আগের কোড ... */
  .search-result-item img { width: 100%; aspect-ratio: 2 / 3; object-fit: cover; border-radius: 5px; margin-bottom: 5px; }
/* --- এই অংশটি পরিবর্তন করুন --- */
/* START: Reverted and Clean Pagination Styles */
.pagination { 
    display: flex; 
    justify-content: center; 
    align-items: center; 
    gap: 10px; 
    margin: 30px 0; 
}
.pagination a, .pagination span { 
    padding: 12px 25px; /* Bigger padding for a bolder look */
    border-radius: 8px; 
    font-weight: 600; 
    font-size: 1rem;
    transition: all 0.2s ease;
    text-align: center;
    border: none;
    text-decoration: none;
}

/* Default state for Previous/Next buttons */
.pagination a { 
    background-color: var(--card-bg); 
    color: var(--text-light); 
}
.pagination a:hover { 
    background-color: #333; 
    color: white;
    transform: translateY(-1px);
}

/* Current Page Span - Matching the RED style from the image */
.pagination .current { 
    background-color: var(--primary-color); 
    color: white;
    box-shadow: 0 4px 10px rgba(229, 9, 20, 0.4);
}
/* END: Reverted and Clean Pagination Styles */
/* --- পরিবর্তন শেষ --- */
  
  @media (min-width: 769px) { 
    .container { padding: 0 40px; } .main-header { padding: 0 40px; }
    body { padding-bottom: 0; } .bottom-nav { display: none; }
    .hero-slider .hero-title { font-size: 2.2rem; }
    .hero-slider .hero-slide-content { padding: 40px; }
    .category-grid { grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); }
    .full-page-grid { grid-template-columns: repeat(auto-fill, minmax(180px, 1fr)); }
    .full-page-grid-container { padding: 120px 40px 20px; }
  }
  .theme-toggle {
  position: relative;
  margin-right: 10px;
}

.theme-btn {
  background: none;
  border: none;
  color: white;
  font-size: 1.3rem;
  cursor: pointer;
  transition: transform 0.2s;
}

.theme-btn:hover {
  transform: scale(1.1);
}

.theme-popup {
  position: absolute;
  top: 120%;
  right: 0;
  background-color: #1a1a1a !important; /* এই পরিবর্তনটি নিশ্চিতভাবে কাজ করবে */
  border: 1px solid #333;
  border-radius: 8px;
  display: none;
  flex-direction: column;
  padding: 8px;
  box-shadow: 0 4px 10px rgba(0,0,0,0.5);
  z-index: 10000;
}

.theme-option {
  display: flex;
  align-items: center;
  gap: 10px;
  color: white;
  padding: 8px 15px;
  cursor: pointer;
  border-radius: 5px;
  transition: background 0.2s;
}

.theme-option:hover {
  background-color: rgba(255,255,255,0.1);
}

body.light-mode {
  --bg-color: #ffffff;
  --card-bg: #f5f5f5;
  --text-light: #000000;
  --text-dark: #444;
}
/* --- START: News Ticker Styles --- */
.news-ticker-container {
    display: flex;
    align-items: stretch; /* লেবেল এবং কনটেন্টকে সমান উচ্চতা দেওয়ার জন্য */
    background-color: #004d40; /* সবুজ ব্যাকগ্রাউন্ড */
    border-radius: 6px;
    overflow: hidden;
    margin: 15px 0 20px 0; /* উপরে ও নিচে কিছুটা জায়গা রাখার জন্য */
    box-shadow: 0 4px 10px rgba(0,0,0,0.5);
    line-height: 1.5; /* লাইন হাইট ঠিক রাখার জন্য */
}
.ticker-label {
    display: flex;
    align-items: center;
    justify-content: center;
    background-color: var(--primary-color); /* থিমের লাল রঙ */
    color: white;
    padding: 10px 20px;
    font-weight: 700;
    font-size: 0.9rem;
    white-space: nowrap; /* লেখা যেন ভেঙ্গে না যায় */
    flex-shrink: 0;
}
.ticker-content {
    flex-grow: 1;
    overflow: hidden;
    position: relative;
    padding: 0 10px;
}
.ticker-text {
    position: absolute;
    top: 15%; /* মাঝখানে আনার জন্য */
    transform: translateY(-50%);
    white-space: nowrap; /* লেখা যেন ভেঙ্গে না যায় */
    font-size: 1rem;
    color: white;
    will-change: transform;
    /* এখানে 60s পরিবর্তন করে স্পিড কন্ট্রোল করতে পারবেন */
    animation: scroll-left 60s linear infinite;
}
@keyframes scroll-left {
    0% {
        transform: translate(100vw, -50%);
    }
    100% {
        transform: translate(-100%, -50%);
    }
}
/* --- END: News Ticker Styles --- */
.theme-toggle {
  position: relative;
  margin-right: 10px;
}

.theme-btn {
  background: none;
  border: none;
  color: white;
  font-size: 1.3rem;
  cursor: pointer;
  transition: transform 0.2s;
}

.theme-btn:hover {
  transform: scale(1.1);
}

.theme-popup {
  position: absolute;
  top: 120%;
  right: 0;
  background-color: var(--card-bg);
  border: 1px solid #333;
  border-radius: 8px;
  display: none;
  flex-direction: column;
  padding: 8px;
  box-shadow: 0 4px 10px rgba(0,0,0,0.5);
  z-index: 10000;
}

.theme-option {
  display: flex;
  align-items: center;
  gap: 10px;
  color: white;
  padding: 8px 15px;
  cursor: pointer;
  border-radius: 5px;
  transition: background 0.2s;
}

.theme-option:hover {
  background-color: rgba(255,255,255,0.1);
}

/* এই অংশটি লাইট মোডের জন্য রঙ পরিবর্তন করবে */
body.light-mode {
  --bg-color: #f0f2f5;
  --card-bg: #ffffff;
  --text-light: #1c1e21;
  --text-dark: #65676b;
  --nav-height: 60px;
}

body.light-mode .bottom-nav,
body.light-mode .mobile-nav-menu,
body.light-mode .search-overlay,
body.light-mode .home-search-form {
    background-color: var(--card-bg);
    color: var(--text-light);
}
body.light-mode .close-btn,
body.light-mode .close-search-btn {
    color: var(--text-light);
}


body.light-mode .home-search-input {
    color: var(--text-light);
}
body.light-mode .home-search-input::placeholder {
      color: var(--text-dark);
}
body.light-mode .news-ticker-container {
    background-color: #e0f2f1; /* হালকা সবুজ ব্যাকগ্রাউন্ড */
}
body.light-mode .ticker-text {
    color: #004d40; /* koyu সবুজ লেখা */
}
body.light-mode .main-footer {
    background-color: #e9ecef;
}
/* === [UPDATED] OTT Platform Section Styles === */
  .platform-section { 
    margin: 40px 0; 
    overflow: hidden; /* স্লাইডারের জন্য এটি জরুরি */
  }
  .platform-slider .swiper-slide { 
    width: 100px; /* প্রতিটি আইটেমের প্রস্থ */
  }
  .platform-item { 
    display: flex; 
    flex-direction: column; 
    align-items: center; 
    justify-content: center; 
    text-decoration: none; 
    color: var(--text-dark); 
    transition: transform 0.2s ease, color 0.2s ease; 
  }
  .platform-item:hover { 
    transform: scale(1.08); 
    color: var(--text-light); 
  }
  .platform-logo-wrapper { 
    width: 80px; 
    height: 80px; 
    border-radius: 50%; /* গোলাকার ডিজাইন */
    background-color: #fff; /* সাদা ব্যাকগ্রাউন্ড */
    display: flex; 
    align-items: center; 
    justify-content: center; 
    margin-bottom: 10px; 
    box-shadow: 0 4px 15px rgba(0,0,0,0.3); 
    border: 2px solid #444; 
    transition: all 0.3s ease;
  }
  .platform-item:hover .platform-logo-wrapper {
    border-color: var(--cyan-accent);
    box-shadow: 0 0 20px rgba(0, 255, 255, 0.4);
  }
  .platform-logo-wrapper img { 
    max-width: 65%; /* লোগোকে একটু ছোট দেখানো হলো */
    max-height: 65%; 
    object-fit: contain; 
  }
  .platform-item span { 
    font-weight: 500; 
    font-size: 0.8rem; 
    text-align: center; 
  }
  .section-title-simple { /* নতুন সিম্পল টাইটেল স্টাইল */
    font-size: 1.6rem; 
    font-weight: 600; 
    margin-bottom: 20px;
    padding-left: 10px;
    border-left: 4px solid var(--primary-color);
  }
/* --- শুধুমাত্র ডেক্সটপ স্ক্রিনের জন্য বড় ডিজাইন --- */
  @media (min-width: 769px) {
    .platform-slider .swiper-slide {
      width: 130px; /* ডেক্সটপের জন্য আইটেমের প্রস্থ বাড়ানো হলো */
    }
    .platform-logo-wrapper {
      width: 100px;  /* লোগোর কন্টেইনার বড় করা হলো */
      height: 100px;
    }
    .platform-item span {
      font-size: 0.9rem; /* নিচের লেখাটিও একটু বড় করা হলো */
    }
  }
/* === [NEW] Featured Badge Style === */
  .featured-badge {
    position: absolute; top: 0; left: 0; background-color: #ffc107; /* হলুদ রঙ */
    color: #000; /* কালো লেখা */
    padding: 4px 12px 4px 8px; font-size: 0.7rem; font-weight: 700;
    z-index: 3; clip-path: polygon(0 0, 100% 0, 85% 100%, 0 100%);
  }

/* === [NEW] Platform Page Header Style === */
.platform-header {
  text-align: center;
  margin-bottom: 20px;
}
.platform-logo-display {
  display: inline-flex;
  justify-content: center;
  align-items: center;
  width: 100px; /* লোগোর সাইজ */
  height: 100px;
  background-color: #fff;
  border-radius: 50%; /* গোলাকার ডিজাইন */
  padding: 15px;
  box-shadow: 0 5px 15px rgba(0,0,0,0.4);
  border: 2px solid #444;
}
.platform-logo-display img {
  max-width: 100%;
  max-height: 100%;
  object-fit: contain;
}
/* === [FINAL] Professional Footer Styles === */
  .professional-footer {
    background: linear-gradient(to bottom, #1a1a1a, #0f0f0f);
    color: var(--text-dark);
    padding-top: 60px;
    margin-top: 50px;
    border-top: 4px solid #000;
  }
  .footer-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
    gap: 40px;
    padding-bottom: 50px;
  }
  .footer-column-title {
    font-size: 1.3rem;
    font-weight: 600;
    color: var(--text-light);
    margin-bottom: 25px;
    position: relative;
    padding-bottom: 10px;
  }
  .footer-column-title::after {
    content: '';
    position: absolute;
    bottom: 0;
    left: 0;
    width: 50px;
    height: 3px;
    background-color: var(--primary-color);
  }
  .footer-logo img {
    max-width: 160px;
    margin-bottom: 15px;
  }
  .footer-description {
    font-size: 0.95rem;
    line-height: 1.7;
  }
  .links-section ul {
    list-style: none; padding: 0; margin: 0;
  }
  .links-section ul li {
    margin-bottom: 12px;
  }
  .links-section ul li a {
    display: flex;
    align-items: center;
    gap: 10px;
    text-decoration: none;
    color: var(--text-dark);
    transition: all 0.2s ease-in-out;
  }
  .links-section ul li a:hover {
    color: var(--primary-color);
    transform: translateX(5px);
  }
  .telegram-buttons-container {
    display: flex;
    flex-direction: column;
    gap: 15px;
  }
  .telegram-button {
    display: flex;
    align-items: center;
    gap: 15px;
    padding: 12px 15px;
    border-radius: 8px;
    text-decoration: none;
    color: white;
    background-color: rgba(255, 255, 255, 0.05);
    border: 1px solid rgba(255, 255, 255, 0.1);
    transition: all 0.2s ease;
  }
  .telegram-button:hover {
    background-color: rgba(255, 255, 255, 0.1);
    border-color: var(--primary-color);
    transform: translateY(-2px);
  }
  .telegram-button i {
    font-size: 1.8rem;
    width: 30px;
    text-align: center;
  }
  .telegram-button.notification i { color: #34B7F1; } /* Telegram Blue */
  .telegram-button.request i { color: #f5c518; } /* Yellow for attention */
  .telegram-button.backup i { color: #28a745; } /* Green for safety */
  .telegram-button span {
    display: flex;
    flex-direction: column;
  }
  .telegram-button small {
    font-size: 0.75rem;
    color: var(--text-dark);
  }
  .footer-note {
    font-size: 0.8rem;
    color: var(--text-dark);
    margin-top: 20px;
    background-color: rgba(0,0,0,0.2);
    padding: 10px;
    border-radius: 5px;
  }
  .footer-note a {
    color: #34B7F1;
    font-weight: bold;
  }
  .footer-bottom-bar {
    background-color: #000;
    text-align: center;
    padding: 20px;
    font-size: 0.9rem;
    border-top: 1px solid #222;
  }
  @media (max-width: 768px) {
    .footer-grid { text-align: center; }
    .footer-column-title::after { left: 50%; transform: translateX(-50%); }
    .footer-logo { margin-left: auto; margin-right: auto; }
    .links-section ul li a { justify-content: center; }
  }
</style>
</head>
<body>
{{ ad_settings.ad_body_top | safe }}
<header class="main-header">
    <div class="container header-content">
    <a href="{{ url_for('home') }}" class="logo">
    <!-- Updated Header Logo -->
    <img src="https://i.postimg.cc/L4kGt56P/1000018917-removebg-preview.png" alt="{{ website_name }} Logo" style="height: 45px; width: auto;">
</a>
    <div style="display: flex; align-items: center;">
        <div class="theme-toggle">
            <button class="theme-btn" aria-label="Toggle Theme"><i class="fas fa-palette"></i></button>
            <div class="theme-popup">
                <div class="theme-option" data-theme="dark"><i class="fas fa-moon"></i> Dark</div>
                <div class="theme-option" data-theme="light"><i class="fas fa-sun"></i> Light</div>
            </div>
        </div>
        <button class="menu-toggle"><i class="fas fa-bars"></i></button>
    </div>
</div>
</header>
<div class="mobile-nav-menu">
    <button class="close-btn">&times;</button>
    <div class="mobile-links">
        <a href="{{ url_for('home') }}">Home</a>
        <a href="{{ url_for('all_movies') }}">All Movies</a>
        <a href="{{ url_for('all_series') }}">All Series</a>
        <a href="{{ url_for('request_content') }}">Request Content</a>
        <a href="{{ url_for('disclaimer') }}">Disclaimer</a>
        <a href="{{ url_for('dmca') }}">DMCA</a>
        <a href="{{ url_for('create_website') }}" class="glowing-link">Create Your Own Website</a>
        <hr>
    </div>
</div>
<main>
  {% macro render_movie_card(m, is_featured=False) %} {# ★ নতুন is_featured ভেরিয়েবল যোগ করা হলো #}
    <a href="{{ url_for('movie_detail', movie_id=m._id) }}" class="movie-card">
      <div class="poster-wrapper">
        <div class="card-preloader">
            <div class="play-button-loader-small"></div>
        </div>
        
        {% if m.vote_average and m.vote_average > 0 %}
            <span class="rating-tag"><i class="fas fa-star"></i> {{ "%.1f"|format(m.vote_average) }}</span>
        {% endif %}

        {# ★ নতুন লজিক: Featured ব্যাজ অথবা NEW ব্যাজ দেখানো হবে #}
        {% if is_featured %}
            <span class="featured-badge">Featured</span>
        {% elif (datetime.utcnow() - m._id.generation_time.replace(tzinfo=None)).days < 7 %}
            <span class="new-badge">NEW</span>
        {% endif %}

        {% if m.poster_badge %}<span class="language-tag">{{ m.poster_badge }}</span>{% endif %}
        <img class="movie-poster" loading="lazy" src="{{ m.poster or 'https://via.placeholder.com/400x600.png?text=No+Image' }}" alt="{{ m.title }}">
        <span class="type-tag">{{ m.type | title }}</span>
      </div>
      <div class="card-info">
        <h4 class="card-title">
          {{ m.title }}
          {% if m.release_year %} ({{ m.release_year }}){% elif m.release_date %} ({{ m.release_date.split('-')[0] }}){% endif %}
        </h4>
      </div>
    </a>
  {% endmacro %}

  {% if is_full_page_list %}
    <div class="full-page-grid-container">
    
    {# <!-- START: Platform Logo Display on List Page (আপনার বিদ্যমান কোড) --> #}
        {% if platform_info and ott_platform_logos.get(platform_info.name) %}
        <div class="platform-header">
            <div class="platform-logo-display">
                <img src="{{ ott_platform_logos[platform_info.name] }}" alt="{{ platform_info.name }} Logo">
            </div>
        </div>
        {% endif %}
    {# <!-- END: Platform Logo Display on List Page --> #}
        
        <h2 class="full-page-grid-title">{{ query }}</h2>
        {% if movies|length == 0 %}<p style="text-align:center;">No content found.</p>
        {% else %}
        <div class="full-page-grid">
            {% for m in movies %}
                {# ★★★ এই লাইনটি পরিবর্তন করতে হবে ★★★ #}
                {{ render_movie_card(m, is_featured=is_featured_page) }}
            {% endfor %}
        </div>
        {% if pagination and pagination.total_pages > 1 %}
        <div class="pagination">
            {% if pagination.has_prev %}<a href="{{ url_for(request.endpoint, page=pagination.prev_num, name=query if 'category' in request.endpoint or 'platform' in request.endpoint else None, genre_name=query.replace('Genres: ', '') if 'genre' in request.endpoint else None) }}">&laquo; Prev</a>{% endif %}
            
            <span class="current">Page {{ pagination.page }} of {{ pagination.total_pages }}</span>
            
            {% if pagination.has_next %}<a href="{{ url_for(request.endpoint, page=pagination.next_num, name=query if 'category' in request.endpoint or 'platform' in request.endpoint else None, genre_name=query.replace('Genres: ', '') if 'genre' in request.endpoint else None) }}">Next &raquo;</a>{% endif %}
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

    <!-- START: New Search Bar Section -->
    <section class="home-search-section container">
        <form action="{{ url_for('home') }}" method="get" class="home-search-form">
            <input type="text" name="q" class="home-search-input" placeholder="Search and explore your favorite content...">
            <button type="submit" class="home-search-button" aria-label="Search">
                <i class="fas fa-search"></i>
            </button>
        </form>
    </section>
    <!-- END: New Search Bar Section -->
    
    <!-- START: News Ticker Section -->
    <section class="container">
        <div class="news-ticker-container">
            <div class="ticker-label">Notice</div>
            <div class="ticker-content">
                <p class="ticker-text">
                    A warm welcome to you at {{ website_name }}. Here you can search and explore all the latest movies and web series. If you can't find your favorite content, feel free to let us know using the 'Request' option. For all the latest updates and news on new releases, please join our official Telegram channel: @PrimeCineZone. Thank you for visiting and stay with us. ••• {{ website_name }} এ আপনাকে আন্তরিকভাবে স্বাগতম। এখানে আপনি নতুন-পুরানো সব মুভি ও সিরিজ সার্চ করতে এবং দেখতে পারবেন। আপনার পছন্দের কোনো কনটেন্ট খুঁজে না পেলে, 'Request' অপশন ব্যবহার করে আমাদের জানাতে পারেন। সর্বশেষ আপডেট এবং নতুন সব কনটেন্টের খবরের জন্য আমাদের টেলিগ্রাম চ্যানেলে যোগ দিন: @PrimeCineZone। আমাদের সাথে থাকার জন্য ধন্যবাদ।
                </p>
            </div>
        </div>
    </section>
    <!-- END: News Ticker Section -->

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

    <!-- START: Updated OTT Platform Slider Section -->
    {% if available_otts %}
    <section class="platform-section container">
        <h2 class="section-title-simple">Available On</h2>
        <div class="swiper platform-slider">
            <div class="swiper-wrapper">
                {% for platform in available_otts %}
                    {% if ott_platform_logos.get(platform) %}
                    <div class="swiper-slide">
                        <a href="{{ url_for('movies_by_platform', platform_name=platform) }}" class="platform-item">
                            <div class="platform-logo-wrapper">
                                <img src="{{ ott_platform_logos[platform] }}" alt="{{ platform }} Logo">
                            </div>
                            <span>{{ platform }}</span>
                        </a>
                    </div>
                    {% endif %}
                {% endfor %}
            </div>
        </div>
    </section>
    {% endif %}
    <!-- END: Updated OTT Platform Slider Section -->

    <div class="container">
      {# এই ম্যাক্রোটি এখন আর ব্যবহার হচ্ছে না, চাইলে রেখে দিতে পারেন বা ডিলিটও করতে পারেন #}
      {% macro render_grid_section(title, movies_list, cat_name) %}
          {% if movies_list %}
          <section class="category-section">
              <div class="category-header">
                  <h2 class="category-title">{{ title }}</h2>
                  <a href="{{ url_for('movies_by_category', name=cat_name) }}" class="view-all-link">View All &rarr;</a>
              </div>
              <div class="category-grid">
                  {% for m in movies_list %}
                      {{ render_movie_card(m) }} {# ★ is_featured=False যোগ করা হলো #}
                  {% endfor %}
              </div>
          </section>
          {% endif %}
      {% endmacro %}

      <!-- START: New Featured Slider Section -->
    {% if featured_content %}
    <section class="category-section">
        <div class="category-header">
            <h2 class="category-title">Featured</h2>
            <a href="{{ url_for('movies_by_category', name='Featured') }}" class="view-all-link">View All &rarr;</a>
        </div>
        <div class="swiper featured-slider">
            <div class="swiper-wrapper">
                {% for m in featured_content %}
                <div class="swiper-slide">
                    {# ★ এখানে is_featured=True পাস করা হচ্ছে #}
                    {{ render_movie_card(m, is_featured=True) }}
                </div>
                {% endfor %}
            </div>
        </div>
    </section>
    {% endif %}
    <!-- END: New Featured Slider Section -->
      
      {% if trending_content %}
      <section class="category-section">
          <div class="category-header">
              <h2 class="category-title">Trending Now</h2>
              <a href="{{ url_for('movies_by_category', name='Trending') }}" class="view-all-link">View All &rarr;</a>
          </div>
          <div class="category-grid">
                  {% for m in trending_content %}
                      {{ render_movie_card(m, is_featured=False) }} {# ★ is_featured=False যোগ করা হলো #}
                  {% endfor %}
              </div>
      </section>
      {% endif %}

      {% if latest_content %}
      <section class="category-section">
          <div class="category-header">
              <h2 class="category-title">Recently Added</h2>
              <a href="{{ url_for('all_content') }}" class="view-all-link">View All &rarr;</a>
          </div>
          <div class="category-grid">
              {% for m in latest_content %}
                  {{ render_movie_card(m) }}
              {% endfor %}
          </div>
      </section>
      {% endif %}
      
      {# বিজ্ঞাপনটি শুধু একবার এখানে থাকবে #}
      {% if ad_settings.ad_list_page %}<div class="ad-container">{{ ad_settings.ad_list_page | safe }}</div>{% endif %}
      
      {% if latest_movies %}
      <section class="category-section">
          <div class="category-header">
              <h2 class="category-title">Latest Movies</h2>
              <a href="{{ url_for('all_movies') }}" class="view-all-link">View All &rarr;</a>
          </div>
          <div class="category-grid">
              {% for m in latest_movies %}
                  {{ render_movie_card(m) }}
              {% endfor %}
          </div>
      </section>
      {% endif %}

      {% if latest_series %}
      <section class="category-section">
          <div class="category-header">
              <h2 class="category-title">Latest Series</h2>
              <a href="{{ url_for('all_series') }}" class="view-all-link">View All &rarr;</a>
          </div>
          <div class="category-grid">
              {% for m in latest_series %}
                  {{ render_movie_card(m) }}
              {% endfor %}
          </div>
      </section>
      {% endif %}

      {% if coming_soon %}
      <section class="category-section">
          <div class="category-header">
              <h2 class="category-title">Coming Soon</h2>
              <a href="{{ url_for('movies_by_category', name='Coming Soon') }}" class="view-all-link">View All &rarr;</a>
          </div>
          <div class="category-grid">
              {% for m in coming_soon %}
                  {{ render_movie_card(m) }}
              {% endfor %}
          </div>
      </section>
      {% endif %}

    </div>
  {% endif %}
</main>
<!-- === [NEW] CREATE WEBSITE SECTION === -->
<section class="create-website-section">
    <div class="container">
        <h2>Want a Website Like This?</h2>
        <a href="{{ url_for('create_website') }}" class="glowing-link">
            <i class="fas fa-star"></i> Create Your Own Website With Us <i class="fas fa-star"></i>
        </a>
    </div>
</section>
<!-- === END OF SECTION === -->

<!-- START: Final Professional Footer -->
<footer class="professional-footer">
    <div class="container footer-grid">
        <!-- Section 1: About the Site -->
        <div class="footer-column about-section">
            <a href="{{ url_for('home') }}" class="footer-logo">
                <!-- Updated Footer Logo -->
                <img src="https://i.postimg.cc/L4kGt56P/1000018917-removebg-preview.png" alt="{{ website_name }} Logo">
            </a>
            <p class="footer-description">
                Your ultimate destination for the latest movies and web series. We are dedicated to providing a seamless entertainment experience.
            </p>
        </div>

        <!-- Section 2: Important Links -->
        <div class="footer-column links-section">
            <h4 class="footer-column-title">Site Links</h4>
            <ul>
                <li><a href="{{ url_for('dmca') }}"><i class="fas fa-gavel"></i> DMCA Policy</a></li>
                <li><a href="{{ url_for('disclaimer') }}"><i class="fas fa-exclamation-triangle"></i> Disclaimer</a></li>
                <li><a href="{{ url_for('create_website') }}"><i class="fas fa-palette"></i> Create Your Website</a></li>
            </ul>
        </div>

        <!-- Section 3: Join Our Community -->
        <div class="footer-column community-section">
            <h4 class="footer-column-title">Join Our Community</h4>
            <div class="telegram-buttons-container">
                <a href="https://t.me/+YhqvLHXHdIViNTRl" target="_blank" class="telegram-button notification">
                    <i class="fas fa-bell"></i>
                    <span><strong>New Content Alerts</strong><small>Get notified for every new upload</small></span>
                </a>
                <a href="https://t.me/+YhqvLHXHdIViNTRl" target="_blank" class="telegram-button request">
                    <i class="fas fa-comments"></i>
                    <span><strong>Join Request Group</strong><small>Request your favorite content</small></span>
                </a>
                <a href="https://t.me/TGLinkBase" target="_blank" class="telegram-button backup">
                    <i class="fas fa-shield-alt"></i>
                    <span><strong>Backup Channel</strong><small>Join for future updates</small></span>
                </a>
            </div>
            <p class="footer-note">
                <strong>Alternatively,</strong> you can use the <a href="{{ url_for('request_content') }}">Request</a> option in our bottom menu to submit requests directly on the site.
            </p>
        </div>
    </div>
    <div class="footer-bottom-bar">
        <p>&copy; {{ datetime.utcnow().year }} {{ website_name }}. All Rights Reserved. Crafted with care for movie lovers.</p>
    </div>
</footer>
<!-- END: Final Professional Footer -->

<nav class="bottom-nav">
  <a href="{{ url_for('home') }}" class="nav-item active"><i class="fas fa-home"></i><span>Home</span></a>
  <a href="{{ url_for('genres_page') }}" class="nav-item"><i class="fas fa-layer-group"></i><span>Genres</span></a>
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
    // === [FINAL & PERFECT] Featured Slider with Correct Rewind & Autoplay ===
    let featuredAutoplayTimeout;

    const featuredSwiper = new Swiper('.featured-slider', {
        // Responsive breakpoints
        breakpoints: {
            320: { slidesPerView: 2, spaceBetween: 15 },
            768: { slidesPerView: 4, spaceBetween: 20 }
        },
        speed: 800,
        loop: false,
    });

    function startFeaturedAutoplay() {
        stopFeaturedAutoplay();
        featuredAutoplayTimeout = setInterval(() => {
            if (featuredSwiper.isEnd) {
                // যদি শেষে পৌঁছে যায়, তাহলে অটো-প্লে থামাও
                stopFeaturedAutoplay();
                // এবং রিওয়াইন্ড প্রক্রিয়া শুরু করো
                setTimeout(() => {
                    featuredSwiper.slideTo(0, 2000); // মসৃণভাবে শুরুতে যাও
                    // রিওয়াইন্ড শেষ হওয়ার পর অটো-প্লে আবার চালু করো
                    setTimeout(() => {
                        startFeaturedAutoplay();
                    }, 2000); // রিওয়াইন্ডের গতির সমান সময়
                }, 1500); // শেষে ১.৫ সেকেন্ড অপেক্ষা
            } else {
                // যদি শেষে না থাকে, তাহলে পরের স্লাইডে যাও
                featuredSwiper.slideNext();
            }
        }, 3000);
    }

    function stopFeaturedAutoplay() {
        clearInterval(featuredAutoplayTimeout);
    }

    const featuredSliderEl = document.querySelector('.featured-slider');
    let featuredInteractionTimeout;

    const onFeaturedInteractionStart = () => {
        stopFeaturedAutoplay();
        clearTimeout(featuredInteractionTimeout);
    };

    const onFeaturedInteractionEnd = () => {
        featuredInteractionTimeout = setTimeout(() => {
            startFeaturedAutoplay();
        }, 3500);
    };

    featuredSliderEl.addEventListener('touchstart', onFeaturedInteractionStart, { passive: true });
    featuredSliderEl.addEventListener('touchend', onFeaturedInteractionEnd, { passive: true });
    featuredSliderEl.addEventListener('mouseenter', onFeaturedInteractionStart);
    featuredSliderEl.addEventListener('mouseleave', onFeaturedInteractionEnd);

    startFeaturedAutoplay();
    
    // === [ADVANCED & CUSTOM LOOP] OTT Platform Slider ===
    let autoplayTimeout; // একটি টাইমার ভেরিয়েবল তৈরি করা হলো

    const platformSwiper = new Swiper('.platform-slider', {
        slidesPerView: 'auto',
        spaceBetween: 25,
        speed: 800,
        loop: false, // <-- গুরুত্বপূর্ণ: ডিফল্ট লুপ বন্ধ থাকবে

        // স্লাইডার যখন শেষ প্রান্তে পৌঁছাবে তখন কী হবে
        on: {
            reachEnd: function () {
                // ১ সেকেন্ড অপেক্ষা করা হবে
                setTimeout(() => {
                    // মসৃণভাবে প্রথম স্লাইডে ফিরে যাবে
                    this.slideTo(0, 1500); // দ্বিতীয় প্যারামিটারটি হলো ফিরে যাওয়ার গতি (ms)
                }, 1000); // ১ সেকেন্ড (1000ms)
            },
        },
    });

    // অটো-প্লে ফাংশন
    function startAutoplay() {
        stopAutoplay(); // পুরোনো টাইমার বন্ধ করা হলো
        autoplayTimeout = setInterval(() => {
            // যদি স্লাইডার শেষ প্রান্তে না থাকে, তাহলে পরের স্লাইডে যাও
            if (!platformSwiper.isEnd) {
                platformSwiper.slideNext();
            }
            // যদি শেষ প্রান্তে থাকে, তাহলে 'reachEnd' ইভেন্টটি বাকি কাজ করবে
        }, 3000); // ৩ সেকেন্ড পর পর স্লাইড হবে
    }

    // অটো-প্লে বন্ধ করার ফাংশন
    function stopAutoplay() {
        clearInterval(autoplayTimeout);
    }

    // স্লাইডারের মূল এলিমেন্টটি সিলেক্ট করা
    const platformSliderEl = document.querySelector('.platform-slider');
    let interactionTimeout; // ব্যবহারকারীর ইন্টারেকশনের জন্য টাইমার

    // ব্যবহারকারী যখন স্লাইডার স্পর্শ করবে বা মাউস দিয়ে ধরবে
    const onInteractionStart = () => {
        stopAutoplay();
        clearTimeout(interactionTimeout); // পুরোনো রিস্টার্ট টাইমার বন্ধ করা
    };

    // ব্যবহারকারী যখন স্পর্শ ছেড়ে দেবে বা মাউস সরাবে
    const onInteractionEnd = () => {
        // ৩.৫ সেকেন্ড পর অটো-প্লে রিস্টার্ট করার জন্য টাইমার সেট করা
        interactionTimeout = setTimeout(() => {
            startAutoplay();
        }, 3500); // ৩.৫ সেকেন্ড
    };

    // ইভেন্ট লিসেনারগুলো যোগ করা
    platformSliderEl.addEventListener('touchstart', onInteractionStart, { passive: true });
    platformSliderEl.addEventListener('touchend', onInteractionEnd, { passive: true });
    platformSliderEl.addEventListener('mouseenter', onInteractionStart);
    platformSliderEl.addEventListener('mouseleave', onInteractionEnd);

    // পেজ লোড হওয়ার সাথে সাথে অটো-প্লে চালু করা
    startAutoplay();

    // এই ফাংশনটি সকল কনটেন্ট কার্ডে লোডার যুক্ত করার জন্য
    function initializeCardLoaders() {
        const contentLinks = document.querySelectorAll('.movie-card');
        
        contentLinks.forEach(card => {
            card.addEventListener('click', function(event) {
                // লিঙ্কের স্বাভাবিক আচরণে বাধা দেওয়া হচ্ছে
                event.preventDefault();
                
                // শুধুমাত্র ক্লিক করা কার্ডের ভেতরের preloader খুঁজে বের করা হচ্ছে
                const preloader = this.querySelector('.card-preloader');
                if (preloader) {
                    preloader.classList.add('active'); // লোডারটি দৃশ্যমান করা হচ্ছে
                }

                const destinationUrl = this.href;
                
                // একটি ছোট্ট সময় দেওয়া হচ্ছে যাতে ব্রাউজার লোডারটি দেখানোর সুযোগ পায়
                setTimeout(() => {
                    window.location.href = destinationUrl; // এরপর নতুন পেজে নিয়ে যাওয়া হচ্ছে
                }, 150); 
            });
        });
    }

    // পুরো পেজ লোড হওয়ার পর উপরের ফাংশনটি চালু করা হচ্ছে
    document.addEventListener('DOMContentLoaded', function() {
        initializeCardLoaders();
    });

    /* ... আপনার বিদ্যমান কোড ... */
    // ব্রাউজারের Back বাটনে ক্লিক করলে ক্যাশ থেকে পেজ লোড হওয়ার সমস্যা সমাধান
    window.addEventListener('pageshow', function(event) {
        if (event.persisted) {
            document.querySelectorAll('.card-preloader.active').forEach(preloader => {
                preloader.classList.remove('active');
            });
        }
    });
    
// --- [NEW] Pagination Jump Functionality (FINAL FIX) ---
const initializePaginationJump = () => {
    const pageJumpInput = document.getElementById('page-jump-input');
    const pageJumpBtn = document.getElementById('page-jump-btn'); 
    
    // পেজ জাম্প ফাংশন
    const goToPage = () => {
        if (!pageJumpInput) return;
        
        const totalPages = parseInt(pageJumpInput.getAttribute('max'));
        let pageNumber = parseInt(pageJumpInput.value);
        
        // ইনপুট ভ্যালিডেশন
        if (isNaN(pageNumber) || pageNumber < 1) {
            pageNumber = 1;
        } else if (pageNumber > totalPages) {
            pageNumber = totalPages;
        }
        
        // বর্তমান URL থেকে 'page' প্যারামিটার পরিবর্তনের লজিক
        const url = new URL(window.location.href);
        
        // 1. URL থেকে যদি q (search) থাকে, তা মুছে ফেলা
        // 2. page প্যারামিটার সেট করা
        url.searchParams.set('page', pageNumber);
        
        // নতুন URL এ রিডাইরেক্ট
        window.location.href = url.toString();
    };

    if (pageJumpInput) {
        // Enter key functionality
        pageJumpInput.addEventListener('keydown', function(event) {
            if (event.key === 'Enter') {
                goToPage();
            }
        });
    }

    if (pageJumpBtn) { 
        pageJumpBtn.addEventListener('click', goToPage);
    }
};

document.addEventListener('DOMContentLoaded', function() {
    // নিশ্চিত করুন যে পেজিনেশন ফাংশনটি DOM লোড হওয়ার পরে কল হচ্ছে
    initializePaginationJump();
    
    // অন্যান্য ফাংশন যেমন initializeCardLoaders
    if (typeof initializeCardLoaders === 'function') {
        initializeCardLoaders();
    }
});
// --- [NEW] Pagination Jump Functionality End ---
    
    // --- [NEW] Theme Switcher Logic ---
    const themeBtn = document.querySelector('.theme-btn');
    const themePopup = document.querySelector('.theme-popup');
    const themeOptions = document.querySelectorAll('.theme-option');

    // Function to apply the saved theme on page load
    const applyTheme = (theme) => {
        if (theme === 'light') {
            document.body.classList.add('light-mode');
        } else {
            document.body.classList.remove('light-mode');
        }
    };

    // Immediately apply theme from localStorage to prevent flash
    const savedTheme = localStorage.getItem('theme') || 'dark';
    applyTheme(savedTheme);

    // Toggle popup visibility
    themeBtn.addEventListener('click', () => {
        const isDisplayed = themePopup.style.display === 'flex';
        themePopup.style.display = isDisplayed ? 'none' : 'flex';
    });

    // Handle theme selection
    themeOptions.forEach(option => {
        option.addEventListener('click', () => {
            const selectedTheme = option.getAttribute('data-theme');
            localStorage.setItem('theme', selectedTheme);
            applyTheme(selectedTheme);
            themePopup.style.display = 'none'; // Hide popup after selection
        });
    });

    // Hide popup if clicked outside
    document.addEventListener('click', (event) => {
        if (!themeBtn.contains(event.target) && !themePopup.contains(event.target)) {
            themePopup.style.display = 'none';
        }
    });
</script>
{{ ad_settings.ad_footer | safe }}
</body></html>
"""
# নিশ্চিত করুন এর আগের ভেরিয়েবলটি """ দিয়ে শেষ হয়েছে।
# তারপর নিচের কোডটি শুরু হবে:

detail_html = """
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no" />
<title>{{ movie.title if movie else "Content Not Found" }} - {{ website_name }}</title>
<!-- LOGO FIXED HERE -->
<link rel="icon" href="https://i.postimg.cc/L4kGt56P/1000018917-removebg-preview.png" type="image/png">
<meta name="description" content="{{ movie.overview|striptags|truncate(160) }}">
<meta name="keywords" content="{{ movie.title }}, movie details, download {{ movie.title }}, {{ website_name }}">
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic" crossorigin><link href="https://fonts.googleapis.com/css2?family=Poppins:wght@300;400;500;600;700&display=swap" rel="stylesheet">
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.2.0/css/all.min.css">
<link rel="stylesheet" href="https://unpkg.com/swiper/swiper-bundle.min.css"/>
{{ ad_settings.ad_header | safe }}
<style>
  :root {--primary-color: #E50914; --watch-color: #007bff; --bg-color: #141414;--card-bg: #1a1a1a;--text-light: #ffffff;--text-dark: #a0a0a0;}
  html { box-sizing: border-box; } *, *:before, *:after { box-sizing: inherit; }
  body { font-family: 'Poppins', sans-serif; background-color: var(--bg-color); color: var(--text-light); overflow-x: hidden; }
  a { text-decoration: none; color: inherit; }
  .container { max-width: 1200px; margin: 0 auto; padding: 0 15px; }

  .page-header { padding: 20px 15px 15px 15px; }
  .go-back-btn { display: inline-flex; align-items: center; gap: 10px; background-color: rgba(45, 45, 45, 0.9); color: #fff; padding: 10px 20px; border-radius: 12px; font-size: 1rem; font-weight: 500; }
  .hero-section-wrapper { margin: 0 15px 30px 15px; position: relative; overflow: visible; margin-bottom: 120px; }
  .detail-hero-backdrop { width: 100%; aspect-ratio: 16 / 9; border-radius: 16px; overflow: hidden; position: relative; box-shadow: 0 0 30px 0 rgba(0, 255, 255, 0.25); border: 1px solid rgba(0, 255, 255, 0.2); background-color: #000; }
  .hero-backdrop-img { position: absolute; top: 0; left: 0; width: 100%; height: 100%; object-fit: cover; z-index: 1; }
  .hero-overlay { position: absolute; top: 0; left: 0; width: 100%; height: 100%; z-index: 2; background: linear-gradient(180deg, rgba(20,20,20,0) 50%, rgba(20,20,20,0.8) 100%); }
  .overlay-poster { position: absolute; z-index: 4; bottom: -80px; left: 20px; width: 35%; max-width: 150px; border-radius: 12px; border: 3px solid rgba(255, 255, 255, 0.15); box-shadow: 0 15px 35px rgba(0,0,0,0.8); }
  .content-type-badge { position: absolute; z-index: 3; bottom: 20px; right: 20px; background-color: #00ff00; color: #000; padding: 10px 25px; border-radius: 10px; font-size: 0.9rem; font-weight: 700; text-transform: uppercase; }
  
  .content-info-section { padding: 20px; }
  .detail-title { font-size: 2rem; font-weight: 700; line-height: 1.3; margin-bottom: 15px; }
  .detail-meta { display: flex; flex-wrap: wrap; gap: 10px 20px; color: var(--text-dark); margin-bottom: 20px; font-size: 0.9rem; }
  .meta-item { display: flex; align-items: center; gap: 8px; }
  .meta-item.rating { color: #f5c518; font-weight: 600; }
  .detail-overview { font-size: 1rem; line-height: 1.7; color: var(--text-dark); margin-bottom: 30px; }
  
  .section-title { font-size: 1.5rem; font-weight: 700; margin: 30px 0 20px 0; padding-bottom: 5px; border-bottom: 2px solid var(--primary-color); display: inline-block; }
  .ad-container { margin: 30px 0; text-align: center; }
  .links-wrapper { margin-top: 10px; }
  .links-container { display: flex; flex-wrap: wrap; gap: 40px; align-items: flex-start; }
  .link-section { flex: 1; min-width: 250px; }
  .download-button { display: block; width: 100%; padding: 12px 20px; color: white; text-decoration: none; border-radius: 4px; font-weight: 700; transition: background-color 0.3s ease; margin-bottom: 10px; text-align: center; background-color: var(--primary-color); }
  .download-button:hover { background-color: #f61f29; }
  .telegram-button { background-color: #2AABEE; display: flex; align-items: center; justify-content: center; gap: 10px; }
  .telegram-button:hover { background-color: #1e96d1; }
  .telegram-button i { font-size: 1.2rem; }
  
  .episode-item { display: flex; flex-direction: column; align-items: stretch; margin-bottom: 15px; padding: 15px; border-radius: 5px; background-color: var(--card-bg); border-left: 4px solid var(--primary-color); }
  .episode-info { display: flex; justify-content: space-between; align-items: center; margin-bottom: 15px; flex-wrap: wrap; }
  .episode-title { font-size: 1.1rem; font-weight: 500; color: #fff; }
  .episode-buttons { display: flex; flex-wrap: wrap; gap: 10px; }
  .episode-button { display: inline-flex; flex: 1; justify-content: center; align-items: center; gap: 8px; padding: 10px 15px; color: white; border-radius: 4px; font-weight: 700; transition: background-color 0.3s ease; text-align: center; }
  .episode-button.stream-btn { background-color: #007bff; } .episode-button.stream-btn:hover { background-color: #0069d9; }
  .episode-button.download-btn { background-color: var(--primary-color); } .episode-button.download-btn:hover { background-color: #f61f29; }
  .episode-button.custom-btn { background-color: #555; } .episode-button.custom-btn:hover { background-color: #444; }

  .trailer-section { margin: 0 0 40px 0; }
  .trailer-section h2 { font-size: 1.5rem; font-weight: 600; margin-bottom: 20px; }
  .trailer-video-wrap { position: relative; width: 100%; max-width: 900px; margin: 0 auto; aspect-ratio: 16 / 9; border-radius: 12px; overflow: hidden; }
  .trailer-video-wrap iframe { position: absolute; width: 100%; height: 100%; top: 0; left: 0; border: 0; }
  .related-content { margin-top: 50px; }
  .movie-carousel .swiper-slide { width: 150px; }
  .card-title { font-size: 0.9rem; font-weight: 500; }
  .card-meta { font-size: 0.8rem; color: var(--text-dark); }
  .swiper-button-next, .swiper-button-prev { color: var(--text-light); display: none; }

  @media (min-width: 768px) {
    .container { padding: 0 40px; }
    .hero-section-wrapper { margin: 0 40px 40px 40px; margin-bottom: 60px; }
    .overlay-poster { left: 50px; bottom: -80px; max-width: 220px; }
    .content-info-section { padding-left: 300px; }
    .detail-title { font-size: 2.5rem; }
    .movie-carousel .swiper-slide { width: 180px; }
    .swiper-button-next, .swiper-button-prev { display: flex; }
  }
  .category-section { margin: 50px 0; }
  .category-title { font-size: 1.5rem; font-weight: 600; }
  .movie-carousel .swiper-slide { width: 150px; }
  .movie-card { display: block; }
  .movie-poster { 
    width: 100%; 
    aspect-ratio: 2 / 3; 
    object-fit: cover; 
    border-radius: 8px; 
    margin-bottom: 10px; 
  }
  @media (min-width: 768px) {
    .movie-carousel .swiper-slide { width: 220px; }
  }
  /* === You Might Also Like Grid & Card Styles (Final Version) === */
  .category-section { margin-top: 50px; }
  .category-header { margin-bottom: 20px; }
  .category-title {
      font-size: 1.5rem; font-weight: 600; padding-bottom: 5px;
      border-bottom: 2px solid var(--primary-color); display: inline-block;
  }

  /* গ্রিড লেআউট */
  .related-grid {
      display: grid;
      grid-template-columns: repeat(3, 1fr);
      gap: 15px;
  }

  /* প্রতিটি কার্ডের স্টাইল */
  .movie-card {
      display: block; border-radius: 12px; overflow: hidden;
      background-color: var(--card-bg); border: 1px solid #2a2a2a;
      transition: transform 0.2s ease, box-shadow 0.2s ease;
  }
  .movie-card:hover {
      transform: translateY(-5px); box-shadow: 0 8px 25px rgba(0, 0, 0, 0.5);
  }

  /* পোস্টার এবং ব্যাজগুলোর ধারক */
  .poster-wrapper { position: relative; }
  .movie-poster {
      width: 100%; aspect-ratio: 2 / 3;
      object-fit: cover; display: block;
  }

  /* কার্ডের নিচের তথ্যের অংশ */
  .card-info { padding: 12px; }
  .card-title {
      font-size: 0.9rem; font-weight: 500; color: var(--text-light);
      margin: 0; line-height: 1.4; min-height: 2.8em;
      display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden;
  }

  /* --- ব্যাজ কন্টেইনার এবং গ্রুপিং --- */
  .badges-top, .badges-bottom {
      position: absolute; left: 0; right: 0;
      display: flex; justify-content: space-between;
      align-items: center; z-index: 2; pointer-events: none;
  }
  .badges-top { top: 0; } /* Top: 0 করা হলো যেন NEW ব্যাজ কোণায় থাকে */
  .badges-bottom { bottom: 8px; padding: 0 8px; }
  .badge-group-left, .badge-group-right {
      display: flex; gap: 6px; pointer-events: all;
      align-items: center; /* ব্যাজগুলোকে উল্লম্বভাবে মাঝখানে রাখে */
  }
  .badges-top .badge-group-right { padding-right: 8px; } /* ডানপাশের ব্যাজের জন্য প্যাডিং */

  /* --- অন্যান্য ব্যাজের স্টাইল (Rating, Series, Language) --- */
  .language-tag, .rating-tag, .type-tag {
      padding: 4px 10px; font-size: 0.75rem; font-weight: 600;
      border-radius: 6px; color: white; display: inline-flex;
      align-items: center; gap: 4px;
  }
  .language-tag { background-color: rgba(0, 0, 0, 0.7); }
  .rating-tag { background-color: rgba(245, 197, 24, 0.9); color: #000; }
  .type-tag { background-color: #00E599; color: #000; }

  /* --- শুধুমাত্র NEW ব্যাজের জন্য বিশেষ ডিজাইন --- */
  .new-badge {
      background-color: var(--primary-color);
      color: white;
      font-weight: 700;
      padding: 4px 12px 4px 8px; /* ডানদিকে বেশি প্যাডিং slanting এর জন্য */
      font-size: 0.7rem;
      /* এই clip-path কোডটিই মূল ডিজাইনটি তৈরি করে */
      clip-path: polygon(0 0, 100% 0, 85% 100%, 0 100%);
  }

  /* ==============================================
     ==== শুধুমাত্র মোবাইল ডিভাইসের জন্য পরিবর্তন ====
     ============================================== */
  @media (max-width: 768px) {
      .related-grid { gap: 10px; }
      .card-title { font-size: 0.8rem; }
      .badges-bottom { bottom: 6px; padding: 0 6px; }

      /* মোবাইলের জন্য অন্যান্য ব্যাজ ছোট করা হলো */
      .language-tag, .rating-tag, .type-tag {
          padding: 2px 7px;
          font-size: 0.6rem;
          border-radius: 4px;
      }
      /* মোবাইলের জন্য NEW ব্যাজের সাইজ ঠিক করা হলো */
      .new-badge {
          padding: 3px 10px 3px 6px;
          font-size: 0.6rem;
      }
  }
  
  /* ডেস্কটপের জন্য ৪ কলাম */
  @media (min-width: 769px) {
      .related-grid {
          grid-template-columns: repeat(4, 1fr);
      }
  }

  /* Preloader Styles */
  .card-preloader { position: absolute; top: 0; left: 0; width: 100%; height: 100%; background-color: rgba(0, 0, 0, 0.75); z-index: 5; display: none; justify-content: center; align-items: center; backdrop-filter: blur(4px); }
  .card-preloader.active { display: flex; }
  .play-button-loader-small { width: 40px; height: 40px; border: 4px solid rgba(255, 255, 255, 0.4); border-top-color: #fff; border-radius: 50%; animation: spin 1s ease-in-out infinite; }
  @keyframes spin { to { transform: rotate(360deg); } }
  /* === [নতুন] লাইট মোড থিমের জন্য স্টাইল === */
body.light-mode {
  --bg-color: #f0f2f5;
  --card-bg: #ffffff;
  --text-light: #1c1e21;
  --text-dark: #65676b;
}

body.light-mode .go-back-btn {
    background-color: #e9ecef;
    color: #495057;
    border: 1px solid #dee2e6;
}

body.light-mode .hero-section-wrapper {
    margin-bottom: 40px; /* পোস্টারের নিচের গ্যাপ ঠিক রাখা */
}

body.light-mode .detail-hero-backdrop {
    box-shadow: 0 8px 25px rgba(0,0,0,0.1);
    border: 1px solid #e9ecef;
}

body.light-mode .overlay-poster {
    border-color: rgba(0,0,0,0.1);
}

body.light-mode .episode-item {
    border-left-color: #007bff; /* অন্য একটি রঙ দেওয়া হলো */
}
/* ========================================= */
.main-footer {
  text-align: center;
  padding: 15px 10px;
  background-color: #111;
  color: #ccc;
  font-size: 0.9rem;
  border-top: 1px solid rgba(255,255,255,0.1);
  margin-top: 40px;
  transition: background 0.3s;
}

.main-footer:hover {
  background-color: #222;
  color: #fff;
}
/* === [নতুন] রিপোর্ট বাটনের জন্য স্টাইল === */
  .report-button {
      display: inline-flex;
      align-items: center;
      gap: 10px;
      background-color: #555;
      color: #fff;
      padding: 12px 25px;
      border-radius: 8px;
      font-size: 1rem;
      font-weight: 500;
      border: 1px solid #666;
      transition: background-color 0.2s ease;
  }
  .report-button:hover {
      background-color: #6c757d;
  }
  .report-button i {
      font-size: 1.1rem;
  }
  /* ... আপনার বিদ্যমান CSS কোড ... */
/* === [NEW] Floating Edit Button Style for Admin Quick Access === */
.edit-icon-link {
    position: absolute;
    top: 20px; /* Adjust vertical position */
    right: 20px; /* Adjust horizontal position */
    background-color: rgba(0, 0, 0, 0.6);
    color: #fff;
    padding: 10px;
    width: 40px;
    height: 40px;
    display: flex;
    justify-content: center;
    align-items: center;
    border-radius: 50%;
    font-size: 1.2rem;
    transition: background-color 0.2s, transform 0.2s;
    z-index: 10;
    border: 2px solid #555;
    box-shadow: 0 4px 10px rgba(0,0,0,0.5);
}
.edit-icon-link:hover {
    background-color: var(--primary-color);
    border-color: var(--primary-color);
    transform: scale(1.1);
}
@media (min-width: 768px) {
    .edit-icon-link {
        right: 50px;
    }
}
/* ... আপনার বিদ্যমান CSS কোড ... */
/* === [FINAL] Professional Footer Styles === */
  .professional-footer {
    background: linear-gradient(to bottom, #1a1a1a, #0f0f0f);
    color: var(--text-dark);
    padding-top: 60px;
    margin-top: 50px;
    border-top: 4px solid #000;
  }
  .footer-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
    gap: 40px;
    padding-bottom: 50px;
  }
  .footer-column-title {
    font-size: 1.3rem;
    font-weight: 600;
    color: var(--text-light);
    margin-bottom: 25px;
    position: relative;
    padding-bottom: 10px;
  }
  .footer-column-title::after {
    content: '';
    position: absolute;
    bottom: 0;
    left: 0;
    width: 50px;
    height: 3px;
    background-color: var(--primary-color);
  }
  .footer-logo img {
    max-width: 160px;
    margin-bottom: 15px;
  }
  .footer-description {
    font-size: 0.95rem;
    line-height: 1.7;
  }
  .links-section ul {
    list-style: none; padding: 0; margin: 0;
  }
  .links-section ul li {
    margin-bottom: 12px;
  }
  .links-section ul li a {
    display: flex;
    align-items: center;
    gap: 10px;
    text-decoration: none;
    color: var(--text-dark);
    transition: all 0.2s ease-in-out;
  }
  .links-section ul li a:hover {
    color: var(--primary-color);
    transform: translateX(5px);
  }
  .telegram-buttons-container {
    display: flex;
    flex-direction: column;
    gap: 15px;
  }
  .telegram-button {
    display: flex;
    align-items: center;
    gap: 15px;
    padding: 12px 15px;
    border-radius: 8px;
    text-decoration: none;
    color: white;
    background-color: rgba(255, 255, 255, 0.05);
    border: 1px solid rgba(255, 255, 255, 0.1);
    transition: all 0.2s ease;
  }
  .telegram-button:hover {
    background-color: rgba(255, 255, 255, 0.1);
    border-color: var(--primary-color);
    transform: translateY(-2px);
  }
  .telegram-button i {
    font-size: 1.8rem;
    width: 30px;
    text-align: center;
  }
  .telegram-button.notification i { color: #34B7F1; } /* Telegram Blue */
  .telegram-button.request i { color: #f5c518; } /* Yellow for attention */
  .telegram-button.backup i { color: #28a745; } /* Green for safety */
  .telegram-button span {
    display: flex;
    flex-direction: column;
  }
  .telegram-button small {
    font-size: 0.75rem;
    color: var(--text-dark);
  }
  .footer-note {
    font-size: 0.8rem;
    color: var(--text-dark);
    margin-top: 20px;
    background-color: rgba(0,0,0,0.2);
    padding: 10px;
    border-radius: 5px;
  }
  .footer-note a {
    color: #34B7F1;
    font-weight: bold;
  }
  .footer-bottom-bar {
    background-color: #000;
    text-align: center;
    padding: 20px;
    font-size: 0.9rem;
    border-top: 1px solid #222;
  }
  @media (max-width: 768px) {
    .footer-grid { text-align: center; }
    .footer-column-title::after { left: 50%; transform: translateX(-50%); }
    .footer-logo { margin-left: auto; margin-right: auto; }
    .links-section ul li a { justify-content: center; }
  }
  /* === [FINAL & RESPONSIVE] Auto-Changing Gallery Styles === */
.gallery-section {
    margin: 40px 0;
}

/* Keyframes for the animated RGB border (Remains the same) */
@keyframes rgb-glow-border {
    0%   { border-color: #ff00de; box-shadow: 0 0 8px #ff00de; }
    25%  { border-color: #00ffff; box-shadow: 0 0 10px #00ffff; }
    50%  { border-color: #00ff7f; box-shadow: 0 0 8px #00ff7f; }
    75%  { border-color: #f83d61; box-shadow: 0 0 10px #f83d61; }
    100% { border-color: #ff00de; box-shadow: 0 0 8px #ff00de; }
}

/* This wrapper centers the gallery and handles the layout change */
.gallery-content-wrapper {
    max-width: 90%; /* For mobile view */
    margin: 0 auto;
}

/* Base styles for all gallery items (Mobile First) */
.gallery-item a {
    display: block;
    position: relative;
    padding-top: 56.25%; /* 16:9 Aspect Ratio */
    border-radius: 8px;
    overflow: hidden;
    border: 2px solid transparent;
    animation: rgb-glow-border 5s linear infinite;
}
.gallery-item img {
    position: absolute;
    top: 0;
    left: 0;
    width: 100%;
    height: 100%;
    object-fit: cover;
    transition: opacity 0.7s ease-in-out;
}

/* The stack of thumbnails for mobile */
.thumbnail-stack {
    display: flex;
    flex-direction: column;
    gap: 10px;
    margin-top: 10px;
}

/* Special styles for the top auto-changing item */
#auto-change-item .changing-image {
    opacity: 0;
}
#auto-change-item .changing-image.active {
    opacity: 1;
}

/* --- DESKTOP STYLES (Applied on screens wider than 768px) --- */
@media (min-width: 768px) {
    .gallery-content-wrapper {
        display: grid;
        grid-template-columns: 2fr 1fr; /* 2/3 for hero, 1/3 for thumbnails */
        gap: 15px;
        max-width: 1200px; /* Limit max width on very large screens */
    }
    
    .hero-image-container {
        grid-column: 1 / 2; /* Place in the first column */
    }

    .thumbnail-stack {
        grid-column: 2 / 3; /* Place in the second column */
        display: grid;
        grid-template-columns: 1fr 1fr; /* 2x2 grid for thumbnails */
        gap: 10px;
        margin-top: 0;
    }
}
/* ... আপনার অন্যান্য CSS কোডের সাথে যোগ করুন ... */

/* === [NEW] Download Hub Section Styles === */
.download-hub-section {
    background-color: var(--card-bg);
    border: 1px solid #2a2a2a;
    border-radius: 12px;
    padding: 25px;
    margin: 40px auto;
    max-width: 800px;
    text-align: center;
}
.hub-section-title {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 12px;
    font-size: 1.5rem;
    font-weight: 600;
    margin: 0 0 10px 0;
}
.hub-section-description {
    color: var(--text-dark);
    margin: 0 0 25px 0;
    font-size: 1rem;
    line-height: 1.6;
}
.hub-proceed-button {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    gap: 12px;
    background-color: var(--primary-color);
    color: white;
    padding: 15px 35px;
    border-radius: 8px;
    font-size: 1.2rem;
    font-weight: 700;
    text-decoration: none;
    transition: all 0.2s ease;
    border: none;
    cursor: pointer;
    box-shadow: 0 4px 15px rgba(229, 9, 20, 0.3);
}
.hub-proceed-button:hover {
    transform: translateY(-2px);
    box-shadow: 0 6px 20px rgba(229, 9, 20, 0.5);
    filter: brightness(1.1);
}

/* ===== Enhanced Loading Spinner ===== */
.custom-loading-container {
    position: relative;
    width: 100%;
    max-width: 600px;
    margin: 50px auto;
    padding: 60px 0;
    text-align: center;
    background: #111;
    border-radius: 12px;
    box-shadow: 0 0 25px rgba(0,0,0,0.5);
}

.custom-loading-spinner {
    margin: 0 auto 25px;
    width: 100px;
    height: 100px;
    border: 10px solid #444; /* Outer color */
    border-top: 10px solid #ff0000; /* Red top border */
    border-radius: 50%;
    animation: enhanced-spin 1s linear infinite;
    display: block; /* নিশ্চিত করে div দেখা যাবে */
}

.custom-loading-text {
    color: #fff;
    font-size: 1.3rem;
    font-weight: bold;
    line-height: 1.4;
}

@keyframes enhanced-spin {
    0% { transform: rotate(0deg); }
    100% { transform: rotate(360deg); }
}

/* Responsive */
@media(max-width: 600px){
    .custom-loading-spinner {
        width: 70px;
        height: 70px;
        border-width: 8px;
    }
    .custom-loading-text {
        font-size: 1.1rem;
    }
}
</style>
</head>
<body>
{{ ad_settings.ad_body_top | safe }}

{# === এই ম্যাক্রোটি এখানে যোগ করুন === #}
{% macro render_movie_card(m) %}
    <a href="{{ url_for('movie_detail', movie_id=m._id) }}" class="movie-card">
      <div class="poster-wrapper">
        {# Card preloader আগের মতোই থাকবে #}
        <div class="card-preloader">
            <div class="play-button-loader-small"></div>
        </div>

        {# উপরের ব্যাজগুলোর জন্য কন্টেইনার #}
        <div class="badges-top">
            <div class="badge-group-left">
                {% if (datetime.utcnow() - m._id.generation_time.replace(tzinfo=None)).days < 7 %}
                    <span class="new-badge">NEW</span>
                {% endif %}
            </div>
            <div class="badge-group-right">
                {% if m.poster_badge %}
                    <span class="language-tag">{{ m.poster_badge }}</span>
                {% endif %}
            </div>
        </div>

        <img class="movie-poster" loading="lazy" src="{{ m.poster or 'https://via.placeholder.com/400x600.png?text=No+Image' }}" alt="{{ m.title }}">

        {# নিচের ব্যাজগুলোর জন্য কন্টেইনার #}
        <div class="badges-bottom">
            <div class="badge-group-left">
                {% if m.vote_average and m.vote_average > 0 %}
                    <span class="rating-tag"><i class="fas fa-star"></i> {{ "%.1f"|format(m.vote_average) }}</span>
                {% endif %}
            </div>
            <div class="badge-group-right">
                <span class="type-tag">{{ m.type | title }}</span>
            </div>
        </div>
      </div>
      <div class="card-info">
        <h4 class="card-title">
          {{ m.title }}
          {% if m.release_year %} ({{ m.release_year }}){% elif m.release_date %} ({{ m.release_date.split('-')[0] }}){% endif %}
        </h4>
      </div>
    </a>
{% endmacro %}
{# ================================ #}

{% if movie %}
<div class="page-header" style="position: relative;">
    <a href="{{ url_for('home') }}" class="go-back-btn"><i class="fas fa-arrow-left"></i><span> Go Back</span></a>
    
    <!-- ★★★ নতুন এডিট বাটনটি এখানে যোগ করুন ★★★ -->
    {% if movie %}
        <a href="{{ url_for('edit_auth_redirect', movie_id=movie._id) }}" class="edit-icon-link" title="Edit Content" onclick="return confirm('You are about to enter the Admin Edit area. Continue?')">
            <i class="fas fa-pencil-alt"></i>
        </a>
    {% endif %}
    <!-- ★★★ নতুন এডিট বাটন শেষ ★★★ -->
</div>
<div class="hero-section-wrapper">
    <div class="detail-hero-backdrop"><img src="{{ movie.backdrop or movie.poster }}" class="hero-backdrop-img" alt="Backdrop"><div class="hero-overlay"></div></div>
    <img src="{{ movie.poster or 'https://via.placeholder.com/400x600.png?text=No+Image' }}" alt="{{ movie.title }}" class="overlay-poster">
    {% if movie.type %}<div class="content-type-badge">{{ movie.type | title }}</div>{% endif %}
</div>
<div class="container content-info-section">
    <div class="detail-info">
        <h1 class="detail-title">{{ movie.title }}</h1>
        <div class="detail-meta">
            {% if movie.vote_average %}<div class="meta-item rating"><i class="fas fa-star"></i> {{ "%.1f"|format(movie.vote_average) }}</div>{% endif %}
            {% if movie.release_year %}<div class="meta-item"><i class="fas fa-calendar-alt"></i> {{ movie.release_year }}</div>{% elif movie.release_date %}<div class="meta-item"><i class="fas fa-calendar-alt"></i> {{ movie.release_date.split('-')[0] }}</div>{% endif %}
            {% if movie.languages %}<div class="meta-item"><i class="fas fa-language"></i> {{ movie.languages | join(' / ') }}</div>{% endif %}
            {% if movie.genres %}<div class="meta-item"><i class="fas fa-tag"></i> {{ movie.genres | join(' / ') }}</div>{% endif %}
        </div>
        <p class="detail-overview">{{ movie.overview }}</p>
    </div>
</div>
<div class="container">
    {% if movie.trailer_url %}
    <div class="trailer-section">
        <h2 class="section-title"><i class="fas fa-video"></i> Watch Trailer</h2>
        <div class="trailer-video-wrap"><iframe src="{{ movie.trailer_url }}" title="YouTube video player" frameborder="0" allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture" allowfullscreen></iframe></div>
    </div>
    {% endif %}

    
    <div style="text-align: center; margin: 40px 0;">
        <a href="{{ url_for('request_content', report_id=movie._id, title=movie.title) }}" class="report-button">
            <i class="fas fa-flag"></i> Report a Problem
        </a>
    </div>

    <!-- ===== ফাইনাল এবং রেসপন্সিভ অটো-চেঞ্জিং ইমেজ গ্যালারি শুরু ===== -->
{% if movie.backdrop_images and movie.backdrop_images|length > 0 %}
<section class="gallery-section">
    <h2 class="section-title"><i class="fas fa-images"></i> Image Gallery</h2>
    
    <div class="gallery-content-wrapper">

        <!-- প্রধান ছবি (Auto-changing) - বাম কলাম (ডেস্কটপ) / উপরে (মোবাইল) -->
        <div class="gallery-item hero-image-container" id="auto-change-item">
            <a href="{{ movie.backdrop_images[0] }}" target="_blank">
                {# এখানে ১ম ছবি এবং ৬ষ্ঠ ছবি থেকে বাকিগুলো স্বয়ংক্রিয় পরিবর্তনের জন্য রাখা হচ্ছে #}
                {% set images_for_hero = movie.backdrop_images[:1] + movie.backdrop_images[5:] %}
                {% for image in images_for_hero %}
                    <img src="{{ image }}" 
                         class="changing-image {% if loop.first %}active{% endif %}" 
                         alt="{{ movie.title }} backdrop image">
                {% endfor %}
            </a>
        </div>

        <!-- থাম্বনেইল ছবিগুলো - ডান কলাম (ডেস্কটপ) / নিচে (মোবাইল) -->
        {% if movie.backdrop_images|length > 1 %}
        <div class="thumbnail-stack">
            {# movie.backdrop_images[1:5] মানে হলো ২য় থেকে ৫ম ছবি পর্যন্ত নেওয়া #}
            {% for img_url in movie.backdrop_images[1:5] %}
            <div class="gallery-item thumbnail-item">
                <a href="{{ img_url }}" target="_blank">
                    <img src="{{ img_url }}" loading="lazy" alt="{{ movie.title }} backdrop thumbnail">
                </a>
            </div>
            {% endfor %}
        </div>
        {% endif %}

    </div>
</section>
{% endif %}
<!-- ===== ফাইনাল এবং রেসপন্সিভ অটো-চেঞ্জিং ইমেজ গ্যালারি শেষ ===== -->
    
    {% if ad_settings.ad_detail_page %}<div class="ad-container">{{ ad_settings.ad_detail_page | safe }}</div>{% endif %}
    
    <!-- ... কোডের আগের অংশ ... -->
    {% if movie.type == 'movie' %}
        {# Check if there are any links available for the movie #}
        {% set has_links = movie.streaming_links or movie.links or movie.files %}
        {% if has_links %}
            <div class="download-hub-section">
                <h3 class="hub-section-title">
                    <i class="fas fa-download"></i>
                    <span>Streaming & Download Options</span>
                </h3>
                <p class="hub-section-description">
                    All available links (1080p, 720p, Stream, Direct Dawnload, Telegram File etc.) are organized on the next page for your convenience 🔗👇.
                </p>
                <a href="{{ url_for('wait_page', target=quote(url_for('download_hub', movie_id=movie._id))) }}" class="hub-proceed-button">
                    <span>🍿 Proceed to Movie Link 🍿</span>
                    <i class="fas fa-arrow-right"></i>
                </a>
            </div>
        {% endif %}
   {% elif movie.type == 'series' %}
        {# Check if there are any episodes available for the series #}
        {% if movie.episodes %}
            <div class="download-hub-section">
                <h3 class="hub-section-title">
                    <i class="fas fa-play-circle"></i>
                    <span>Watch All Episodes</span>
                </h3>
                <p class="hub-section-description">
                    All available seasons and episodes (1080p, 720p, Stream, Direct Dawnload, Telegram File etc.) are organized on the next page. Click below to see all links 🔗👇.
                </p>
                <a href="{{ url_for('wait_page', target=quote(url_for('series_hub', series_id=movie._id))) }}" class="hub-proceed-button">
                    <span>🍿 Proceed to Series Link 🍿</span>
                    <i class="fas fa-arrow-right"></i>
                </a>
            </div>
        {% endif %}
    {% endif %}
    

{# === ✅ UNIVERSAL LINK CHECK & FALLBACK VIDEO WITH LOADING === #}
{% set all_links = [] %}

{% if movie.streaming_links %}{% set _ = all_links.append('stream') %}{% endif %}
{% if movie.links %}{% set _ = all_links.append('download') %}{% endif %}
{% if movie.files %}{% set _ = all_links.append('telegram') %}{% endif %}
{% if movie.episodes %}
    {% for ep in movie.episodes %}
        {% if ep.stream_link or ep.download_link or ep.links %}
            {% set _ = all_links.append('episode') %}
        {% endif %}
    {% endfor %}
{% endif %}

{% if all_links|length == 0 %}
<div style="margin-top:30px;text-align:center;">

  {# ===== Title & Message ===== #}
  {% if movie.type == 'movie' %}
      <h3 class="section-title"><i class="fas fa-link"></i> Links & Downloads</h3>
      <p style="font-size:1rem;color:#ccc;margin-bottom:5px;">
          Oops! No streaming or download links are available for "{{ movie.title }}" yet. We are working to add them soon 🍿.
      </p>
      <hr style="width:50px;border:2px solid red;margin:auto;margin-bottom:20px;">
  {% elif movie.type == 'series' %}
      <h3 class="section-title"><i class="fas fa-play-circle"></i> Links & Episodes</h3>
      <p style="font-size:1rem;color:#ccc;margin-bottom:5px;">
          Oops! All episodes of "{{ movie.title }}" are currently unavailable. Please check back soon 🍿.
      </p>
      <hr style="width:50px;border:2px solid red;margin:auto;margin-bottom:20px;">
  {% endif %}

  {# ===== Loading Spinner ===== #}
  <div class="custom-loading-container">
    <div class="custom-loading-spinner"></div>
    <div class="custom-loading-text">
        Loading<br>Please Wait
    </div>
</div>
</div>
{% endif %}
{# === ✅ END UNIVERSAL CHECK WITH LOADING === #}
    
    
{% if related_content %}
<section class="category-section">
    <div class="category-header">
        <h2 class="category-title">You Might Also Like</h2>
    </div>
    <div class="related-grid">
        {% for m in related_content %}
            {{ render_movie_card(m) }} {# এখানে ম্যাক্রোটিকে কল করা হচ্ছে #}
        {% endfor %}
    </div>
</section>
{% endif %}
</div>
{% else %}<div style="display:flex; justify-content:center; align-items:center; height:100vh;"><h2>Content not found.</h2></div>{% endif %}
<script src="https://unpkg.com/swiper/swiper-bundle.min.js"></script>
<!-- START: Final Professional Footer -->
<footer class="professional-footer">
    <div class="container footer-grid">
        <!-- Section 1: About the Site -->
        <div class="footer-column about-section">
            <a href="{{ url_for('home') }}" class="footer-logo">
                <!-- LOGO CHANGED HERE (Footer) -->
                <img src="https://i.postimg.cc/L4kGt56P/1000018917-removebg-preview.png" alt="{{ website_name }} Logo">
            </a>
            <p class="footer-description">
                Your ultimate destination for the latest movies and web series. We are dedicated to providing a seamless entertainment experience.
            </p>
        </div>

        <!-- Section 2: Important Links -->
        <div class="footer-column links-section">
            <h4 class="footer-column-title">Site Links</h4>
            <ul>
                <li><a href="{{ url_for('dmca') }}"><i class="fas fa-gavel"></i> DMCA Policy</a></li>
                <li><a href="{{ url_for('disclaimer') }}"><i class="fas fa-exclamation-triangle"></i> Disclaimer</a></li>
                <li><a href="{{ url_for('create_website') }}"><i class="fas fa-palette"></i> Create Your Website</a></li>
            </ul>
        </div>

        <!-- Section 3: Join Our Community -->
        <div class="footer-column community-section">
            <h4 class="footer-column-title">Join Our Community</h4>
            <div class="telegram-buttons-container">
                <a href="https://t.me/+YhqvLHXHdIViNTRl" target="_blank" class="telegram-button notification">
                    <i class="fas fa-bell"></i>
                    <span><strong>New Content Alerts</strong><small>Get notified for every new upload</small></span>
                </a>
                <a href="https://t.me/+YhqvLHXHdIViNTRl" target="_blank" class="telegram-button request">
                    <i class="fas fa-comments"></i>
                    <span><strong>Join Request Group</strong><small>Request your favorite content</small></span>
                </a>
                <a href="https://t.me/+YhqvLHXHdIViNTRl" target="_blank" class="telegram-button backup">
                    <i class="fas fa-shield-alt"></i>
                    <span><strong>Backup Channel</strong><small>Join for future updates</small></span>
                </a>
            </div>
            <p class="footer-note">
                <strong>Alternatively,</strong> you can use the <a href="{{ url_for('request_content') }}">Request</a> option in our bottom menu to submit requests directly on the site.
            </p>
        </div>
    </div>
    <div class="footer-bottom-bar">
        <p>&copy; {{ datetime.utcnow().year }} {{ website_name }}. All Rights Reserved. Crafted with care for movie lovers.</p>
    </div>
</footer>
<!-- END: Final Professional Footer -->
<script>
    document.addEventListener('DOMContentLoaded', function () {
        // (আপনার থিম কোড এখানে থাকবে)
        const applySavedTheme = () => {
            const savedTheme = localStorage.getItem('theme') || 'dark';
            if (savedTheme === 'light') {
                document.body.classList.add('light-mode');
            } else {
                document.body.classList.remove('light-mode');
            }
        };
        applySavedTheme();

        // ===== ফাইনাল ভার্টিক্যাল গ্যালারির জন্য জাভাস্ক্রিপ্ট (অপরিবর্তিত) =====
        const autoChangeContainer = document.getElementById('auto-change-item');
        if (autoChangeContainer) {
            const images = autoChangeContainer.querySelectorAll('.changing-image');
            const link = autoChangeContainer.querySelector('a');
            let currentIndex = 0;

            if (images.length > 1) {
                setInterval(() => {
                    // বর্তমান ছবিকে hide করা
                    images[currentIndex].classList.remove('active');

                    // পরবর্তী ইনডেক্স নির্ধারণ করা
                    currentIndex = (currentIndex + 1) % images.length;

                    // নতুন ছবিকে show করা এবং তার লিংক আপডেট করা
                    images[currentIndex].classList.add('active');
                    link.href = images[currentIndex].src;

                }, 1500); // প্রতি 1.5 সেকেন্ডে ছবি পরিবর্তন হবে
            }
        }
    });
</script>
{{ ad_settings.ad_footer | safe }}
</body></html>
"""
# নিশ্চিত করুন যে কোডের শেষে এই তিনটি কোটেশন (""") আছে


# =======================================================================================
# === [START] UPDATED WAITING PAGE TEMPLATES ============================================
# =======================================================================================

# --- STEP 1 HTML ---
wait_step1_html = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>Generating Link... (Step 1/3) - {{ website_name }}</title>
    <link rel="icon" href="https://i.postimg.cc/L4kGt56P/1000018917-removebg-preview.png" type="image/png">
    <meta name="robots" content="noindex, nofollow">
    <link href="https://fonts.googleapis.com/css2?family=Poppins:wght@400;500;700&display=swap" rel="stylesheet">
    {{ ad_settings.ad_header | safe }}
    <style>
        :root {--primary-color: #E50914; --bg-color: #000000; --card-bg: #1a1a1a; --text-light: #ffffff; --text-dark: #a0a0a0;}
        html { scroll-behavior: smooth; }
        body { font-family: 'Poppins', sans-serif; background-color: var(--bg-color); color: var(--text-light); text-align: center; margin: 0; padding: 0; }
        
        /* Fixed Header Styles */
        .fixed-header {
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            background-color: var(--card-bg);
            padding: 10px 0;
            z-index: 1000;
            display: flex;
            justify-content: center;
            align-items: center;
            box-shadow: 0 2px 10px rgba(0,0,0,0.5);
            border-bottom: 1px solid #333;
        }
        .fixed-header img {
            height: 50px; /* লোগোর সাইজ নিয়ন্ত্রণ করুন */
            width: auto;
        }

        .page-section { min-height: 100vh; display: flex; flex-direction: column; justify-content: center; align-items: center; padding: 20px; box-sizing: border-box; }
        
        /* Adjust main content to avoid being hidden by the header */
        #top-content {
            padding-top: 80px; /* হেডার এর উচ্চতা অনুযায়ী জায়গা তৈরি */
        }
        
        .wait-container { background-color: var(--card-bg); padding: 40px; border-radius: 12px; max-width: 500px; width: 100%; box-shadow: 0 10px 30px rgba(0,0,0,0.5); }
        h1 { font-size: 1.8rem; color: var(--primary-color); margin-bottom: 20px; }
        p { color: var(--text-dark); margin-bottom: 30px; font-size: 1rem; }
        .timer { font-size: 2.5rem; font-weight: 700; color: var(--text-light); margin-bottom: 30px; }
        .action-btn { display: inline-block; text-decoration: none; color: white; font-weight: 600; cursor: pointer; border: none; padding: 12px 30px; border-radius: 50px; font-size: 1rem; background-color: #555; transition: background-color 0.2s; }
        .action-btn:disabled { cursor: not-allowed; }
        .action-btn.ready { background-color: var(--primary-color); }
        .ad-container { margin: 30px auto; width: 100%; max-width: 90%; display: flex; justify-content: center; align-items: center; overflow: hidden; min-height: 50px; text-align: center; }
        
        #bottom-content { display: none; }
        .main-footer {
  text-align: center;
  padding: 15px 10px;
  background-color: #111;
  color: #ccc;
  font-size: 0.9rem;
  border-top: 1px solid rgba(255,255,255,0.1);
  margin-top: 40px;
  transition: background 0.3s;
}

.main-footer:hover {
  background-color: #222;
  color: #fff;
}
    </style>
</head>
<body>
    <!-- Fixed Header HTML -->
    <header class="fixed-header">
        <img src="https://i.postimg.cc/L4kGt56P/1000018917-removebg-preview.png" alt="Website Logo">
    </header>

    <div id="top-content" class="page-section">
        {{ ad_settings.ad_body_top | safe }}
        <div class="wait-container">
            <h1>Please Wait</h1>
            <p>Your download link is being prepared. Please scroll down after the timer ends.</p>
            <div id="timer-text" class="timer">Please wait <span id="countdown">10</span> seconds...</div>
            <a id="continue-btn-1" href="#bottom-content" class="action-btn" disabled>Preparing Link...</a>
        </div>
        {% if ad_settings.ad_wait_page %}<div class="ad-container">{{ ad_settings.ad_wait_page | safe }}</div>{% endif %}
    </div>

    <div class="ad-section" style="padding: 50px 0;">
        <h2>Advertisement</h2>
        {% if ad_settings.ad_wait_page %}<div class="ad-container" style="min-height: 200px;">{{ ad_settings.ad_wait_page | safe }}</div>{% endif %}
        {% if ad_settings.ad_detail_page %}<div class="ad-container">{{ ad_settings.ad_detail_page | safe }}</div>{% endif %}
    </div>
    
    <div id="bottom-content" class="page-section">
        <div class="wait-container">
            <h1>Ready to Continue</h1>
            <p>Click the button below to proceed to the next step.</p>
            <a href="{{ next_step_url }}" class="action-btn ready">Continue</a>
        </div>
    </div>
    <a href="https://t.me/TGLinkBase" target="_blank" rel="noopener noreferrer" style="text-decoration: none;">
  <footer class="main-footer">
      <p>&copy; 2025 {{ website_name }}. All Rights Reserved.</p>
  </footer>
</a>

    <script>
        (function() {
            let timeLeft = 10;
            const countdownElement = document.getElementById('countdown');
            const timerTextElement = document.getElementById('timer-text');
            const continueBtn1 = document.getElementById('continue-btn-1');
            const bottomContent = document.getElementById('bottom-content');

            const timer = setInterval(() => {
                if (timeLeft <= 0) {
                    clearInterval(timer);
                    timerTextElement.textContent = "Please scroll down and click continue.";
                    continueBtn1.removeAttribute('disabled');
                    continueBtn1.classList.add('ready');
                    continueBtn1.textContent = 'Click Here to Continue';
                    bottomContent.style.display = 'flex';
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

# --- STEP 2 HTML ---
wait_step2_html = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>Processing... (Step 2/3) - {{ website_name }}</title>
    <link rel="icon" href="https://i.postimg.cc/L4kGt56P/1000018917-removebg-preview.png" type="image/png">
    <meta name="robots" content="noindex, nofollow">
    <link href="https://fonts.googleapis.com/css2?family=Poppins:wght@400;500;700&display=swap" rel="stylesheet">
    {{ ad_settings.ad_header | safe }}
    <style>
        :root {--primary-color: #007bff; --bg-color: #000000; --card-bg: #1a1a1a; --text-light: #ffffff; --text-dark: #a0a0a0;}
        html { scroll-behavior: smooth; }
        body { font-family: 'Poppins', sans-serif; background-color: var(--bg-color); color: var(--text-light); text-align: center; margin: 0; padding: 0; }

        .fixed-header { position: fixed; top: 0; left: 0; width: 100%; background-color: var(--card-bg); padding: 10px 0; z-index: 1000; display: flex; justify-content: center; align-items: center; box-shadow: 0 2px 10px rgba(0,0,0,0.5); border-bottom: 1px solid #333; }
        .fixed-header img { height: 50px; width: auto; }

        .page-section { min-height: 100vh; display: flex; flex-direction: column; justify-content: center; align-items: center; padding: 20px; box-sizing: border-box; }
        #top-content { padding-top: 80px; }
        
        .wait-container { background-color: var(--card-bg); padding: 40px; border-radius: 12px; max-width: 500px; width: 100%; box-shadow: 0 10px 30px rgba(0,0,0,0.5); }
        h1 { font-size: 1.8rem; color: var(--primary-color); margin-bottom: 20px; }
        p { color: var(--text-dark); margin-bottom: 30px; font-size: 1rem; }
        .timer { font-size: 2.5rem; font-weight: 700; color: var(--text-light); margin-bottom: 30px; }
        .action-btn { display: inline-block; text-decoration: none; color: white; font-weight: 600; cursor: pointer; border: none; padding: 12px 30px; border-radius: 50px; font-size: 1rem; background-color: #555; transition: background-color 0.2s; }
        .action-btn:disabled { cursor: not-allowed; }
        .action-btn.ready { background-color: var(--primary-color); }
        .ad-container { margin: 30px auto; width: 100%; max-width: 90%; display: flex; justify-content: center; align-items: center; overflow: hidden; min-height: 50px; text-align: center; }

        #bottom-content { display: none; }
        .main-footer {
  text-align: center;
  padding: 15px 10px;
  background-color: #111;
  color: #ccc;
  font-size: 0.9rem;
  border-top: 1px solid rgba(255,255,255,0.1);
  margin-top: 40px;
  transition: background 0.3s;
}

.main-footer:hover {
  background-color: #222;
  color: #fff;
}
    </style>
</head>
<body>
    <header class="fixed-header">
        <img src="https://i.postimg.cc/L4kGt56P/1000018917-removebg-preview.png" alt="Website Logo">
    </header>

    <div id="top-content" class="page-section">
        {{ ad_settings.ad_body_top | safe }}
        <div class="wait-container">
            <h1>Almost There...</h1>
            <p>Please wait while we process your request. Scroll down after the timer.</p>
            <div id="timer-text" class="timer">Wait <span id="countdown">7</span> seconds...</div>
            <a id="continue-btn-1" href="#bottom-content" class="action-btn" disabled>Processing...</a>
        </div>
        {% if ad_settings.ad_wait_page %}<div class="ad-container">{{ ad_settings.ad_wait_page | safe }}</div>{% endif %}
    </div>

    <div class="ad-section" style="padding: 50px 0;">
        <h2>Advertisement</h2>
        {% if ad_settings.ad_wait_page %}<div class="ad-container" style="min-height: 200px;">{{ ad_settings.ad_wait_page | safe }}</div>{% endif %}
    </div>
    
    <div id="bottom-content" class="page-section">
        <div class="wait-container">
            <h1>Ready for Final Step</h1>
            <p>Click the button below to proceed.</p>
            <a href="{{ next_step_url }}" class="action-btn ready">Continue to Final Step</a>
        </div>
    </div>
    <a href="https://t.me/TGLinkBase" target="_blank" rel="noopener noreferrer" style="text-decoration: none;">
  <footer class="main-footer">
      <p>&copy; 2025 {{ website_name }}. All Rights Reserved.</p>
  </footer>
</a>

    <script>
        (function() {
            let timeLeft = 7;
            const countdownElement = document.getElementById('countdown');
            const timerTextElement = document.getElementById('timer-text');
            const continueBtn1 = document.getElementById('continue-btn-1');
            const bottomContent = document.getElementById('bottom-content');

            const timer = setInterval(() => {
                if (timeLeft <= 0) {
                    clearInterval(timer);
                    timerTextElement.innerHTML = "Ready! Please scroll down.";
                    continueBtn1.removeAttribute('disabled');
                    continueBtn1.classList.add('ready');
                    continueBtn1.textContent = 'Click to Continue';
                    bottomContent.style.display = 'flex';
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

# --- STEP 3 HTML (FINAL PAGE) ---
wait_step3_html = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>Link Ready! (Step 3/3) - {{ website_name }}</title>
    <link rel="icon" href="https://i.postimg.cc/L4kGt56P/1000018917-removebg-preview.png" type="image/png">
    <meta name="robots" content="noindex, nofollow">
    <link href="https://fonts.googleapis.com/css2?family=Poppins:wght@400;500;700&display=swap" rel="stylesheet">
    {{ ad_settings.ad_header | safe }}
    <style>
        :root {--primary-color: #28a745; --bg-color: #000000; --card-bg: #1a1a1a; --text-light: #ffffff; --text-dark: #a0a0a0;}
        html { scroll-behavior: smooth; }
        body { font-family: 'Poppins', sans-serif; background-color: var(--bg-color); color: var(--text-light); text-align: center; margin: 0; padding: 0; }
        
        .fixed-header { position: fixed; top: 0; left: 0; width: 100%; background-color: var(--card-bg); padding: 10px 0; z-index: 1000; display: flex; justify-content: center; align-items: center; box-shadow: 0 2px 10px rgba(0,0,0,0.5); border-bottom: 1px solid #333; }
        .fixed-header img { height: 50px; width: auto; }

        .page-section { min-height: 100vh; display: flex; flex-direction: column; justify-content: center; align-items: center; padding: 20px; box-sizing: border-box; }
        #top-content { padding-top: 80px; }
        
        .wait-container { background-color: var(--card-bg); padding: 40px; border-radius: 12px; max-width: 500px; width: 100%; box-shadow: 0 10px 30px rgba(0,0,0,0.5); }
        h1 { font-size: 1.8rem; color: var(--primary-color); margin-bottom: 20px; }
        p { color: var(--text-dark); margin-bottom: 30px; font-size: 1rem; }
        .timer { font-size: 2.5rem; font-weight: 700; color: var(--text-light); margin-bottom: 30px; }
        .action-btn { display: inline-block; text-decoration: none; color: white; font-weight: 600; cursor: pointer; border: none; padding: 12px 30px; border-radius: 50px; font-size: 1rem; background-color: #555; transition: background-color 0.2s; }
        .action-btn:disabled { cursor: not-allowed; }
        .action-btn.ready { background-color: var(--primary-color); }
        .ad-container { margin: 30px auto; width: 100%; max-width: 90%; display: flex; justify-content: center; align-items: center; overflow: hidden; min-height: 50px; text-align: center; }

        #bottom-content { display: none; }
    </style>
</head>
<body>
    <header class="fixed-header">
        <img src="https://i.postimg.cc/L4kGt56P/1000018917-removebg-preview.png" alt="Website Logo">
    </header>

    <div id="top-content" class="page-section">
        {{ ad_settings.ad_body_top | safe }}
        <div class="wait-container">
            <h1>Final Step</h1>
            <p>Your download link is ready. Please scroll down after the timer.</p>
            <div id="timer-text" class="timer">Please wait <span id="countdown">5</span> seconds...</div>
            <a id="continue-btn-1" href="#bottom-content" class="action-btn" disabled>Generating Link...</a>
        </div>
        {% if ad_settings.ad_wait_page %}<div class="ad-container">{{ ad_settings.ad_wait_page | safe }}</div>{% endif %}
    </div>

    <div class="ad-section" style="padding: 50px 0;">
        <h2>Advertisement</h2>
        {% if ad_settings.ad_wait_page %}<div class="ad-container" style="min-height: 200px;">{{ ad_settings.ad_wait_page | safe }}</div>{% endif %}
    </div>
    
    <div id="bottom-content" class="page-section">
        <div class="wait-container">
            <h1>Your Link is Ready!</h1>
            <p>Click the button below to get your file.</p>
            <a href="{{ target_url | safe }}" class="action-btn ready">Get Link</a>
        </div>
    </div>

    <script>
        (function() {
            let timeLeft = 5;
            const countdownElement = document.getElementById('countdown');
            const timerTextElement = document.getElementById('timer-text');
            const continueBtn1 = document.getElementById('continue-btn-1');
            const bottomContent = document.getElementById('bottom-content');

            const timer = setInterval(() => {
                if (timeLeft <= 0) {
                    clearInterval(timer);
                    timerTextElement.innerHTML = "Link is Ready! Scroll Down.";
                    continueBtn1.removeAttribute('disabled');
                    continueBtn1.classList.add('ready');
                    continueBtn1.textContent = 'Click to Scroll Down';
                    bottomContent.style.display = 'flex';
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

# =======================================================================================
# === [END] UPDATED WAITING PAGE TEMPLATES ==============================================
# =======================================================================================

# ===== request_html এর পুরোনো কোডটি ডিলিট করে এটি পেস্ট করুন =====
request_html = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Contact Us / Report - {{ website_name }}</title>
    <link rel="icon" href="https://i.postimg.cc/L4kGt56P/1000018917-removebg-preview.png" type="image/png">
    <link href="https://fonts.googleapis.com/css2?family=Poppins:wght@400;500;700&display=swap" rel="stylesheet">
    <style>
        :root { --primary-color: #E50914; --bg-color: #141414; --card-bg: #1a1a1a; --text-light: #f5f5f5; --text-dark: #a0a0a0; }
        body { font-family: 'Poppins', sans-serif; background: var(--bg-color); color: var(--text-light); padding: 20px; display: flex; flex-direction: column; justify-content: center; align-items: center; min-height: 100vh; }
        .contact-container { max-width: 600px; width: 100%; background: var(--card-bg); padding: 30px; border-radius: 8px; }
        h2 { color: var(--primary-color); font-size: 2.5rem; text-align: center; margin-bottom: 25px; }
        .form-group { margin-bottom: 20px; } label { display: block; margin-bottom: 8px; font-weight: 500; }
        input, select, textarea { width: 100%; padding: 12px; border-radius: 4px; border: 1px solid #333; font-size: 1rem; background: #222; color: var(--text-light); box-sizing: border-box; }
        textarea { resize: vertical; min-height: 120px; }
        button[type="submit"] { background: var(--primary-color); color: white; font-weight: 700; cursor: pointer; border: none; padding: 12px 25px; border-radius: 4px; font-size: 1.1rem; width: 100%; }
        .success-message { text-align: center; padding: 20px; background-color: #1f4e2c; color: #d4edda; border-radius: 5px; margin-bottom: 20px; }
        .back-link { display: block; text-align: center; margin-top: 20px; color: var(--primary-color); text-decoration: none; font-weight: bold; }
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
            <div class="form-group">
                <label for="type">Subject:</label>
                <select name="type" id="type">
                    <option value="Movie Request" {% if prefill_type == 'Problem Report' %}disabled{% endif %}>Movie/Series Request</option>
                    <option value="Problem Report" {% if prefill_type == 'Problem Report' %}selected{% endif %}>Report a Problem</option>
                    <option value="General Feedback">General Feedback</option>
                </select>
            </div>
            <div class="form-group">
                <label for="content_title">Movie/Series Title:</label>
                <input type="text" name="content_title" id="content_title" value="{{ prefill_title }}" required>
            </div>
            <div class="form-group">
                <label for="message">Your Message:</label>
                <textarea name="message" id="message" required {% if prefill_id %}autofocus{% endif %}></textarea>
            </div>
            <div class="form-group">
                <label for="email">Your Email (Optional):</label>
                <input type="email" name="email" id="email">
            </div>
            <input type="hidden" name="reported_content_id" value="{{ prefill_id }}">
            <button type="submit">Submit</button>
        </form>
        <a href="{{ url_for('home') }}" class="back-link">← Cancel</a>
    {% endif %}
</div>
</body>
</html>
"""


admin_html = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Admin Panel - {{ website_name }}</title>
    <link rel="icon" href="https://i.postimg.cc/L4kGt56P/1000018917-removebg-preview.png" type="image/png">
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
        hr { border: 0; height: 1px; background-color: var(--light-gray); margin: 30px 0; }
        .tmdb-fetcher { display: flex; gap: 10px; }
        .checkbox-group { display: flex; flex-wrap: wrap; gap: 15px; padding: 10px 0; } .checkbox-group label { display: flex; align-items: center; gap: 8px; font-weight: normal; cursor: pointer;}
        .checkbox-group input { width: auto; }
        .modal-overlay { position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.85); z-index: 2000; display: none; justify-content: center; align-items: center; padding: 20px; }
        .modal-content { background: var(--dark-gray); padding: 30px; border-radius: 8px; width: 100%; max-width: 900px; max-height: 90vh; display: flex; flex-direction: column; }
        .modal-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; flex-shrink: 0; }
        .modal-body { overflow-y: auto; }
        .modal-close { background: none; border: none; color: #fff; font-size: 2rem; cursor: pointer; }
        #search-results { display: grid; grid-template-columns: repeat(auto-fill, minmax(150px, 1fr)); gap: 20px; }
        .result-item { cursor: pointer; text-align: center; }
        .result-item img { width: 100%; aspect-ratio: 2/3; object-fit: cover; border-radius: 5px; margin-bottom: 10px; border: 2px solid transparent; transition: all 0.2s; }
        .result-item:hover img { transform: scale(1.05); border-color: var(--netflix-red); }
        .manage-content-header { display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 20px; margin-bottom: 20px; }
        .search-form { display: flex; gap: 10px; flex-grow: 1; max-width: 500px; }
        .dashboard-stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 20px; margin-bottom: 30px; }
        .stat-card { background: var(--dark-gray); padding: 20px; border-radius: 8px; text-align: center; border-left: 5px solid var(--netflix-red); }
        .stat-card h3 { margin: 0 0 10px; font-size: 1.2rem; } .stat-card p { font-size: 2.5rem; font-weight: 700; margin: 0; color: var(--netflix-red); }
        .category-management { display: flex; flex-wrap: wrap; gap: 30px; align-items: flex-start; }
        .status-badge { padding: 4px 8px; border-radius: 4px; color: white; font-size: 0.8rem; font-weight: bold; }
        .status-pending { background-color: #ffc107; color: black; } .status-fulfilled { background-color: #28a745; } .status-rejected { background-color: #6c757d; }
        .pagination { display: flex; justify-content: center; align-items: center; gap: 10px; margin: 30px 0; }
        .pagination a, .pagination span { padding: 10px 18px; border-radius: 6px; font-weight: 600; font-size: 0.9rem; text-decoration: none; border: none; }
        .pagination a { background-color: var(--light-gray); color: var(--text-light); }
        .pagination a:hover { background-color: #444; }
        .pagination .current { background-color: var(--netflix-red); color: white; }
        
        /* === [NEW] Admin Panel Tabs CSS === */
        .admin-tabs {
            display: flex;
            gap: 5px;
            margin-bottom: 25px;
            border-bottom: 2px solid var(--light-gray);
        }
        .tab-button {
            padding: 15px 25px;
            cursor: pointer;
            background: none;
            border: none;
            color: var(--text-light);
            font-size: 1.1rem;
            font-weight: bold;
            border-bottom: 3px solid transparent;
            transition: all 0.2s ease-in-out;
        }
        .tab-button:hover {
            background-color: var(--light-gray);
        }
        .tab-button.active {
            color: var(--netflix-red);
            border-bottom-color: var(--netflix-red);
        }
        .tab-content {
            display: none; /* Ocultar todo el contenido por defecto */
        }
        .tab-content.active {
            display: block; /* Mostrar solo el contenido activo */
            animation: fadeIn 0.5s;
        }
        @keyframes fadeIn {
            from { opacity: 0; }
            to { opacity: 1; }
        }
        /* === End Admin Panel Tabs CSS === */       
    </style>
</head>
<body>
<div class="admin-container">
    <header class="admin-header"><h1>Admin Panel</h1><a href="{{ url_for('home') }}" target="_blank">View Site</a></header>
    
    <!-- === [NEW] Admin Panel Tabs Structure === -->
    <div class="admin-tabs">
        <button class="tab-button active" onclick="openTab(event, 'add-content')"><i class="fas fa-plus-circle"></i> Add/Edit Content</button>
        <button class="tab-button" onclick="openTab(event, 'manage-content')"><i class="fas fa-tasks"></i> Content Management</button>
        <button class="tab-button" onclick="openTab(event, 'site-settings')"><i class="fas fa-cogs"></i> Site Settings</button>
    </div>

    <!-- Tab 1: Add Content (Default) -->
    <div id="add-content" class="tab-content active">
        <h2><i class="fas fa-plus-circle"></i> Add New Content</h2>
        <fieldset><legend>Automatic Method (Search TMDB)</legend><div class="form-group"><div class="tmdb-fetcher"><input type="text" id="tmdb_search_query" placeholder="e.g., Avengers Endgame"><button type="button" id="tmdb_search_btn" class="btn btn-primary" onclick="searchTmdb()">Search</button></div></div></fieldset>
        <form method="post">
            <input type="hidden" name="form_action" value="add_content"><input type="hidden" name="tmdb_id" id="tmdb_id">
            <fieldset><legend>Core Details</legend>
                <div class="form-group"><label>Title:</label><input type="text" name="title" id="title" required></div>
                <div class="form-group"><label>Poster URL:</label><input type="url" name="poster" id="poster"></div>
                <div class="form-group"><label>Backdrop URL:</label><input type="url" name="backdrop" id="backdrop"></div>
                <div class="form-group"><label>Overview:</label><textarea name="overview" id="overview"></textarea></div>
                <div class="form-group"><label>Languages (comma-separated):</label><input type="text" name="languages" id="languages" placeholder="e.g. Hindi, English"></div>
                <div class="form-group"><label>Poster Badge:</label><input type="text" name="poster_badge" placeholder="e.g., 4K HDR, Bsub, Dubbed"></div>
                <div class="form-group"><label>Genres (comma-separated):</label><input type="text" name="genres" id="genres"></div>
                <div class="form-group"><label>Release Year:</label><input type="text" name="release_year" id="release_year" placeholder="e.g., 2024"></div>
                <div class="form-group"><label>Trailer URL (YouTube Embed):</label><input type="url" name="trailer_url" id="trailer_url" placeholder="https://www.youtube.com/embed/VIDEO_ID"></div>
                <div class="form-group"><label>Content Type:</label><select name="content_type" id="content_type" onchange="toggleFields()"><option value="movie">Movie</option><option value="series">Series</option></select></div>
            </fieldset>
            <fieldset><legend>Backdrop Images</legend>
                <div id="backdrop_images_container"></div>
                <button type="button" onclick="addBackdropField()" class="btn btn-secondary"><i class="fas fa-plus"></i> Add Backdrop Image</button>
            </fieldset>
            <fieldset><legend>Categories</legend>
                <div class="form-group checkbox-group">
                    {% for cat in categories_list %}<label><input type="checkbox" name="categories" value="{{ cat.name }}"> {{ cat.name }}</label>{% endfor %}
                </div>
            </fieldset>
            <fieldset><legend>OTT Platforms</legend>
                <div class="form-group checkbox-group">
                    {% for platform in ott_platforms_list %}<label><input type="checkbox" name="ott_platforms" value="{{ platform.name }}"> {{ platform.name }}</label>{% endfor %}
                </div>
            </fieldset>
            <div id="movie_fields">
                <fieldset><legend>Movie Links</legend>
                    <p><b>Streaming Links (Optional)</b></p>
                    <div class="form-group"><label>Streaming Link 1 (e.g., 480p Server):</label><input type="url" name="streaming_link_1" /></div>
                    <div class="form-group"><label>Streaming Link 2 (e.g., 720p Server):</label><input type="url" name="streaming_link_2" /></div>
                    <div class="form-group"><label>Streaming Link 3 (e.g., 1080p Server):</label><input type="url" name="streaming_link_3" /></div><hr style="margin:20px 0;">
                    <p><b>Direct Download Links</b></p>
                    <div class="form-group"><label>480p Link:</label><input type="url" name="link_480p" /></div>
                    <div class="form-group"><label>720p Link:</label><input type="url" name="link_720p" /></div>
                    <div class="form-group"><label>1080p Link:</label><input type="url" name="link_1080p" /></div><hr style="margin:20px 0;">
                    <p><b>Get from Telegram</b></p>
                    <div class="form-group"><label>480p Telegram Link:</label><input type="url" name="telegram_link_480p" /></div>
                    <div class="form-group"><label>720p Telegram Link:</label><input type="url" name="telegram_link_720p" /></div>
                    <div class="form-group"><label>1080p Telegram Link:</label><input type="url" name="telegram_link_1080p" /></div>
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
    </div>

    <!-- Tab 2: Content Management -->
    <div id="manage-content" class="tab-content">
        <h2><i class="fas fa-tachometer-alt"></i> At a Glance</h2>
        <div class="dashboard-stats">
            <div class="stat-card"><h3>Total Content</h3><p>{{ stats.total_content }}</p></div>
            <div class="stat-card"><h3>Total Movies</h3><p>{{ stats.total_movies }}</p></div>
            <div class="stat-card"><h3>Total Series</h3><p>{{ stats.total_series }}</p></div>
            <div class="stat-card"><h3>Pending Requests</h3><p>{{ stats.pending_requests }}</p></div>
        </div>
        <hr>
        <h2><i class="fas fa-inbox"></i> Manage Requests</h2>
        <div class="table-container">
            <table>
                <thead><tr><th>Subject (Type)</th><th>Title</th><th>Message</th><th>Email</th><th>Status</th><th>Actions</th></tr></thead>
                <tbody>
                {% for req in requests_list %}
                <tr>
                    <td>{{ req.type or 'N/A' }}</td>
                    <td>{{ req.name }}</td>
                    <td style="white-space: pre-wrap; min-width: 200px;">{{ req.info }}</td>
                    <td>{{ req.email or 'N/A' }}</td>
                    <td><span class="status-badge status-{{ req.status|lower }}">{{ req.status }}</span></td>
                    <td class="action-buttons">
                        <a href="{{ url_for('update_request_status', req_id=req._id, status='Fulfilled') }}" class="btn btn-success" style="padding: 5px 10px;">Fulfilled</a>
                        <a href="{{ url_for('update_request_status', req_id=req._id, status='Rejected') }}" class="btn btn-secondary" style="padding: 5px 10px;">Rejected</a>
                        <a href="{{ url_for('delete_request', req_id=req._id) }}" class="btn btn-danger" style="padding: 5px 10px;" onclick="return confirm('Are you sure?')">Delete</a>
                    </td>
                </tr>
                {% else %}
                <tr><td colspan="6" style="text-align:center;">No pending requests.</td></tr>
                {% endfor %}
                </tbody>
            </table>
        </div>
        <hr>
        <div class="manage-content-header">
            <h2><i class="fas fa-tasks"></i> Manage Content</h2>
            <div class="search-form"><input type="search" id="admin-live-search" placeholder="Type to search content live..." autocomplete="off"></div>
        </div>
        <form method="post" id="bulk-action-form">
            <input type="hidden" name="form_action" value="bulk_delete">
            <div class="table-container"><table>
                <thead><tr><th><input type="checkbox" id="select-all"></th><th>Title</th><th>Type</th><th>Views</th><th>Actions</th></tr></thead>
                <tbody id="content-table-body">
                {% for movie in content_list %}
                <tr>
                    <td><input type="checkbox" name="selected_ids" value="{{ movie._id }}" class="row-checkbox"></td>
                    <td>{{ movie.title }}</td><td>{{ movie.type|title }}</td><td><i class="fas fa-eye"></i> {{ movie.view_count or 0 }}</td>
                    <td class="action-buttons">
                        <a href="{{ url_for('edit_movie', movie_id=movie._id) }}" class="btn btn-edit">Edit</a>
                        <a href="{{ url_for('delete_movie', movie_id=movie._id) }}" onclick="return confirm('Are you sure?')" class="btn btn-danger">Delete</a>
                    </td>
                </tr>
                {% endfor %}
                </tbody>
            </table></div>
            {% if pagination and pagination.total_pages > 1 %}
            <div class="pagination">
                {% if pagination.has_prev %}<a href="{{ url_for('admin', page=pagination.prev_num) }}">&laquo; Prev</a>{% endif %}
                <span class="current">Page {{ pagination.page }} of {{ pagination.total_pages }}</span>
                {% if pagination.has_next %}<a href="{{ url_for('admin', page=pagination.next_num) }}">Next &raquo;</a>{% endif %}
            </div>
            {% endif %}
            <button type="submit" class="btn btn-danger" style="margin-top: 15px;" onclick="return confirm('Delete selected items?')"><i class="fas fa-trash-alt"></i> Delete Selected</button>
        </form>
    </div>

    <!-- Tab 3: Site Settings -->
    <div id="site-settings" class="tab-content">
        <h2><i class="fas fa-tags"></i> Category Management</h2>
        <div class="category-management">
            <form method="post" style="flex: 1; min-width: 300px;">
                <input type="hidden" name="form_action" value="add_category">
                <fieldset><legend>Add New Category</legend>
                    <div class="form-group"><label>Category Name:</label><input type="text" name="category_name" required></div>
                    <button type="submit" class="btn btn-primary"><i class="fas fa-plus"></i> Add Category</button>
                </fieldset>
            </form>
            <div style="flex: 1; min-width: 250px;">
                <h3>Existing Categories</h3>
                {% for cat in categories_list %}<div style="display: flex; justify-content: space-between; align-items: center; background: var(--dark-gray); padding: 10px 15px; border-radius: 4px; margin-bottom: 10px;"><span>{{ cat.name }}</span><a href="{{ url_for('delete_category', cat_id=cat._id) }}" onclick="return confirm('Are you sure?')" class="btn btn-danger" style="padding: 5px 10px; font-size: 0.8rem;">Delete</a></div>{% endfor %}
            </div>
        </div>
        <hr>
        <h2><i class="fas fa-tv"></i> OTT Platform Management</h2>
        <div class="category-management">
            <form method="post" style="flex: 1; min-width: 300px;">
                <input type="hidden" name="form_action" value="add_ott_platform">
                <fieldset><legend>Add New OTT Platform</legend>
                    <div class="form-group"><label>Platform Name:</label><input type="text" name="ott_platform_name" required></div>
                    <button type="submit" class="btn btn-primary"><i class="fas fa-plus"></i> Add Platform</button>
                </fieldset>
            </form>
            <div style="flex: 1; min-width: 250px;">
                <h3>Existing Platforms</h3>
                {% for platform in ott_platforms_list %}<div style="display: flex; justify-content: space-between; align-items: center; background: var(--dark-gray); padding: 10px 15px; border-radius: 4px; margin-bottom: 10px;"><span>{{ platform.name }}</span><a href="{{ url_for('delete_ott_platform', platform_id=platform._id) }}" onclick="return confirm('Are you sure?')" class="btn btn-danger" style="padding: 5px 10px; font-size: 0.8rem;">Delete</a></div>{% endfor %}
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
    </div>
    <!-- === End Admin Panel Tabs === -->
</div>

<div class="modal-overlay" id="search-modal"><div class="modal-content"><div class="modal-header"><h2>Select Content</h2><button class="modal-close" onclick="closeModal()">&times;</button></div><div class="modal-body" id="search-results"></div></div></div>
<script>
    function toggleFields() { const isSeries = document.getElementById('content_type').value === 'series'; document.getElementById('episode_fields').style.display = isSeries ? 'block' : 'none'; document.getElementById('movie_fields').style.display = isSeries ? 'none' : 'block'; }
    function addTelegramFileField() { const c = document.getElementById('telegram_files_container'); const d = document.createElement('div'); d.className = 'dynamic-item'; d.innerHTML = `<button type="button" onclick="this.parentElement.remove()" class="btn btn-danger"><i class="fas fa-times"></i></button><div class="form-group"><label>Quality (e.g., 720p):</label><input type="text" name="telegram_quality[]" required /></div><div class="form-group"><label>Telegram URL:</label><input type="url" name="telegram_url[]" placeholder="https://t.me/..." required /></div>`; c.appendChild(d); }
    function addEpisodeField() { const c = document.getElementById('episodes_container'); const d = document.createElement('div'); d.className = 'dynamic-item'; d.innerHTML = `<button type="button" onclick="this.parentElement.remove()" class="btn btn-danger">X</button><div class="form-group"><label>Season:</label><input type="number" name="episode_season[]" value="1" required></div><div class="form-group"><label>Episode Number (e.g., 1 or 1-10):</label><input type="text" name="episode_number[]" required></div><div class="form-group"><label>Title:</label><input type="text" name="episode_title[]"></div><hr style="margin:15px 0;"><p><b>Links:</b></p><div class="form-group"><label>Streaming Link:</label><input type="url" name="episode_stream_link[]" /></div><div class="form-group"><label>Download Link:</label><input type="url" name="episode_download_link[]" /></div><div class="form-group"><label>Telegram Link:</label><input type="url" name="episode_telegram_link[]" /></div><hr style="margin:15px 0;"><p><b>Custom Links (Optional):</b></p><div class="form-group"><label>Links (One per line: Button Text | URL):</label><textarea name="episode_links[]" rows="3" placeholder="e.g., Watch G-Drive | https://..."></textarea></div>`; c.appendChild(d); }
    function addBackdropField() { const c = document.getElementById('backdrop_images_container'); const d = document.createElement('div'); d.className = 'dynamic-item'; d.innerHTML = `<button type="button" onclick="this.parentElement.remove()" class="btn btn-danger"><i class="fas fa-times"></i></button><div class="form-group"><label>Image URL:</label><input type="url" name="backdrop_images[]" placeholder="https://image.tmdb.org/..." required /></div>`; c.appendChild(d); }
    function openModal() { document.getElementById('search-modal').style.display = 'flex'; }
    function closeModal() { document.getElementById('search-modal').style.display = 'none'; }
    async function searchTmdb() { const query = document.getElementById('tmdb_search_query').value.trim(); if (!query) return; const searchBtn = document.getElementById('tmdb_search_btn'); searchBtn.disabled = true; searchBtn.innerHTML = 'Searching...'; openModal(); try { const response = await fetch('/admin/api/search?query=' + encodeURIComponent(query)); const results = await response.json(); const container = document.getElementById('search-results'); container.innerHTML = ''; if(results.length > 0) { results.forEach(item => { const resultDiv = document.createElement('div'); resultDiv.className = 'result-item'; resultDiv.onclick = () => selectResult(item.id, item.media_type); resultDiv.innerHTML = `<img src="${item.poster}" alt="${item.title}"><p><strong>${item.title}</strong> (${item.year})</p>`; container.appendChild(resultDiv); }); } else { container.innerHTML = '<p>No results found.</p>'; } } finally { searchBtn.disabled = false; searchBtn.innerHTML = 'Search'; } }
    async function selectResult(tmdbId, mediaType) {
        closeModal();
        const response = await fetch(`/admin/api/details?id=${tmdbId}&type=${mediaType}`);
        const data = await response.json();
        document.getElementById('tmdb_id').value = data.tmdb_id || '';
        document.getElementById('title').value = data.title || '';
        document.getElementById('overview').value = data.overview || '';
        document.getElementById('poster').value = data.poster || '';
        document.getElementById('backdrop').value = data.backdrop || '';
        document.getElementById('genres').value = data.genres ? data.genres.join(', ') : '';
        if (data.release_date) {
            document.getElementById('release_year').value = data.release_date.split('-')[0];
        }
        document.getElementById('trailer_url').value = data.trailer_url || '';
        document.getElementById('content_type').value = data.type === 'series' ? 'series' : 'movie';
        toggleFields();
        const backdropContainer = document.getElementById('backdrop_images_container');
        backdropContainer.innerHTML = '';
        if (data.backdrop_images && data.backdrop_images.length > 0) {
            data.backdrop_images.forEach(imgUrl => {
                const d = document.createElement('div');
                d.className = 'dynamic-item';
                d.innerHTML = `
                    <button type="button" onclick="this.parentElement.remove()" class="btn btn-danger"><i class="fas fa-times"></i></button>
                    <div class="form-group">
                        <label>Image URL:</label>
                        <input type="url" name="backdrop_images[]" value="${imgUrl}">
                    </div>
                `;
                backdropContainer.appendChild(d);
            });
        }
    }
    let debounceTimer; const searchInput = document.getElementById('admin-live-search'); const tableBody = document.getElementById('content-table-body'); searchInput.addEventListener('input', () => { clearTimeout(debounceTimer); debounceTimer = setTimeout(() => { const query = searchInput.value.trim(); tableBody.innerHTML = '<tr><td colspan="5" style="text-align:center;">Loading...</td></tr>'; fetch(`/admin/api/live_search?q=${encodeURIComponent(query)}`).then(response => response.json()).then(data => { tableBody.innerHTML = ''; if (data.length > 0) { data.forEach(movie => { const row = `<tr><td><input type="checkbox" name="selected_ids" value="${movie._id}" class="row-checkbox"></td><td>${movie.title}</td><td>${movie.type.charAt(0).toUpperCase() + movie.type.slice(1)}</td><td><i class="fas fa-eye"></i> ${movie.view_count || 0}</td><td class="action-buttons"><a href="/edit_movie/${movie._id}" class="btn btn-edit">Edit</a><a href="/delete_movie/${movie._id}" onclick="return confirm('Are you sure?')" class="btn btn-danger">Delete</a></td></tr>`; tableBody.innerHTML += row; }); } else { tableBody.innerHTML = '<tr><td colspan="5" style="text-align:center;">No content found.</td></tr>'; } }); }, 400); });
    document.addEventListener('DOMContentLoaded', function() { toggleFields(); const selectAll = document.getElementById('select-all'); if(selectAll) { selectAll.addEventListener('change', e => document.querySelectorAll('.row-checkbox').forEach(c => c.checked = e.target.checked)); } });

    // === [NEW] Admin Panel Tab Logic ===
    function openTab(event, tabName) {
        const tabContents = document.getElementsByClassName('tab-content');
        for (let i = 0; i < tabContents.length; i++) {
            tabContents[i].style.display = 'none';
            tabContents[i].classList.remove('active');
        }
        const tabButtons = document.getElementsByClassName('tab-button');
        for (let i = 0; i < tabButtons.length; i++) {
            tabButtons[i].classList.remove('active');
        }
        document.getElementById(tabName).style.display = 'block';
        document.getElementById(tabName).classList.add('active');
        event.currentTarget.classList.add('active');
    }
</script>
</body></html>
"""

edit_html = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Edit Content - {{ website_name }}</title>
    <link rel="icon" href="https://i.postimg.cc/L4kGt56P/1000018917-removebg-preview.png" type="image/png">
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
        .dynamic-item .btn-danger { position: absolute; top: 10px; right: 10px; padding: 4px 8px; font-size: 0.8rem; }
        .checkbox-group { display: flex; flex-wrap: wrap; gap: 15px; } .checkbox-group label { display: flex; align-items: center; gap: 5px; font-weight: normal; }
        .checkbox-group input { width: auto; }
        hr { border: 0; height: 1px; background-color: var(--light-gray); margin: 20px 0; }
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
        <div class="form-group"><label>Languages:</label><input type="text" name="languages" value="{{ movie.languages|join(', ') if movie.languages else '' }}"></div>
        <div class="form-group"><label>Poster Badge:</label><input type="text" name="poster_badge" value="{{ movie.poster_badge or '' }}" placeholder="e.g., 4K HDR, Bsub, Dubbed"></div>
        <div class="form-group"><label>Genres:</label><input type="text" name="genres" value="{{ movie.genres|join(', ') if movie.genres else '' }}"></div>
        <div class="form-group"><label>Release Year:</label><input type="text" name="release_year" value="{{ movie.release_year or '' }}" placeholder="e.g., 2024"></div>
        <div class="form-group"><label>Trailer URL (YouTube Embed):</label><input type="url" name="trailer_url" value="{{ movie.trailer_url or '' }}" placeholder="https://www.youtube.com/embed/VIDEO_ID"></div>
        <div class="form-group"><label>Content Type:</label><select name="content_type" id="content_type" onchange="toggleFields()"><option value="movie" {% if movie.type == 'movie' %}selected{% endif %}>Movie</option><option value="series" {% if movie.type == 'series' %}selected{% endif %}>Series</option></select></div>
    </fieldset>
    
    <!-- নতুন ব্যাকড্রপ ইমেজ সেকশন -->
    <fieldset><legend>Backdrop Images</legend>
        <div id="backdrop_images_container">
            {% if movie.backdrop_images %}
                {% for img_url in movie.backdrop_images %}
                <div class="dynamic-item">
                    <button type="button" onclick="this.parentElement.remove()" class="btn btn-danger"><i class="fas fa-times"></i></button>
                    <div class="form-group">
                        <label>Image URL:</label>
                        <input type="url" name="backdrop_images[]" value="{{ img_url }}">
                    </div>
                </div>
                {% endfor %}
            {% endif %}
        </div>
        <button type="button" onclick="addBackdropField()" class="btn btn-secondary"><i class="fas fa-plus"></i> Add Backdrop Image</button>
    </fieldset>

    <fieldset><legend>Categories</legend>
        <div class="form-group checkbox-group">
            {% for cat in categories_list %}<label><input type="checkbox" name="categories" value="{{ cat.name }}" {% if movie.categories and cat.name in movie.categories %}checked{% endif %}> {{ cat.name }}</label>{% endfor %}
        </div>
    </fieldset>

    <fieldset><legend>OTT Platforms</legend>
        <div class="form-group checkbox-group">
            {% for platform in ott_platforms_list %}<label><input type="checkbox" name="ott_platforms" value="{{ platform.name }}" {% if movie.ott_platforms and platform.name in movie.ott_platforms %}checked{% endif %}> {{ platform.name }}</label>{% endfor %}
        </div>
    </fieldset>

    <div id="movie_fields">
        <fieldset><legend>Movie Links</legend>
            {% set stream_link_1 = (movie.streaming_links | selectattr('name', 'equalto', '480p') | map(attribute='url') | first) or '' %}
            {% set stream_link_2 = (movie.streaming_links | selectattr('name', 'equalto', '720p') | map(attribute='url') | first) or '' %}
            {% set stream_link_3 = (movie.streaming_links | selectattr('name', 'equalto', '1080p') | map(attribute='url') | first) or '' %}
            <p><b>Streaming Links (Optional)</b></p>
            <div class="form-group"><label>Streaming Link 1 (480p):</label><input type="url" name="streaming_link_1" value="{{ stream_link_1 }}" /></div>
            <div class="form-group"><label>Streaming Link 2 (720p):</label><input type="url" name="streaming_link_2" value="{{ stream_link_2 }}" /></div>
            <div class="form-group"><label>Streaming Link 3 (1080p):</label><input type="url" name="streaming_link_3" value="{{ stream_link_3 }}" /></div><hr>
            
            <p><b>Direct Download Links</b></p>
            <div class="form-group"><label>480p Link:</label><input type="url" name="link_480p" value="{% for l in movie.links %}{% if l.quality == '480p' %}{{ l.url }}{% endif %}{% endfor %}" /></div>
            <div class="form-group"><label>720p Link:</label><input type="url" name="link_720p" value="{% for l in movie.links %}{% if l.quality == '720p' %}{{ l.url }}{% endif %}{% endfor %}" /></div>
            <div class="form-group"><label>1080p Link:</label><input type="url" name="link_1080p" value="{% for l in movie.links %}{% if l.quality == '1080p' %}{{ l.url }}{% endif %}{% endfor %}" /></div><hr>

            <p><b>Get from Telegram</b></p>
            <div class="form-group"><label>480p Telegram Link:</label><input type="url" name="telegram_link_480p" value="{% for f in movie.files %}{% if f.quality == '480p' %}{{ f.url }}{% endif %}{% endfor %}" /></div>
            <div class="form-group"><label>720p Telegram Link:</label><input type="url" name="telegram_link_720p" value="{% for f in movie.files %}{% if f.quality == '720p' %}{{ f.url }}{% endif %}{% endfor %}" /></div>
            <div class="form-group"><label>1080p Telegram Link:</label><input type="url" name="telegram_link_1080p" value="{% for f in movie.files %}{% if f.quality == '1080p' %}{{ f.url }}{% endif %}{% endfor %}" /></div>
        </fieldset>
    </div>

    <div id="episode_fields" style="display: none;">
      <fieldset><legend>Individual Episodes</legend>
        <div id="episodes_container">
        {% if movie.type == 'series' and movie.episodes %}{% for ep in movie.episodes|sort(attribute='episode_number')|sort(attribute='season') %}<div class="dynamic-item">
            <button type="button" onclick="this.parentElement.remove()" class="btn btn-danger">X</button>
            <div class="form-group"><label>Season:</label><input type="number" name="episode_season[]" value="{{ ep.season or 1 }}" required></div>
            <div class="form-group"><label>Episode Number (e.g., 1 or 1-10):</label><input type="text" name="episode_number[]" value="{{ ep.episode_number }}" required></div>
            <div class="form-group"><label>Title:</label><input type="text" name="episode_title[]" value="{{ ep.title or '' }}"></div><hr>
            <p><b>Links:</b></p>
            <div class="form-group"><label>Streaming Link:</label><input type="url" name="episode_stream_link[]" value="{{ ep.stream_link or '' }}"></div>
            <div class="form-group"><label>Download Link:</label><input type="url" name="episode_download_link[]" value="{{ ep.download_link or '' }}"></div>
            <div class="form-group"><label>Telegram Link:</label><input type="url" name="episode_telegram_link[]" value="{{ ep.telegram_link or '' }}"></div><hr>
            <p><b>Custom Links (Optional):</b></p>
            <div class="form-group"><label>Links (One per line: Button Text | URL):</label><textarea name="episode_links[]" rows="3">{% for link in ep.links %}{{ link.text }} | {{ link.url }}{% if not loop.last %}
{% endif %}{% endfor %}</textarea></div>
        </div>{% endfor %}{% endif %}</div><button type="button" onclick="addEpisodeField()" class="btn btn-secondary"><i class="fas fa-plus"></i> Add Episode</button></fieldset>
    </div>
    
    <!-- START: NEW TELEGRAM NOTIFY CHECKBOX (এই অংশটি যোগ করুন) -->
    <div class="form-group" style="background: #111; padding: 15px; border-radius: 5px;">
        <label style="display: flex; align-items: center; gap: 10px; cursor: pointer;">
            <input type="checkbox" name="notify_telegram" value="yes" style="width: auto; height: 20px; width: 20px;">
            <strong>Notify Telegram Channel About This Update</strong>
        </label>
    </div>
    <!-- END: NEW TELEGRAM NOTIFY CHECKBOX -->
    
    <button type="submit" class="btn btn-primary"><i class="fas fa-save"></i> Update Content</button>
  </form>
</div>
<script>
    function toggleFields() { var isSeries = document.getElementById('content_type').value === 'series'; document.getElementById('episode_fields').style.display = isSeries ? 'block' : 'none'; document.getElementById('movie_fields').style.display = isSeries ? 'none' : 'block'; }
    function addTelegramFileField() { const c = document.getElementById('telegram_files_container'); const d = document.createElement('div'); d.className = 'dynamic-item'; d.innerHTML = `<button type="button" onclick="this.parentElement.remove()" class="btn btn-danger"><i class="fas fa-times"></i></button><div class="form-group"><label>Quality (e.g., 720p):</label><input type="text" name="telegram_quality[]" required /></div><div class="form-group"><label>Telegram URL:</label><input type="url" name="telegram_url[]" placeholder="https://t.me/..." required /></div>`; c.appendChild(d); }
    function addEpisodeField() { const c = document.getElementById('episodes_container'); const d = document.createElement('div'); d.className = 'dynamic-item'; d.innerHTML = `<button type="button" onclick="this.parentElement.remove()" class="btn btn-danger">X</button><div class="form-group"><label>Season:</label><input type="number" name="episode_season[]" value="1" required></div><div class="form-group"><label>Episode Number (e.g., 1 or 1-10):</label><input type="text" name="episode_number[]" required></div><div class="form-group"><label>Title:</label><input type="text" name="episode_title[]"></div><hr style="margin:15px 0;"><p><b>Links:</b></p><div class="form-group"><label>Streaming Link:</label><input type="url" name="episode_stream_link[]" /></div><div class="form-group"><label>Download Link:</label><input type="url" name="episode_download_link[]" /></div><div class="form-group"><label>Telegram Link:</label><input type="url" name="episode_telegram_link[]" /></div><hr style="margin:15px 0;"><p><b>Custom Links (Optional):</b></p><div class="form-group"><label>Links (One per line: Button Text | URL):</label><textarea name="episode_links[]" rows="3" placeholder="e.g., Watch G-Drive | https://..."></textarea></div>`; c.appendChild(d); }
    // ... addEpisodeField() ফাংশনের ঠিক পরে এটি যোগ করতে পারেন ...
    function addBackdropField() { const c = document.getElementById('backdrop_images_container'); const d = document.createElement('div'); d.className = 'dynamic-item'; d.innerHTML = `<button type="button" onclick="this.parentElement.remove()" class="btn btn-danger"><i class="fas fa-times"></i></button><div class="form-group"><label>Image URL:</label><input type="url" name="backdrop_images[]" placeholder="https://image.tmdb.org/..." required /></div>`; c.appendChild(d); }
    document.addEventListener('DOMContentLoaded', toggleFields);
</script>
</body></html>
"""

# আপনার index (2) (12).py ফাইলের ভেতরে এই সম্পূর্ণ কোড ব্লকটি পেস্ট করুন

download_hub_html = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>Download Hub: {{ movie.title }} - {{ website_name }}</title>
    <link rel="icon" href="https://i.postimg.cc/L4kGt56P/1000018917-removebg-preview.png" type="image/png">
    <meta name="robots" content="noindex, nofollow">
    <link href="https://fonts.googleapis.com/css2?family=Poppins:wght@400;500;600;700&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.2.0/css/all.min.css">
    <style>
        :root { --primary-color: #E50914; --bg-color: #141414; --card-bg: #1a1a1a; --text-light: #ffffff; --text-dark: #a0a0a0; --stream-color: #007bff; --telegram-color: #2AABEE; }
        body { font-family: 'Poppins', sans-serif; background-color: var(--bg-color); color: var(--text-light); margin: 0; padding: 20px; display: flex; flex-direction: column; justify-content: center; align-items: center; min-height: 100vh; }
        
        /* Main Hub Container */
        .hub-container { background-color: var(--card-bg); width: 100%; max-width: 700px; border-radius: 12px; box-shadow: 0 10px 40px rgba(0,0,0,0.6); overflow: hidden; border: 1px solid #333; margin-bottom: 40px; }
        .hub-header { padding: 20px; background-color: #111; text-align: center; }
        .hub-header h1 { font-size: 1.5rem; margin: 0 0 5px 0; }
        .hub-header p { font-size: 0.9rem; color: var(--text-dark); margin: 0; }
        .hub-body { padding: 25px; }
        .disclaimer-box { background-color: rgba(255, 193, 7, 0.1); border: 1px solid #ffc107; color: #ffc107; padding: 15px; border-radius: 8px; margin-bottom: 25px; font-size: 0.9rem; text-align: center; }
        
        /* Tabs and Link Buttons */
        .quality-tabs { display: flex; flex-wrap: wrap; gap: 10px; margin-bottom: 25px; }
        .tab-btn { flex-grow: 1; padding: 12px 10px; font-size: 1rem; font-weight: 600; color: var(--text-dark); background-color: #282828; border: none; border-radius: 6px; cursor: pointer; transition: all 0.2s ease; }
        .tab-btn.active { background-color: var(--primary-color); color: white; }
        .quality-content { display: none; }
        .quality-content.active { display: block; animation: fadeIn 0.4s; }
        @keyframes fadeIn { from { opacity: 0; } to { opacity: 1; } }
        .link-button { display: flex; align-items: center; width: 100%; text-align: left; padding: 15px 20px; margin-bottom: 12px; border-radius: 8px; text-decoration: none; color: white; font-weight: 500; font-size: 1rem; transition: transform 0.2s ease, background-color 0.2s ease; box-sizing: border-box; }
        .link-button:hover { transform: scale(1.02); }
        .link-button i { font-size: 1.3rem; margin-right: 15px; width: 25px; text-align: center; }
        .link-button.stream { background-color: var(--stream-color); } .link-button.stream:hover { background-color: #0069d9; }
        .link-button.download { background-color: var(--primary-color); } .link-button.download:hover { background-color: #B20710; }
        .link-button.telegram { background-color: var(--telegram-color); } .link-button.telegram:hover { background-color: #1e96d1; }
        .no-links { text-align: center; color: var(--text-dark); padding: 20px; }
        
        /* Report Button Styles */
        .hub-footer-actions { text-align: center; padding: 0 25px 25px; }
        .report-button-hub { display: inline-flex; align-items: center; gap: 10px; padding: 10px 20px; border-radius: 6px; text-decoration: none; font-size: 0.9rem; font-weight: 500; background-color: #444; color: var(--text-light); transition: background-color 0.2s ease; }
        .report-button-hub:hover { background-color: #555; }
        .report-button-hub i { margin-right: 5px; }
        
        /* Professional Footer Styles */
        .professional-footer { width: 100%; background: linear-gradient(to bottom, #1a1a1a, #0f0f0f); color: var(--text-dark); padding-top: 60px; margin-top: auto; border-top: 4px solid #000; }
        .footer-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 40px; padding-bottom: 50px; max-width: 1200px; margin: 0 auto; padding-left: 20px; padding-right: 20px; }
        .footer-column-title { font-size: 1.3rem; font-weight: 600; color: var(--text-light); margin-bottom: 25px; position: relative; padding-bottom: 10px; }
        .footer-column-title::after { content: ''; position: absolute; bottom: 0; left: 0; width: 50px; height: 3px; background-color: var(--primary-color); }
        .footer-logo img { max-width: 160px; margin-bottom: 15px; }
        .footer-description { font-size: 0.95rem; line-height: 1.7; }
        .links-section ul { list-style: none; padding: 0; margin: 0; } .links-section ul li { margin-bottom: 12px; }
        .links-section ul li a { display: flex; align-items: center; gap: 10px; text-decoration: none; color: var(--text-dark); transition: all 0.2s ease-in-out; }
        .links-section ul li a:hover { color: var(--primary-color); transform: translateX(5px); }
        .telegram-button { display: flex; align-items: center; gap: 15px; padding: 12px 15px; border-radius: 8px; text-decoration: none; color: white; background-color: rgba(255, 255, 255, 0.05); border: 1px solid rgba(255, 255, 255, 0.1); transition: all 0.2s ease; }
        .telegram-button:hover { background-color: rgba(255, 255, 255, 0.1); border-color: var(--primary-color); transform: translateY(-2px); }
        .telegram-button i { font-size: 1.8rem; width: 30px; text-align: center; }
        .telegram-button span { display: flex; flex-direction: column; } .telegram-button small { font-size: 0.75rem; color: var(--text-dark); }
        .footer-bottom-bar { background-color: #000; text-align: center; padding: 20px; font-size: 0.9rem; border-top: 1px solid #222; }
        /* ... আপনার অন্যান্য .telegram-button CSS এর সাথে যোগ করুন ... */
        .telegram-button.notification i { color: #34B7F1; } /* Telegram Blue */
        .telegram-button.request i { color: #f5c518; } /* Yellow for attention */
        .telegram-button.backup i { color: #28a745; } /* Green for safety */
  
        /* Responsive Footer Styles */
        @media (max-width: 768px) {
            .footer-grid { text-align: center; }
            .footer-column-title::after { left: 50%; transform: translateX(-50%); }
            .footer-logo { margin-left: auto; margin-right: auto; }
            .links-section ul li a { justify-content: center; }
        }
    </style>
</head>
<body>

<div class="hub-container">
    <div class="hub-header">
        <h1>{{ movie.title }}</h1>
        <p>Select your preferred quality and download source.</p>
    </div>
    <div class="hub-body">
        <div class="disclaimer-box">
            <strong>Notice:</strong> If Stream or Download links do not work due to server load, please use the <strong>Get from Telegram</strong> links for a faster experience.
        </div>

        {% if qualities %}
        <div class="quality-tabs">
            {% for quality in sorted_qualities %}
                <button class="tab-btn" data-quality="{{ quality }}">{{ quality }}</button>
            {% endfor %}
        </div>

        {% for quality, links in qualities.items() %}
        <div class="quality-content" id="content-{{ quality }}">
            {% for link in links %}
                <a href="{{ link.url }}" class="link-button {{ link.type }}" target="_blank">
                    <i class="fas fa-{{ 'play-circle' if link.type == 'stream' else 'download' if link.type == 'download' else 'paper-plane' }}"></i>
                    <span>
                        {% if link.type == 'stream' %}Stream in {{ link.name }} Video 
                        {% elif link.type == 'download' %}Download in {{ link.quality }} File
                        {% elif link.type == 'telegram' %}Get {{ link.quality }} from Telegram
                        {% endif %}
                    </span>
                </a>
            {% endfor %}
        </div>
        {% endfor %}
        {% else %}
            <p class="no-links">No download links are available for this content yet.</p>
        {% endif %}
    </div>
    <div class="hub-footer-actions">
        <a href="{{ url_for('request_content', report_id=movie._id, title=movie.title) }}" class="report-button-hub">
            <i class="fas fa-flag"></i> Report a Problem
        </a>
    </div>
</div> <!-- .hub-container ends here -->

<!-- Professional Footer -->
<footer class="professional-footer">
    <div class="footer-grid">
        <div class="footer-column about-section"><a href="{{ url_for('home') }}" class="footer-logo"><img src="https://i.postimg.cc/L4kGt56P/1000018917-removebg-preview.png" alt="{{ website_name }} Logo"></a><p class="footer-description">Your ultimate destination for the latest movies and web series. We are dedicated to providing a seamless entertainment experience.</p></div>
        <div class="footer-column links-section"><h4 class="footer-column-title">Site Links</h4><ul><li><a href="{{ url_for('dmca') }}"><i class="fas fa-gavel"></i> DMCA Policy</a></li><li><a href="{{ url_for('disclaimer') }}"><i class="fas fa-exclamation-triangle"></i> Disclaimer</a></li><li><a href="{{ url_for('create_website') }}"><i class="fas fa-palette"></i> Create Your Website</a></li></ul></div>
        <!-- Section 3: Join Our Community -->
        <div class="footer-column community-section">
            <h4 class="footer-column-title">Join Our Community</h4>
            <div class="telegram-buttons-container">
                <a href="https://t.me/+YhqvLHXHdIViNTRl" target="_blank" class="telegram-button notification">
                    <i class="fas fa-bell"></i>
                    <span><strong>New Content Alerts</strong><small>Get notified for every new upload</small></span>
                </a>
                <a href="https://t.me/+YhqvLHXHdIViNTRl" target="_blank" class="telegram-button request">
                    <i class="fas fa-comments"></i>
                    <span><strong>Join Request Group</strong><small>Request your favorite content</small></span>
                </a>
                <a href="https://t.me/TGLinkBase" target="_blank" class="telegram-button backup">
                    <i class="fas fa-shield-alt"></i>
                    <span><strong>Backup Channel</strong><small>Join for future updates</small></span>
                </a>
            </div>
            <p class="footer-note">
                <strong>Alternatively,</strong> you can use the <a href="{{ url_for('request_content') }}">Request</a> option in our bottom menu to submit requests directly on the site.
            </p>
        </div>
    <div class="footer-bottom-bar"><p>&copy; {{ datetime.utcnow().year }} {{ website_name }}. All Rights Reserved.</p></div>
</footer>

<script>
    document.addEventListener('DOMContentLoaded', function() {
        const tabs = document.querySelectorAll('.tab-btn');
        const contents = document.querySelectorAll('.quality-content');
        if (tabs.length > 0) {
            tabs[0].classList.add('active');
            if (contents.length > 0) contents[0].classList.add('active');
            tabs.forEach(tab => {
                tab.addEventListener('click', () => {
                    tabs.forEach(t => t.classList.remove('active'));
                    contents.forEach(c => c.classList.remove('active'));
                    tab.classList.add('active');
                    const quality = tab.getAttribute('data-quality');
                    document.getElementById('content-' + quality).classList.add('active');
                });
            });
        }
    });
</script>
</body>
</html>
"""


# আপনার index.py ফাইলের ভেতরে এই সম্পূর্ণ কোড ব্লকটি পেস্ট করুন

series_hub_html = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>Series Hub: {{ series.title }}</title>
    <link rel="icon" href="https://i.postimg.cc/LXSgKV1P/IMG-20251021-044957-147.jpg" type="image/png">
    <meta name="robots" content="noindex, nofollow">
    <link href="https://fonts.googleapis.com/css2?family=Poppins:wght@400;500;600;700&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.2.0/css/all.min.css">
    <style>
        :root { --primary-color: #E50914; --bg-color: #141414; --card-bg: #1a1a1a; --text-light: #ffffff; --text-dark: #a0a0a0; --stream-color: #007bff; --telegram-color: #2AABEE; }
        body { font-family: 'Poppins', sans-serif; background-color: var(--bg-color); color: var(--text-light); margin: 0; padding: 20px; display: flex; flex-direction: column; justify-content: center; align-items: center; min-height: 100vh; }
        .hub-container { background-color: var(--card-bg); width: 100%; max-width: 800px; margin: 20px auto; border-radius: 12px; box-shadow: 0 10px 40px rgba(0,0,0,0.6); overflow: hidden; border: 1px solid #333; }
        .hub-header { padding: 20px; background-color: #111; text-align: center; border-bottom: 1px solid #333;}
        .hub-header h1 { font-size: 1.8rem; margin: 0; }
        .hub-body { padding: 25px; }
        .disclaimer-box { background-color: rgba(255, 193, 7, 0.1); border: 1px solid #ffc107; color: #ffc107; padding: 15px; border-radius: 8px; margin-bottom: 25px; font-size: 0.9rem; text-align: center; }
        .season-tabs { display: flex; flex-wrap: wrap; gap: 10px; margin-bottom: 25px; border-bottom: 2px solid #333; padding-bottom: 15px; }
        .season-tab { padding: 10px 20px; font-size: 1rem; font-weight: 600; color: var(--text-dark); background-color: #282828; border: none; border-radius: 6px; cursor: pointer; transition: all 0.2s ease; }
        .season-tab.active { background-color: var(--primary-color); color: white; }
        .episode-list { display: none; }
        .episode-list.active { display: block; animation: fadeIn 0.4s; }
        @keyframes fadeIn { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: translateY(0); } }
        .episode-item-hub { background-color: #222; padding: 15px; border-radius: 8px; margin-bottom: 10px; }
        .episode-title-hub { font-weight: 600; font-size: 1.1rem; margin-bottom: 15px; }
        .episode-buttons-hub { display: flex; flex-wrap: wrap; gap: 10px; }
        .custom-links-container { display: flex; flex-direction: column; gap: 10px; margin-top: 10px; width: 100%; }
        .link-button { display: inline-flex; flex-grow: 1; justify-content: center; align-items: center; gap: 8px; text-decoration: none; color: white; padding: 12px; border-radius: 6px; font-weight: 500; transition: filter 0.2s; }
        .link-button:hover { filter: brightness(1.1); }
        .link-button i { line-height: 1; }
        .link-button.stream { background-color: var(--stream-color); }
        .link-button.download { background-color: var(--primary-color); }
        .link-button.telegram { background-color: var(--telegram-color); }
        .link-button.custom { background-color: #555; }
        .no-episodes { text-align: center; color: var(--text-dark); padding: 20px; }
        .hub-footer-actions { text-align: center; padding: 0 25px 25px; }
        .report-button-hub { display: inline-flex; align-items: center; gap: 10px; padding: 10px 20px; border-radius: 6px; text-decoration: none; font-size: 0.9rem; font-weight: 500; background-color: #444; color: var(--text-light); transition: background-color 0.2s ease; }
        .report-button-hub:hover { background-color: #555; }
        
        /* === [FINAL] Professional Footer Styles === */
        .professional-footer { width: 100%; background: linear-gradient(to bottom, #1a1a1a, #0f0f0f); color: var(--text-dark); padding-top: 60px; margin-top: auto; border-top: 4px solid #000; }
        .footer-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 40px; padding-bottom: 50px; max-width: 1200px; margin: 0 auto; padding-left: 20px; padding-right: 20px; }
        .footer-column-title { font-size: 1.3rem; font-weight: 600; color: var(--text-light); margin-bottom: 25px; position: relative; padding-bottom: 10px; }
        .footer-column-title::after { content: ''; position: absolute; bottom: 0; left: 0; width: 50px; height: 3px; background-color: var(--primary-color); }
        .footer-logo img { max-width: 160px; margin-bottom: 15px; }
        .footer-description { font-size: 0.95rem; line-height: 1.7; }
        .links-section ul { list-style: none; padding: 0; margin: 0; } .links-section ul li { margin-bottom: 12px; }
        .links-section ul li a { display: flex; align-items: center; gap: 10px; text-decoration: none; color: var(--text-dark); transition: all 0.2s ease-in-out; }
        .links-section ul li a:hover { color: var(--primary-color); transform: translateX(5px); }
        .telegram-buttons-container { display: flex; flex-direction: column; gap: 15px; }
        .telegram-button { display: flex; align-items: center; gap: 15px; padding: 12px 15px; border-radius: 8px; text-decoration: none; color: white; background-color: rgba(255, 255, 255, 0.05); border: 1px solid rgba(255, 255, 255, 0.1); transition: all 0.2s ease; }
        .telegram-button:hover { background-color: rgba(255, 255, 255, 0.1); border-color: var(--primary-color); transform: translateY(-2px); }
        .telegram-button i { font-size: 1.8rem; width: 30px; text-align: center; }
        .telegram-button span { display: flex; flex-direction: column; } .telegram-button small { font-size: 0.75rem; color: var(--text-dark); }
        .footer-bottom-bar { background-color: #000; text-align: center; padding: 20px; font-size: 0.9rem; border-top: 1px solid #222; }
        .telegram-button.notification i { color: #34B7F1; } .telegram-button.request i { color: #f5c518; } .telegram-button.backup i { color: #28a745; }
        @media (max-width: 768px) { .footer-grid { text-align: center; } .footer-column-title::after { left: 50%; transform: translateX(-50%); } .footer-logo { margin-left: auto; margin-right: auto; } .links-section ul li a { justify-content: center; } }
    </style>
</head>
<body>
<div class="hub-container">
    <div class="hub-header"><h1>{{ series.title }}</h1></div>
    <div class="hub-body">
        <div class="disclaimer-box">
            <strong>Notice:</strong> If Stream or Download links do not work due to server load, please use the <strong>Get from Telegram</strong> links for a faster experience.
        </div>
        {% if episodes_by_season %}
        <div class="season-tabs">
            {% for season_num in seasons_sorted %}
                <button class="season-tab" data-season="{{ season_num }}">Season {{ season_num }}</button>
            {% endfor %}
        </div>

        {% for season_num, episodes in episodes_by_season.items() %}
        <div class="episode-list" id="season-{{ season_num }}">
            {% for ep in episodes | sort(attribute='episode_number') %}
            <div class="episode-item-hub">
                <div class="episode-title-hub">Episode {{ ep.episode_number }}{% if ep.title %}: {{ ep.title }}{% endif %}</div>
                <div class="episode-buttons-hub">
                    {% if ep.stream_link %}
                    <a href="{{ ep.stream_link }}" class="link-button stream" target="_blank"><i class="fas fa-play"></i> Stream</a>
                    {% endif %}
                    {% if ep.download_link %}
                    <a href="{{ ep.download_link }}" class="link-button download" target="_blank"><i class="fas fa-download"></i> Download</a>
                    {% endif %}
                    {% if ep.telegram_link %}
                    <a href="{{ ep.telegram_link }}" class="link-button telegram" target="_blank"><i class="fab fa-telegram"></i> Get from Telegram</a>
                    {% endif %}
                </div>
                {% if ep.links %}
                <div class="custom-links-container">
                    {% for link in ep.links %}
                    <a href="{{ link.url }}" class="link-button custom" target="_blank"><i class="fas fa-link"></i> {{ link.text }}</a>
                    {% endfor %}
                </div>
                {% endif %}
            </div>
            {% endfor %}
        </div>
        {% endfor %}
        {% else %}
            <p class="no-episodes">No episodes are available for this series yet.</p>
        {% endif %}
    </div>
    <div class="hub-footer-actions">
        <a href="{{ url_for('request_content', report_id=series._id, title=series.title) }}" class="report-button-hub"><i class="fas fa-flag"></i> Report Problem with this Series</a>
    </div>
</div>

<footer class="professional-footer">
    <div class="container footer-grid">
        <div class="footer-column about-section">
            <a href="{{ url_for('home') }}" class="footer-logo">
                <img src="https://i.postimg.cc/L4kGt56P/1000018917-removebg-preview.png" alt="{{ website_name }} Logo">
            </a>
            <p class="footer-description">Your ultimate destination for the latest movies and web series. We are dedicated to providing a seamless entertainment experience.</p>
        </div>
        <div class="footer-column links-section">
            <h4 class="footer-column-title">Site Links</h4>
            <ul>
                <li><a href="{{ url_for('dmca') }}"><i class="fas fa-gavel"></i> DMCA Policy</a></li>
                <li><a href="{{ url_for('disclaimer') }}"><i class="fas fa-exclamation-triangle"></i> Disclaimer</a></li>
                <li><a href="{{ url_for('create_website') }}"><i class="fas fa-palette"></i> Create Your Website</a></li>
            </ul>
        </div>
        <div class="footer-column community-section">
            <h4 class="footer-column-title">Join Our Community</h4>
            <div class="telegram-buttons-container">
                <a href="https://t.me/+YhqvLHXHdIViNTRl" target="_blank" class="telegram-button notification">
                    <i class="fas fa-bell"></i>
                    <span><strong>New Content Alerts</strong><small>Get notified for every new upload</small></span>
                </a>
                <a href="https://t.me/+YhqvLHXHdIViNTRl" target="_blank" class="telegram-button request">
                    <i class="fas fa-comments"></i>
                    <span><strong>Join Request Group</strong><small>Request your favorite content</small></span>
                </a>
                <a href="https://t.me/TGLinkBase" target="_blank" class="telegram-button backup">
                    <i class="fas fa-shield-alt"></i>
                    <span><strong>Backup Channel</strong><small>Join for future updates</small></span>
                </a>
            </div>
        </div>
    </div>
    <div class="footer-bottom-bar">
        <p>&copy; {{ datetime.utcnow().year }} {{ website_name }}. All Rights Reserved.</p>
    </div>
</footer>

<script>
    document.addEventListener('DOMContentLoaded', function() {
        const tabs = document.querySelectorAll('.season-tab');
        const contents = document.querySelectorAll('.episode-list');
        if (tabs.length > 0) {
            tabs[0].classList.add('active');
            contents[0].classList.add('active');
            tabs.forEach(tab => {
                tab.addEventListener('click', () => {
                    tabs.forEach(t => t.classList.remove('active'));
                    contents.forEach(c => c.classList.remove('active'));
                    tab.classList.add('active');
                    const season = tab.getAttribute('data-season');
                    document.getElementById('season-' + season).classList.add('active');
                });
            });
        }
    });
</script>
</body>
</html>
"""


# === [NEW] DISCLAIMER, DMCA, CREATE WEBSITE TEMPLATES ===

disclaimer_html = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Disclaimer - {{ website_name }}</title>
    <link rel="icon" href="https://i.postimg.cc/LXSgKV1P/IMG-20251021-044957-147.jpg" type="image/png">
    <style>
        :root { --primary-color: #E50914; --bg-color: #141414; --card-bg: #1a1a1a; --text-light: #f5f5f5; --text-dark: #a0a0a0; }
        body { font-family: 'Poppins', sans-serif; background: var(--bg-color); color: var(--text-light); padding: 40px 20px; line-height: 1.6; }
        .container { max-width: 800px; margin: 0 auto; background: var(--card-bg); padding: 30px; border-radius: 8px; }
        h1 { color: var(--primary-color); font-size: 2.5rem; margin-bottom: 20px; text-align: center; }
        p { margin-bottom: 15px; color: var(--text-dark); }
        strong { color: var(--text-light); }
        .btn { display: inline-block; background-color: var(--primary-color); color: #fff; padding: 10px 20px; border-radius: 5px; text-decoration: none; font-weight: bold; transition: 0.3s; }
        .btn:hover { background-color: #b00610; text-decoration: none; }
        .button-container { text-align: center; margin-top: 30px; }
    </style>
</head>
<body>
    <div class="container">
        <h1>Disclaimer</h1>
        <p><strong>{{ website_name }}</strong> does not host, store, or upload any video, films, or media files. Our site does not own any of the content displayed. We are not responsible for the accuracy, compliance, copyright, legality, decency, or any other aspect of the content of other linked sites.</p>
        <p>The content available on this website is collected from various publicly available sources on the internet. We act as a search engine that indexes and displays hyperlinks to content that is freely available online. We do not exercise any control over the content of these external websites.</p>
        <p>All content is the copyright of their respective owners. We encourage all copyright owners to recognize that the links contained within this site are located elsewhere on the web. The embedded links are from other sites such as (but not limited to) YouTube, Dailymotion, Google Drive, etc. If you have any legal issues please contact the appropriate media file owners or host sites.</p>
        <p>If you believe that any content on our website infringes upon your copyright, please visit our <a href="{{ url_for('dmca') }}" class="btn">DMCA Page</a> for instructions on how to submit a takedown request.</p>

        <div class="button-container">
            <a href="{{ url_for('home') }}" class="btn">&larr; Back to Home</a>
        </div>
    </div>
</body>
</html>
"""

dmca_html = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>DMCA Policy - {{ website_name }}</title>
    <link rel="icon" href="https://i.postimg.cc/LXSgKV1P/IMG-20251021-044957-147.jpg" type="image/png">
    <style>
        :root { --primary-color: #E50914; --bg-color: #141414; --card-bg: #1a1a1a; --text-light: #f5f5f5; --text-dark: #a0a0a0; }
        body { font-family: 'Poppins', sans-serif; background: var(--bg-color); color: var(--text-light); padding: 40px 20px; line-height: 1.6; }
        .container { max-width: 800px; margin: 0 auto; background: var(--card-bg); padding: 30px; border-radius: 8px; }
        h1 { color: var(--primary-color); font-size: 2.5rem; margin-bottom: 20px; text-align: center; }
        h2 { font-size: 1.8rem; margin-top: 25px; margin-bottom: 10px; border-bottom: 2px solid var(--primary-color); padding-bottom: 5px; }
        p, li { margin-bottom: 15px; color: var(--text-dark); }
        ul { padding-left: 20px; }
        .btn { display: inline-block; background-color: var(--primary-color); color: #fff; padding: 10px 20px; border-radius: 5px; text-decoration: none; font-weight: bold; transition: 0.3s; }
        .btn:hover { background-color: #b00610; text-decoration: none; }
        .button-container { text-align: center; margin-top: 30px; }
    </style>
</head>
<body>
    <div class="container">
        <h1>DMCA Copyright Infringement Notification</h1>
        <p>{{ website_name }} respects the intellectual property rights of others and expects its users to do the same. In accordance with the Digital Millennium Copyright Act (DMCA), we will respond promptly to notices of alleged copyright infringement.</p>
        <p>As stated in our disclaimer, this website does not host any files on its servers. All content is provided by non-affiliated third parties from publicly available sources.</p>
        
        <h2>Procedure for Reporting Copyright Infringement:</h2>
        <p>If you are a copyright owner or an agent thereof and believe that any content on our website infringes upon your copyrights, you may submit a notification by providing our Copyright Agent with the following information in writing:</p>
        <ul>
            <li>A physical or electronic signature of a person authorized to act on behalf of the owner of an exclusive right that is allegedly infringed.</li>
            <li>Identification of the copyrighted work claimed to have been infringed.</li>
            <li>Identification of the material that is claimed to be infringing and information reasonably sufficient to permit us to locate the material (please provide the exact URL(s)).</li>
            <li>Information reasonably sufficient to permit us to contact you, such as an email address.</li>
            <li>A statement that you have a good faith belief that use of the material in the manner complained of is not authorized by the copyright owner, its agent, or the law.</li>
        </ul>

        <h2>Where to Send a Takedown Notice:</h2>
        <p>Please send your DMCA takedown notice to us via our contact page. We recommend using the "Problem Report" subject for faster processing.</p>
        <div class="button-container">
            <a href="{{ url_for('request_content') }}" class="btn">Go to Request/Contact Page</a>
        </div>
        <p>We will review your request and remove the infringing content within 48-72 hours.</p>

        <div class="button-container">
            <a href="{{ url_for('home') }}" class="btn">&larr; Back to Home</a>
        </div>
    </div>
</body>
</html>
"""

create_website_html = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Create Your Own Website - {{ website_name }}</title>
    <link rel="icon" href="https://i.postimg.cc/LXSgKV1P/IMG-20251021-044957-147.jpg" type="image/png">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.2.0/css/all.min.css">
    <style>
        :root { --primary-color: #E50914; --bg-color: #141414; --card-bg: #1a1a1a; --text-light: #f5f5f5; --text-dark: #a0a0a0; }
        body { font-family: 'Poppins', sans-serif; background: var(--bg-color); color: var(--text-light); padding: 40px 20px; line-height: 1.7; display: flex; flex-direction: column; align-items: center; justify-content: center; min-height: 100vh; }
        .container { max-width: 800px; margin: 0 auto; background: var(--card-bg); padding: 40px; border-radius: 8px; text-align: center; border: 1px solid #333; }
        h1 { color: var(--primary-color); font-size: 2.8rem; margin-bottom: 20px; }
        p { margin-bottom: 20px; color: var(--text-dark); font-size: 1.1rem; }
        strong { color: var(--text-light); }
        .contact-button { 
            display: inline-flex; align-items: center; gap: 12px; 
            background-color: #2AABEE; color: white; 
            padding: 15px 35px; border-radius: 50px; 
            font-size: 1.2rem; font-weight: 700; 
            text-decoration: none;
            transition: all 0.3s ease;
            margin-top: 20px;
        }
        .contact-button:hover { transform: scale(1.05); background-color: #1e96d1; box-shadow: 0 0 20px rgba(42, 171, 238, 0.5); }
        .contact-button i { font-size: 1.5rem; }
        .back-link { display: block; text-align: center; margin-top: 40px; font-weight: bold; color: var(--primary-color); text-decoration: none; }
    </style>
</head>
<body>
    <div class="container">
        <h1>Build a Professional Website With Us!</h1>
        <p>আপনি কি নিজের জন্য একটি মুভি স্ট্রিমিং, ফাইল শেয়ারিং অথবা যেকোনো ধরনের ব্যক্তিগত বা ব্যবসায়িক ওয়েবসাইট তৈরি করতে চান? আমরা আপনাকে সাহায্য করতে প্রস্তুত।</p>
        <p>আমরা খুব যত্ন সহকারে এবং আপনার চাহিদা অনুযায়ী আধুনিক ও আকর্ষণীয় ওয়েবসাইট তৈরি করে দেই। আমাদের বিশেষজ্ঞ টিম আপনাকে সেরা মানের পরিষেবা এবং সার্বক্ষণিক সহায়তা প্রদান করবে।</p>
        <p>আপনার স্বপ্নের ওয়েবসাইটটি তৈরি করতে আজই আমাদের সাথে যোগাযোগ করুন।</p>
        
        <a href="https://t.me/ctgmovies23" target="_blank" class="contact-button">
            <i class="fa-brands fa-telegram"></i>
            <span>Contact Us on Telegram</span>
        </a>

        <a href="{{ url_for('home') }}" class="back-link">&larr; Back to Home</a>
    </div>
</body>
</html>
"""

# --- TMDB API Helper Function ---
# ... কোডের আগের অংশ ...
def get_tmdb_details(tmdb_id, media_type):
    if not TMDB_API_KEY: return None
    search_type = "tv" if media_type == "tv" else "movie"
    try:
        # We add "images" to get backdrop images along with video data
        detail_url = f"https://api.themoviedb.org/3/{search_type}/{tmdb_id}?api_key={TMDB_API_KEY}&append_to_response=videos,images"
        res = requests.get(detail_url, timeout=10)
        res.raise_for_status()
        data = res.json()
        
        # Find the official YouTube trailer
        trailer_url = None
        # ... (বাকি trailer খোঁজার কোড অপরিবর্তিত থাকবে) ...
        videos = data.get("videos", {}).get("results", [])
        for video in videos:
            if video.get("site") == "YouTube" and video.get("type") == "Trailer":
                trailer_url = f"https://www.youtube.com/embed/{video.get('key')}"
                break

        # Extract backdrop images (get up to 10 images)
        backdrop_images = []
        backdrops = data.get("images", {}).get("backdrops", [])
        for backdrop in backdrops[:10]:
            backdrop_images.append(f"https://image.tmdb.org/t/p/w1280{backdrop.get('file_path')}")

        details = {
            "tmdb_id": tmdb_id,
            "title": data.get("title") or data.get("name"),
            "poster": f"https://image.tmdb.org/t/p/w500{data.get('poster_path')}" if data.get('poster_path') else None,
            "backdrop": f"https://image.tmdb.org/t/p/w1280{data.get('backdrop_path')}" if data.get('backdrop_path') else None,
            "backdrop_images": backdrop_images,  # <-- নতুন ডেটা যোগ করা হলো
            "overview": data.get("overview"),
            "release_date": data.get("release_date") or data.get("first_air_date"),
            "genres": [g['name'] for g in data.get("genres", [])],
            "vote_average": data.get("vote_average"),
            "type": "series" if search_type == "tv" else "movie",
            "trailer_url": trailer_url
        }
        return details
    except requests.RequestException as e:
        print(f"ERROR: TMDb API request failed: {e}")
        return None

# --- START: FINAL UPDATED TELEGRAM FUNCTION (এই সম্পূর্ণ কোডটি পেস্ট করুন) ---
def send_to_telegram(movie_data, movie_id):
    """
    Formats and sends a professionally designed notification to a Telegram channel.
    """
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHANNEL_ID:
        print("INFO: Telegram credentials not set. Skipping notification.")
        return

    # --- 1. Build the Enhanced Caption ---
    title = movie_data.get('title', 'Untitled')
    year = movie_data.get('release_year')
    full_title = f"{title} ({year})" if year else title
    
    caption_parts = [
        f"🔥 <b>New Content Added on {WEBSITE_NAME}!</b> 🔥",
        "━━━━━━━━━━━━━━━━━",
        f"🎬 <b>{full_title}</b>",
        "━━━━━━━━━━━━━━━━━"
    ]

    # Add a short, engaging overview if available
    overview = movie_data.get('overview', '')
    if overview:
        short_overview = overview if len(overview) < 150 else overview[:150] + '...'
        caption_parts.append(f"💬 <i>{short_overview}</i>")
        caption_parts.append("━━━━━━━━━━━━━━━━━")

    # Add key details
    details = []
    details.append(f"✨ <b>Type:</b> {movie_data.get('type', 'N/A').title()}")
    
    # --- এই অংশটি ব্যাজ যোগ করার জন্য ---
    if movie_data.get('poster_badge'):
        details.append(f"💌 <b>Badge:</b> {movie_data.get('poster_badge')}")

    if movie_data.get('genres'):
        details.append(f"🎭 <b>Genres:</b> {', '.join(movie_data.get('genres', []))}")
        
    if movie_data.get('languages'):
        details.append(f"🔊 <b>Language:</b> {', '.join(movie_data.get('languages', []))}")

    # Add Quality/Episode Info
    if movie_data['type'] == 'movie':
        qualities = set()
        for link in movie_data.get('links', []): qualities.add(link.get('quality'))
        for file in movie_data.get('files', []): qualities.add(file.get('quality'))
        quality_info = " | ".join(sorted([q for q in qualities if q], reverse=True))
        if quality_info:
             details.append(f"💿 <b>Quality:</b> {quality_info}")
    elif movie_data['type'] == 'series':
        seasons = sorted(list(set(ep.get('season') for ep in movie_data.get('episodes', []))))
        if seasons:
            season_summary = ", ".join([f"Season {s}" for s in seasons])
            details.append(f"📺 <b>Available:</b> {season_summary}")
    
    caption_parts.append("\n".join(details))
    caption_parts.append("━━━━━━━━━━━━━━━━━")
    caption_parts.append(f"👇 <b>Watch or Download on {WEBSITE_NAME}</b> 👇")
    
    caption = "\n".join(caption_parts)

    # --- 2. Build the Inline Keyboard with the New Button ---
    watch_url = url_for('movie_detail', movie_id=movie_id, _external=True)
    keyboard = {
        "inline_keyboard": [
            [{"text": "✅ Watch on Website", "url": watch_url}],
            [{"text": "🤔 How to Download?", "url": HOW_TO_DOWNLOAD_URL}],
            [{"text": "🔔 Join Our Backup Channel", "url": "https://t.me/TGLinkBase"}] # <-- নতুন বাটন
        ]
    }
    reply_markup = json.dumps(keyboard)

    # --- 3. Send the Photo to Telegram API ---
    api_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"
    payload = {
        'chat_id': TELEGRAM_CHANNEL_ID,
        'photo': movie_data.get('poster'),
        'caption': caption,
        'parse_mode': 'HTML',
        'reply_markup': reply_markup
    }

    try:
        response = requests.post(api_url, data=payload, timeout=20)
        response.raise_for_status()
        result = response.json()
        if result.get('ok'):
            print(f"SUCCESS: Successfully posted '{title}' to Telegram.")
        else:
            print(f"ERROR: Failed to post to Telegram. Response: {result.get('description')}")
    except requests.exceptions.RequestException as e:
        print(f"FATAL: An error occurred while sending request to Telegram: {e}")
# --- END: FINAL UPDATED TELEGRAM FUNCTION ---

from urllib.parse import urlparse, parse_qs

# --- [ADD THIS NEW HELPER FUNCTION] ---
def convert_to_embed_url(url):
    """Converts various YouTube URL formats to the embed format."""
    if not url or not isinstance(url, str):
        return ""

    # If it's already an embed link, return it as is
    if "youtube.com/embed/" in url:
        return url

    video_id = None
    parsed_url = urlparse(url)
    
    # Handle short URLs like youtu.be/VIDEO_ID
    if "youtu.be" in parsed_url.netloc:
        video_id = parsed_url.path[1:]
    
    # Handle long URLs like youtube.com/watch?v=VIDEO_ID
    if "youtube.com" in parsed_url.netloc:
        query_params = parse_qs(parsed_url.query)
        if 'v' in query_params:
            video_id = query_params['v'][0]

    if video_id:
        return f"https://www.youtube.com/embed/{video_id}"
    
    # If no valid YouTube ID is found, return empty
    return ""
    
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
        
def get_paginated_content(query_filter, page):
    skip = (page - 1) * ITEMS_PER_PAGE
    total_count = movies.count_documents(query_filter)
    content_list = list(movies.find(query_filter).sort('updated_at', -1).skip(skip).limit(ITEMS_PER_PAGE))
    pagination = Pagination(page, ITEMS_PER_PAGE, total_count)
    return content_list, pagination

# =======================================================================================
# === [START] FLASK ROUTES ==============================================================
# =======================================================================================
# --- নতুন এবং আপডেট করা কোড ---
@app.route('/')
def home():
    query = request.args.get('q', '').strip()
    if query:
        movies_list = list(movies.find({"title": {"$regex": query, "$options": "i"}}).sort('updated_at', -1))
        total_results = movies.count_documents({"title": {"$regex": query, "$options": "i"}})
        pagination = Pagination(1, ITEMS_PER_PAGE, total_results)
        return render_template_string(index_html, movies=movies_list, query=f'Results for "{query}"', is_full_page_list=True, pagination=pagination)

    available_otts = sorted([p for p in movies.distinct("ott_platforms") if p])
    
    # --- ডেটা সংগ্রহ করার নতুন লজিক ---
    slider_content = list(movies.find({}).sort('updated_at', -1).limit(10))
    
    # ★ নতুন: Featured সেকশনের জন্য ডেটা সংগ্রহ করা
    featured_content = list(movies.find({"categories": "Featured"}).sort('updated_at', -1).limit(10))
    
    # Trending কন্টেন্ট আগের মতোই থাকছে
    trending_content = list(movies.find({"categories": "Trending"}).sort('updated_at', -1).limit(10))
    
    latest_content = list(movies.find({}).sort('updated_at', -1).limit(10))
    latest_movies = list(movies.find({"type": "movie"}).sort('updated_at', -1).limit(10))
    latest_series = list(movies.find({"type": "series"}).sort('updated_at', -1).limit(10))
    coming_soon = list(movies.find({"categories": "Coming Soon"}).sort('updated_at', -1).limit(10))

    # টেমপ্লেটে পাঠানোর জন্য context প্রস্তুত করা
    context = {
        "slider_content": slider_content,
        "featured_content": featured_content, # ★ নতুন ভেরিয়েবল পাস করা হলো
        "trending_content": trending_content, # ★ Trending ভেরিয়েবল আগের মতোই থাকছে
        "latest_content": latest_content,
        "latest_movies": latest_movies,
        "latest_series": latest_series,
        "coming_soon": coming_soon,
        "available_otts": available_otts,
        "is_full_page_list": False
    }
    return render_template_string(index_html, **context)
    
@app.route('/movie/<movie_id>')
def movie_detail(movie_id):
    try:
        movie = movies.find_one({"_id": ObjectId(movie_id)})
        if not movie: return "Content not found", 404

        # ---> এইখানে ভিউ কাউন্ট বাড়ানোর কোডটি যোগ করতে হবে <---
        movies.update_one({"_id": ObjectId(movie_id)}, {"$inc": {"view_count": 1}})

        related_content = list(movies.find({"type": movie.get('type'), "_id": {"$ne": movie['_id']}}).sort('updated_at', -1).limit(12))
        return render_template_string(detail_html, movie=movie, related_content=related_content)
    except: return "Content not found", 404

# ===== নতুন ফাংশনটি এখানে যোগ করুন =====
@app.route('/download-hub/<movie_id>')
def download_hub(movie_id):
    try:
        movie = movies.find_one({"_id": ObjectId(movie_id)})
        if not movie:
            return "Content not found", 404

        qualities = {}

        # 1. Process streaming links
        for link in movie.get('streaming_links', []):
            q = link.get('name', 'Unknown').strip()
            if q not in qualities: qualities[q] = []
            qualities[q].append({**link, 'type': 'stream'})

        # 2. Process direct download links
        for link in movie.get('links', []):
            q = link.get('quality', 'Unknown').strip()
            if q not in qualities: qualities[q] = []
            qualities[q].append({**link, 'type': 'download'})

        # 3. Process telegram files
        for file in movie.get('files', []):
            q = file.get('quality', 'Unknown').strip()
            if q not in qualities: qualities[q] = []
            qualities[q].append({**file, 'type': 'telegram'})

        # Sort qualities (e.g., 1080p, 720p, 480p)
        def sort_key(q):
            try:
                num = int(''.join(filter(str.isdigit, q)))
                return -num # Negative for descending order
            except:
                return 0 # Fallback for non-numeric qualities

        sorted_qualities = sorted(qualities.keys(), key=sort_key)

        return render_template_string(download_hub_html, movie=movie, qualities=qualities, sorted_qualities=sorted_qualities)

    except Exception as e:
        print(f"Error in download_hub: {e}")
        return "An error occurred", 500
# ===== নতুন ফাংশন যোগ করা শেষ =====

# ... download_hub ফাংশনটি এখানে শেষ হবে ...

# ===== নতুন সিরিজ হাব ফাংশনটি এখানে যোগ করুন =====
@app.route('/series-hub/<series_id>')
def series_hub(series_id):
    try:
        series = movies.find_one({"_id": ObjectId(series_id), "type": "series"})
        if not series:
            return "Series not found", 404

        episodes_by_season = {}
        for ep in series.get('episodes', []):
            season_num = ep.get('season')
            if season_num not in episodes_by_season:
                episodes_by_season[season_num] = []
            episodes_by_season[season_num].append(ep)
        
        # Sort season numbers numerically
        seasons_sorted = sorted(episodes_by_season.keys())

        return render_template_string(series_hub_html, series=series, episodes_by_season=episodes_by_season, seasons_sorted=seasons_sorted)

    except Exception as e:
        print(f"Error in series_hub: {e}")
        return "An error occurred", 500
# ===== নতুন ফাংশন যোগ করা শেষ =====


@app.route('/movies')
def all_movies():
    page = request.args.get('page', 1, type=int)
    all_movie_content, pagination = get_paginated_content({"type": "movie"}, page)
    return render_template_string(index_html, movies=all_movie_content, query="All Movies", is_full_page_list=True, pagination=pagination)
# ঠিক এই ফাংশনটির নিচে নতুন কোড যোগ করবেন
@app.route('/series')
def all_series():
    page = request.args.get('page', 1, type=int)
    all_series_content, pagination = get_paginated_content({"type": "series"}, page)
    return render_template_string(index_html, movies=all_series_content, query="Web Series & TV Shows", is_full_page_list=True, pagination=pagination)

@app.route('/all-content')
def all_content():
    # একটি ফাঁকা {} ফিল্টার মানে mongoDB-তে সব ডকুমেন্ট খুঁজে বের করা।
    page = request.args.get('page', 1, type=int)
    all_recent_content, pagination = get_paginated_content({}, page) 
    return render_template_string(
        index_html, 
        movies=all_recent_content, 
        query="All Recently Added Content", # আপনার ইচ্ছামতো নাম দিতে পারেন
        is_full_page_list=True, 
        pagination=pagination
    )

# ... আপনার অন্যান্য Flask Routes
# ঠিক এইখানে নতুন ফাংশনটি যুক্ত করুন:
@app.route('/edit_auth_redirect/<movie_id>')
@requires_auth
def edit_auth_redirect(movie_id):
    """
    Successfully authenticates the user via Basic Auth 
    and redirects them to the actual content edit page.
    """
    # If the requires_auth decorator passes, the user is authenticated.
    return redirect(url_for('edit_movie', movie_id=movie_id))
# ... আপনার অন্যান্য Flask Routes

@app.route('/platform/<platform_name>')
def movies_by_platform(platform_name):
    page = request.args.get('page', 1, type=int)

    # decode the platform name for display
    decoded_name = unquote_plus(platform_name)  # 'Amazon%20Prime' -> 'Amazon Prime'

    # Query DB: try both decoded and raw values to be safe
    platform_content, pagination = get_paginated_content(
        {"ott_platforms": {"$in": [platform_name, decoded_name]}}, page
    )
    
    platform_data = { "name": decoded_name }

    return render_template_string(
        index_html,
        movies=platform_content,
        query=f'Available on {decoded_name}',
        is_full_page_list=True,
        pagination=pagination,
        platform_info=platform_data
    )
    
# ===== নতুন কোড শুরু =====
genres_html = """
<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8" /><meta name="viewport" content="width=device-width, initial-scale=1.0, user-scalable=no" /><title>Browse by Genre - {{ website_name }}</title>
<link rel="icon" href="https://i.postimg.cc/L4kGt56P/1000018917-removebg-preview.png" type="image/png">
<style>
  @import url('https://fonts.googleapis.com/css2?family=Poppins:wght@400;600;700&display=swap');
  :root { --primary-color: #E50914; --bg-color: #141414; --card-bg: #1a1a1a; --text-light: #f5f5f5; }
  body { font-family: 'Poppins', sans-serif; background-color: var(--bg-color); color: var(--text-light); } a { text-decoration: none; color: inherit; }
  .main-container { padding: 80px 15px 30px; } .page-title { font-size: 2.2rem; font-weight: 700; margin-bottom: 30px; text-align: center; color: var(--primary-color); }
  .back-button { color: var(--text-light); font-size: 1rem; margin-bottom: 20px; display: inline-block; } .back-button:hover { color: var(--primary-color); }
  .genre-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 15px; }
  .genre-card { background: var(--card-bg); border-radius: 8px; padding: 25px 15px; text-align: center; font-size: 1.1rem; font-weight: 600; transition: all 0.2s ease; border: 1px solid #333; }
  .genre-card:hover { transform: translateY(-5px); background: var(--primary-color); border-color: var(--primary-color); }
  @media (min-width: 768px) { .genre-grid { grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); } .main-container { padding: 100px 50px 50px; } }
</style><link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.2.0/css/all.min.css"></head>
<body>
<div class="main-container">
    <a href="{{ url_for('home') }}" class="back-button"><i class="fas fa-arrow-left"></i> Back to Home</a>
    <h1 class="page-title">Browse by Genres</h1>
    <div class="genre-grid">
        {% for genre in genres %}
            <a href="{{ url_for('movies_by_genre_name', genre_name=genre) }}" class="genre-card"><span>{{ genre }}</span></a>
        {% endfor %}
    </div>
</div>
</body></html>
"""

@app.route('/genres')
def genres_page():
    # ডাটাবেস থেকে সকল ইউনিক জেনর খুঁজে বের করা হচ্ছে
    all_genres = sorted([g for g in movies.distinct("genres") if g])
    return render_template_string(genres_html, genres=all_genres)


@app.route('/genre/<genre_name>')
def movies_by_genre_name(genre_name):
    # ===== এই লাইনটি যোগ করুন =====
    decoded_genre_name = unquote_plus(genre_name)
    # ============================
    
    page = request.args.get('page', 1, type=int)
    # এখানে decoded_genre_name ব্যবহার করুন
    genre_content, pagination = get_paginated_content({"genres": decoded_genre_name}, page)
    return render_template_string(index_html, movies=genre_content, query=f'Genres: {decoded_genre_name}', is_full_page_list=True, pagination=pagination)

@app.route('/category')
def movies_by_category():
    title = request.args.get('name')
    if not title: return redirect(url_for('home'))
    page = request.args.get('page', 1, type=int)
    
    query_filter = {}
    if title == "Latest Movies":
        query_filter = {"type": "movie"}
    elif title == "Latest Series":
        query_filter = {"type": "series"}
    else:
        query_filter = {"categories": title}
    
    # ★ নতুন: এটি একটি বিশেষ ভেরিয়েবল যা টেমপ্লেটকে বলে দেবে Featured পেজ দেখানো হচ্ছে কি না
    is_featured_page = (title == "Featured")

    content_list, pagination = get_paginated_content(query_filter, page)
    return render_template_string(
        index_html, 
        movies=content_list, 
        query=title, 
        is_full_page_list=True, 
        pagination=pagination,
        is_featured_page=is_featured_page # ★ নতুন ভেরিয়েবলটি টেমপ্লেটে পাস করা হলো
    )


@app.route('/request', methods=['GET', 'POST'])
def request_content():
    if request.method == 'POST':
        # ফর্ম থেকে সব তথ্য সংগ্রহ করা
        request_data = {
            "type": request.form.get("type"),
            "name": request.form.get("content_title"),  # 'name' ফিল্ড হিসেবে সেভ হচ্ছে
            "info": request.form.get("message"),       # 'info' ফিল্ড হিসেবে সেভ হচ্ছে
            "email": request.form.get("email", "").strip(),
            "reported_content_id": request.form.get("reported_content_id"),
            "status": "Pending", # ডিফল্ট স্ট্যাটাস
            "created_at": datetime.utcnow()
        }
        # নতুন সিস্টেমে 'requests_collection'-এ ডেটা সেভ করা হচ্ছে
        requests_collection.insert_one(request_data)
        
        # পুরোনো ডিজাইনের মতো একটি সাকসেস মেসেজসহ পেজটি আবার রেন্ডার করা হচ্ছে
        return render_template_string(request_html, message_sent=True)

    # GET রিকোয়েস্টের জন্য (যখন কোনো মুভি থেকে রিপোর্ট করা হয়)
    prefill_title = request.args.get('title', '')
    prefill_id = request.args.get('report_id', '')
    prefill_type = 'Problem Report' if prefill_id else 'Movie Request'
    
    return render_template_string(request_html, message_sent=False, prefill_title=prefill_title, prefill_id=prefill_id, prefill_type=prefill_type)
    
@app.route('/wait')
def wait_page():
    encoded_target_url = request.args.get('target')
    if not encoded_target_url:
        return redirect(url_for('home'))
    
    # ধাপ ২ এর জন্য URL তৈরি করুন
    next_step_url = url_for('wait_page_step2', target=encoded_target_url)
    
    # ধাপ ১ এর টেমপ্লেট রেন্ডার করুন
    return render_template_string(wait_step1_html, next_step_url=next_step_url)

@app.route('/wait/step2')
def wait_page_step2():
    encoded_target_url = request.args.get('target')
    if not encoded_target_url:
        return redirect(url_for('home'))
        
    # ধাপ ৩ এর জন্য URL তৈরি করুন
    next_step_url = url_for('wait_page_step3', target=encoded_target_url)

    # ধাপ ২ এর টেমপ্লেট রেন্ডার করুন
    return render_template_string(wait_step2_html, next_step_url=next_step_url)

@app.route('/wait/step3')
def wait_page_step3():
    encoded_target_url = request.args.get('target')
    if not encoded_target_url:
        return redirect(url_for('home'))
        
    # এটি চূড়ান্ত ধাপ, তাই এখানে URL টি decode করুন
    final_target_url = unquote(encoded_target_url)

    # চূড়ান্ত (ধাপ ৩) টেমপ্লেট রেন্ডার করুন
    return render_template_string(wait_step3_html, target_url=final_target_url)

# === [NEW] ROUTES FOR DISCLAIMER, DMCA, AND CREATE WEBSITE ===
@app.route('/disclaimer')
def disclaimer():
    return render_template_string(disclaimer_html)

@app.route('/dmca')
def dmca():
    return render_template_string(dmca_html)

@app.route('/create-website')
def create_website():
    return render_template_string(create_website_html)

# --- START: FINAL UPDATED ADMIN ROUTE (এই সম্পূর্ণ কোডটি পেস্ট করুন) ---
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
        elif form_action == "add_ott_platform":
            platform_name = request.form.get("ott_platform_name", "").strip()
            if platform_name: ott_platforms_collection.update_one({"name": platform_name}, {"$set": {"name": platform_name}}, upsert=True)
        elif form_action == "bulk_delete":
            ids_to_delete = request.form.getlist("selected_ids")
            if ids_to_delete: movies.delete_many({"_id": {"$in": [ObjectId(id_str) for id_str in ids_to_delete]}})
        
        elif form_action == "add_content":
            content_type = request.form.get("content_type", "movie")
            movie_data = {
                "title": request.form.get("title").strip(), "type": content_type,
                "poster": request.form.get("poster").strip() or PLACEHOLDER_POSTER,
                "view_count": 0,
                "backdrop": request.form.get("backdrop").strip() or None,
                "overview": request.form.get("overview").strip(),
                "languages": [lang.strip() for lang in request.form.get("languages", "").split(',') if lang.strip()],
                "poster_badge": request.form.get("poster_badge", "").strip() or None,
                "release_year": request.form.get("release_year").strip() or None, 
                "genres": [g.strip() for g in request.form.get("genres", "").split(',') if g.strip()],
                "ott_platforms": request.form.getlist("ott_platforms"),
                "categories": request.form.getlist("categories"),
                "trailer_url": convert_to_embed_url(request.form.get("trailer_url", "").strip()),
                "backdrop_images": request.form.getlist("backdrop_images[]"),
                "created_at": datetime.utcnow(), "updated_at": datetime.utcnow(),
                "streaming_links": [], "links": [], "files": [], "episodes": []
            }
            tmdb_id = request.form.get("tmdb_id")
            if tmdb_id:
                tmdb_details = get_tmdb_details(tmdb_id, "tv" if content_type == "series" else "movie")
                if tmdb_details:
                    movie_data.update({
                        'release_date': tmdb_details.get('release_date'),
                        'vote_average': tmdb_details.get('vote_average')
                    })
                    if not movie_data.get("trailer_url") and tmdb_details.get("trailer_url"):
                         movie_data["trailer_url"] = tmdb_details.get("trailer_url")

            if content_type == "movie":
                streaming_links_data = [
                    ("480p", request.form.get("streaming_link_1", "").strip()),
                    ("720p", request.form.get("streaming_link_2", "").strip()),
                    ("1080p", request.form.get("streaming_link_3", "").strip()),
                ]
                movie_data['streaming_links'] = [{"name": name, "url": url} for name, url in streaming_links_data if url]

                movie_data['links'] = [{"quality": q, "url": u} for q, u in [
                    ("480p", request.form.get("link_480p")), 
                    ("720p", request.form.get("link_720p")), 
                    ("1080p", request.form.get("link_1080p"))
                ] if u and u.strip()]

                movie_data['files'] = [{"quality": q, "url": u} for q, u in [
                    ("480p", request.form.get("telegram_link_480p")), 
                    ("720p", request.form.get("telegram_link_720p")), 
                    ("1080p", request.form.get("telegram_link_1080p"))
                ] if u and u.strip()]
            
            else: # This is for Series
                seasons = request.form.getlist('episode_season[]')
                ep_nums = request.form.getlist('episode_number[]')
                ep_titles = request.form.getlist('episode_title[]')
                ep_stream_links = request.form.getlist('episode_stream_link[]')
                ep_download_links = request.form.getlist('episode_download_link[]')
                ep_telegram_links = request.form.getlist('episode_telegram_link[]')
                ep_links_texts = request.form.getlist('episode_links[]')
                
                for s, e, t, stream, dl, telegram, links_text in zip(seasons, ep_nums, ep_titles, ep_stream_links, ep_download_links, ep_telegram_links, ep_links_texts):
                    if s.strip() and e.strip():
                        custom_links = []
                        for line in links_text.strip().splitlines():
                            if '|' in line:
                                parts = line.split('|', 1)
                                if len(parts) == 2 and parts[0].strip() and parts[1].strip():
                                    custom_links.append({"text": parts[0].strip(), "url": parts[1].strip()})
                        
                        movie_data['episodes'].append({
                            "season": int(s), "episode_number": e.strip(),
                            "title": t.strip(), "stream_link": stream.strip() or None,
                            "download_link": dl.strip() or None,
                            "telegram_link": telegram.strip() or None,
                            "links": custom_links,
                        })

            # ডেটাবেসে কনটেন্টটি যোগ করুন এবং এর নতুন আইডি নিন
            insert_result = movies.insert_one(movie_data)
            
            # টেলিগ্রামে পোস্ট পাঠানোর জন্য নতুন ফাংশনটিকে কল করুন
            # url_for ব্যবহার করার জন্য app context দরকার হয়
            with app.app_context():
                send_to_telegram(movie_data, insert_result.inserted_id)

        return redirect(url_for('admin'))
    
    page = request.args.get('page', 1, type=int)
    content_list, pagination = get_paginated_content({}, page)

    stats = {"total_content": movies.count_documents({}), "total_movies": movies.count_documents({"type": "movie"}), "total_series": movies.count_documents({"type": "series"}), "pending_requests": requests_collection.count_documents({"status": "Pending"})}
    requests_list = list(requests_collection.find().sort("created_at", -1))
    categories_list = list(categories_collection.find().sort("name", 1))
    ott_platforms_list = list(ott_platforms_collection.find().sort("name", 1))
    ad_settings_data = settings.find_one({"_id": "ad_config"}) or {}
    return render_template_string(admin_html, content_list=content_list, stats=stats, requests_list=requests_list, ad_settings=ad_settings_data, categories_list=categories_list, ott_platforms_list=ott_platforms_list, pagination=pagination)
# --- END: FINAL UPDATED ADMIN ROUTE ---

@app.route('/admin/category/delete/<cat_id>')
@requires_auth
def delete_category(cat_id):
    try: categories_collection.delete_one({"_id": ObjectId(cat_id)})
    except: pass
    return redirect(url_for('admin'))

@app.route('/admin/ott_platform/delete/<platform_id>')
@requires_auth
def delete_ott_platform(platform_id):
    try: ott_platforms_collection.delete_one({"_id": ObjectId(platform_id)})
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

# --- START: FINAL UPDATED EDIT_MOVIE FUNCTION (এই সম্পূর্ণ কোডটি পেস্ট করুন) ---
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
            "languages": [lang.strip() for lang in request.form.get("languages", "").split(',') if lang.strip()],
            "poster_badge": request.form.get("poster_badge").strip() or None,
            "release_year": request.form.get("release_year").strip() or None, 
            "genres": [g.strip() for g in request.form.get("genres").split(',') if g.strip()],
            "ott_platforms": request.form.getlist("ott_platforms"),
            "categories": request.form.getlist("categories"),
            "trailer_url": convert_to_embed_url(request.form.get("trailer_url", "").strip()),
            "backdrop_images": request.form.getlist("backdrop_images[]"),
            "updated_at": datetime.utcnow()
        }
        
        if content_type == "movie":
            streaming_links_data = [
                ("480p", request.form.get("streaming_link_1", "").strip()),
                ("720p", request.form.get("streaming_link_2", "").strip()),
                ("1080p", request.form.get("streaming_link_3", "").strip()),
            ]
            update_data["streaming_links"] = [{"name": name, "url": url} for name, url in streaming_links_data if url]
            update_data["links"] = [{"quality": q, "url": u} for q, u in [("480p", request.form.get("link_480p")), ("720p", request.form.get("link_720p")), ("1080p", request.form.get("link_1080p"))] if u and u.strip()]
            
            update_data["files"] = [{"quality": q, "url": u} for q, u in [
                ("480p", request.form.get("telegram_link_480p")), 
                ("720p", request.form.get("telegram_link_720p")), 
                ("1080p", request.form.get("telegram_link_1080p"))
            ] if u and u.strip()]
            
            movies.update_one({"_id": obj_id}, {"$set": update_data, "$unset": {"episodes": ""}})
        
        else: # This is for series
            update_data["episodes"] = []
            seasons = request.form.getlist('episode_season[]')
            ep_nums = request.form.getlist('episode_number[]')
            ep_titles = request.form.getlist('episode_title[]')
            ep_stream_links = request.form.getlist('episode_stream_link[]')
            ep_download_links = request.form.getlist('episode_download_link[]')
            ep_telegram_links = request.form.getlist('episode_telegram_link[]')
            ep_links_texts = request.form.getlist('episode_links[]')

            for s, e, t, stream, dl, telegram, links_text in zip(seasons, ep_nums, ep_titles, ep_stream_links, ep_download_links, ep_telegram_links, ep_links_texts):
                if s.strip() and e.strip():
                    custom_links = []
                    for line in links_text.strip().splitlines():
                        if '|' in line:
                            parts = line.split('|', 1)
                            if len(parts) == 2 and parts[0].strip() and parts[1].strip():
                                custom_links.append({"text": parts[0].strip(), "url": parts[1].strip()})
                    
                    update_data["episodes"].append({
                        "season": int(s), "episode_number": e.strip(),
                        "title": t.strip(), "stream_link": stream.strip() or None,
                        "download_link": dl.strip() or None,
                        "telegram_link": telegram.strip() or None,
                        "links": custom_links
                    })
            
            movies.update_one({"_id": obj_id}, {"$set": update_data, "$unset": {"links": "", "streaming_links": "", "files": ""}})
        
        # --- START: NEW TELEGRAM NOTIFICATION LOGIC FOR EDIT ---
        # চেক করুন অ্যাডমিন নোটিফিকেশন পাঠাতে চান কিনা
        if request.form.get("notify_telegram") == "yes":
            # পোস্ট পাঠানোর জন্য movie_data এবং movie_id দুটোই দরকার
            # movie_data হলো update_data এবং movie_id হলো obj_id
            with app.app_context():
                send_to_telegram(update_data, obj_id)
        # --- END: NEW TELEGRAM NOTIFICATION LOGIC FOR EDIT ---
        
        return redirect(url_for('admin'))
    
    categories_list = list(categories_collection.find().sort("name", 1))
    ott_platforms_list = list(ott_platforms_collection.find().sort("name", 1))
    return render_template_string(edit_html, movie=movie_obj, categories_list=categories_list, ott_platforms_list=ott_platforms_list)
# --- END: FINAL UPDATED EDIT_MOVIE FUNCTION ---
    
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
        results = list(movies.find({"title": {"$regex": query, "$options": "i"} if query else {}}, {"_id": 1, "title": 1, "type": 1, "view_count": 1}).sort('updated_at', -1))
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
    details = get_tmdb_details(tmdb_id, media_type)
    if details: return jsonify(details)
    else: return jsonify({"error": "Details not found on TMDb"}), 404

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
    # For local development
    port = int(os.environ.get('PORT', 3000))
    app.run(debug=True, host='0.0.0.0', port=port)
