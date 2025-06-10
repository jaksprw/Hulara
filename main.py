import requests
from bs4 import BeautifulSoup
import random
import logging
import base64
import json
import mimetypes
from dateutil import parser
from concurrent.futures import ThreadPoolExecutor, as_completed
import xml.etree.ElementTree as ET
import datetime
import urllib3

# Disable SSL warnings (since we're using verify=False)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Logging Setup
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# WordPress API
WP_API_URL = "https://lightsalmon-finch-839269.hostingersite.com/wp-json/wp/v2/posts"
WP_MEDIA_URL = "https://lightsalmon-finch-839269.hostingersite.com/wp-json/wp/v2/media"
WP_CATEGORIES_URL = "https://lightsalmon-finch-839269.hostingersite.com/wp-json/wp/v2/categories"
WP_TAGS_URL = "https://lightsalmon-finch-839269.hostingersite.com/wp-json/wp/v2/tags"

WP_USERNAME = "Deep@gmail.com"
WP_PASSWORD = "fE4n M8pz rpDg OBUN IlPs MfOE"

# User-Agent List
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64)...",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)..."
]

# Session Setup
session = requests.Session()
session.auth = requests.auth.HTTPBasicAuth(WP_USERNAME, WP_PASSWORD)

AUTH_HEADER = {
    'Authorization': f'Basic {base64.b64encode(f"{WP_USERNAME}:{WP_PASSWORD}".encode()).decode()}',
    'Content-Type': 'application/json'
}

def fetch_url(url):
    for attempt in range(3):
        try:
            headers = {"User-Agent": random.choice(USER_AGENTS)}
            # Added verify=False to bypass SSL certificate verification
            response = session.get(url, headers=headers, timeout=10, verify=False)
            response.raise_for_status()
            return response
        except Exception as e:
            logging.warning(f"Retrying {url} after {2**attempt}s (Attempt {attempt+1}): {e}")
    logging.error(f"Failed to fetch URL: {url}")
    return None

def fetch_existing_titles():
    existing_titles = set()
    page = 1
    while True:
        # Added verify=False here as well
        response = session.get(WP_API_URL, params={"per_page": 100, "page": page}, verify=False)
        if response.status_code != 200 or not response.json():
            break
        for post in response.json():
            existing_titles.add(post['title']['rendered'].strip())
        page += 1
    logging.info(f"Fetched {len(existing_titles)} existing post titles.")
    return existing_titles

def get_urls_from_sitemaps(sitemap_urls):
    all_urls = []
    for sitemap in sitemap_urls:
        response = fetch_url(sitemap)
        if not response:
            continue
        root = ET.fromstring(response.content)
        namespace = {'ns': 'http://www.sitemaps.org/schemas/sitemap/0.9'}
        for url in root.findall('ns:url', namespace):
            loc = url.find('ns:loc', namespace)
            if loc is not None:
                all_urls.append(loc.text)
    logging.info(f"Total {len(all_urls)} URLs fetched from sitemap(s).")
    return all_urls

