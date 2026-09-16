"""
IMDb title fetching for Jelly Request application.

IMDb's HTML pages sit behind AWS WAF, which answers ordinary HTTP requests
with a "Human Verification" JavaScript challenge instead of the page. Both
plain `requests` and headless Chromium get stopped by it, so instead of
fighting the challenge we read the same data from IMDb's public GraphQL
endpoint that imdb.com's own frontend uses. It is not WAF-challenged, needs
no API key, and returns clean JSON.

IMDB_URL stays the user-facing knob: the URL is translated into the
equivalent GraphQL query. Supported forms:
  - https://www.imdb.com/chart/<slug>                (moviemeter, top, ...)
  - https://www.imdb.com/india/top-rated-indian-movies/
  - https://www.imdb.com/list/ls<id>/                (public user lists)
  - https://www.imdb.com/search/title/?<filters>     (advanced search)
"""

import json
import urllib.parse

from config import IMDB_URL, MOVIE_LIMIT, logger
from utils import create_session_with_retries, decode_html_entities, normalize_title

GRAPHQL_ENDPOINT = "https://api.graphql.imdb.com/"

# The endpoint serves up to 250 edges per request; anything larger than that
# is fetched by following the `after` cursor.
_PAGE_SIZE = 250

_HEADERS = {
    "content-type": "application/json",
    "accept": "application/json",
    # Identify as the site's own web client - the endpoint rejects requests
    # that do not name a client.
    "x-imdb-client-name": "imdb-web-next",
    "x-imdb-user-country": "US",
    "x-imdb-user-language": "en-US",
    "user-agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/140.0.0.0 Safari/537.36"
    ),
}

# IMDb URL path -> ChartTitleType enum value.
_CHART_TYPES = {
    "chart/moviemeter": "MOST_POPULAR_MOVIES",
    "chart/tvmeter": "MOST_POPULAR_TV_SHOWS",
    "chart/top": "TOP_RATED_MOVIES",
    "chart/toptv": "TOP_RATED_TV_SHOWS",
    "chart/top-english-movies": "TOP_RATED_ENGLISH_MOVIES",
    "chart/bottom": "LOWEST_RATED_MOVIES",
    "india/top-rated-indian-movies": "TOP_RATED_INDIAN_MOVIES",
    "india/top-rated-malayalam-movies": "TOP_RATED_MALAYALAM_MOVIES",
    "india/top-rated-tamil-movies": "TOP_RATED_TAMIL_MOVIES",
    "india/top-rated-telugu-movies": "TOP_RATED_TELUGU_MOVIES",
}

# Charts that contain no movies at all - worth calling out, because the
# Jellyseerr side only requests movies.
_TV_CHART_TYPES = {"MOST_POPULAR_TV_SHOWS", "TOP_RATED_TV_SHOWS"}

# `title_type=` values used by IMDb's search URLs -> GraphQL title type ids.
_TITLE_TYPE_IDS = {
    "feature": "movie",
    "movie": "movie",
    "tv_movie": "tvMovie",
    "tv_series": "tvSeries",
    "tv_miniseries": "tvMiniSeries",
    "tv_special": "tvSpecial",
    "tv_short": "tvShort",
    "short": "short",
    "video": "video",
    "video_game": "videoGame",
    "music_video": "musicVideo",
}

# `sort=<key>,<order>` keys used by IMDb's search URLs -> sortBy enum values.
_SORT_KEYS = {
    "popularity": "POPULARITY",
    "moviemeter": "POPULARITY",
    "user_rating": "USER_RATING",
    "num_votes": "USER_RATING_COUNT",
    "release_date": "RELEASE_DATE",
    "alpha": "TITLE_REGIONAL",
    "runtime": "RUNTIME",
    "boxoffice_gross_us": "BOX_OFFICE_GROSS_DOMESTIC",
    "ranking": "RANKING",
}

# Genre ids are capitalised on the API side ("horror" -> "Horror"). Hyphenated
# names title-case cleanly apart from this one.
_GENRE_OVERRIDES = {"reality-tv": "Reality-TV"}

# Search parameters we translate, plus the presentational ones IMDb puts in
# its own URLs that have no bearing on which titles come back.
_KNOWN_SEARCH_PARAMS = {
    "title_type", "genres", "primary_language", "countries", "country_of_origin",
    "release_date", "year", "user_rating", "num_votes", "keywords", "sort",
    "ref_", "count", "start", "view", "explore",
}

_TITLE_FIELDS = """
    id
    titleText { text }
    originalTitleText { text }
    releaseYear { year }
    titleType { id }
    ratingsSummary { aggregateRating voteCount }
"""


