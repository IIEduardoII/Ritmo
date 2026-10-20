#!/usr/bin/env bash
# generate-certs.sh: Gera CA local e certificado TLS para o Ritmo
set -euo pipefail

DOMAIN="${1:-meu-servidor.minha-tailnet.ts.net}"
IP="${2:-100.64.0.1}"
OUT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/certs"

mkdir -p "$OUT_DIR"
cd "$OUT_DIR"

echo "==> Gerando chave privada da CA (ECDSA P-256)..."
openssl ecparam -name prime256v1 -genkey -noout -out ca.key

echo "==> Gerando certificado raiz da CA..."
openssl req -new -x509 -sha256 -key ca.key -out ca.crt -days 3650 \
    -subj "/CN=Ritmo Local CA ($DOMAIN)"

echo "==> Gerando chave privada do servidor..."
openssl ecparam -name prime256v1 -genkey -noout -out server.key

echo "==> Criando requisição CSR do servidor..."
openssl req -new -key server.key -out server.csr -subj "/CN=$DOMAIN"

echo "==> Assinando certificado do servidor com SAN ($DOMAIN, $IP)..."
cat > server.ext <<EOF
subjectAltName=DNS:$DOMAIN,IP:$IP
basicConstraints=critical,CA:false
keyUsage=critical,digitalSignature
extendedKeyUsage=serverAuth
EOF

openssl x509 -req -in server.csr -CA ca.crt -CAkey ca.key -CAcreateserial \
    -out server.crt -days 825 -sha256 -extfile server.ext

rm -f server.csr server.ext ca.srl

echo "==> Certificados gerados com sucesso em $OUT_DIR:"
echo "    - ca.crt (instalar no celular/cliente)"
echo "    - server.crt e server.key (usados pelo Nginx)"
