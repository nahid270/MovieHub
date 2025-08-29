import os
from flask import Flask, render_template_string, request, redirect, url_for, session, jsonify

# ----------------------------
# 1. অ্যাপ কনফিগারেশন
# ----------------------------
app = Flask(__name__)
# সেশন ব্যবহারের জন্য একটি সিক্রেট কী দরকার। ডিপ্লয়মেন্টের সময় এটি পরিবর্তন করা উচিত।
app.secret_key = os.environ.get('SECRET_KEY', 'my_super_secret_key_for_dev')

# ----------------------------
# 2. ইন-মেমোরি ডেটাবেস (বাস্তব প্রজেক্টে MongoDB বা PostgreSQL ব্যবহৃত হবে)
# ----------------------------
# এটি আমাদের মুভির তালিকা। বাস্তব অ্যাপে এটি ডেটাবেস থেকে আসবে।
movies_db = [
    {
        "id": 1,
        "title": "Inception",
        "year": 2010,
        "genre": ["Sci-Fi", "Action", "Thriller"],
        "description": "A thief who steals corporate secrets through the use of dream-sharing technology is given the inverse task of planting an idea into the mind of a C.E.O.",
        "poster_url": "https://image.tmdb.org/t/p/w500/oYuLEt3zVCKq27gApcjBJUuNXa6.jpg",
        "rating": 8.8,
        "is_featured": True,
        "is_trending": True,
    },
    {
        "id": 2,
        "title": "The Dark Knight",
        "year": 2008,
        "genre": ["Action", "Crime", "Drama"],
        "description": "When the menace known as the Joker wreaks havoc and chaos on the people of Gotham, Batman must accept one of the greatest psychological and physical tests of his ability to fight injustice.",
        "poster_url": "https://image.tmdb.org/t/p/w500/qJ2tW6WMUDux911r6m7haRef0WH.jpg",
        "rating": 9.0,
        "is_featured": True,
        "is_trending": False,
    },
    {
        "id": 3,
        "title": "Parasite",
        "year": 2019,
        "genre": ["Comedy", "Thriller", "Drama"],
        "description": "Greed and class discrimination threaten the newly formed symbiotic relationship between the wealthy Park family and the destitute Kim clan.",
        "poster_url": "https://image.tmdb.org/t/p/w500/7IiTTgloJzvGI1TAYymCfbfl3vT.jpg",
        "rating": 8.5,
        "is_featured": False,
        "is_trending": True,
    }
]
next_movie_id = 4 # নতুন মুভি যোগ করার জন্য আইডি ট্র্যাকিং

# ----------------------------
# 3. HTML টেমপ্লেট (বাস্তব প্রজেক্টে এগুলো আলাদা .html ফাইলে থাকে)
# ----------------------------

