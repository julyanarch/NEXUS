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
