"""
Scraper for imot.bg listing detail pages.

Fetches each listing URL, parses out structured fields, and appends
one JSON object per line to a local JSONL file. Safe to stop and
re-run: already-scraped listing IDs are skipped on the next run.
"""

import time
import json
import httpx
from pathlib import Path
from bs4 import BeautifulSoup

REQUEST_HEADERS = {"User-Agent": "personal-research-project (tursqkushta@gmail.com)"}
# OUTPUT_FILE_PATH = Path("data/detail_snapshot.jsonl")
OUTPUT_FILE_PATH = Path(
    "/Volumes/workspace/default/real-estate/raw/detail_snapshot.jsonl"
)
SECONDS_BETWEEN_REQUESTS = 1.5


def parse_listing_detail_page(html_text: str, listing_url: str) -> dict:
    """Parse one imot.bg detail page's HTML into a flat dictionary of fields."""
    parsed_page = BeautifulSoup(html_text, "lxml")

    # The page embeds a JSON-LD "Offer" block with price, currency, and
    # the listing's own product info (nested under itemOffered).
    offer_data = {}
    for script_tag in parsed_page.find_all("script", type="application/ld+json"):
        try:
            block_data = json.loads(script_tag.get_text())
        except (json.JSONDecodeError, TypeError):
            continue
        if block_data.get("@type") == "Offer":
            offer_data = block_data
            break

    product_data = offer_data.get("itemOffered") or {}
    seller_data = offer_data.get("seller") or {}

    listing_id = product_data.get("sku")
    sale_price = offer_data.get("price")
    price_currency = offer_data.get("priceCurrency")
    agency_name = seller_data.get("name")

    location_element = parsed_page.select_one(".advHeader .location")
    location_text = (
        location_element.get_text(" ", strip=True) if location_element else None
    )

    # Property parameters (area, plot size, floor, construction type) are
    # rendered as "<label>:<br><strong>value</strong>" divs.
    property_parameters = {}
    for parameter_div in parsed_page.select(".adParams > div"):
        full_text = parameter_div.get_text(strip=True)
        parameter_label = full_text.split(":")[0]
        value_element = parameter_div.find("strong")
        if value_element:
            property_parameters[parameter_label] = value_element.get_text(strip=True)

    description_element = parsed_page.select_one(".moreInfo .text")
    description_text = (
        description_element.get_text("\n", strip=True) if description_element else None
    )

    feature_tags = [
        feature_div.get_text(strip=True)
        for feature_div in parsed_page.select(".carExtri .items > div")
    ]

    # Contains the "last edited" or "published" timestamp plus the view count.
    listing_info_element = parsed_page.select_one(".adPrice .info")
    listing_info_text = (
        listing_info_element.get_text(" ", strip=True) if listing_info_element else None
    )

    return {
        "listing_id": listing_id,
        "url": listing_url,
        "price": sale_price,
        "currency": price_currency,
        "agency_name": agency_name,
        "location_text": location_text,
        "property_parameters": property_parameters,
        "description": description_text,
        "feature_tags": feature_tags,
        "listing_info_text": listing_info_text,
    }


def load_already_scraped_listing_ids() -> set:
    """Read the output file (if it exists) and return the set of listing IDs
    already saved, so a re-run can skip them."""
    if not OUTPUT_FILE_PATH.exists():
        return set()

    already_scraped_ids = set()
    with open(OUTPUT_FILE_PATH, encoding="utf-8") as existing_file:
        for line in existing_file:
            try:
                saved_row = json.loads(line)
            except json.JSONDecodeError:
                continue
            saved_listing_id = saved_row.get("listing_id")
            if saved_listing_id:
                already_scraped_ids.add(saved_listing_id)
    return already_scraped_ids


def scrape_listing_urls(listing_id_url_pairs: list[tuple[str, str]]) -> None:
    """Fetch and parse each (listing_id, url) pair, appending results to
    OUTPUT_FILE_PATH. Pairs whose listing_id is already in the output
    file are skipped."""
    already_scraped_ids = load_already_scraped_listing_ids()
    OUTPUT_FILE_PATH.parent.mkdir(exist_ok=True)

    print(
        f"got {len(listing_id_url_pairs)} listing URLs, "
        f"{len(already_scraped_ids)} already scraped"
    )

    with httpx.Client(
        headers=REQUEST_HEADERS, timeout=20, follow_redirects=True
    ) as http_client, open(OUTPUT_FILE_PATH, "a", encoding="utf-8") as output_file:

        for listing_id, listing_url in listing_id_url_pairs:
            if listing_id in already_scraped_ids:
                continue

            try:
                response = http_client.get(listing_url)
                if response.status_code != 200:
                    print(f"  SKIP {listing_id}: status {response.status_code}")
                    continue

                response.encoding = "windows-1251"
                parsed_row = parse_listing_detail_page(response.text, listing_url)

                output_file.write(json.dumps(parsed_row, ensure_ascii=False) + "\n")
                # output_file.flush()
                already_scraped_ids.add(listing_id)

                print(listing_id, parsed_row["listing_id"], parsed_row["price"], parsed_row["currency"])

            except httpx.HTTPError as error:
                print(f"  ERROR {listing_id}: {error}")

            time.sleep(SECONDS_BETWEEN_REQUESTS)


if __name__ == "__main__":
    from imot_bg_sitemap_discovery import load_pairs_from_file

    listing_id_url_pairs = load_pairs_from_file()
    scrape_listing_urls(listing_id_url_pairs)