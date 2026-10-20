# Contexto e Histórico Geral do Projeto Ritmo

**Data de Consolidação:** 15 de Outubro de 2026  
**Versão Atual da Aplicação:** `v1.2.0` (com suporte a HTTPS `:8443`, Web Push e Backups no Drive)  
**Status do Ambiente:** 100% operacional no dispositivo servidor  

---

## 1. Visão Geral e Diretrizes Inegociáveis

O **Ritmo** é um sistema pessoal e autônomo (PWA) para planejamento, agendamento e registro de treinos de musculação e condicionamento físico, desenvolvido em português do Brasil.

### Princípios Fundamentais:
1. **Privacidade e Isolamento de Rede:** Toda a comunicação opera estritamente dentro da rede privada **Tailscale** (`100.64.0.0/10`). Não há Tailscale Funnel, portas expostas na WAN nem domínios DNS públicos.
2. **Custo R$ 0 Absoluto:** Nenhuma ferramenta, infraestrutura ou API com cobrança foi utilizada. O modelo de inteligência artificial adotado é o **Gemini 3.1 Flash-Lite** sob a cota gratuita oficial, com fallbacks estritos.
3. **Resiliência e Imutabilidade de Dados:** Alterações no catálogo de exercícios nunca alteram o histórico de treinos concluídos (snapshots imutáveis). O banco de dados passa por verificações de integridade e backups versionados na nuvem (Google Drive gratuito).

---

## 2. Topologia de Dispositivos e Papéis

| Dispositivo | IP Tailscale (Exemplo) | Hostname MagicDNS (Exemplo) | Função no Ecossistema |
| :--- | :--- | :--- | :--- |
| **Servidor Android (Termux)** | `100.64.0.10` | `servidor-ritmo.<sua-tailnet>.ts.net` | **Servidor Principal (Host Fixo):** Permanece ligado rodando Termux com Nginx, Gunicorn/Flask, SQLite, despachante de Web Push e rotina de backup no Drive. |
| **Celular Cliente (PWA)** | `100.64.0.20` | `celular-cliente.<sua-tailnet>.ts.net` | **Dispositivo Cliente Principal:** Celular de uso diário onde o PWA está instalado e onde chegam as notificações de treino em segundo plano. |
| **Estação de Trabalho** | `100.64.0.30` | `workstation.<sua-tailnet>.ts.net` | **Estação de Trabalho / Desenvolvimento:** Utilizado para manutenção, túneis de configuração e acesso web alternativo. |
| **Servidor Legado (Docker)** | `100.64.0.40` | `legacy-host.<sua-tailnet>.ts.net` | *Descontinuado / Offline:* Antigo host histórico em Docker/MySQL. |

---

## 3. Arquitetura de Software e Serviços no Redmi A3x

Os processos são supervisionados pelo sistema `runit` (`termux-services`), com logs dedicados em `~/.local/share/ritmo/log/`:

```
                                  [ Tailscale Network ]
                                            │
                      ┌─────────────────────┴─────────────────────┐
                      ▼                                           ▼
             [ Porta HTTP 8088 ]                        [ Porta HTTPS 8443 ]
             (Fallback / Loopback)                      (TLS v1.2/1.3 + HTTP/2)
                      │                                           │
                      └─────────────────────┬─────────────────────┘
                                            ▼
                               [ Nginx (Worker Nativo) ]
                                            │
                           ┌────────────────┴────────────────┐
                           ▼                                 ▼
                     Arquivos Estáticos                Proxy Reverso (/api/*)
                     `frontend/`                             │
                                                             ▼
                                                    [ Gunicorn :8000 ]
                                                    (1 Worker / 4 Threads)
                                                             │
                                                             ▼
                                                    [ Backend Flask ]
                                                             │
                                                             ▼
                                                    [ SQLite Database ]
                                                `~/.local/share/ritmo/ritmo.sqlite3`
```

### Daemons Ativos (`runsv`):
1. **`ritmo-api`**: Aplicação Flask em Python 3.13 no virtualenv `.venv`, servida por Gunicorn em `127.0.0.1:8000`.
2. **`ritmo-nginx`**: Servidor web atendendo portas `8088` e `8443` com controle estrito de acesso (`allow 127.0.0.1; allow 100.64.0.0/10; deny all;`).
3. **`ritmo-backup`**: Serviço diário (03:00) de cópia consistente do SQLite, dump textual e sincronização com Google Drive.
4. **`ritmo-push`**: Despachante autônomo em background que monitora agendamentos a cada 30 segundos e envia notificações Web Push via VAPID.

---

## 4. Histórico Cronológico de Modificações e Entregas

