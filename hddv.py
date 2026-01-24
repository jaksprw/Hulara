import requests
import time
import base64
import logging
from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor

logging.basicConfig(level=logging.INFO)

# ================= CONFIG =================

BASE_SITE = "https://new2.hdhub4u.fo"
START_PAGE = 1
END_PAGE = 50000

DEST_SITE = "https://seashell-whale-304753.hostingersite.com"
WP_API = DEST_SITE + "/wp-json/wp/v2/posts"

USERNAME = "admin2"
APP_PASSWORD = "oA1s qPxQ OqlH 9nXq kHXh MnXx"
POST_STATUS = "publish"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Linux; Android 10) Chrome/120",
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

# ================= HELPERS =================

def fetch_url(url):
    try:
        r = session.get(url, timeout=12)
        r.raise_for_status()
        return r
    except Exception as e:
        logging.warning(f"Fetch failed: {url} | {e}")
        return None


# ================= HDHUB4U LIST PAGE =================

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
        except:
            pass

    return items


# ================= POST PAGE → HUBDRIVE =================

def extract_hubdrive(post_url):
    resp = fetch_url(post_url)
    if not resp:
        return None

    soup = BeautifulSoup(resp.content, "html.parser")

    for a in soup.find_all("a", href=True):
        href = a["href"]
        if "hubdrive.space/file/" in href:
            return href

    return None


# ================= HUBDRIVE → HUBCLOUD =================

def scrape_hubdrive(hubdrive_url):
    resp = fetch_url(hubdrive_url)
    if not resp:
        return None, None

    soup = BeautifulSoup(resp.content, "html.parser")

    btn = soup.select_one(
        'a.btn.btn-primary.btn-user.btn-success1'
    )

    if not btn:
        return None, None

    title = soup.title.text.strip() if soup.title else "Download Link"
    content = str(btn)

    return title, content


# ================= WORDPRESS PUBLISH =================

def publish_wp(title, content):
    payload = {
        "title": title,
        "content": content,
        "status": POST_STATUS
    }

    r = session.post(WP_API, json=payload, headers=WP_HEADERS)
    return r.status_code == 201


# ================= MAIN RUNNER =================

def main():
    for page in range(START_PAGE, END_PAGE + 1):
        page_url = f"{BASE_SITE}/page/{page}/"
        print(f"\n📄 Page {page}")

        posts = scrape_page(page_url)
        if not posts:
            print("⚠️ No posts found")
            continue

        print(f"➡️ {len(posts)} posts")

        for post in posts:
            print("🔗", post["title"])

            hubdrive = extract_hubdrive(post["link"])
            if not hubdrive:
                print("   ❌ HubDrive not found")
                continue

            title, content = scrape_hubdrive(hubdrive)
            if not content:
                print("   ❌ HubCloud button missing")
                continue

            ok = publish_wp(title, content)
            print("   ✅ Published" if ok else "   ❌ Publish failed")

        time.sleep(0.2)


# ================= START =================

if __name__ == "__main__":
    main()
