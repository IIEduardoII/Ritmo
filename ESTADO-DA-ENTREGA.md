# Cópia de trabalho — 13/10/2026

As correções nesta cópia ainda não foram implantadas no RF511. Consulte
RELATORIO-CORRECOES.md. As seções abaixo são o registro histórico da entrega anterior.

# Estado da entrega — 11 de outubro de 2026

Implantação em `/home/cloud/treinos` no RF511. Acesso privado verificado:
https://<seu-servidor>.<sua-tailnet>.ts.net/

## Verificado

- Nginx, Python e MySQL: três containers saudáveis.
- `restart: unless-stopped` nos três; Docker e tailscaled habilitados no boot.
- Banco persistente em volume; nenhuma porta do MySQL publicada. Nginx somente em loopback.
- HTTPS privado via Tailscale Serve em modo persistente; página aberta no navegador.
- Testes locais de login/CSRF, hash Argon2id, catálogo, exercícios próprios, rotinas,
  sugestões editáveis, séries, validação de dados, calendário, histórico e exclusões.
- Integração testada também com MySQL em pilha local isolada.
- Navegador: criação de rotina, registro de carga, série concluída, pausa/pulo do descanso,
  finalização, calendário, gráfico e adaptação a 390 pixels de largura.
- Backup local SQL + aplicação com checksum criado em `backups/weekly.tar.gz` no servidor.
- Restauração testada no servidor em projeto Compose, rede, volume e porta separados;
  catálogo de 19 exercícios, saúde e login com senha temporária aleatória validados.
- Containers/volume temporários removidos. Banco ativo preservado.
- Backup semanal e teste mensal agendados por systemd, com execução persistente após boot.

Não se reiniciou o servidor nem o daemon Docker; foram conferidas as configurações
que garantem o retorno dos containers ativos depois de uma reinicialização.

## Pendências do proprietário

1. **Senha pessoal:** configurada pelo proprietário e confirmada na atualização PWA.
   Para trocar: `cd /home/cloud/treinos && docker compose exec app python manage.py`.
   Não envie a senha pelo chat.
2. **Google Drive:** remote rclone não autenticado. Diretório privado de configuração
   preparado em `/home/cloud/.config/treinos-rclone`; seguir README e preencher `backup.conf`.
3. **Pendrive:** não estava conectado na inspeção. Identificar UUID, montar de forma
   persistente sem formatar, conceder escrita a cloud e preencher `USB_MOUNT` em `backup.conf`.

O backup local foi bem-sucedido, mas as cópias externas **não foram realizadas**.
O script retorna falha e registra os dois destinos pendentes; o agendamento está habilitado,
porém a política completa de backup depende dessas etapas. Após configurar, executar
`./scripts/backup.sh weekly` e conferir sucesso em ambos os destinos.

## Próximas execuções

- Backup: 18/10/2026 às 03:00 (Brasília), com atraso aleatório de até cinco minutos.
- Teste mensal: 01/11/2026 às 04:00 (Brasília).

## Arquivos principais

`docker-compose.yml`, `backend/Dockerfile`, `backend/app.py`, `backend/manage.py`,
`frontend/`, `.env.example`, `scripts/`, `tests/check.py` e `README.md`.
O pacote de código entregue não inclui senhas, `.env`, tokens ou dados de backup.


## Atualização PWA inicial — 11/10/2026 (tema substituído pela identidade abaixo)

- Manifest com abertura standalone na mesma origem privada do RF511.
- Ícones PNG 192/512, maskable 512 e apple-touch-icon 180.
- Brave ofereceu o botão Instalar aplicativo pelo evento nativo de instalação.
- Tema claro/escuro testado no navegador, incluindo persistência após recarregar.
- Tela de 390 pixels verificada sem largura excedente; console sem erros.
- Cache-Control no-store nos arquivos e API; fetch da API sem cache.
- Nenhum service worker, Cache Storage ou IndexedDB; sem suporte offline.
- Somente a preferência visual é salva em localStorage (ritmo-theme).
- Backup extra local pré-atualização criado no RF511 e checksum validada.
- Apenas interface e configuração Nginx atualizadas; os três containers continuam saudáveis.
- Manifest/ícones e HTTPS privado verificados na implantação, além do teste tests/pwa-check.js.

