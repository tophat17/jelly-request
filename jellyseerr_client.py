"""
Jellyseerr API client for Jelly Request application.
Handles all interactions with the Jellyseerr API including search and requests.
"""

import json
import time
from datetime import datetime
from config import JELLYSEERR_URL, API_KEY, IS_4K_REQUEST, DEBUG_MODE, logger
from utils import normalize_title, create_session_with_retries, decode_html_entities

# A candidate has to at least share its whole title with the IMDb entry to be
# worth requesting. Tuned so an exact title alone passes, but a loose substring
# hit whose year contradicts IMDb does not.
_MIN_MATCH_SCORE = 20


def _release_year(release_date):
    """Pull the year out of a TMDB release date such as '1998-10-16'."""
    if not release_date or not isinstance(release_date, str):
        return None
    head = release_date.split("-")[0]
    return int(head) if head.isdigit() else None


def _score_match(candidate, wanted_title, wanted_year, wanted_imdb_id, original_title=""):
    """
    Score how well a Jellyseerr search result matches the IMDb entry.

    Args:
        candidate (dict): Parsed search result
        wanted_title (str): Title from IMDb
        wanted_year (int): Release year from IMDb, if known
        wanted_imdb_id (str): IMDb id from IMDb, if known
        original_title (str): The result's untranslated title, if any

    Returns:
        int: Higher is a better match
    """
    score = 0
    wanted_norm = normalize_title(wanted_title)
    titles = {normalize_title(candidate["title"])}
    if original_title:
        titles.add(normalize_title(original_title))

    # An IMDb id agreeing is conclusive; nothing else needs to line up.
    if wanted_imdb_id and candidate.get("imdb_id") == wanted_imdb_id:
        score += 100

    if wanted_norm and wanted_norm in titles:
        score += 50
    elif wanted_norm and any(wanted_norm in t or t in wanted_norm for t in titles if t):
        score += 20

    # TMDB and IMDb often disagree by a year on festival or limited releases,
    # so treat a near miss as neutral and only penalise a real mismatch.
    if wanted_year and candidate.get("year"):
        difference = abs(wanted_year - candidate["year"])
        if difference == 0:
            score += 25
        elif difference > 1:
            score -= 30

    return score


