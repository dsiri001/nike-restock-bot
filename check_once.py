"""
Runs ONE stock check for the Nike Norway 2026 Home Jersey (IB5170-673).
GitHub Actions runs this every ~10 minutes. state.json remembers what
was in stock last time so you only get pinged when something changes.
"""

import json
import os
import sys
import requests

STYLE_COLOR = "IB5170-673"
PRODUCT_URL = ("https://www.nike.com/t/norway-national-team-2026-match-home-mens-"
               "nike-aero-fit-soccer-jersey-FOyGGFwA/IB5170-673")
STATE_FILE = "state.json"

NTFY_TOPIC = os.environ["NTFY_TOPIC"]
SIZES = {s.strip() for s in os.environ.get("SIZES", "").split(",") if s.strip()}
TEST_MODE = os.environ.get("TEST_MODE", "false").lower() == "true"

FEED_URL = (
    "https://api.nike.com/product_feed/threads/v2/"
    "?filter=marketplace(US)&filter=language(en)"
    "&filter=channelId(d9a5bc42-4b9c-4976-858a-f159cf99c647)"
    f"&filter=productInfo.merchProduct.styleColor({STYLE_COLOR})"
)
HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/128.0 Safari/537.36"),
    "Accept": "application/json",
}


def notify(title, message, priority="high"):
    requests.post(
        f"https://ntfy.sh/{NTFY_TOPIC}",
        data=message.encode("utf-8"),
        headers={"Title": title, "Priority": priority,
                 "Click": PRODUCT_URL, "Tags": "soccer"},
        timeout=20,
    )
    print("NOTIFIED:", title, "|", message)


def load_state():
    try:
        with open(STATE_FILE) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"alerted_sizes": [], "consecutive_failures": 0}


def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2, sort_keys=True)
        f.write("\n")


def get_in_stock_sizes():
    r = requests.get(FEED_URL, headers=HEADERS, timeout=20)
    r.raise_for_status()
    in_stock = set()
    for obj in r.json().get("objects", []):
        for info in obj.get("productInfo", []):
            if info.get("merchProduct", {}).get("styleColor") != STYLE_COLOR:
                continue
            sku_to_size = {s.get("id"): s.get("nikeSize") for s in info.get("skus", [])}
            for a in info.get("availableSkus", []):
                if a.get("available") and a.get("level", "").upper() != "OOS":
                    size = sku_to_size.get(a.get("skuId") or a.get("id"))
                    if size:
                        in_stock.add(size)
    return in_stock


def main():
    if TEST_MODE:
        notify("Test notification", "Your Nike restock bot is set up and working.", "default")
        return

    state = load_state()

    try:
        available = get_in_stock_sizes()
    except Exception as e:
        state["consecutive_failures"] = state.get("consecutive_failures", 0) + 1
        print("Check failed:", e)
        # Ping once if it has been failing for about an hour
        if state["consecutive_failures"] == 6:
            notify("Restock bot is having trouble",
                   "Nike checks have failed 6 times in a row. Nike may be blocking "
                   "GitHub's servers. Check the Actions log.", "default")
        save_state(state)
        sys.exit(0)  # don't mark the run as failed, avoids a flood of emails

    state["consecutive_failures"] = 0
    matches = (available & SIZES) if SIZES else available
    new = matches - set(state.get("alerted_sizes", []))
    print("Available:", sorted(available) or "none", "| Watching:", sorted(SIZES) or "any")

    if new:
        notify("Norway jersey restocked!",
               f"In stock now: {', '.join(sorted(new))}. Tap to open.")

    state["alerted_sizes"] = sorted(matches)  # resets if it sells out again
    save_state(state)


if __name__ == "__main__":
    main()
