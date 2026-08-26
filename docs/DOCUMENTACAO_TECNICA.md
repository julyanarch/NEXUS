# NEXUS — Documentação Técnica

Base explicativa do projeto NEXUS (gestão de usuários via Ansible + dashboard web + IA local),
para consulta e apresentações futuras. Este documento é vivo: cresce conforme novas dúvidas
técnicas surgem durante o desenvolvimento e os testes.

---

## 1. O que é o projeto

O NEXUS automatiza o onboarding/offboarding de usuários Linux em múltiplos servidores, substituindo
um fluxo antigo baseado em terminal + aliases + edição manual de CSV por um **dashboard web**
(tema roxo/preto) que:

- executa as ações reais (criar, bloquear, remover, purgar usuário) via **Ansible**, sem pedir
  senha por servidor a cada execução;
- guarda todo o histórico/auditoria de quem fez o quê, quando, e com qual chamado;
- tem uma **IA local baseada em regras** (sem API externa) que resume cada usuário: permissões,
  dias bloqueado, criação, documentos vinculados, comandos executados (best-effort);
- remove automaticamente, após 90 dias de bloqueio, contas que não foram reativadas — avisando
  antes de agir.

### Por que o nome mudou de "CORTEX" para "NEXUS"

O nome original do projeto colidia com o nome da IA interna da própria empresa. Como o projeto
passou a ter sua própria IA (motor de regras local) e sua própria identidade, foi renomeado para
evitar confusão de marca.

### Por que o scan de segurança saiu do projeto

O projeto original incluía um scanner de risco (`cortex_scan.sh` + `cortex_analyzer.py`). Foi
decidido remover essa parte do repositório: o foco passou a ser exclusivamente **gestão de
usuários**, não hardening/scan de segurança.

---

## 2. Duas autenticações diferentes — por que a chave SSH não elimina tudo

Uma dúvida recorrente: "se configurei chave SSH, por que ainda preciso digitar uma senha de sudo?"

No Linux, entrar no servidor e ter privilégio de administrador são **duas barreiras distintas**:

| Camada | Pergunta que resolve | Como o NEXUS resolve |
|---|---|---|
| 1. SSH (login) | "Quem é você?" | Chave SSH (`ssh-keygen` + `ssh-copy-id`) — zero senha |
| 2. `sudo` (privilégio) | "Você pode agir como root?" | Ansible Vault (senha guardada criptografada) |

A chave SSH resolve **só a camada 1**. Criar/bloquear/remover usuário exige root
(`useradd`/`userdel`/etc.), e o Linux exige senha de `sudo` pra isso **independente** de como você
entrou no servidor — uma coisa não substitui a outra.

A tela "senha sudo" (por servidor) não pede a senha antes de cada ação — é uma configuração feita
**uma única vez por servidor**. A partir daí, toda execução (Simular, Aplicar, Forçar remoção, etc.)
usa essa senha guardada automaticamente, sem nenhum prompt. Ou seja:

- **Antes** (`cortex_remote.sh`, jeito antigo): senha pedida a cada execução.
- **Agora**: senha configurada uma vez por servidor; nunca mais pedida depois disso.

### Por que a senha de sudo é configurada por servidor, e não uma só global

Servidores diferentes podem ter usuários/senhas de sudo diferentes (ex.: `think@douglas` e
`andressa.silva@andressa` têm senhas distintas). Por isso o Vault do NEXUS guarda uma senha
separada por servidor (`ansible/host_vars/<nome-do-servidor>/vault.yml`), não uma senha única
compartilhada.

### Alternativa (não usada aqui) para eliminar até essa configuração única

Seria configurar `NOPASSWD` no `sudoers` de cada servidor gerenciado. Isso eliminaria até a
etapa de configurar a senha no Vault, mas é uma mudança de segurança nos servidores gerenciados
(qualquer processo autenticado por aquela chave SSH poderia virar root sem senha nenhuma) — não é
o padrão escolhido para este projeto.

### Onde gerar a chave SSH — só uma vez, só na ponte

