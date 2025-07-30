"""
Jellyseerr API client for Jelly Request application.
Handles all interactions with the Jellyseerr API including search and requests.
"""

import urllib.parse
import json
import time
from datetime import datetime
from config import JELLYSEERR_URL, API_KEY, IS_4K_REQUEST, DEBUG_MODE, logger
from utils import normalize_title, create_session_with_retries

class JellyseerrClient:
    """Client for interacting with Jellyseerr API."""
    
    def __init__(self):
        self.base_url = JELLYSEERR_URL
        self.headers = {
            "X-Api-Key": API_KEY, 
            "Connection": "close"
        }
    
    def search_movie(self, movie_name, max_retries=3):
        """
        Search for a movie in Jellyseerr.
        
        Args:
            movie_name (str): Name of the movie to search for
            max_retries (int): Maximum number of retry attempts
            
        Returns:
            dict or None: JSON response from Jellyseerr API
        """
        encoded_query = urllib.parse.quote(movie_name, safe='')
        logger.debug(f"Searching Jellyseerr for '{movie_name}' with encoded query: {encoded_query}")
        start_time = datetime.now()
        
        for attempt in range(1, max_retries + 1):
            try:
                with create_session_with_retries() as session:
                    logger.debug(f"Attempt {attempt} for '{movie_name}': Sending request...")
                    res = session.get(
                        f"{self.base_url}/api/v1/search", 
                        params={"query": encoded_query}, 
                        headers=self.headers, 
                        timeout=(5, 15)
                    )
                    
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
                    
            except Exception as e:
                elapsed = (datetime.now() - start_time).total_seconds()
                logger.error(f"Error querying Jellyseerr for '{movie_name}' on attempt {attempt} after {elapsed:.2f}s: {e}")
                print(f"❌ Error querying Jellyseerr for '{movie_name}': {e}")
                if attempt == max_retries:
                    logger.warning(f"Max retries reached for '{movie_name}', skipping")
                    print(f"❌ Max retries reached for '{movie_name}', skipping")
                    return None
                time.sleep(2 ** attempt)  # Exponential backoff
                
        return None
    
    def get_movie_details(self, movie_name, json_data):
        """
        Extract movie details from Jellyseerr search response.
        
        Args:
            movie_name (str): Original movie name being searched
            json_data (dict): JSON response from Jellyseerr search
            
        Returns:
            tuple: (imdb_id, media_id, tmdb_id) or (None, None, None)
        """
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
    
    def make_request(self, tmdb_id, media_id):
        """
        Make a request for a movie in Jellyseerr.
        
        Args:
            tmdb_id (int): TMDB ID of the movie
            media_id (int): Media ID from Jellyseerr
            
        Returns:
            tuple: (success: bool, message: str)
        """
        payload = {
            "mediaType": "movie",
            "tmdbId": tmdb_id,
            "mediaId": media_id,
            "is4k": IS_4K_REQUEST
        }
        
        logger.debug(f"Making request for tmdbId: {tmdb_id}, mediaId: {media_id}, payload: {json.dumps(payload)}")
        
        try:
            with create_session_with_retries() as session:
                res = session.post(
                    f"{self.base_url}/api/v1/request", 
                    json=payload, 
                    headers=self.headers, 
                    timeout=(5, 15)
                )
                
                if res.status_code == 201:
                    logger.info(f"Successfully requested movie (tmdbId: {tmdb_id}, mediaId: {media_id})")
                    print(f"✅ Requested movie (tmdbId: {tmdb_id}, mediaId: {media_id})")
                    return True, res.text
                else:
                    logger.info(f"Request skipped for mediaId {media_id}: {res.text}")
                    print(f"ℹ️ Request skipped for mediaId {media_id}: {res.text}")
                    return False, res.text
                    
        except Exception as e:
            logger.error(f"Error requesting movie (tmdbId: {tmdb_id}, mediaId: {media_id}): {e}")
            print(f"❌ Error requesting movie: {e}")
            return False, str(e)
