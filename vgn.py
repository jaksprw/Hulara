import requests
import random
import logging
from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor, as_completed
from dateutil import parser

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# WordPress API setup
WP_API_URL = "https://lightsalmon-finch-839269.hostingersite.com/wp-json/wp/v2/posts"
WP_CATEGORY_URL = "https://lightsalmon-finch-839269.hostingersite.com/wp-json/wp/v2/categories"
WP_MEDIA_URL = "https://lightsalmon-finch-839269.hostingersite.com/wp-json/wp/v2/media"
WP_USERNAME = "admin"
WP_PASSWORD = "nT9v 6ej1 bwPX dEjT koUR i3aH"

# User-Agent list
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
]

# Session setup
session = requests.Session()
session.auth = (WP_USERNAME, WP_PASSWORD)

# Cache for uploaded images
uploaded_images_cache = {}

def fetch_url(url):
    """Fetch a URL with retries and User-Agent rotation."""
    for attempt in range(3):
        try:
            headers = {"User-Agent": random.choice(USER_AGENTS)}
            response = session.get(url, headers=headers, timeout=10)
            response.raise_for_status()
            return response
        except requests.exceptions.RequestException as e:
            logging.warning(f"Retrying {url} (Attempt {attempt + 1}): {e}")
            continue
    logging.error(f"Failed to fetch URL after 3 attempts: {url}")
    return None

def get_existing_titles():
    """Fetch all existing post titles from WordPress."""
    existing_titles = set()
    page = 1
    while True:
        response = session.get(WP_API_URL, params={"per_page": 100, "page": page})
        if response.status_code != 200:
            break
        posts = response.json()
        if not posts:
            break
        for post in posts:
            existing_titles.add(post["title"]["rendered"].strip().lower())
        page += 1
    logging.info(f"Fetched {len(existing_titles)} existing post titles.")
    return existing_titles

def get_or_create_category(name):
    """Check if a category exists; if not, create it and return the ID."""
    response = session.get(WP_CATEGORY_URL, params={"search": name})
    if response.status_code == 200:
        categories = response.json()
        for cat in categories:
            if cat["name"].lower() == name.lower():
                return cat["id"]
    category_data = {"name": name}
    response = session.post(WP_CATEGORY_URL, json=category_data)
    if response.status_code == 201:
        return response.json()["id"]
    else:
        logging.error(f"Failed to create category '{name}': {response.text}")
        return None

def upload_featured_image_once(image_url):
    """Download and upload featured image to WordPress only once."""
    if not image_url:
        return None
    if image_url in uploaded_images_cache:
        return uploaded_images_cache[image_url]
    try:
        image_data = requests.get(image_url, timeout=10).content
        filename = image_url.split("/")[-1].split("?")[0]
        headers = {
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Content-Type": "image/jpeg",
        }
        response = session.post(WP_MEDIA_URL, headers=headers, data=image_data)
        if response.status_code == 201:
            media_id = response.json()["id"]
            uploaded_images_cache[image_url] = media_id
            return media_id
        else:
            logging.error(f"Image upload failed: {response.text}")
            return None
    except Exception as e:
        logging.error(f"Error uploading image {image_url}: {e}")
        return None

def replace_source_url_in_content(content):
    """Replace all https://vegamovies.band/ URLs with '/' in the content."""
    if not content:
        return content
    return content.replace("https://vegamovies.band/", "/")

def scrape_page(url):
    """Scrape post links from a page."""
    response = fetch_url(url)
    if not response:
        return []
    soup = BeautifulSoup(response.content, 'html.parser')
    posts = []
    for article in soup.select('article.grid-item'):
        try:
            post_link = article.select_one('.post-title a')['href']
            post_title = article.select_one('.post-title a').text.strip()
            featured_image = article.select_one('.post-thumbnail img')['src']
            categories = [cls.replace('category-', '').replace('-', ' ').title() for cls in article.get("class", []) if cls.startswith('category-')]
            if not categories:
                categories = ["1080p HD"]
            posts.append({
                'link': post_link,
                'title': post_title,
                'featured_image': featured_image,
                'categories': categories
            })
        except Exception as e:
            logging.warning(f"Error parsing article: {e}")
    return posts

def scrape_post(post_url):
    """Scrape an individual post."""
    response = fetch_url(post_url)
    if not response:
        return None
    soup = BeautifulSoup(response.content, 'html.parser')
    post_title = soup.select_one('.post-title.entry-title')
    post_title = post_title.text.strip() if post_title else "No Title"
    featured_image = soup.select_one('meta[property="og:image"]')
    featured_image = featured_image['content'] if featured_image else None
    content_div = soup.select_one('.entry-inner')
    post_content = str(content_div) if content_div else "<p>No content available</p>"
    # Extract Date
    published_date_tag = soup.select_one('.post-byline time')
    published_date = None
    if published_date_tag:
        try:
            published_date = parser.parse(published_date_tag.text.strip()).isoformat()
        except Exception:
            pass
    # Replace source URLs
    post_content = replace_source_url_in_content(post_content)
    return {
        'title': post_title,
        'content': post_content,
        'featured_image': featured_image,
        'published_date': published_date,
    }

def upload_post_to_wordpress(title, content, featured_image, categories, existing_titles, published_date):
    """Upload post to WordPress with duplicate title check and correct date."""
    if title.lower() in existing_titles:
        logging.info(f"⚠️ Skipping duplicate post: {title}")
        return
    category_ids = [get_or_create_category(cat) for cat in categories if cat]
    category_ids = [cat_id for cat_id in category_ids if cat_id]
    featured_image_id = upload_featured_image_once(featured_image) if featured_image else None
    post_data = {
        "title": title,
        "content": content,
        "status": "publish",
        "categories": category_ids,
        "featured_media": featured_image_id,
        "date": published_date if published_date else None,
    }
    response = session.post(WP_API_URL, json=post_data)
    if response.status_code == 201:
        logging.info(f"✅ Post '{title}' successfully uploaded with date {published_date}.")
        existing_titles.add(title.lower())
    else:
        logging.error(f"❌ Post '{title}' upload failed: {response.text}")

def process_page(page, base_url, existing_titles):
    """Process a single page: scrape posts and upload them."""
    posts = scrape_page(f"{base_url}page/{page}/")
    logging.info(f"Scraped {len(posts)} posts from page {page}")
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = []
        for post in posts:
            post_data = scrape_post(post['link'])
            if post_data:
                futures.append(executor.submit(
                    upload_post_to_wordpress,
                    post_data['title'],
                    post_data['content'],
                    post_data['featured_image'],
                    post['categories'],
                    existing_titles,
                    post_data['published_date']
                ))
        for future in as_completed(futures):
            future.result()  # Wait for all uploads to finish

def main():
    """Main function to scrape and upload posts."""
    base_url = "https://vegamovies.yoga/"
    start_page = 1
    end_page = 700  # Adjust as needed
    logging.info(f"Fetching existing posts from WordPress...")
    existing_titles = get_existing_titles()
    logging.info(f"Scraping pages from {start_page} to {end_page}")
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = {executor.submit(process_page, page, base_url, existing_titles): page for page in range(start_page, end_page + 1)}
        for future in as_completed(futures):
            future.result()  # Wait for all pages to finish

if __name__ == "__main__":
    main()
