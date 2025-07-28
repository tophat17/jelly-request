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
JELLYSEERR_URL = os.environ.get('JELLYSEERR_URL', 'http://192.168.0.29:5054')  # Default if not set
API_KEY = os.environ.get('API_KEY', 'MTY3MzkzMTU4MjI1NzNmZWQ4OGQ1LWQ1NDMtNDY0OC1hYzI3LWQ3ODAyMTM5OWUwNyk=')  # Default if not set
IMDB_URL = os.environ.get('IMDB_URL', 'https://www.imdb.com/chart/moviemeter')  # Default if not set
MOVIE_LIMIT = int(os.environ.get('MOVIE_LIMIT', 50))  # Default to 50 if not set
RUN_INTERVAL_DAYS = int(os.environ.get('RUN_INTERVAL_DAYS', 7))  # Default to every 7 days
DEBUG_MODE = os.environ.get('DEBUG_MODE', 'SIMPLE').upper()  # Default to SIMPLE (SIMPLE or VERBOSE)
IS_4K_REQUEST = os.environ.get('IS_4K_REQUEST', 'true').lower() == 'true'  # New 4K toggle
LOG_FILE = "/logs/imdb_jellyseerr.log"  # Fixed path for container logs

# Setup logging
logging_level = logging.DEBUG if DEBUG_MODE == 'VERBOSE' else logging.INFO
logger = logging.getLogger(__name__)
logger.setLevel(logging_level)

# File handler
file_handler = logging.FileHandler(LOG_FILE)
file_handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
logger.addHandler(file_handler)

# Console handler to duplicate logs to stdout
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
logger.addHandler(console_handler)

def normalize_title(title):
    """Normalize titles by removing special characters, spaces, and numbers."""
    if not title:
        return ""
    # Remove special characters, keep letters and numbers
    title = re.sub(r'[^\w\s]', '', title.lower())
    # Remove extra spaces
    title = ' '.join(title.split())
    return title

def scrape_imdb_top_movies(limit=MOVIE_LIMIT):
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
        }
        response = requests.get(IMDB_URL, headers=headers, timeout=(5, 10))
        logger.debug(f"IMDb response status: {response.status_code}")
        logger.debug(f"IMDb response snippet: {response.text[:500]}")
        print(f"IMDb response status: {response.status_code}")
        if response.status_code != 200:
            logger.error(f"Failed to fetch IMDb chart: {response.status_code}")
            print(f"❌ Failed to fetch IMDb chart: {response.status_code}")
            return []

        soup = BeautifulSoup(response.text, "html.parser")
        # Try JSON-LD structured data
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
                logger.info(f"Scraped {len(movies)} unique movies from JSON-LD: {movies}")
                print(f"Scraped {len(movies)} unique movies from JSON-LD: {movies}")
                return movies

        # Fallback to HTML scraping
        movie_elements = soup.select("ul.ipc-metadata-list li.ipc-metadata-list-summary-item a h3")
        logger.debug(f"Found {len(movie_elements)} movie elements before slicing")
        print(f"Found {len(movie_elements)} movie elements before slicing")
        movie_elements = movie_elements[:limit]
        if not movie_elements:
            logger.error("No movie elements found with selector")
            print(f"❌ No movie elements found with selector")
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
        logger.info(f"Scraped {len(movies)} unique movies from HTML: {movies}")
        print(f"Scraped {len(movies)} unique movies from HTML: {movies}")
        return movies
    except Exception as e:
        logger.error(f"Error scraping IMDb: {e}")
        print(f"❌ Error scraping IMDb: {e}")
        return []

def search_jellyseerr(movie_name, max_retries=3):
    headers = {"X-Api-Key": API_KEY, "Connection": "close"}
    encoded_query = urllib.parse.quote(movie_name, safe='')
    logger.debug(f"Searching Jellyseerr for '{movie_name}' with encoded query: {encoded_query}")
    start_time = datetime.now()
    for attempt in range(1, max_retries + 1):
        try:
            with requests.Session() as session:
                retries = Retry(total=3, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504])
                session.mount('http://', HTTPAdapter(max_retries=retries))
                session.mount('https://', HTTPAdapter(max_retries=retries))
                logger.debug(f"Attempt {attempt} for '{movie_name}': Sending request...")
                res = session.get(f"{JELLYSEERR_URL}/api/v1/search", params={"query": encoded_query}, headers=headers, timeout=(5, 15))
                logger.debug(f"Attempt {attempt} for '{movie_name}': Response received with status {res.status_code}")
                elapsed = (datetime.now() - start_time).total_seconds()
                logger.debug(f"Jellyseerr search for '{movie_name}' attempt {attempt} took {elapsed:.2f}s, headers: {res.headers}, response_size: {len(res.text)} bytes")
                if res.status_code != 200:
                    logger.error(f"Jellyseerr search failed for '{movie_name}' on attempt {attempt}: {res.text}")
                    print(f"❌ Jellyseerr search failed for '{movie_name}': {res.text}")
                    if attempt == max_retries:
                        logger.warning(f"Max retries reached for '{movie_name}', skipping")
                        print(f"❌ Max retries reached for '{movie_name}', skipping")
                        return None
                    continue
                logger.debug(f"Jellyseerr full response for '{movie_name}': {res.text[:500]}")
                if DEBUG_MODE == 'VERBOSE':
                    print(f"Jellyseerr response for '{movie_name}': {res.text[:500]}")
                return res.json()
        except requests.exceptions.RequestException as e:
            elapsed = (datetime.now() - start_time).total_seconds()
            logger.error(f"Error querying Jellyseerr for '{movie_name}' on attempt {attempt} after {elapsed:.2f}s: {e}")
            print(f"❌ Error querying Jellyseerr for '{movie_name}': {e}")
            if attempt == max_retries:
                logger.warning(f"Max retries reached for '{movie_name}', skipping")
                print(f"❌ Max retries reached for '{movie_name}', skipping")
                return None
            time.sleep(2 ** attempt)  # Exponential backoff
        except Exception as e:
            elapsed = (datetime.now() - start_time).total_seconds()
            logger.error(f"Unexpected error querying Jellyseerr for '{movie_name}' on attempt {attempt} after {elapsed:.2f}s: {e}")
            print(f"❌ Unexpected error querying Jellyseerr for '{movie_name}': {e}")
            if attempt == max_retries:
                logger.warning(f"Max retries reached for '{movie_name}', skipping")
                print(f"❌ Max retries reached for '{movie_name}', skipping")
                return None
            time.sleep(2 ** attempt)  # Exponential backoff
    return None

