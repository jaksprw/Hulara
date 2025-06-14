import requests
from bs4 import BeautifulSoup
import random
from time import sleep
import logging
import base64
from dateutil import parser
import os
import tempfile
import threading
import concurrent.futures

# --- Logging Setup ---
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# --- WordPress API Info ---
WP_API_URL = "https://9xflix.at/wp-json/wp/v2/posts"
WP_MEDIA_URL = "https://9xflix.at/wp-json/wp/v2/media"
WP_CATEGORIES_URL = "https://9xflix.at/wp-json/wp/v2/categories"
WP_USERNAME = "admin"
WP_PASSWORD = "FJJc J9uY KO1T xArI DI2y Igd2"

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
]

session = requests.Session()
session.auth = requests.auth.HTTPBasicAuth(WP_USERNAME, WP_PASSWORD)

uploaded_images_cache = {}

def fetch_existing_titles():
    existing_titles = set()
    page = 1
    while True:
        response = session.get(WP_API_URL, params={"per_page": 100, "page": page})
        if response.status_code != 200:
            logging.error(f"Failed to fetch posts page {page}, status code: {response.status_code}")
            break
        try:
            data = response.json()
        except Exception as e:
            logging.error(f"JSON decode error on page {page}: {e}")
            break
        if not data:
            break
        for post in data:
            existing_titles.add(post['title']['rendered'].strip())
        page += 1
    logging.info(f"Fetched {len(existing_titles)} existing post titles.")
    return existing_titles

def fetch_url(url):
    for attempt in range(3):
        try:
            headers = {"User-Agent": random.choice(USER_AGENTS)}
            response = session.get(url, headers=headers, timeout=10)
            response.raise_for_status()
            return response
        except Exception as e:
            delay = random.uniform(1, 3)
            logging.warning(f"Retrying {url} after {delay:.1f}s (Attempt {attempt+1}): {e}")
            sleep(delay)
    logging.error(f"Failed to fetch URL: {url}")
    return None

def upload_image_to_wordpress(image_url):
    if image_url in uploaded_images_cache:
        return uploaded_images_cache[image_url]

    try:
        headers = {"User-Agent": random.choice(USER_AGENTS)}
        resp = requests.get(image_url, headers=headers, timeout=15)
        resp.raise_for_status()

        ext = os.path.splitext(image_url)[-1].split('?')[0]
        if not ext or len(ext) > 5:
            ext = ".jpg"

        with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
            tmp.write(resp.content)
            tmp_path = tmp.name

        filename = os.path.basename(tmp_path)

        with open(tmp_path, 'rb') as img_file:
            media_headers = {
                'Content-Disposition': f'attachment; filename={filename}',
                'Content-Type': resp.headers.get('Content-Type', 'image/jpeg'),
            }
            upload_resp = session.post(WP_MEDIA_URL, headers=media_headers, data=img_file)
        os.remove(tmp_path)

        if upload_resp.status_code in (200, 201):
            media_data = upload_resp.json()
            new_url = media_data.get('source_url')
            if new_url:
                uploaded_images_cache[image_url] = new_url
                logging.info(f"Uploaded image to WordPress: {new_url}")
                return new_url
            else:
                logging.error(f"No source_url in media upload response for {image_url}")
                return None
        else:
            logging.error(f"WordPress media upload failed ({upload_resp.status_code}): {upload_resp.text}")
            return None

    except Exception as e:
        logging.error(f"WordPress image upload error for {image_url}: {e}")
        return None

    return None

