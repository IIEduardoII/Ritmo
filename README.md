# Ritmo — acompanhamento pessoal de treinos

Aplicação em português brasileiro para um único usuário, em celular e computador.
Nginx serve HTML/CSS/JavaScript sem framework ou etapa de compilação: são poucos arquivos,
não há CDN, e os controles nativos reduzem dependências e consumo de memória.
Flask + SQLAlchemy + PyMySQL atendem a API; MySQL 8.4 guarda os dados em volume persistente.
Gunicorn usa um worker e quatro threads. Não há cadastro público. Gemini é opcional e pode permanecer desligado.

## Instalação no RF511

Diretório reservado: `/home/cloud/treinos`. Não reutilize um diretório com arquivos existentes.

```bash
cd /home/cloud/treinos
python3 scripts/setup.py          # cria .env uma única vez, com modo 600
# Configure recursos/porta em .env sem divulgar seu conteúdo.
find frontend -type d -exec chmod 755 {} +
find frontend -type f -exec chmod 644 {} +
chmod 644 nginx.conf
docker compose up -d --build --wait
docker compose exec app python manage.py
```

O último comando pede e confirma a senha sem eco, exige 12–256 caracteres e grava somente
hash Argon2id no banco. Use também para trocar a senha; sessões anteriores são invalidadas.
Não use a senha de SSH como senha da aplicação. Nenhuma senha padrão foi configurada.
O `.env` contém credenciais de infraestrutura aleatórias, não a senha pessoal; nunca versionar.

### Acesso privado e reinício automático

Nginx publica **somente** `127.0.0.1:8088`. Backend e banco não publicam portas.
A rede do banco é interna. Tailscale Serve encaminha HTTPS privado ao Nginx:

```bash
sudo tailscale serve --bg --yes http://127.0.0.1:8088
sudo tailscale serve status
systemctl is-enabled docker tailscaled
```

Se o Serve solicitar ativação no painel do Tailscale, o proprietário deve abrir o link
exibido pelo comando e habilitar HTTPS/Serve. Não habilitar Funnel. O endereço final aparece
em `tailscale serve status`; usar somente em aparelhos conectados à tailnet autorizada.

Os três serviços possuem `restart: unless-stopped`. Docker e tailscaled devem estar
habilitados no boot (`sudo systemctl enable docker tailscaled`, caso necessário).
Após queda de energia ou reinicialização, containers que estavam ativos voltam automaticamente.
O `--bg` mantém o encaminhamento Serve depois de reiniciar o servidor.
Um container parado manualmente permanece parado; execute `docker compose up -d --wait`
para retomá-lo. `docker compose down` remove os containers e exige esse mesmo comando.
Não é necessário criar um serviço systemd que execute Compose no boot.
Healthchecks verificam banco, API e Nginx. Após um reboot os processos podem levar um minuto
para estabilizar. O backend tenta novamente a conexão com o MySQL durante a inicialização.
Não se reiniciou a máquina nem o daemon Docker durante a implantação.

Limites: Nginx 128 MB/0,5 CPU; Python 384 MB/1 CPU; MySQL 1 GB/1,5 CPU.
Logs Docker têm rotação (2 × 5 MB por serviço). Banco permanece no volume `treinos_mysql_data`.

## Uso

- **Rotinas:** criar manualmente ou gerar sugestões considerando objetivo, 1–6 dias e
  15–120 minutos. Cada sugestão precisa ser revisada e salva individualmente. Ajustar séries,
  repetições e descanso; as regras são modelos editáveis, sem IA e sem progressão automática.
- **Exercícios:** 19 exercícios iniciais por grupo; criar, editar ou excluir exercícios próprios.
  Para excluir, remover antes das rotinas. O nome dos exercícios nas sessões antigas é preservado.
- **Treinar:** iniciar pela rotina ou retomar a sessão em andamento. As mudanças são salvas
  ao sair do campo ou marcar a série; o estado confirma o salvamento. Use “Salvar agora” antes
  de fechar a página. Carga em kg, inclusive zero para exercícios sem carga externa.
  Cronômetro permite iniciar, pausar, continuar e pular. O cronômetro é local à página;
  recarregar preserva as séries salvas, mas reinicia o cronômetro.
