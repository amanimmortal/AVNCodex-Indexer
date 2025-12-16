import logging
import json
from app.services.f95_client import F95ZoneClient

logging.basicConfig(level=logging.INFO)


def main():
    client = F95ZoneClient()
    if client.login():
        print("Login Success")

    results = client.search_games("Eternum")
    if results:
        print(f"Found {len(results)} results.")
        # Print the first result's keys and raw data
        for r in results:
            if "Eternum" in r.get("title", ""):
                print(f"--- Data for {r.get('title')} ---")
                print(json.dumps(r, indent=2))
    else:
        print("No results found.")


if __name__ == "__main__":
    main()
