NEXUS — SISTEMA INTELIGENTE DE GESTÃO DE USUÁRIOS COM AUTOMAÇÃO E IA LOCAL
============================================================================

**Documentação Técnica de Projeto de Estágio (Inteligência Artificial)**

---

**Instituição:** Grupo Think
**Área:** Tecnologia da Informação / Infraestrutura de Servidores
**Autoria:** Julyana Silva (Estágio)
**Documento:** Documento de Projeto — Template 2 (Pacote de Entrega – Projeto de IA)
**Versão:** 1.0
**Data:** 04 de setembro de 2026

---

## RESUMO

Este documento apresenta o projeto NEXUS, uma solução que aplica automação orquestrada (Ansible) e Inteligência Artificial local baseada em regras para modernizar o processo de gestão de usuários (onboarding e offboarding) em múltiplos servidores Linux. O processo anterior, executado manualmente via terminal e edição de planilhas CSV, apresentava gargalos de tempo, ausência de auditoria centralizada e risco de contas esquecidas sem revisão. A solução proposta substitui esse fluxo por um painel web que executa as ações reais nos servidores, registra auditoria completa e utiliza um motor de IA local para sintetizar, em linguagem natural, a situação de cada usuário gerido — sem depender de API externa e sem enviar dados sensíveis para fora do ambiente da empresa. São descritos o diagnóstico do processo atual (AS IS), a proposta futura (TO BE), os benefícios esperados, os riscos identificados e o plano de adoção.

**Palavras-chave:** Automação de TI. Inteligência Artificial baseada em regras. Gestão de identidade e acesso. Ansible. Auditoria de segurança.

---

## SUMÁRIO

1. RESUMO EXECUTIVO
2. CONTEXTO DO PROCESSO
3. PROBLEMA IDENTIFICADO
4. SOLUÇÃO PROPOSTA COM IA
5. FLUXO TO BE (ANTES x DEPOIS)
6. BENEFÍCIOS ESPERADOS
7. RISCOS E CONTROLES
8. PLANO DE IMPLANTAÇÃO SIMPLIFICADO
9. CONCLUSÃO
APÊNDICE A — Arquitetura Técnica Detalhada
APÊNDICE B — Decisões de Arquitetura e Alternativas Consideradas
REFERÊNCIAS

---

## 1 RESUMO EXECUTIVO

**Problema.** A gestão de usuários (criação, bloqueio e remoção de contas Linux) em múltiplos servidores era feita manualmente, servidor por servidor, por meio de terminal, aliases de shell e edição direta de uma planilha CSV. Não havia auditoria centralizada, senha de administrador (sudo) era solicitada a cada execução, e não existia nenhum mecanismo automático para identificar contas bloqueadas havia muito tempo e nunca reativadas — um risco de segurança silencioso.

**Solução com IA.** O NEXUS substitui esse fluxo por um painel web (dashboard) que orquestra as ações reais nos servidores via Ansible e incorpora um motor de Inteligência Artificial local baseado em regras (`ai_engine.py`), que lê os dados de cada usuário gerido e gera, em tempo real, um resumo em português e fatos estruturados de apoio à decisão (situação da conta, tempo restante até expiração automática, nível de urgência). Um agendador diário aplica, de forma automática e auditável, a remoção de contas bloqueadas há mais de 90 dias sem intervenção humana.

**Ganho principal.** Centralização de toda a operação e da auditoria em um único painel, eliminação da digitação de senha a cada execução, eliminação de erros de digitação manual em planilha, e detecção automática de contas de risco (bloqueadas há muito tempo) que antes dependiam inteiramente da memória do analista.

---

## 2 CONTEXTO DO PROCESSO

### 2.1 Área

Tecnologia da Informação — Infraestrutura de servidores e Segurança da Informação (gestão de identidade e acesso, *Identity and Access Management*, em escala reduzida e local).

### 2.2 Objetivo do processo

Garantir que o ciclo de vida de contas de usuário em servidores Linux — criação no onboarding, bloqueio, remoção e expurgo no offboarding — seja executado de forma correta, rastreável e dentro do prazo, em todos os servidores relevantes, com registro de quem executou cada ação, quando e sob qual chamado/justificativa.

### 2.3 Descrição do processo (evolução até o NEXUS)

