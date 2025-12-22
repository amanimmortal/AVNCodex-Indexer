import asyncio
import os
import sys

# Ensure app is in path
sys.path.append(os.getcwd())

from app.services.seed_service import SeedService

# Avoid actual IO
from unittest.mock import MagicMock


async def main():
    print("Initializing Service...")
    s = SeedService()

    import inspect

    sig = inspect.signature(s.seed_loop)
    print(f"Signature: {sig}")

    if "reset" not in sig.parameters:
        print("FAIL: 'reset' parameter missing from signature!")
    else:
        print("PASS: 'reset' parameter present.")

    # Try calling it (will fail logic but should pass arg check)
    print("Calling seed_loop(reset=True)...")
    s.is_running = True  # Prevent immediate return? No, checks is_running at start.
    # Logic: if is_running: return.
    # We want to test reset block which is AFTER is_running check?
    # No, reset check is inside.
    # Wait, my code:
    # if self.is_running: return
    # if reset: ...

    # So if is_running is True, it returns early.
    # s.is_running defaults to False (or what load_state says).
    s.is_running = False

    try:
        # It will try to save state (might fail with WinError)
        # It will try to login (network)
        # We assume it crashes or hangs, so we wrap in timeout or just catch early error.
        # actually we just want to see if TypeError is raised.

        # Mock client to avoid network
        s.client = MagicMock()

        await s.seed_loop(reset=True)
        print("Result: Call successful (logic ran)")
    except TypeError as e:
        print(f"Result: TypeError Caught: {e}")
    except Exception as e:
        print(f"Result: Other Exception: {e}")


if __name__ == "__main__":
    asyncio.run(main())