def _post_graphql(query, variables=None):
    """
    Send a GraphQL query to IMDb and return the `data` payload.

    Args:
        query (str): GraphQL query document
        variables (dict): Optional query variables

    Returns:
        dict: The `data` object from the response

    Raises:
        RuntimeError: If the request fails or the API reports errors
    """
    payload = {"query": query}
    if variables:
        payload["variables"] = variables

    with create_session_with_retries() as session:
        res = session.post(
            GRAPHQL_ENDPOINT,
            headers=_HEADERS,
            data=json.dumps(payload),
            timeout=(10, 30),
        )

    if res.status_code != 200:
        raise RuntimeError(f"IMDb API returned HTTP {res.status_code}: {res.text[:300]}")

    try:
        body = res.json()
    except ValueError as e:
        raise RuntimeError(f"IMDb API returned a non-JSON response: {e}")

    if body.get("errors"):
        messages = "; ".join(err.get("message", "?") for err in body["errors"])
        raise RuntimeError(f"IMDb API error: {messages}")

    return body.get("data") or {}


def _dig(mapping, *keys):
    """Walk nested dicts, returning None instead of raising on a missing key."""
    current = mapping
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def _node_title(node):
    """
    Unwrap the Title object from a connection node.

    Charts nest the title directly, advanced search wraps it in `title`, and
    list items wrap it in `item`.
    """
    if not isinstance(node, dict):
        return None
    for key in ("title", "item"):
        if isinstance(node.get(key), dict):
            return node[key]
    return node


def _title_from_node(node):
    """Turn a GraphQL Title node into the dict the rest of the module uses."""
    if not node:
        return None

    title = _dig(node, "titleText", "text") or _dig(node, "originalTitleText", "text")
    if not title:
        return None

    return {
        "title": decode_html_entities(title),
        "imdb_id": node.get("id"),
        "year": _dig(node, "releaseYear", "year"),
        "title_type": _dig(node, "titleType", "id"),
        "rating": _dig(node, "ratingsSummary", "aggregateRating"),
        "votes": _dig(node, "ratingsSummary", "voteCount"),
    }


def _paginate(build_query, extract, limit):
    """
    Follow `after` cursors until `limit` titles are collected.

    Args:
        build_query (callable): Takes (page_size, after_cursor), returns a query
        extract (callable): Takes the `data` payload, returns the connection dict
        limit (int): Maximum number of titles to collect

    Returns:
        list: Title dicts
    """
    titles = []
    cursor = None

    while len(titles) < limit:
        page_size = min(_PAGE_SIZE, limit - len(titles))
        data = _post_graphql(build_query(page_size, cursor))
        connection = extract(data)
        if not connection:
            break

        edges = connection.get("edges") or []
        for edge in edges:
            parsed = _title_from_node(_node_title(edge.get("node")))
            if parsed:
                titles.append(parsed)

        page_info = connection.get("pageInfo") or {}
        cursor = page_info.get("endCursor")
        if not edges or not page_info.get("hasNextPage") or not cursor:
            break

    return titles[:limit]


def _fetch_chart(chart_type, limit):
    """Fetch titles from one of IMDb's built-in charts."""
    def build_query(page_size, cursor):
        after = ', after: "{0}"'.format(cursor) if cursor else ""
        return """
        {{
          chartTitles(first: {size}{after}, chart: {{chartType: {chart}}}) {{
            edges {{ node {{ {fields} }} }}
            pageInfo {{ hasNextPage endCursor }}
          }}
        }}
        """.format(size=page_size, after=after, chart=chart_type, fields=_TITLE_FIELDS)

    return _paginate(build_query, lambda data: data.get("chartTitles"), limit)


def _fetch_list(list_id, limit):
    """Fetch titles from a public IMDb user list (ls...)."""
    def build_query(page_size, cursor):
        after = ', after: "{0}"'.format(cursor) if cursor else ""
        return """
        {{
          list(id: {list_id}) {{
            items(first: {size}{after}) {{
              edges {{ node {{ item {{ ... on Title {{ {fields} }} }} }} }}
              pageInfo {{ hasNextPage endCursor }}
            }}
          }}
        }}
        """.format(list_id=json.dumps(list_id), size=page_size, after=after,
                   fields=_TITLE_FIELDS)

    return _paginate(build_query, lambda data: _dig(data, "list", "items"), limit)


def _fetch_search(constraints, sort, limit):
    """Fetch titles through IMDb's advanced title search."""
    def build_query(page_size, cursor):
        after = ', after: "{0}"'.format(cursor) if cursor else ""
        return """
        {{
          advancedTitleSearch(first: {size}{after}, sort: {sort}, constraints: {constraints}) {{
            edges {{ node {{ title {{ {fields} }} }} }}
            pageInfo {{ hasNextPage endCursor }}
          }}
        }}
        """.format(size=page_size, after=after, sort=sort, constraints=constraints,
                   fields=_TITLE_FIELDS)

    return _paginate(build_query, lambda data: data.get("advancedTitleSearch"), limit)