A gestão de usuários passou por dois estágios de evolução antes deste projeto de IA começar. É importante registrar essa linha do tempo corretamente, porque o ganho real do NEXUS só fica claro quando comparado ao processo verdadeiramente original — e não a uma versão dele que já havia sido parcialmente automatizada antes deste projeto.

#### 2.3.1 Estágio 1 — processo manual original (anterior a qualquer automação)

Antes de existir qualquer script, cada ação de gestão de usuário era feita por completo manualmente, servidor por servidor, sem nenhuma ferramenta de apoio:

1. O analista abre uma sessão SSH diretamente para um servidor específico, autenticando com **login e senha** (sem chave SSH, sem automação, um servidor de cada vez).
2. Digita, um a um, os comandos padrão do próprio Linux correspondentes à ação desejada — por exemplo `useradd`/`passwd`/`chage -d 0` para criar; `usermod -L`/`chage -E 0` para bloquear; `userdel` ou `userdel -r` para remover/purgar.
3. Confere manualmente o resultado ainda na mesma sessão (ex.: `id`, `passwd -S`).
4. Encerra a sessão e repete os passos 1 a 3 inteiramente do zero no próximo servidor, caso a mesma ação precise ser aplicada em mais de um.

Não havia script, não havia lista de servidores centralizada, não havia planilha de lote e não havia nenhum arquivo de log de auditoria — o único registro, quando existia, era feito de memória ou em anotações avulsas do próprio analista. Esse é o processo genuinamente original: mais lento, sem nenhuma padronização entre execuções, e mais sujeito a erro de digitação em comandos potencialmente destrutivos (ex.: um `userdel -r` digitado no usuário errado, sem nenhuma etapa de simulação prévia).

**Tempo médio gasto (estimativa qualificada):** da ordem de 25 a 35 minutos por ação, por servidor, somando login manual, digitação de múltiplos comandos individuais e conferência manual do resultado — sem nenhum log automático de apoio.

#### 2.3.2 Estágio 2 — protótipo com script e planilha CSV

Como uma primeira evolução — ainda anterior a este projeto de IA — foi criado, pela própria equipe, um protótipo de automação por linha de comando: um controlador remoto (`nexus_remote.sh`), uma lista de servidores em texto (`servidores.conf`), um script único que padroniza as ações no servidor de destino (`nexus_sanitize_users.sh`) e um arquivo de lote (`usuarios.csv`) onde o analista descrevia os usuários e ações a processar. Esse script continua existindo e é reaproveitado pelo NEXUS sem alterações na lógica (ver seção 4.2).

Esse protótipo trouxe uma melhoria real sobre o Estágio 1 — o mesmo comando sempre executa a mesma sequência testada de ações no servidor, sem depender da memória do analista para lembrar cada comando individual, e passou a gerar relatórios de execução (TXT/JSON/CSV) em cada servidor. Mas manteve dois atritos importantes, que se tornaram o novo gargalo:

**Fluxo sequencial do Estágio 2:**

1. O analista abre um terminal com acesso SSH à máquina de controle.
2. Edita manualmente o arquivo `usuarios.csv`, adicionando/alterando a linha do usuário e da ação desejada (criar, bloquear, remover).
3. Confere manualmente, olhando o arquivo `servidores.conf`, em qual(is) servidor(es) a ação deve ser aplicada.
4. Executa o comando de simulação (`nexus-users-dry`) e revisa a saída no próprio terminal.
5. Executa o comando real (`nexus-users-apply`), digitando a senha de sudo daquele servidor — repetindo esse passo a cada novo servidor de destino.
6. Confirma manualmente, olhando arquivos de log gerados em `/var/log/nexus/` em cada servidor (TXT, JSON e CSV separados), se a ação realmente teve sucesso.
7. Não existe nenhuma etapa automática de revisão periódica: identificar uma conta bloqueada há mais de 90 dias dependia de o analista lembrar de checar manualmente, servidor por servidor.

**Pontos manuais:** edição de CSV em texto puro; digitação de senha de sudo a cada execução e a cada servidor; conferência de logs espalhados por servidor, sem consolidação.

**Retrabalho:** repetição do mesmo procedimento por servidor (sem execução paralela nem lote unificado); nenhuma reutilização de decisão já tomada (ex.: "este servidor não pede senha") entre execuções.

**Erros frequentes:** erro de digitação de nome de grupo/shell em texto livre no CSV; ausência de validação de senha temporária (sem exigência de complexidade); uso recorrente da mesma senha temporária padrão da equipe, que na prática nunca era trocada por muitos usuários.

