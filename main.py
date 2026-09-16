"""
Main entry point for Jelly Request application.
Orchestrates the IMDb scraping and Jellyseerr requesting process.
"""

import time
from config import RUN_INTERVAL_DAYS, DRY_RUN, logger
from imdb_scraper import fetch_imdb_titles
from jellyseerr_client import JellyseerrClient
from header import display_header

def main():
    """Main application loop."""
    # Display application header
    display_header()
    
    logger.info(f"Starting IMDb to Jellyseerr sync, configured to run every {RUN_INTERVAL_DAYS} day(s)")
    print(f"Configured to run every {RUN_INTERVAL_DAYS} day(s)")

    if DRY_RUN:
        logger.info("DRY_RUN is on; no requests will be created")
        print("🧪 DRY RUN: matching everything but creating no requests")
    
    # Initialize Jellyseerr client
    jellyseerr = JellyseerrClient()
    
    while True:
        try:
            print("\nFetching IMDb's Top Movies of the Week...")
            top_movies = fetch_imdb_titles()

            if not top_movies:
                logger.error("No movies found from IMDb")
                print("❌ No movies found.")
            else:
                logger.info(f"Fetched {len(top_movies)} unique movies")
                print(f"✅ Top Movies of the Week (Total: {len(top_movies)}):")
                for i, movie in enumerate(top_movies, 1):
                    print(f"{i}. {movie['title']} ({movie['year']})")

                process_movies(jellyseerr, top_movies)
                
        except Exception as e:
            logger.error(f"Unexpected error in main loop: {e}")
            print(f"❌ Unexpected error: {e}")
        finally:
            logger.info(f"Completed run, sleeping for {RUN_INTERVAL_DAYS} day(s)")
            print(f"ℹ️ Completed run, sleeping for {RUN_INTERVAL_DAYS} day(s)")
            time.sleep(RUN_INTERVAL_DAYS * 24 * 60 * 60)  # Sleep for specified days

def process_movies(jellyseerr_client, movies):
    """
    Process a list of movies through Jellyseerr with enhanced duplicate prevention.
    
    Args:
        jellyseerr_client (JellyseerrClient): Initialized Jellyseerr client
        movies (list): IMDb entries (title, year, imdb_id) to process
    """
    # Initialize counters for summary
    stats = {
        "total": len(movies),
        "new_requests": 0,
        "skipped_requested": 0,
        "skipped_available": 0,
        "skipped_processing": 0,
        "skipped_pending": 0,
        "skipped_declined": 0,
        "not_found": 0,
        "would_request": 0,
        "errors": 0
    }
    
    # Fetch existing requests for duplicate prevention
    jellyseerr_client.get_existing_requests()
    
    print("\nRequesting movies in Jellyseerr...")
    
    for i, movie in enumerate(movies, 1):
        title = movie["title"]
        print(f"\nProcessing '{title}' ({movie['year']}) ({i}/{len(movies)})...")
        try:
            # Search for the movie in Jellyseerr
            json_data = jellyseerr_client.search_movie(title)
            if not json_data:
                stats["not_found"] += 1
                print(f"❌ SKIPPED: Not found in Jellyseerr search results")
                continue

            # Pick the best match using the IMDb year and id as tiebreakers
            imdb_id, media_id, tmdb_id = jellyseerr_client.get_movie_details(movie, json_data)
            if not media_id:
                stats["not_found"] += 1
                print(f"❌ SKIPPED: Not found in Jellyseerr search results")
                continue
            
            # Check if already requested or available
            should_skip, skip_reason, skip_details = jellyseerr_client.is_already_requested_or_available(
                tmdb_id, imdb_id, title
            )
            
            if should_skip:
                # Categorize skip reason for stats
                status = str(skip_details.get("status", "")).upper()
                if status == "AVAILABLE":
                    stats["skipped_available"] += 1
                elif status == "APPROVED":
                    stats["skipped_requested"] += 1
                elif status == "PROCESSING":
                    stats["skipped_processing"] += 1
                elif status == "PENDING":
                    stats["skipped_pending"] += 1
                elif status == "DECLINED":
                    stats["skipped_declined"] += 1
                else:
                    stats["skipped_requested"] += 1  # Default to requested
                
                # Enhanced logging with detailed skip reason
                _log_skip_reason(title, skip_reason, skip_details)
                continue
            
            # Movie is new - make the request
            if DRY_RUN:
                stats["would_request"] += 1
                print(f"🧪 WOULD REQUEST: New movie not in system (tmdbId: {tmdb_id})")
                continue

            print(f"🎬 REQUESTING: New movie not in system")
            success, msg = jellyseerr_client.make_request(tmdb_id, media_id)
            
            if success:
                stats["new_requests"] += 1
                print(f"✅ SUCCESS: Movie requested - Status: PENDING")
            else:
                stats["errors"] += 1
                if "Request for this media already exists" not in msg:
                    logger.error(f"Failed to request '{title}': {msg}")
                    print(f"❌ FAILED: Could not request movie - {msg}")
                else:
                    # This is a race condition where movie was requested between our check and request
                    stats["skipped_requested"] += 1
                    print(f"⏭️ SKIPPED: Request already exists (race condition)")
                
        except Exception as e:
            stats["errors"] += 1
            logger.error(f"Error processing movie '{movie.get('title', movie)}': {e}")
            print(f"❌ ERROR: Processing failed - {e}")
            continue
    
    # Print summary
    _print_summary(stats)

