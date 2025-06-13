import requests
from bs4 import BeautifulSoup
import random
import logging
import base64
import json
import mimetypes
from dateutil import parser
from concurrent.futures import ThreadPoolExecutor, as_completed

# Logging Setup
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# WordPress API
WP_API_URL = "https://dktechnozone.shop/wp-json/wp/v2/posts"
WP_MEDIA_URL = "https://dktechnozone.shop/wp-json/wp/v2/media"
WP_CATEGORIES_URL = "https://dktechnozone.shop/wp-json/wp/v2/categories"
WP_TAGS_URL = "https://dktechnozone.shop/wp-json/wp/v2/tags"

WP_USERNAME = "Dktczn"
WP_PASSWORD = "IAFM Rvvf XDQx fTWs FYVu gUZ5"

# User-Agent List
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
]

# Session Setup
session = requests.Session()
session.auth = requests.auth.HTTPBasicAuth(WP_USERNAME, WP_PASSWORD)

# Authentication Header
AUTH_HEADER = {
    'Authorization': f'Basic {base64.b64encode(f"{WP_USERNAME}:{WP_PASSWORD}".encode()).decode()}',
    'Content-Type': 'application/json'
}

# Function to Fetch URL Content
def fetch_url(url):
    for attempt in range(3):
        try:
            headers = {"User-Agent": random.choice(USER_AGENTS)}
            response = session.get(url, headers=headers, timeout=10)
            response.raise_for_status()
            return response
        except requests.exceptions.RequestException as e:
            logging.warning(f"Retrying {url} after {2 ** attempt} seconds (Attempt {attempt + 1}): {e}")
    logging.error(f"Failed to fetch URL: {url}")
    return None

# Function to Fetch Existing Titles
def fetch_existing_titles():
    existing_titles = set()
    page = 1
    while True:
        response = session.get(WP_API_URL, params={"per_page": 100, "page": page})
        if response.status_code != 200 or not response.json():
            break
        for post in response.json():
            existing_titles.add(post['title']['rendered'].strip())
        page += 1
    logging.info(f"Fetched {len(existing_titles)} existing post titles.")
    return existing_titles

# Function to Scrape a Single Post
def scrape_post(post_url):
    response = fetch_url(post_url)
    if not response:
        return None

    soup = BeautifulSoup(response.content, 'html.parser')

    title_tag = soup.select_one('h1')
    content_div = soup.select_one('div.entry-content')
    category_tag = soup.select_one('.cat-links a')
    tag_tags = soup.select('.tags-links a')

    if not title_tag or not content_div:
        return None

    title = title_tag.get_text(strip=True)
    category = category_tag.get_text(strip=True) if category_tag else "Uncategorized"
    tags = [tag.get_text(strip=True) for tag in tag_tags] if tag_tags else []

    time_tag = soup.select_one('time.entry-date.published')
    post_date = time_tag['datetime'] if time_tag else None

    for unwanted_selector in ['.rajudigitalservices-in-article-posts', '.related-posts-container', '.code-block' ,'.wp-code-block-embed', '.Teckshop-related-post', '.Teckshop-related-posts', '#ez-toc-container', '.ez-toc-v2_0_73c', '.ez-toc-title-container',  'figure', '.heateor_sss_sharing_container', '#rank-math-toc', '.wp-block-image']:  # Add selectors for unwanted widgets
        for element in content_div.select(unwanted_selector):
            element.decompose()

    img_tag = soup.select_one('.featured-image img, .entry-content img')
    featured_image = img_tag.get('data-src') or img_tag.get('src') if img_tag else None

    return {
        'title': title,
        'content': str(content_div),
        'category': category,
        'tags': tags,
        'featured_image': featured_image,
        'published_date': post_date
    }

# Function to Upload Image to WordPress
def upload_image_to_wordpress(image_url):
    response = fetch_url(image_url)
    if not response or response.status_code != 200:
        return None

    filename = image_url.split("/")[-1].split("?")[0]
    mime_type, _ = mimetypes.guess_type(filename)

    if not mime_type:
        mime_type = "image/jpeg"

    files = {'file': (filename, response.content, mime_type)}
    upload_response = session.post(WP_MEDIA_URL, headers={'Authorization': AUTH_HEADER['Authorization']}, files=files)

    if upload_response.status_code == 201:
        return upload_response.json().get('id')
    return None

# Function to Handle Categories
def get_or_create_category(category_name):
    response = session.get(WP_CATEGORIES_URL, headers=AUTH_HEADER, params={"search": category_name})
    if response.status_code == 200 and response.json():
        return response.json()[0]['id']

    category_data = {"name": category_name}
    response = session.post(WP_CATEGORIES_URL, headers=AUTH_HEADER, json=category_data)
    if response.status_code == 201:
        return response.json()['id']
    return None

# Function to Handle Tags
def get_or_create_tags(tag_names):
    tag_ids = []
    for tag in tag_names:
        response = session.get(WP_TAGS_URL, headers=AUTH_HEADER, params={"search": tag})
        if response.status_code == 200 and response.json():
            tag_ids.append(response.json()[0]['id'])
        else:
            tag_data = {"name": tag}
            response = session.post(WP_TAGS_URL, headers=AUTH_HEADER, json=tag_data)
            if response.status_code == 201:
                tag_ids.append(response.json()['id'])
    return tag_ids

# Function to Upload Post to WordPress
def upload_to_wordpress(post_data):
    category_id = get_or_create_category(post_data['category']) if post_data.get('category') else None
    tag_ids = get_or_create_tags(post_data['tags']) if post_data.get('tags') else []

    media_id = None
    if post_data.get('featured_image'):
        media_id = upload_image_to_wordpress(post_data['featured_image'])

    wp_post_data = {
        'title': post_data['title'],
        'content': post_data['content'],
        'status': 'publish',
        'date': post_data.get('published_date'),
        'categories': [category_id] if category_id else [],
        'tags': tag_ids,
        'featured_media': media_id if media_id else None
    }

    response = session.post(WP_API_URL, json=wp_post_data, headers=AUTH_HEADER)
    if response.status_code == 201:
        logging.info(f"Post uploaded successfully: {post_data['title']}")
    else:
        logging.error(f"Failed to upload post: {post_data['title']}. Response: {response.text}")

# Multi-threaded Scraping
def main():
    base_url = "https://aarshahospitality.com/category/automobile/"
    existing_titles = fetch_existing_titles()
    post_urls = []

    for page in range(1, 300):
        response = fetch_url(f"{base_url}page/{page}/")
        if not response:
            break

        soup = BeautifulSoup(response.content, 'html.parser')
        articles = soup.select('article h2 a')

        for a in articles:
            post_urls.append(a['href'])

    with ThreadPoolExecutor(max_workers=15) as executor:
        futures = {executor.submit(scrape_post, url): url for url in post_urls}
        for future in as_completed(futures):
            post_data = future.result()
            if post_data and post_data['title'] not in existing_titles:
                upload_to_wordpress(post_data)
                existing_titles.add(post_data['title'])

if __name__ == "__main__":
    main()
