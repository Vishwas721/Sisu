import json
import logging
import threading
import time
import urllib.parse
from pathlib import Path
from typing import List, Dict, Any, Optional, Set
import requests

logger = logging.getLogger("leads_pipeline.discovery")

OVERPASS_ENDPOINTS = [
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass-api.de/api/interpreter"
]

# ==============================================================================
# Comprehensive OpenStreetMap Niche & Category Tag Mappings
# Maps high-ticket B2B service niches to precise OSM amenity/craft/office tags
# ==============================================================================
NICHE_TAG_MAPPINGS = {
    # --- High-Ticket Home & Trade Services ---
    "hvac": [('craft', 'hvac'), ('craft', 'heating_contractor'), ('craft', 'air_conditioning')],
    "roofing": [('craft', 'roofer'), ('craft', 'roofing')],
    "electrician": [('craft', 'electrician')],
    "plumber": [('craft', 'plumber')],
    "landscaping": [('craft', 'gardener'), ('craft', 'landscaper')],
    "construction": [('craft', 'builder'), ('office', 'construction_company')],
    "painter": [('craft', 'painter')],
    "carpenter": [('craft', 'carpenter'), ('craft', 'joiner')],
    "solar": [('craft', 'photovoltaic'), ('office', 'energy_supplier')],
    "cleaning": [('craft', 'cleaning'), ('office', 'cleaning')],
    "pest control": [('craft', 'pest_control')],
    "flooring": [('craft', 'floorer'), ('craft', 'parquet_layer')],
    "locksmith": [('craft', 'locksmith'), ('shop', 'locksmith')],
    "remodeling": [('craft', 'builder'), ('craft', 'renovation')],
    "pool service": [('craft', 'swimming_pool'), ('shop', 'swimming_pool')],

    # --- Healthcare & Medical Practices ---
    "dentist": [('amenity', 'dentist'), ('healthcare', 'dentist')],
    "dental": [('amenity', 'dentist'), ('healthcare', 'dentist')],
    "dental clinic": [('amenity', 'dentist'), ('healthcare', 'dentist')],
    "chiropractor": [('healthcare', 'chiropractor'), ('amenity', 'clinic')],
    "physiotherapy": [('healthcare', 'physiotherapist'), ('healthcare', 'physiotherapy')],
    "optometrist": [('healthcare', 'optometrist'), ('shop', 'optician')],
    "dermatologist": [('healthcare', 'dermatologist'), ('amenity', 'doctors')],
    "plastic surgery": [('healthcare', 'plastic_surgery'), ('amenity', 'clinic')],
    "orthodontist": [('healthcare', 'orthodontist'), ('amenity', 'dentist')],
    "veterinary": [('amenity', 'veterinary'), ('healthcare', 'veterinary')],
    "doctor": [('amenity', 'doctors'), ('healthcare', 'doctor')],
    "clinic": [('amenity', 'clinic'), ('healthcare', 'clinic')],
    "hospital": [('amenity', 'hospital'), ('healthcare', 'hospital')],
    "pharmacy": [('amenity', 'pharmacy'), ('healthcare', 'pharmacy')],

    # --- Professional & Financial Services ---
    "real estate": [('office', 'estate_agent'), ('shop', 'estate_agent')],
    "architecture": [('office', 'architect')],
    "lawyer": [('office', 'lawyer'), ('office', 'attorney')],
    "accountant": [('office', 'accountant'), ('office', 'financial')],
    "insurance": [('office', 'insurance')],
    "financial advisor": [('office', 'financial_advisor'), ('office', 'financial')],
    "marketing agency": [('office', 'advertising_agency'), ('office', 'marketing')],
    "property management": [('office', 'property_management')],
    "moving company": [('craft', 'mover'), ('office', 'logistics')],

    # --- Automotive, Wellness & Hospitality ---
    "auto repair": [('shop', 'car_repair'), ('craft', 'car_repair')],
    "salon": [('shop', 'hairdresser'), ('shop', 'beauty')],
    "spa": [('leisure', 'spa'), ('amenity', 'spa')],
    "gym": [('leisure', 'fitness_centre')],
    "restaurant": [('amenity', 'restaurant')],
    "cafe": [('amenity', 'cafe')],
    "hotel": [('tourism', 'hotel')],
}

