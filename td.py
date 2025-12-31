import requests, base64, time
from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor
import dateparser

# ================= CONFIG ================= #
BASE_URL = "https://moviesmod.build/page/"
START_PAGE = 186
END_PAGE = 500

WP_API = "https://ecom.tamilprint.info/wp-json/wp/v2/posts"
WP_MEDIA = "https://ecom.tamilprint.info/wp-json/wp/v2/media"
WP_CAT = "https://ecom.tamilprint.info/wp-json/wp/v2/categories"

WP_USER = "admin"
WP_PASS = "uY7B ApDt 2HBW BCKy p7mb HfWP"

MAX_WORKERS = 15
# ======================================== #

session = requests.Session()
session.auth = requests.auth.HTTPBasicAuth(WP_USER, WP_PASS)

HEADERS = {"User-Agent": "Mozilla/5.0"}

# ---------------------------------------- #

def fetch(url):
    try:
        r = session.get(url, headers=HEADERS, timeout=15)
        r.raise_for_status()
        return r
    except:
        return None


# ---------------- EXISTING POSTS ---------------- #
def get_existing_titles():
    titles = set()
    page = 1
    while True:
        r = session.get(WP_API, params={"per_page": 100, "page": page})
        if r.status_code != 200 or not r.json():
            break
        for p in r.json():
            titles.add(p["title"]["rendered"].strip().lower())
        page += 1
    return titles


# ---------------- CATEGORY ---------------- #
def get_category_id(name):
    r = session.get(WP_CAT, params={"search": name})
    if r.status_code == 200 and r.json():
        return r.json()[0]["id"]

    res = session.post(WP_CAT, auth=(WP_USER, WP_PASS), json={"name": name})
    if res.status_code == 201:
        return res.json()["id"]
    return None


# ---------------- IMAGE UPLOAD ---------------- #
def upload_image(img_url):
    try:
        r = fetch(img_url)
        if not r:
            return None

        filename = img_url.split("/")[-1].split("?")[0]
        headers = {
            "Authorization": "Basic " + base64.b64encode(f"{WP_USER}:{WP_PASS}".encode()).decode()
        }

        res = session.post(
            WP_MEDIA,
            headers=headers,
            files={"file": (filename, r.content)}
        )
        if res.status_code == 201:
            return res.json()["id"]
    except:
        pass
    return None


# ---------------- CLEAN CONTENT ---------------- #
def clean_content(soup):
    remove_selectors = [
        ".alert", ".alert-danger", ".button", ".button4k",
        ".buttontg", ".download-btn", ".btn", ".ads"
    ]
    for sel in remove_selectors:
        for tag in soup.select(sel):
            tag.decompose()


# ---------------- SCRAPE POST ---------------- #
def scrape_post(url, fallback_img):
    r = fetch(url)
    if not r:
        return None

    soup = BeautifulSoup(r.text, "html.parser")

    clean_content(soup)

    title_tag = soup.find("h1")
    if not title_tag:
        return None
    title = title_tag.get_text(strip=True)

    content = soup.find("div", class_="entry-content")
    if not content:
        return None

    # IMAGE priority
    featured = None
    og = soup.find("meta", property="og:image")
    if og and og.get("content"):
        featured = og["content"]
    elif fallback_img:
        featured = fallback_img
    else:
        img = content.find("img")
        if img:
            featured = img.get("src")

    if featured and featured.startswith("/"):
        from urllib.parse import urljoin
        featured = urljoin(url, featured)

    # DATE
    published = None
    t = soup.find("meta", property="article:published_time")
    if t:
        published = dateparser.parse(t["content"]).isoformat()

    # CATEGORY
    cats = []
    cat_box = soup.select_one(".thecategory")
    if cat_box:
        for a in cat_box.find_all("a"):
            cid = get_category_id(a.text.strip())
            if cid:
                cats.append(cid)

    return {
        "title": title,
        "content": str(content),
        "image": featured,
        "date": published,
        "cats": cats
    }


# ---------------- UPLOAD ---------------- #
def upload_post(data):
    payload = {
        "title": data["title"],
        "content": data["content"],
        "status": "publish",
        "date": data["date"],
        "categories": data["cats"]
    }

    if data["image"]:
        mid = upload_image(data["image"])
        if mid:
            payload["featured_media"] = mid

    r = session.post(WP_API, auth=(WP_USER, WP_PASS), json=payload)
    return r.status_code == 201


# ---------------- PAGE SCRAPER ---------------- #
def scrape_page(page):
    url = f"{BASE_URL}{page}/"
    print(f"\n📄 PAGE {page}")
    r = fetch(url)
    if not r:
        return []

    soup = BeautifulSoup(r.text, "html.parser")
    results = []

    for art in soup.select("article"):
        a = art.find("a", href=True)
        if not a:
            continue

        img = art.select_one(".featured-thumbnail img")
        thumb = img["src"] if img else None
        results.append((a["href"], thumb))

    return results


# ---------------- MAIN ---------------- #
def main():
    existing = get_existing_titles()

    for page in range(START_PAGE, END_PAGE + 1):
        posts = scrape_page(page)

        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as exe:
            for link, img in posts:
                def task(u=link, f=img):
                    data = scrape_post(u, f)
                    if not data:
                        return
                    if data["title"].lower() in existing:
                        print("⏭ SKIP:", data["title"])
                        return
                    if upload_post(data):
                        print("✅ POSTED:", data["title"])
                        existing.add(data["title"].lower())

                exe.submit(task)


if __name__ == "__main__":
    main()