def scrape_post(post_url):
    response = fetch_url(post_url)
    if not response:
        return None

    soup = BeautifulSoup(response.content, 'html.parser')

    # Title
    title_tag = soup.select_one('h1.entry-title[itemprop="name"]')
    title = title_tag.get_text(strip=True) if title_tag else None

    # Content (description)
    desc_div = soup.select_one('div.video-description div.desc')
    content_html = str(desc_div) if desc_div else ""

    # Date
    date_div = soup.select_one('div#video-date')
    post_date = None
    if date_div:
        # Date format: "Date: September 14, 2023"
        date_text = date_div.get_text(strip=True).replace('Date:', '').strip()
        try:
            post_date = datetime.datetime.strptime(date_text, '%B %d, %Y').isoformat()
        except Exception:
            post_date = None

    # Category (Actress name)
    actress_div = soup.select_one('div#video-actors a')
    category = actress_div.get_text(strip=True) if actress_div else "Uncategorized"

    # Tags
    tag_links = soup.select('div.tags-list a.label')
    tags = [tag.get_text(strip=True) for tag in tag_links]

    # Featured image from meta tag inside div.video-player
    meta_thumb = soup.select_one('div.video-player meta[itemprop="thumbnailUrl"]')
    featured_image_url = meta_thumb['content'] if meta_thumb else None

    # Video URL from meta tag contentURL
    meta_video = soup.select_one('div.video-player meta[itemprop="contentURL"]')
    video_url = meta_video['content'] if meta_video else None

    # Prepare featured image HTML to prepend in content (no media upload)
    featured_image_html = f'<img class="featured-image" src="{featured_image_url}" alt="{title}">' if featured_image_url else ''

    # Prepend video iframe or video URL embed at top of content
    video_embed_html = ''
    if video_url:
        video_embed_html = f'<video controls class="featured-video" src="{video_url}"></video>'

    # Final content with video and featured image at top
    final_content = video_embed_html + featured_image_html + content_html

    return {
        'title': title,
        'content': final_content,
        'category': category,
        'tags': tags,
        'published_date': post_date,
        # No featured_media upload, so omit or set None
        'featured_media': None
    }

def get_or_create_category(category_name):
    # Added verify=False
    response = session.get(WP_CATEGORIES_URL, headers=AUTH_HEADER, params={"search": category_name}, verify=False)
    if response.status_code == 200 and response.json():
        # Check if the category name matches exactly
        for cat in response.json():
            if cat['name'] == category_name:
                return cat['id']
    # If the category doesn't exist, create it
    category_data = {"name": category_name}
    # Added verify=False
    response = session.post(WP_CATEGORIES_URL, headers=AUTH_HEADER, json=category_data, verify=False)
    if response.status_code == 201:
        return response.json()['id']
    return None

def get_or_create_tags(tag_names):
    tag_ids = []
    for tag in tag_names:
        # Added verify=False
        response = session.get(WP_TAGS_URL, headers=AUTH_HEADER, params={"search": tag}, verify=False)
        if response.status_code == 200 and response.json():
            # Check if the tag name matches exactly
            for t in response.json():
                if t['name'] == tag:
                    tag_ids.append(t['id'])
                    break  # Tag found, move to the next tag
            else:
                # Tag not found, create it
                tag_data = {"name": tag}
                # Added verify=False
                response = session.post(WP_TAGS_URL, headers=AUTH_HEADER, json=tag_data, verify=False)
                if response.status_code == 201:
                    tag_ids.append(response.json()['id'])
        else:
            # Tag not found, create it
            tag_data = {"name": tag}
            # Added verify=False
            response = session.post(WP_TAGS_URL, headers=AUTH_HEADER, json=tag_data, verify=False)
            if response.status_code == 201:
                tag_ids.append(response.json()['id'])
    return tag_ids

def upload_to_wordpress(post_data):
    category_name = post_data['category']
    category_id = get_or_create_category(category_name) if post_data.get('category') else None
    tag_ids = get_or_create_tags(post_data['tags']) if post_data.get('tags') else []

    wp_post_data = {
        'title': post_data['title'],
        'content': post_data['content'],
        'status': 'publish',
        'date': post_data.get('published_date'),
        'categories': [category_id] if category_id else [],
        'tags': tag_ids,
    }

    # Added verify=False
    response = session.post(WP_API_URL, json=wp_post_data, headers=AUTH_HEADER, verify=False)
    if response.status_code == 201:
        logging.info(f"Uploaded: {post_data['title']}")
    else:
        logging.error(f"Failed: {post_data['title']}, Response: {response.text}")

def main():
    sitemap_urls = [    
    "https://deephot.link/post-sitemap7.xml"
    ]
    existing_titles = fetch_existing_titles()
    post_urls = get_urls_from_sitemaps(sitemap_urls)

    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = {executor.submit(scrape_post, url): url for url in post_urls}
        for future in as_completed(futures):
            post_data = future.result()
            if post_data and post_data['title'] not in existing_titles:
                upload_to_wordpress(post_data)
                existing_titles.add(post_data['title'])

if __name__ == "__main__":
    main()
