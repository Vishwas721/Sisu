from unittest import mock

import pytest

import discovery
from discovery import make_dedupe_key, build_overpass_query

@pytest.mark.parametrize("url,key", [
    ("http://www.Smile.com/", "smile.com"),
    ("https://smile.com/locations/austin", "smile.com"),
    ("smile.com", "smile.com"),
    ("https://www.instagram.com/SmileATX/", "instagram.com/smileatx"),
    ("https://maps.google.com/?cid=123", "maps.google.com?cid=123"),
])
def test_make_dedupe_key(url, key):
    assert make_dedupe_key(url) == key

def test_overpass_query_has_no_result_limit():
    query = build_overpass_query("Austin", "plumber")
    assert query.rstrip().endswith("out tags;")
    assert '"craft"="plumber"' in query

def _overpass_response(elements):
    response = mock.Mock(status_code=200)
    response.json.return_value = {"elements": elements}
    return response

def test_osm_skips_chains_and_known_businesses():
    elements = [
        {"id": 1, "tags": {"name": "Aspen Dental", "brand": "Aspen Dental", "website": "https://aspendental.com"}},
        {"id": 2, "tags": {"name": "Known", "website": "https://www.known.com"}},
        {"id": 3, "tags": {"name": "New Smile", "website": "http://newsmile.com/home", "phone": "555"}},
    ]
    with mock.patch("discovery.requests.post", return_value=_overpass_response(elements)):
        leads = discovery.discover_osm_leads("Austin", "dentist", limit=10, exclude_keys={"known.com"})
    assert [l["business_name"] for l in leads] == ["New Smile"]
    assert leads[0]["dedupe_key"] == "newsmile.com"
    assert leads[0]["phone"] == "555"

def test_google_places_maps_website_and_no_website_leads():
    payload = {"places": [
        {"id": "abc", "displayName": {"text": "Bob Plumbing"}, "nationalPhoneNumber": "(512) 555-0100",
         "googleMapsUri": "https://maps.google.com/?cid=1", "businessStatus": "OPERATIONAL",
         "rating": 4.6, "userRatingCount": 88},
        {"id": "d", "displayName": {"text": "Smile"}, "websiteUri": "http://www.smile.com/home"},
        {"id": "e", "displayName": {"text": "Closed"}, "businessStatus": "CLOSED_PERMANENTLY"},
    ]}
    response = mock.Mock(status_code=200)
    response.json.return_value = payload
    with mock.patch("discovery.requests.post", return_value=response):
        leads = discovery.discover_google_places("Austin", "plumber", "key")
    by_name = {l["business_name"]: l for l in leads}
    assert set(by_name) == {"Bob Plumbing", "Smile"}
    assert by_name["Bob Plumbing"]["campaign_strategy"] == "no_website"
    assert by_name["Bob Plumbing"]["dedupe_key"] == "gplace:abc"
    assert by_name["Bob Plumbing"]["review_count"] == 88
    assert by_name["Smile"]["dedupe_key"] == "smile.com"
    assert by_name["Smile"]["campaign_strategy"] is None

def test_geocode_unknown_city_uses_nominatim_bbox():
    response = mock.Mock()
    response.json.return_value = [{"boundingbox": ["43.50", "43.69", "-116.36", "-116.09"], "display_name": "Boise"}]
    with mock.patch("discovery.requests.get", return_value=response):
        assert discovery.resolve_bbox("Boise Test City") == "43.5,-116.36,43.69,-116.09"

def test_geocode_raises_for_unknown_place():
    response = mock.Mock()
    response.json.return_value = []
    with mock.patch("discovery.requests.get", return_value=response):
        with pytest.raises(ValueError):
            discovery.resolve_bbox("Nowhere At All 123")

def test_unknown_niche_searches_common_osm_keys():
    query = build_overpass_query("Austin", "tattoo studio")
    for key in ("amenity", "shop", "craft", "office", "healthcare"):
        assert f'"{key}"="tattoo_studio"' in query