- **Finalizar:** exige pelo menos uma série concluída. Somente sessões finalizadas aparecem
  no calendário e séries concluídas entram no histórico de cargas. Séries não feitas continuam
  visíveis nos detalhes do registro. Não existe sugestão de aumento de carga.
- **Visão geral:** mês selecionável, dias treinados, detalhes por dia, quantidade de sessões
  e comparação entre a maior carga da primeira e da última sessão do mês por exercício.
- **Evolução:** todas as séries realizadas em lista; o gráfico representa a maior carga por sessão.
- Para bicicleta/esteira, registrar tempo nas observações; campos numéricos seguem contagens
  de séries e repetições. Prancha também pode ter duração anotada nas observações.

Datas são armazenadas no horário de Brasília (`America/Sao_Paulo`). A instalação é para um
único usuário. Dados de rotina são copiados para a sessão, portanto editar ou apagar uma
rotina não altera registros antigos. Exclusões têm confirmação na interface.

## Backups

```bash
cp backup.conf.example backup.conf
chmod 600 backup.conf
# Preencher USB_MOUNT, DRIVE_REMOTE e RCLONE_CONFIG_DIR conforme os destinos reais.
./scripts/backup.sh weekly
```

O arquivo `backups/weekly.tar.gz` contém exportação SQL consistente (`--single-transaction`)
e os arquivos da aplicação, incluindo `.env`, necessários à recuperação. Backups não são
criptografados. Guardar os destinos com acesso restrito; senha pessoal continua sendo hash.
O arquivo `backup.conf` e a autenticação do rclone não entram no pacote. A checksum SHA-256
permite verificar a integridade. Logs: `backups/backup.log` e journal systemd.

Cada destino usa o mesmo nome `weekly.tar.gz` (uma única versão semanal substituída a cada
execução), acompanhado da checksum. O pendrive recebe em arquivo temporário e renomeia
apenas após copiar. Antes de atualizações, `pre-update-DATA-HORA.tar.gz` conserva a cópia
extra, separada da semanal. Essas cópias extras não são removidas automaticamente.
Falha de qualquer destino resulta em exit code 1 e registro explícito; cópia local é mantida.
Se USB não estiver montado, o script não escreve no diretório que seria o ponto de montagem.
O script usa flock para evitar duas execuções simultâneas.

### Pendrive

Nenhum pendrive foi identificado na inspeção inicial. Conecte o de 32 GB e confira:

```bash
lsblk -o NAME,SIZE,FSTYPE,UUID,MOUNTPOINTS
```

Escolha e monte a partição correta sem formatar. Dê ao usuário `cloud` permissão para escrever
no destino. Configure montagem persistente por UUID em `/etc/fstab`, com `nofail` para que a
máquina ligue mesmo sem pendrive. Essa alteração precisa usar o UUID e o sistema de arquivos
reais do dispositivo. Depois, informe o ponto de montagem em `USB_MOUNT` e rode o backup.
Não configure caminho sem validar `mountpoint -q CAMINHO`.

### Google Drive

O rclone é executado em container somente durante o backup, sem instalar pacote global:

```bash
mkdir -p ~/.config/treinos-rclone
chmod 700 ~/.config/treinos-rclone
docker run --rm -it --user "$(id -u):$(id -g)" \
  -v "$HOME/.config/treinos-rclone:/config/rclone" \
  rclone/rclone:1.70.3 config
```

Crie remote `drive`, tipo Google Drive, sem publicar tokens. Em servidor sem navegador,
responda não à autenticação automática e siga as instruções do rclone para autorizar pelo
navegador de outro computador (`rclone authorize drive`). Cole o resultado somente no
terminal privado do assistente do rclone. Ajuste permissão `chmod 600` de `rclone.conf`.
No `backup.conf`, definir `DRIVE_REMOTE=drive:Treinos` e o caminho real de `RCLONE_CONFIG_DIR`.
O diretório Treinos recebe somente os arquivos desta aplicação; não há sync/delete de outros arquivos.

### Agendamentos persistentes

