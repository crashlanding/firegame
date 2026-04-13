# X Follower Analyzer — Implementation Plan

## Codebase Context

The repo is a Python/Flask app deployed on Heroku via Gunicorn. It uses Bootstrap 4 for styling, Jinja2 templates, and has no frontend build tooling. The new feature should follow the same conventions: Flask routes, Jinja2 templates, Bootstrap 4, `requirements.txt`, `Procfile`. No new framework layer is needed.

---

## 1. Technology Stack

**Backend:** Python 3.10 + Flask (already in use)
- `tweepy` 4.x for X API calls — abstracts pagination (`Paginator`), rate-limit backoff, and OAuth 2.0 Bearer Token auth
- `python-dotenv` for local `.env` loading
- `Flask-Caching` (SimpleCache) for memoizing user lookups

**Frontend:** Jinja2 templates + Bootstrap 4 (already in use)
- No React/Vue needed — complexity does not justify a SPA

**Deployment target:** Heroku (existing Procfile pattern)

---

## 2. X API v2 Endpoints, Auth, and Rate Limits

### Auth

Use **OAuth 2.0 App-Only (Bearer Token)**. This requires no user login flow, is sufficient for reading public follower data, and is the correct choice for a server-side lookup tool. Store the token as `TWITTER_BEARER_TOKEN` in the environment (`.env` locally, Heroku config var in production).

### Endpoints and Limits

| Purpose | Endpoint | Limit (app-only) | Notes |
|---|---|---|---|
| Resolve username to user ID | `GET /2/users/by/username/:username` | 500 req/15 min | Returns `id`, `username`, `public_metrics` |
| Get followers list | `GET /2/users/:id/followers` | **15 req/15 min** | `max_results=1000` per page; pass `user.fields=public_metrics` to get follower counts inline |
| Get user by ID (bulk) | `GET /2/users` | 300 req/15 min | Up to 100 IDs per request — not needed with the inline approach |

### Critical Insight

The followers endpoint returns each follower's `public_metrics` (including `followers_count`) **in the same response** if you pass `user.fields=public_metrics`. This eliminates a second round of per-follower API calls entirely.

The entire data-collection flow is:
1. One call to resolve username → user ID
2. One or more paginated calls to `GET /2/users/:id/followers?user.fields=public_metrics&max_results=1000`

### Rate Limit Math

With 15 requests per 15-minute window, each returning up to 1,000 followers, you can fetch at most **15,000 followers per 15-minute window**. For the MVP, cap analysis at 3 pages (3,000 followers) to keep latency and API cost low.

### API Tier Reality Check

> **A paid Basic tier (~$100/month) is essentially required.** The free tier gives near-zero reads on the followers endpoint for app-only auth. With Basic you get the 15 req/15 min window described above. This must be disclosed to users.

---

## 3. Data Flow and Architecture

```
Browser
  |
  | POST /twitter/lookup  { username: "handle" }
  |
Flask route: /twitter/lookup
  |
  |-- 1. GET /2/users/by/username/:username
  |       returns: { id, username, followers_count }
  |
  |-- 2. Paginated loop (up to MAX_PAGES = 3):
  |       GET /2/users/:id/followers
  |           ?user.fields=public_metrics
  |           &max_results=1000
  |           &pagination_token=<next_token>
  |
  |-- 3. Collect followers_count for each follower
  |-- 4. Compute: average, median, min, max, total sampled
  |
  | Render results template
  |
Browser displays results
```

### Synchronous vs Asynchronous

With `MAX_PAGES = 3` and a ~1-second inter-request gap, worst-case latency is ~5 seconds — well within Heroku's 30-second dyno timeout. A synchronous Flask route is sufficient for the MVP. An async job-queue approach (background thread + polling) can be added later if the page cap is raised.

---

## 4. Rate Limit Handling Strategy

| Strategy | Detail |
|---|---|
| **Page cap** | `MAX_PAGES = 3` (3,000 followers max). Surface this to the user. |
| **Response caching** | Cache results per username for 60 minutes with `Flask-Caching`. Repeat lookups are free. |
| **Pre-flight check** | In-memory `RateLimiter` tracks request timestamps. Reject early with "try again in Xm Ys" if the window is exhausted. |
| **Graceful mid-fetch rate limit** | Catch `tweepy.errors.TooManyRequests`, return partial results with a warning flag. |
| **Retry on transient errors** | Exponential backoff (`2 ** attempt` seconds) for 503s, capped at 3 attempts. |

---

## 5. File Structure

```
firegame/
├── app.py                          # ADD: Cache init, load_dotenv(), two new routes
├── requirements.txt                # ADD: tweepy, python-dotenv, Flask-Caching
├── .env                            # NEW: TWITTER_BEARER_TOKEN=... (gitignored)
├── .gitignore                      # ADD: .env entry
├── Procfile                        # unchanged
├── runtime.txt                     # unchanged
│
├── twitter/
│   ├── __init__.py
│   ├── client.py                   # Bearer Token auth wrapper
│   ├── analyzer.py                 # Fetch + compute statistics
│   └── rate_limiter.py             # In-memory window tracker
│
└── templates/twitter/
    ├── index.html                  # @username input form
    └── results.html                # Results display
```