def _graphql_string_list(values):
    """Render a Python list of strings as a GraphQL list literal."""
    return "[" + ", ".join(json.dumps(v) for v in values) + "]"


def _normalize_genre(value):
    """Convert a search URL genre ("sci-fi") to an API genre id ("Sci-Fi")."""
    key = value.strip().lower()
    if key in _GENRE_OVERRIDES:
        return _GENRE_OVERRIDES[key]
    return "-".join(part.capitalize() for part in key.split("-"))


def _expand_date(value, is_end):
    """
    Expand IMDb's partial date formats to a full YYYY-MM-DD date.

    "2024" becomes 2024-01-01 as a range start and 2024-12-31 as a range end;
    "2024-06" behaves the same way within the month.
    """
    parts = value.strip().split("-")
    if not parts or not parts[0].isdigit():
        return None

    year = parts[0]
    if len(parts) == 1:
        return f"{year}-12-31" if is_end else f"{year}-01-01"
    if len(parts) == 2:
        month = parts[1].zfill(2)
        if is_end:
            # Last day of the month, without pulling in a calendar dependency.
            last = {"01": "31", "02": "28", "03": "31", "04": "30", "05": "31",
                    "06": "30", "07": "31", "08": "31", "09": "30", "10": "31",
                    "11": "30", "12": "31"}.get(month, "28")
            return f"{year}-{month}-{last}"
        return f"{year}-{month}-01"
    return f"{year}-{parts[1].zfill(2)}-{parts[2].zfill(2)}"


def _range_params(value):
    """Split an IMDb "min,max" range parameter into (min, max) strings."""
    low, _, high = value.partition(",")
    return low.strip() or None, high.strip() or None


def _build_search_query(params):
    """
    Translate IMDb search URL parameters into GraphQL constraints and sort.

    Args:
        params (dict): Parsed query string, values flattened to single strings

    Returns:
        tuple: (constraints literal, sort literal)
    """
    constraints = []

    title_types = params.get("title_type")
    ids = [_TITLE_TYPE_IDS.get(t.strip().lower(), t.strip())
           for t in (title_types or "").split(",") if t.strip()]
    if not ids:
        # IMDb's search page returns every title type, episodes included, when
        # none is given. Jellyseerr can only be asked for movies, so default to
        # those; an explicit title_type= in the URL still wins.
        ids = ["movie"]
        logger.info("No title_type in IMDB_URL, defaulting the search to feature films")
    constraints.append(
        f"titleTypeConstraint: {{anyTitleTypeIds: {_graphql_string_list(ids)}}}"
    )

    genres = params.get("genres")
    if genres:
        ids = [_normalize_genre(g) for g in genres.split(",") if g.strip()]
        if ids:
            constraints.append(
                f"genreConstraint: {{allGenreIds: {_graphql_string_list(ids)}}}"
            )

    languages = params.get("primary_language")
    if languages:
        codes = [code.strip() for code in languages.split(",") if code.strip()]
        if codes:
            constraints.append(
                f"languageConstraint: {{anyPrimaryLanguages: {_graphql_string_list(codes)}}}"
            )

    countries = params.get("countries") or params.get("country_of_origin")
    if countries:
        codes = [c.strip().upper() for c in countries.split(",") if c.strip()]
        if codes:
            constraints.append(
                f"originCountryConstraint: {{anyPrimaryCountries: {_graphql_string_list(codes)}}}"
            )

    release_date = params.get("release_date") or params.get("year")
    if release_date:
        low, high = _range_params(release_date)
        start = _expand_date(low, is_end=False) if low else None
        end = _expand_date(high, is_end=True) if high else None
        # A bare "2024" with no comma means the whole of that year.
        if start and not end and "," not in release_date:
            end = _expand_date(low, is_end=True)
        bounds = []
        if start:
            bounds.append(f'start: "{start}"')
        if end:
            bounds.append(f'end: "{end}"')
        if bounds:
            constraints.append(
                f"releaseDateConstraint: {{releaseDateRange: {{{', '.join(bounds)}}}}}"
            )

    ratings = []
    user_rating = params.get("user_rating")
    if user_rating:
        low, high = _range_params(user_rating)
        bounds = []
        if low:
            bounds.append(f"min: {float(low)}")
        if high:
            bounds.append(f"max: {float(high)}")
        if bounds:
            ratings.append(f"aggregateRatingRange: {{{', '.join(bounds)}}}")

    num_votes = params.get("num_votes")
    if num_votes:
        low, high = _range_params(num_votes)
        bounds = []
        if low:
            bounds.append(f"min: {int(low)}")
        if high:
            bounds.append(f"max: {int(high)}")
        if bounds:
            ratings.append(f"ratingsCountRange: {{{', '.join(bounds)}}}")

    if ratings:
        constraints.append(f"userRatingsConstraint: {{{', '.join(ratings)}}}")

    keywords = params.get("keywords")
    if keywords:
        words = [k.strip() for k in keywords.split(",") if k.strip()]
        if words:
            constraints.append(
                f"keywordConstraint: {{anyKeywords: {_graphql_string_list(words)}}}"
            )

    unsupported = sorted(set(params) - _KNOWN_SEARCH_PARAMS)
    if unsupported:
        logger.warning(
            f"Ignoring unsupported IMDb search parameters: {', '.join(unsupported)}"
        )

    sort_key, _, sort_order = (params.get("sort") or "popularity,asc").partition(",")
    sort_by = _SORT_KEYS.get(sort_key.strip().lower())
    if not sort_by:
        logger.warning(f"Unknown IMDb sort key '{sort_key}', falling back to popularity")
        sort_by = "POPULARITY"
    order = "DESC" if sort_order.strip().lower() == "desc" else "ASC"

    # IMDb ranks popularity ascending, so "popularity,desc" asks for the
    # *least* popular titles. It is nearly always a typo for "popularity,asc".
    if sort_by == "POPULARITY" and order == "DESC":
        logger.warning(
            "IMDB_URL sorts by 'popularity,desc', which returns the LEAST popular "
            "titles first. Use 'popularity,asc' for the most popular ones."
        )
        print("⚠️ 'popularity,desc' returns the least popular titles - did you mean 'popularity,asc'?")

    return f"{{{', '.join(constraints)}}}", f"{{sortBy: {sort_by}, sortOrder: {order}}}"


