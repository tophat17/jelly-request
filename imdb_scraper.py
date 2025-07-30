"""
IMDb scraping functionality for Jelly Request application.
Handles web scraping of IMDb's most popular movies chart.
"""

import requests
import json
from bs4 import BeautifulSoup
from config import IMDB_URL, MOVIE_LIMIT, logger
from utils import normalize_title

def scrape_imdb_top_movies(limit=MOVIE_LIMIT):
    """
    Scrape top movies from IMDb's most popular movies chart.
    
    Args:
        limit (int): Maximum number of movies to scrape
        
    Returns:
        list: List of movie titles
    """
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
        
        # Try JSON-LD structured data first
        movies = _extract_from_json_ld(soup, limit)
        if movies:
            return movies
            
        # Fallback to HTML scraping
        return _extract_from_html(soup, limit)
        
    except Exception as e:
        logger.error(f"Error scraping IMDb: {e}")
        print(f"❌ Error scraping IMDb: {e}")
        return []

def _extract_from_json_ld(soup, limit):
    """Extract movie titles from JSON-LD structured data."""
    json_ld = soup.find("script", type="application/ld+json")
    if not json_ld:
        return []
        
    try:
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
    except (json.JSONDecodeError, KeyError) as e:
        logger.debug(f"Failed to parse JSON-LD data: {e}")
        
    return []

def _extract_from_html(soup, limit):
    """Extract movie titles from HTML elements as fallback."""
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
