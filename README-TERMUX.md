# Ritmo no Android com Termux (v1.1.0)

O **Ritmo v1.1.0** opera nativamente no Termux (Android 13 ARM64), utilizando SQLite no modo WAL, Nginx e daemons gerenciados pelo `runit`.

---

## Novidades da Versão 1.1.0 no Termux

- **Bypass de Login (Single-User):** Início imediato sem necessidade de digitar senhas ao acessar via loopback (`127.0.0.1`) ou pela rede privada Tailscale.
- **100% Offline (Zero Gemini):** Sem dependência de internet ou APIs de IA; consumo de memória RAM do processo Gunicorn mantido abaixo de 45 MB.
- **Evolução & Biometria:** Registro de peso corporal com cálculo automático de variação/delta e upload de fotos com compressão local WebP (largura máx. 1080px, ~150 KB por foto).
- **Taxonomia Anatômica:** Foco substituído diretamente por Grupos Musculares com chips interativos no catálogo e no editor de rotinas.
- **Calendário Inteligente:** Dias passados sem treino exibem descanso; dias com treino exibem histórico detalhado e bloqueiam agendamento retroativo.

---

## Instalação e Atualização no Termux

```bash
cd "$HOME/ritmo-termux"
pkg install -y python python-pillow nginx termux-services openssl-tool clang pkg-config cmake

# Inicializa o ambiente
python scripts/setup-termux.py

# Inicia os 4 serviços pelo runit
scripts/termux-start-services.sh

# Verifica o status dos serviços
sv status ritmo-api ritmo-nginx ritmo-backup ritmo-push
```

- **No próprio celular:** Abra `http://127.0.0.1:8088` para usar e instalar o PWA em tela cheia.
- **Em outros dispositivos da Tailnet:** Abra `http://<ip-do-servidor-tailscale>:8088` ou `https://<servidor-ritmo>.<sua-tailnet>.ts.net:8443`.
