from __future__ import annotations

import json
import os
import socket
import ssl
import subprocess
from pathlib import Path
from typing import Any
from urllib import request

DEFAULT_FLASK_PORT = int(os.getenv("PIKIT_FLASK_PORT", "5050"))
DEFAULT_TRANSFER_PORT = int(os.getenv("PIKIT_TRANSFER_PORT", "55055"))
DEFAULT_CERT_PATH = Path(os.getenv("PIKIT_CERT", "storage/pikit.crt"))
DEFAULT_KEY_PATH = Path(os.getenv("PIKIT_KEY", "storage/pikit.key"))
DEFAULT_TIMEOUT = float(os.getenv("PIKIT_TRANSFER_TIMEOUT", "15"))
MAX_MESSAGE_BYTES = int(os.getenv("PIKIT_TRANSFER_MAX_BYTES", "131072"))


def ensure_local_tls_material(
    cert_path: Path = DEFAULT_CERT_PATH,
    key_path: Path = DEFAULT_KEY_PATH,
) -> tuple[Path, Path]:
    cert_path = Path(cert_path)
    key_path = Path(key_path)
    if cert_path.exists() and key_path.exists():
        return cert_path, key_path

    cert_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "openssl",
        "req",
        "-x509",
        "-newkey",
        "rsa:2048",
        "-sha256",
        "-days",
        "3650",
        "-nodes",
        "-keyout",
        str(key_path),
        "-out",
        str(cert_path),
        "-subj",
        "/CN=localhost",
    ]
    subprocess.run(cmd, check=True, capture_output=True, text=True)
    return cert_path, key_path


def create_server_ssl_context(
    cert_path: Path = DEFAULT_CERT_PATH,
    key_path: Path = DEFAULT_KEY_PATH,
) -> ssl.SSLContext:
    cert_path, key_path = ensure_local_tls_material(cert_path, key_path)
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.load_cert_chain(certfile=str(cert_path), keyfile=str(key_path))
    return ctx


def create_client_ssl_context() -> ssl.SSLContext:
    ctx = ssl._create_unverified_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


def write_json_line(sock, payload: dict[str, Any]) -> None:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8") + b"\n"
    sock.sendall(data)


def read_json_line(sock, max_bytes: int = MAX_MESSAGE_BYTES) -> dict[str, Any]:
    chunks = bytearray()
    while len(chunks) < max_bytes:
        chunk = sock.recv(4096)
        if not chunk:
            break
        chunks.extend(chunk)
        if b"\n" in chunk:
            break
    if not chunks:
        raise RuntimeError("Socket closed before a message was received.")
    line = bytes(chunks).split(b"\n", 1)[0].strip()
    if not line:
        raise RuntimeError("Received an empty transfer message.")
    return json.loads(line.decode("utf-8"))


def fetch_shared_document(share_url: str, timeout: float = DEFAULT_TIMEOUT) -> dict[str, Any]:
    req = request.Request(
        share_url,
        headers={"User-Agent": "PiKit-Transfer/1.0", "Accept": "application/json"},
    )
    if share_url.startswith("https://"):
        handle = request.urlopen(
            req,
            timeout=timeout,
            context=create_client_ssl_context(),
        )
    else:
        handle = request.urlopen(req, timeout=timeout)
    with handle as resp:
        payload = resp.read().decode("utf-8")
    return json.loads(payload)


def infer_local_ip_for_peer(peer_host: str) -> str:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
            probe.connect((peer_host, 1))
            detected = probe.getsockname()[0]
            if detected:
                return detected
    except Exception:
        pass
    try:
        return socket.gethostbyname(socket.gethostname())
    except Exception:
        return "127.0.0.1"
