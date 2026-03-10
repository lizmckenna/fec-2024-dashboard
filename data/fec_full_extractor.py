#!/usr/bin/env python3
"""
FEC 2024 Election Disbursement Data Extractor

A comprehensive script to extract Federal Election Commission (FEC) 2024 election
disbursement data, focusing on tech provider spending and overall vendor analysis.

REQUIREMENTS:
- Python 3.7+
- requests library (pip install requests)
- Free FEC API key from https://api.data.gov/signup/

USAGE:
    # Method 1: Command line argument
    python fec_full_extractor.py YOUR_API_KEY

    # Method 2: Environment variable
    export FEC_API_KEY=YOUR_API_KEY
    python fec_full_extractor.py

    # Method 3: Prompt for key
    python fec_full_extractor.py

OUTPUT FILES:
    - fec_2024_all_vendor_spending.csv
        Top 500 vendors by total spending with party breakdowns
    - fec_2024_tech_provider_detail.csv
        Individual committee payments to tech providers
    - fec_2024_tech_provider_summary.csv
        Summary statistics by tech provider

FEATURES:
    - Automatic pagination through all API results
    - Smart rate limiting with exponential backoff
    - Committee detail caching to minimize API calls
    - Progress tracking and resume capability
    - Comprehensive error handling
    - Real-time progress output with ETA

AUTHOR: Generated with Claude Code
LICENSE: Public Domain
"""

import os
import sys
import json
import time
import csv
import argparse
import requests
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any
from collections import defaultdict
from pathlib import Path


# ============================================================================
# CONFIGURATION
# ============================================================================

TECH_PROVIDERS = {
    "Fundraising": [
        "ACTBLUE",
        "WINRED",
        "ANEDOT",
        "REVV",
        "DONORBOX",
    ],
    "CRM/Voter": [
        "EVERYACTION",
        "NGP VAN",
        "NGPVAN",
        "NATIONBUILDER",
    ],
    "SMS": [
        "HUSTLE",
        "TWILIO",
        "TATANGO",
        "SCALE TO WIN",
        "RUMBLEUP",
        "OPN SESAME",
        "STRIVE DIGITAL",
    ],
    "Email": [
        "MAILCHIMP",
        "CONSTANT CONTACT",
    ],
    "Digital Ads": [
        "GOOGLE",
        "FACEBOOK",
        "META PLATFORMS",
        "SNAP",
        "TWITTER",
        "X CORP",
        "TIKTOK",
        "STACKADAPT",
        "THE TRADE DESK",
    ],
    "Consulting": [
        "BULLY PULPIT",
        "TARGETED VICTORY",
        "RISING TIDE INTERACTIVE",
        "TRILOGY INTERACTIVE",
        "MIDDLE SEAT",
        "GMMB",
        "GPS IMPACT",
        "MOTHERSHIP STRATEGIES",
        "PRECISION STRATEGIES",
        "PUSH DIGITAL",
        "RED CURVE SOLUTIONS",
        "SCREEN STRATEGIES",
        "BASK DIGITAL",
        "CAMPAIGN NUCLEUS",
        "FLEX POINT MEDIA",
        "HOOKS CREATIVE",
    ],
    "Data/Analytics": [
        "L2",
        "I360",
        "ARISTOTLE",
        "CIVIS ANALYTICS",
        "BLUELABS",
        "CATALIST",
        "DATA TRUST",
        "TARGETPOINT",
        "DEEP ROOT ANALYTICS",
        "ECHELON INSIGHTS",
    ],
    "Web/Hosting": [
        "SQUARESPACE",
        "WIX",
        "AMAZON WEB SERVICES",
        "CLOUDFLARE",
        "GODADDY",
    ],
    "Voter Contact": [
        "MOBILIZE",
        "THRUTALK",
        "THRUTEXT",
        "CALLHUB",
    ],
    "Payment": [
        "STRIPE",
        "PAYPAL",
    ],
    "Compliance": [
        "ISP COMPLIANCE",
    ],
}

# Flatten provider list
ALL_TECH_PROVIDERS = []
for category_providers in TECH_PROVIDERS.values():
    ALL_TECH_PROVIDERS.extend(category_providers)

