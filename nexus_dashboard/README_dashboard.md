# NEXUS Dashboard — Gestão de Usuários via Interface Gráfica

Este subprojeto substitui o fluxo por terminal/aliases (`nexus_remote.sh` + `servidores.conf` +
edição manual de `usuarios.csv`) por um **dashboard web** (Flask) que executa as mesmas operações
via **Ansible**, sem pedir senha por servidor a cada execução.

O projeto foi originalmente batizado de "CORTEX", nome que colidia com a IA interna da empresa —
por isso passou a se chamar **NEXUS**. Ele também chegou a incluir um scan de segurança
(`cortex_scan.sh` / `cortex_analyzer.py`), removido do repositório: o foco passou a ser
exclusivamente gestão de usuários, reaproveitando `nexus_sanitize_users.sh` sem alterações na
lógica.

## Passo a passo, do zero, na VM (máquina ponte)

O dashboard precisa de Linux — o Ansible não roda nativamente no Windows. Ele deve rodar na mesma
VM/ponte que já tem acesso SSH aos servidores gerenciados (`douglas`, `andressa`).

**1. Levar o projeto até a VM.** Use o mesmo caminho que você já usa hoje (pasta compartilhada do
VirtualBox), só que copiando a pasta toda em vez de arquivo por arquivo:

```bash
# dentro da VM, com a pasta do projeto montada em /media/sf_vm_pasta_compartilhada
cp -r /media/sf_vm_pasta_compartilhada/Projeto_estagio ~/nexus
cd ~/nexus/nexus_dashboard
```

Mantenha a estrutura de pastas intacta — `nexus_dashboard/` espera encontrar
`nexus_sanitize_users.sh` e `servidores.conf` um nível acima (`../`).

**2. Instalar dependências do sistema** (uma vez só, Ubuntu/Debian):

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip openssh-client
```

**3. Criar o ambiente Python e instalar as dependências do projeto:**

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Isso instala Flask, Ansible (`ansible-core` + `ansible-runner`) e o restante dentro do `.venv` —
nada é instalado no sistema.

**4. Confirmar que a chave SSH da ponte já está autorizada** nos servidores gerenciados (se ainda
não fez isso, é o mesmo passo do `README.md` original):

```bash
ssh-copy-id think@10.1.255.111        # douglas
ssh-copy-id andressa.silva@10.1.88.21 # andressa
```

**5. Rodar o dashboard** (com o `.venv` ativado):

```bash
python app.py
```

Isso cria o banco `db/nexus.db`, importa os servidores de `../servidores.conf` (uma única vez) e
sobe o site em `http://0.0.0.0:5000` — acessível tanto de dentro da VM quanto de outra máquina na
mesma rede.

**6. Abrir no navegador.** Descubra o IP da VM com `ip a` (procure algo como `192.168.x.x` ou
`10.x.x.x`) e acesse `http://IP-DA-VM:5000` do navegador do Windows. Se a VM só tiver rede NAT
(sem IP acessível do Windows), abra direto dentro da VM (se ela tiver interface gráfica) ou
configure port forwarding 5000→5000 nas configurações de rede do VirtualBox.

**7. Primeiros passos na interface**, na ordem:

1. **Identificar operador** — informe seu nome (sem senha; é só para o registro de auditoria).
2. **Configuração (Vault)** — informe a senha de `sudo` dos servidores uma única vez. Ela é
   gravada criptografada (Ansible Vault) e reutilizada automaticamente em toda execução seguinte.
3. **Servidores** — confira/edite a lista importada, ou cadastre novos. Use "testar conexão" para
   validar SSH + Vault sem digitar nada.
4. **Nova Ação** — substitui `nexus-users-dry` / `nexus-users-apply`: informe nome, chamado, ação
   (criar/bloquear/remover/purgar), grupos/shell/motivo quando fizer sentido, escolha o(s)
   servidor(es) e clique em **Simular** ou **Aplicar** — sem terminal.
5. **Usuários** — lista todos os usuários geridos pelo dashboard; cada um tem uma página de
   detalhe com o resumo da **IA NEXUS** (local, baseada em regras, sem envio de dados a serviços
   externos): status, dias bloqueado/restantes até a remoção automática, grupos, criação
   (quando/quem), documentos vinculados e comandos executados (best-effort, via
   `~/.bash_history`).

## Expiração automática de contas bloqueadas

Todo dia às 03:00 (horário do processo Flask), o NEXUS verifica os usuários bloqueados:

- a partir de **80 dias** de bloqueio, a conta aparece com aviso visual no painel;
- ao completar **90 dias**, a conta é **removida automaticamente** do servidor via Ansible, e a
  linha de auditoria fica marcada como "automático" (nunca confundida com uma remoção manual).

Isso pode ser adiantado manualmente a qualquer momento pelo botão "Forçar remoção agora" na página
do usuário.

## Onde cada coisa fica

| O que | Onde |
|---|---|
| Servidores geridos | tabela `servers` (substitui `servidores.conf`) |
| Usuários geridos e status | tabela `managed_users` |
| Auditoria/timeline de toda ação | tabela `action_log` |
| Documentos/chamados vinculados | tabela `documents` |
| Histórico de comandos coletado | tabela `collected_facts` |
| Playbooks Ansible | `ansible/playbooks/` |
| Senha de sudo (criptografada) | `ansible/group_vars/all/vault.yml` + `ansible/.vault_pass` |

## Segurança

- Nenhuma senha de servidor é solicitada fora da configuração única do Vault.
- A senha temporária de um novo usuário é digitada apenas no formulário web (HTTPS recomendado em
  produção) e nunca é enviada em texto puro ao servidor remoto — apenas o hash SHA-512.
- `ansible/.vault_pass` e `ansible/group_vars/all/vault.yml` nunca devem ser versionados (já estão
  no `.gitignore` do projeto).
- Proteja o acesso ao arquivo `db/nexus.db` — contém histórico de comandos e dados de auditoria.