---

## 6. Key Implementation Details

### `twitter/client.py`

```python
import tweepy
import os

def get_client():
    bearer_token = os.environ.get("TWITTER_BEARER_TOKEN")
    if not bearer_token:
        raise RuntimeError("TWITTER_BEARER_TOKEN not configured")
    # wait_on_rate_limit=False so we handle it ourselves and return
    # a user-friendly message rather than silently blocking the dyno
    return tweepy.Client(bearer_token=bearer_token, wait_on_rate_limit=False)
```

### `twitter/analyzer.py`

```python
import tweepy
from twitter.client import get_client

MAX_PAGES = 3
RESULTS_PER_PAGE = 1000

def get_user_by_username(username: str) -> dict:
    client = get_client()
    resp = client.get_user(username=username, user_fields=["public_metrics"])
    if resp.errors:
        raise ValueError(f"User not found: {username}")
    user = resp.data
    return {
        "id": user.id,
        "username": user.username,
        "followers_count": user.public_metrics["followers_count"]
    }

def fetch_follower_stats(user_id: str) -> dict:
    client = get_client()
    follower_counts = []
    pages_fetched = 0
    rate_limited = False

    try:
        paginator = tweepy.Paginator(
            client.get_users_followers,
            id=user_id,
            user_fields=["public_metrics"],
            max_results=RESULTS_PER_PAGE,
            limit=MAX_PAGES
        )
        for response in paginator:
            if response.data is None:
                break
            for follower in response.data:
                count = follower.public_metrics.get("followers_count", 0)
                follower_counts.append(count)
            pages_fetched += 1

    except tweepy.errors.TooManyRequests:
        rate_limited = True  # return partial results with warning
    except tweepy.errors.TwitterServerError:
        if not follower_counts:
            raise

    if not follower_counts:
        return {"error": "No followers found or account is private"}

    total = len(follower_counts)
    avg = sum(follower_counts) / total
    median = sorted(follower_counts)[total // 2]

    return {
        "sampled_count": total,
        "average_followers": round(avg, 1),
        "median_followers": median,
        "max_followers": max(follower_counts),
        "min_followers": min(follower_counts),
        "pages_fetched": pages_fetched,
        "capped": pages_fetched >= MAX_PAGES,
        "rate_limited": rate_limited,
    }
```

### `twitter/rate_limiter.py`

```python
import time
from threading import Lock

class RateLimiter:
    """
    In-memory window tracker for the followers endpoint.
    15 requests allowed per 15-minute window (app-only auth).
    """
    WINDOW_SECONDS = 15 * 60
    MAX_REQUESTS = 14  # use 14 of 15 as a safety buffer

    def __init__(self):
        self._requests = []
        self._lock = Lock()

    def can_proceed(self) -> bool:
        now = time.time()
        with self._lock:
            self._requests = [t for t in self._requests
                              if now - t < self.WINDOW_SECONDS]
            return len(self._requests) < self.MAX_REQUESTS

    def record(self):
        with self._lock:
            self._requests.append(time.time())

    def reset_time(self) -> float:
        """Seconds until the oldest request expires from the window."""
        if not self._requests:
            return 0
        return max(0, self.WINDOW_SECONDS - (time.time() - min(self._requests)))
```

### Routes to add to `app.py`

```python
from dotenv import load_dotenv
from flask_caching import Cache
from twitter.analyzer import get_user_by_username, fetch_follower_stats
from twitter.rate_limiter import RateLimiter

load_dotenv()
cache = Cache(app, config={"CACHE_TYPE": "SimpleCache", "CACHE_DEFAULT_TIMEOUT": 3600})
rate_limiter = RateLimiter()

@app.route('/twitter', methods=['GET'])
def twitter_index():
    return render_template('twitter/index.html')

@app.route('/twitter/lookup', methods=['POST'])
def twitter_lookup():
    username = request.form.get('username', '').strip().lstrip('@')
    if not username:
        return render_template('twitter/index.html', error="Please enter a username.")

    cache_key = f"twitter_lookup_{username.lower()}"
    cached = cache.get(cache_key)
    if cached:
        return render_template('twitter/results.html', **cached, cached=True)

    if not rate_limiter.can_proceed():
        wait_secs = int(rate_limiter.reset_time())
        error = f"Rate limit reached. Please try again in {wait_secs // 60}m {wait_secs % 60}s."
        return render_template('twitter/index.html', error=error)

    try:
        user = get_user_by_username(username)
    except ValueError as e:
        return render_template('twitter/index.html', error=str(e))

    rate_limiter.record()

    try:
        stats = fetch_follower_stats(user['id'])
    except Exception:
        return render_template('twitter/index.html',
            error="Failed to fetch follower data. The account may be private or the API is unavailable.")

    result_data = {"user": user, "stats": stats}
    cache.set(cache_key, result_data)
    return render_template('twitter/results.html', **result_data, cached=False)
```