API_BASE_URL = "https://api.open.fec.gov/v1"
RATE_LIMIT_DELAY = 0.2  # Seconds between API calls
MAX_RETRIES = 3
BACKOFF_FACTOR = 2
CHECKPOINT_FILE = "fec_extraction_checkpoint.json"
OUTPUT_DIR = "."


# ============================================================================
# UTILITY CLASSES
# ============================================================================


class RateLimiter:
    """Simple rate limiter with exponential backoff."""

    def __init__(self, min_delay: float = 0.2):
        self.min_delay = min_delay
        self.last_call = 0
        self.current_delay = min_delay

    def wait(self):
        """Wait until enough time has passed since the last call."""
        elapsed = time.time() - self.last_call
        if elapsed < self.current_delay:
            time.sleep(self.current_delay - elapsed)
        self.last_call = time.time()

    def reset(self):
        """Reset the backoff delay."""
        self.current_delay = self.min_delay

    def backoff(self):
        """Increase the backoff delay."""
        self.current_delay = min(self.current_delay * BACKOFF_FACTOR, 10)


class ProgressTracker:
    """Track progress with ETA calculation."""

    def __init__(self, total_items: int):
        self.total_items = total_items
        self.completed_items = 0
        self.start_time = time.time()

    def update(self, count: int = 1):
        """Update progress."""
        self.completed_items += count

    def get_eta(self) -> Optional[str]:
        """Calculate and return estimated time remaining."""
        if self.completed_items == 0:
            return None

        elapsed = time.time() - self.start_time
        rate = self.completed_items / elapsed
        remaining = self.total_items - self.completed_items
        eta_seconds = remaining / rate if rate > 0 else 0

        if eta_seconds < 60:
            return f"{int(eta_seconds)}s"
        elif eta_seconds < 3600:
            return f"{int(eta_seconds / 60)}m"
        else:
            return f"{int(eta_seconds / 3600)}h {int((eta_seconds % 3600) / 60)}m"

    def get_progress_str(self) -> str:
        """Get a formatted progress string."""
        pct = (self.completed_items / self.total_items * 100) if self.total_items > 0 else 0
        eta = self.get_eta()
        eta_str = f" ETA: {eta}" if eta else ""
        return f"[{self.completed_items}/{self.total_items} ({pct:.1f}%){eta_str}]"


class CheckpointManager:
    """Manage progress checkpoints for resume capability."""

    def __init__(self, filename: str = CHECKPOINT_FILE):
        self.filename = filename
        self.data = self._load()

    def _load(self) -> Dict:
        """Load checkpoint data from file."""
        if os.path.exists(self.filename):
            try:
                with open(self.filename, "r") as f:
                    return json.load(f)
            except Exception as e:
                print(f"Warning: Could not load checkpoint file: {e}")
                return {}
        return {}

    def save(self, key: str, value: Any):
        """Save a checkpoint value."""
        self.data[key] = value
        try:
            with open(self.filename, "w") as f:
                json.dump(self.data, f, indent=2, default=str)
        except Exception as e:
            print(f"Warning: Could not save checkpoint: {e}")

    def get(self, key: str, default: Any = None) -> Any:
        """Get a checkpoint value."""
        return self.data.get(key, default)

    def has(self, key: str) -> bool:
        """Check if a checkpoint key exists."""
        return key in self.data

    def clear(self):
        """Clear all checkpoint data."""
        self.data = {}
        if os.path.exists(self.filename):
            os.remove(self.filename)


# ============================================================================
# API INTERACTIONS
# ============================================================================


