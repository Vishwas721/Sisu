import logging
import urllib.parse
from typing import List, Dict, Any, Optional
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

def build_overpass_query(city: str, niche: str, limit: int = 15, bbox: Optional[str] = None) -> str:
    """
    Construct Overpass QL query accepting businesses with EITHER a website,
    contact:instagram, OR contact:facebook tag.
    """
    niche_lower = niche.lower().strip()
    tag_pairs = NICHE_TAG_MAPPINGS.get(niche_lower, [('amenity', niche_lower)])

    if not bbox:
        try:
            from config import TARGET_CITIES
            bbox = TARGET_CITIES.get(city)
            if not bbox:
                for name, coords in TARGET_CITIES.items():
                    if name.lower() == city.lower() or city.lower() in name.lower():
                        bbox = coords
                        break
        except ImportError:
            bbox = None

    if not bbox:
        # Fallback bounding box for Central Austin, TX (South, West, North, East)
        bbox = "30.25,-97.76,30.30,-97.70"

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

    query = f"""[out:json][timeout:25];
(
  {filter_block}
);
out tags {limit};"""
    return query

def discover_leads(city: str, niche: str, limit: int = 10, bbox: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Query Overpass API for businesses in given city and niche that include EITHER
    website, contact:instagram, or contact:facebook.
    Assigns campaign_strategy = 'no_website' if social links exist but no website.
    """
    logger.info(f"Discovering leads for niche='{niche}' in city='{city}' (limit={limit}, bbox={bbox})...")
    query = build_overpass_query(city, niche, limit, bbox=bbox)

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "*/*"
    }

    raw_elements = []
    for endpoint in OVERPASS_ENDPOINTS:
        try:
            logger.debug(f"Querying Overpass endpoint: {endpoint}")
            response = requests.post(endpoint, data={"data": query}, headers=headers, timeout=25)
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
        if dedupe_key in seen_urls:
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
            "osm_tags": tags
        }
        leads.append(lead)

        if len(leads) >= limit:
            break

    logger.info(f"Filtered {len(leads)} valid businesses for niche='{niche}' in '{city}'.")
    return leads

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    results = discover_leads(city="Austin", niche="hvac", limit=3)
    print("\n--- TEST RESULT ---")
    for r in results:
        print(f"Name: {r['business_name']} | URL: {r['website_url']} | Strategy: {r['campaign_strategy']}")