def normalize_url(url: str) -> str:
    """Ensure URL has valid protocol and standard format."""
    url = url.strip()
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    parsed = urllib.parse.urlparse(url)
    cleaned = urllib.parse.urlunparse((parsed.scheme, parsed.netloc, parsed.path, parsed.params, parsed.query, ""))
    return cleaned.rstrip("/")

def make_dedupe_key(url: str) -> str:
    """
    Identity of a business for deduplication. Websites collapse to their bare domain so
    http/https, www, trailing paths and location pages all match; social profiles keep their path.
    """
    parsed = urllib.parse.urlparse(normalize_url(url))
    host = parsed.netloc.lower().split(":")[0]
    if host.startswith("www."):
        host = host[4:]
    if any(host.endswith(s) for s in ("instagram.com", "facebook.com", "fb.com")):
        return f"{host}{parsed.path.lower().rstrip('/')}"
    if host.endswith("google.com"):
        # Maps links identify the place in the query string (?cid=...)
        return f"{host}{parsed.path.rstrip('/')}?{parsed.query}"
    return host

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
# Nominatim usage policy: at most one request per second
NOMINATIM_MIN_INTERVAL = 1.1
# Looked-up cities are remembered across runs so each city is geocoded once
GEOCODE_CACHE_FILE = Path(__file__).parent / "geocode_cache.json"
_nominatim_lock = threading.Lock()
_last_nominatim_call = 0.0

