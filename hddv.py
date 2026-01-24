import requests
import time
import base64
import logging
from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor, as_completed

logging.basicConfig(level=logging.INFO)

# ================= CONFIG =================

BASE_SITE = "https://new2.hdhub4u.fo"
START_PAGE = 1
END_PAGE = 500

DEST_SITE = "https://seashell-whale-304753.hostingersite.com"
WP_API = DEST_SITE + "/wp-json/wp/v2/posts"

USERNAME = "admin2"
APP_PASSWORD = "oA1s qPxQ OqlH 9nXq kHXh MnXx"
POST_STATUS = "publish"

# ✅ REAL MOBILE CHROME UA (ORIGINAL)
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Mobile Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Connection": "keep-alive",
}

# ================= SESSION =================

session = requests.Session()
session.headers.update(HEADERS)

auth = base64.b64encode(f"{USERNAME}:{APP_PASSWORD}".encode()).decode()
WP_HEADERS = {
    "Authorization": f"Basic {auth}",
    "Content-Type": "application/json"
}

# ================= HELPERS =================

def fetch_url(url):
    try:
        return session.get(url, timeout=10)
    except Exception as e:
        logging.warning(f"Fetch failed: {url} | {e}")
        return None


# ================= LIST PAGE =================

def scrape_page(page):
    url = f"{BASE_SITE}/page/{page}/"
    r = fetch_url(url)
    if not r:
        return []

    soup = BeautifulSoup(r.text, "html.parser")
    posts = []

    for li in soup.select("li.thumb"):
        try:
            posts.append(li.select_one("a")["href"])
        except:
            pass

    return posts


# ================= POST → HUBDRIVE =================

def extract_hubdrive(post_url):
    r = fetch_url(post_url)
    if not r:
        return None

    soup = BeautifulSoup(r.text, "html.parser")
    for a in soup.find_all("a", href=True):
        if "hubdrive.space/file/" in a["href"]:
            return a["href"]
    return None


# ================= HUBDRIVE → HUBCLOUD =================

def scrape_hubdrive(hubdrive_url):
    r = fetch_url(hubdrive_url)
    if not r:
        return None, None

    soup = BeautifulSoup(r.text, "html.parser")
    btn = soup.select_one("a.btn.btn-primary.btn-user.btn-success1")

    if not btn:
        return None, None

    title = soup.title.text.strip() if soup.title else "Download"
    return title, str(btn)


# ================= WP PUBLISH =================

def publish_wp(title, content):
    payload = {
        "title": title,
        "content": content,
        "status": POST_STATUS
    }
    r = session.post(WP_API, json=payload, headers=WP_HEADERS, timeout=10)
    return r.status_code == 201


# ================= FULL PIPELINE =================

def process_post(post_url):
    hubdrive = extract_hubdrive(post_url)
    if not hubdrive:
        return "❌ HubDrive missing"

    title, content = scrape_hubdrive(hubdrive)
    if not content:
        return "❌ HubCloud missing"

    ok = publish_wp(title, content)
    return "✅ Published" if ok else "❌ WP Failed"


# ================= MAIN =================

def main():
    with ThreadPoolExecutor(max_workers=8) as executor:  # 🔥 ~8 posts/sec
        for page in range(START_PAGE, END_PAGE + 1):
            print(f"\n📄 Page {page}")
            posts = scrape_page(page)

            if not posts:
                print("⚠️ No posts")
                continue

            futures = [executor.submit(process_post, p) for p in posts]

            for f in as_completed(futures):
                print(f.result())

            time.sleep(0.2)  # micro delay (anti-ban)

# ================= START =================

if __name__ == "__main__":
    main()
