
"""Create a self-signed HTTPS development certificate for Jarvis.

The certificate covers localhost plus every LAN address detected on
this machine, so Android Chrome can open https://<laptop-ip>:5173 and
treat it as a secure context (required for microphone access).

Files are written to data/certs/dev.crt and data/certs/dev.key.
start_jarvis.bat and vite.config.ts pick them up automatically on the
next restart.

For Android to fully trust the certificate (no warning, reliable
microphone permission), install dev.crt on the phone:
Settings > Security > Install a certificate > CA certificate.
Otherwise choose to proceed past the browser warning; the connection
is still encrypted and the mic works in most Chrome versions, but the
warning will appear on first visit per session."""

import shutil
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]

CERT_DIR = PROJECT_ROOT / "data" / "certs"
CERT_FILE = CERT_DIR / "dev.crt"
KEY_FILE = CERT_DIR / "dev.key"

# 825 days is the maximum Chrome accepts for publicly trusted certs
# and a convenient long life for a private dev CA.
DAYS = "825"


def lan_ips():
    sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

    try:
        from lan_ip import main as lan_ip_main
    except ImportError:
        return []

    # lan_ip prints a single address; call it directly.
    import io
    import contextlib

    buffer = io.StringIO()

    with contextlib.redirect_stdout(buffer):
        try:
            lan_ip_main()
        except Exception:
            return []

    return [buffer.getvalue().strip()]


def main():
    openssl = shutil.which("openssl")

    if not openssl:
        print("openssl was not found on PATH.")
        print("Install OpenSSL (e.g. via Git for Windows) and rerun:")
        print("  python scripts/make_dev_cert.py")
        return 1

    subject_names = ["DNS:localhost", "IP:127.0.0.1"]

    hostname = socket_gethostname()

    if hostname:
        subject_names.append(f"DNS:{hostname}")

    for address in lan_ips():
        if address and address not in ("127.0.0.1", ""):
            subject_names.append(f"IP:{address}")

    extensions = ",".join(subject_names)

    CERT_DIR.mkdir(parents=True, exist_ok=True)

    command = [
        openssl,
        "req",
        "-x509",
        "-newkey",
        "rsa:2048",
        "-sha256",
        "-days",
        DAYS,
        "-nodes",
        "-keyout",
        str(KEY_FILE),
        "-out",
        str(CERT_FILE),
        "-subj",
        "/CN=Jarvis Dev Certificate",
        "-addext",
        f"subjectAltName={extensions}",
        "-addext",
        "keyUsage=digitalSignature,keyEncipherment",
        "-addext",
        "extendedKeyUsage=serverAuth",
    ]

    completed = subprocess.run(
        command,
        capture_output=True,
        text=True,
    )

    if completed.returncode != 0:
        print("Certificate generation failed:")
        print(completed.stderr)
        return 1

    print(f"Wrote {CERT_FILE}")
    print(f"Wrote {KEY_FILE}")
    print(f"Covered names: {extensions}")
    print()
    print("Restart Jarvis (start_jarvis.bat) to enable HTTPS.")
    print(
        "On your Android phone, install data/certs/dev.crt as a CA "
        "certificate once for warning-free access and microphone "
        "permissions."
    )
    return 0


def socket_gethostname():
    import socket

    try:
        return socket.gethostname()
    except Exception:
        return ""


if __name__ == "__main__":
    sys.exit(main())