def upload_featured_image(image_url):
    try:
        headers = {"User-Agent": random.choice(USER_AGENTS)}
        resp = requests.get(image_url, headers=headers, timeout=15)
        resp.raise_for_status()

        ext = os.path.splitext(image_url)[-1].split('?')[0]
        if not ext or len(ext) > 5:
            ext = ".jpg"

        with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
            tmp.write(resp.content)
            tmp_path = tmp.name

        filename = os.path.basename(tmp_path)

        with open(tmp_path, 'rb') as img_file:
            media_headers = {
                'Content-Disposition': f'attachment; filename={filename}',
                'Content-Type': resp.headers.get('Content-Type', 'image/jpeg'),
            }
            upload_resp = session.post(WP_MEDIA_URL, headers=media_headers, data=img_file)
        os.remove(tmp_path)

        if upload_resp.status_code in (200, 201):
            media_data = upload_resp.json()
            media_id = media_data.get('id')
            if media_id:
                logging.info(f"Uploaded featured image with media ID: {media_id}")
                return media_id
            else:
                logging.error(f"No media ID in featured image upload response for {image_url}")
                return None
        else:
            logging.error(f"Featured image upload failed ({upload_resp.status_code}): {upload_resp.text}")
            return None

    except Exception as e:
        logging.error(f"Featured image upload error for {image_url}: {e}")
        return None

def get_or_create_category(cat_name):
    try:
        response = session.get(WP_CATEGORIES_URL, params={"search": cat_name})
        data = response.json()
        for cat in data:
            if cat['name'].lower() == cat_name.lower():
                return cat['id']
        response = session.post(WP_CATEGORIES_URL, json={"name": cat_name})
        if response.status_code == 201:
            return response.json()['id']
    except Exception as e:
        logging.error(f"Category error: {e}")
    return None

def extract_categories(article_tag):
    class_list = article_tag.get('class', [])
    categories = []
    for cls in class_list:
        if cls.startswith('category-'):
            clean_cat = cls.replace('category-', '').replace('-', ' ').strip().title()
            categories.append(clean_cat)
    return list(set(categories))

def extract_breadcrumb_category(soup):
    categories = []
    bc = soup.select_one('div.nav-breadcrumbs-wrap span#dle-speedbar')
    if bc:
        links = bc.select('a span[itemprop="title"]')
        if len(links) >= 2:
            categories.append(links[-1].text.strip())
    return categories

def upload_to_wordpress(post_data, featured_media_id=None):
    wp_post_data = {
        'title': post_data['title'],
        'content': post_data['content'],
        'status': 'publish',
        'date': post_data.get('published_date'),
    }

    if featured_media_id:
        wp_post_data['featured_media'] = featured_media_id

    cat_ids = []
    for cat_name in post_data.get('categories', []):
        cat_id = get_or_create_category(cat_name)
        if cat_id:
            cat_ids.append(cat_id)
    if cat_ids:
        wp_post_data['categories'] = cat_ids

    try:
        auth_header = base64.b64encode(f"{WP_USERNAME}:{WP_PASSWORD}".encode('utf-8')).decode('utf-8')
        headers = {'Authorization': f'Basic {auth_header}', 'Content-Type': 'application/json'}
        response = session.post(WP_API_URL, json=wp_post_data, headers=headers)
        if response.status_code == 201:
            logging.info(f"Uploaded post: {post_data['title']}")
        else:
            logging.error(f"Upload failed for post: {post_data['title']} | {response.status_code} {response.text}")
    except Exception as e:
        logging.error(f"Upload error for post {post_data['title']}: {e}")

def scrape_page(url):
    response = fetch_url(url)
    if not response:
        return []
    soup = BeautifulSoup(response.content, 'html.parser')
    posts = []
    for article in soup.select('article.post-item'):
        try:
            post_link = article.select_one('a.blog-img')['href']
            post_title = article.select_one('h3.entry-title a').text.strip()
            categories = extract_categories(article)
            posts.append({'link': post_link, 'title': post_title, 'categories': categories})
        except Exception as e:
            logging.warning(f"Post parse error: {e}")
    return posts