### `templates/twitter/index.html`

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>X Follower Analyzer</title>
  <link rel="stylesheet" href="https://stackpath.bootstrapcdn.com/bootstrap/4.5.2/css/bootstrap.min.css">
</head>
<body>
  <div class="container" style="max-width:500px; margin-top:60px;">
    <h2 class="mb-1">X Follower Analyzer</h2>
    <p class="text-muted mb-4">Calculates the average follower count of an account's followers.</p>

    {% if error %}
    <div class="alert alert-danger">{{ error }}</div>
    {% endif %}

    <form action="/twitter/lookup" method="post">
      <div class="input-group mb-3">
        <div class="input-group-prepend">
          <span class="input-group-text">@</span>
        </div>
        <input type="text" class="form-control" name="username"
               placeholder="username" autofocus required>
        <div class="input-group-append">
          <button class="btn btn-dark" type="submit">Analyze</button>
        </div>
      </div>
      <small class="text-muted">
        Results are sampled from up to 3,000 followers and cached for 1 hour.
      </small>
    </form>
  </div>
</body>
</html>
```

### `templates/twitter/results.html`

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>Results for @{{ user.username }}</title>
  <link rel="stylesheet" href="https://stackpath.bootstrapcdn.com/bootstrap/4.5.2/css/bootstrap.min.css">
</head>
<body>
  <div class="container" style="max-width:600px; margin-top:60px;">
    <a href="/twitter" class="text-muted">&larr; New lookup</a>
    <h2 class="mt-3">@{{ user.username }}</h2>
    <p class="text-muted">Account has {{ "{:,}".format(user.followers_count) }} followers</p>

    {% if stats.error %}
      <div class="alert alert-warning">{{ stats.error }}</div>
    {% else %}
      <div class="card mb-3">
        <div class="card-body">
          <h4 class="card-title">
            Average follower count of followers:
            <strong>{{ "{:,.0f}".format(stats.average_followers) }}</strong>
          </h4>
          <hr>
          <dl class="row mb-0">
            <dt class="col-sm-5">Median follower count</dt>
            <dd class="col-sm-7">{{ "{:,}".format(stats.median_followers) }}</dd>
            <dt class="col-sm-5">Highest follower count seen</dt>
            <dd class="col-sm-7">{{ "{:,}".format(stats.max_followers) }}</dd>
            <dt class="col-sm-5">Followers sampled</dt>
            <dd class="col-sm-7">{{ "{:,}".format(stats.sampled_count) }}</dd>
          </dl>
        </div>
      </div>

      {% if stats.capped %}
      <div class="alert alert-info">
        Showing results for the first {{ "{:,}".format(stats.sampled_count) }} followers
        (capped at 3,000 to manage API usage).
      </div>
      {% endif %}

      {% if stats.rate_limited %}
      <div class="alert alert-warning">
        Rate limit reached mid-fetch. Results are based on a partial sample.
      </div>
      {% endif %}

      {% if cached %}
      <small class="text-muted">Cached result (refreshes hourly).</small>
      {% endif %}
    {% endif %}
  </div>
</body>
</html>
```

---

## 7. `requirements.txt` Additions

```
tweepy==4.14.0
python-dotenv==1.0.1
Flask-Caching==2.3.0
```

---

## 8. Environment Configuration

**Local development** — create `/home/user/firegame/.env`:
```
TWITTER_BEARER_TOKEN=AAAAAAAAAAAAAAAAAAAAAxxxxxxxxx...
```

**Heroku production:**
```bash
heroku config:set TWITTER_BEARER_TOKEN=AAAAAAA...
```

Add `.env` to `.gitignore`.

---

## 9. Caveats and Limitations

| Issue | Mitigation |
|---|---|
| Only most-recent 3,000 followers sampled | Label results clearly; explain the cap |
| Mean skewed by celebrity outliers | Show median prominently alongside average |
| Private accounts return HTTP 403 | Friendly error message |
| Multi-dyno deployments | Replace in-memory `RateLimiter` + cache with Redis |
| Free API tier is nearly useless | Basic tier (~$100/month) required; disclose this |

**Follower order note:** The API returns followers in reverse-chronological order (most recent first). The sample is not random — results should be labeled "based on most recent followers."

---

## 10. Step-by-Step Implementation Order

1. Add `TWITTER_BEARER_TOKEN` to `.env` and Heroku config vars
2. Add `tweepy`, `python-dotenv`, `Flask-Caching` to `requirements.txt`
3. Create `twitter/__init__.py` (empty)
4. Implement `twitter/client.py`
5. Implement `twitter/rate_limiter.py`
6. Implement `twitter/analyzer.py`
7. Add `load_dotenv()`, Cache init, `RateLimiter`, and two routes to `app.py`
8. Create `templates/twitter/index.html`
9. Create `templates/twitter/results.html`
10. Test locally against a small public account (under 1,000 followers avoids pagination)
11. Verify error paths: private account, nonexistent user, rate limit
12. Deploy: `git push heroku main`
