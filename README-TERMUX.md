# Ritmo no Android com Termux (v1.2.0)

Esta cópia mantém a versão Docker original em `outputs/ritmo/` e usa SQLite para a instalação no celular. SQLite evita um serviço MySQL separado para o uso individual do Ritmo.

## Controle de Versões e Modos de Operação (v1.0 vs v1.2.0)

- **Versões 1.0.x (Modo Gateway):**
  - O Nginx restringia as conexões estritamente a clientes Tailscale (`allow 100.64.0.0/10; deny all;`).
  - Nessa versão, como o Android Tailscale não possui CLI para `tailscale serve`, o acesso direto pelo IP do celular (`http://<ip-do-servidor-tailscale>:8088`) não é reconhecido pelos navegadores móveis como Contexto Seguro (Secure Context).
  - **Exigência da v1.0:** Para conseguir instalar o PWA na tela inicial do celular ou habilitar as notificações do navegador, era estritamente necessária uma máquina externa na Tailnet atuando como **Gateway HTTPS Privado** (ex.: outro computador Linux executando `tailscale serve` com certificado TLS e fazendo proxy reverso para a porta 8088 do celular).

- **Versão 1.2.0 (Modo Standalone com Localhost):**
  - O Nginx libera acesso local direto no aparelho (`allow 127.0.0.1;`), além de manter a rede privada Tailscale para outros dispositivos (`allow 100.64.0.0/10; deny all;`).
  - Pelas especificações oficiais do W3C e dos navegadores Chromium (Chrome, Brave, etc.), conexões para `http://127.0.0.1` ou `http://localhost` são classificadas nativamente como **Contextos Seguros (Secure Contexts)**, mesmo sobre HTTP.
  - **Vantagem da v1.2.0:** O celular onde o Ritmo está hospedado pode abrir diretamente **`http://127.0.0.1:8088`** no navegador. O botão de instalação do PWA e a API de notificações locais passam a funcionar diretamente no aparelho de forma autônoma (Standalone), **sem precisar de gateway externo nem de outro computador ligado**.
  - O acesso de outros computadores da sua rede privada continua 100% ativo e seguro através do IP da Tailscale (`http://<ip-do-servidor-tailscale>:8088`).

## Requisitos e instalação

O celular precisa ter Termux e o app Tailscale conectados à mesma tailnet dos dispositivos que acessarão o Ritmo. No Termux, instale os pacotes `python`, `argon2`, `python-greenlet`, `nginx`, `termux-services`, `openssl-tool`, `clang`, `pkg-config` e `cmake`. Copie esta pasta para `$HOME/ritmo-termux` e execute:

```sh
cd "$HOME/ritmo-termux"
pkg install -y python argon2 python-greenlet nginx termux-services openssl-tool clang pkg-config cmake
python scripts/setup-termux.py
python -m venv --system-site-packages .venv
.venv/bin/pip install --no-cache-dir scikit-build-core setuptools-scm
.venv/bin/pip install --no-cache-dir --no-build-isolation -r backend/requirements-termux.txt
chmod +x scripts/termux-*.sh scripts/termux-*-run services/ritmo-*/run services/ritmo-*/log/run
scripts/termux-start-services.sh
```

Configure a senha inicial da aplicação por SSH com:

```sh
cd "$HOME/ritmo-termux"
scripts/termux-set-password.sh
```

- **No próprio celular:** Abra `http://127.0.0.1:8088` para usar e instalar o PWA com suporte a notificações locais.
- **Em outras máquinas da rede:** Abra `http://<ip-do-servidor-tailscale>:8088` (ou o hostname MagicDNS). O Nginx permite apenas conexões locais e IPv4 Tailscale (`100.64.0.0/10`). A API fica em `127.0.0.1:8000`, sem porta pública.

## Limites do Android

- O Android/Termux deste aparelho não suporta Docker Engine. A hospedagem nativa usa processos Termux, Nginx e SQLite.
- O cliente Android do Tailscale conecta o aparelho à tailnet; ele não oferece CLI para `tailscale serve`.
- Mantenha o Tailscale conectado, o Android ligado e o Termux sem restrição de bateria para disponibilidade contínua. `termux-wake-lock` reduz suspensão, mas o Android ainda pode encerrar processos sob pressão de memória. Para iniciar após reinício, instale o app Termux:Boot e copie `scripts/termux-boot.sh` para `$HOME/.termux/boot/ritmo.sh`.
- Lembretes do Ritmo continuam limitados à página aberta; não são enviados se o servidor estiver desligado ou se o app estiver 100% fechado (o que exigiria Web Push).

## Operação

```sh
scripts/termux-start-services.sh
scripts/termux-stop-services.sh
sv status ritmo-api ritmo-nginx
```

Banco local: `$HOME/.local/share/ritmo/ritmo.sqlite3`. Guarde cópias dessa pasta fora do celular; esta configuração não sincroniza nem faz backup automático.