**Tempo médio gasto (estimativa qualificada, a validar com medição real após adoção plena):** aproximadamente 15 a 20 minutos por ação, por servidor, somando edição de CSV, execução, digitação de senha e conferência manual de log — ação replicada em cada servidor de destino, sem paralelismo. Já representa uma melhoria frente ao Estágio 1, mas ainda está longe do potencial de automação real.

#### 2.3.3 Ponto de partida deste projeto (AS IS de referência)

Este projeto de IA parte do **Estágio 2** como baseline operacional imediato: é esse fluxo de scripts e planilha CSV que o NEXUS Dashboard substitui diretamente, reaproveitando a lógica já testada do script (`nexus_sanitize_users.sh`) sem reescrevê-la, mas eliminando a necessidade de editar CSV manualmente e de digitar senha a cada execução. A comparação AS IS x TO BE apresentada nas seções 3 e 5 deste documento toma o Estágio 2 como referência de "processo atual", por ser o que estava efetivamente em uso no momento em que este projeto foi iniciado. O Estágio 1 é apresentado aqui como contexto histórico indispensável, para que o ganho do projeto seja dimensionado sobre a evolução completa do processo, não apenas sobre a etapa mais recente dela.

---

## 3 PROBLEMA IDENTIFICADO

### 3.1 Gargalos

- **Ausência de auditoria centralizada.** Cada servidor mantinha seu próprio conjunto de relatórios (TXT/JSON/CSV), sem visão consolidada de "quem fez o quê, quando, em qual servidor, com qual justificativa".
- **Atrito de autenticação repetido.** Senha de administrador (sudo) solicitada a cada execução e por servidor, mesmo quando a mesma ação era aplicada a vários servidores em sequência.
- **Sem alerta para contas esquecidas.** Uma conta bloqueada (ex.: colaborador afastado) não tinha nenhum mecanismo que sinalizasse "esta conta está bloqueada há muito tempo e nunca foi decidida a remoção definitiva" — dependia inteiramente de memória humana.
- **Validação de dados fraca.** Campos como grupo e shell eram texto livre digitado em CSV, sem lista de valores válidos; a senha temporária de criação de conta não tinha nenhuma regra mínima de complexidade.
- **Nenhuma visão executiva.** Não existia painel, indicador ou relatório gerencial — apenas arquivos de log técnicos, não voltados a leitura por gestores.

### 3.2 Impactos no negócio

- **Risco de segurança:** contas bloqueadas sem revisão por tempo indeterminado são superfície de ataque — se reativadas indevidamente ou nunca formalmente encerradas, representam um risco de acesso não autorizado.
- **Risco de conformidade/auditoria:** sem registro centralizado de quem executou cada ação e com qual justificativa (chamado), é mais difícil comprovar, em uma auditoria, que o processo de desligamento de acesso foi seguido corretamente.
- **Custo operacional:** tempo do analista consumido em tarefas repetitivas e mecânicas (digitar senha, editar CSV, checar log por servidor), que poderia ser direcionado a atividades de maior valor.
- **Erro humano:** planilha editada manualmente é fonte recorrente de inconsistência (nome de grupo errado, shell incorreto, esquecimento de linha).

### 3.3 Quem é impactado

- **Analistas de infraestrutura/segurança** — executores diretos do processo, hoje sobrecarregados por tarefas manuais e repetitivas.
- **Gestores de segurança e compliance** — dependem de auditoria confiável para responder "quem tinha acesso a quê, e por quê".
- **Colaboradores da empresa** — usuários finais das contas criadas/removidas; atrasos ou erros no processo afetam diretamente seu acesso a sistemas no primeiro dia de trabalho ou geram risco se o desligamento não for concluído a tempo.
- **Diretoria** — carece de visibilidade executiva sobre volume de ações, servidores geridos e status de segurança das contas.

---

## 4 SOLUÇÃO PROPOSTA COM IA

### 4.1 Onde a IA entra

A Inteligência Artificial do NEXUS está no módulo `ai_engine.py`, embutido na própria aplicação web, em produção. Para cada usuário gerido, o motor:

- lê os dados já coletados no banco local (status da conta, grupos/permissões, data de criação, data de bloqueio, chamado associado, histórico de comandos executados via SSH — coletado de forma best-effort);
- calcula fatos derivados (dias bloqueado, dias restantes até a remoção automática aos 90 dias, se o caso é urgente);
- monta, em tempo real, um **resumo em português** e um conjunto de **fatos estruturados**, exibidos no painel "IA NEXUS" da página de detalhe de cada usuário.