def _load_geocode_cache() -> Dict[str, str]:
    try:
        return json.loads(GEOCODE_CACHE_FILE.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

def _save_geocode_cache(cache: Dict[str, str]) -> None:
    try:
        GEOCODE_CACHE_FILE.write_text(json.dumps(cache, indent=2, sort_keys=True), encoding="utf-8")
    except OSError as e:
        logger.warning(f"Could not save geocode cache: {e}")

def _nominatim_get(params: Dict[str, Any]) -> List[Dict[str, Any]]:
    """GET Nominatim, never more than once per NOMINATIM_MIN_INTERVAL seconds."""
    global _last_nominatim_call
    with _nominatim_lock:
        wait = _last_nominatim_call + NOMINATIM_MIN_INTERVAL - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        try:
            response = requests.get(
                NOMINATIM_URL,
                params=params,
                headers={"User-Agent": "SisuLeadPipeline/1.0 (+https://github.com/Vishwas721/Sisu)"},
                timeout=20,
            )
        finally:
            _last_nominatim_call = time.monotonic()
    response.raise_for_status()
    return response.json()

def geocode_city(city: str) -> str:
    """
    Bounding box "South,West,North,East" for any city name via OpenStreetMap Nominatim.
    Settlements are preferred so "Springfield" doesn't resolve to a county or state.
    Raises ValueError if nothing matches.
    """
    key = city.lower().strip()
    cache = _load_geocode_cache()
    if key in cache:
        return cache[key]

    results: List[Dict[str, Any]] = []
    for params in ({"featureType": "settlement"}, {}):
        results = _nominatim_get({"q": city, "format": "jsonv2", "limit": 1, **params})
        if results:
            break
    if not results:
        raise ValueError(f"Could not find a city called '{city}'")

    # Nominatim's boundingbox is [south, north, west, east]
    south, north, west, east = (float(x) for x in results[0]["boundingbox"])
    if north - south > 2 or east - west > 2:
        logger.warning(f"'{city}' resolved to a very large area ({results[0].get('display_name')}); discovery may be slow")
    bbox = f"{south},{west},{north},{east}"
    logger.info(f"Geocoded '{city}' -> {results[0].get('display_name')} [{bbox}]")
    cache[key] = bbox
    _save_geocode_cache(cache)
    return bbox

def resolve_bbox(city: str, bbox: Optional[str] = None) -> str:
    """Bounding box "South,West,North,East": TARGET_CITIES first, otherwise geocoded."""
    if bbox:
        return bbox
    from config import TARGET_CITIES
    for name, coords in TARGET_CITIES.items():
        if name.lower() == city.lower().strip():
            return coords
    return geocode_city(city)

def build_overpass_query(city: str, niche: str, bbox: Optional[str] = None) -> str:
    """
    Construct Overpass QL query accepting businesses with EITHER a website,
    contact:instagram, OR contact:facebook tag.
    """
    niche_lower = niche.lower().strip()
    # Typed niches outside the mapping ("tattoo", "bakery") are tried across the usual OSM keys
    slug = niche_lower.replace(" ", "_")
    fallback = [(key, slug) for key in ("amenity", "shop", "craft", "office", "healthcare")]
    tag_pairs = NICHE_TAG_MAPPINGS.get(niche_lower, fallback)
    bbox = resolve_bbox(city, bbox)

    filters = []
    # Accept businesses that have EITHER a website, contact:instagram, OR contact:facebook tag
    for k, v in tag_pairs:
        # Website queries
        filters.append(f'node["{k}"="{v}"]["website"]({bbox});')
        filters.append(f'way["{k}"="{v}"]["website"]({bbox});')
        filters.append(f'node["{k}"="{v}"]["contact:website"]({bbox});')
        filters.append(f'way["{k}"="{v}"]["contact:website"]({bbox});')
        # Instagram queries
        filters.append(f'node["{k}"="{v}"]["contact:instagram"]({bbox});')
        filters.append(f'way["{k}"="{v}"]["contact:instagram"]({bbox});')
        filters.append(f'node["{k}"="{v}"]["instagram"]({bbox});')
        filters.append(f'way["{k}"="{v}"]["instagram"]({bbox});')
        # Facebook queries
        filters.append(f'node["{k}"="{v}"]["contact:facebook"]({bbox});')
        filters.append(f'way["{k}"="{v}"]["contact:facebook"]({bbox});')
        filters.append(f'node["{k}"="{v}"]["facebook"]({bbox});')
        filters.append(f'way["{k}"="{v}"]["facebook"]({bbox});')

    filter_block = "\n  ".join(filters)

    # No result limit: Overpass returns elements in a fixed order, so a limit would hand back the
    # same first N businesses every run. Tags-only output stays small even for big cities.
    query = f"""[out:json][timeout:90];
(
  {filter_block}
);
out tags;"""
    return query

def discover_osm_leads(
    city: str,
    niche: str,
    limit: int = 10,
    bbox: Optional[str] = None,
    exclude_keys: Optional[Set[str]] = None
) -> List[Dict[str, Any]]:
    """
    Query Overpass API for businesses in given city and niche that include EITHER
    website, contact:instagram, or contact:facebook.
    Assigns campaign_strategy = 'no_website' if social links exist but no website.
    Businesses whose dedupe key is in exclude_keys (already in the database) are skipped
    before the limit is applied, so each run reaches further into the city.
    """
    exclude_keys = exclude_keys or set()
    logger.info(f"Discovering leads for niche='{niche}' in city='{city}' (limit={limit}, bbox={bbox})...")
    query = build_overpass_query(city, niche, bbox=bbox)

    # Overpass usage policy asks clients to identify themselves rather than pose as a browser
    headers = {
        "User-Agent": "SisuLeadPipeline/1.0 (+https://github.com/Vishwas721/Sisu)",
        "Accept": "application/json"
    }

    raw_elements = []
    for endpoint in OVERPASS_ENDPOINTS:
        try:
            logger.debug(f"Querying Overpass endpoint: {endpoint}")
            response = requests.post(endpoint, data={"data": query}, headers=headers, timeout=100)
            if response.status_code == 200:
                data = response.json()
                raw_elements = data.get("elements", [])
                logger.info(f"Successfully retrieved {len(raw_elements)} raw elements from {endpoint}")
                break
            else:
                logger.warning(f"Endpoint {endpoint} returned status {response.status_code}. Trying next mirror...")
        except Exception as e:
            logger.warning(f"Request failed for {endpoint}: {e}. Trying next mirror...")

    leads: List[Dict[str, Any]] = []
    seen_urls = set()

    for element in raw_elements:
        tags = element.get("tags", {})
        website = tags.get("website") or tags.get("contact:website")
        instagram = tags.get("contact:instagram") or tags.get("instagram")
        facebook = tags.get("contact:facebook") or tags.get("facebook")

        # Must have EITHER website, contact:instagram, OR contact:facebook
        if not website and not instagram and not facebook:
            continue

        # Chains and franchises (Aspen Dental, Jiffy Lube...) buy websites from head office
        if tags.get("brand") or tags.get("brand:wikidata"):
            continue

        # Format social links if present
        instagram_url = None
        if instagram:
            inst = instagram.strip()
            if inst.startswith(("http://", "https://")):
                instagram_url = normalize_url(inst)
            else:
                instagram_url = f"https://www.instagram.com/{inst.lstrip('@')}"

        facebook_url = None
        if facebook:
            fb = facebook.strip()
            if fb.startswith(("http://", "https://")):
                facebook_url = normalize_url(fb)
            else:
                facebook_url = f"https://www.facebook.com/{fb.lstrip('/')}"

        # Strategy assignment and primary URL normalization
        if website:
            norm_url = normalize_url(website)
            campaign_strategy = None  # Will be determined by extractor.py (legacy_redesign or ai_automation)
        else:
            # Business with social media links but NO website URL
            norm_url = instagram_url or facebook_url
            campaign_strategy = "no_website"

        if not norm_url:
            continue
        dedupe_key = make_dedupe_key(norm_url)
        if dedupe_key in seen_urls or dedupe_key in exclude_keys:
            continue
        seen_urls.add(dedupe_key)

        name = tags.get("name") or tags.get("operator") or tags.get("brand") or "Local Business"
        osm_id = element.get("id")
        phone = tags.get("phone") or tags.get("contact:phone")
        email = tags.get("email") or tags.get("contact:email")

        initial_emails = [email.strip()] if email else []

        lead = {
            "business_name": name,
            "website_url": norm_url,
            "dedupe_key": dedupe_key,
            "city": city,
            "niche": niche,
            "initial_emails": initial_emails,
            "phone": phone,
            "instagram_url": instagram_url,
            "facebook_url": facebook_url,
            "campaign_strategy": campaign_strategy,
            "osm_id": osm_id,
            "osm_tags": tags,
            "source": "osm",
        }
        leads.append(lead)

        if len(leads) >= limit:
            break

    logger.info(f"Filtered {len(leads)} valid businesses for niche='{niche}' in '{city}'.")
    return leads

GOOGLE_PLACES_URL = "https://places.googleapis.com/v1/places:searchText"
GOOGLE_PLACES_FIELDS = ",".join([
    "places.id", "places.displayName", "places.websiteUri", "places.nationalPhoneNumber",
    "places.internationalPhoneNumber", "places.rating", "places.userRatingCount",
    "places.formattedAddress", "places.businessStatus", "places.googleMapsUri", "nextPageToken",
])
# Text Search returns at most 3 pages of 20
GOOGLE_MAX_PAGES = 3

def discover_google_places(
    city: str,
    niche: str,
    api_key: str,
    bbox: Optional[str] = None,
    exclude_keys: Optional[Set[str]] = None
) -> List[Dict[str, Any]]:
    """
    Query Google Places Text Search (New) for "<niche> in <city>", restricted to the city's bbox.
    Far better coverage than OSM, and returns phone, rating and review count. Places without a
    websiteUri become 'no_website' leads reachable by phone.
    """
    exclude_keys = exclude_keys or set()
    south, west, north, east = (float(x) for x in resolve_bbox(city, bbox).split(","))
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": api_key,
        "X-Goog-FieldMask": GOOGLE_PLACES_FIELDS,
    }
    body: Dict[str, Any] = {
        "textQuery": f"{niche} in {city}",
        "pageSize": 20,
        "locationRestriction": {"rectangle": {
            "low": {"latitude": south, "longitude": west},
            "high": {"latitude": north, "longitude": east},
        }},
    }

    places: List[Dict[str, Any]] = []
    for _ in range(GOOGLE_MAX_PAGES):
        try:
            response = requests.post(GOOGLE_PLACES_URL, json=body, headers=headers, timeout=30)
        except requests.RequestException as e:
            logger.warning(f"Google Places request failed: {e}")
            break
        if response.status_code != 200:
            logger.warning(f"Google Places returned HTTP {response.status_code}: {response.text[:300]}")
            break
        data = response.json()
        places.extend(data.get("places", []))
        if not data.get("nextPageToken"):
            break
        body["pageToken"] = data["nextPageToken"]

    leads: List[Dict[str, Any]] = []
    for place in places:
        if place.get("businessStatus", "OPERATIONAL") != "OPERATIONAL":
            continue
        website = place.get("websiteUri")
        if website:
            website_url = normalize_url(website)
            dedupe_key = make_dedupe_key(website_url)
            campaign_strategy = None
        else:
            website_url = place.get("googleMapsUri") or f"https://www.google.com/maps/place/?q=place_id:{place['id']}"
            dedupe_key = f"gplace:{place['id']}"
            campaign_strategy = "no_website"
        if dedupe_key in exclude_keys:
            continue

        leads.append({
            "business_name": (place.get("displayName") or {}).get("text", "Local Business"),
            "website_url": website_url,
            "dedupe_key": dedupe_key,
            "city": city,
            "niche": niche,
            "initial_emails": [],
            "phone": place.get("internationalPhoneNumber") or place.get("nationalPhoneNumber"),
            "address": place.get("formattedAddress"),
            "rating": place.get("rating"),
            "review_count": place.get("userRatingCount"),
            "instagram_url": None,
            "facebook_url": None,
            "campaign_strategy": campaign_strategy,
            "source": "google",
        })

    logger.info(f"Google Places: {len(leads)} new businesses for '{niche}' in '{city}' ({len(places)} returned).")
    return leads