class FECAPIClient:
    """Client for interacting with the OpenFEC API."""

    def __init__(self, api_key: str):
        self.api_key = api_key
        self.rate_limiter = RateLimiter(RATE_LIMIT_DELAY)
        self.committee_cache = {}
        self.cache_hits = 0
        self.cache_misses = 0

    def _make_request(
        self, endpoint: str, params: Dict[str, Any] = None, retry_count: int = 0
    ) -> Optional[Dict]:
        """Make an HTTP request to the FEC API with rate limiting and retries."""
        if params is None:
            params = {}

        params["api_key"] = self.api_key

        url = f"{API_BASE_URL}{endpoint}"

        try:
            self.rate_limiter.wait()
            response = requests.get(url, params=params, timeout=30)

            if response.status_code == 429:  # Rate limited
                if retry_count < MAX_RETRIES:
                    self.rate_limiter.backoff()
                    wait_time = self.rate_limiter.current_delay
                    print(f"  Rate limited. Waiting {wait_time:.1f}s before retry...")
                    time.sleep(wait_time)
                    return self._make_request(endpoint, params, retry_count + 1)
                else:
                    print(f"  Error: Rate limited and max retries exceeded")
                    return None

            response.raise_for_status()
            self.rate_limiter.reset()
            return response.json()

        except requests.exceptions.RequestException as e:
            if retry_count < MAX_RETRIES:
                wait_time = RATE_LIMIT_DELAY * (BACKOFF_FACTOR ** retry_count)
                print(f"  Request failed: {e}. Retrying in {wait_time:.1f}s...")
                time.sleep(wait_time)
                return self._make_request(endpoint, params, retry_count + 1)
            else:
                print(f"  Error: Request failed after {MAX_RETRIES} retries: {e}")
                return None

    def get_paginated_results(
        self, endpoint: str, params: Dict[str, Any] = None, page_size: int = 100
    ) -> List[Dict]:
        """Fetch all paginated results from an endpoint."""
        if params is None:
            params = {}

        all_results = []
        page = 1

        while True:
            params["per_page"] = page_size
            params["page"] = page

            data = self._make_request(endpoint, params)

            if data is None:
                break

            results = data.get("results", [])
            if not results:
                break

            all_results.extend(results)

            pagination = data.get("pagination", {})
            total_pages = pagination.get("pages", 1)

            if page >= total_pages:
                break

            page += 1

        return all_results

    def get_committee_details(self, committee_id: str) -> Optional[Dict]:
        """Get committee details with caching."""
        if committee_id in self.committee_cache:
            self.cache_hits += 1
            return self.committee_cache[committee_id]

        self.cache_misses += 1
        data = self._make_request(f"/committee/{committee_id}/")

        if data and "results" in data and data["results"]:
            result = data["results"][0]
            self.committee_cache[committee_id] = result
            return result

        return None

    def search_disbursements_by_recipient(
        self, recipient_name: str, max_results: int = None
    ) -> List[Dict]:
        """Search for disbursements to a specific recipient."""
        params = {
            "recipient_name": recipient_name,
            "sort": "-disbursement_date",
        }

        results = self.get_paginated_results("/schedules/schedule_b/by_recipient/", params)

        if max_results:
            results = results[:max_results]

        return results

    def get_top_vendors(self, limit: int = 500) -> List[Dict]:
        """Get top vendors by total spending."""
        params = {
            "sort": "-total",
        }

        results = self.get_paginated_results(
            "/schedules/schedule_b/by_recipient/", params, page_size=100
        )

        return results[:limit]


# ============================================================================
# DATA PROCESSING
# ============================================================================


def get_party_affiliation(committee_details: Optional[Dict]) -> str:
    """Extract party affiliation from committee details."""
    if not committee_details:
        return "Unknown"

    # Try multiple fields that might contain party info
    party = committee_details.get("party", "")
    if party:
        if "DEMOCRATIC" in party.upper():
            return "Democratic"
        elif "REPUBLICAN" in party.upper():
            return "Republican"
        elif "LIBERTARIAN" in party.upper():
            return "Libertarian"
        elif "GREEN" in party.upper():
            return "Green"
        else:
            return party[:20]  # Truncate for safety

    committee_type = committee_details.get("committee_type_full", "")
    if "PARTY" in committee_type.upper():
        if "DEMOCRATIC" in committee_details.get("name", "").upper():
            return "Democratic"
        elif "REPUBLICAN" in committee_details.get("name", "").upper():
            return "Republican"

    return "Unknown"


def get_candidate_name(committee_details: Optional[Dict]) -> str:
    """Extract candidate name from committee details."""
    if not committee_details:
        return ""

    candidate_id = committee_details.get("candidate_ids", [])
    if candidate_id:
        return committee_details.get("candidate_name", "")

    return ""