### Etapa 1: Auditoria e Validação do Código via SSH
- Conexão estabelecida via SSH (`<usuario-termux>@<ip-servidor-tailscale>:8022`).
- Validação das baterias de testes no ambiente real do Termux:
  - `tests/check.py`: **Aprovado** (Autenticação, CSRF, catálogo, CRUD, sessão).
  - `tests/corrections-check.py`: **Aprovado** (Imutabilidade de histórico, agendamentos, Server-Timing).
  - `tests/gemini-check.py`: **Aprovado** (Modelo `gemini-3.1-flash-lite`, tratamento de cotas e erros).

### Etapa 2: Backup Físico Integral da Versão 1.0
- Antes de qualquer alteração estrutural, foi gerado um snapshot idêntico da versão 1.0 (código, dependências e banco de dados real com as 9 tabelas) na mídia física externa:
  - Caminho: `/caminho/do/backup-externo/Ritmo-v1.0/`
  - Arquivo compactado: `/caminho/do/backup-externo/Ritmo-v1.0-archive.tar.gz`

### Etapa 3: Liberação do Loopback e Versão 1.2.0
- **Problema:** O Nginx bloqueava `127.0.0.1`, impedindo que o próprio aparelho hospedeiro considerasse a página como um Contexto Seguro (Secure Context).
- **Correção:** Adicionada a diretiva `allow 127.0.0.1;` no `nginx-termux.conf`.
- **Diferenciação Formal de Versões:**
  - **v1.0.x (Modo Gateway):** Nginx restrito apenas a `100.64.0.0/10`, exigindo obrigatoriamente um Gateway HTTPS externo na Tailnet para PWA.
  - **v1.2.0 (Modo Standalone):** Nginx com `allow 127.0.0.1;`, permitindo PWA autônomo no dispositivo hospedeiro e mantendo Tailscale para outras máquinas.

### Etapa 4: Backups Automatizados no Google Drive
- **Ferramenta:** `rclone` (v1.74.3) instalado nativamente no Termux.
- **Autenticação Segura:** Configurado remote `gdrive` com escopo restrito `drive.file` (não tem acesso a outros arquivos pessoais do usuário).
- **Mecanismo (`scripts/termux-backup.sh`):**
  1. Criação de snapshot do banco SQLite via API `sqlite3.backup()` em modo somente leitura (sem locks na API).
  2. Execução de `PRAGMA integrity_check`.
  3. Geração de dump textual SQL legível (`ritmo.sql`).
  4. Empacotamento com manifesto contendo contagem de linhas e hash SHA-256.
  5. Sincronização para a pasta `Ritmo/` no Google Drive com validação de hash MD5 após o upload.
  6. Política de retenção automática: 30 backups diários e 12 backups mensais.
  7. Exclusão garantida de arquivos sensíveis do pacote (`.env`, `.venv`, `certs/`).
- **Serviço Runit:** Criado daemon `ritmo-backup` que roda após as 03:00 e recupera execuções pendentes se o aparelho for reiniciado.

### Etapa 5: Infraestrutura HTTPS com Autoridade Certificadora (CA) Própria
- **Criação da CA Local:**
  - Gerada chave elíptica P-256 e certificado raiz da CA com **Name Constraints** estritas (válido exclusivamente para `<servidor-ritmo>.<sua-tailnet>.ts.net` e `<ip-servidor-tailscale>`). Qualquer outro domínio é rejeitado criptograficamente.
- **Emissão do Certificado de Servidor:**
  - Certificado emitido e assinado pela CA com SAN para o DNS MagicDNS e IP da Tailscale.
- **Configuração Nginx Dual-Port (`nginx-termux.conf`):**
  - Porta `8088`: HTTP comum.
  - Porta `8443`: HTTPS nativo com HTTP/2, TLS 1.2/1.3 e session cache.
  - Endpoint de distribuição pública do certificado CA: `/ritmo-ca.crt`.

### Etapa 6: Notificações em Segundo Plano (Web Push RFC 8291 / 8292)
- **Instalação:** Adicionados `python-cryptography` (48.0.1) e `pywebpush` (2.5.0) no ambiente Python do servidor.
- **Par de Chaves VAPID:**
  - Chave privada salva em `~/.local/share/ritmo/vapid_private.pem` (permissão `600`).
  - Chave pública disponibilizada via endpoint `/api/push/public_key`.
- **Banco de Dados:**
  - Criada tabela `push_subscriptions` (`endpoint`, `p256dh`, `auth`, `user_agent`).
  - Adicionada coluna `notified_at` na tabela `schedules`.
- **Rotas Backend (`backend/app.py`):**
  - `GET /api/push/public_key`: Retorna a chave pública VAPID.
  - `POST /api/push/subscribe`: Registra o endpoint do navegador do celular.
  - `POST /api/push/unsubscribe`: Cancela a assinatura.
  - `POST /api/push/test`: Rota de teste para disparo imediato de notificação.
- **Service Worker (`frontend/sw.js`):**
  - Implementados listeners dos eventos `push` e `notificationclick` para exibição de notificações com vibração e redirecionamento direto para a tela de treinos.