def process_all_images_and_cleanup(content_html, post_url):
    soup = BeautifulSoup(content_html, 'html.parser')

    # Remove unwanted tags
    for tag in soup.select('.entry-meta, .emoji, img.emoji'):
        tag.decompose()

    # Remove ins tags
    for ins_tag in soup.find_all('ins'):
        ins_tag.decompose()

    # Remove elements with class 'code-block'
    for code_block in soup.select('.code-block'):
        code_block.decompose()

    # Process images
    imgs = soup.find_all('img')

    image_upload_failed = False
    for img in imgs:
        src = img.get('src', '')
        if src.startswith('/uploads/') or src.startswith('/wp-content/uploads/') or src.startswith('https://dotmovies.ac'):
            full_url = src if src.startswith('http') else f"https://dotmovies.ac{src}"
            new_url = upload_image_to_wordpress(full_url)
            if new_url is None:
                image_upload_failed = True
                break
            img['src'] = new_url

    if image_upload_failed:
        return None  # Discard post if any image upload fails

    # Fix anchor hrefs pointing to dotmovies.diy or begamovies.in domain
    for a in soup.find_all('a', href=True):
        href = a['href']
        if 'dotmovies.diy' in href or 'vegamovies.mk' in href:
            a['href'] = '/'

    return str(soup)

def scrape_post(post_url):
    response = fetch_url(post_url)
    if not response:
        return None
    soup = BeautifulSoup(response.content, 'html.parser')

    # Extract og:image for featured image
    og_image_tag = soup.find('meta', property='og:image')
    featured_image_url = og_image_tag['content'] if og_image_tag and og_image_tag.get('content') else None

    content_div = soup.select_one('div.entry-content')
    if not content_div:
        return None

    processed_content = process_all_images_and_cleanup(str(content_div), post_url)
    if processed_content is None:
        return None  # Image upload failed, discard post

    post_title = soup.select_one('h1.entry-title').text.strip() if soup.select_one('h1.entry-title') else "No Title"

    published_date = None
    pd_tag = soup.select_one('.date-time .entry-date')
    if pd_tag:
        try:
            published_date = parser.parse(pd_tag.text.strip()).isoformat()
        except Exception:
            pass

    categories = extract_breadcrumb_category(soup)

    # Upload og:image to WordPress media and get media ID for featured_media
    featured_media_id = None
    if featured_image_url:
        featured_media_id = upload_featured_image(featured_image_url)
        # No need to inject featured image in content, just use featured_media_id

    # Log concise info only
    snippet = processed_content[:200].replace('\n', ' ').strip()
    logging.info(f"Scraped post '{post_title}' with content snippet: {snippet}...")

    return {
        'title': post_title,
        'content': processed_content,
        'published_date': published_date,
        'categories': categories,
        'featured_media_id': featured_media_id  # Use this for featured_media field
    }

def scrape_and_upload_post(post, existing_titles, lock):
    try:
        with lock:
            if post['title'] in existing_titles:
                logging.info(f"Skipping existing post: {post['title']}")
                return
            existing_titles.add(post['title'])

        post_data = scrape_post(post['link'])
        if post_data:
            if not post_data['categories']:
                post_data['categories'] = post['categories']

            # Only upload if all images uploaded successfully
            upload_to_wordpress(post_data, featured_media_id=post_data.get('featured_media_id'))
    except Exception as e:
        logging.error(f"Error processing post '{post.get('title')}': {e}")

def main():
    base_url = "https://vegamovies.mk/"
    start_page = 1
    end_page = 200

    existing_titles = fetch_existing_titles()
    existing_titles_lock = threading.Lock()
    logging.info(f"Starting scraping pages {start_page} to {end_page}")

    for page in range(start_page, end_page + 1):
        page_url = f"{base_url}page/{page}/"
        logging.info(f"Scraping page {page}: {page_url}")
        posts = scrape_page(page_url)
        logging.info(f"Page {page} contains {len(posts)} posts")

        # Threaded post processing with 10 workers
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            futures = []
            for post in posts:
                futures.append(executor.submit(scrape_and_upload_post, post, existing_titles, existing_titles_lock))
            for future in concurrent.futures.as_completed(futures):
                try:
                    future.result()
                except Exception as e:
                    logging.error(f"Error in threaded post processing: {e}")

        logging.info("Waiting 2 seconds before next page...")
        sleep(2)

if __name__ == "__main__":
    main()
