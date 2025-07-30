import requests
from bs4 import BeautifulSoup
import urllib.parse
import sys
import json
import logging
import re
import os
import time
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry
from datetime import datetime

# === CONFIG ===
JELLYSEERR_URL = os.environ.get('JELLYSEERR_URL', 'http://192.168.0.29:5054')
API_KEY = os.environ.get('API_KEY', 'MTY3MzkzMTU4MjI1NzNmZWQ4OGQ1LWQ1NDMtNDY0OC1hYzI3LWQ3ODAyMTM5OWUwNyk=')
IMDB_URL = os.environ.get('IMDB_URL', 'https://www.imdb.com/chart/moviemeter')
MOVIE_LIMIT = int(os.environ.get('MOVIE_LIMIT', 50))
RUN_INTERVAL_DAYS = int(os.environ.get('RUN_INTERVAL_DAYS', 7))
DEBUG_MODE = os.environ.get('DEBUG_MODE', 'SIMPLE').upper()
IS_4K_REQUEST = os.environ.get('IS_4K_REQUEST', 'true').lower() == 'true'  # New 4K toggle
LOG_FILE = "/logs/imdb_jellyseerr.log"

# Setup logging
logging_level = logging.DEBUG if DEBUG_MODE == 'VERBOSE' else logging.INFO
logger = logging.getLogger(__name__)
logger.setLevel(logging_level)

file_handler = logging.FileHandler(LOG_FILE)
file_handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
logger.addHandler(file_handler)

console_handler = logging.StreamHandler(sys.stdout)
console_handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
logger.addHandler(console_handler)

def normalize_title(title):
    if not title:
        return ""
    title = re.sub(r'[^\w\s]', '', title.lower())
    title = ' '.join(title.split())
    return title

def scrape_imdb_top_movies(limit=MOVIE_LIMIT):
    try:
        headers = {
            "User-Agent": "Mozilla/5.0"
        }
        response = requests.get(IMDB_URL, headers=headers, timeout=(5, 10))
        logger.debug(f"IMDb response status: {response.status_code}")
        if response.status_code != 200:
            logger.error(f"Failed to fetch IMDb chart: {response.status_code}")
            return []

        soup = BeautifulSoup(response.text, "html.parser")
        json_ld = soup.find("script", type="application/ld+json")
        if json_ld:
            json_data = json.loads(json_ld.string)
            movies = []
            seen_titles = set()
            if "itemListElement" in json_data:
                for item in json_data["itemListElement"]:
                    title = item.get("item", {}).get("name")
                    if title:
                        norm_title = normalize_title(title)
                        if norm_title and norm_title not in seen_titles:
                            movies.append(title)
                            seen_titles.add(norm_title)
                    if len(movies) >= limit:
                        break
                logger.info(f"Scraped {len(movies)} movies from JSON-LD")
                return movies

        movie_elements = soup.select("ul.ipc-metadata-list li.ipc-metadata-list-summary-item a h3")
        movie_elements = movie_elements[:limit]
        if not movie_elements:
            logger.error("No movie elements found with selector")
            return []
        
        movies = []
        seen_titles = set()
        for element in movie_elements:
            title = element.get_text().strip().split(". ")[-1]
            if title:
                norm_title = normalize_title(title)
                if norm_title and norm_title not in seen_titles:
                    movies.append(title)
                    seen_titles.add(norm_title)
            if len(movies) >= limit:
                break
        logger.info(f"Scraped {len(movies)} movies from HTML")
        return movies
    except Exception as e:
        logger.error(f"Error scraping IMDb: {e}")
        return []

def search_jellyseerr(movie_name, max_retries=3):
    headers = {"X-Api-Key": API_KEY, "Connection": "close"}
    encoded_query = urllib.parse.quote(movie_name, safe='')
    start_time = datetime.now()
    for attempt in range(1, max_retries + 1):
        try:
            with requests.Session() as session:
                retries = Retry(total=3, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504])
                session.mount('http://', HTTPAdapter(max_retries=retries))
                session.mount('https://', HTTPAdapter(max_retries=retries))
                res = session.get(f"{JELLYSEERR_URL}/api/v1/search", params={"query": encoded_query}, headers=headers, timeout=(5, 15))
                if res.status_code != 200:
                    logger.warning(f"Jellyseerr search failed for '{movie_name}' on attempt {attempt}")
                    continue
                return res.json()
        except requests.exceptions.RequestException as e:
            logger.warning(f"Request error on attempt {attempt} for '{movie_name}': {e}")
            time.sleep(2 ** attempt)
    return None

def get_movie_details(movie_name, json_data):
    if not json_data or "results" not in json_data:
        return None, None, None
    normalized_movie_name = normalize_title(movie_name)
    for result in json_data["results"]:
        if result.get("mediaType") == "movie":
            title = result.get("title", "")
            normalized_title = normalize_title(title)
            imdb_id = result.get("mediaInfo", {}).get("imdbId") or result.get("imdbId")
            media_id = result.get("id")
            tmdb_id = result.get("tmdbId", media_id)
            if not media_id or not title:
                continue
            if normalized_movie_name in normalized_title:
                return imdb_id, media_id, tmdb_id
    return None, None, None

def make_request(tmdb_id, media_id):
    headers = {"X-Api-Key": API_KEY, "Connection": "close"}
    payload = {
        "mediaType": "movie",
        "tmdbId": tmdb_id,
        "mediaId": media_id,
        "is4k": IS_4K_REQUEST
    }
    try:
        with requests.Session() as session:
            retries = Retry(total=3, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504])
            session.mount('http://', HTTPAdapter(max_retries=retries))
            session.mount('https://', HTTPAdapter(max_retries=retries))
            res = session.post(f"{JELLYSEERR_URL}/api/v1/request", json=payload, headers=headers, timeout=(5, 15))
            if res.status_code == 201:
                logger.info(f"✅ Requested movie (tmdbId: {tmdb_id}, mediaId: {media_id}, is4k: {IS_4K_REQUEST})")
                return True, res.text
            else:
                logger.info(f"ℹ️ Request skipped for mediaId {media_id}: {res.text}")
                return False, res.text
    except requests.exceptions.RequestException as e:
        logger.error(f"Error requesting movie: {e}")
        return False, str(e)

def main():
    logger.info(f"Starting IMDb to Jellyseerr sync (4K request: {IS_4K_REQUEST}), running every {RUN_INTERVAL_DAYS} day(s)")
    while True:
        try:
            top_movies = scrape_imdb_top_movies()
            if not top_movies:
                logger.error("No movies found from IMDb")
            else:
                logger.info(f"Found {len(top_movies)} top movies")
                for i, movie in enumerate(top_movies, 1):
                    try:
                        logger.info(f"Processing ({i}/{len(top_movies)}): {movie}")
                        json_data = search_jellyseerr(movie)
                        imdb_id, media_id, tmdb_id = get_movie_details(movie, json_data)
                        if media_id:
                            success, msg = make_request(tmdb_id, media_id)
                            if not success and "Request for this media already exists" not in msg:
                                logger.error(f"❌ Failed to request '{movie}': {msg}")
                    except Exception as e:
                        logger.error(f"Exception for movie '{movie}': {e}")
        except Exception as e:
            logger.error(f"Unexpected error in main loop: {e}")
        finally:
            logger.info(f"Completed run, sleeping for {RUN_INTERVAL_DAYS} day(s)")
            time.sleep(RUN_INTERVAL_DAYS * 86400)

if __name__ == "__main__":
    main()
