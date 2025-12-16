import requests
import time
import sys


def check_health(url: str, retries: int = 30, delay: int = 2):
    print(f"Checking health of {url}...")
    for i in range(retries):
        try:
            resp = requests.get(url)
            if resp.status_code == 200:
                print(f"✅ Success! Received 200 OK from {url}")
                print(f"Response: {resp.json()}")
                return True
            else:
                print(f"⚠️ Received status code {resp.status_code}")
        except requests.exceptions.ConnectionError:
            print(f"⏳ Attempt {i + 1}/{retries}: Connection refused. Waiting...")

        time.sleep(delay)

    print("❌ Failed to connect after multiple attempts.")
    return False


if __name__ == "__main__":
    success = check_health("http://localhost:8000/")
    sys.exit(0 if success else 1)