Após confirmar os caminhos dos units, instalar somente os units desta aplicação:

```bash
sudo install -m 644 scripts/treinos-{backup,restore-test}.{service,timer} /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now treinos-backup.timer treinos-restore-test.timer
systemctl list-timers 'treinos-*'
```

Backup domingo às 03h de Brasília (atraso aleatório de até 5 minutos), restauração dia 1 às
04h de Brasília. `Persistent=true` executa agendamentos perdidos depois que a máquina ligar.
Os timers não substituem as políticas Docker de reinício.

```bash
journalctl -u treinos-backup.service -u treinos-restore-test.service
systemctl --failed
```

### Testar restauração sem afetar dados atuais

```bash
./scripts/restore-test.sh backups/weekly.tar.gz
```

Extrai em `/tmp`, cria projeto Compose único, rede e volume separados, importa SQL **somente
no banco isolado**, verifica saúde, catálogo e formato do hash, testa login com senha temporária aleatória
somente nesse banco de teste, e remove os containers/volume
de teste ao terminar. Porta de teste `127.0.0.1:18088`; mudar com `RESTORE_TEST_PORT` se ocupada.
Não importa dados no banco ativo e não executa `down -v` no projeto de produção.
Atenção: esse teste constrói imagens e inicia um segundo MySQL temporariamente.

### Recuperar após perda do servidor

Em outro servidor limpo, extrair o pacote para um diretório vazio usando Python tarfile
com `filter='data'` (como no script), extrair `application.tar.gz` para o novo projeto,
proteger `.env` com `chmod 600`, e iniciar **somente** o banco:

```bash
docker compose up -d --wait db
docker compose exec -T db sh -c \
  'MYSQL_PWD="$MYSQL_PASSWORD" exec mysql -u"$MYSQL_USER" "$MYSQL_DATABASE"' < /CAMINHO/database.sql
docker compose up -d --build --wait
```

Reconectar Tailscale, configurar Serve e os destinos de backup. Para recuperar no servidor
atual, primeiro faça outro backup e use um projeto/diretório isolado com outra porta; só
migre o acesso depois de verificar os dados. Nunca importar um dump sobre o banco ativo
como teste. Não execute `docker compose down -v` em produção.

## Atualizar e operar

Executar `./scripts/backup.sh pre-update` **antes** de substituir os arquivos do projeto.
Preservar `.env`, `backup.conf` e `backups/`; copiar os novos arquivos e executar
`docker compose up -d --build --wait`. `scripts/update.sh` serve para reconstruir/atualizar
imagens dos arquivos atuais, sempre fazendo backup primeiro; recusa a atualização quando
um destino de backup falha. Não há migrações destrutivas automáticas; a primeira versão
cria tabelas ausentes e dados iniciais. Mudanças futuras de schema exigem migração explícita.

```bash
docker compose ps
docker compose logs --tail=80 app nginx db
docker compose restart app nginx      # somente os serviços deste projeto
curl -f http://127.0.0.1:8088/api/health
```

Para teste local de lógica: `python -m venv .venv`, instalar `backend/requirements.txt` e
executar `.venv/bin/python tests/check.py`. O teste usa SQLite temporário por padrão; também
aceita `DATABASE_URL` de um MySQL **isolado e sem usuário**. Não executar contra produção.
Para testar a pilha inteira em outra máquina, gerar `.env` e usar Compose com nome diferente,
porta diferente e `COOKIE_SECURE=false` somente no ambiente HTTP de teste.

## Segurança e limites

Sessão em cookie Secure/HttpOnly/SameSite Strict com expiração de 12 horas e token CSRF em
operações de escrita, inclusive login. Limite de 10 falhas de login em cinco minutos por
processo, um worker compartilhado pelas threads. HTTPS da tailnet protege o acesso remoto.
Entradas validadas, consultas ORM parametrizadas e nomes escapados no HTML.
Não há senha pessoal nos logs, arquivos ou repositório. Segredos Docker existem em `.env`
restrito e nas configurações dos containers: só administradores do host/Docker devem acessá-los.
A camada de proteção de acesso combina tailnet autorizada e a senha pessoal.