def _fetch_titles(url, limit):
    """
    Resolve an IMDb URL to title dicts via the GraphQL API.

    Args:
        url (str): Any supported imdb.com chart, list or search URL
        limit (int): Maximum number of titles to return

    Returns:
        list: Title dicts, empty if the URL is not supported
    """
    parsed = urllib.parse.urlparse(url)
    path = parsed.path.strip("/").lower()

    chart_type = _CHART_TYPES.get(path)
    if chart_type:
        logger.info(f"Fetching IMDb chart {chart_type} (from {url})")
        if chart_type in _TV_CHART_TYPES:
            logger.warning(
                f"{chart_type} holds TV shows, which Jellyseerr movie requests cannot match"
            )
        return _fetch_chart(chart_type, limit)

    segments = path.split("/")
    if len(segments) > 1 and segments[0] == "list":
        list_id = segments[1]
        logger.info(f"Fetching IMDb list {list_id} (from {url})")
        return _fetch_list(list_id, limit)

    if path.startswith("search/title"):
        params = {k: v[0] for k, v in urllib.parse.parse_qs(parsed.query).items()}
        constraints, sort = _build_search_query(params)
        logger.info(f"Fetching IMDb search (from {url})")
        logger.debug(f"IMDb search constraints: {constraints} sort: {sort}")
        return _fetch_search(constraints, sort, limit)

    logger.error(
        f"Unsupported IMDB_URL '{url}'. Supported forms are /chart/<slug>, "
        f"/list/ls<id>/ and /search/title/?<filters>."
    )
    print(f"❌ Unsupported IMDB_URL '{url}'")
    return []


def scrape_imdb_top_movies(limit=MOVIE_LIMIT, url=IMDB_URL):
    """
    Fetch top movie titles from the configured IMDb list.

    Args:
        limit (int): Maximum number of movies to return
        url (str): IMDb chart/list/search URL to read

    Returns:
        list: List of movie titles
    """
    try:
        titles = _fetch_titles(url, limit)
    except Exception as e:
        logger.error(f"Error fetching titles from IMDb: {e}")
        print(f"❌ Error fetching titles from IMDb: {e}")
        return []

    if not titles:
        logger.error("IMDb returned no titles")
        print("❌ IMDb returned no titles")
        return []

    movies = []
    seen_titles = set()
    for entry in titles:
        norm_title = normalize_title(entry["title"])
        if not norm_title or norm_title in seen_titles:
            continue
        seen_titles.add(norm_title)
        movies.append(entry["title"])
        logger.debug(
            f"IMDb title: {entry['title']} ({entry['year']}) "
            f"[{entry['imdb_id']}, {entry['title_type']}, rating={entry['rating']}]"
        )

    logger.info(f"Fetched {len(movies)} unique titles from IMDb: {movies}")
    print(f"Fetched {len(movies)} unique titles from IMDb")
    return movies


if __name__ == "__main__":
    for index, name in enumerate(scrape_imdb_top_movies(), 1):
        print(f"{index}. {name}")
