"""
Minimal async DNS server for captive portal use.
Redirects all A-record queries to a single IP address.
"""

import logging
import socket

import uasyncio

# Default AP IP assigned by the Pico W in AP mode
_REDIRECT_IP = bytes([192, 168, 4, 1])


def _build_response(request: bytes) -> bytes:
    # Header: reflect TX id | QR+RA flags | copy QDCOUNT | ANCOUNT=1 | rest=0
    header = request[:2] + b"\x81\x80" + request[4:6] + b"\x00\x01\x00\x00\x00\x00"
    question = request[12:]
    # Answer: name ptr → offset 12, type A, class IN, TTL 60s, RDATA = redirect IP
    answer = b"\xc0\x0c\x00\x01\x00\x01\x00\x00\x00\x3c\x00\x04" + _REDIRECT_IP
    return header + question + answer


async def run_server(stop_event: uasyncio.Event, port: int = 53) -> None:
    """
    Async DNS server. Runs until stop_event is set.
    Uses a non-blocking socket and yields to the event loop between polls.
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("", port))
    sock.setblocking(False)
    logging.info("DNS server listening on port %d", port)
    try:
        while not stop_event.is_set():
            try:
                data, addr = sock.recvfrom(512)
                sock.sendto(_build_response(data), addr)
            except OSError:
                await uasyncio.sleep_ms(10)
    finally:
        sock.close()
        logging.info("DNS server stopped.")