def get_movie_details(movie_name, json_data):
    if not json_data or "results" not in json_data:
        logger.error(f"No results in Jellyseerr response for '{movie_name}'")
        print(f"❌ No results in Jellyseerr response for '{movie_name}'")
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
                logger.warning(f"Skipping result for '{title}' (missing mediaId or title)")
                print(f"❌ Skipping '{title}' (missing mediaId or title)")
                continue
            logger.debug(f"Found movie: {title} (tmdbId: {tmdb_id}, imdbId: {imdb_id}, mediaId: {media_id})")
            if normalized_movie_name in normalized_title:
                logger.info(f"Found movie: '{movie_name}' (imdbId: {imdb_id}, mediaId: {media_id}, tmdbId: {tmdb_id})")
                print(f"✅ Found movie: '{movie_name}' (imdbId: {imdb_id}, mediaId: {media_id}, tmdbId: {tmdb_id})")
                return imdb_id, media_id, tmdb_id
    logger.warning(f"No matching movie found in Jellyseerr for '{movie_name}'")
    print(f"❌ No matching movie found in Jellyseerr for '{movie_name}'")
    return None, None, None

def make_request(tmdb_id, media_id):
    headers = {"X-Api-Key": API_KEY, "Connection": "close"}
    payload = {
        "mediaType": "movie",
        "tmdbId": tmdb_id,
        "mediaId": media_id,
        "is4k": IS_4K_REQUEST
    }
    logger.debug(f"Making request for tmdbId: {tmdb_id}, mediaId: {media_id}, payload: {json.dumps(payload)}")
    try:
        with requests.Session() as session:
            retries = Retry(total=3, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504])
            session.mount('http://', HTTPAdapter(max_retries=retries))
            session.mount('https://', HTTPAdapter(max_retries=retries))
            res = session.post(f"{JELLYSEERR_URL}/api/v1/request", json=payload, headers=headers, timeout=(5, 15))
            if res.status_code == 201:
                logger.info(f"Successfully requested movie (tmdbId: {tmdb_id}, mediaId: {media_id})")
                print(f"✅ Requested movie (tmdbId: {tmdb_id}, mediaId: {media_id})")
                return True, res.text
            else:
                logger.info(f"Request skipped for mediaId {media_id}: {res.text}")
                print(f"ℹ️ Request skipped for mediaId {media_id}: {res.text}")
                return False, res.text
    except requests.exceptions.RequestException as e:
        logger.error(f"Error requesting movie (tmdbId: {tmdb_id}, mediaId: {media_id}): {e}")
        print(f"❌ Error requesting movie: {e}")
        return False, str(e)
    except Exception as e:
        logger.error(f"Unexpected error requesting movie (tmdbId: {tmdb_id}, mediaId: {media_id}): {e}")
        print(f"❌ Unexpected error requesting movie: {e}")
        return False, str(e)

# === MAIN ===
def main():
    logger.info(f"Starting IMDb to Jellyseerr sync, configured to run every {RUN_INTERVAL_DAYS} day(s)")
    print(f"Configured to run every {RUN_INTERVAL_DAYS} day(s)")
    
    while True:
        try:
            print("Scraping IMDb's Top Movies of the Week...")
            top_movies = scrape_imdb_top_movies()
            if not top_movies:
                logger.error("No movies found from IMDb")
                print("❌ No movies found.")
            else:
                logger.info(f"Scraped {len(top_movies)} unique movies")
                print(f"\n✅ Top Movies of the Week (Total: {len(top_movies)}):")
                for i, movie in enumerate(top_movies, 1):
                    print(f"{i}. {movie}")

                print("\nRequesting movies in Jellyseerr...")
                for i, movie in enumerate(top_movies, 1):
                    print(f"\nProcessing '{movie}' ({i}/{len(top_movies)})...")
                    try:
                        json_data = search_jellyseerr(movie)
                        imdb_id, media_id, tmdb_id = get_movie_details(movie, json_data)
                        if media_id:
                            success, msg = make_request(tmdb_id, media_id)
                            if not success and "Request for this media already exists" not in msg:
                                logger.error(f"Failed to request '{movie}': {msg}")
                                print(f"❌ Failed to request '{movie}': {msg}")
                    except Exception as e:
                        logger.error(f"Error processing movie '{movie}': {e}")
                        print(f"❌ Error processing movie '{movie}': {e}")
                        continue  # Continue to next movie
        except Exception as e:
            logger.error(f"Unexpected error in main loop: {e}")
            print(f"❌ Unexpected error: {e}")
        finally:
            logger.info(f"Completed run, sleeping for {RUN_INTERVAL_DAYS} day(s)")
            print(f"ℹ️ Completed run, sleeping for {RUN_INTERVAL_DAYS} day(s)")
            time.sleep(RUN_INTERVAL_DAYS * 24 * 60 * 60)  # Sleep for specified days

if __name__ == "__main__":
    main()