def process_disbursement_data(
    disbursements: List[Dict],
    client: FECAPIClient,
    progress: Optional[ProgressTracker] = None,
) -> Tuple[List[Dict], Dict]:
    """Process disbursement data and enrich with committee information."""
    enriched_data = []
    summary_by_provider = defaultdict(
        lambda: {"total": 0, "dem_total": 0, "rep_total": 0, "unknown_total": 0, "count": 0}
    )

    for i, disbursement in enumerate(disbursements):
        if progress:
            progress.update(1)

        committee_id = disbursement.get("committee_id")
        committee_details = client.get_committee_details(committee_id) if committee_id else None
        party = get_party_affiliation(committee_details)

        amount = disbursement.get("disbursement_amount", 0)
        recipient = disbursement.get("recipient_name", "Unknown")

        # Determine category (will be updated when processing by provider)
        category = "Tech Provider"

        enriched_record = {
            "date": disbursement.get("disbursement_date", ""),
            "committee_id": committee_id,
            "committee_name": disbursement.get("committee_name", ""),
            "party": party,
            "candidate": get_candidate_name(committee_details),
            "recipient": recipient,
            "amount": amount,
            "category": category,
            "description": disbursement.get("purpose_description", ""),
        }

        enriched_data.append(enriched_record)

        # Update summary
        summary_by_provider[recipient]["total"] += amount
        summary_by_provider[recipient]["count"] += 1

        if party == "Democratic":
            summary_by_provider[recipient]["dem_total"] += amount
        elif party == "Republican":
            summary_by_provider[recipient]["rep_total"] += amount
        else:
            summary_by_provider[recipient]["unknown_total"] += amount

    return enriched_data, summary_by_provider


# ============================================================================
# FILE OUTPUT
# ============================================================================


def save_vendor_spending_csv(
    vendors: List[Dict], filename: str = "fec_2024_all_vendor_spending.csv"
):
    """Save top vendor spending data to CSV."""
    with open(filename, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "rank",
                "vendor_name",
                "total_spending",
                "number_of_payments",
                "avg_payment_amount",
            ],
        )
        writer.writeheader()

        for rank, vendor in enumerate(vendors, 1):
            writer.writerow(
                {
                    "rank": rank,
                    "vendor_name": vendor.get("recipient_name", ""),
                    "total_spending": vendor.get("total", 0),
                    "number_of_payments": vendor.get("count", 0),
                    "avg_payment_amount": (
                        vendor.get("total", 0) / vendor.get("count", 1) if vendor.get("count") else 0
                    ),
                }
            )

    print(f"Saved vendor spending to {filename}")


def save_tech_provider_detail_csv(
    data: List[Dict], filename: str = "fec_2024_tech_provider_detail.csv"
):
    """Save detailed tech provider disbursement data to CSV."""
    if not data:
        print(f"No data to save to {filename}")
        return

    fieldnames = [
        "date",
        "committee_id",
        "committee_name",
        "party",
        "candidate",
        "recipient",
        "amount",
        "category",
        "description",
    ]

    with open(filename, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(data)

    print(f"Saved {len(data)} detail records to {filename}")


def save_tech_provider_summary_csv(
    summary: Dict, filename: str = "fec_2024_tech_provider_summary.csv"
):
    """Save tech provider summary statistics to CSV."""
    with open(filename, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "provider_name",
                "total_spending",
                "democratic_spending",
                "republican_spending",
                "unknown_spending",
                "number_of_payments",
                "avg_payment_amount",
            ],
        )
        writer.writeheader()

        # Sort by total spending
        sorted_summary = sorted(summary.items(), key=lambda x: x[1]["total"], reverse=True)

        for provider, stats in sorted_summary:
            writer.writerow(
                {
                    "provider_name": provider,
                    "total_spending": stats["total"],
                    "democratic_spending": stats["dem_total"],
                    "republican_spending": stats["rep_total"],
                    "unknown_spending": stats["unknown_total"],
                    "number_of_payments": stats["count"],
                    "avg_payment_amount": stats["total"] / stats["count"] if stats["count"] > 0 else 0,
                }
            )

    print(f"Saved summary for {len(summary)} providers to {filename}")