A instalação real em um celular não foi executada neste ambiente. O navegador compatível
reconheceu a instalação e o proprietário pode concluí-la pelo botão/menu no aparelho.
O PWA utiliza a mesma interface, API e autenticação do site. Necessita conexão com o RF511;
no endereço privado, Tailscale deve permanecer conectado.

## Identidade visual Ritmo — 11/10/2026

- Tema sempre escuro em todas as telas web e na PWA, conforme a paleta solicitada.
- Logo vetorial R com seta ascendente e nome Ritmo no cabeçalho.
- Ícones PNG da PWA e apple-touch-icon derivados do mesmo símbolo; maskable com margem segura.
- Ações, foco, números e ícones ativos dourados; conclusão e confirmações verdes.
- Contraste das combinações de texto validado em tests/pwa-check.js: mínimo 7,93:1.
- Telas principais e editor de rotina verificados em 390px com dados fictícios locais,
  sem largura excedente e sem erros no console. Logo e visão geral conferidas no computador.
- Removida alternância de tema e armazenamento da preferência visual.
- Instalação física no celular continua dependendo do navegador e aceite do proprietário.
- Implantação confirmada no HTTPS privado; logo e ícones retornam HTTP 200 e o navegador
  oferece Instalar aplicativo. Os três containers seguem saudáveis.
- Backup local pré-atualização: backups/pre-update-identidade-20261011-235617.tar.gz,
  com checksum validada. Docker/Tailscale habilitados no boot; containers unless-stopped.

## Integração opcional Gemini — 12/10/2026

- Backend usa apenas gemini-2.5-flash-lite, listado como gratuito pela Google nesta data.
- Integração entregue desligada e sem chave; ativação exige projeto sem faturamento,
  variáveis privadas no backend e declaração GEMINI_FREE_PROJECT_CONFIRMED.
- Aviso sobre dados enviados e uso no nível gratuito, autorização por geração e desativação
  compartilhada entre dispositivos. Peso e altura opcionais.
- Geração sem gravação no banco; revisão permite editar/remover, salvar apenas um exercício
  ou confirmar rotina/novos exercícios em transação atômica.
- Busca e duplicatas normalizadas sem diferenças de maiúsculas, acentos ou espaços.
- Schema JSON, validação estrita, campos sem carga/diagnóstico/tratamento, erros genéricos
  sem chave/conteúdo externo e nenhum fallback pago/repetição automática.
- Testes isolados: check.py, gemini-check.py e pwa-check.js aprovados. Fluxo no navegador
  com resposta simulada: opt-in, geração, revisão, confirmação, desativação e busca.
- Formulário verificado em 390px sem largura excedente e com tema escuro.
- Chamada real à Google pendente da chave do proprietário; nenhuma chave paga usada.
- Instruções, cotas, limites de verificação do faturamento e desativação no README.md.
- Implantação confirmada no HTTPS privado, backend sem chave/configuração ativa e três
  containers saudáveis. Teste Gemini passou também dentro da imagem implantada.
- Backup apenas local: backups/pre-update-gemini-20261012-014232.tar.gz, checksum validada.
- Limpeza dos campos ao fechar o diálogo confirmada no navegador.

## Pesquisa por nome — 12/10/2026

- Filtro local usa exclusivamente o nome; mantém a grafia original exibida.
- Ignora caixa, acentos e espaços, aceita trechos e mostra tudo com campo vazio.
- Normalização compartilhada com duplicatas; pesquisar não chama Gemini nem outra API.
- tests/search-check.js aprovado com Supino Reto, SUPINO RÊTO e supinoreto.

## Pesquisa em todas as telas — 12/10/2026

- Pesquisa compartilhada nas rotinas, escolha de treino, treino ativo, registros/cargas,
  detalhes do histórico, evolução, editor, sugestões locais e rascunhos/revisão IA.
- Seletores recebem campo de pesquisa escrita sem mudar o exercício selecionado ao digitar.
- Filtro local, normalização comum, grafia preservada e sem chamadas Gemini por pesquisa.
- Teste search-check.js cobre filtro de nomes, rotinas e preservação da seleção.
- Navegador com banco fictício: filtros, seleção na evolução, sugestões locais e salvamento
  com exercício oculto verificados. Todas as séries preservadas; editor/evolução em 390px.