A chave SSH é gerada **uma única vez, na máquina ponte** (onde o dashboard roda), nunca dentro dos
servidores gerenciados. O `ssh-copy-id` só envia a parte **pública** da chave (não é segredo) para
autorizar cada servidor novo — a chave privada nunca saí da ponte. Para adicionar mais um servidor
à demonstração, não é preciso gerar chave nova: só rodar `ssh-copy-id usuario@novo-servidor` de
novo, reaproveitando a mesma chave.

---

## 3. Arquitetura

```
Navegador (Windows) ── HTTP ──> Flask (VM ponte) ── Ansible ──> servidores gerenciados (douglas, andressa, ...)
                                     │
                                     └── SQLite (nexus.db): servidores, usuários geridos,
                                         auditoria/timeline, documentos vinculados, histórico coletado
```

- **Backend**: Flask (Python), server-side com Jinja2 — sem framework de frontend.
- **Persistência**: SQLite local (`db/nexus.db`) — servidores, usuários geridos e status, log de
  ações/auditoria, documentos, fatos coletados (histórico de comandos).
- **Automação remota**: Ansible (via `ansible-runner`), reaproveitando o script já testado
  `nexus_sanitize_users.sh` sem reescrever a lógica — o Ansible só copia e executa esse script no
  servidor de destino.
- **IA**: motor de regras local (`ai_engine.py`) — lê os dados do SQLite e monta um resumo em
  português + fatos estruturados. Não chama nenhuma API externa; nenhum dado sai da máquina.
- **Expiração automática**: job diário (APScheduler) dentro do próprio processo Flask, que verifica
  contas bloqueadas e remove automaticamente ao completar 90 dias (com aviso visual a partir de 80).

### Importante: as ações são reais, não só registros no banco

Quando uma ação é "Aplicada" pelo dashboard, o Ansible executa de verdade o
`nexus_sanitize_users.sh` **dentro do servidor de destino** — o mesmo script que já existia,
fazendo `useradd`, `usermod -L`, `userdel`, etc. de verdade no sistema operacional daquele servidor.
O banco do NEXUS guarda só o **histórico/auditoria** da ação (quem fez, quando, com qual chamado);
o usuário real vive no `/etc/passwd`/`/etc/shadow` do servidor, como sempre viveu. Isso pode ser
confirmado entrando via SSH direto no servidor:

```bash
getent passwd nome.usuario
id nome.usuario
sudo passwd -S nome.usuario     # ativo, bloqueado, etc.
sudo chage -l nome.usuario      # expiração
```

---

## 4. Fluxo de trabalho entre PC pessoal e VM da empresa (via Git)

O código é escrito no PC pessoal (VS Code) e a VM roda num notebook físico diferente (da empresa) —
são duas máquinas separadas, sem pasta compartilhada entre elas. A solução adotada foi um
**repositório privado no GitHub** (`https://github.com/julyanarch/NEXUS`):

```
PC pessoal (git push)  →  GitHub (repo privado)  →  VM da empresa (git pull)
```

- No PC pessoal, depois de qualquer mudança: `git add . && git commit -m "..." && git push`.
- Na VM, pra trazer a atualização: `git pull`.
- A VM nunca precisa commitar nada, a menos que algum arquivo seja editado diretamente nela.
- Autenticação no GitHub (repo privado) via token de acesso pessoal ou chave SSH configurada na VM.

---

## 5. Ambiente Python (`.venv`)

`.venv` é um ambiente virtual do Python — uma cópia isolada do Python só para este projeto, numa
pasta própria (`nexus_dashboard/.venv/`). Sem isso, os pacotes do projeto (Flask, ansible-runner,
etc.) iriam para o Python do sistema inteiro da VM.

- Criado uma vez: `python3 -m venv .venv`
- Precisa ser **ativado a cada nova sessão de terminal**: `source .venv/bin/activate` (o prompt
  passa a mostrar `(.venv)` na frente quando está ativo). Isso não é permanente — fechar o
  terminal ou reconectar o SSH perde a ativação, e é preciso rodar o comando de novo.
- Para sair dele: `deactivate`.

---