### 4.2 Qual decisão, análise ou tarefa ela apoia

O motor de IA apoia a decisão operacional mais crítica do processo: **"esta conta precisa de atenção agora, e por quê?"** — substituindo a necessidade de o analista cruzar manualmente múltiplos campos (status, data de bloqueio, histórico) para chegar à mesma conclusão. Também sinaliza casos que exigem revisão humana obrigatória — por exemplo, contas descobertas como pré-existentes no servidor (importadas de fora do NEXUS), cuja data real de bloqueio é desconhecida e que, por isso, **não** entram automaticamente na contagem dos 90 dias até que um analista confirme manualmente o início da contagem.

### 4.3 Qual tecnologia/conceito de IA é usada, e por quê

Trata-se de **IA baseada em regras (sistema especialista determinístico)** — não um modelo de linguagem (LLM) nem uma API externa. A lógica é toda condicional (`if`/`elif`) sobre dados estruturados já existentes no banco. Essa escolha foi deliberada (ver Apêndice B): é auditável (qualquer decisão do "resumo da IA" pode ser explicada linha a linha do código), roda sem custo de API, e principalmente **nenhum dado de servidor ou de usuário sai da rede da empresa** — requisito relevante em um projeto que lida com dados de infraestrutura e credenciais.

Combinada à camada de **automação inteligente** (Ansible orquestrando ações reais nos servidores) e à camada de **decisão automática auditável** (expurgo automático de contas expiradas, detecção automática de servidores sem exigência de senha), o NEXUS se enquadra nas três categorias aceitas pelo escopo do projeto: IA generativa não é usada; IA preditiva/de regras e automação inteligente, sim.

### 4.4 Exemplo prático

Um usuário `joao.silva` foi bloqueado há 82 dias. Sem o NEXUS, essa informação estaria implícita em um `chage -l` rodado manualmente, servidor por servidor. Com o NEXUS, a página do usuário mostra, gerado pela IA local:

> "joao.silva está bloqueado há 82 dia(s) — restam 8 dia(s) até a remoção automática. Próximo do limite: será removido automaticamente pelo NEXUS se não houver ação manual antes disso."

Essa frase é montada dinamicamente a partir de `LOCK_MAX_DAYS = 90` e `LOCK_WARNING_DAYS = 80` (config.py), cruzando a data de bloqueio real gravada no banco — sem qualquer intervenção manual de cálculo.

---

## 5 FLUXO TO BE (ANTES x DEPOIS)

| Etapa do processo | AS IS (antes) | TO BE (com NEXUS) |
|---|---|---|
| Autenticação por execução | Senha de sudo digitada a cada execução, por servidor | Senha configurada uma única vez por servidor (Ansible Vault); nunca mais solicitada depois |
| Definição da ação | Edição manual de linha em CSV, campos em texto livre | Formulário web com validação; grupos e shell restritos a opções válidas |
| Execução em múltiplos servidores | Um servidor por vez, sequencial, manual | Seleção múltipla ("Selecionar todos"), execução orquestrada via Ansible |
| Simulação antes de aplicar | Comando de dry-run separado, no terminal | Botão "Simular" na mesma tela, sem trocar de ferramenta |
| Auditoria | Arquivos de log (TXT/JSON/CSV) dispersos por servidor | Tabela única de auditoria (`action_log`), consultável e filtrável, com paginação |
| Contas bloqueadas há muito tempo | Sem alerta; dependia de checagem manual periódica (se houvesse) | Alerta visual a partir de 80 dias; remoção automática e auditável aos 90 dias |
| Resumo da situação de um usuário | Reconstruído manualmente cruzando múltiplos campos/logs | Gerado automaticamente pela IA local, em português, em tempo real |
| Visão executiva | Inexistente | Painel com indicadores e gráficos (usuários por status, execuções por dia, execuções por servidor) |
| Adição de novo servidor | Configuração manual, sem checagem prévia | Cadastro testa a conexão SSH na hora; detecta automaticamente se o servidor exige senha de sudo; importa usuários pré-existentes automaticamente |

**Fluxo TO BE, sequencial:**

