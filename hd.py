import requests
from bs4 import BeautifulSoup
import random
from time import sleep
import logging
import base64
from concurrent.futures import ThreadPoolExecutor, as_completed

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# WordPress API setup
WP_API_URL = "https://zharmovies.com/wp-json/wp/v2/posts"
WP_MEDIA_URL = "https://zharmovies.com/wp-json/wp/v2/media"
WP_CATEGORIES_URL = "https://zharmovies.com/wp-json/wp/v2/categories"
WP_USERNAME = "krrishn344@gmail.com"
WP_PASSWORD = "Ett1 H8L9 7tdE DlJ6 CShQ xnFl"

# User-Agent list
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
]

# Session setup
session = requests.Session()
session.auth = requests.auth.HTTPBasicAuth(WP_USERNAME, WP_PASSWORD)


def fetch_existing_titles():
    existing = set()
    page = 1
    while True:
        resp = session.get(WP_API_URL, params={"per_page": 100, "page": page})
        if resp.status_code != 200 or not resp.json():
            break
        for p in resp.json():
            existing.add(p["title"]["rendered"].strip())
        page += 1
    logging.info(f"Fetched {len(existing)} existing post titles.")
    return existing


def fetch_url(url):
    for attempt in range(3):
        try:
            headers = {"User-Agent": random.choice(USER_AGENTS)}
            resp = session.get(url, headers=headers, timeout=20)
            resp.raise_for_status()
            return resp
        except requests.RequestException as e:
            delay = random.uniform(1, 3)
            logging.warning(f"Retry {url} after {delay:.1f}s (#{attempt+1}): {e}")
            sleep(delay)
    logging.error(f"Failed to fetch {url} after 3 attempts")
    return None


def upload_image_to_wordpress(image_url):
    resp = fetch_url(image_url)
    if not resp:
        return None
    name = image_url.split("/")[-1]
    auth = base64.b64encode(f"{WP_USERNAME}:{WP_PASSWORD}".encode()).decode()
    headers = {
        "Authorization": f"Basic {auth}",
        "Content-Disposition": f'attachment; filename="{name}"'
    }
    files = {"file": (name, resp.content)}
    up = session.post(WP_MEDIA_URL, headers=headers, files=files)
    if up.status_code == 201:
        return up.json().get("source_url")
    logging.error(f"Image upload failed: {up.text}")
    return None


def get_or_create_categories(names):
    ids = []
    ex = session.get(WP_CATEGORIES_URL, params={"per_page": 100})
    existing = {c["name"].lower(): c["id"] for c in ex.json()} if ex.status_code == 200 else {}
    auth = base64.b64encode(f"{WP_USERNAME}:{WP_PASSWORD}".encode()).decode()
    headers = {"Authorization": f"Basic {auth}", "Content-Type": "application/json"}

    for name in names:
        key = name.lower()
        if key in existing:
            ids.append(existing[key])
        else:
            cr = session.post(WP_CATEGORIES_URL, headers=headers, json={"name": name})
            if cr.status_code in (200, 201):
                ids.append(cr.json()["id"])
            else:
                logging.warning(f"Category create failed '{name}': {cr.text}")
    return ids


def replace_and_upload_images(html):
    soup = BeautifulSoup(html, "html.parser")
    # remove unwanted
    for sel in [".code-block", "ins", ".wpra-reactions-wrap", ".disqus-comments", ".wpra-reactions-container"]:
        for t in soup.select(sel):
            t.decompose()
    # images
    for img in soup.find_all("img"):
        src = img.get("src", "")
        if src.startswith("https://hdhub4u.frl/"):
            new = upload_image_to_wordpress(src)
            if new:
                img["src"] = new
            else:
                logging.warning(f"Image replace failed: {src}")
    # links
    for a in soup.find_all("a", href=True):
        if a["href"].startswith("https://hdhub4u.frl/"):
            a["href"] = a["href"].replace("https://hdhub4u.frl/", "/")
    return str(soup)


def scrape_page(url):
    resp = fetch_url(url)
    if not resp:
        return []
    soup = BeautifulSoup(resp.content, "html.parser")
    items = []
    for li in soup.select("li.thumb"):
        try:
            link = li.select_one("a")["href"]
            title = li.select_one("figcaption p").text.strip()
            items.append({"link": link, "title": title})
        except Exception as e:
            logging.warning(f"Parse error on {url}: {e}")
    return items


def scrape_post(u):
    resp = fetch_url(u)
    if not resp:
        return None
    soup = BeautifulSoup(resp.content, "html.parser")
    body = soup.select_one("main.page-body")
    if not body:
        logging.warning(f"No content at {u}")
        return None

    # categories
    cats = []
    meta = soup.select_one("div.page-meta")
    if meta:
        cats = [em.text.strip() for em in meta.select("a em.material-text")]

    title_tag = soup.select_one("h1.page-title span.material-text")
    title = title_tag.text.strip() if title_tag else "No Title"

    pub = soup.select_one('meta[property="article:published_time"]')
    date = pub["content"] if pub else None

    content_html = replace_and_upload_images(str(body))

    return {
        "title": title,
        "content": content_html,
        "published_date": date,
        "categories": cats,
    }


def upload_to_wordpress(data):
    payload = {
        "title": data["title"],
        "content": data["content"],
        "status": "publish",
        "date": data.get("published_date"),
    }
    if data.get("categories"):
        ids = get_or_create_categories(data["categories"])
        if ids:
            payload["categories"] = ids

    auth = base64.b64encode(f"{WP_USERNAME}:{WP_PASSWORD}".encode()).decode()
    headers = {"Authorization": f"Basic {auth}", "Content-Type": "application/json"}
    r = session.post(WP_API_URL, json=payload, headers=headers)
    if r.status_code == 201:
        logging.info(f"Uploaded: {data['title']}")
        return True
    else:
        logging.error(f"Upload failed '{data['title']}': {r.text}")
        return False


def process_page(page_url, existing_titles):
    posts = scrape_page(page_url)
    uploaded_titles = []

    with ThreadPoolExecutor(max_workers=2) as post_executor:
        futures = []
        for p in posts:
            if p["title"] in existing_titles:
                logging.info(f"Duplicate skip: {p['title']}")
                continue
            futures.append(post_executor.submit(scrape_post, p["link"]))

        for f in as_completed(futures):
            post_data = f.result()
            if post_data and upload_to_wordpress(post_data):
                existing_titles.add(post_data["title"])
                uploaded_titles.append(post_data["title"])

    return uploaded_titles


def main():
    base = "https://hdhub4u.gratis/category/bollywood-movies/"
    start, end = 1, 75
    existing = fetch_existing_titles()
    all_uploaded = []

    with ThreadPoolExecutor(max_workers=10) as page_executor:
        future_to_page = {
            page_executor.submit(process_page, f"{base}page/{pg}/", existing): pg
            for pg in range(start, end + 1)
        }

        for future in as_completed(future_to_page):
            pg = future_to_page[future]
            try:
                ups = future.result()
                logging.info(f"Page {pg} uploaded {len(ups)} posts.")
                all_uploaded.extend(ups)
            except Exception as exc:
                logging.error(f"Page {pg} generated error: {exc}")

    logging.info(f"Total uploaded posts: {len(all_uploaded)}")
    for t in all_uploaded:
        logging.info(f"--> {t}")


if __name__ == "__main__":
    main()
