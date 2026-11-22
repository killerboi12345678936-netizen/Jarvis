
"""Wait for the Jarvis backend /health endpoint to answer.

Usage: python scripts/wait_backend.py [scheme]

Exits 0 when healthy, 1 after the retry budget runs out."""

import sys
import time
import urllib.request
import ssl

SCHEME = sys.argv[1] if len(sys.argv) > 1 else "http"

URL = f"{SCHEME}://localhost:8000/health"


def main():
    context = None

    if SCHEME == "https":
        # Dev certificate is self-signed; health is checked locally.
        context = ssl.create_default_context()
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE

    for _ in range(30):
        try:
            with urllib.request.urlopen(URL, timeout=2, context=context) as response:
                if response.status == 200:
                    print("READY")
                    return 0
        except Exception:
            pass

        time.sleep(1)

    print("FAILED")
    return 1


if __name__ == "__main__":
    sys.exit(main())