def discover_leads(
    city: str,
    niche: str,
    limit: int = 10,
    bbox: Optional[str] = None,
    exclude_keys: Optional[Set[str]] = None
) -> List[Dict[str, Any]]:
    """
    Combine Google Places (when GOOGLE_PLACES_API_KEY is set) with OpenStreetMap, deduplicated
    and capped at limit. Google results come first: fresher data, and they include phone numbers.
    """
    from config import config
    seen = set(exclude_keys or set())
    combined: List[Dict[str, Any]] = []

    if config.GOOGLE_PLACES_API_KEY:
        for lead in discover_google_places(city, niche, config.GOOGLE_PLACES_API_KEY, bbox=bbox, exclude_keys=seen):
            if lead["dedupe_key"] not in seen:
                seen.add(lead["dedupe_key"])
                combined.append(lead)

    if len(combined) < limit:
        for lead in discover_osm_leads(city, niche, limit=limit - len(combined), bbox=bbox, exclude_keys=seen):
            if lead["dedupe_key"] not in seen:
                seen.add(lead["dedupe_key"])
                combined.append(lead)

    return combined[:limit]

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    results = discover_leads(city="Austin", niche="hvac", limit=3)
    print("\n--- TEST RESULT ---")
    for r in results:
        print(f"Name: {r['business_name']} | URL: {r['website_url']} | Strategy: {r['campaign_strategy']}")