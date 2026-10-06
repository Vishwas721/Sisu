import os
from dataclasses import dataclass
from typing import Dict, List
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

@dataclass
class Config:
    # Database settings
    DB_HOST: str = os.getenv("DB_HOST", "127.0.0.1")
    DB_PORT: int = int(os.getenv("DB_PORT", "5432"))
    DB_NAME: str = os.getenv("DB_NAME", "leads_pipeline")
    DB_USER: str = os.getenv("DB_USER", "postgres")
    DB_PASSWORD: str = os.getenv("DB_PASSWORD", "")

    # Ollama settings
    OLLAMA_BASE_URL: str = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
    OLLAMA_MODEL: str = os.getenv("OLLAMA_MODEL", "llama3.2:1b")

    # Scraper settings
    PLAYWRIGHT_HEADLESS: bool = os.getenv("PLAYWRIGHT_HEADLESS", "true").lower() in ("true", "1", "yes")
    PAGE_TIMEOUT_MS: int = int(os.getenv("PAGE_TIMEOUT_MS", "30000"))

    @property
    def dsn(self) -> str:
        return f"postgresql://{self.DB_USER}:{self.DB_PASSWORD}@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"

config = Config()

# ==============================================================================
# Master High-Ticket B2B Service Niches
# Subset of NICHE_TAG_MAPPINGS keys in discovery.py. Aliases ("dental") and institutions that
# never hire freelancers (hospitals, pharmacy chains) are left out of the rotation.
# ==============================================================================
TARGET_NICHES: List[str] = [
    # High-Ticket Trades & Craft Services
    "hvac",
    "roofing",
    "electrician",
    "plumber",
    "landscaping",
    "construction",
    "painter",
    "carpenter",
    "solar",
    "cleaning",
    "pest control",
    "flooring",
    "locksmith",
    "remodeling",
    "pool service",

    # Healthcare, Wellness & Medical
    "dentist",
    "chiropractor",
    "physiotherapy",
    "optometrist",
    "dermatologist",
    "plastic surgery",
    "orthodontist",
    "veterinary",
    "doctor",
    "clinic",

    # Professional & Financial Services
    "real estate",
    "architecture",
    "lawyer",
    "accountant",
    "insurance",
    "financial advisor",
    "marketing agency",
    "property management",
    "moving company",

    # Commercial Services, Lifestyle & Hospitality
    "auto repair",
    "salon",
    "spa",
    "gym",
    "restaurant",
    "cafe",
    "hotel",
]