1. Analista identifica-se no painel (registro de auditoria — sem senha, apenas nome).
2. Servidor de destino já está cadastrado (com senha de sudo configurada uma única vez, ou detectado automaticamente como isento dela).
3. Analista preenche o formulário "Nova Ação" (usuário, chamado, ação, servidor(es) de destino).
4. Clica em "Simular" para revisão prévia.
5. Clica em "Aplicar" — o Ansible executa a ação real no(s) servidor(es) selecionado(s), em lote.
6. O resultado (sucesso, ignorado, bloqueado ou falha real) é gravado automaticamente na auditoria central e refletido na tela.
7. A partir daí, a IA local mantém o resumo do usuário atualizado a cada acesso à sua página de detalhe, sem nenhuma ação manual adicional.
8. Diariamente, às 03h, o agendador confere sozinho todas as contas bloqueadas e remove automaticamente as que atingiram 90 dias, registrando a ação como automática na auditoria.

---

## 6 BENEFÍCIOS ESPERADOS

### 6.1 Operacionais

- **Redução de tempo por ação:** eliminação da digitação repetida de senha (uma configuração por servidor, não por execução) e da execução sequencial servidor a servidor (agora em lote). Estimativa qualificada, a confirmar com medição em produção: redução da ordem de 70–85% no tempo operacional por ação, quando aplicada a mais de um servidor simultaneamente.
- **Redução de erros:** campos antes em texto livre (grupo, shell) passaram a ser seleção fixa validada; senha temporária passou a exigir complexidade mínima (10 caracteres, maiúscula, minúscula e caractere especial) e teve a senha padrão informal da equipe explicitamente banida no backend.
- **Auditoria unificada:** uma única tabela central (`action_log`) substitui logs fragmentados por servidor, com filtros por servidor, usuário, ação, status e origem (manual/automática), e paginação para grandes volumes.
- **Detecção proativa de risco:** identificação automática de contas bloqueadas próximas do limite de 90 dias, com remoção automática auditável quando não há ação manual — elimina a dependência de memória humana para esse controle.

### 6.2 Estratégicos

- **Melhoria da qualidade da informação para auditoria e compliance:** rastreabilidade completa de quem fez o quê, quando e sob qual chamado, em todos os servidores geridos.
- **Escalabilidade:** adicionar um novo servidor à operação passou a ser um cadastro simples, com teste de conexão, detecção de necessidade de senha e importação de usuários já existentes ocorrendo automaticamente — sem exigir reconfiguração manual da lógica de automação.
- **Independência de ferramentas externas para a camada de IA:** por rodar localmente, o custo de operação da inteligência do sistema não cresce com o uso e não depende de disponibilidade de terceiros.
- **Base para evolução futura:** a estrutura de dados centralizada (SQLite com histórico completo) viabiliza, no futuro, relatórios executivos mais ricos ou modelos preditivos mais sofisticados, caso o negócio decida investir nessa direção.

---

## 7 RISCOS E CONTROLES

### 7.1 Técnicos

- **Onde a IA pode errar:** por ser um sistema de regras determinístico (não um modelo de linguagem), a IA não "alucina" no sentido de um LLM, mas seu resumo é tão correto quanto os dados de origem. Duas fontes de imprecisão conhecidas foram identificadas e mitigadas: (a) o histórico de comandos coletado via `~/.bash_history` não registra comandos de uma sessão SSH ainda aberta no momento da coleta — mitigado com aviso explícito na tela; (b) contas descobertas como pré-existentes no servidor não têm data de bloqueio confiável — mitigado exigindo confirmação manual antes de entrarem na contagem automática de expiração.
- **Dependência de dados:** a qualidade de toda a análise depende da confiabilidade da coleta feita via Ansible/SSH. Falhas de conectividade, chave SSH não autorizada ou indisponibilidade do servidor de destino resultam em dados desatualizados, não em dados incorretos — o sistema sinaliza status de falha em vez de presumir sucesso (correção aplicada após identificação de um bug crítico em que uma execução ignorada pelo script de baixo nível era erroneamente registrada como sucesso).

### 7.2 Operacionais