## 6. Cadastrando novos servidores (ex.: para demonstração)

1. Autorizar a chave SSH da ponte nesse servidor (reaproveitando a mesma chave já existente):
   ```bash
   ssh-copy-id usuario@IP-DO-NOVO-SERVIDOR
   ```
2. Cadastrar na interface — **Servidores → + Novo servidor** (nome, usuário SSH, host, porta).
   O arquivo `servidores.conf` só é lido **uma vez**, na primeira execução do projeto (para
   popular o banco); depois disso, quem manda é o banco de dados, editado pela própria tela.
3. Configurar a senha de sudo desse servidor (botão "senha sudo" na lista de Servidores).
4. Testar conexão.

---

## 7. O que o Painel mostra

A tela **Painel** entrega a proposta original de dashboard: cartões-resumo (usuários ativos,
bloqueados, expirando em breve ≥80 dias, removidos) e duas tabelas (usuários bloqueados próximos
da remoção automática de 90 dias; execuções recentes). Os números começam zerados até a primeira
ação real ser aplicada — a partir daí o Painel e a tela de Usuários (com o painel da IA NEXUS por
usuário) passam a refletir dados reais.

---

## 8. Problemas encontrados durante o setup e como foram resolvidos

| Sintoma | Causa | Solução |
|---|---|---|
| `ssh-copy-id`: "ERROR: No identities found" | Nenhuma chave SSH gerada ainda na ponte | Rodar `ssh-keygen -t ed25519` antes (uma vez, sem senha) |
| `Command 'python' not found` | `.venv` não estava ativado nessa sessão de terminal | `source .venv/bin/activate` antes de `python app.py` |
| `Address already in use` na porta 5000 | Processo anterior do Flask ainda rodando (sessão SSH caiu sem encerrar) | Achar o PID (`ss -tlnp \| grep :5000`) e `kill <PID>` |
| `[ERROR]: The vault-ids default,default are available to encrypt` ao salvar a senha de sudo | `vault_password_file` declarado tanto no `ansible.cfg` quanto explicitamente no comando — duas fontes ambíguas | Remover a declaração duplicada do `ansible.cfg`, mantendo só a passagem explícita no código |
| Tela mostrava versão antiga da interface após corrigir o código | `git pull` não tinha sido executado (ou servidor não foi reiniciado) na VM antes de testar | Confirmar `git log --oneline -3` bate com o último commit, `git pull`, reiniciar `python app.py` |

---

## 9. Decisões de arquitetura e por quê (resumo rápido)

| Decisão | Alternativa considerada | Por que essa escolha |
|---|---|---|
| IA local baseada em regras | IA de linguagem real (API externa) | Sem custo, sem enviar dados de servidores/usuários para fora |
| SQLite | Continuar em CSV/JSON | Permite consultas (dias bloqueado, contagens) e é a base do rastreio de 90 dias |
| Flask + Jinja2 (server-side) | FastAPI + frontend separado (React) | Mais simples de manter e explicar; menos peças móveis |
| Reaproveitar `nexus_sanitize_users.sh` via Ansible `copy`+`command` | Reimplementar em módulos nativos do Ansible (`user`, etc.) | O script já tinha lógica testada (contas protegidas, hash de senha temporária, relatórios); reimplementar duplicaria risco sem ganho |
| Senha de sudo por servidor (Ansible Vault, `host_vars`) | Uma senha global compartilhada | Servidores diferentes têm senhas de sudo diferentes na prática |
| Identificação de operador simples (nome, sem senha) | Sistema de login completo | Fora do escopo pedido; suficiente para registro de auditoria interna |
| Exclusão de servidor só permitida sem histórico; senão só "desabilitar" | Excluir sempre, sem checagem | Excluir um servidor com usuários/execuções já registrados apagaria/orfanaria a auditoria (a tela de Usuários usa `JOIN` com a tabela de servidores) |
| Cadastro permite dois servidores com o mesmo host/IP e usuários SSH diferentes | Bloquear host duplicado | É um padrão válido no Ansible (contas de acesso diferentes numa mesma máquina física); o sistema só avisa, não bloqueia |

