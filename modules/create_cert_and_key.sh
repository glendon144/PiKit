mkdir -p storage
openssl req -x509 -newkey rsa:2048 -sha256 -days 3650 -nodes \
  -keyout storage/pikit.key -out storage/pikit.crt \
  -subj "/CN=localhost"