- **Frontend (`frontend/app.js`):**
  - Função `syncPush()` que converte a chave VAPID via `urlB64ToUint8Array` e registra a inscrição no `PushManager`.
  - Botão de lembretes atualizado para exibir o status em tempo real: *"Notificações ativas (mesmo com o aplicativo fechado)"*.
- **Despachante Autônomo (`scripts/push-dispatcher.py` & `ritmo-push`):**
  - Daemon que monitora a cada 30 segundos os agendamentos da data/hora atual no fuso de Brasília.
  - Dispara o push para os aparelhos inscritos e marca o agendamento como notificado para evitar repetições.

### Etapa 7: Otimização PWA (Remoção da Barra de URL) e Inicialização Automática
- **Modo Tela Cheia:**
  - Atualizado `manifest.webmanifest` para `"display": "fullscreen"` e `"display_override": ["fullscreen", "standalone"]`.
  - Elimina a barra de endereços do navegador e cabeçalhos residuais no Android.
- **Inicialização Automática (`Termux:Boot`):**
  - Configurado script executável em `~/.termux/boot/ritmo.sh`.
  - Permite que o Redmi A3x inicie todos os serviços do Ritmo sozinho caso seja reiniciado após falta de energia.

---

## 5. Estrutura Atual de Arquivos do Projeto (`~/ritmo-termux`)

```
ritmo-termux/
├── backend/
│   ├── app.py                      # API Flask, autenticação, rotas de treino e push
│   ├── gemini.py                   # Integração com Gemini 3.1 Flash-Lite
│   ├── requirements-termux.txt     # Dependências Python
│   └── manage.py                   # Utilitário de setup de usuário/senha
├── certs/
│   ├── server.crt                  # Certificado TLS do servidor (público)
│   └── server.key                  # Chave privada TLS (permissão 600)
├── frontend/
│   ├── index.html                  # Interface SPA principal
│   ├── app.js                      # Lógica do app, dashboard, treinos e push
│   ├── ai.js                       # Assistente e sugestões de IA
│   ├── install.js                  # Lógica de instalação PWA
│   ├── sw.js                       # Service Worker com cache e listener Web Push
│   ├── style.css                   # Dark theme de alto contraste
│   ├── manifest.webmanifest        # Manifesto PWA em modo fullscreen
│   ├── ritmo-ca.crt                # Certificado público da CA para download
│   └── icons/                      # Ícones em todas as resoluções
├── scripts/
│   ├── termux-start-services.sh    # Script mestre de inicialização
│   ├── termux-stop-services.sh     # Script de parada segura
│   ├── termux-backup.sh            # Script de backup consistente e upload Drive
│   ├── termux-backup-run           # Loop de execução diária do backup
│   ├── push-dispatcher.py          # Daemon de verificação e despacho Web Push
│   └── termux-boot.sh              # Gatilho para inicialização pelo Termux:Boot
├── services/
│   ├── ritmo-api/                  # Definição runit da API
│   ├── ritmo-nginx/                # Definição runit do Nginx
│   ├── ritmo-backup/               # Definição runit do Backup
│   └── ritmo-push/                 # Definição runit do Web Push
├── tests/
│   ├── check.py                    # Testes de regressão da API
│   ├── corrections-check.py        # Testes de banco e históricos
│   └── gemini-check.py             # Testes do modelo de IA
├── nginx-termux.conf               # Configuração Nginx HTTP (8088) e HTTPS (8443)
├── nginx-ritmo-common.conf         # Regras comuns de segurança e proxy
└── .env                            # Variáveis de ambiente e segredos (permissão 600)
```

---

## 6. Guia Operacional de Acesso e Uso

### No Dispositivo Cliente (Celular de Uso Diário):
- **Acesso Recomendado:** `http://<ip-servidor-tailscale>:8088` (com a flag `chrome://flags/#unsafely-treat-insecure-origin-as-secure` ativada) ou `https://<servidor-ritmo>.<sua-tailnet>.ts.net:8443` (com a CA instalada).
- **Instalação PWA:** Menu do navegador ➔ *Instalar aplicativo*.
- **Ativação de Notificações:** Toque em *"Ativar notificações de treino"* no topo do calendário.

### Manutenção dos Serviços no Servidor (Termux via SSH):
- **Verificar status de todos os serviços:**
  ```bash
  sv status ritmo-api ritmo-nginx ritmo-backup ritmo-push
  ```
- **Disparar um backup manual imediato para o Google Drive:**
  ```bash
  ~/ritmo-termux/scripts/termux-backup.sh manual
  ```
- **Disparar teste de notificação Web Push (via curl):**
  ```bash
  curl -X POST http://127.0.0.1:8000/api/push/test
  ```
- **Ver logs em tempo real:**
  ```bash
  tail -f ~/.local/share/ritmo/log/nginx/current
  tail -f ~/.local/share/ritmo/log/api/current
  tail -f ~/.local/share/ritmo/log/backup/current
  tail -f ~/.local/share/ritmo/log/push/current
  ```