---

## 10. Perguntas frequentes durante os testes

**"Cadastrei um servidor novo com o mesmo host de outro já existente, só que com usuário SSH
diferente, e funcionou — isso está certo?"** Sim. Não há trava para host duplicado, só para nome
duplicado — porque ter mais de uma "entrada" apontando pra mesma máquina física, cada uma com seu
próprio usuário SSH (e sua própria senha de sudo no Vault), é uma situação legítima. O NEXUS agora
avisa (sem bloquear) quando isso acontece, caso tenha sido sem querer.

**"Por que só tem 'editar' e 'desabilitar' nos servidores, sem 'excluir'?"** Porque excluir de
verdade um servidor que já tem usuários geridos ou ações registradas quebraria a auditoria (as
telas de Usuários/Execuções dependem de conseguir achar o nome do servidor a partir do histórico).
Por isso o NEXUS oferece **exclusão apenas para servidores sem histórico nenhum** (cadastros feitos
por engano, por exemplo) — nesse caso aparece um botão "excluir". Quando já existe histórico, só
"desabilitar" fica disponível, o que remove o servidor das ações futuras sem apagar o passado.

**"A senha temporária de criação de usuário não pedia nenhum requisito — e ela serve só pro
primeiro login, certo?"** As duas coisas foram ajustadas/confirmadas:

- **Requisitos de senha**: agora a senha temporária (tela Nova Ação → criar usuário) exige no
  mínimo 10 caracteres, com letra maiúscula, letra minúscula e caractere especial. A validação
  acontece nos dois lados: no navegador (feedback imediato) e no servidor Flask (é a que realmente
  decide — nunca confie só na validação do navegador, ela pode ser contornada). O limite mínimo
  fica em `config.TEMP_PASSWORD_MIN_LENGTH`, fácil de ajustar depois.
- **Só serve para o primeiro login, sim.** O `nexus_sanitize_users.sh` roda `chage -d 0` no usuário
  logo depois de definir essa senha — isso zera a data da última troca de senha, o que força o
  Linux a exigir uma nova senha (definida pelo próprio usuário) no primeiro acesso via SSH. Depois
  dessa troca, a senha temporária deixa de valer.

**"Numa apresentação, se perguntarem 'onde entra a IA integrada nesse projeto', o que eu respondo?"**
Resposta certa: **o `ai_engine.py`, dentro do `nexus_dashboard/`** — um motor de regras local que
roda dentro da aplicação já em produção, lê os dados de cada usuário gerido (status, grupos, dias
bloqueado, documentos, histórico de comandos) e gera em tempo real o resumo em português + fatos
estruturados exibidos no painel "IA NEXUS" da página de detalhe do usuário. Não depende de API
externa.

O que **não** é a resposta: dizer que "a IA (o Claude, usado durante o desenvolvimento) + o
Ansible fizeram a parte visual" — isso descreve *como o projeto foi construído* (uma ferramenta de
desenvolvimento), não *o que o produto faz*. Ansible é automação/orquestração, sem relação com IA;
ele só executa de verdade as ações nos servidores. A pergunta "onde entra a IA" é sobre uma
funcionalidade do sistema em produção, e essa funcionalidade é o `ai_engine.py`.

**"As evidências (TXT/JSON/histórico) alimentam uma IA interna já existente?"** Não, nunca
alimentaram — isso era uma frase antiga do projeto original (CORTEX), corrigida no `README.md` e
nos comentários dos scripts. O propósito dessas evidências é exclusivamente **auditoria e eventual
investigação futura** (reconstruir o que foi feito, quando, por quem). A única coisa que lê esses
dados "como uma IA" é o `ai_engine.py` do próprio NEXUS, e mesmo assim só os dados que já estão no
banco (`nexus.db`), não os arquivos TXT/JSON do servidor remoto diretamente.

**"O Painel não tinha 'dashboards' de verdade — só números."** Os cartões numéricos e as tabelas já
existiam, mas faltavam gráficos visuais mesmo (a proposta original pedia isso explicitamente).
Foram adicionados 3 gráficos ao Painel, montados com HTML/CSS puro (sem biblioteca de gráficos
externa, mesmo padrão da barra de progresso que já existia na página do usuário):