# মূল লেআউট, যা সব পেজে ব্যবহৃত হবে
LAYOUT_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{{ title }} - MovieFlix</title>
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif; background-color: #0b0c10; color: #c5c6c7; margin: 0; }
        .navbar { background-color: #1f2833; padding: 1rem; display: flex; justify-content: space-between; align-items: center; border-bottom: 2px solid #66fcf1; }
        .navbar a { color: #66fcf1; text-decoration: none; font-weight: bold; font-size: 1.2rem; margin: 0 1rem; }
        .navbar .logo { font-size: 1.8rem; color: #45a29e; }
        .container { max-width: 1300px; margin: 2rem auto; padding: 0 1rem; }
        h1, h2 { color: #66fcf1; border-left: 4px solid #45a29e; padding-left: 10px; }
        /* Mobile responsive adjustments */
        @media (max-width: 768px) {
            .navbar { flex-direction: column; }
            .navbar a { margin: 0.5rem 0; }
        }
    </style>
</head>
<body>
    <nav class="navbar">
        <a href="/" class="logo">🎬 MovieFlix</a>
        <div>
            <a href="/">Home</a>
            {% if session.get('logged_in') %}
                <a href="/admin">Admin Panel</a>
                <a href="/logout">Logout</a>
            {% else %}
                <a href="/login">Admin Login</a>
            {% endif %}
        </div>
    </nav>
    <main class="container">
        {{ content | safe }}
    </main>
</body>
</html>
"""

# হোমপেজের কন্টেন্ট
HOME_TEMPLATE = """
<style>
    .movie-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 1.5rem; }
    .movie-card { background-color: #1f2833; border-radius: 8px; overflow: hidden; text-decoration: none; color: #c5c6c7; transition: transform 0.2s; }
    .movie-card:hover { transform: scale(1.05); }
    .movie-card img { width: 100%; display: block; }
    .movie-card-content { padding: 1rem; }
    .movie-card-title { font-size: 1.1rem; font-weight: bold; margin: 0 0 0.5rem 0; color: #ffffff; }
    .movie-card-year { font-size: 0.9rem; color: #45a29e; }
    @media (max-width: 480px) {
        .movie-grid { grid-template-columns: repeat(auto-fill, minmax(140px, 1fr)); }
    }
</style>
<h1>Featured Movies</h1>
<div class="movie-grid">
    {% for movie in featured_movies %}
    <a href="/movie/{{ movie.id }}" class="movie-card">
        <img src="{{ movie.poster_url }}" alt="{{ movie.title }}">
        <div class="movie-card-content">
            <h3 class="movie-card-title">{{ movie.title }}</h3>
            <p class="movie-card-year">{{ movie.year }}</p>
        </div>
    </a>
    {% endfor %}
</div>
<h1 style="margin-top: 3rem;">Trending Movies</h1>
<div class="movie-grid">
    {% for movie in trending_movies %}
    <a href="/movie/{{ movie.id }}" class="movie-card">
        <img src="{{ movie.poster_url }}" alt="{{ movie.title }}">
        <div class="movie-card-content">
            <h3 class="movie-card-title">{{ movie.title }}</h3>
            <p class="movie-card-year">{{ movie.year }}</p>
        </div>
    </a>
    {% endfor %}
</div>
"""

# মুভি ডিটেইলস পেজের কন্টেন্ট
DETAIL_TEMPLATE = """
<style>
    .detail-container { display: flex; gap: 2rem; }
    .poster img { max-width: 300px; border-radius: 8px; }
    .info h1 { font-size: 3rem; margin-top: 0; }
    .info .genre { background-color: #45a29e; color: #0b0c10; padding: 0.3rem 0.7rem; border-radius: 15px; font-size: 0.9rem; margin-right: 0.5rem; }
    .back-link { color: #66fcf1; text-decoration: none; margin-bottom: 1rem; display: inline-block; }
    @media (max-width: 768px) {
        .detail-container { flex-direction: column; align-items: center; text-align: center; }
        .info h1 { font-size: 2rem; }
    }
</style>
<a href="/" class="back-link">&larr; Back to Home</a>
<div class="detail-container">
    <div class="poster">
        <img src="{{ movie.poster_url }}" alt="{{ movie.title }}">
    </div>
    <div class="info">
        <h1>{{ movie.title }} ({{ movie.year }})</h1>
        <p><strong>Rating:</strong> {{ movie.rating }} / 10</p>
        <div style="margin-bottom: 1rem;">
            {% for g in movie.genre %}
            <span class="genre">{{ g }}</span>
            {% endfor %}
        </div>
        <p>{{ movie.description }}</p>
    </div>
</div>
"""

# লগইন পেজের কন্টেন্ট
LOGIN_TEMPLATE = """
<style>
    .login-form { max-width: 400px; margin: 2rem auto; padding: 2rem; background-color: #1f2833; border-radius: 8px; }
    .login-form h1 { text-align: center; }
    .form-group { margin-bottom: 1rem; }
    .form-group label { display: block; margin-bottom: 0.5rem; }
    .form-group input { width: 100%; padding: 0.7rem; border-radius: 4px; border: none; background-color: #0b0c10; color: white; box-sizing: border-box; }
    .form-group button { width: 100%; padding: 0.8rem; background-color: #66fcf1; color: #0b0c10; border: none; border-radius: 4px; font-weight: bold; cursor: pointer; }
    .error { color: #e50914; text-align: center; }
</style>
<div class="login-form">
    <h1>Admin Login</h1>
    {% if error %}
    <p class="error">{{ error }}</p>
    {% endif %}
    <form method="post">
        <div class="form-group">
            <label for="username">Username:</label>
            <input type="text" id="username" name="username" value="admin" required>
        </div>
        <div class="form-group">
            <label for="password">Password:</label>
            <input type="password" id="password" name="password" value="password" required>
        </div>
        <div class="form-group">
            <button type="submit">Login</button>
        </div>
    </form>
</div>
"""

# অ্যাডমিন প্যানেলের কন্টেন্ট
ADMIN_TEMPLATE = """
<style>
    table { width: 100%; border-collapse: collapse; }
    th, td { padding: 0.8rem; border: 1px solid #1f2833; text-align: left; }
    th { background-color: #1f2833; color: #66fcf1; }
    .add-movie-form { margin-top: 2rem; padding: 2rem; background-color: #1f2833; border-radius: 8px; }
    /* ... (login form styles can be reused) ... */
</style>
<h2>Movie Management</h2>
<table>
    <thead>
        <tr>
            <th>ID</th>
            <th>Title</th>
            <th>Year</th>
        </tr>
    </thead>
    <tbody>
        {% for movie in all_movies %}
        <tr>
            <td>{{ movie.id }}</td>
            <td>{{ movie.title }}</td>
            <td>{{ movie.year }}</td>
        </tr>
        {% endfor %}
    </tbody>
</table>

<div class="add-movie-form">
    <h2>Add New Movie</h2>
    <form method="post" action="/admin/add">
        <input type="text" name="title" placeholder="Title" required style="width: 100%; padding: 0.7rem; margin-bottom: 1rem; box-sizing: border-box;">
        <input type="number" name="year" placeholder="Year" required style="width: 100%; padding: 0.7rem; margin-bottom: 1rem; box-sizing: border-box;">
        <textarea name="description" placeholder="Description" required style="width: 100%; padding: 0.7rem; margin-bottom: 1rem; box-sizing: border-box;"></textarea>
        <input type="text" name="poster_url" placeholder="Poster URL" required style="width: 100%; padding: 0.7rem; margin-bottom: 1rem; box-sizing: border-box;">
        <button type="submit" style="width: 100%; padding: 0.8rem; background-color: #66fcf1; color: #0b0c10; border: none; font-weight: bold; cursor: pointer;">Add Movie</button>
    </form>
</div>
"""

# ----------------------------
# 4. রাউট এবং লজিক (Backend Logic)
# ----------------------------

# Helper function to render pages within the layout
def render_page(title, content_template, **kwargs):
    content = render_template_string(content_template, **kwargs)
    return render_template_string(LAYOUT_TEMPLATE, title=title, content=content)

# হোমপেজ
@app.route('/')
def home():
    featured_movies = [m for m in movies_db if m.get('is_featured')]
    trending_movies = [m for m in movies_db if m.get('is_trending')]
    return render_page(
        title="Home",
        content_template=HOME_TEMPLATE,
        featured_movies=featured_movies,
        trending_movies=trending_movies
    )

# মুভি ডিটেইলস পেজ
@app.route('/movie/<int:movie_id>')
def movie_detail(movie_id):
    movie = next((m for m in movies_db if m['id'] == movie_id), None)
    if movie:
        return render_page(title=movie['title'], content_template=DETAIL_TEMPLATE, movie=movie)
    return "Movie not found", 404

# লগইন পেজ
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        # ডেমো পারপাসে ইউজারনেম 'admin' এবং পাসওয়ার্ড 'password' হার্ডকোড করা হয়েছে
        if request.form['username'] == 'admin' and request.form['password'] == 'password':
            session['logged_in'] = True
            return redirect(url_for('admin_panel'))
        else:
            return render_page(title="Login", content_template=LOGIN_TEMPLATE, error="Invalid credentials")
    return render_page(title="Login", content_template=LOGIN_TEMPLATE)

# লগআউট
@app.route('/logout')
def logout():
    session.pop('logged_in', None)
    return redirect(url_for('home'))

# অ্যাডমিন প্যানেল
@app.route('/admin')
def admin_panel():
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    return render_page(title="Admin Panel", content_template=ADMIN_TEMPLATE, all_movies=movies_db)

# নতুন মুভি যোগ করার জন্য অ্যাডমিন অ্যাকশন
@app.route('/admin/add', methods=['POST'])
def add_movie():
    global next_movie_id
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    
    new_movie = {
        "id": next_movie_id,
        "title": request.form['title'],
        "year": int(request.form['year']),
        "description": request.form['description'],
        "poster_url": request.form['poster_url'],
        "genre": ["New"], "rating": 0.0, "is_featured": False, "is_trending": True,
    }
    movies_db.append(new_movie)
    next_movie_id += 1
    return redirect(url_for('admin_panel'))

# একটি বেসিক API এন্ডপয়েন্টের উদাহরণ
@app.route('/api/movies')
def api_movies():
    return jsonify(movies_db)

# ----------------------------
# 5. অ্যাপ চালানো
# ----------------------------
if __name__ == '__main__':
    # Vercel বা অন্য কোনো প্রোডাকশন সার্ভারে এটি ব্যবহৃত হবে না
    app.run(host='0.0.0.0', port=5000, debug=True)