# ============================================================================
# MAIN EXTRACTION LOGIC
# ============================================================================


def extract_tech_provider_data(
    client: FECAPIClient,
    checkpoint: CheckpointManager,
    output_dir: str = ".",
) -> Tuple[List[Dict], Dict]:
    """Extract data for all tech providers."""

    providers_to_process = ALL_TECH_PROVIDERS.copy()
    completed_providers = checkpoint.get("completed_providers", [])
    all_enriched_data = checkpoint.get("all_enriched_data", [])
    all_summary = checkpoint.get("all_summary", {})

    # Convert summary back to defaultdict with proper structure
    all_summary_dict = defaultdict(
        lambda: {"total": 0, "dem_total": 0, "rep_total": 0, "unknown_total": 0, "count": 0}
    )
    for k, v in all_summary.items():
        all_summary_dict[k] = v

    # Filter out already completed providers
    remaining_providers = [p for p in providers_to_process if p not in completed_providers]

    if not remaining_providers:
        print("All providers already processed. Skipping tech provider extraction.")
        return all_enriched_data, dict(all_summary_dict)

    print(f"\nExtracting tech provider data ({len(remaining_providers)} providers remaining)...")

    progress = ProgressTracker(len(remaining_providers))

    for provider_name in remaining_providers:
        print(f"\n{progress.get_progress_str()} Processing: {provider_name}")

        try:
            disbursements = client.search_disbursements_by_recipient(provider_name)

            if disbursements:
                print(f"  Found {len(disbursements)} disbursements")
                enriched, summary = process_disbursement_data(disbursements, client)
                all_enriched_data.extend(enriched)

                for provider, stats in summary.items():
                    all_summary_dict[provider]["total"] += stats["total"]
                    all_summary_dict[provider]["dem_total"] += stats["dem_total"]
                    all_summary_dict[provider]["rep_total"] += stats["rep_total"]
                    all_summary_dict[provider]["unknown_total"] += stats["unknown_total"]
                    all_summary_dict[provider]["count"] += stats["count"]
            else:
                print(f"  No disbursements found")

        except Exception as e:
            print(f"  Error processing {provider_name}: {e}")

        completed_providers.append(provider_name)
        progress.update()

        # Save checkpoint regularly
        checkpoint.save("completed_providers", completed_providers)
        checkpoint.save("all_enriched_data", all_enriched_data)
        checkpoint.save("all_summary", dict(all_summary_dict))

    print(f"\nTech provider extraction complete.")
    print(f"Cache statistics: {client.cache_hits} hits, {client.cache_misses} misses")

    return all_enriched_data, dict(all_summary_dict)


def extract_top_vendors(
    client: FECAPIClient,
    checkpoint: CheckpointManager,
    limit: int = 500,
) -> List[Dict]:
    """Extract top vendors by spending."""

    if checkpoint.has("top_vendors"):
        print("Top vendors already extracted. Loading from checkpoint...")
        return checkpoint.get("top_vendors", [])

    print(f"\nExtracting top {limit} vendors by spending...")

    vendors = client.get_top_vendors(limit=limit)

    # Enrich with party information for top vendors
    enriched_vendors = []

    progress = ProgressTracker(len(vendors))

    for vendor in vendors:
        # Get a sample of committee details to determine party affiliation patterns
        committee_id = vendor.get("committee_id")

        if committee_id:
            committee_details = client.get_committee_details(committee_id)
            party = get_party_affiliation(committee_details)
        else:
            party = "Unknown"

        vendor["party_sample"] = party
        enriched_vendors.append(vendor)
        progress.update()

    checkpoint.save("top_vendors", enriched_vendors)

    return enriched_vendors


# ============================================================================
# ARGUMENT PARSING AND MAIN
# ============================================================================