- **Usuários por status** — barra empilhada horizontal (ativos/bloqueados/removidos).
- **Execuções por dia** (últimos 14 dias) — barras empilhadas por dia, sucesso vs. falha.
- **Execuções por servidor** (últimos 30 dias) — barras horizontais de magnitude.

Decisões de design (para não reintroduzir sem querer se alguém pedir "mais gráficos" depois):
- **Nenhum gráfico de pizza.** O pedido original mencionava "pizza, barras, linha do tempo", mas
  pizza é a forma errada para "distribuição de status" e é desencorajada para comparar valores
  próximos — usamos barra empilhada no lugar (mesma ideia de parte-do-todo, mais legível).
- **Cores de status são fixas e reservadas**: verde (`#0ca30c`) = bom/ativo/sucesso, âmbar
  (`#fab219`) = atenção/bloqueado, vermelho (`#d03b3b`) = crítico/falha, cinza (`#8a8a95`) =
  neutro/removido. Essas cores nunca devem ser reaproveitadas para outra coisa (ex.: não usar
  vermelho para "servidor X" num gráfico categórico — isso confundiria com "erro").
- **Execuções por servidor usa uma única cor** (roxo, `#8b5cf6`) porque é comparação de magnitude
  (volume), não identidade — colorir cada servidor diferente aqui seria ruído, não informação.
- Todas as cores foram validadas para contraste >=3:1 contra o fundo dos cards antes de ir para o
  código (ver `nexus_dashboard/config.py`, constantes `CHART_COLOR_*`).

## 11. Caso real: "Missing sudo password" e a opção NOPASSWD

Durante os testes, uma execução de `create` falhou só num servidor específico, com o erro do
Ansible:
```
fatal: [thierry]: FAILED! => {"changed": false, "msg": "Missing sudo password"}
```

**O que esse erro significa de fato:** é uma checagem do próprio Ansible, feita *antes* de tentar
autenticar — "eu preciso de uma senha de sudo pra essa tarefa e não tenho nenhuma configurada pra
esse host". Ele nem chega a testar se o usuário SSH tem permissão de sudo ou não. Por isso:

- Se a permissão de sudo estivesse faltando (mas a senha estivesse configurada), o erro seria
  outro (`"... is not in the sudoers file"`).
- Se o servidor tivesse `NOPASSWD` configurado no `sudoers`, esse erro **nunca apareceria** —
  NOPASSWD significa que o `sudo` nunca pede senha, então não haveria prompt nenhum pra faltar
  resposta. A presença desse erro é, na prática, prova de que **não** é NOPASSWD.

**A causa real, nesse caso**, foi simplesmente que a senha de sudo daquele servidor ainda não
tinha sido configurada na tela "senha sudo" no momento daquela execução. Depois de configurada, a
mesma linha de auditoria **continua marcada como `failed` pra sempre** — o histórico não se
reescreve; é preciso rodar a ação de novo pra gerar um registro novo e confirmar que passou a
funcionar.

**Limitação real que isso revelou:** o NEXUS, antes desse ajuste, *exigia* uma senha de sudo
configurada pra liberar qualquer ação em um servidor — mesmo que aquele servidor tivesse `sudo`
configurado com `NOPASSWD` (nunca pede senha) e a pessoa não soubesse nenhuma senha porque nunca
foi necessária. Foi adicionado um campo `sudo_nopasswd` na tabela `servers` (com migração segura
para bancos já existentes, feita em `models._migrate_schema()`).

**Detecção automática (e não só um campo manual).** A pedido explícito do dono do projeto — "o
projeto é pra facilitar a vida do analista, não pra ele checar servidor por servidor" — isso foi
além de um checkbox manual: ao cadastrar um servidor novo, o NEXUS testa sozinho, na hora, se
aquele servidor pede senha de sudo ou não, e já libera pra ações automaticamente quando não
precisar.