# ==============================================================================
# Top 100 High-GDP, English-Speaking Market Cities
# Formatted for Overpass API Bounding Box: "South,West,North,East"
# (min_latitude, min_longitude, max_latitude, max_longitude)
# ==============================================================================
TARGET_CITIES: Dict[str, str] = {
    # --- UNITED STATES (55 High-GDP Markets) ---
    "New York": "40.49,-74.26,40.92,-73.70",
    "Los Angeles": "33.70,-118.67,34.34,-118.15",
    "Chicago": "41.64,-87.94,42.02,-87.52",
    "Houston": "29.53,-95.79,30.11,-95.01",
    "Phoenix": "33.29,-112.33,33.92,-111.92",
    "Philadelphia": "39.86,-75.28,40.14,-74.95",
    "San Antonio": "29.21,-98.78,29.70,-98.32",
    "San Diego": "32.53,-117.29,33.11,-116.91",
    "Dallas": "32.61,-96.99,33.02,-96.56",
    "Austin": "30.10,-97.94,30.52,-97.56",
    "San Jose": "37.12,-121.98,37.47,-121.70",
    "San Francisco": "37.70,-122.52,37.83,-122.35",
    "Seattle": "47.49,-122.44,47.74,-122.23",
    "Denver": "39.61,-105.11,39.91,-104.60",
    "Washington DC": "38.79,-77.12,38.99,-76.90",
    "Boston": "42.22,-71.19,42.40,-70.92",
    "Atlanta": "33.64,-84.55,33.89,-84.28",
    "Miami": "25.70,-80.32,25.86,-80.13",
    "Fort Worth": "32.55,-97.53,32.99,-97.03",
    "Charlotte": "35.01,-81.01,35.40,-80.65",
    "Indianapolis": "39.63,-86.33,39.93,-85.93",
    "Columbus": "39.80,-83.21,40.16,-82.77",
    "Nashville": "35.97,-87.06,36.41,-86.51",
    "Baltimore": "39.19,-76.71,39.37,-76.52",
    "Minneapolis": "44.89,-93.33,45.05,-93.19",
    "Tampa": "27.81,-82.56,28.17,-82.36",
    "Orlando": "28.35,-81.51,28.62,-81.18",
    "Raleigh": "35.69,-78.82,35.97,-78.49",
    "Pittsburgh": "40.36,-80.10,40.50,-79.86",
    "Portland": "45.43,-122.84,45.65,-122.47",
    "Las Vegas": "36.11,-115.37,36.34,-115.06",
    "Salt Lake City": "40.69,-112.11,40.85,-111.73",
    "Kansas City": "38.82,-94.77,39.36,-94.38",
    "St. Louis": "38.53,-90.32,38.77,-90.17",
    "Sacramento": "38.43,-121.56,38.69,-121.36",
    "Cincinnati": "39.04,-84.71,39.23,-84.35",
    "Cleveland": "41.39,-81.88,41.60,-81.53",
    "Detroit": "42.25,-83.29,42.45,-82.91",
    "Milwaukee": "42.92,-88.07,43.19,-87.86",
    "Jacksonville": "30.10,-82.05,30.59,-81.39",
    "Oklahoma City": "35.30,-97.71,35.68,-97.31",
    "Richmond": "37.45,-77.60,37.60,-77.38",
    "Louisville": "38.10,-85.90,38.30,-85.52",
    "Hartford": "41.72,-72.72,41.81,-72.64",
    "New Orleans": "29.86,-90.14,30.08,-89.87",
    "Providence": "41.77,-71.47,41.86,-71.37",
    "Memphis": "34.99,-90.14,35.27,-89.70",
    "Buffalo": "42.82,-78.92,42.97,-78.79",
    "Birmingham (AL)": "33.40,-86.91,33.62,-86.64",
    "Rochester": "43.10,-77.68,43.27,-77.53",
    "Bridgeport": "41.15,-73.25,41.24,-73.15",
    "Omaha": "41.18,-96.22,41.37,-95.91",
    "Honolulu": "21.25,-157.92,21.36,-157.75",
    "Albuquerque": "34.98,-106.77,35.22,-106.47",
    "Tucson": "32.05,-111.08,32.32,-110.74",

    # --- UNITED KINGDOM (18 High-GDP Markets) ---
    "London": "51.28,-0.51,51.69,0.33",
    "Manchester": "53.38,-2.35,53.55,-2.14",
    "Birmingham (UK)": "52.38,-2.03,52.57,-1.75",
    "Leeds": "53.72,-1.68,53.89,-1.43",
    "Glasgow": "55.79,-4.39,55.93,-4.13",
    "Edinburgh": "55.88,-3.36,55.99,-3.07",
    "Liverpool": "53.33,-3.02,53.48,-2.85",
    "Bristol": "51.40,-2.69,51.52,-2.51",
    "Sheffield": "53.31,-1.58,53.45,-1.36",
    "Newcastle upon Tyne": "54.95,-1.72,55.04,-1.54",
    "Nottingham": "52.90,-1.24,53.01,-1.10",
    "Belfast": "54.54,-6.02,54.66,-5.84",
    "Cardiff": "51.44,-3.28,51.55,-3.11",
    "Southampton": "50.88,-1.47,50.95,-1.34",
    "Leicester": "52.59,-1.20,52.68,-1.06",
    "Coventry": "52.36,-1.58,52.45,-1.44",
    "Cambridge": "52.17,0.07,52.24,0.18",
    "Oxford": "51.71,-1.30,51.79,-1.19",

    # --- CANADA (15 High-GDP Markets) ---
    "Toronto": "43.58,-79.64,43.86,-79.12",
    "Montreal": "45.41,-73.98,45.71,-73.47",
    "Vancouver": "49.20,-123.27,49.32,-123.02",
    "Calgary": "50.84,-114.32,51.21,-113.86",
    "Edmonton": "53.39,-113.71,53.66,-113.27",
    "Ottawa": "45.24,-76.01,45.54,-75.49",
    "Winnipeg": "49.77,-97.35,49.99,-96.95",
    "Quebec City": "46.73,-71.43,46.91,-71.16",
    "Hamilton": "43.16,-80.03,43.34,-79.72",
    "Kitchener": "43.38,-80.57,43.51,-80.41",
    "London (ON)": "42.90,-81.38,43.07,-81.14",
    "Victoria": "48.40,-123.42,48.46,-123.32",
    "Halifax": "44.60,-63.68,44.71,-63.53",
    "Mississauga": "43.49,-79.77,43.74,-79.54",
    "Brampton": "43.62,-79.86,43.82,-79.64",

    # --- AUSTRALIA (12 High-GDP Markets) ---
    "Sydney": "-34.02,151.05,-33.72,151.30",
    "Melbourne": "-37.92,144.85,-37.70,145.08",
    "Brisbane": "-27.56,152.92,-27.38,153.14",
    "Perth": "-32.06,115.75,-31.85,115.98",
    "Adelaide": "-35.03,138.50,-34.84,138.69",
    "Gold Coast": "-28.17,153.30,-27.88,153.46",
    "Canberra": "-35.39,149.03,-35.18,149.21",
    "Newcastle (AU)": "-32.97,151.68,-32.87,151.81",
    "Wollongong": "-34.48,150.83,-34.36,150.93",
    "Hobart": "-42.93,147.25,-42.82,147.38",
    "Geelong": "-38.20,144.30,-38.10,144.42",
    "Sunshine Coast": "-26.74,153.04,-26.58,153.15"
}
