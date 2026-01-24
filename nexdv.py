import requests
from bs4 import BeautifulSoup
import time
import base64
from concurrent.futures import ThreadPoolExecutor

# ================= CONFIG =================
BASE_URL = "https://vegamovies.sy/"
START_PAGE = 100
END_PAGE = 250

DEST_SITE = "https://seashell-whale-304753.hostingersite.com"
WP_API = DEST_SITE + "/wp-json/wp/v2/posts"

USERNAME = "admin2"
APP_PASSWORD = "oA1s qPxQ OqlH 9nXq kHXh MnXx"
POST_STATUS = "publish"

HEADERS = {
    "User-Agent": "Mozilla/5.0 Chrome/120",
    "Accept": "text/html"
}

# ================= SESSION =================
session = requests.Session()
session.headers.update(HEADERS)

auth = base64.b64encode(f"{USERNAME}:{APP_PASSWORD}".encode()).decode()
WP_HEADERS = {
    "Authorization": f"Basic {auth}",
    "Content-Type": "application/json"
}

# ================= CACHES =================
visited_posts = set()
visited_buttons = set()

# ================= HELPERS =================

def fetch(url):
    r = session.get(url, timeout=10)
    r.raise_for_status()
    return r.text

def get_page_posts(page_url):
    soup = BeautifulSoup(fetch(page_url), "html.parser")
    links = []
    for a in soup.select("h2.entry-title a, h3.entry-title a"):
        href = a.get("href")
        if href and href not in visited_posts:
            links.append(href)
    return links[:20]

def extract_button_links(post_url):
    visited_posts.add(post_url)
    soup = BeautifulSoup(fetch(post_url), "html.parser")
    btn_links = []

    # h1–h6 or div with text-align:center
    for tag in soup.find_all(["h1", "h2", "h3", "h4", "h5", "h6", "div"]):
        style = tag.get("style", "")
        if "text-align" in style and "center" in style:
            for a in tag.find_all("a", href=True):
                # ensure it's a download-style button
                if a.find("button") or "btn" in a.get("class", []):
                    href = a["href"].strip()
                    if href and href not in visited_buttons:
                        visited_buttons.add(href)
                        btn_links.append(href)

    return btn_links


def scrape_button_page(btn_url):
    visited_buttons.add(btn_url)
    soup = BeautifulSoup(fetch(btn_url), "html.parser")

    # 🏷 Title
    title = soup.title.text.strip() if soup.title else "Download Links"

    content_html = ""

    # 1️⃣ Try .card first
    card = soup.select_one(".card")
    if card:
        content_html = str(card)

    # 2️⃣ Fallback → .entry-content
    if not content_html:
        entry = soup.select_one(".entry-content")
        if entry:
            content_html = str(entry)

    # 3️⃣ Last safety fallback (optional)
    if not content_html:
        content_html = "<p>Download links not found.</p>"

    return title, content_html

def publish_wp(title, content):
    payload = {
        "title": title,
        "content": content,
        "status": POST_STATUS
    }
    r = session.post(WP_API, json=payload, headers=WP_HEADERS)
    return r.status_code == 201

# ================= MAIN =================

def main():
    for page in range(START_PAGE, END_PAGE + 1):
        page_url = f"{BASE_URL}page/{page}/"
        print(f"\n📄 Page {page}")

        try:
            posts = get_page_posts(page_url)
        except Exception as e:
            print("❌ Page error:", e)
            continue

        if not posts:
            print("⚠️ No posts found, skipping page")
            continue

        print(f"➡️ {len(posts)} posts")

        for idx, post_url in enumerate(posts, 1):
            print(f"   🔗 Post {idx}")

            try:
                btn_links = extract_button_links(post_url)
                print(f"      ⚡ Buttons: {len(btn_links)}")

                # ⚡ FAST button page scraping (parallel but limited)
                with ThreadPoolExecutor(max_workers=9) as exe:
                    for title, content in exe.map(scrape_button_page, btn_links):
                        if content:
                            ok = publish_wp(title, content)
                            print("         ✅" if ok else "         ❌")

            except Exception as e:
                print("      ❌ Post error:", e)

        time.sleep(0.15)  # ultra-small delay (safe)

if __name__ == "__main__":
    main()
