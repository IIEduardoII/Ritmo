# Ritmo — correções de 13/10/2026

**Estado: código preparado e testado localmente; não implantado no RF511.**
Nenhum plano, faturamento, chave, variável privada, serviço ou banco de produção foi alterado.
Nenhuma dependência foi adicionada. O projeto usa os mesmos Flask/SQLAlchemy e JavaScript nativo.

## Implementado nesta cópia

- Calendário: qualquer dia abre um editor com rotina e horário de Brasília. Agendamentos ficam separados dos treinos realizados. Dourado marca agendado; verde marca concluído. Dia mostra rotina, horário, estado e exercícios/registros vinculados, inclusive se o treino aconteceu em outra data. Agendamentos podem iniciar a rotina ou ser removidos sem excluir o treino realizado.
- Exercícios: edição liberada também no catálogo inicial. Nomes e valores de treinos existentes permanecem nos snapshots históricos. Sugestão manual continua funcionando após renomear exercícios iniciais.
- Salvamento: mudanças pendentes são reunidas na versão mais recente; conteúdo idêntico em andamento compartilha uma requisição. Botão Salvar agora fica desabilitado durante envio. Confirmação só aparece após sucesso do servidor; falha mantém os campos para tentativa manual. Navegação por abas salva os campos e aguarda a resposta antes de trocar de tela.
- Navegação: renderizações assíncronas são serializadas; clicar em Visão geral, inclusive quando seu hash já está selecionado, abre o painel. O histórico de todos os exercícios do treino é carregado em uma chamada; consultas ORM passam a carregar exercícios/séries em lote.
- Lembretes limitados à página aberta: permissão solicitada pelo botão, desativação disponível, calendário preservado sem suporte. Consulta ao servidor antes de lembrar; servidor indisponível não produz notificação. Não há entrega em segundo plano ou com aplicativo fechado.
- Gemini: endpoint preparado para `gemini-3.1-flash-lite`; mensagens e logs distinguem erros de chave/configuração, schema, modelo/endpoint, conexão, cota, resposta inválida e indisponibilidade. Sem fallback, repetição automática, mudança de plano ou ferramentas pagas. Modo manual preservado.

## Falha Gemini reproduzida no RF511

Inspeção somente de leitura constatou chave presente no backend, `GEMINI_ENABLED=true` e `GEMINI_FREE_PROJECT_CONFIRMED=true`. A chave não foi exibida ou copiada para esta entrega.
Uma geração com dados fictícios no código original retornou **HTTP 404 / NOT_FOUND** em `gemini-2.5-flash-lite:generateContent`. O código anterior agrupava HTTP 400/401/403/404 numa mensagem genérica de configuração. A chave autentica a listagem de modelos, e a listagem inclui 2.5; ela não garante que o projeto tenha acesso à geração pelo 2.5.

A Google informa que limita acesso aos modelos 2.5 a projetos que já os utilizavam. Isso é compatível com o 404, mas a aplicação dessa regra ao projeto específico não foi comprovada. A falha diretamente reproduzida é a rejeição 404 do modelo/endpoint, mascarada pela mensagem genérica.

A primeira migração para 3.5 Flash-Lite também não serviu a esse ambiente: a chamada mínima excedeu 25 segundos. O 3.1 Flash-Lite respondeu HTTP 200 em **5,07 s** para o pedido mínimo. O pedido de geração completo com o schema anterior retornou **HTTP 400 / INVALID_ARGUMENT**. Um schema enxuto, com tipos e enumerações, foi aceito; o backend validou a resposta real. A correção envia somente esses tipos/enums ao Gemini e mantém limites, campos permitidos, intervalos, quantidade de rotinas e segurança validados no backend. Assim, os limites continuam estritos no Ritmo sem depender da aceitação da API para essas restrições JSON Schema.

