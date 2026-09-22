"""
Discover current imot.bg listing URLs from the site's sitemap, filtered
to a chosen scope (offer type, city, property type keyword).

The sitemap index lists ~39 gzipped listing files covering every city
and offer type mixed together, so we download and filter each one.
"""

import gzip
import json
import time
import httpx
from pathlib import Path
from xml.etree import ElementTree

REQUEST_HEADERS = {"User-Agent": "personal-research-project (tursqkushta@gmail.com)"}
SITEMAP_INDEX_URL = "https://www.imot.bg/sitemap/index.xml"
SITEMAP_XML_NAMESPACE = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
SECONDS_BETWEEN_SITEMAP_DOWNLOADS = 1.0
DISCOVERED_PAIRS_FILE_PATH = Path("data/discovered_listing_urls.json")


def get_listing_sitemap_file_urls(http_client: httpx.Client) -> list[str]:
    """Fetch the sitemap index and return only the listings-N.xml.gz URLs
    (skipping agency pages and any entry with a missing/blank <loc>)."""
    response = http_client.get(SITEMAP_INDEX_URL)
    response.raise_for_status()

    index_tree = ElementTree.fromstring(response.content)
    all_location_elements = index_tree.findall(".//sm:loc", SITEMAP_XML_NAMESPACE)

    listing_sitemap_urls = []
    for location_element in all_location_elements:
        sitemap_url = (location_element.text or "").strip()
        if "/listings-" in sitemap_url:
            listing_sitemap_urls.append(sitemap_url)

    return listing_sitemap_urls


def listing_id_from_url(listing_url: str) -> str | None:
    """Pull the listing ID out of a URL like
    https://www.imot.bg/obiava-1j177817033718276-prodava-kashta-...
    -> "1j177817033718276" """
    url_path_segment = listing_url.rsplit("/", 1)[-1]
    if not url_path_segment.startswith("obiava-"):
        return None
    remaining_text = url_path_segment[len("obiava-"):]
    listing_id = remaining_text.split("-", 1)[0]
    return listing_id or None


def url_matches_scope(listing_url: str, required_slug_keywords: list[str]) -> bool:
    """True if every keyword in required_slug_keywords matches a whole
    hyphen-separated segment of the URL slug (not just a substring).
    This avoids false positives like "varna" matching inside "kavarna".
    A keyword may itself contain hyphens (e.g. "prodava-kashta"), in
    which case it must appear as a contiguous run of segments."""
    url_path_segment = listing_url.rsplit("/", 1)[-1].lower()
    slug_segments = url_path_segment.split("-")

    for keyword in required_slug_keywords:
        keyword_segments = keyword.split("-")
        keyword_segment_count = len(keyword_segments)
        found_match = any(
            slug_segments[position : position + keyword_segment_count] == keyword_segments
            for position in range(len(slug_segments) - keyword_segment_count + 1)
        )
        if not found_match:
            return False
    return True


def discover_listing_id_url_pairs(
    required_slug_keywords: list[str],
) -> list[tuple[str, str]]:
    """Download every listings-N.xml.gz file, keep only URLs matching
    required_slug_keywords, and return (listing_id, url) pairs."""
    matched_pairs = []

    with httpx.Client(
        headers=REQUEST_HEADERS, timeout=30, follow_redirects=True
    ) as http_client:
        listing_sitemap_urls = get_listing_sitemap_file_urls(http_client)
        print(f"found {len(listing_sitemap_urls)} listing sitemap files")

        for sitemap_file_number, sitemap_file_url in enumerate(listing_sitemap_urls, start=1):
            response = http_client.get(sitemap_file_url)
            if response.status_code != 200:
                print(f"  SKIP {sitemap_file_url}: status {response.status_code}")
                continue

            decompressed_xml_bytes = gzip.decompress(response.content)
            sitemap_tree = ElementTree.fromstring(decompressed_xml_bytes)
            location_elements = sitemap_tree.findall(".//sm:loc", SITEMAP_XML_NAMESPACE)

            file_match_count = 0
            for location_element in location_elements:
                listing_url = (location_element.text or "").strip()
                if not listing_url:
                    continue
                if url_matches_scope(listing_url, required_slug_keywords):
                    listing_id = listing_id_from_url(listing_url)
                    if listing_id:
                        matched_pairs.append((listing_id, listing_url))
                        file_match_count += 1

            print(
                f"  [{sitemap_file_number}/{len(listing_sitemap_urls)}] "
                f"{sitemap_file_url.rsplit('/', 1)[-1]}: "
                f"{len(location_elements)} urls, {file_match_count} matched"
            )

            time.sleep(SECONDS_BETWEEN_SITEMAP_DOWNLOADS)

    return matched_pairs


def save_pairs_to_file(listing_id_url_pairs: list[tuple[str, str]]) -> None:
    """Save (listing_id, url) pairs as a JSON list of [id, url] lists.
    Deduplicates by listing_id first, keeping the first URL seen for
    each ID (the same listing can appear in more than one sitemap file)."""
    seen_listing_ids = set()
    deduplicated_pairs = []
    for listing_id, listing_url in listing_id_url_pairs:
        if listing_id not in seen_listing_ids:
            seen_listing_ids.add(listing_id)
            deduplicated_pairs.append((listing_id, listing_url))

    duplicate_count = len(listing_id_url_pairs) - len(deduplicated_pairs)
    if duplicate_count:
        print(f"removed {duplicate_count} duplicate listing_ids")

    DISCOVERED_PAIRS_FILE_PATH.parent.mkdir(exist_ok=True)
    with open(DISCOVERED_PAIRS_FILE_PATH, "w", encoding="utf-8") as output_file:
        json.dump(deduplicated_pairs, output_file, ensure_ascii=False, indent=2)
    print(f"saved {len(deduplicated_pairs)} pairs to {DISCOVERED_PAIRS_FILE_PATH}")


def load_pairs_from_file() -> list[tuple[str, str]]:
    """Load (listing_id, url) pairs previously saved by save_pairs_to_file."""
    with open(DISCOVERED_PAIRS_FILE_PATH, encoding="utf-8") as input_file:
        raw_pairs = json.load(input_file)
    return [tuple(pair) for pair in raw_pairs]


if __name__ == "__main__":
    # Sale, houses, Varna. Adjust keywords to change scope.
    houses_for_sale_in_varna = discover_listing_id_url_pairs(
        required_slug_keywords=["prodava-kashta", "varna"]
    )
    print(f"\ntotal matched: {len(houses_for_sale_in_varna)}")
    save_pairs_to_file(houses_for_sale_in_varna)