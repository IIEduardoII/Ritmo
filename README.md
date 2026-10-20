# Ritmo v1.1.0 — Sistema Soberano de Gestão de Treinos e Evolução Física

O **Ritmo** é uma aplicação web progressiva (**PWA**) pessoal, em português brasileiro (`pt-BR`), construída sob os princípios de **soberania de dados**, **operação 100% local-first e offline** e **zero dependências externas**.

Ele unifica planejamento de rotinas por grupos musculares anatômicos, execução de treinos em tempo real, acompanhamento biométrico de peso corporal com deltas automáticos, galeria de fotos de evolução com compressão nativa em WebP e notificações Web Push na rede privada.

---

## Principais Pilares da Versão 1.1.0

1. **Autenticação Monousuário (Bypass de Senhas):**
   - Sistema opera em modo *Single-User Trusted Local*.
   - Toda requisição local ou dentro da faixa privada Tailscale (`100.64.0.0/10`) é autenticada automaticamente no perfil principal (`user_id = 1`).
   - Telas de login e digitação de senha foram totalmente suprimidas.

2. **Galeria de Fotos com Pipeline de Compressão WebP:**
   - Acompanhamento visual da evolução física com fotos categorizadas por ângulos (*Frontal*, *Costas*, *Lateral*, *Outro*).
   - Compressão automática via HTML Canvas no frontend e Pillow no backend: largura máxima de **1080px**, formato **WebP** com taxa de qualidade de **80%** (peso médio entre 100 KB e 250 KB).

3. **100% Offline (Desacoplamento Completo de IA Externa):**
   - Nenhuma chamada para APIs de LLM externas (Gemini expurgado).
   - Zero telemetria, menor consumo de memória RAM (< 45 MB RSS) e garantia de operação autônoma sem internet.

4. **Biometria e Histórico de Peso Corporal com Deltas:**
   - Registro de massa corporal com cálculo dinâmico de variação em relação à pesagem imediatamente anterior (ex: `+1.2 kg`, `-0.4 kg`).
   - Micro-gráfico minimalista renderizado em SVG puro (zero bibliotecas JS externas).

5. **Base de Código Unificada (Single Codebase):**
   - O mesmo código roda no Linux Desktop e no Android via Termux, com detecção automática de ambiente:
     `IS_TERMUX = "com.termux" in os.environ.get("PREFIX", "")`

6. **Limpeza de Interface (UI/UX Focada):**
   - Remoção de barras de pesquisa de telas estáticas (Calendário, Biometria, Perfil).
   - Buscas mantidas exclusivamente no Catálogo de Exercícios e no Histórico Geral.

7. **Calendário Inteligente com Matriz de Estados Temporais:**
   - **Passado com treino:** Exibe card detalhado do treino feito (séries, cargas, volume). Bloqueia novos agendamentos (somente leitura).
   - **Passado sem treino:** Exibe *"Dia de descanso / Nenhum treino realizado"*. Oculta botões de agendamento.
   - **Hoje com treino:** Exibe resumo do treino concluído de hoje. Oculta agendamento duplicado.
   - **Hoje sem treino:** Exibe treino programado com destaque no botão: `[ Iniciar Treino de Hoje → ]`.
   - **Futuro:** Exibe treino planejado ou botão `[+ Agendar Treino]`.

8. **Filtro Reativo por Grupos Musculares:**
   - Chips anatômicos no seletor de exercícios (`Peito`, `Costas`, `Quadríceps`, `Posterior`, `Ombros`, `Bíceps`, `Tríceps`, `Abdômen`, `Panturrilha`, `Outro`).
   - Filtragem instantânea client-side combinada com refinamento textual.

9. **Taxonomia Anatômica (Extinção de "Foco"):**
   - Eliminação de conceitos abstratos como "força", "hipertrofia" e "resistência".
   - Rotinas e fichas são tipificadas diretamente pelos grupos musculares trabalhados.

10. **Trava Operacional de Backup Pré-Deploy:**
    - Script `scripts/backup_pre_deploy.sh` congela com integridade garantida a versão 1.0 antes de qualquer deploy em produção.

---

## Estrutura do Projeto

```
Ritmo/
├── backend/
│   ├── app.py                     # API Flask, SQLite WAL e rotas
│   ├── manage.py                  # Gestão de perfil monousuário
│   ├── requirements.txt           # Dependências Linux/Python
│   ├── requirements-termux.txt    # Dependências Android/Termux
│   └── static/uploads/evolution/  # Fotos de evolução física (WebP)
├── frontend/
│   ├── index.html                 # Estrutura semântica SPA
│   ├── style.css                  # Design Dark Mode responsivo e chips
│   ├── app.js                     # SPA Vanilla JS (Roteamento, Timer, Gráficos)
│   ├── sw.js                      # Service Worker offline & Web Push
│   ├── manifest.webmanifest       # PWA Manifest tela cheia
│   └── icons/                     # Ícones adaptativos
├── scripts/
│   ├── backup_pre_deploy.sh       # Trava de segurança pré-migração
│   ├── push-dispatcher.py         # Daemon de notificações Web Push
│   ├── termux-backup.sh           # Backup com rclone para o Google Drive
│   ├── termux-start-services.sh   # Inicializador runit
│   └── generate-certs.sh          # Gerador de certificados TLS locais
├── services/                      # Definições runit (api, nginx, backup, push)
└── tests/
    └── v1_1_check.py              # Suíte de testes automatizados da v1.1.0
```

---

## Execução Local e no Termux

### 1. No Linux Desktop
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
python backend/app.py
```
Acesse em `http://127.0.0.1:8000`.

### 2. No Android / Termux
```bash
pkg install -y python python-pillow nginx termux-services
python scripts/setup-termux.py
scripts/termux-start-services.sh
```
Acesse em `http://127.0.0.1:8088` (ou pelo IP/MagicDNS da Tailscale).

---

## Licença e Privacidade
Projeto 100% pessoal, privado e autônomo. Sem planos pagos, sem anúncios, sem rastreamento.