O fluxo completo, pela rota autenticada `/api/ai/suggest` do backend ativo, foi **HTTP 200** com dados fictícios: uma rotina, seis exercícios, todos validados. A chamada não gravou dados no banco. O projeto já indicava `GEMINI_ENABLED=true`, `GEMINI_FREE_PROJECT_CONFIRMED=true` e chave presente. Nenhuma variável, chave ou plano foi alterado. O Gemini 3.1 Flash-Lite está listado com entrada/saída gratuitas no nível Free. Cotas e plano efetivos continuam sujeitos ao projeto/chave do proprietário.

Os erros agora distinguem chave/configuração, schema, modelo/endpoint, conexão, timeout, cota, resposta inválida e indisponibilidade do upstream. O log usa apenas modelo, HTTP, categoria, códigos conhecidos e duração; nunca mensagem/corpo remoto, chave ou perfil pessoal. O fluxo manual permanece disponível quando a API falha.

A interface completa de revisão e o recebimento de resposta também foram verificados no Brave local usando resposta simulada; a chamada real passou pelo backend e pelo validador, mas não pela interface instalada em produção, pois a cópia corrigida ainda não foi implantada.

Fontes oficiais consultadas em 13/10/2026: [restrições de disponibilidade dos modelos 2.5](https://ai.google.dev/gemini-api/docs/deprecations), [schema estruturado suportado](https://ai.google.dev/gemini-api/docs/generate-content/structured-output), [preço de entrada/saída do Gemini 3.1 Flash-Lite](https://ai.google.dev/gemini-api/docs/pricing#gemini-3.1-flash-lite).
## Medição de desempenho

Instrumentação adicionada:

- Console `Ritmo timing`: método, rota sem ID/query, duração até receber e interpretar a resposta e `Server-Timing`.
- Console `Ritmo save`: duração da coleta/fila/envios até confirmar a gravação.
- Header `Server-Timing`: API e banco. Banco soma tempo de instruções SQL e commit. API inclui autenticação, validação, ORM, banco e serialização. Não mede a rede/Nginx; DB não separa espera por conexão/pool.
- Log do backend: rota normalizada, método, status, tempos e quantidade de consultas. Sem SQL, parâmetros, corpos ou dados dos treinos.

Comparação controlada local, SQLite isolado, mesma rotina de 12 exercícios/36 séries, 2 aquecimentos + 10 salvamentos:

| Métrica | Código original | Código corrigido |
|---|---:|---:|
| Consultas SQL por salvamento | 16 | 5 |
| Mediana do pedido no test_client | 15,35 ms | 7,39 ms |
| Máximo | 18,40 ms | 9,67 ms |
| Mediana somente SQL | 0,55 ms | 0,39 ms |

Duas execuções posteriores marcaram medianas de 9,76 ms e 10,91 ms, com máximos de 12,60 ms e 13,08 ms. A variação é da máquina local; nenhum número representa garantia para o RF511/MySQL ou para o celular.

No Brave comum, com um exercício/duas séries no servidor local isolado: UI do salvamento 56,3 ms; pedido/resposta JSON 54,5 ms; API 6,84 ms; DB 0,72 ms. A gravação persistiu depois de recarregar.

Encontrados no código: fila de snapshots completos a cada alteração, consultas de séries por exercício e renderizações assíncronas concorrentes. São problemas corrigidos e contribuintes plausíveis para lentidão/navegação. A causa da demora observada no PWA do proprietário não foi medida no aparelho; não se extrapola o benchmark local.

## Testes executados

- `tests/check.py`: autenticação/CSRF, CRUD, sugestões locais, séries, validação, histórico e snapshots.
- `tests/corrections-check.py`: catálogo inicial editável, preservação de treino/histórico, sugestão após edição, horários inválidos, agendamento duplicado, agendado/em andamento/concluído, remoção sem perda de treino, histórico em lote e Server-Timing.
- `tests/gemini-check.py`: transporte simulado, configuração gratuita, consentimento, rascunho sem gravação, revisão/importação atômica, cotas, resposta inválida e classificação 400/401/403/404/429/500, sem chave/corpo remoto vazados.
- `tests/save-check.js`: envios repetidos, reunião da mudança mais recente, confirmação somente após resposta, falha sem perda dos campos, tentativa manual e finalização.
- `tests/reminders-check.js`: servidor indisponível, envio único, concluído/atrasado não notificado, permissão revogada e desativação.
- `tests/pwa-check.js` e `tests/search-check.js`: manifest/ícones/contraste/sem cache persistente e busca sem chamadas externas.
- Sintaxe JavaScript aprovada.
- Brave comum: agendar 15/10 às 06:00, iniciar rotina, editar carga/marcar série, salvar, recarregar, navegar a Visão geral, editar exercício inicial mantendo o nome antigo no treino, finalizar e abrir o dia com os registros vinculados. Resultado Gemini simulado exibido para revisão. Dados exclusivamente fictícios.

## O que exige etapas além do código

1. **Implantação e banco:** substituir os arquivos no RF511, reconstruir/reiniciar o backend e criar a tabela adicional `schedules` (o código a cria na inicialização). Não executado por ser uma etapa fora do código e pela queda do servidor. Preservar `.env`, banco e backups existentes; não executar scripts de atualização que alterem outros serviços/planos. Backup precisa ser resolvido antes da implantação, conforme instruções anteriores do projeto.
2. **Gemini real:** quando o RF511 estiver acessível, validar a geração pelo backend com a chave já configurada, resposta estruturada e apresentação na interface. Não ativar faturamento; se depender de plano/configuração fora do código, informar antes de alterar.
3. **PWA instalado:** os testes no Brave comum e do manifest passaram. Não foi instalado um novo PWA nem operado o aplicativo instalado no aparelho do proprietário. Salvar, navegação, latência real e retomada após perda de conexão permanecem pendentes nesse ambiente.
4. **Notificações com app fechado:** precisam de Web Push, service worker, chaves VAPID, inscrições no banco e despacho no servidor. Não foram configurados. O lembrete desta cópia só funciona enquanto a página estiver aberta; pode ser suspenso pelo navegador/sistema, não recupera atrasos acima de um minuto e não persiste o opt-in após fechar/recarregar. Suporte deve ser conferido no dispositivo previsto.
5. **Servidor desligado/sem internet:** após a reconexão, os containers do RF511 ficaram saudáveis e o endpoint da Google respondeu. Durante a queda anterior, o Ritmo não estava acessível. O teste de lembretes simula a consulta indisponível e impede envio; não se desligou o servidor do proprietário para testar a experiência real no aparelho. A entrega de notificações depende do RF511 ligado, internet e acesso via Tailscale. O Ritmo não funciona offline.

As correções estão em uma cópia local, ainda sem implantação no RF511. O backend Gemini real já respondeu e passou pela validação; a interface Gemini em produção e os testes do PWA instalado ainda dependem da implantação.

---

## Atualização v1.2.0 (14/10/2026)

### Modificações Realizadas
1. **Configuração Nginx (`nginx-termux.conf`):**
   - Adicionada diretiva `allow 127.0.0.1;` antes de `allow 100.64.0.0/10;` e `deny all;`.
   - Permite que o navegador do próprio celular acesse a aplicação em `http://127.0.0.1:8088`.
   - O W3C e navegadores Chromium reconhecem `localhost` e `127.0.0.1` como **Contexto Seguro (Secure Context)** nativo, viabilizando o registro do Service Worker e o disparo do evento `beforeinstallprompt` para instalação do PWA.
2. **Interface do Usuário (`frontend/index.html`):**
   - Inclusão da identificação visual de versão `v1.2.0` no rodapé da aplicação.
3. **Documentação e Arquitetura (`README-TERMUX.md`):**
   - Formalização da distinção entre **v1.0.x** (exigência de Gateway HTTPS externo) e **v1.2.0** (suporte autônomo standalone via `127.0.0.1`).
4. **Preservação de Dados:**
   - Realizado backup integral do estado v1.0 do projeto e do banco de dados SQLite para mídia física externa em `/caminho/do/backup-externo/Ritmo-v1.0` antes da ativação da v1.2.0.