Referências técnicas: [políticas de reinício Docker](https://docs.docker.com/engine/containers/start-containers-automatically/),
[Tailscale Serve](https://tailscale.com/docs/features/tailscale-serve),
[segurança Flask](https://flask.palletsprojects.com/en/stable/web-security/).

## PWA e modo escuro

A interface pode ser instalada como aplicativo em navegadores compatíveis. O manifest
`frontend/manifest.webmanifest` define escopo na mesma origem, abertura `standalone`, nome,
ícones PNG de 192 e 512 pixels e ícone maskable. Há também apple-touch-icon de 180 pixels.
O aplicativo instalado acessa o mesmo backend e MySQL no RF511; não cria outra base de dados.

Abra **https://<seu-servidor>.<sua-tailnet>.ts.net/** (ou **http://<ip-do-servidor-tailscale>:8088**) com Tailscale conectado. No Android com Chrome,
use “Instalar aplicativo” quando o navegador oferecer a opção, ou o menu de instalação
/adicionar à tela inicial do navegador. No iPhone, use o menu Compartilhar e a opção de
adicionar à tela inicial. O nome das opções depende do navegador e da versão do sistema.
Fora da rede local, manter o Tailscale conectado. O endereço privado escolhido também usa
Tailscale dentro da rede local; instalar não substitui nem desativa essa conexão.

O botão interno “Instalar aplicativo” só aparece quando o navegador emite
`beforeinstallprompt`; a instalação também pode estar disponível no menu do navegador.
Em navegadores sem instalação, a interface continua funcionando como site responsivo.
No aplicativo instalado, a mesma interface, autenticação e funcionalidades permanecem disponíveis.

**Primeira versão somente online:** não há service worker, Cache Storage nem IndexedDB.
Respostas da API e arquivos servidos usam `Cache-Control: no-store`; chamadas da API também
usam `fetch` com `cache: no-store`. Senhas e dados pessoais de treino não são gravados em
cache persistente. O cookie seguro de sessão permanece necessário à autenticação.
Sem conexão com o servidor/Tailscale, o aplicativo não acessa nem registra treinos.

A identidade visual é sempre escura, tanto no site quanto na PWA, sem preferência
armazenada no navegador. Fundo #111111, superfícies #1E1E1E, texto #FFFFFF,
rótulos #BBBBBB, ações e foco #FFD700 e confirmações #2ECC71. Botões dourados
e verdes usam texto #111111. A logo vetorial `frontend/logo.svg` combina R e seta
ascendente; `frontend/symbol.svg` fornece o símbolo usado nos ícones da PWA.
Uma instalação anterior pode atualizar o ícone conforme o sistema operacional;
se continuar com o antigo, remova o atalho e instale novamente pela mesma URL.

Verificação adicional: `node tests/pwa-check.js` (somente bibliotecas nativas do Node).
Instalação no dispositivo exige um navegador com suporte e o aceite do seu diálogo nativo.
Referência: [requisitos de instalação PWA — MDN](https://developer.mozilla.org/en-US/docs/Web/Progressive_web_apps/Guides/Making_PWAs_installable).

## Gemini opcional: somente projeto gratuito

**Leia antes de configurar a chave:** use uma chave de um projeto Google Cloud **sem
faturamento ativo**, mostrado como Free no Google AI Studio. As chaves herdam o plano e
as cotas do projeto; uma chave de projeto pago pode gerar cobranças mesmo para um modelo
que também oferece nível gratuito. Não vincule uma conta de faturamento, não use créditos
promocionais de projeto pago e não habilite faturamento para aumentar a cota.

O backend usa exclusivamente `gemini-3.1-flash-lite` via `generateContent` padrão, listado
com entrada e saída gratuitas em 13/10/2026. Não usa modelos alternativos, ferramentas,
busca, contexto em cache, batch ou serviços pagos. Se o modelo ficar indisponível, falha
com uma mensagem e mantém o modo manual. Não há fallback para outro modelo.

As condições da Google podem mudar. Antes de ativar, confira o projeto, o modelo e as
cotas reais no AI Studio. A chave sozinha **não permite ao Ritmo verificar o faturamento
do projeto**: `GEMINI_FREE_PROJECT_CONFIRMED=true` é uma declaração do administrador após
essa conferência, não uma verificação automática da Google. Se ativar faturamento depois,
desative a integração e remova a chave; o aplicativo não consegue detectar essa mudança.

### Configuração no RF511

Não envie a chave pelo chat, por formulário do site, por argumento de comando ou em um
arquivo versionado. No servidor, abra o `.env` privado com um editor local; ele já é ignorado
pelo Git. Configure somente depois de confirmar que o projeto está sem faturamento:

```dotenv
GEMINI_ENABLED=true
GEMINI_FREE_PROJECT_CONFIRMED=true
GEMINI_API_KEY=SUBSTITUA_NO_SERVIDOR_PELA_CHAVE_DO_PROJETO_GRATUITO
```

Mantenha `.env` com permissões 600 e recrie somente o serviço Python:

```bash
cd /home/cloud/treinos
chmod 600 .env
docker compose up -d --no-deps app
```

O Compose injeta a chave exclusivamente no ambiente do backend. Ela não é enviada ao
frontend, retornada pela API, incluída na imagem Docker nem registrada nos logs. Não
publique saídas de `docker compose config`, `docker inspect` ou dumps do ambiente: essas
ferramentas administrativas podem mostrar segredos. Backups locais de recuperação incluem
`.env` e devem ser tratados como secretos; não coloque a chave no ZIP de código entregue.

Na web/PWA, abra **Rotinas → Rascunho com Gemini** (também disponível em Exercícios),
habilite a integração e preencha os campos. A opção de habilitar começa desligada e é
compartilhada entre dispositivos pelo backend. Antes de cada geração, é necessário marcar
a autorização de envio à Google. Peso e altura são opcionais e só são enviados se preenchidos.

### Dados enviados, revisão e limites

Envia somente objetivo, experiência, dias, duração, equipamentos, limitações e peso/altura
opcionais. Não envia catálogo, histórico, cargas, notas dos treinos ou senha. Campos extras
na requisição são ignorados. No nível gratuito a Google pode usar os dados para melhorar
seus produtos; o aviso aparece antes de qualquer envio. O consentimento é por geração.
Os campos e os rascunhos não são armazenados em localStorage, IndexedDB ou cache, e são
limpos ao fechar o diálogo/sair. A Google processa os campos enviados segundo seus termos.

A resposta solicitada é JSON com nomes de rotinas, nomes/grupos de exercícios e contagens
de séries/repetições/descanso. O backend valida campos permitidos, tipos, tamanhos,
intervalos, duplicatas e bloqueia textos detectados como instruções clínicas/de carga.
Respostas truncadas, bloqueadas ou inválidas não são exibidas como planos válidos. O esquema
não aceita carga, diagnóstico, tratamento ou explicações livres. Essa validação não certifica
adequação clínica: rascunhos precisam de revisão humana; restrições que exijam avaliação
clínica não devem ser resolvidas pela IA. Não existe aumento automático de carga.

**Gerar não grava no banco.** Na revisão, edite/remova exercícios e confirme para salvar a
rotina e os novos exercícios, em uma única transação. É possível revisar e salvar apenas
um exercício no editor manual. Nomes equivalentes reutilizam o catálogo. Busca e verificação
de duplicatas ignoram maiúsculas/minúsculas, acentos e espaços; isso não identifica sinônimos.
O backend repete a validação e a verificação de duplicatas no momento de salvar.

As cotas são por projeto e modelo, incluindo requisições/minuto, tokens/minuto e
requisições/dia. Consulte os valores atuais no AI Studio; não há número universal garantido.
Além da cota Google, Ritmo permite uma solicitação por minuto e uma geração em andamento.
Cota esgotada (HTTP 429), chave inválida, falha de rede ou modelo indisponível exibem mensagens
claras. Não há repetição automática, contratação, aumento de plano ou fallback. Aguarde a
renovação da cota indicada pela Google ou use **Sugestão local**, **Criar rotina** e o catálogo
manual, que funcionam sem a API. A cota diária da Google é renovada à meia-noite no horário
Pacific; o limite local é renovado após 60 segundos e reinicia com o processo.

### Desativar

Desmarque **Habilitar integração com Google Gemini** no diálogo. A preferência é persistida
no servidor e impede novos envios em todos os dispositivos; um resultado em andamento é
descartado se a integração tiver sido desativada. Uma solicitação já enviada não pode ser
retirada dos servidores da Google. Rascunhos revisados podem continuar sendo salvos manualmente.
Para bloquear administrativamente, defina `GEMINI_ENABLED=false`, remova `GEMINI_API_KEY`
e recrie `app`. Não é necessário excluir rotinas já revisadas e salvas.

Verificações locais sem chamar Google: `python tests/check.py`,
`python tests/gemini-check.py` e `node tests/pwa-check.js`. Use ambiente/banco isolado.
A configuração original dependia de chave gratuita do proprietário. Em 13/10/2026,
o fluxo real foi validado no backend ativo usando o projeto/chave já configurados;
ver resultados, causa 404 do modelo 2.5 e a correção do schema em RELATORIO-CORRECOES.md.
A cópia corrigida ainda não foi implantada no servidor.

Fontes oficiais consultadas em 12/10/2026:
[preços e uso de dados](https://ai.google.dev/gemini-api/docs/pricing),
[chaves e projetos](https://ai.google.dev/gemini-api/docs/api-key),
[faturamento](https://ai.google.dev/gemini-api/docs/billing),
[cotas](https://ai.google.dev/gemini-api/docs/rate-limits),
[respostas estruturadas](https://ai.google.dev/gemini-api/docs/structured-output).

## Pesquisa de exercícios

Na tela Exercícios, use Buscar exercício para filtrar por nome. A pesquisa é local no
navegador, sem chamar Gemini ou outra API a cada digitação. Ignora maiúsculas/minúsculas,
acentos e espaços: Supino Reto, SUPINO RÊTO e supinoreto encontram o mesmo nome.
Também aceita parte do nome; campo vazio mostra todo o catálogo. A grafia original é
preservada na interface e no banco. A normalização é a mesma usada para detectar duplicatas.
Verificação: `node tests/search-check.js`.

### Pesquisa nas demais telas

A mesma busca por nome está disponível nas rotinas (nome da rotina ou exercício incluído),
na escolha de rotina para treinar, no treino em andamento, nos registros/cargas do mês,
nos detalhes do histórico, nas sugestões locais e nos rascunhos/revisão Gemini. Pesquisar
apenas filtra itens já carregados; não chama Gemini nem envia a pesquisa ao servidor.

No editor de rotinas e na Evolução, digite em Pesquisar exercício e escolha o resultado no
seletor Exercicio. Digitar não altera a seleção existente; se não corresponder ao filtro,
o exercício atual permanece identificado como selecionado. Escolher outro exercício na
Evolução carrega seu histórico pela API própria do Ritmo, sem uso de Gemini.

Os filtros ignoram caixa, acentos e espaços e mantêm os nomes originais. Em treinos e
rascunhos, ocultar um item pela pesquisa não o remove do plano nem do salvamento.
Campo vazio restaura a lista inteira. A mesma interface funciona na web e na PWA.


## Correções de 13/10/2026 — código preparado, ainda não implantado

Abra qualquer dia da Visão geral, escolha a rotina e informe um horário (Brasília).
Agendamentos ficam em uma tabela separada `schedules`; treinos históricos não são
convertidos em agendamentos. Dourado identifica agendados e verde identifica concluídos.
Ao abrir o dia aparecem a rotina, o horário, o estado e os exercícios/registros vinculados.
É possível iniciar a rotina agendada ou remover apenas seu agendamento. A implantação
criará esta tabela ausente; essa alteração do banco de produção não foi executada.

Todos os exercícios podem ser editados, inclusive os iniciais. Nomes, séries, cargas,
descanso e observações de treinos existentes permanecem nos snapshots históricos.
A exclusão do catálogo inicial continua bloqueada; a edição de nomes não quebra a
sugestão local. As rotinas futuras usam os nomes atuais do catálogo.

Salvamentos pendentes do treino são reunidos na versão mais recente; cliques repetidos
com o mesmo conteúdo compartilham a requisição. Salvar agora fica desabilitado durante
o envio. Só aparece confirmação depois de HTTP bem-sucedido; em erro, os campos ficam
na tela e é possível tentar novamente. Não existe repetição automática.
Navegação por abas espera o salvamento e serializa renderizações; clicar novamente
em Visão geral também abre o painel. O histórico do treino usa uma chamada em lote.

Para medição, o console registra `Ritmo timing` (interface/rede/JSON e cabeçalho
Server-Timing) e `Ritmo save` (coleta/fila/requisições até confirmação).
`Server-Timing` informa API e DB: DB soma instruções SQL e commit; API inclui DB,
autenticação, validação e serialização, sem o trânsito de rede/Nginx. Logs registram
rota normalizada, método, status, tempo de API/DB e quantidade de consultas. Não
registram SQL, parâmetros, corpos, senha, chave Gemini ou conteúdo dos treinos.

### Lembretes e limites

O botão Ativar lembretes com o Ritmo aberto solicita a permissão nativa; é possível
desativar na mesma página. A preferência é da sessão, sem persistência. Navegadores
sem suporte mantêm os horários no calendário. Esta entrega oferece apenas lembretes
com a página aberta, por consulta a cada 30 segundos. Navegadores podem suspender
a página e atrasar/impedir lembretes, sobretudo no celular. Notificações com o Ritmo
fechado NÃO estão implementadas: exigem Web Push, service worker, VAPID, armazenamento
de inscrições e rotina no servidor. Essas configurações não foram criadas nem ativadas,
conforme a restrição de alterações fora do código.

Mesmo com a página aberta, o servidor precisa estar ligado, conectado à internet
e acessível pela conexão privada do Ritmo/Tailscale. Antes de notificar, a página
consulta novamente o servidor; se ele estiver inacessível, não envia o lembrete.
Não recupera lembretes atrasados em mais de um minuto. O calendário já exibido permanece
na tela, mas reabrir/atualizar o site sem servidor não funciona: o Ritmo continua online.
O teste real de desligamento/reconexão e de entrega no aparelho permanece pendente.

### Gemini

A falha real reproduzida foi HTTP 404/NOT_FOUND no endpoint `gemini-2.5-flash-lite`.
A chave existe no backend e os dois indicadores de habilitação/projeto gratuito estão
ativos. A listagem de modelos da Google inclui o modelo, mas generateContent retorna
404 nesse projeto. A documentação informa restrição dos modelos 2.5 a projetos que
já os utilizavam. Essa é uma explicação compatível com a falha, ainda não comprovada
como política específica aplicada ao projeto.

O código preparado passa a usar exclusivamente `gemini-3.1-flash-lite`, com nível
gratuito oficial, sem fallback/retry/ferramentas. Ainda precisa validar uma resposta
real nesse endpoint: houve queda do RF511 antes dessa validação. Nenhuma mudança de
plano, faturamento, chave ou variável do servidor foi realizada. A declaração de
projeto gratuito já existente não permite verificar automaticamente o faturamento;
a tabela de preços gratuita também não certifica o plano da chave.

Erros agora distinguem chave/configuração, formato/schema, modelo/endpoint, conexão,
cota e indisponibilidade remota. O log usa somente modelo, HTTP, categoria, códigos
conhecidos e duração. Não registra a mensagem/corpo remoto, chave nem perfil pessoal.
Criação manual, sugestão local e exercícios continuam disponíveis sem Gemini.

Testes adicionais, em banco isolado:
`python tests/corrections-check.py` e `node tests/save-check.js`.
Veja `RELATORIO-CORRECOES.md` para os resultados e pendências de implantação/validação.


Nota de integração Gemini: a API atual aceita o schema estrutural e enumerações;
o cliente omite apenas restrições de quantidade numérica/lista e propriedades extras,
que são conferidas pelo mesmo backend após a resposta. Isso mantém a validação estrita
no servidor e evita rejeição 400 do endpoint gratuito no fluxo real.
