
"""Print this machine's primary LAN IP address (e.g. 192.168.1.42).

Used by start_jarvis.bat to show the mobile access URL. The UDP
connect trick finds the interface the OS would route through without
sending any packets."""

import socket


def main():
    ip = ""

    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.settimeout(0.5)
            sock.connect(("8.8.8.8", 80))
            ip = sock.getsockname()[0]
    except OSError:
        pass

    if not ip:
        try:
            ip = socket.gethostbyname(socket.gethostname())
        except OSError:
            ip = "127.0.0.1"

    print(ip)


if __name__ == "__main__":
    main()
