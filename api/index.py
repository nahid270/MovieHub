import os
import sys
import requests
import json
from flask import Flask, render_template_string, request, redirect, url_for, Response, jsonify, flash
from pymongo import MongoClient
from bson.objectid import ObjectId
from functools import wraps
from urllib.parse import unquote, quote
from datetime import datetime, timedelta
import math
import re

# --- Environment Variables ---
MONGO_URI = os.environ.get("MONGO_URI", "mongodb+srv://mewayo8672:mewayo8672@cluster0.ozhvczp.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0")
TMDB_API_KEY = os.environ.get("TMDB_API_KEY", "7dc544d9253bccc3cfecc1c677f69819")
ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "Nahid421")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "Nahid421")
WEBSITE_NAME = os.environ.get("WEBSITE_NAME", "CineZoneBD")
DEVELOPER_TELEGRAM_ID = os.environ.get("DEVELOPER_TELEGRAM_ID", "CineZoneBDBot")
WEBSITE_URL = os.environ.get("WEBSITE_URL", "https://your-website-url.com") # [গুরুত্বপূর্ণ] আপনার ওয়েবসাইটের সঠিক URL এখানে দিন

# পুরনো টেলিগ্রাম ভ্যারিয়েবলগুলো এখন শুধু একটি সেটিং হিসেবে ব্যবহৃত হবে না, DB তে সেভ হবে।
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHANNEL_ID = os.environ.get("TELEGRAM_CHANNEL_ID")

# --- Community Links Configuration ---
COMMUNITY_LINKS = [
    {
        'title': 'New Content Alerts',
        'subtitle': 'Get notified for every new upload',
        'icon_class': 'fas fa-bell',
        'icon_color': '#3b9eff',
        'url': 'https://t.me/+YhqvLHXHdIViNTRl'
    },
    {
        'title': 'Join Request Group',
        'subtitle': 'Request your favorite content',
        'icon_class': 'fas fa-comments',
        'icon_color': '#ffc107',
        'url': 'https://t.me/Movie_Request_Group_23'
    },
    {
        'title': 'Backup Channel',
        'subtitle': 'Join for future updates',
        'icon_class': 'fas fa-shield-alt',
        'icon_color': '#28a745',
        'url': 'https://t.me/+60goZWp-FpkxNzVl'
    }
]


# --- App Initialization ---
PLACEHOLDER_POSTER = "https://via.placeholder.com/400x600.png?text=Poster+Not+Found"
ITEMS_PER_PAGE = 20
ADMIN_ITEMS_PER_PAGE = 30 # নতুন: অ্যাডমিন প্যানেলের জন্য প্রতি পৃষ্ঠায় আইটেম সংখ্যা
app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "a_super_secret_key_for_flash_messages")


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
    ott_collection = db["ott_platforms"]
    print("SUCCESS: Successfully connected to MongoDB!")

    if categories_collection.count_documents({}) == 0:
        default_categories = ["Bangla", "Hindi", "English", "18+ Adult", "Korean", "Dual Audio", "Bangla Dubbed", "Hindi Dubbed", "Indonesian", "Horror", "Action", "Thriller", "Anime", "Romance", "Trending"]
        # নতুন: ডিফল্ট ক্যাটাগরিতে order ফিল্ড যোগ করা হচ্ছে
        categories_to_insert = [{"name": cat, "order": i} for i, cat in enumerate(default_categories)]
        categories_collection.insert_many(categories_to_insert)
        print("SUCCESS: Initialized default categories in the database with order.")
    
    # One-time migration for old categories without 'order' field
    if categories_collection.count_documents({"order": {"$exists": False}}) > 0:
        print("INFO: Migrating old categories to include 'order' field...")
        cats_to_update = list(categories_collection.find({"order": {"$exists": False}}))
        max_order_doc = categories_collection.find_one(sort=[("order", -1)])
        next_order = (max_order_doc['order'] + 1) if max_order_doc and 'order' in max_order_doc else 0
        for i, cat in enumerate(cats_to_update):
            categories_collection.update_one({"_id": cat["_id"]}, {"$set": {"order": next_order + i}})
        print(f"SUCCESS: Migrated {len(cats_to_update)} categories.")


    default_design_settings = {
        "_id": "design_config",
        "language_tag_css": "padding: 3px 8px; font-size: 0.7rem; top: 8px; right: 8px; background-color: #00ffaa; color: #111; font-weight: 700; border-radius: 4px; box-shadow: 0 0 8px rgba(0, 255, 170, 0.5); z-index: 5;",
        "new_badge_css": "background-color: var(--primary-color); color: white; padding: 4px 12px 4px 8px; font-size: 0.7rem; font-weight: 700; z-index: 3; clip-path: polygon(0 0, 100% 0, 85% 100%, 0 100%);",
        "new_badge_text": "NEW"
    }
    if not settings.find_one({"_id": "design_config"}):
        settings.insert_one(default_design_settings)
        print("SUCCESS: Initialized default design settings.")

    try:
        movies.create_index("title")
        movies.create_index("type")
        movies.create_index("categories")
        movies.create_index("updated_at")
        movies.create_index("tmdb_id")
        movies.create_index("ott_platform")
        categories_collection.create_index("name", unique=True)
        categories_collection.create_index("order") # নতুন: order ফিল্ডের জন্য ইনডেক্স
        ott_collection.create_index("name", unique=True)
        requests_collection.create_index("status")
        print("SUCCESS: MongoDB indexes checked/created.")
    except Exception as e:
        print(f"WARNING: Could not create MongoDB indexes: {e}")

    result = movies.update_many(
        {"updated_at": {"$exists": False}},
        [{"$set": {"updated_at": "$created_at"}}]
    )
    if result.modified_count > 0:
        print(f"SUCCESS: Migrated {result.modified_count} old documents to include 'updated_at' field.")

except Exception as e:
    print(f"FATAL: Error connecting to MongoDB: {e}.")
    if os.environ.get('VERCEL') != '1':
        sys.exit(1)

# --- Helper function to format series info ---
def format_series_info(episodes, season_packs):
    info_parts = []
    if season_packs:
        sorted_packs = sorted(season_packs, key=lambda p: p.get('season_number', 0))
        for pack in sorted_packs:
            season_num = pack.get('season_number')
            if season_num is not None:
                info_parts.append(f"S{season_num:02d} [COMPLETE SEASON]")
    if episodes:
        episodes_by_season = {}
        for ep in episodes:
            season = ep.get('season')
            ep_num = ep.get('episode_number')
            if season is not None and ep_num is not None:
                if season not in episodes_by_season: episodes_by_season[season] = []
                episodes_by_season[season].append(ep_num)
        for season in sorted(episodes_by_season.keys()):
            ep_nums = sorted(episodes_by_season[season])
            if not ep_nums: continue
            ep_range = f"EP{ep_nums[0]:02d}" if len(ep_nums) == 1 else f"EP{ep_nums[0]:02d}-{ep_nums[-1]:02d}"
            info_parts.append(f"S{season:02d} [{ep_range} ADDED]")
    return " & ".join(info_parts)


# --- [MODIFIED] Telegram Notification Function ---
def send_telegram_notification(movie_data, content_id, notification_type='new', series_update_info=None):
    # This function now ignores content_id, notification_type, and series_update_info
    # as the caption is static as per your request.
    
    tele_configs = settings.find_one({"_id": "telegram_config"}) or {}
    channels = tele_configs.get('channels', [])

    if not channels and (not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHANNEL_ID):
        print("INFO: No Telegram channels configured. Skipping notification.")
        return

    if TELEGRAM_BOT_TOKEN and TELEGRAM_CHANNEL_ID:
        if not any(c.get('channel_id') == TELEGRAM_CHANNEL_ID for c in channels):
            channels.append({'token': TELEGRAM_BOT_TOKEN, 'channel_id': TELEGRAM_CHANNEL_ID})

    try:
        # আপনার দেওয়া নির্দিষ্ট ফরম্যাটের মেসেজ
        caption = """🔥 𝙈𝙤𝙫𝙞𝙚𝙕𝙤𝙣𝙚BD 🔥
━━━━━━━━━━━━━━━━━

🎬 মুভিটি আপলোড করা হয়েছে!

📥 Download / Watch Now:
👉 https://moviezonebd.vercel.app/
(লিংক কপি করে Chrome Browser দিয়ে ওপেন করুন ✅)

🔞 18+ Exclusive Site:
👉 https://cinezonebdhd.blogspot.com/

━━━━━━━━━━━━━━━━━

💬 সাহায্য লাগলে বা কিছু জানার থাকলে
নির্দ্বিধায় যোগাযোগ করুন 👇
👨‍💻 Admin: @CineZoneBDBot"""

        sent_count = 0
        for config in channels:
            bot_token, channel_id = config.get('token'), config.get('channel_id')
            if not bot_token or not channel_id: continue

            api_url = f"https://api.telegram.org/bot{bot_token}/sendPhoto"
            # এখানে payload থেকে inline keyboard (reply_markup) এবং parse_mode বাদ দেওয়া হয়েছে
            payload = {
                'chat_id': channel_id,
                'photo': movie_data.get('poster', PLACEHOLDER_POSTER),
                'caption': caption
            }

            try:
                response = requests.post(api_url, data=payload, timeout=15)
                response.raise_for_status()
                if response.json().get('ok'):
                    print(f"SUCCESS: Telegram notification sent to channel '{channel_id}'.")
                    sent_count += 1
                else:
                    print(f"WARNING: Telegram API error for channel '{channel_id}': {response.json().get('description')}")
            except requests.exceptions.RequestException as e:
                print(f"ERROR: Failed to send notification to channel '{channel_id}': {e}")

        if sent_count == 0:
            print("WARNING: Notification attempt failed for all configured channels.")
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

# --- Context Processor ---
@app.context_processor
def inject_globals():
    ad_settings = settings.find_one({"_id": "ad_config"})
    design_settings = settings.find_one({"_id": "design_config"}) or {}
    site_config = settings.find_one({"_id": "site_config"}) or {}
    
    # নতুন: order অনুযায়ী ক্যাটাগরি সাজানো হচ্ছে
    all_categories = [cat['name'] for cat in categories_collection.find().sort("order", 1)]
    all_ott_platforms = list(ott_collection.find().sort("name", 1))
    
    category_icons = { "Bangla": "fa-film", "Hindi": "fa-film", "English": "fa-film", "18+ Adult": "fa-exclamation-circle", "Korean": "fa-tv", "Dual Audio": "fa-headphones", "Bangla Dubbed": "fa-microphone-alt", "Hindi Dubbed": "fa-microphone-alt", "Horror": "fa-ghost", "Action": "fa-bolt", "Thriller": "fa-knife-kitchen", "Anime": "fa-dragon", "Romance": "fa-heart", "Trending": "fa-fire", "ALL MOVIES": "fa-layer-group", "WEB SERIES & TV SHOWS": "fa-tv-alt", "HOME": "fa-home" }
    
    return dict(
        website_name=WEBSITE_NAME,
        logo_url=site_config.get('logo_url'),
        ad_settings=ad_settings or {},
        design_settings=design_settings,
        predefined_categories=all_categories,
        quote=quote,
        datetime=datetime,
        category_icons=category_icons,
        all_ott_platforms=all_ott_platforms,
        developer_telegram_id=DEVELOPER_TELEGRAM_ID,
        headlines=site_config.get('headlines', []),
        community_links=COMMUNITY_LINKS
    )

