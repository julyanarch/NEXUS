# NEXUS — Gestão de Usuários

O NEXUS automatiza o onboarding/offboarding de usuários Linux em múltiplos servidores,
substituindo um protótipo anterior baseado em terminal + aliases + edição manual de CSV — que, por
sua vez, já tinha substituído um processo ainda mais antigo, 100% manual (login e senha em cada
servidor, comandos padrão do Linux digitados um a um). Toda ação (criar, bloquear, remover, purgar)
fica registrada para fins de **auditoria** — quem fez o quê, quando, e com qual chamado.

> A linha do tempo completa (processo manual original → protótipo com scripts e CSV → NEXUS) está
> detalhada em [docs/DOCUMENTACAO_PROJETO_ESTAGIO_IA.md](docs/DOCUMENTACAO_PROJETO_ESTAGIO_IA.md),
> seção 2.3.

O projeto se chamava **"CORTEX"** originalmente; o nome colidia com a IA interna da empresa, e
como o projeto ganhou sua própria IA e identidade, foi renomeado para **NEXUS** ("ligação/elo" em
latim) — o ponto central que conecta a gestão de todos os servidores num só lugar.

## Como o projeto é operado hoje

Existem duas camadas, mas **apenas uma é usada no dia a dia**:

| Camada | O que é | Uso hoje |
| --- | --- | --- |
| **Dashboard web** (`nexus_dashboard/`) | Flask + Ansible + IA local, com interface gráfica | ✅ Forma atual de operar — sem terminal, sem editar CSV |
| Script + aliases por terminal (`nexus_sanitize_users.sh`, `nexus_remote.sh`, `servidores.conf`) | Protótipo por linha de comando, anterior ao dashboard (não é o processo original — ver nota acima) | Mantido como referência/emergência — a lógica de baixo nível (`nexus_sanitize_users.sh`) é a mesma que o Ansible executa por trás do dashboard |

Ou seja: o dashboard não é um projeto separado — é a evolução desse protótipo por linha de comando,
com a mesma base testada de script, só que orquestrada por Ansible e exposta numa interface web,
sem pedir senha por servidor a cada execução. E esse próprio protótipo já tinha sido, no seu
tempo, uma evolução sobre o processo 100% manual que existia antes dele (ver seção 2.3 do link
acima).

**Para rodar e apresentar o projeto, use o dashboard:** manual completo em
[nexus_dashboard/README_dashboard.md](nexus_dashboard/README_dashboard.md).

**Para consultar a lógica interna do script reaproveitado pelo Ansible** (ou operar manualmente em
caso de emergência): [README_sanitize_users.md](README_sanitize_users.md).

**Para dúvidas técnicas de arquitetura, decisões de design e bugs já resolvidos** (útil para
apresentações e perguntas do tipo "por que foi feito assim"):
[docs/DOCUMENTACAO_TECNICA.md](docs/DOCUMENTACAO_TECNICA.md).

## Onde entra a IA integrada

A proposta do projeto inclui uma IA própria, embutida no dashboard: um motor de regras local
(`nexus_dashboard/ai_engine.py`) que roda **dentro da aplicação em produção**. Para cada usuário
gerido, ele lê os dados já coletados (status, grupos/permissões, tempo bloqueado, criação,
histórico de comandos) e gera, em tempo real, um resumo em português + fatos estruturados — exibido
na página de detalhe do usuário, no painel "IA NEXUS". Não depende de nenhuma API externa: nenhum
dado de usuário/servidor sai da máquina.

O Ansible é uma camada separada, de automação/orquestração — não tem relação com a parte de IA.
Ele só executa de verdade, nos servidores, as ações que a interface manda (criar/bloquear/remover
usuário).

## Arquitetura resumida

```
Navegador (Windows) ── HTTP ──> Flask (VM ponte) ── Ansible ──> servidores gerenciados
                                     │
                                     └── SQLite (nexus.db): servidores, usuários geridos,
                                         auditoria/timeline, histórico coletado
```

- **Backend**: Flask (Python), server-side com Jinja2.
- **Persistência**: SQLite local (`nexus_dashboard/db/nexus.db`).
- **Automação remota**: Ansible (via `ansible-runner`), reaproveitando `nexus_sanitize_users.sh`
  sem reescrever a lógica testada — o Ansible só copia e executa esse script no servidor de
  destino.
- **IA**: motor de regras local (`ai_engine.py`), sem API externa.
- **Autenticação em duas camadas** (servidor gerenciado): chave SSH resolve o login
  (`ssh-copy-id`); senha de sudo (Ansible Vault, uma por servidor) resolve o privilégio de root —
  uma coisa não substitui a outra. Detalhe completo na seção 2 de
  [docs/DOCUMENTACAO_TECNICA.md](docs/DOCUMENTACAO_TECNICA.md).

## Fluxo de trabalho: PC pessoal → GitHub → VM ponte

