"""
Scraper for imot.bg listing detail pages.

Fetches each listing URL, parses out structured fields, and maintains:
- one JSON object per listing in detail_snapshot.jsonl containing the
  latest/current state
- one JSON object per price observation/change in price_history.jsonl

Every currently discovered listing is scraped on every run.
Price history is only updated when a listing is new or its price changes.
"""

import time
import json
import httpx
from pathlib import Path
from bs4 import BeautifulSoup

REQUEST_HEADERS = {"User-Agent": "personal-research-project (tursqkushta@gmail.com)"}

OUTPUT_FILE_PATH = Path(
    "/Volumes/workspace/default/real-estate/raw/detail_snapshot.jsonl"
)

PRICE_HISTORY_FILE_PATH = Path(
    "/Volumes/workspace/default/real-estate/raw/price_history.jsonl"
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
        listing_info_element.get_text(" ", strip=True)
        if listing_info_element
        else None
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


def load_existing_listing_rows() -> dict:
    """Load the latest saved row for each listing ID."""
    if not OUTPUT_FILE_PATH.exists():
        return {}

    existing_listing_rows = {}

    with open(OUTPUT_FILE_PATH, encoding="utf-8") as existing_file:
        for line in existing_file:
            try:
                saved_row = json.loads(line)
            except json.JSONDecodeError:
                continue

            saved_listing_id = saved_row.get("listing_id")

            if saved_listing_id:
                existing_listing_rows[saved_listing_id] = saved_row

    return existing_listing_rows


def load_already_scraped_listing_ids() -> set:
    """
    Keep the original function name for compatibility.

    Returns the listing IDs currently present in the snapshot.
    The scraper no longer uses these IDs to skip scraping.
    """
    existing_listing_rows = load_existing_listing_rows()
    return set(existing_listing_rows)


def load_price_history() -> list:
    """Load the existing price history."""
    if not PRICE_HISTORY_FILE_PATH.exists():
        return []

    price_history = []

    with open(PRICE_HISTORY_FILE_PATH, encoding="utf-8") as history_file:
        for line in history_file:
            try:
                saved_row = json.loads(line)
            except json.JSONDecodeError:
                continue

            price_history.append(saved_row)

    return price_history


def scrape_listing_urls(listing_id_url_pairs: list[tuple[str, str]]) -> None:
    """
    Fetch and parse every currently discovered listing.

    detail_snapshot.jsonl contains only the latest/current state.

    price_history.jsonl contains the initial price and every subsequent
    price change for each listing.
    """
    existing_listing_rows = load_existing_listing_rows()
    price_history = load_price_history()

    OUTPUT_FILE_PATH.parent.mkdir(exist_ok=True)

    print(
        f"got {len(listing_id_url_pairs)} listing URLs, "
        f"{len(existing_listing_rows)} existing listings"
    )

    current_listing_rows = {}
    current_price_history = list(price_history)

    with httpx.Client(
        headers=REQUEST_HEADERS, timeout=20, follow_redirects=True
    ) as http_client:

        for listing_id, listing_url in listing_id_url_pairs:
            try:
                response = http_client.get(listing_url)

                if response.status_code != 200:
                    print(f"  SKIP {listing_id}: status {response.status_code}")
                    continue

                response.encoding = "windows-1251"
                parsed_row = parse_listing_detail_page(response.text, listing_url)

                parsed_listing_id = parsed_row.get("listing_id") or listing_id

                # Make sure the sitemap listing ID is retained if the page's
                # JSON-LD does not provide one.
                if not parsed_row.get("listing_id"):
                    parsed_row["listing_id"] = listing_id

                current_listing_rows[parsed_listing_id] = parsed_row

                previous_row = existing_listing_rows.get(parsed_listing_id)

                previous_price = (
                    previous_row.get("price") if previous_row else None
                )
                previous_currency = (
                    previous_row.get("currency") if previous_row else None
                )

                current_price = parsed_row.get("price")
                current_currency = parsed_row.get("currency")

                price_changed = (
                    previous_row is not None
                    and (
                        previous_price != current_price
                        or previous_currency != current_currency
                    )
                )

                new_listing = previous_row is None

                if new_listing or price_changed:
                    current_price_history.append(
                        {
                            "listing_id": parsed_listing_id,
                            "url": parsed_row.get("url"),
                            "price": current_price,
                            "currency": current_currency,
                            "observed_at": time.strftime(
                                "%Y-%m-%dT%H:%M:%S"
                            ),
                        }
                    )

                    if new_listing:
                        print(
                            f"NEW {parsed_listing_id} "
                            f"{current_price} {current_currency}"
                        )
                    else:
                        print(
                            f"PRICE CHANGE {parsed_listing_id}: "
                            f"{previous_price} {previous_currency} -> "
                            f"{current_price} {current_currency}"
                        )
                else:
                    print(
                        f"OK {parsed_listing_id} "
                        f"{current_price} {current_currency}"
                    )

            except httpx.HTTPError as error:
                print(f"  ERROR {listing_id}: {error}")

            time.sleep(SECONDS_BETWEEN_REQUESTS)

    # Write the complete current snapshot in one operation.
    #
    # "w" is used because Databricks Volumes can reject append/seek
    # operations with OSError: [Errno 29] Illegal seek.
    with open(OUTPUT_FILE_PATH, "w", encoding="utf-8") as output_file:
        for parsed_row in current_listing_rows.values():
            output_file.write(
                json.dumps(parsed_row, ensure_ascii=False) + "\n"
            )

    # Write the complete price history in one operation.
    with open(PRICE_HISTORY_FILE_PATH, "w", encoding="utf-8") as history_file:
        for history_row in current_price_history:
            history_file.write(
                json.dumps(history_row, ensure_ascii=False) + "\n"
            )

    print(
        f"\nfinished: {len(current_listing_rows)} current listings"
    )

    print(
        f"price history records: {len(current_price_history)}"
    )


if __name__ == "__main__":
    from imot_bg_sitemap_discovery import load_pairs_from_file

    listing_id_url_pairs = load_pairs_from_file()
    scrape_listing_urls(listing_id_url_pairs)
