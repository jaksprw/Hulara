import asyncio
import aiohttp
from aiohttp import ClientSession
from bs4 import BeautifulSoup
import base64
import datetime
import xml.etree.ElementTree as ET
import logging
import warnings
import urllib3
import async_timeout

warnings.filterwarnings("ignore", category=urllib3.exceptions.InsecureRequestWarning)

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

WP_API_URL = "https://unpackpickle.s6-tastewp.com/wp-json/wp/v2/posts"
WP_CATEGORIES_URL = "https://unpackpickle.s6-tastewp.com/wp-json/wp/v2/categories"
WP_TAGS_URL = "https://unpackpickle.s6-tastewp.com/wp-json/wp/v2/tags"

WP_USERNAME = "admin"
WP_PASSWORD = "7yE7 95v9 2sm6 5l56 fbPB twGq"

AUTH_HEADER = {
    'Authorization': 'Basic ' + base64.b64encode(f"{WP_USERNAME}:{WP_PASSWORD}".encode()).decode(),
    'Content-Type': 'application/json'
}

SITEMAP_URLS = [
   "https://deephot.link/post-sitemap9.xml",
      "https://deephot.link/post-sitemap8.xml",
       "https://deephot.link/post-sitemap7.xml",
     "https://deephot.link/post-sitemap6.xml",
    "https://deephot.link/post-sitemap5.xml",
     "https://deephot.link/post-sitemap4.xml",  
      "https://deephot.link/post-sitemap3.xml",
       "https://deephot.link/post-sitemap2.xml",
]

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64)...",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)..."
]

category_cache = {}
tag_cache = {}

async def fetch(session: ClientSession, url: str, method='GET', retries=3, **kwargs):
    headers = kwargs.pop('headers', {})
    headers['User-Agent'] = kwargs.pop('user_agent', USER_AGENTS[0])
    for attempt in range(1, retries+1):
        try:
            async with async_timeout.timeout(15):
                async with session.request(method, url, headers=headers, ssl=False, **kwargs) as response:
                    response.raise_for_status()
                    if method == 'GET':
                        return await response.text()
                    else:
                        return await response.json()
        except Exception as e:
            logging.warning(f"Attempt {attempt} failed for {url}: {e}")
            await asyncio.sleep(2 * attempt)  # exponential backoff
    logging.error(f"All {retries} attempts failed for {url}")
    return None

async def get_urls_from_sitemap(session, sitemap_url):
    text = await fetch(session, sitemap_url)
    if not text:
        return []
    root = ET.fromstring(text)
    namespace = {'ns': 'http://www.sitemaps.org/schemas/sitemap/0.9'}
    urls = [url.find('ns:loc', namespace).text for url in root.findall('ns:url', namespace) if url.find('ns:loc', namespace) is not None]
    logging.info(f"Found {len(urls)} URLs in sitemap {sitemap_url}")
    return urls

async def get_or_create_category(session, category_name):
    if not category_name:
        return None
    if category_name in category_cache:
        return category_cache[category_name]
    search_url = f"{WP_CATEGORIES_URL}?search={category_name}"
    categories = await fetch(session, search_url, headers=AUTH_HEADER)
    if categories:
        import json
        cats = json.loads(categories)
        for cat in cats:
            if cat['name'].lower() == category_name.lower():
                category_cache[category_name] = cat['id']
                return cat['id']
    data = {'name': category_name}
    created = await fetch(session, WP_CATEGORIES_URL, method='POST', headers=AUTH_HEADER, json=data)
    if created and 'id' in created:
        category_cache[category_name] = created['id']
        return created['id']
    return None

async def get_or_create_tag(session, tag_name):
    if not tag_name:
        return None
    if tag_name in tag_cache:
        return tag_cache[tag_name]
    search_url = f"{WP_TAGS_URL}?search={tag_name}"
    tags = await fetch(session, search_url, headers=AUTH_HEADER)
    if tags:
        import json
        tag_list = json.loads(tags)
        for t in tag_list:
            if t['name'].lower() == tag_name.lower():
                tag_cache[tag_name] = t['id']
                return t['id']
    data = {'name': tag_name}
    created = await fetch(session, WP_TAGS_URL, method='POST', headers=AUTH_HEADER, json=data)
    if created and 'id' in created:
        tag_cache[tag_name] = created['id']
        return created['id']
    return None

async def scrape_post(session, url):
    html = await fetch(session, url)
    if not html:
        return None
    soup = BeautifulSoup(html, 'html.parser')

    title_tag = soup.select_one('h1.entry-title[itemprop="name"]')
    title = title_tag.get_text(strip=True) if title_tag else None
    if not title:
        logging.warning(f"No title found for {url}")
        return None

    desc_div = soup.select_one('div.video-description div.desc')
    description_html = str(desc_div) if desc_div else ""

    date_div = soup.select_one('div#video-date')
    post_date = None
    if date_div:
        date_text = date_div.get_text(strip=True).replace('Date:', '').strip()
        try:
            post_date = datetime.datetime.strptime(date_text, '%B %d, %Y').isoformat()
        except Exception:
            post_date = None

    actress_div = soup.select_one('div#video-actors a')
    category = actress_div.get_text(strip=True) if actress_div else None

    tag_links = soup.select('div.tags-list a.label')
    tags = [tag.get_text(strip=True) for tag in tag_links]

    meta_thumb = soup.select_one('div.video-player meta[itemprop="thumbnailUrl"]')
    featured_image_url = meta_thumb['content'] if meta_thumb else None

    meta_video = soup.select_one('div.video-player meta[itemprop="contentURL"]')
    video_url = meta_video['content'] if meta_video else None

    video_iframe_html = f'<iframe src="{video_url}" frameborder="0" allowfullscreen></iframe>' if video_url else ''
    featured_img_html = f'<img class="featured-image" src="{featured_image_url}" alt="{title}"/>' if featured_image_url else ''

    content_html = video_iframe_html + featured_img_html + description_html

    return {
        'title': title,
        'content': content_html,
        'category': category,
        'tags': tags,
        'published_date': post_date,
    }

async def upload_post(session, post_data):
    category_id = await get_or_create_category(session, post_data['category']) if post_data.get('category') else None

    tag_ids = []
    for tag in post_data.get('tags', []):
        tag_id = await get_or_create_tag(session, tag)
        if tag_id:
            tag_ids.append(tag_id)

    wp_post_data = {
        'title': post_data['title'],
        'content': post_data['content'],
        'status': 'private',
        'date': post_data.get('published_date'),
        'categories': [category_id] if category_id else [],
        'tags': tag_ids,
    }

    async with session.post(WP_API_URL, json=wp_post_data, headers=AUTH_HEADER, ssl=False) as resp:
        if resp.status in [200, 201]:
            logging.info(f"Uploaded: {post_data['title']}")
        else:
            text = await resp.text()
            logging.error(f"Failed to upload {post_data['title']}: {resp.status} {text}")

async def main():
    async with aiohttp.ClientSession() as session:
        all_urls = []
        for sitemap_url in SITEMAP_URLS:
            urls = await get_urls_from_sitemap(session, sitemap_url)
            all_urls.extend(urls)

        sem = asyncio.Semaphore(15)  # concurrency limit reduced for slower but reliable posting

        async def sem_task(url):
            async with sem:
                post_data = await scrape_post(session, url)
                if post_data:
                    await upload_post(session, post_data)
                    await asyncio.sleep(1)  # 1 second delay between posts to reduce load

        tasks = [asyncio.create_task(sem_task(url)) for url in all_urls]
        await asyncio.gather(*tasks)

if __name__ == "__main__":
    asyncio.run(main())