O código é escrito no **PC pessoal** (VS Code) e o dashboard roda numa **VM da empresa** usada como
ambiente de teste (máquina ponte, ex.: `asc-bd-lab-01`) — são máquinas separadas, sem pasta
compartilhada. A ligação entre elas é feita por um **repositório privado no GitHub**
(`https://github.com/julyanarch/NEXUS`):

```
PC pessoal (git push)  →  GitHub (repo privado)  →  VM ponte (git pull)
```

**No PC pessoal**, depois de qualquer mudança:

```bash
git add .
git commit -m "..."
git push
```

> Existe um script auxiliar (`scripts/auto_commit.ps1`) que monitora a pasta e faz commit+push
> automaticamente a cada intervalo, para quem prefere não commitar manualmente durante o
> desenvolvimento.

**Na VM ponte**, dentro da pasta já clonada (`~/nexus`), para trazer a atualização:

```bash
cd ~/nexus
git pull
```

Autenticação no GitHub (repo privado): token de acesso pessoal ou chave SSH configurada na VM.

**Rodando o dashboard na VM ponte** (ambiente real de testes, usuário `root`, exemplo do host
`asc-bd-lab-01`):

```bash
cd ~/nexus/nexus_dashboard
source .venv/bin/activate     # ativa o ambiente virtual Python já criado
python app.py
```

O prompt fica assim quando está tudo certo:

```
(.venv) root@asc-bd-lab-01:~/nexus/nexus_dashboard#
```

Passo a passo completo (primeira vez, dependências, IP de acesso, uso da interface):
[nexus_dashboard/README_dashboard.md](nexus_dashboard/README_dashboard.md).

## Componentes

| Arquivo/pasta | Função |
| --- | --- |
| `nexus_dashboard/` | Dashboard web (Flask + Ansible + IA) — forma atual de operar |
| `nexus_sanitize_users.sh` | Cria, bloqueia ou remove usuários; reaproveitado pelo Ansible e disponível para uso manual via CSV |
| `nexus_remote.sh` + `servidores.conf` | Controlador remoto por terminal/aliases (protótipo anterior ao dashboard, não o processo original — ver [README_sanitize_users.md](README_sanitize_users.md)) |
| `scripts/auto_commit.ps1` | Auxiliar opcional no PC pessoal: commit+push automático das mudanças |
| `docs/DOCUMENTACAO_TECNICA.md` | Documentação técnica viva: decisões de arquitetura, bugs resolvidos, perguntas frequentes |

## Relatórios e evidências (auditoria)

Cada ação (criar, bloquear, remover, purgar) deixa rastro em dois lugares, só para fins de
auditoria/investigação futura — nenhum dos dois alimenta uma IA externa:

**1. No próprio servidor gerido** (gravado pelo `nexus_sanitize_users.sh`):

```
/var/log/nexus/nexus_sanitize_users_HOST_DATA.txt      # relatório legível da execução
/var/log/nexus/nexus_sanitize_users_HOST_DATA.json     # mesmo relatório, em JSON
/var/log/nexus/nexus_sanitize_users_history.csv        # histórico acumulado nesse servidor
```

**2. Na VM ponte, quando a execução é feita pelo dashboard:**

```
nexus_dashboard/db/nexus.db                  # tabela action_log = auditoria completa
nexus_dashboard/ansible/artifacts/<run_id>/  # saída bruta de cada execução do Ansible
```

A tabela `action_log` é a fonte mais completa: junta o que aconteceu em todos os servidores num só
lugar, com quem executou, se foi manual ou automático (expiração de 90 dias), e o resultado. Ela
alimenta as telas de **Usuários** e **Execuções** do dashboard, além do resumo da IA local.

## Segurança

- Nunca coloque senha real no `usuarios.csv` nem em nenhum arquivo versionado.
- O script não registra a senha temporária nos relatórios ou no histórico — só o hash SHA-512
  trafega, e nem esse fica gravado.
- Cada servidor tem sua própria senha de sudo (Ansible Vault) — nunca compartilhada entre
  servidores.
- `ansible/.vault_pass`, `ansible/host_vars/` e qualquer `.db`/`.csv` real nunca são versionados
  (já cobertos pelo `.gitignore` do projeto).
- O script impede alterações em contas protegidas, como `root`, `daemon` e `sshd`.
- Sempre valide com "Simular"/`--dry-run` antes de aplicar uma ação real.

## Requisitos

- Linux e Bash na VM ponte (o Ansible não roda nativamente no Windows);
- Python 3 + `venv` na VM ponte, para o dashboard;
- acesso `sudo` nos servidores gerenciados;
- `openssl` na VM ponte, para gerar hashes das senhas temporárias;
- SSH (chave configurada via `ssh-copy-id`) entre a VM ponte e os servidores gerenciados.

## Limitação de senhas locais

Cada servidor mantém seu próprio `/etc/shadow`. A senha temporária pode ser aplicada em vários
servidores, mas uma troca feita em um servidor não altera automaticamente os demais. Para uma senha
única e centralizada, o ambiente precisaria de Active Directory, LDAP ou FreeIPA — fora do escopo
atual do projeto.