# =========================================================================================
# === [START] HTML TEMPLATES =============================================================
# =========================================================================================
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
<meta name="robots" content="noindex, nofollow">
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
    --search-accent-color: #00bfff;
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
  
  .main-header { position: fixed; top: 0; left: 0; width: 100%; height: var(--nav-height); display: flex; align-items: center; z-index: 1000; transition: background-color: 0.3s ease; background-color: rgba(0,0,0,0.7); backdrop-filter: blur(5px); }
  .header-content { display: flex; justify-content: flex-end; align-items: center; width: 100%; position: relative; }
  .logo {
    position: absolute;
    left: 50%;
    top: 50%;
    transform: translate(-50%, -50%);
    font-size: 1.8rem;
    font-weight: 700;
    color: var(--primary-color);
  }
  .logo img {
      max-height: 45px;
      width: auto;
      display: block;
  }
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
  
  .platform-section { margin: 40px 0; overflow: hidden; }
  .platform-slider .swiper-slide { width: 100px; }
  .platform-item { display: flex; flex-direction: column; align-items: center; justify-content: center; text-decoration: none; color: var(--text-dark); transition: transform 0.2s ease, color 0.2s ease; }
  .platform-item:hover { transform: scale(1.08); color: var(--text-light); }
  .platform-logo-wrapper { width: 80px; height: 80px; border-radius: 50%; background-color: #fff; display: flex; align-items: center; justify-content: center; margin-bottom: 10px; box-shadow: 0 4px 15px rgba(0,0,0,0.3); border: 2px solid #444; }
  .platform-logo-wrapper img { max-width: 70%; max-height: 70%; object-fit: contain; }
  .platform-item span { font-weight: 500; font-size: 0.8rem; text-align: center; }

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
    position: absolute; color: white; font-weight: 600; z-index: 2; text-transform: uppercase;
  }
  
  .language-tag { 
      {{ design_settings.language_tag_css | safe }}
  }
  
  .type-tag { bottom: 8px; right: 8px; background-color: var(--type-color); padding: 2px 8px; border-radius: 4px; font-size: 0.65rem; }
  .new-badge {
    position: absolute; top: 0; left: 0;
    {{ design_settings.new_badge_css | safe }}
  }

  .full-page-grid-container { padding: 80px 10px 20px; }
  .full-page-grid-title { font-size: 1.8rem; font-weight: 700; margin-bottom: 20px; text-align: center; }
  .main-footer { background-color: #111; padding: 30px 20px; text-align: center; color: var(--text-dark); margin-top: 30px; font-size: 0.9rem; }
  .footer-links { display: flex; justify-content: center; gap: 20px; margin-bottom: 20px; flex-wrap: wrap; }
  .footer-links a { color: var(--text-dark); font-weight: 500; transition: color 0.2s; }
  .footer-links a:hover { color: var(--text-light); }
  .footer-disclaimer { max-width: 800px; margin: 15px auto 0; font-size: 0.8rem; line-height: 1.6; color: #666; }

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

  /* Headline Ticker Styles */
  .headline-ticker-section { margin: 10px 0 20px 0; }
  .headline-ticker {
    display: flex;
    align-items: center;
    background-color: var(--card-bg);
    border-radius: 8px;
    border: 1px solid #333;
    overflow: hidden;
    padding: 5px;
    box-shadow: 0 4px 15px rgba(0,0,0,0.2);
  }
  .ticker-icon {
    background-color: var(--primary-color);
    color: white;
    padding: 10px 15px;
    border-radius: 5px;
    font-size: 1.1rem;
    margin-right: 10px;
  }
  .ticker-content-wrapper {
    flex-grow: 1;
    overflow: hidden;
    position: relative;
    white-space: nowrap;
  }
  .ticker-content {
    display: inline-block;
    animation: ticker-scroll linear infinite;
  }
  .headline-ticker:hover .ticker-content {
    animation-play-state: paused;
  }
  .headline-item {
    display: inline-block;
    margin-right: 40px;
    color: var(--text-dark);
    font-weight: 500;
  }
  .separator {
    color: var(--primary-color);
    margin: 0 10px;
    font-size: 1.2em;
    vertical-align: middle;
  }
  @keyframes ticker-scroll {
    0% { transform: translateX(0); }
    100% { transform: translateX(-100%); }
  }

  /* Community Section Styles */
  .community-section { margin: 40px auto; padding: 20px 0; max-width: 800px; }
  .community-title {
      font-size: 1.8rem;
      font-weight: 700;
      text-align: center;
      margin-bottom: 10px;
  }
  .community-title-underline {
      width: 60px;
      height: 4px;
      background-color: var(--primary-color);
      margin: 0 auto 30px auto;
      border-radius: 2px;
  }
  .community-links-container {
      display: flex;
      flex-direction: column;
      gap: 15px;
  }
  .community-link {
      display: flex;
      align-items: center;
      background-color: var(--card-bg);
      border-radius: 12px;
      padding: 15px 20px;
      text-decoration: none;
      border: 1px solid #282828;
      transition: all 0.2s ease-in-out;
  }
  .community-link:hover {
      transform: translateY(-3px);
      background-color: #2a2a2a;
      border-color: var(--primary-color);
  }
  .community-icon {
      font-size: 1.8rem;
      margin-right: 20px;
      width: 40px;
      text-align: center;
  }
  .community-link .text-content h4 {
      margin: 0 0 4px 0;
      font-size: 1.1rem;
      color: var(--text-light);
      font-weight: 600;
  }
  .community-link .text-content p {
      margin: 0;
      font-size: 0.9rem;
      color: var(--text-dark);
  }

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
        <a href="{{ url_for('home') }}" class="logo">
            {% if logo_url %}
                <img src="{{ logo_url }}" alt="{{ website_name }} Logo">
            {% else %}
                {{ website_name }}
            {% endif %}
        </a>
        <button class="menu-toggle"><i class="fas fa-bars"></i></button>
    </div>
</header>
<div class="mobile-nav-menu">
    <button class="close-btn">&times;</button>
    <div class="mobile-links">
        <a href="{{ url_for('home') }}">Home</a>
        <a href="{{ url_for('all_series') }}">All Web Series</a>
        <a href="{{ url_for('all_movies') }}">All Movies</a>
        <hr>
        <a href="https://t.me/{{ developer_telegram_id }}" target="_blank">Contact Developer</a>
    </div>
</div>
<main>
  {% macro render_movie_card(m) %}
    <a href="{{ url_for('movie_detail', movie_id=m._id) }}" class="movie-card">
      <div class="poster-wrapper">
        {% if (datetime.utcnow() - m._id.generation_time.replace(tzinfo=None)).days < 7 %}
            <span class="new-badge">{{ design_settings.new_badge_text or "NEW" }}</span>
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
            {% set url_args = {'page': pagination.prev_num} %}
            {% if 'category' in request.endpoint %}{% set _ = url_args.update({'name': query}) %}{% endif %}
            {% if 'platform' in request.endpoint %}{% set _ = url_args.update({'platform_name': query.replace(' Originals', '')}) %}{% endif %}
            {% if pagination.has_prev %}<a href="{{ url_for(request.endpoint, **url_args) }}">&laquo; Prev</a>{% endif %}
            
            <span class="current">Page {{ pagination.page }} of {{ pagination.total_pages }}</span>
            
            {% set url_args = {'page': pagination.next_num} %}
            {% if 'category' in request.endpoint %}{% set _ = url_args.update({'name': query}) %}{% endif %}
            {% if 'platform' in request.endpoint %}{% set _ = url_args.update({'platform_name': query.replace(' Originals', '')}) %}{% endif %}
            {% if pagination.has_next %}<a href="{{ url_for(request.endpoint, **url_args) }}">Next &raquo;</a>{% endif %}
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

    <!-- Headline Ticker Section -->
    {% if headlines %}
    <section class="headline-ticker-section container">
        <div class="headline-ticker">
            <div class="ticker-icon"><i class="fas fa-bullhorn"></i></div>
            <div class="ticker-content-wrapper" id="ticker-wrapper">
                <div class="ticker-content" id="ticker-content">
                    {% for headline in headlines %}
                        <span class="headline-item">{{ headline }}</span>
                        {% if not loop.last %}<span class="separator">&starf;</span>{% endif %}
                    {% endfor %}
                </div>
            </div>
        </div>
    </section>
    {% endif %}

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

    {% if all_ott_platforms %}
    <section class="platform-section container">
        <div class="swiper platform-slider">
            <div class="swiper-wrapper">
                {% for platform in all_ott_platforms %}
                <div class="swiper-slide">
                    <a href="{{ url_for('movies_by_platform', platform_name=platform.name) }}" class="platform-item">
                        <div class="platform-logo-wrapper">
                            <img src="{{ platform.logo_url }}" alt="{{ platform.name }} Logo">
                        </div>
                        <span>{{ platform.name }}</span>
                    </a>
                </div>
                {% endfor %}
            </div>
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

    <!-- Community Section -->
    <div class="container">
      {% if community_links %}
      <section class="community-section">
          <h2 class="community-title">Join Our Community</h2>
          <div class="community-title-underline"></div>
          <div class="community-links-container">
              {% for link in community_links %}
              <a href="{{ link.url }}" class="community-link" target="_blank" rel="noopener noreferrer">
                  <div class="community-icon" style="color: {{ link.icon_color }};">
                      <i class="{{ link.icon_class }}"></i>
                  </div>
                  <div class="text-content">
                      <h4>{{ link.title }}</h4>
                      <p>{{ link.subtitle }}</p>
                  </div>
              </a>
              {% endfor %}
          </div>
      </section>
      {% endif %}
    </div>

  {% endif %}
</main>
<footer class="main-footer">
    <div class="footer-links">
        <a href="{{ url_for('about_us') }}">About Us</a>
        <a href="{{ url_for('contact_us') }}">Contact Us</a>
        <a href="{{ url_for('dmca') }}">DMCA</a>
        <a href="{{ url_for('privacy_policy') }}">Privacy Policy</a>
        <a href="{{ url_for('terms_of_service') }}">Terms of Service</a>
    </div>
    <p>&copy; {{ datetime.utcnow().year }} {{ website_name }}. All Rights Reserved.</p>
    <p class="footer-disclaimer">
        <strong>Disclaimer:</strong> This site does not store any files on its server. All contents are provided by non-affiliated third parties.
    </p>
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
    new Swiper('.platform-slider', {
        slidesPerView: 'auto',
        spaceBetween: 20,
    });
    // Dynamic Headline Ticker Speed
    document.addEventListener('DOMContentLoaded', () => {
        const tickerWrapper = document.getElementById('ticker-wrapper');
        const tickerContent = document.getElementById('ticker-content');
        if (tickerWrapper && tickerContent) {
            const contentWidth = tickerContent.scrollWidth;
            const wrapperWidth = tickerWrapper.offsetWidth;

            if (contentWidth > wrapperWidth) {
                const clone = tickerContent.cloneNode(true);
                tickerContent.parentElement.appendChild(clone);
                
                const duration = (contentWidth / 60);
                const allContent = document.querySelectorAll('.ticker-content');
                allContent.forEach(item => {
                    item.style.animationDuration = duration + 's';
                });
            } else {
                tickerContent.style.animation = 'none';
            }
        }
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
<meta name="robots" content="noindex, nofollow">
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin><link href="https://fonts.googleapis.com/css2?family=Poppins:wght@400;500;600;700&family=Oswald:wght@700&display=swap" rel="stylesheet">
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.2.0/css/all.min.css">
<link rel="stylesheet" href="https://unpkg.com/swiper/swiper-bundle.min.css"/>
{{ ad_settings.ad_header | safe }}
<style>
  :root {
      --bg-color: #0d0d0d;
      --card-bg: #1a1a1a;
      --text-light: #ffffff;
      --text-dark: #8c8c8c;
      --primary-color: #E50914;
      --cyan-accent: #00FFFF;
      --lime-accent: #adff2f;
      --g-1: #ff00de; --g-2: #00ffff;
  }
  html { box-sizing: border-box; } *, *:before, *:after { box-sizing: inherit; }
  body { font-family: 'Poppins', sans-serif; background-color: var(--bg-color); color: var(--text-light); overflow-x: hidden; margin:0; padding:0; }
  a { text-decoration: none; color: inherit; }
  .container { max-width: 1200px; margin: 0 auto; padding: 20px 15px; }

  .back-link { 
      display: inline-block; 
      margin-bottom: 20px; 
      padding: 8px 15px; 
      background-color: var(--card-bg); 
      color: var(--text-dark);
      border-radius: 50px; 
      text-decoration: none; 
      font-size: 0.9rem; 
      transition: all 0.2s ease; 
  }
  .back-link:hover { 
      color: var(--text-light);
      background-color: #333;
  }
  .back-link i { 
      margin-right: 8px; 
  }
  
  .hero-section {
      position: relative;
      width: 100%;
      max-width: 900px;
      margin: 20px auto 80px;
      aspect-ratio: 16 / 9;
      background-size: cover;
      background-position: center;
      border-radius: 12px;
      box-shadow: 0 0 25px rgba(0, 255, 255, 0.4);
      overflow: visible;
  }
  .hero-poster {
      position: absolute;
      left: 30px;
      bottom: -60px;
      height: 95%;
      aspect-ratio: 2 / 3;
      object-fit: cover;
      border-radius: 8px;
      box-shadow: 0 8px 25px rgba(0,0,0,0.6);
      border: 2px solid rgba(255, 255, 255, 0.1);
  }
  .badge-new, .badge-completed {
      position: absolute;
      padding: 6px 15px;
      font-weight: bold;
      font-size: 0.9rem;
      color: white;
      border-radius: 5px;
      text-transform: uppercase;
      backdrop-filter: blur(5px);
  }
  .badge-new {
      top: 20px;
      right: 20px;
      background-color: rgba(255, 30, 30, 0.8);
  }
  .badge-completed {
      bottom: 20px;
      right: 20px;
      background-color: rgba(0, 255, 0, 0.8);
      color: #000;
  }
  .content-title-section {
      text-align: center;
      padding: 10px 15px 30px;
      max-width: 900px;
      margin: 0 auto;
  }
  .main-title {
      font-family: 'Oswald', sans-serif;
      font-size: clamp(1.8rem, 5vw, 2.5rem);
      font-weight: 700;
      line-height: 1.4;
      color: var(--cyan-accent);
      text-transform: uppercase;
  }
  .title-meta-info {
      color: var(--lime-accent);
      display: block;
  }

  .tabs-nav { display: flex; justify-content: center; gap: 10px; margin: 20px 0 30px; }
  .tab-link { flex: 1; max-width: 200px; padding: 12px; background-color: var(--card-bg); border: none; color: var(--text-dark); font-weight: 600; font-size: 1rem; border-radius: 8px; cursor: pointer; transition: all 0.2s ease; }
  .tab-link.active { background-color: var(--primary-color); color: var(--text-light); }
  .tab-pane { display: none; }
  .tab-pane.active { display: block; animation: fadeIn 0.5s; }
  @keyframes fadeIn { from { opacity: 0; } to { opacity: 1; } }
  
  #info-pane p { font-size: 0.95rem; line-height: 1.8; color: var(--text-dark); text-align: justify; background-color: var(--card-bg); padding: 20px; border-radius: 8px; }
  .link-group, .episode-list { display: flex; flex-direction: column; gap: 10px; max-width: 800px; margin: 0 auto; }
  .link-group h3, .episode-list h3 { font-size: 1.2rem; font-weight: 500; margin-bottom: 10px; color: var(--text-dark); text-align: center; }
  .action-btn { display: flex; justify-content: space-between; align-items: center; width: 100%; padding: 15px 20px; border-radius: 8px; font-weight: 500; font-size: 1rem; color: white; background: linear-gradient(90deg, var(--g-1), var(--g-2), var(--g-1)); background-size: 200% 100%; transition: background-position 0.5s ease; }
  .action-btn:hover { background-position: 100% 0; }
  .category-section { margin: 50px 0; }
  .category-title { font-size: 1.5rem; font-weight: 600; margin-bottom: 20px; }
  .movie-carousel .swiper-slide { width: 140px; }
  .movie-card { display: block; position: relative; }
  .movie-card .movie-poster { width: 100%; aspect-ratio: 2 / 3; object-fit: cover; border-radius: 8px; }

  .download-disclaimer {
      max-width: 800px; margin: 20px auto; padding: 15px;
      background-color: rgba(255, 204, 0, 0.1); border: 1px solid rgba(255, 204, 0, 0.3);
      border-radius: 8px; text-align: center; font-size: 0.85rem; color: #ccc;
  }
  
  /* === নতুন স্ক্রিনশট স্টাইল শুরু === */
  @keyframes rgb-glow-border {
      0%   { border-color: #ff00de; box-shadow: 0 0 15px #ff00de; }
      25%  { border-color: #00ffff; box-shadow: 0 0 15px #00ffff; }
      50%  { border-color: #adff2f; box-shadow: 0 0 15px #adff2f; }
      75%  { border-color: #f83d61; box-shadow: 0 0 15px #f83d61; }
      100% { border-color: #ff00de; box-shadow: 0 0 15px #ff00de; }
  }

  .screenshot-grid {
      display: grid;
      grid-template-columns: 1fr; /* মোবাইল ডিভাইসের জন্য ডিফল্ট এক কলাম */
      gap: 25px;
  }

  .screenshot-item {
      border: 3px solid transparent;
      border-radius: 10px;
      overflow: hidden;
      animation: rgb-glow-border 4s linear infinite;
      background-color: #000; /* যদি ছবি লোড না হয়, একটি কালো ব্যাকগ্রাউন্ড দেখাবে */
      transition: transform 0.3s ease;
  }
  
  .screenshot-item:hover {
      transform: scale(1.03); /* হোভারে হালকা জুম ইফেক্ট */
  }

  .screenshot-image {
      width: 100%;
      height: auto;
      display: block;
      border-radius: 6px; /* ভেতরের ছবির জন্য সামান্য ছোট ব্যাসার্ধ */
  }
  /* === নতুন স্ক্রিনশট স্টাইল শেষ === */

  @media (min-width: 768px) {
      .movie-carousel .swiper-slide { width: 180px; }
      /* বড় স্ক্রিনের জন্য স্ক্রিনশট গ্রিড লেআউট */
      .screenshot-grid {
          grid-template-columns: repeat(2, 1fr);
      }
  }
</style>
</head>
<body>
{{ ad_settings.ad_body_top | safe }}
{% if movie %}
<main class="container">
    <a href="#" onclick="window.history.back(); return false;" class="back-link">
        <i class="fas fa-arrow-left"></i> Go Back
    </a>
    
    <div class="hero-section" style="background-image: url('{{ movie.backdrop or movie.poster or 'https://via.placeholder.com/1280x720.png?text=No+Backdrop' }}');">
        <img src="{{ movie.poster or 'https://via.placeholder.com/400x600.png?text=No+Image' }}" alt="{{ movie.title }}" class="hero-poster">
        
        {% if (datetime.utcnow() - movie._id.generation_time.replace(tzinfo=None)).days < 3 %}
            <span class="badge-new">NEW</span>
        {% endif %}
        
        {% if movie.is_completed %}
            <span class="badge-completed">COMPLETED</span>
        {% endif %}
    </div>

    <div class="content-title-section">
        <h1 class="main-title">
            {{ movie.title }}
            <strong class="title-meta-info">
                {% if movie.release_date %}({{ movie.release_date.split('-')[0] }}){% endif %}
                {% if movie.type == 'series' and movie.episodes %}
                    {% set season_num = movie.episodes|map(attribute='season')|unique|sort|first %}
                    S{{ '%02d'|format(season_num|int) if season_num else '01' }}
                {% endif %}
                {{ movie.language or '' }}
            </strong>
        </h1>
    </div>

    <nav class="tabs-nav">
        <button class="tab-link" data-tab="info-pane">Info</button>
        <button class="tab-link active" data-tab="downloads-pane">Links</button>
    </nav>

    <div class="tabs-content">
        <div class="tab-pane" id="info-pane">
            <p>{{ movie.overview or 'No description available.' }}</p>
        </div>
        <div class="tab-pane active" id="downloads-pane">
            {% if ad_settings.ad_detail_page %}<div class="ad-container">{{ ad_settings.ad_detail_page | safe }}</div>{% endif %}

            <div class="download-disclaimer">
                <strong>Disclaimer:</strong> This site does not store any files on its server. All contents are provided by non-affiliated third parties. Clicking on the links will redirect you to third-party sites.
            </div>
            
            {% if movie.type == 'movie' and (movie.links or movie.manual_links) %}
                <div class="link-group">
                    <a href="{{ url_for('first_wait_step', movie_id=movie._id) }}" class="action-btn" style="justify-content: center; font-size: 1.2rem; padding: 18px;">
                        <span><i class="fas fa-bolt"></i> Get Links</span>
                    </a>
                </div>
            {% endif %}
            
            {% if movie.type == 'series' %}
                {% set all_seasons = ((movie.episodes | map(attribute='season') | list) + (movie.season_packs | map(attribute='season_number') | list)) | unique | sort %}
                {% for season_num in all_seasons %}
                    <div class="episode-list" style="margin-bottom: 20px;">
                        <h3>Season {{ season_num }}</h3>
                        <a href="{{ url_for('first_wait_step', movie_id=movie._id, season=season_num) }}" class="action-btn" style="justify-content: center; font-size: 1.1rem; padding: 16px;">
                            <span><i class="fas fa-list-ul"></i> Get Season {{ season_num }} Links</span>
                        </a>
                    </div>
                {% endfor %}
            {% endif %}

            {% if not movie.links and not movie.manual_links and not movie.episodes and not movie.season_packs %}
                <p style="text-align:center; color: var(--text-dark);">No links available yet.</p>
            {% endif %}
        </div>
    </div>
    
    {% if movie.screenshots %}
    <section class="category-section">
        <h2 class="category-title">Screenshots</h2>
        <!-- নতুন স্ক্রিনশট গ্রিড -->
        <div class="screenshot-grid">
            {% for ss in movie.screenshots %}
            <div class="screenshot-item">
                <img src="{{ ss }}" loading="lazy" alt="Screenshot of {{ movie.title }}" class="screenshot-image">
            </div>
            {% endfor %}
        </div>
    </section>
    {% endif %}

    {% if related_content %}
    <section class="category-section">
        <h2 class="category-title">You Might Also Like</h2>
        <div class="swiper movie-carousel">
            <div class="swiper-wrapper">
                {% for m in related_content %}
                <div class="swiper-slide">
                    <a href="{{ url_for('movie_detail', movie_id=m._id) }}" class="movie-card">
                        <img class="movie-poster" loading="lazy" src="{{ m.poster or 'https://via.placeholder.com/400x600.png?text=No+Image' }}" alt="{{ m.title }}">
                    </a>
                </div>
                {% endfor %}
            </div>
        </div>
    </section>
    {% endif %}
</main>
{% else %}<div style="display:flex; justify-content:center; align-items:center; height:100vh;"><h2>Content not found.</h2></div>{% endif %}
<script src="https://unpkg.com/swiper/swiper-bundle.min.js"></script>
<script>
    document.addEventListener('DOMContentLoaded', function () {
        const tabLinks = document.querySelectorAll('.tab-link');
        const tabPanes = document.querySelectorAll('.tab-pane');
        tabLinks.forEach(link => {
            link.addEventListener('click', () => {
                const tabId = link.getAttribute('data-tab');
                tabLinks.forEach(item => item.classList.remove('active'));
                tabPanes.forEach(pane => pane.classList.remove('active'));
                link.classList.add('active');
                document.getElementById(tabId).classList.add('active');
            });
        });
        new Swiper('.movie-carousel', { slidesPerView: 3, spaceBetween: 15, breakpoints: { 640: { slidesPerView: 4 }, 768: { slidesPerView: 5 }, 1024: { slidesPerView: 6 } } });
        // মুছে ফেলা হয়েছে: Swiper gallery-thumbs এর কোডটি এখান থেকে সরানো হয়েছে কারণ আমরা আর স্লাইডার ব্যবহার করছি না।
    });
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
    <title>Please Wait... - {{ website_name }}</title>
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
        .get-link-btn { display: none; text-decoration: none; color: white; font-weight: 600; cursor: pointer; border: none; padding: 12px 30px; border-radius: 50px; font-size: 1rem; background-color: var(--primary-color); transition: background-color 0.2s; }
        .ad-container { margin: 30px auto 0; width: 100%; max-width: 100%; display: flex; justify-content: center; align-items: center; overflow: hidden; min-height: 50px; text-align: center; }
        .ad-container > * { max-width: 100% !important; }
    </style>
</head>
<body>
    {{ ad_settings.ad_body_top | safe }}
    <div class="wait-container">
        <h1>Step 1: Preparing Link</h1>
        <p>Your link will be ready in a moment. Please wait.</p>
        <div id="timer-container" class="timer">Please wait <span id="countdown">10</span> seconds...</div>
        <a id="get-link-btn" class="get-link-btn" href="{{ target_url | safe }}">Go to Links Page</a>
        {% if ad_settings.ad_wait_page %}<div class="ad-container">{{ ad_settings.ad_wait_page | safe }}</div>{% endif %}
    </div>
    <script>
        (function() {
            let timeLeft = 10;
            const countdownElement = document.getElementById('countdown');
            const timerContainer = document.getElementById('timer-container');
            const linkButton = document.getElementById('get-link-btn');
            
            const timer = setInterval(() => {
                if (timeLeft <= 0) {
                    clearInterval(timer);
                    timerContainer.style.display = 'none';
                    linkButton.style.display = 'inline-block';
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
        .back-link {
            align-self: flex-start;
            margin-bottom: 20px;
            color: var(--text-dark);
            text-decoration: none;
            font-size: 0.9rem;
            padding: 8px 15px;
            background-color: var(--card-bg);
            border-radius: 50px;
            transition: all 0.2s ease;
        }
        .back-link:hover {
            background-color: #333;
            color: var(--text-light);
        }
        .back-link i {
            margin-right: 8px;
        }
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
        <a href="#" onclick="window.history.back(); return false;" class="back-link">
            <i class="fas fa-arrow-left"></i> Go Back
        </a>
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
    <script src="https://cdnjs.cloudflare.com/ajax/libs/Sortable/1.15.0/Sortable.min.js"></script> <!-- নতুন: SortableJS লাইব্রেরি -->
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
        .result-item img { width: 100%; aspect-ratio: 2 / 3; object-fit: cover; border-radius: 5px; margin-bottom: 10px; border: 2px solid transparent; transition: all 0.2s; }
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
        .management-section { display: flex; flex-wrap: wrap; gap: 30px; align-items: flex-start; }
        .management-list { flex: 1; min-width: 250px; }
        .management-item { display: flex; justify-content: space-between; align-items: center; background: var(--dark-gray); padding: 10px 15px; border-radius: 4px; margin-bottom: 10px; }
        .status-badge { padding: 4px 8px; border-radius: 4px; color: white; font-size: 0.8rem; font-weight: bold; }
        .status-pending { background-color: #ffc107; color: black; }
        .status-fulfilled { background-color: #28a745; }
        .status-rejected { background-color: #6c757d; }
        .pagination { display: flex; justify-content: center; align-items: center; gap: 10px; margin-top: 20px; }
        .pagination a, .pagination span { padding: 8px 15px; border-radius: 5px; background-color: var(--light-gray); color: var(--text-light); text-decoration: none; }
        .pagination .current { background-color: var(--netflix-red); font-weight: bold; }
        /* নতুন: ক্যাটাগরি সাজানোর জন্য স্টাইল */
        #sortable-categories .management-item { cursor: grab; }
        #sortable-categories .management-item:active { cursor: grabbing; }
        .sortable-ghost { opacity: 0.4; background: #444; }
    </style>
</head>
<body>
<div class="admin-container">
    <header class="admin-header"><h1>Admin Panel</h1><a href="{{ url_for('home') }}" target="_blank">View Site</a></header>
    
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
            <div class="form-group"><label>OTT Platform:</label>
                <select name="ott_platform">
                    <option value="None">None</option>
                    {% for platform in ott_list %}
                    <option value="{{ platform.name }}">{{ platform.name }}</option>
                    {% endfor %}
                </select>
            </div>
            <div class="form-group"><div class="checkbox-group"><label><input type="checkbox" name="is_completed"> Mark as Completed?</label></div></div>
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
    
    <div class="management-content-section">
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
        <!-- নতুন: পেজিনেশন কন্ট্রোল -->
        {% if pagination and pagination.total_pages > 1 %}
        <div class="pagination">
            {% if pagination.has_prev %}<a href="{{ url_for('admin', page=pagination.prev_num) }}">&laquo; Prev</a>{% endif %}
            <span class="current">Page {{ pagination.page }} of {{ pagination.total_pages }}</span>
            {% if pagination.has_next %}<a href="{{ url_for('admin', page=pagination.next_num) }}">Next &raquo;</a>{% endif %}
        </div>
        {% endif %}
    </div>
    <hr>

    <h2><i class="fas fa-brush"></i> Design Settings (Poster Tags)</h2>
    <form method="post">
        <input type="hidden" name="form_action" value="update_design_settings">
        <fieldset><legend>Language Tag Customization (CSS)</legend>
            <div class="form-group">
                <label>Language Tag CSS Properties:</label>
                <textarea name="language_tag_css" rows="3" placeholder="e.g., padding: 4px 10px; font-size: 0.8rem; top: 10px; right: 10px; background-color: #00ffaa;">{{ design_settings.language_tag_css or '' }}</textarea>
                <small>Style must include position (top, right) and size/color (font-size, padding, background-color). Do NOT include 'position: absolute' or 'color: white'.</small>
            </div>
        </fieldset>
        <fieldset><legend>New/Recent Badge Customization</legend>
            <div class="form-group">
                <label>Badge Text (e.g., NEW, HOT, নতুন):</label>
                <input type="text" name="new_badge_text" value="{{ design_settings.new_badge_text or 'NEW' }}">
            </div>
            <div class="form-group">
                <label>New Badge CSS Properties (The red ribbon/badge):</label>
                <textarea name="new_badge_css" rows="3" placeholder="e.g., background-color: #E50914; color: white; padding: 4px 12px 4px 8px;">{{ design_settings.new_badge_css or '' }}</textarea>
                <small>Style must include background/color/padding. Do NOT include 'position: absolute'.</small>
            </div>
        </fieldset>
        <button type="submit" class="btn btn-primary"><i class="fas fa-save"></i> Save Design Settings</button>
    </form>
    <hr>

    <h2><i class="fas fa-cogs"></i> General Site Settings</h2>
    <form method="post">
        <input type="hidden" name="form_action" value="update_site_config">
        <fieldset><legend>Website Logo</legend>
            <div class="form-group">
                <label for="logo_url">Logo Image URL:</label>
                <input type="url" name="logo_url" id="logo_url" value="{{ site_config.logo_url or '' }}" placeholder="https://.../logo.png">
                <small>Provide a direct link to your logo image. If you leave this blank, the website name will be shown as text. Recommended logo height is around 40-50 pixels.</small>
            </div>
        </fieldset>
        <fieldset>
            <legend>Manage Scrolling Headlines</legend>
            <div class="form-group">
                <label for="headlines_text">Headlines (One per line):</label>
                <textarea name="headlines_text" id="headlines_text" rows="5" placeholder="Enter each headline on a new line.&#10;Example: New Bangla movie added!&#10;Server maintenance on Sunday.">{{ headlines_text or '' }}</textarea>
                <small>Each line you enter here will be shown as a separate scrolling headline on the homepage.</small>
            </div>
        </fieldset>
        <button type="submit" class="btn btn-primary"><i class="fas fa-save"></i> Save Site Settings</button>
    </form>
    <hr>

    <h2><i class="fab fa-telegram-plane"></i> Telegram Notification Channels</h2>
    <div class="management-section">
        <form method="post" style="flex: 2; min-width: 300px; padding: 15px;">
            <input type="hidden" name="form_action" value="update_telegram_settings">
            <fieldset><legend>General Settings</legend>
                <div class="form-group">
                    <label>"How to Download" Tutorial Video URL:</label>
                    <input type="url" name="tutorial_video_url" value="{{ telegram_settings.tutorial_video_url or '' }}" placeholder="https://t.me/your_channel/video_id">
                    <small>This link will be added as a button to every notification.</small>
                </div>
            </fieldset>
            <fieldset><legend>Add New Channel</legend>
                <div class="form-group"><label>Bot Token:</label><input type="text" name="bot_token"></div>
                <div class="form-group"><label>Channel ID (e.g., @mychannel or -100xxxxxxxxxx):</label><input type="text" name="channel_id"></div>
                <button type="submit" name="submit_action" value="add_channel" class="btn btn-primary"><i class="fas fa-plus"></i> Add Channel</button>
            </fieldset>
            <button type="submit" name="submit_action" value="save_settings" class="btn btn-success" style="margin-top: 15px;"><i class="fas fa-save"></i> Save Settings</button>
        </form>
        <div class="management-list" style="flex: 1; min-width: 300px;">
            <h3>Configured Channels</h3>
            {% for channel in telegram_channels %}
            <div class="management-item">
                <span>{{ channel.channel_id }} ({{ channel.token[:10] }}...)</span>
                <a href="{{ url_for('delete_telegram_channel', channel_id=channel.channel_id) }}" onclick="return confirm('Are you sure you want to delete this channel configuration?')" class="btn btn-danger" style="padding: 5px 10px; font-size: 0.8rem;">Delete</a>
            </div>
            {% else %}
            <p style="padding: 10px; color: #888;">No channels configured yet.</p>
            {% endfor %}
        </div>
    </div>
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
    
    <div class="management-section">
        <div style="flex: 1; min-width: 300px;">
            <h2><i class="fas fa-tags"></i> Category Management</h2>
            <form method="post" id="add-category-form">
                <input type="hidden" name="form_action" value="add_category">
                <fieldset><legend>Add New Category</legend>
                    <div class="form-group"><label>Category Name:</label><input type="text" name="category_name" required></div>
                    <button type="submit" class="btn btn-primary"><i class="fas fa-plus"></i> Add Category</button>
                </fieldset>
            </form>
            <div class="management-list">
                <h3>Existing Categories (Drag to Reorder)</h3>
                <div id="sortable-categories">
                    {% for cat in categories_list %}<div class="management-item" data-id="{{ cat._id }}"><span><i class="fas fa-grip-vertical" style="margin-right: 10px;"></i>{{ cat.name }}</span><a href="{{ url_for('delete_category', cat_id=cat._id) }}" onclick="return confirm('Are you sure?')" class="btn btn-danger" style="padding: 5px 10px; font-size: 0.8rem;">Delete</a></div>{% endfor %}
                </div>
                <form method="post" id="save-order-form" style="padding:0; margin-top: 15px; background: none;">
                    <input type="hidden" name="form_action" value="save_category_order">
                    <input type="hidden" name="category_order" id="category_order_input">
                    <button type="submit" class="btn btn-success"><i class="fas fa-save"></i> Save Category Order</button>
                </form>
            </div>
        </div>
        <div style="flex: 1; min-width: 300px;">
            <h2><i class="fas fa-tv"></i> OTT Platform Management</h2>
            <form method="post">
                <input type="hidden" name="form_action" value="add_platform">
                <fieldset><legend>Add New Platform</legend>
                    <div class="form-group"><label>Platform Name:</label><input type="text" name="platform_name" required></div>
                    <div class="form-group"><label>Logo URL:</label><input type="url" name="platform_logo_url" required></div>
                    <button type="submit" class="btn btn-primary"><i class="fas fa-plus"></i> Add Platform</button>
                </fieldset>
            </form>
            <div class="management-list">
                <h3>Existing Platforms</h3>
                {% for platform in ott_list %}<div class="management-item"><span>{{ platform.name }}</span><a href="{{ url_for('delete_platform', platform_id=platform._id) }}" onclick="return confirm('Are you sure?')" class="btn btn-danger" style="padding: 5px 10px; font-size: 0.8rem;">Delete</a></div>{% endfor %}
            </div>
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
    document.addEventListener('DOMContentLoaded', function() { 
        toggleFields(); 
        const selectAll = document.getElementById('select-all'); 
        if(selectAll) { selectAll.addEventListener('change', e => document.querySelectorAll('.row-checkbox').forEach(c => c.checked = e.target.checked)); }
        
        // নতুন: ক্যাটাগরি সাজানোর জন্য SortableJS চালু করা
        const sortableList = document.getElementById('sortable-categories');
        if (sortableList) {
            const sortable = new Sortable(sortableList, {
                animation: 150,
                ghostClass: 'sortable-ghost'
            });

            const saveOrderForm = document.getElementById('save-order-form');
            saveOrderForm.addEventListener('submit', function(e) {
                const order = sortable.toArray(); // get the data-id attributes in the new order
                document.getElementById('category_order_input').value = order.join(',');
            });
        }
    });
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
        <div class="form-group"><label>OTT Platform:</label>
            <select name="ott_platform">
                <option value="None">None</option>
                {% for platform in ott_list %}
                <option value="{{ platform.name }}" {% if movie.ott_platform == platform.name %}selected{% endif %}>{{ platform.name }}</option>
                {% endfor %}
            </select>
        </div>
        <div class="form-group"><div class="checkbox-group"><label><input type="checkbox" name="is_completed" {% if movie.is_completed %}checked{% endif %}> Mark as Completed?</label></div></div>
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
                <input type="checkbox" name="send_notification" id="send_notification_checkbox" checked>
                Send Update Notification to Telegram?
            </label>
        </div>
        <div class="form-group" id="notification_text_container" style="display: none;">
            <label for="custom_notification_text">Custom Notification Text (Optional):</label>
            <input type="text" name="custom_notification_text" id="custom_notification_text" placeholder="Auto-generated if left empty. e.g., S01 [EP 01-10 ADDED]">
        </div>
        <button type="submit" class="btn btn-primary"><i class="fas fa-save"></i> Update Content</button>
    </div>
  </form>
</div>
<script>
    function toggleFields() { 
        var isSeries = document.getElementById('content_type').value === 'series'; 
        document.getElementById('episode_fields').style.display = isSeries ? 'block' : 'none'; 
        document.getElementById('movie_fields').style.display = isSeries ? 'none' : 'block'; 
        const notificationContainer = document.getElementById('notification_text_container');
        const sendNotificationCheckbox = document.getElementById('send_notification_checkbox');
        if (isSeries && sendNotificationCheckbox.checked) {
            notificationContainer.style.display = 'block';
        } else {
            notificationContainer.style.display = 'none';
        }
    }
    function addEpisodeField() { const c = document.getElementById('episodes_container'); const d = document.createElement('div'); d.className = 'dynamic-item'; d.innerHTML = `<button type="button" onclick="this.parentElement.remove()" class="btn btn-danger">X</button><div class="form-group"><label>Season:</label><input type="number" name="episode_season[]" value="1" required></div><div class="form-group"><label>Episode:</label><input type="number" name="episode_number[]" required></div><div class="form-group"><label>Title:</label><input type="text" name="episode_title[]"></div><div class="form-group"><label>Download/Watch Link:</label><input type="url" name="episode_watch_link[]" required></div>`; c.appendChild(d); }
    function addSeasonPackField() { const container = document.getElementById('season_packs_container'); const newItem = document.createElement('div'); newItem.className = 'dynamic-item'; newItem.innerHTML = `<button type="button" onclick="this.parentElement.remove()" class="btn btn-danger">X</button><div class="season-pack-item"><div class="form-group"><label>Season No.</label><input type="number" name="season_pack_number[]" value="1" required></div><div class="form-group"><label>Watch Link</label><input type="url" name="season_pack_watch_link[]"></div><div class="form-group"><label>Download Link</label><input type="url" name="season_pack_download_link[]"></div></div>`; container.appendChild(newItem); }
    function addManualLinkField() { const container = document.getElementById('manual_links_container'); const newItem = document.createElement('div'); newItem.innerHTML = `<button type="button" onclick="this.parentElement.remove()" class="btn btn-danger">X</button><div class="link-pair"><div class="form-group"><label>Button Name</label><input type="text" name="manual_link_name[]" placeholder="e.g., 480p G-Drive" required></div><div class="form-group"><label>Link URL</label><input type="url" name="manual_link_url[]" placeholder="https://..." required></div></div>`; container.appendChild(newItem); }
    
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

    function formatSeriesInfoJS(episodes, seasonPacks) {
        let infoParts = [];
        if (seasonPacks && seasonPacks.length > 0) {
            const sortedPacks = seasonPacks.sort((a, b) => a.season_number - b.season_number);
            sortedPacks.forEach(pack => {
                const seasonNum = String(pack.season_number).padStart(2, '0');
                infoParts.push(`S${seasonNum} [COMPLETE SEASON]`);
            });
        }
        if (episodes && episodes.length > 0) {
            const episodesBySeason = {};
            episodes.forEach(ep => {
                if (!episodesBySeason[ep.season]) episodesBySeason[ep.season] = [];
                episodesBySeason[ep.season].push(ep.episode_number);
            });
            Object.keys(episodesBySeason).sort((a, b) => a - b).forEach(season => {
                const epNums = episodesBySeason[season].sort((a, b) => a - b);
                if (epNums.length === 0) return;
                const seasonNum = String(season).padStart(2, '0');
                const firstEp = String(epNums[0]).padStart(2, '0');
                const lastEp = String(epNums[epNums.length - 1]).padStart(2, '0');
                const epRange = (firstEp === lastEp) ? `EP${firstEp}` : `EP${firstEp}-${lastEp}`;
                infoParts.push(`S${seasonNum} [${epRange} ADDED]`);
            });
        }
        return infoParts.join(' & ');
    }

    function autoGenerateNotificationText() {
        if (document.getElementById('content_type').value !== 'series') {
            document.getElementById('custom_notification_text').value = '';
            return;
        }
        const oldEpisodes = JSON.parse('{{ movie.episodes|tojson|safe }}' || '[]');
        const oldSeasonPacks = JSON.parse('{{ movie.season_packs|tojson|safe }}' || '[]');
        const oldEpIds = new Set(oldEpisodes.map(ep => `${ep.season}-${ep.episode_number}`));
        const oldPackIds = new Set(oldSeasonPacks.map(p => p.season_number));
        const currentEps = [];
        document.querySelectorAll('#episodes_container .dynamic-item').forEach(item => {
            const season = item.querySelector('[name="episode_season[]"]').value;
            const episode = item.querySelector('[name="episode_number[]"]').value;
            if (season && episode) currentEps.push({ season: parseInt(season), episode_number: parseInt(episode) });
        });
        const currentPacks = [];
        document.querySelectorAll('#season_packs_container .dynamic-item').forEach(item => {
            const season = item.querySelector('[name="season_pack_number[]"]').value;
            if (season) currentPacks.push({ season_number: parseInt(season) });
        });
        const newlyAddedEps = currentEps.filter(ep => !oldEpIds.has(`${ep.season}-${ep.episode_number}`));
        const newlyAddedPacks = currentPacks.filter(p => !oldPackIds.has(p.season_number));
        const generatedText = formatSeriesInfoJS(newlyAddedEps, newlyAddedPacks);
        document.getElementById('custom_notification_text').value = generatedText;
    }

    function setupMutationObserver() {
        const episodesContainer = document.getElementById('episodes_container');
        const packsContainer = document.getElementById('season_packs_container');
        const observerCallback = (mutationsList, observer) => {
            for(const mutation of mutationsList) { if (mutation.type === 'childList') autoGenerateNotificationText(); }
        };
        const observer = new MutationObserver(observerCallback);
        const config = { childList: true };
        if (episodesContainer) observer.observe(episodesContainer, config);
        if (packsContainer) observer.observe(packsContainer, config);
        document.body.addEventListener('input', (event) => {
            if (event.target.matches('[name="episode_season[]"], [name="episode_number[]"], [name="season_pack_number[]"]')) {
                autoGenerateNotificationText();
            }
        });
    }

    document.addEventListener('DOMContentLoaded', function() {
        toggleFields();
        setupMutationObserver();
        const checkbox = document.getElementById('send_notification_checkbox');
        checkbox.addEventListener('change', toggleFields);
    });
</script>
</body></html>
"""
legal_page_template_html = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{{ title }} - {{ website_name }}</title>
    <link rel="icon" href="https://img.icons8.com/fluency/48/cinema-.png" type="image/png">
    <meta name="robots" content="noindex, nofollow">
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Poppins:wght@400;500;700&display=swap" rel="stylesheet">
    <style>
        :root { --primary-color: #E50914; --bg-color: #141414; --card-bg: #1a1a1a; --text-light: #ffffff; --text-dark: #a0a0a0; }
        body { font-family: 'Poppins', sans-serif; background-color: var(--bg-color); color: var(--text-light); line-height: 1.8; margin: 0; padding: 0; }
        a { color: var(--primary-color); text-decoration: none; }
        a:hover { text-decoration: underline; }
        .container { max-width: 900px; margin: 0 auto; padding: 40px 20px; }
        .page-header { text-align: center; border-bottom: 2px solid var(--primary-color); padding-bottom: 20px; margin-bottom: 30px; }
        .page-header h1 { font-size: 2.5rem; margin: 0; }
        .page-content { background-color: var(--card-bg); padding: 30px; border-radius: 8px; }
        .page-content h2 { color: var(--primary-color); font-size: 1.8rem; }
        .page-content p { color: var(--text-dark); }
        .page-content ul { list-style-position: inside; padding-left: 0; }
        .main-footer { background-color: #111; padding: 30px 20px; text-align: center; color: var(--text-dark); margin-top: 30px; font-size: 0.9rem; }
        .footer-links { display: flex; justify-content: center; gap: 20px; margin-bottom: 20px; flex-wrap: wrap; }
        .footer-links a { color: var(--text-dark); font-weight: 500; transition: color 0.2s; }
        .footer-links a:hover { color: var(--text-light); }
        .footer-disclaimer { max-width: 800px; margin: 15px auto 0; font-size: 0.8rem; line-height: 1.6; color: #666; }
    </style>
</head>
<body>
    <div class="container">
        <div class="page-header">
            <a href="{{ url_for('home') }}" style="text-decoration:none;"><h1>{{ website_name }}</h1></a>
        </div>
        <div class="page-content">
            <h2>{{ title }}</h2>
            {{ content|safe }}
        </div>
    </div>
    <footer class="main-footer">
        <div class="footer-links">
            <a href="{{ url_for('about_us') }}">About Us</a>
            <a href="{{ url_for('contact_us') }}">Contact Us</a>
            <a href="{{ url_for('dmca') }}">DMCA</a>
            <a href="{{ url_for('privacy_policy') }}">Privacy Policy</a>
            <a href="{{ url_for('terms_of_service') }}">Terms of Service</a>
        </div>
        <p>&copy; {{ datetime.utcnow().year }} {{ website_name }}. All Rights Reserved.</p>
        <p class="footer-disclaimer">
            <strong>Disclaimer:</strong> This site does not store any files on its server. All contents are provided by non-affiliated third parties.
        </p>
    </footer>
</body>
</html>
"""
generate_links_html = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>Generating Links for {{ movie.title }} - {{ website_name }}</title>
    <link rel="icon" href="https://img.icons8.com/fluency/48/cinema-.png" type="image/png">
    <meta name="robots" content="noindex, nofollow">
    <link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin><link href="https://fonts.googleapis.com/css2?family=Poppins:wght@400;500;700&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.2.0/css/all.min.css">
    {{ ad_settings.ad_header | safe }}
    <style>
        :root { --primary-color: #E50914; --bg-color: #141414; --card-bg: #1a1a1a; --text-light: #ffffff; --text-dark: #a0a0a0; --g-1: #ff00de; --g-2: #00ffff; }
        body { font-family: 'Poppins', sans-serif; background-color: var(--bg-color); color: var(--text-light); display: flex; flex-direction: column; justify-content: center; align-items: center; min-height: 100vh; padding: 20px; box-sizing: border-box; }
        .main-container { background-color: var(--card-bg); padding: 25px; border-radius: 12px; max-width: 600px; width: 100%; box-shadow: 0 10px 30px rgba(0,0,0,0.5); text-align: center; }
        .movie-info { display: flex; align-items: center; gap: 20px; text-align: left; margin-bottom: 25px; }
        .movie-info img { width: 100px; border-radius: 8px; }
        .movie-info h1 { font-size: 1.5rem; margin: 0; }
        .movie-info p { color: var(--text-dark); margin: 5px 0 0; font-size: 0.9rem; }
        
        #countdown-container p { font-size: 1.1rem; color: var(--text-dark); }
        .timer { font-size: 2.5rem; font-weight: 700; color: var(--primary-color); margin: 15px 0; }
        .loader { width: 50px; height: 50px; border: 5px solid #333; border-top-color: var(--primary-color); border-radius: 50%; animation: spin 1s linear infinite; margin: 20px auto; }
        @keyframes spin { to { transform: rotate(360deg); } }

        #links-container { display: none; flex-direction: column; gap: 12px; margin-top: 20px; }
        .link-button { display: flex; justify-content: space-between; align-items: center; text-decoration: none; color: white; font-weight: 600; padding: 15px 20px; border-radius: 8px; font-size: 1rem; background: linear-gradient(90deg, var(--g-1), var(--g-2), var(--g-1)); background-size: 200% 100%; transition: all 0.4s ease; }
        .link-button:hover { background-position: 100% 0; transform: scale(1.03); }
        .link-button .quality { font-size: 1.1rem; text-align: left; }
        .link-button .icon i { font-size: 1.2rem; }

        .ad-container { margin: 25px auto 0; width: 100%; max-width: 100%; display: flex; justify-content: center; align-items: center; overflow: hidden; min-height: 50px; }
        .ad-container > * { max-width: 100% !important; }
    </style>
</head>
<body>
    {{ ad_settings.ad_body_top | safe }}
    <div class="main-container">
        <div class="movie-info">
            <img src="{{ movie.poster or 'https://via.placeholder.com/400x600.png?text=No+Image' }}" alt="{{ movie.title }}">
            <div>
                <h1>{{ movie.title }}</h1>
                <p>Links are being prepared...</p>
            </div>
        </div>

        <div id="countdown-container">
            <p>Please wait for the links to be generated.</p>
            <div class="timer"><span id="countdown">5</span> seconds</div>
            <div class="loader"></div>
        </div>

        <div id="links-container">
            {% if movie.type == 'movie' %}
                {% for link in movie.links %}
                  {% if link.download_url %}
                  <a href="{{ link.download_url }}" target="_blank" class="link-button">
                      <span class="quality">Download {{ link.quality }}</span>
                      <span class="icon"><i class="fas fa-download"></i></span>
                  </a>
                  {% endif %}
                  {% if link.watch_url %}
                  <a href="{{ link.watch_url }}" target="_blank" class="link-button">
                      <span class="quality">Watch {{ link.quality }}</span>
                      <span class="icon"><i class="fas fa-play-circle"></i></span>
                  </a>
                  {% endif %}
                {% endfor %}
                {% if movie.manual_links %}
                    {% for m_link in movie.manual_links %}
                    <a href="{{ m_link.url }}" target="_blank" class="link-button">
                        <span class="quality">{{ m_link.name }}</span>
                        <span class="icon"><i class="fas fa-link"></i></span>
                    </a>
                    {% endfor %}
                {% endif %}
            {% elif movie.type == 'series' and season_num is defined %}
                {% set season_pack = (movie.season_packs | selectattr('season_number', 'equalto', season_num) | first) if movie.season_packs else none %}
                {% if season_pack and (season_pack.download_link or season_pack.watch_link) %}
                <a href="{{ season_pack.download_link or season_pack.watch_link }}" target="_blank" class="link-button">
                    <span class="quality">Season {{ season_num }} Complete</span>
                    <span class="icon"><i class="fas fa-file-archive"></i></span>
                </a>
                {% endif %}
                
                {% for ep in episodes_for_season | sort(attribute='episode_number') %}
                    {% if ep.watch_link %}
                    <a href="{{ ep.watch_link }}" target="_blank" class="link-button">
                        <span class="quality">Episode {{ ep.episode_number }}: {{ ep.title or 'Watch/Download' }}</span>
                        <span class="icon"><i class="fas fa-play"></i></span>
                    </a>
                    {% endif %}
                {% endfor %}
            {% endif %}
        </div>
        
        {% if ad_settings.ad_wait_page %}<div class="ad-container">{{ ad_settings.ad_wait_page | safe }}</div>{% endif %}
    </div>

    <script>
        (function() {
            let timeLeft = 5;
            const countdownElement = document.getElementById('countdown');
            const countdownContainer = document.getElementById('countdown-container');
            const linksContainer = document.getElementById('links-container');

            const timer = setInterval(() => {
                if (timeLeft <= 0) {
                    clearInterval(timer);
                    countdownContainer.style.display = 'none';
                    linksContainer.style.display = 'flex';
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

# =========================================================================================
# === [START] PYTHON FUNCTIONS & FLASK ROUTES ============================================
# =========================================================================================

# --- TMDB API Helper Function ---
def get_tmdb_details(tmdb_id, media_type):
    if not TMDB_API_KEY: return None
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
        self.page = page; self.per_page = per_page; self.total_count = total_count
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
@app.route('/robots.txt')
def robots_txt():
    disallow_all = "User-agent: *\nDisallow: /"
    return Response(disallow_all, mimetype='text/plain')

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
    # নতুন: order অনুযায়ী ক্যাটাগরি সাজানো হচ্ছে
    home_categories = [cat['name'] for cat in categories_collection.find().sort("order", 1)]
    categorized_content = {cat: list(movies.find({"categories": cat}).sort('updated_at', -1).limit(10)) for cat in home_categories}
    categorized_content = {k: v for k, v in categorized_content.items() if v}
    context = {"slider_content": slider_content, "latest_content": latest_content, "categorized_content": categorized_content, "is_full_page_list": False}
    return render_template_string(index_html, **context)

@app.route('/movie/<movie_id>')
def movie_detail(movie_id):
    try:
        movie = movies.find_one_and_update({"_id": ObjectId(movie_id)}, {"$inc": {"view_count": 1}}, return_document=True)
        if not movie: return "Content not found", 404
        related_content = list(movies.find({"type": movie.get('type'), "_id": {"$ne": movie['_id']}}).sort('updated_at', -1).limit(10))
        return render_template_string(detail_html, movie=movie, related_content=related_content)
    except:
        return "Content not found", 404

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
    query_filter = {"categories": title}
    content_list, pagination = get_paginated_content(query_filter, page)
    return render_template_string(index_html, movies=content_list, query=title, is_full_page_list=True, pagination=pagination)

@app.route('/platform/<platform_name>')
def movies_by_platform(platform_name):
    page = request.args.get('page', 1, type=int)
    content_list, pagination = get_paginated_content({"ott_platform": platform_name}, page)
    return render_template_string(index_html, movies=content_list, query=f"{platform_name} Originals", is_full_page_list=True, pagination=pagination)

@app.route('/request', methods=['GET', 'POST'])
def request_content():
    if request.method == 'POST':
        content_name = request.form.get('content_name', '').strip()
        if content_name:
            requests_collection.insert_one({"name": content_name, "info": request.form.get('extra_info', '').strip(), "status": "Pending", "created_at": datetime.utcnow()})
            flash('Your request has been submitted successfully!', 'success')
        else:
            flash('Content name is required.', 'error')
        return redirect(url_for('request_content'))
    return render_template_string(request_html)

# --- Two-Step Link Generation Routes ---

@app.route('/wait-step-1/<movie_id>')
def first_wait_step(movie_id):
    season_num = request.args.get('season')
    if season_num:
        target_url = url_for('generate_links_page', movie_id=movie_id, season=season_num)
    else:
        target_url = url_for('generate_links_page', movie_id=movie_id)
    return render_template_string(wait_page_html, target_url=target_url)

@app.route('/generate-links/<movie_id>')
def generate_links_page(movie_id):
    try:
        movie = movies.find_one({"_id": ObjectId(movie_id)})
        if not movie: return "Content not found.", 404

        season_num_str = request.args.get('season')
        episodes_for_season, season_num = [], None

        has_movie_links = movie.get('links') or movie.get('manual_links')
        
        if movie.get('type') == 'series':
            if not season_num_str: return "Season number is required for series.", 400
            season_num = int(season_num_str)
            if 'episodes' in movie:
                episodes_for_season = [ep for ep in movie['episodes'] if ep.get('season') == season_num]
            has_season_pack = any(p.get('season_number') == season_num for p in movie.get('season_packs', []))
            if not episodes_for_season and not has_season_pack:
                return f"No links found for Season {season_num}.", 404
        elif movie.get('type') == 'movie' and not has_movie_links:
            return "No links found for this content.", 404

        return render_template_string(
            generate_links_html, 
            movie=movie, 
            season_num=season_num, 
            episodes_for_season=episodes_for_season
        )
    except Exception as e:
        print(f"Error in generate_links_page: {e}")
        return "Content not found or invalid ID.", 404

# --- Legal Pages Routes ---
@app.route('/about-us')
def about_us():
    title = "About Us"
    content = f"""
    <p>Welcome to {WEBSITE_NAME}, your number one source for discovering new entertainment. We're dedicated to giving you the very best index of movies and web series, with a focus on dependability, user experience, and uniqueness.</p>
    <p>Founded in 2024, {WEBSITE_NAME} has come a long way from its beginnings. We are a community-driven platform that aims to provide an organized and accessible catalog of entertainment content available on the internet.</p>
    <p>Please note that {WEBSITE_NAME} does not host any content on its own servers. We are an index that provides links to content hosted by third-party services. We are not responsible for the content hosted on these third-party sites.</p>
    <p>We hope you enjoy our service as much as we enjoy offering it to you. If you have any questions or comments, please don't hesitate to contact us.</p>
    """
    return render_template_string(legal_page_template_html, title=title, content=content)

@app.route('/contact-us')
def contact_us():
    title = "Contact Us"
    content = f"""
    <p>If you have any questions, suggestions, or need to report an issue, please feel free to reach out to us. We value your feedback and are here to help.</p>
    <p>The best way to contact our support team or the developer is through Telegram.</p>
    <p><strong>Contact via Telegram:</strong> <a href="https://t.me/{DEVELOPER_TELEGRAM_ID}" target="_blank">@{DEVELOPER_TELEGRAM_ID}</a></p>
    <p>For copyright-related inquiries, please refer to our <a href="{url_for('dmca')}">DMCA page</a> for specific instructions on how to submit a notice.</p>
    """
    return render_template_string(legal_page_template_html, title=title, content=content)

@app.route('/dmca')
def dmca():
    title = "DMCA Takedown Policy"
    content = f"""
    <p>{WEBSITE_NAME} is an online service provider as defined in the Digital Millennium Copyright Act. We take copyright infringement very seriously and will vigorously protect the rights of legal copyright owners.</p>
    <p><strong>Please note: We do not host any files on our servers.</strong> All content linked on our website is hosted on third-party servers and provided by non-affiliated third parties. We are merely an index of links available on the internet.</p>
    <p>If you are the copyright owner of content that appears on the {WEBSITE_NAME} website and you did not authorize the use of the content, you must notify us in writing in order for us to identify the allegedly infringing content and take action.</p>
    <p>Your written notice must include the following:</p>
    <ul>
        <li>A physical or electronic signature of the copyright owner or a person authorized to act on their behalf.</li>
        <li>Identification of the copyrighted work claimed to have been infringed.</li>
        <li>Identification of the material that is claimed to be infringing and that is to be removed, and information reasonably sufficient to permit us to locate the material (i.e., the exact URL of the page on {WEBSITE_NAME}).</li>
        <li>Your contact information, including your address, telephone number, and an email address.</li>
        <li>A statement that you have a good faith belief that use of the material in the manner complained of is not authorized by the copyright owner, its agent, or the law.</li>
        <li>A statement that the information in the notification is accurate, and, under penalty of perjury, that you are authorized to act on behalf of the copyright owner.</li>
    </ul>
    <p>Please send your takedown notice to our designated agent via email at: <strong>contact.cinezonebd@proton.me</strong> (Please replace with your actual contact email).</p>
    <p>We will act upon all valid and complete notices within 48-72 business hours.</p>
    """
    return render_template_string(legal_page_template_html, title=title, content=content)

@app.route('/privacy-policy')
def privacy_policy():
    title = "Privacy Policy"
    content = """
    <p>Your privacy is important to us. It is our policy to respect your privacy regarding any information we may collect from you across our website.</p>
    <p>We only ask for personal information when we truly need it to provide a service to you (like content requests). We collect it by fair and lawful means, with your knowledge and consent.</p>
    <p>We do not collect or store any personal user data. We do not use cookies for tracking purposes. Third-party services, such as our advertisers, may use cookies, which are not under our control.</p>
    <p>Our website may link to external sites that are not operated by us. Please be aware that we have no control over the content and practices of these sites, and cannot accept responsibility or liability for their respective privacy policies.</p>
    <p>Your continued use of our website will be regarded as acceptance of our practices around privacy and personal information. If you have any questions about how we handle user data and personal information, feel free to contact us.</p>
    """
    return render_template_string(legal_page_template_html, title=title, content=content)

@app.route('/terms-of-service')
def terms_of_service():
    title = "Terms of Service"
    content = f"""
    <p>By accessing the website at {WEBSITE_URL}, you are agreeing to be bound by these terms of service, all applicable laws and regulations, and agree that you are responsible for compliance with any applicable local laws.</p>
    <p><strong>Use License:</strong> Permission is granted to temporarily view the materials on this website for personal, non-commercial transitory viewing only. This is the grant of a license, not a transfer of title.</p>
    <p><strong>Disclaimer:</strong> The materials on {WEBSITE_NAME}'s website are provided on an 'as is' basis. {WEBSITE_NAME} makes no warranties, expressed or implied, and hereby disclaims all other warranties including, without limitation, implied warranties or conditions of merchantability, fitness for a particular purpose, or non-infringement of intellectual property or other violation of rights.</p>
    <p><strong>Limitations:</strong> In no event shall {WEBSITE_NAME} or its suppliers be liable for any damages arising out of the use or inability to use the materials on the website.</p>
    <p><strong>Links:</strong> {WEBSITE_NAME} has not reviewed all of the sites linked to its website and is not responsible for the contents of any such linked site. The inclusion of any link does not imply endorsement by {WEBSITE_NAME} of the site. Use of any such linked website is at the user's own risk.</p>
    """
    return render_template_string(legal_page_template_html, title=title, content=content)

# --- Admin Panel Routes ---
@app.route('/admin', methods=["GET", "POST"])
@requires_auth
def admin():
    if request.method == "POST":
        form_action = request.form.get("form_action")
        
        if form_action == "save_category_order": # নতুন: ক্যাটাগরি অর্ডার সেভ করার জন্য
            category_ids_ordered = request.form.get("category_order", "").split(',')
            for index, cat_id in enumerate(category_ids_ordered):
                if cat_id:
                    categories_collection.update_one({"_id": ObjectId(cat_id)}, {"$set": {"order": index}})

        elif form_action == "update_site_config":
            headlines_text = request.form.get("headlines_text", "")
            headlines_list = [line.strip() for line in headlines_text.splitlines() if line.strip()]
            logo_url = request.form.get("logo_url", "").strip()
            
            settings.update_one(
                {"_id": "site_config"},
                {"$set": {
                    "headlines": headlines_list,
                    "logo_url": logo_url
                }},
                upsert=True
            )
        elif form_action == "update_ads":
            ad_settings_data = {"ad_header": request.form.get("ad_header"), "ad_body_top": request.form.get("ad_body_top"), "ad_footer": request.form.get("ad_footer"), "ad_list_page": request.form.get("ad_list_page"), "ad_detail_page": request.form.get("ad_detail_page"), "ad_wait_page": request.form.get("ad_wait_page")}
            settings.update_one({"_id": "ad_config"}, {"$set": ad_settings_data}, upsert=True)
        elif form_action == "update_design_settings":
            design_settings_data = { "language_tag_css": request.form.get("language_tag_css").strip(), "new_badge_css": request.form.get("new_badge_css").strip(), "new_badge_text": request.form.get("new_badge_text").strip() }
            settings.update_one({"_id": "design_config"}, {"$set": design_settings_data}, upsert=True)
        elif form_action == "update_telegram_settings":
            submit_action = request.form.get("submit_action")
            tutorial_url = request.form.get("tutorial_video_url", "").strip()
            settings.update_one(
                {"_id": "telegram_config"},
                {"$set": {"tutorial_video_url": tutorial_url}},
                upsert=True
            )
            if submit_action == "add_channel":
                bot_token = request.form.get("bot_token", "").strip()
                channel_id = request.form.get("channel_id", "").strip()
                if bot_token and channel_id:
                    settings.update_one(
                        {"_id": "telegram_config"},
                        {"$push": {"channels": {"token": bot_token, "channel_id": channel_id}}},
                        upsert=True
                    )
        elif form_action == "add_category":
            category_name = request.form.get("category_name", "").strip()
            if category_name:
                # নতুন: নতুন ক্যাটাগরির জন্য order নম্বর ঠিক করা
                max_order_doc = categories_collection.find_one(sort=[("order", -1)])
                new_order = (max_order_doc['order'] + 1) if max_order_doc and 'order' in max_order_doc else 0
                categories_collection.update_one(
                    {"name": category_name}, 
                    {"$setOnInsert": {"name": category_name, "order": new_order}}, 
                    upsert=True
                )
        elif form_action == "add_platform":
            platform_name, logo_url = request.form.get("platform_name", "").strip(), request.form.get("platform_logo_url", "").strip()
            if platform_name and logo_url:
                ott_collection.update_one({"name": platform_name}, {"$set": {"name": platform_name, "logo_url": logo_url}}, upsert=True)
        elif form_action == "bulk_delete":
            ids_to_delete = request.form.getlist("selected_ids")
            if ids_to_delete: movies.delete_many({"_id": {"$in": [ObjectId(id_str) for id_str in ids_to_delete]}})
        elif form_action == "add_content":
            content_type = request.form.get("content_type", "movie")
            movie_data = {
                "title": request.form.get("title").strip(), "type": content_type,
                "poster": request.form.get("poster").strip() or PLACEHOLDER_POSTER, "backdrop": request.form.get("backdrop").strip() or None,
                "overview": request.form.get("overview").strip(), "screenshots": [url.strip() for url in request.form.get("screenshots", "").strip().splitlines() if url.strip()],
                "language": request.form.get("language").strip() or None, "genres": [g.strip() for g in request.form.get("genres", "").split(',') if g.strip()],
                "categories": request.form.getlist("categories"), "episodes": [], "links": [], "season_packs": [], "manual_links": [],
                "created_at": datetime.utcnow(), "updated_at": datetime.utcnow(), "view_count": 0,
                "tmdb_id": request.form.get("tmdb_id") or None, "is_completed": 'is_completed' in request.form
            }
            if request.form.get("ott_platform") != "None": movie_data["ott_platform"] = request.form.get("ott_platform")
            if movie_data["tmdb_id"]:
                tmdb_details = get_tmdb_details(movie_data["tmdb_id"], "series" if content_type == "series" else "movie")
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
                series_info = format_series_info(movie_data.get('episodes', []), movie_data.get('season_packs', [])) if movie_data['type'] == 'series' else None
                send_telegram_notification(movie_data, result.inserted_id, series_update_info=series_info)
        return redirect(url_for('admin'))
    
    # নতুন: অ্যাডমিন প্যানেলের কন্টেন্ট লিস্টের জন্য পেজিনেশন
    page = request.args.get('page', 1, type=int)
    skip = (page - 1) * ADMIN_ITEMS_PER_PAGE
    total_content = movies.count_documents({})
    content_list = list(movies.find({}).sort('updated_at', -1).skip(skip).limit(ADMIN_ITEMS_PER_PAGE))
    pagination = Pagination(page, ADMIN_ITEMS_PER_PAGE, total_content)

    stats = {"total_content": total_content, "total_movies": movies.count_documents({"type": "movie"}), "total_series": movies.count_documents({"type": "series"}), "pending_requests": requests_collection.count_documents({"status": "Pending"})}
    tele_config_data = settings.find_one({"_id": "telegram_config"}) or {}
    site_config = settings.find_one({"_id": "site_config"}) or {}
    headlines_text = '\n'.join(site_config.get('headlines', []))
    
    return render_template_string(
        admin_html,
        content_list=content_list, # পেজিনেটেড লিস্ট পাঠানো হচ্ছে
        pagination=pagination, # পেজিনেশন অবজেক্ট পাঠানো হচ্ছে
        stats=stats,
        requests_list=list(requests_collection.find().sort("created_at", -1)),
        ad_settings=settings.find_one({"_id": "ad_config"}) or {},
        design_settings=settings.find_one({"_id": "design_config"}) or default_design_settings,
        categories_list=list(categories_collection.find().sort("order", 1)), # order অনুযায়ী সাজানো
        ott_list=list(ott_collection.find().sort("name", 1)),
        telegram_channels=tele_config_data.get('channels', []),
        telegram_settings=tele_config_data,
        site_config=site_config,
        headlines_text=headlines_text
    )

@app.route('/admin/telegram/delete/<channel_id>')
@requires_auth
def delete_telegram_channel(channel_id):
    settings.update_one({"_id": "telegram_config"}, {"$pull": {"channels": {"channel_id": unquote(channel_id)}}})
    return redirect(url_for('admin'))

@app.route('/admin/category/delete/<cat_id>')
@requires_auth
def delete_category(cat_id):
    try: categories_collection.delete_one({"_id": ObjectId(cat_id)})
    except: pass
    return redirect(url_for('admin'))

@app.route('/admin/platform/delete/<platform_id>')
@requires_auth
def delete_platform(platform_id):
    try: ott_collection.delete_one({"_id": ObjectId(platform_id)})
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
        update_data = {
            "title": request.form.get("title").strip(), "type": content_type, "poster": request.form.get("poster").strip() or PLACEHOLDER_POSTER,
            "backdrop": request.form.get("backdrop").strip() or None, "overview": request.form.get("overview").strip(), 
            "screenshots": [url.strip() for url in request.form.get("screenshots", "").strip().splitlines() if url.strip()],
            "language": request.form.get("language").strip() or None, "genres": [g.strip() for g in request.form.get("genres").split(',') if g.strip()],
            "categories": request.form.getlist("categories"), "updated_at": datetime.utcnow(), "is_completed": 'is_completed' in request.form
        }
        
        names, urls = request.form.getlist('manual_link_name[]'), request.form.getlist('manual_link_url[]')
        update_data["manual_links"] = [{"name": names[i].strip(), "url": urls[i].strip()} for i in range(len(names)) if names[i] and urls[i]]
        update_query = {"$set": update_data}
        
        series_update_info_str = request.form.get("custom_notification_text", "").strip() or None

        if content_type == "series":
            sp_nums, sp_w, sp_d = request.form.getlist('season_pack_number[]'), request.form.getlist('season_pack_watch_link[]'), request.form.getlist('season_pack_download_link[]')
            update_data['season_packs'] = [{"season_number": int(sp_nums[i]), "watch_link": sp_w[i].strip() or None, "download_link": sp_d[i].strip() or None} for i in range(len(sp_nums)) if sp_nums[i]]
            s, n, t, l = request.form.getlist('episode_season[]'), request.form.getlist('episode_number[]'), request.form.getlist('episode_title[]'), request.form.getlist('episode_watch_link[]')
            update_data["episodes"] = [{"season": int(s[i]), "episode_number": int(n[i]), "title": t[i].strip(), "watch_link": l[i].strip()} for i in range(len(s)) if s[i] and n[i] and l[i]]
            update_query.setdefault("$unset", {})["links"] = ""

            if not series_update_info_str:
                old_ep_ids = {(ep.get('season'), ep.get('episode_number')) for ep in movie_obj.get('episodes', [])}
                old_pack_ids = {p.get('season_number') for p in movie_obj.get('season_packs', [])}
                newly_added_eps = [ep for ep in update_data["episodes"] if (ep.get('season'), ep.get('episode_number')) not in old_ep_ids]
                newly_added_packs = [p for p in update_data["season_packs"] if p.get('season_number') not in old_pack_ids]
                if newly_added_eps or newly_added_packs:
                    series_update_info_str = format_series_info(newly_added_eps, newly_added_packs)
        else: # Movie
            qualities = ["480p", "720p", "1080p", "BLU-RAY"]
            update_data["links"] = [{"quality": q, "watch_url": request.form.get(f"watch_link_{q}"), "download_url": request.form.get(f"download_link_{q}")} for q in qualities if request.form.get(f"watch_link_{q}") or request.form.get(f"download_link_{q}")]
            update_query.setdefault("$unset", {})["episodes"] = ""; update_query.setdefault("$unset", {})["season_packs"] = ""
        
        if request.form.get("ott_platform") != "None":
            update_query["$set"]["ott_platform"] = request.form.get("ott_platform")
        else:
            update_query.setdefault("$unset", {})["ott_platform"] = ""

        movies.update_one({"_id": obj_id}, update_query)
        
        if request.form.get('send_notification'):
            updated_movie = movies.find_one({"_id": obj_id})
            send_telegram_notification(updated_movie, obj_id, notification_type='update', series_update_info=series_update_info_str)
        
        return redirect(url_for('admin'))
    
    return render_template_string(edit_html, movie=movie_obj, categories_list=list(categories_collection.find().sort("name", 1)), ott_list=list(ott_collection.find().sort("name", 1)))

@app.route('/delete_movie/<movie_id>')
@requires_auth
def delete_movie(movie_id):
    try: movies.delete_one({"_id": ObjectId(movie_id)})
    except: return "Invalid ID", 400
    return redirect(url_for('admin'))

# --- Admin Panel API Routes ---
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
    query = request.args.get('query', '').strip()
    if not query: return jsonify({"error": "Query parameter is missing"}), 400
    search_title, search_year = query, None
    match = re.search(r'^(.*?)\s*\(?(\d{4})\)?$', query)
    if match: search_title, search_year = match.group(1).strip(), match.group(2)
    
    all_results, seen_ids = [], set()
    def process_tmdb_results(items, media_type_fallback=None):
        for item in items:
            if item.get('id') in seen_ids or not item.get('poster_path'): continue
            media_type = item.get('media_type', media_type_fallback)
            if media_type not in ['movie', 'tv']: continue
            all_results.append({ "id": item.get('id'), "title": item.get('title') or item.get('name'), "year": (item.get('release_date') or item.get('first_air_date', 'N/A')).split('-')[0], "poster": f"https://image.tmdb.org/t/p/w200{item.get('poster_path')}", "media_type": media_type })
            seen_ids.add(item.get('id'))

    try:
        base_params = {'api_key': TMDB_API_KEY, 'query': quote(search_title), 'language': 'en-US', 'include_adult': 'true'}
        if search_year:
            movie_params = {**base_params, 'primary_release_year': search_year}; tv_params = {**base_params, 'first_air_date_year': search_year}
            movie_res = requests.get("https://api.themoviedb.org/3/search/movie", params=movie_params, timeout=10)
            if movie_res.ok: process_tmdb_results(movie_res.json().get('results', []), 'movie')
            tv_res = requests.get("https://api.themoviedb.org/3/search/tv", params=tv_params, timeout=10)
            if tv_res.ok: process_tmdb_results(tv_res.json().get('results', []), 'tv')

        multi_params = {**base_params, 'query': quote(query)}
        multi_res = requests.get("https://api.themoviedb.org/3/search/multi", params=multi_params, timeout=10)
        if multi_res.ok: process_tmdb_results(multi_res.json().get('results', []))
        return jsonify(all_results)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/admin/api/details')
@requires_auth
def api_get_details():
    tmdb_id, media_type = request.args.get('id'), request.args.get('type')
    if not tmdb_id or not media_type: return jsonify({"error": "ID and type are required"}), 400
    details = get_tmdb_details(tmdb_id, "series" if media_type == "tv" else "movie")
    return jsonify(details) if details else (jsonify({"error": "Details not found"}), 404)

@app.route('/admin/api/resync_tmdb')
@requires_auth
def api_resync_tmdb():
    tmdb_id, media_type = request.args.get('id'), request.args.get('type')
    if not tmdb_id or not media_type: return jsonify({"error": "ID and type are required"}), 400
    details = get_tmdb_details(tmdb_id, media_type)
    return jsonify(details) if details else (jsonify({"error": "Could not fetch details"}), 404)

# --- Public API Route for Live Search ---
@app.route('/api/search')
def api_search():
    query = request.args.get('q', '').strip()
    if not query: return jsonify([])
    try:
        results = list(movies.find({"title": {"$regex": query, "$options": "i"}}, {"_id": 1, "title": 1, "poster": 1}).limit(10))
        for item in results: item['_id'] = str(item['_id'])
        return jsonify(results)
    except:
        return jsonify({"error": "An error occurred"}), 500

if __name__ == "__main__":
    port = int(os.environ.get('PORT', 3000))
    app.run(debug=True, host='0.0.0.0', port=port)