class JellyseerrClient:
    """Client for interacting with Jellyseerr API."""
    
    def __init__(self):
        self.base_url = JELLYSEERR_URL
        self.headers = {
            "X-Api-Key": API_KEY, 
            "Connection": "close"
        }
        self.existing_requests = []
        self.skip_list = {}
    
    def search_movie(self, movie_name, max_retries=3):
        """
        Search for a movie in Jellyseerr.
        
        Args:
            movie_name (str): Name of the movie to search for
            max_retries (int): Maximum number of retry attempts
            
        Returns:
            dict or None: JSON response from Jellyseerr API
        """
        # Hand the raw title to requests, which percent-encodes the query string
        # itself. Encoding it here as well would send "Practical%2520Magic",
        # and Jellyseerr would search for the literal text "Practical%20Magic".
        logger.debug(f"Searching Jellyseerr for '{movie_name}'")
        start_time = datetime.now()

        for attempt in range(1, max_retries + 1):
            try:
                with create_session_with_retries() as session:
                    logger.debug(f"Attempt {attempt} for '{movie_name}': Sending request...")
                    res = session.get(
                        f"{self.base_url}/api/v1/search",
                        params={"query": movie_name},
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
    
    def get_movie_details(self, movie, json_data):
        """
        Pick the best matching movie from a Jellyseerr search response.

        Args:
            movie (str or dict): Title being searched, or an IMDb entry with
                'title' and optionally 'year' and 'imdb_id'
            json_data (dict): JSON response from Jellyseerr search

        Returns:
            tuple: (imdb_id, media_id, tmdb_id) or (None, None, None)
        """
        if isinstance(movie, dict):
            movie_name = movie.get("title", "")
            wanted_year = movie.get("year")
            wanted_imdb_id = movie.get("imdb_id")
        else:
            movie_name = movie
            wanted_year = None
            wanted_imdb_id = None

        if not json_data or "results" not in json_data:
            logger.error(f"No results in Jellyseerr response for '{movie_name}'")
            print(f"❌ No results in Jellyseerr response for '{movie_name}'")
            return None, None, None

        best = None
        for result in json_data["results"]:
            if result.get("mediaType") != "movie":
                continue

            title = decode_html_entities(result.get("title", ""))
            media_id = result.get("id")
            if not media_id or not title:
                logger.debug(f"Skipping result for '{title}' (missing mediaId or title)")
                continue

            candidate = {
                "title": title,
                "imdb_id": result.get("mediaInfo", {}).get("imdbId") or result.get("imdbId"),
                "media_id": media_id,
                "tmdb_id": result.get("tmdbId", media_id),
                "year": _release_year(result.get("releaseDate")),
            }
            candidate["score"] = _score_match(
                candidate, movie_name, wanted_year, wanted_imdb_id,
                decode_html_entities(result.get("originalTitle", "")),
            )

            logger.debug(
                f"Candidate '{title}' ({candidate['year']}) "
                f"tmdbId={candidate['tmdb_id']} score={candidate['score']}"
            )
            if best is None or candidate["score"] > best["score"]:
                best = candidate

        # Below this the result is a different film that merely shares a word,
        # and requesting it would add the wrong movie to the library.
        if not best or best["score"] < _MIN_MATCH_SCORE:
            logger.warning(f"No confident match in Jellyseerr for '{movie_name}'")
            print(f"❌ No matching movie found in Jellyseerr for '{movie_name}'")
            return None, None, None

        logger.info(
            f"Matched '{movie_name}' to '{best['title']}' ({best['year']}) "
            f"(imdbId: {best['imdb_id']}, mediaId: {best['media_id']}, "
            f"tmdbId: {best['tmdb_id']}, score: {best['score']})"
        )
        print(f"✅ Found movie: '{best['title']}' ({best['year']}) (tmdbId: {best['tmdb_id']})")
        return best["imdb_id"], best["media_id"], best["tmdb_id"]
    
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

    def get_existing_requests(self, max_retries=3):
        """
        Fetch all existing requests from Jellyseerr to build skip list.
        
        Args:
            max_retries (int): Maximum number of retry attempts
            
        Returns:
            list: List of existing requests or empty list on error
        """
        print("Fetching existing Jellyseerr requests...")
        logger.info("Fetching existing Jellyseerr requests for duplicate prevention")
        
        for attempt in range(1, max_retries + 1):
            try:
                with create_session_with_retries() as session:
                    # Fetch a large number of requests to ensure we get all of them
                    res = session.get(
                        f"{self.base_url}/api/v1/request",
                        params={"take": 1000},
                        headers=self.headers,
                        timeout=(5, 15)
                    )
                    
                    if res.status_code != 200:
                        logger.error(f"Failed to fetch requests on attempt {attempt}: {res.text}")
                        if attempt == max_retries:
                            logger.warning("Max retries reached for fetching requests, proceeding without duplicate prevention")
                            print("⚠️ Could not fetch existing requests, duplicate prevention disabled")
                            return []
                        continue
                    
                    data = res.json()
                    requests = data.get("results", [])
                    total_requests = len(requests)
                    
                    logger.info(f"Successfully fetched {total_requests} existing requests")
                    print(f"✅ Found {total_requests} existing requests in Jellyseerr")
                    
                    self.existing_requests = requests
                    self._build_skip_list()
                    
                    return requests
                    
            except Exception as e:
                logger.error(f"Error fetching existing requests on attempt {attempt}: {e}")
                if attempt == max_retries:
                    logger.warning("Max retries reached for fetching requests, proceeding without duplicate prevention")
                    print("⚠️ Error fetching existing requests, duplicate prevention disabled")
                    return []
                time.sleep(2 ** attempt)
        
        return []
    
    def _build_skip_list(self):
        """Build internal skip list from existing requests for fast lookups."""
        self.skip_list = {}
        skip_count = 0
        
        logger.debug(f"Processing {len(self.existing_requests)} existing requests for skip list")
        
        for i, request in enumerate(self.existing_requests):
            if i < 3:  # Log first 3 requests for debugging
                logger.debug(f"Request {i+1} structure: {request}")
            
            media = request.get("media", {})
            tmdb_id = media.get("tmdbId")
            imdb_id = media.get("imdbId")
            title = media.get("title", "Unknown")
            status = request.get("status", "unknown")
            
            # Only skip requests that are not failed or declined
            if status not in ["DECLINED", "FAILED", 3]:  # Status 3 = declined
                if tmdb_id:
                    self.skip_list[f"tmdb_{tmdb_id}"] = {
                        "reason": f"Already requested (Status: {status})",
                        "request_id": request.get("id"),
                        "title": title,
                        "status": status,
                        "created": request.get("createdAt", ""),
                        "is_4k": request.get("is4k", False)
                    }
                    skip_count += 1
                
                if imdb_id:
                    self.skip_list[f"imdb_{imdb_id}"] = {
                        "reason": f"Already requested (Status: {status})",
                        "request_id": request.get("id"),
                        "title": title,
                        "status": status,
                        "created": request.get("createdAt", ""),
                        "is_4k": request.get("is4k", False)
                    }
        
        print(f"✅ Skip list built: {skip_count} movies to skip (requested/available)")
        logger.info(f"Built skip list with {skip_count} movies to prevent duplicates")
    
    def check_movie_availability(self, tmdb_id, max_retries=3):
        """
        Check if a movie is already available in the library.
        
        Args:
            tmdb_id (int): TMDB ID of the movie
            max_retries (int): Maximum number of retry attempts
            
        Returns:
            dict or None: Availability info or None if not available/error
        """
        for attempt in range(1, max_retries + 1):
            try:
                with create_session_with_retries() as session:
                    url = f"{self.base_url}/api/v1/movie/{tmdb_id}"
                    res = session.get(
                        url,
                        headers=self.headers,
                        timeout=(5, 15)
                    )
                    
                    if res.status_code == 200:
                        data = res.json()
                        media_info = data.get("mediaInfo", {})
                        status = media_info.get("status")
                        
                        if status == 5:  # Status 5 = Available
                            return {
                                "available": True,
                                "status": "AVAILABLE",
                                "title": data.get("title", "Unknown"),
                                "added_date": media_info.get("createdAt", "")
                            }
                    
                    return None
                    
            except Exception as e:
                logger.debug(f"Error checking availability for tmdbId {tmdb_id} on attempt {attempt}: {e}")
                if attempt == max_retries:
                    return None
                time.sleep(1)
        
        return None
    
    def is_already_requested_or_available(self, tmdb_id, imdb_id=None, title=None):
        """
        Check if movie is already requested or available using multiple matching methods.
        
        Args:
            tmdb_id (int): TMDB ID of the movie
            imdb_id (str, optional): IMDb ID of the movie
            title (str, optional): Title of the movie for logging
            
        Returns:
            tuple: (should_skip: bool, skip_reason: str, skip_details: dict)
        """
        # Method 1: Check skip list (existing requests) by TMDB ID
        tmdb_key = f"tmdb_{tmdb_id}"
        if tmdb_key in self.skip_list:
            details = self.skip_list[tmdb_key]
            return True, details["reason"], details
        
        # Method 2: Check skip list by IMDb ID (backup)
        if imdb_id and isinstance(imdb_id, str):
            imdb_key = f"imdb_{imdb_id}"
            if imdb_key in self.skip_list:
                details = self.skip_list[imdb_key]
                return True, details["reason"], details
        
        # Method 3: Check if already available in library
        availability = self.check_movie_availability(tmdb_id)
        if availability and availability.get("available"):
            return True, "Already available in library", {
                "status": "AVAILABLE",
                "title": availability.get("title", title or "Unknown"),
                "added_date": availability.get("added_date", ""),
                "reason": "Already available in library (Status: AVAILABLE)"
            }
        
        # Movie is not requested and not available - can be requested
        return False, "New movie not in system", {}