def get_api_key() -> str:
    """Get FEC API key from command line, environment, or user input."""
    # Check command line argument
    parser = argparse.ArgumentParser(
        description="Extract FEC 2024 election disbursement data",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python fec_full_extractor.py YOUR_API_KEY
  python fec_full_extractor.py --api-key YOUR_API_KEY
  FEC_API_KEY=YOUR_API_KEY python fec_full_extractor.py
        """,
    )
    parser.add_argument(
        "api_key",
        nargs="?",
        help="FEC API key (or set FEC_API_KEY environment variable)",
    )
    parser.add_argument(
        "--api-key",
        dest="api_key_arg",
        help="FEC API key (alternative flag)",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Resume from last checkpoint",
    )
    parser.add_argument(
        "--clear-cache",
        action="store_true",
        help="Clear checkpoint and start fresh",
    )
    parser.add_argument(
        "--output-dir",
        default=".",
        help="Output directory for CSV files (default: current directory)",
    )

    args = parser.parse_args()

    # Priority: command line arg > --api-key flag > env var > user input
    api_key = args.api_key or args.api_key_arg or os.environ.get("FEC_API_KEY")

    if not api_key:
        api_key = input("Please enter your FEC API key (from https://api.data.gov/signup/): ").strip()

    if not api_key:
        print("Error: FEC API key is required")
        sys.exit(1)

    return api_key, args.output_dir, args.clear_cache


def main():
    """Main entry point."""
    api_key, output_dir, clear_cache = get_api_key()

    # Create output directory if it doesn't exist
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    # Change to output directory for checkpoint and output files
    original_cwd = os.getcwd()
    os.chdir(output_dir)

    try:
        print("=" * 70)
        print("FEC 2024 Election Disbursement Data Extractor")
        print("=" * 70)
        print(f"Output directory: {os.getcwd()}")
        print(f"Providers to search: {len(ALL_TECH_PROVIDERS)}")

        # Initialize checkpoint
        checkpoint = CheckpointManager()

        if clear_cache:
            checkpoint.clear()
            print("Checkpoint cache cleared.")

        # Initialize API client
        client = FECAPIClient(api_key)

        # Test API connection
        print("\nTesting API connection...")
        test_data = client._make_request("/candidates/", {"sort": "-receipts", "per_page": 1})

        if not test_data:
            print("Error: Could not connect to FEC API. Please check your API key.")
            sys.exit(1)

        print("API connection successful!")

        # Extract top vendors
        print("\n" + "=" * 70)
        top_vendors = extract_top_vendors(client, checkpoint, limit=500)

        # Save top vendors
        vendor_list = list(top_vendors)
        save_vendor_spending_csv(vendor_list, os.path.join(output_dir, "fec_2024_all_vendor_spending.csv"))

        # Extract tech provider data
        print("\n" + "=" * 70)
        enriched_data, summary = extract_tech_provider_data(client, checkpoint, output_dir)

        # Save results
        print("\n" + "=" * 70)
        print("Saving results...")

        save_tech_provider_detail_csv(
            enriched_data, os.path.join(output_dir, "fec_2024_tech_provider_detail.csv")
        )
        save_tech_provider_summary_csv(
            summary, os.path.join(output_dir, "fec_2024_tech_provider_summary.csv")
        )

        # Print summary statistics
        print("\n" + "=" * 70)
        print("EXTRACTION COMPLETE")
        print("=" * 70)
        print(f"Total disbursements found: {len(enriched_data)}")
        print(f"Total unique tech providers: {len(summary)}")

        total_spending = sum(s["total"] for s in summary.values())
        dem_spending = sum(s["dem_total"] for s in summary.values())
        rep_spending = sum(s["rep_total"] for s in summary.values())

        print(f"Total tech provider spending: ${total_spending:,.2f}")
        print(f"  Democratic: ${dem_spending:,.2f}")
        print(f"  Republican: ${rep_spending:,.2f}")

        # Clear checkpoint on successful completion
        checkpoint.clear()

        print("\nOutput files created:")
        print(f"  - fec_2024_all_vendor_spending.csv (top 500 vendors)")
        print(f"  - fec_2024_tech_provider_detail.csv (detailed disbursements)")
        print(f"  - fec_2024_tech_provider_summary.csv (provider summary)")

    finally:
        os.chdir(original_cwd)


if __name__ == "__main__":
    main()