- **Como o teste é seguro** (`ansible/playbooks/detect_sudo.yml`): roda `sudo -n true` no
  servidor. A flag `-n` faz o `sudo` ser não-interativo por definição — se uma senha seria
  necessária, ele falha imediatamente com um erro, em vez de ficar esperando por um prompt que
  nunca seria respondido. Isso é o que garante que o teste nunca "trava".
- `rc == 0` → NOPASSWD confirmado, marca `sudo_nopasswd=1` automaticamente e libera ações.
- `rc != 0` → precisa mesmo de senha; avisa o analista pra configurar em "senha sudo".
- Falha de conexão (chave SSH ainda não autorizada, host inacessível) → resultado "unknown", pede
  pra configurar manualmente ou tentar detectar de novo depois.
- Um botão **"detectar"** na lista de Servidores permite repetir esse teste a qualquer momento
  (útil se a chave SSH não estava pronta no momento do cadastro, ou se o `sudoers` mudou depois).
- O checkbox manual "Este servidor não pede senha de sudo" continua existindo, mas só na tela de
  **editar** servidor (não mais no cadastro) — serve como ajuste manual pra quando a detecção
  automática não conseguir concluir.

---

## 12. Bug: "Missing sudo password" mesmo com a senha já configurada

Sintoma: servidor com "senha sudo" marcada como **configurada** na tela Servidores, teste de
conexão OK, mas uma ação real (`apply`) falha com `Task failed: Missing sudo password` na tarefa
que roda o `nexus_sanitize_users.sh` via `become: yes`.

**Causa raiz:** a senha de sudo de cada servidor é salva em
`ansible/host_vars/<servidor>/{vars.yml, vault.yml}` (ver seção "Onde cada coisa fica"). O Ansible
só carrega `host_vars/`/`group_vars/` **automaticamente** quando essa pasta fica ao lado do
arquivo de inventário (`ansible/inventory/`) ou ao lado do playbook (`ansible/playbooks/`) — não é
o caso aqui, `ansible/host_vars/` fica um nível acima de ambos. Resultado: o arquivo com a senha
existe (por isso a tela mostra "configurada", que só checa se o arquivo existe em disco), mas o
Ansible nunca o lê na hora de rodar a playbook, então `ansible_become_pass` nunca é definido e o
`become` falha por falta de senha.

**Correção:** os playbooks que usam `become: yes` (`sanitize_users.yml`,
`fetch_bash_history.yml`) agora recebem a extra-var `host_vars_root` e, como primeira tarefa,
carregam explicitamente `host_vars_root/<inventory_hostname>/` via `include_vars: {dir: ...}` —
guardado por uma checagem `stat` (`delegate_to: localhost`) pra não quebrar em servidores
NOPASSWD, que não têm essa pasta.

**Como confirmar que passou a funcionar:** rodar a ação de novo no mesmo servidor — assim como
outras falhas de auditoria, o registro antigo `failed` não se reescreve sozinho.

---

## 13. Exclusão de servidor com histórico — "soft delete" com motivo

Antes, um servidor com usuários ou execuções registradas simplesmente **não podia** ser excluído
(o botão nem aparecia) — a única saída era "desabilitar". Isso mudou: todo servidor agora tem
botão de excluir, mas o comportamento por trás depende de ter histórico ou não.

**Por que não dá pra simplesmente apagar a linha quando há histórico:** as tabelas
`managed_users`, `action_log` e `collected_facts` referenciam `servers.id` por chave estrangeira
(`PRAGMA foreign_keys = ON`). Um `DELETE FROM servers` com histórico ligado quebraria essa
referência (ou apagaria o rastro de auditoria, se as FKs não estivessem ativas) — exatamente o que
não se quer num sistema cujo propósito é auditoria.

**Como funciona agora:**

- **Sem histórico** (nenhum usuário/execução ligado): exclusão de verdade (`DELETE`), como antes —
  só pede confirmação simples.