- **Ponto único de operação (VM ponte):** toda a automação depende de uma única máquina intermediária que concentra a chave SSH privada e o banco de auditoria. Indisponibilidade dessa máquina interrompe a operação até restabelecimento — mitigação recomendada: backup periódico do banco (`db/nexus.db`) e do diretório de credenciais do Ansible.
- **Necessidade de validação humana em ações irreversíveis:** ações de remoção/expurgo aplicam mudanças reais e, em parte dos casos, irreversíveis (exclusão da pasta pessoal do usuário). O uso do botão "Simular" antes de "Aplicar" é recomendado como prática padrão, mas não é tecnicamente obrigatório — trata-se de um controle de processo, não de um bloqueio de sistema.
- **Remoção automática sem intervenção humana:** a expiração de 90 dias remove contas automaticamente. Embora auditável (fica registrada como ação automática, distinta de ação manual) e alertada com antecedência (a partir de 80 dias), representa uma decisão de negócio que ocorre sem aprovação humana no momento da execução — ponto que deve ser validado formalmente com a área responsável pelo processo de desligamento.

### 7.3 Éticos / segurança

- **Concentração de credenciais:** a senha de administrador (sudo) de cada servidor gerido fica armazenada de forma criptografada (Ansible Vault) na VM ponte. Comprometer essa máquina expõe o acesso privilegiado a todos os servidores geridos — risco inerente a qualquer ferramenta de orquestração centralizada, mitigado por: senha por servidor (não compartilhada), arquivo de credenciais fora do controle de versão, e chave SSH privada que nunca é exportada da máquina ponte.
- **Ausência de autenticação de acesso ao próprio painel:** a identificação de operador registra apenas um nome, sem senha — suficiente para fins de auditoria interna, mas não constitui controle de acesso real à ferramenta. Qualquer pessoa com acesso à rede onde o painel está exposto pode operá-lo. Recomenda-se, como controle complementar (fora do escopo técnico atual), restringir o acesso à URL do painel por rede/VPN e avaliar autenticação formal em uma evolução futura.
- **Dados sensíveis no histórico de comandos:** o histórico de comandos coletado pode conter informações sensíveis; o processo já redige (mascara) credenciais reconhecíveis antes de exibir ou disponibilizar para download, mas a proteção do arquivo `db/nexus.db` como um todo permanece responsabilidade operacional da equipe.

---

## 8 PLANO DE IMPLANTAÇÃO SIMPLIFICADO

### 8.1 Curto prazo

- Consolidar a operação diária integralmente no painel NEXUS, mantendo o fluxo antigo por terminal apenas como contingência de emergência (já é o estado atual documentado).
- Validar, junto à liderança da área, o processo de exceção para a remoção automática de 90 dias (quem deve ser avisado antes, e com quanto tempo de antecedência além do alerta de 80 dias já existente).
- Medir, em produção, o tempo real por ação (antes vs. depois) para substituir as estimativas qualificadas apresentadas na seção 6 por números reais.
- Definir política de backup do banco de auditoria (`db/nexus.db`) e das credenciais do Ansible Vault.

### 8.2 Próximos passos

- **Quem usaria:** analistas de infraestrutura/segurança, como operadores diários; gestores de segurança e diretoria, como consumidores de auditoria e indicadores do Painel.
- **Frequência de uso:** uso orientado a evento (a cada admissão/desligamento/mudança de acesso) para a operação manual, e uso automático diário (03h) para a verificação de expiração — sem necessidade de ação humana recorrente para esse controle específico.
- **Como garantir que vire rotina:** (a) tornar o registro de chamado/justificativa obrigatório no formulário, o que já força o uso do fluxo padronizado; (b) manter o fluxo antigo (terminal) documentado apenas como emergência, não como alternativa de uso corrente; (c) capacitação rápida da equipe, já que a interface foi desenhada para ser autoexplicativa (campos condicionais, tooltips, validação em tempo real); (d) uso do Painel em reuniões periódicas de segurança/infraestrutura como fonte oficial de indicadores, reforçando sua adoção como ferramenta de referência.

---

## 9 CONCLUSÃO

O NEXUS demonstra, em um processo real e recorrente da área de infraestrutura, como automação orquestrada e uma camada de Inteligência Artificial local e auditável podem substituir um fluxo manual, propenso a erro e sem visibilidade centralizada, por um processo padronizado, rastreável e com detecção proativa de risco — sem depender de serviços externos e sem custo adicional de operação da camada de IA. O projeto vale a pena porque resolve uma dor concreta e mensurável da equipe (tempo operacional, erro humano e ausência de auditoria), ao mesmo tempo em que introduz um controle de segurança que antes não existia de forma sistemática — a identificação e o encerramento automático de contas de acesso esquecidas. O escopo foi deliberadamente mantido enxuto (IA de regras, não IA generativa; foco exclusivo em gestão de usuários, sem reintroduzir escopos removidos como scanner de segurança), o que tornou a solução mais simples de manter, de explicar e de confiar — um critério tão importante quanto a sofisticação técnica em um projeto cujo objetivo é apoiar decisões operacionais e de segurança.