def _log_skip_reason(movie, skip_reason, skip_details):
    """
    Log detailed skip reason with enhanced formatting.
    
    Args:
        movie (str): Movie title
        skip_reason (str): Reason for skipping
        skip_details (dict): Additional details about the skip
    """
    status = str(skip_details.get("status", "")).upper()
    
    if status == "AVAILABLE":
        added_date = skip_details.get("added_date", "")
        date_str = f" - Added: {added_date[:10]}" if added_date else ""
        print(f"⏭️ SKIPPED: Already available in library (Status: AVAILABLE){date_str}")
        
    elif status == "APPROVED":
        request_id = skip_details.get("request_id", "")
        created = skip_details.get("created", "")
        date_str = f" - Requested: {created[:10]}" if created else ""
        id_str = f" - Request ID: {request_id}" if request_id else ""
        print(f"⏭️ SKIPPED: Already requested (Status: APPROVED){id_str}{date_str}")
        
    elif status == "PROCESSING":
        request_id = skip_details.get("request_id", "")
        id_str = f" - Request ID: {request_id}" if request_id else ""
        print(f"⏭️ SKIPPED: Currently downloading (Status: PROCESSING){id_str}")
        
    elif status == "PENDING":
        request_id = skip_details.get("request_id", "")
        created = skip_details.get("created", "")
        date_str = f" - Requested: {created[:10]}" if created else ""
        id_str = f" - Request ID: {request_id}" if request_id else ""
        print(f"⏭️ SKIPPED: Pending approval (Status: PENDING){id_str}{date_str}")
        
    elif status == "DECLINED":
        request_id = skip_details.get("request_id", "")
        id_str = f" - Request ID: {request_id}" if request_id else ""
        print(f"⏭️ SKIPPED: Failed previous request (Status: DECLINED){id_str}")
        
    else:
        print(f"⏭️ SKIPPED: {skip_reason}")

def _print_summary(stats):
    """
    Print detailed summary of processing results.
    
    Args:
        stats (dict): Statistics from processing
    """
    total = stats["total"]
    new_requests = stats["would_request"] if DRY_RUN else stats["new_requests"]
    total_skipped = (stats["skipped_requested"] + stats["skipped_available"] + 
                    stats["skipped_processing"] + stats["skipped_pending"] + 
                    stats["skipped_declined"])
    
    print(f"\n{'='*40}")
    print("SUMMARY")
    print(f"{'='*40}")
    print(f"📊 Total movies processed: {total}")
    if DRY_RUN:
        print(f"🧪 Would have requested: {stats['would_request']}")
    else:
        print(f"✅ New requests made: {new_requests}")
    
    if stats["skipped_requested"] > 0:
        print(f"⏭️ Skipped (already requested): {stats['skipped_requested']}")
    if stats["skipped_available"] > 0:
        print(f"📚 Skipped (already available): {stats['skipped_available']}")
    if stats["skipped_processing"] > 0:
        print(f"⚠️ Skipped (currently downloading): {stats['skipped_processing']}")
    if stats["skipped_pending"] > 0:
        print(f"⏸️ Skipped (pending approval): {stats['skipped_pending']}")
    if stats["skipped_declined"] > 0:
        print(f"❌ Skipped (previously declined): {stats['skipped_declined']}")
    if stats["not_found"] > 0:
        print(f"🔍 Not found in search: {stats['not_found']}")
    if stats["errors"] > 0:
        print(f"💥 Errors encountered: {stats['errors']}")
    
    success_rate = (new_requests / total * 100) if total > 0 else 0
    prevention_rate = (total_skipped / total * 100) if total > 0 else 0
    
    print(f"\n🎯 Success rate: {success_rate:.0f}% new requests ({new_requests}/{total} movies were genuinely new)")
    print(f"⚡ Duplicate prevention: {prevention_rate:.0f}% efficiency ({total_skipped}/{total} duplicates avoided)")

if __name__ == "__main__":
    main()