- **Com histórico**: a exclusão pede o **motivo** (ex.: "descomissionamento de máquina", "servidor
  substituído") via prompt no navegador; o servidor não é apagado do banco — é marcado como
  **decomissionado** (`decommissioned_at`, `decommissioned_by`, `decommission_reason` na tabela
  `servers`, `enabled=0`), some da lista de Servidores e de qualquer seleção de destino de ação
  (`models.list_servers()` filtra por padrão), mas a linha continua existindo (preserva a FK). O
  motivo também é gravado como uma linha normal em `action_log` (ação
  `decommission_server`) — visível na tela **Execuções**, junto com quem fez e quando, do mesmo
  jeito que qualquer outra ação de auditoria.

## 14. Layout dos botões de ação (lista de Servidores)

Cada linha da tabela podia ter uma combinação diferente de botões (ex.: "senha sudo" some quando
o servidor é NOPASSWD), então o agrupamento simples (flexbox) fazia os botões desalinharem entre
linhas — e, numa tentativa seguinte de dar uma coluna de tabela por botão, a tabela ficou larga
demais e passou a exigir rolagem horizontal. A solução final usa **CSS Grid com colunas de largura
fixa** dentro de uma única célula "Ações": cada ação sempre cai na mesma posição horizontal em
todas as linhas (mesmo quando o botão daquela posição muda de texto, ex. "habilitar" x
"desabilitar", ou vira um placeholder "—"), sem abrir novas colunas na tabela.

---

## 15. Bug: "database is locked" ao recadastrar um servidor recém-excluído

Sintoma: excluir um servidor com histórico (ex.: "thierry") e, na sequência, cadastrar um novo
servidor com o **mesmo nome** derrubava a aplicação com `sqlite3.OperationalError: database is
locked`.

**Causa raiz, em duas partes:**

1. A coluna `servers.name` é `UNIQUE`. A exclusão de servidor com histórico (seção 13) não apaga
   a linha — ela continua ocupando esse nome. Cadastrar outro servidor com o mesmo nome batia
   direto nessa restrição e o `INSERT` falhava (`IntegrityError`).
2. `models.create_server()` não tinha `try/finally`: quando o `INSERT` falhava, a conexão SQLite
   ficava aberta (nunca chegava no `conn.close()`). Com o Flask em modo debug, o traceback
   interativo mantém aquele quadro de execução vivo na memória — inclusive a conexão travada -,
   então o banco ficava bloqueado até a aplicação ser reiniciada. Esse é um padrão perigoso que
   existia em praticamente toda função de escrita do `models.py`: qualquer erro no meio de um
   `INSERT`/`UPDATE` tinha o mesmo risco.

**Correção:**

- `decommission_server()` agora **arquiva o nome** do servidor excluído (sufixo com a data, ex.
  `thierry [excluído 2026-08-26T10:40:00-03:00]`) em vez de manter o nome original - libera o nome
  para um novo cadastro, e ainda deixa claro nas Execuções antigas que aquele registro é de um
  servidor que já foi decomissionado (evita confundir com um novo servidor que reuse o mesmo nome
  depois).
- Todas as funções de escrita em `models.py` passaram a usar `try/finally` para garantir
  `conn.close()` mesmo quando a operação falha.
- `get_db()` agora abre a conexão com `timeout=10` e `PRAGMA busy_timeout=10000` - o agendador
  (thread separada, roda todo dia às 03:00) e as requisições web podem gravar quase ao mesmo
  tempo; isso faz o SQLite aguardar até 10s por uma trava breve em vez de falhar na hora.

**Se a trava já tiver acontecido:** reiniciar o processo do Flask (`Ctrl+C` e `python app.py` de
novo) libera na hora - a trava é presa à conexão/processo, não ao arquivo em si.

**Pegadinha:** o arquivamento de nome (seção 13) só vale pra exclusões feitas **depois** dessa
correção estar rodando. Um servidor já decomissionado antes disso continua com o nome original
gravado, e recadastrar com o mesmo nome falha do mesmo jeito. `_archive_decommissioned_names()`
resolve isso retroativamente, uma vez, toda vez que a app sobe (`models.init_db()` →
`_migrate_schema()`): varre os servidores já decomissionados e arquiva o nome de quem ainda não
tinha sido arquivado.
