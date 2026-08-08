#!/usr/bin/env bash
set -euo pipefail

CERT_SRC="${1:-storage/pikit.crt}"
CERT_NAME="${2:-pikit-local.crt}"
CERT_DST="/usr/local/share/ca-certificates/${CERT_NAME}"

if [[ ! -f "$CERT_SRC" ]]; then
  echo "Certificate not found: $CERT_SRC" >&2
  exit 1
fi

if [[ "${CERT_DST##*.}" != "crt" ]]; then
  echo "Destination filename must end in .crt" >&2
  exit 1
fi

echo "Installing CA certificate from: $CERT_SRC"
sudo apt-get update
sudo apt-get install -y ca-certificates

sudo cp "$CERT_SRC" "$CERT_DST"
sudo chmod 0644 "$CERT_DST"

echo "Updating system trust store..."
sudo update-ca-certificates

echo
echo "Done."
echo "Installed as: $CERT_DST"
echo "You can verify with:"
echo "  ls -l /etc/ssl/certs/ | grep ${CERT_NAME%.crt}"
echo
echo "If your browser is the snap build, it may still ignore the system trust store."
echo "In that case, test with curl first, or use a non-snap browser/client."