---

## APÊNDICE A — Arquitetura Técnica Detalhada

```
Navegador (analista) ── HTTP ──> Flask (VM ponte) ── Ansible ──> Servidores geridos
                                       │
                                       └── SQLite (nexus.db): servidores, usuários
                                           geridos, auditoria/timeline, histórico
                                           coletado
```

- **Backend:** Flask ≥ 3.0 (Python), renderização server-side com Jinja2 — sem framework de frontend separado.
- **Persistência:** SQLite local (`nexus_dashboard/db/nexus.db`) — tabelas `servers`, `managed_users`, `action_log`, `collected_facts`.
- **Automação remota:** Ansible (`ansible-core` ≥ 2.15, orquestrado via `ansible-runner` ≥ 2.3), reaproveitando sem reescrita o script já validado `nexus_sanitize_users.sh` — o Ansible apenas copia e executa esse script no servidor de destino.
- **Camada de IA:** `ai_engine.py` — motor de regras determinístico, sem chamadas de rede.
- **Agendamento:** APScheduler ≥ 3.10, job diário às 03h00, dentro do próprio processo Flask.
- **Autenticação em duas camadas por servidor gerido:** chave SSH (login) + Ansible Vault (senha de sudo, uma por servidor, criptografada) — camadas independentes, exigidas pelo próprio modelo de segurança do Linux.
- **Ações auditáveis suportadas:** `create`/`add` (criação), `lock` (bloqueio reversível), `remove`/`delete` (remoção preservando ou não a pasta pessoal, conforme configuração) e `purge` (remoção definitiva, sempre com exclusão da pasta pessoal).
- **Regras de expiração:** aviso visual a partir de 80 dias bloqueado (`LOCK_WARNING_DAYS`); remoção automática aos 90 dias (`LOCK_MAX_DAYS`) — parâmetros configuráveis em `config.py`.

---

## APÊNDICE B — Decisões de Arquitetura e Alternativas Consideradas

| Decisão adotada | Alternativa considerada | Justificativa |
|---|---|---|
| IA local baseada em regras | Modelo de linguagem via API externa | Sem custo por uso; nenhum dado de servidor/usuário sai da empresa; decisões auditáveis linha a linha |
| SQLite | Manutenção do fluxo em CSV/JSON | Permite consultas agregadas (dias bloqueado, contagens, filtros) e é a base do controle de 90 dias |
| Flask + Jinja2 (server-side) | Frontend separado (ex.: React) + API | Menor complexidade de manutenção, mais fácil de explicar e operar por uma equipe pequena |
| Reaproveitamento do `nexus_sanitize_users.sh` via Ansible | Reimplementação em módulos nativos do Ansible | O script já possuía lógica testada em produção (contas protegidas, hash de senha temporária); reimplementar duplicaria risco sem ganho correspondente |
| Senha de sudo por servidor (Ansible Vault) | Senha global compartilhada | Servidores diferentes possuem, na prática, senhas de sudo distintas |
| Identificação de operador simples (nome, sem senha) | Sistema de login/senha completo | Fora do escopo solicitado; suficiente para o objetivo de auditoria interna definido para este projeto |
| Exclusão de servidor: apenas "soft delete" quando há histórico | Exclusão sempre permitida | Preserva integridade referencial da auditoria (tabelas de usuários e execuções referenciam o servidor) |

---

## REFERÊNCIAS

GRUPO THINK. *NEXUS — Documentação Técnica*: decisões de arquitetura, bugs resolvidos e perguntas frequentes. Documentação interna de desenvolvimento. Disponível em: `docs/DOCUMENTACAO_TECNICA.md`.

GRUPO THINK. *NEXUS Dashboard — Gestão de Usuários via Interface Gráfica*: manual de instalação e operação. Documentação interna. Disponível em: `nexus_dashboard/README_dashboard.md`.

GRUPO THINK. *NEXUS — Gestão de Usuários*: visão geral do projeto. Documentação interna. Disponível em: `README.md`.

*(Repositório de código-fonte privado — acesso restrito à equipe do projeto.)*
