# NEXUS — Gestão de Usuários

Conjunto de scripts para gestão de usuários (onboarding/offboarding) em servidores
Linux. Os scripts geram evidências em TXT, JSON e CSV para auditoria e para
consumo pela IA interna NEXUS.

> Existe também um dashboard web (`nexus_dashboard/`) que executa este mesmo
> fluxo via Ansible, com interface gráfica em vez de terminal/aliases e sem
> pedir senha por servidor. Veja [nexus_dashboard/README_dashboard.md](nexus_dashboard/README_dashboard.md).
> Este README documenta o fluxo original por terminal, que continua funcionando.

## Componentes

| Arquivo | Função |
| --- | --- |
| `nexus_sanitize_users.sh` | Cria, bloqueia ou remove usuários usando um CSV |
| `usuarios.csv` | Define as ações de onboarding e offboarding |
| `nexus_remote.sh` | Controla a execução do script nos servidores via SSH |
| `servidores.conf` | Lista os servidores administrados pela máquina ponte |
| `nexus_dashboard/` | Dashboard web (Flask + Ansible) para o mesmo fluxo, via interface gráfica |

## Ambiente de teste

Na máquina ponte, os arquivos ficam em:

```text
/opt/nexus_sanitize_users.sh
/opt/usuarios.csv
/opt/nexus_remote.sh
/opt/servidores.conf
```

Prepare as permissões:

```bash
sudo chmod +x /opt/nexus_sanitize_users.sh
```

Valide a sintaxe:

```bash
bash -n /opt/nexus_sanitize_users.sh
```

Se o comando não mostrar erros, a sintaxe está válida.

## Aliases

Adicione ao `~/.bashrc` do usuário que administrará a máquina ponte:

```bash
alias nexus-logs='sudo ls -lah /var/log/nexus'
alias nexus-users-dry='sudo /opt/nexus_sanitize_users.sh --csv /opt/usuarios.csv --dry-run'
alias nexus-users-apply='sudo /opt/nexus_sanitize_users.sh --csv /opt/usuarios.csv --apply'
alias nexus-servers='/opt/nexus_remote.sh list'
alias nexus-remote-test='/opt/nexus_remote.sh test'
alias nexus-remote-logs='/opt/nexus_remote.sh logs'
alias nexus-remote-users-dry='/opt/nexus_remote.sh users-dry'
alias nexus-remote-users-apply='/opt/nexus_remote.sh users-apply'
```

Recarregue e confira:

```bash
source ~/.bashrc
alias | grep nexus
```

## Fluxo de usuários

O sanitizer suporta:

- `create` ou `add`: cria a conta, define grupos e solicita senha temporária;
- `lock`: bloqueia e expira a conta;
- `remove` ou `delete`: remove a conta, com opção de apagar a home;
- `purge`: remove a conta e a home.

Exemplo de `/opt/usuarios.csv`:

```csv
username,action,home,reason,ticket,groups,shell
rebeca,create,yes,admissao,CHG1001,sudo,/bin/bash
joao.silva,lock,no,afastamento,CHG1002,,
maria.souza,remove,yes,desligamento,CHG1003,,
```

Primeiro simule:

```bash
nexus-users-dry
```

Depois aplique:

```bash
nexus-users-apply
```

Para cada linha `create`, o script solicita uma senha temporária e uma
confirmação sem mostrar os caracteres digitados. Na execução remota, essa
solicitação acontece na própria ponte; somente o hash SHA-512 segue pelo SSH.
A senha não é gravada no CSV, TXT, JSON ou histórico. A conta é marcada para
trocar a senha no primeiro login.

Manual completo: [README_sanitize_users.md](README_sanitize_users.md)

## Relatórios

Os scripts gravam os resultados em:

```text
/var/log/nexus/
```

Principais arquivos:

```text
nexus_sanitize_users_HOST_DATA.txt
nexus_sanitize_users_HOST_DATA.json
nexus_sanitize_users_history.csv
```

## Segurança

- Sempre execute o sanitizer primeiro com `--dry-run`.
- Nunca coloque senhas no `usuarios.csv`.
- O script não registra a senha temporária nos relatórios ou no histórico.
- Proteja `/var/log/nexus` e revise os relatórios antes de compartilhá-los.
- Não envie CSVs reais de colaboradores para repositórios Git.
- O script impede alterações em contas protegidas, como `root`, `daemon` e
  `sshd`.

## Máquina ponte e servidores remotos

O `nexus_remote.sh` permite executar o script da ponte em um ou vários
servidores. Ele envia os arquivos para uma pasta protegida em `/tmp`, executa,
coleta os relatórios para a ponte e remove os arquivos temporários.

Instale os arquivos novos na ponte:

```bash
sudo cp nexus_remote.sh servidores.conf /opt/
sudo chmod 755 /opt/nexus_remote.sh
sudo chmod 644 /opt/servidores.conf
bash -n /opt/nexus_remote.sh
```

Servidor inicial em `/opt/servidores.conf`:

```text
# name,user,host,port,enabled
teste-01,think,10.1.255.111,22,yes
```

Para cadastrar novos servidores, edite esse mesmo arquivo na máquina ponte:

```bash
sudo vim /opt/servidores.conf
```

Acrescente uma linha para cada servidor, sem apagar os anteriores:

```text
# name,user,host,port,enabled
teste-01,think,10.1.255.111,22,yes
teste-02,think,10.1.255.112,22,yes
producao-01,admin,10.1.255.120,22,yes
```

Os campos são `nome`, `usuário SSH`, `IP ou hostname`, `porta SSH` e
`habilitado`. Use `yes` para incluir a máquina nas execuções com `all` e `no`
para mantê-la cadastrada, mas desativada. Não é necessário alterar o
`nexus_remote.sh` ao adicionar servidores.

Confira o inventário depois de salvar:

```bash
nexus-servers
```

### Acesso SSH sem pedidos repetidos

O controlador reaproveita temporariamente as conexões SSH, mas o recomendado é
configurar uma chave na máquina ponte. Para o servidor de teste:

```bash
ssh-keygen -t ed25519
ssh-copy-id think@10.1.255.111
ssh think@10.1.255.111 'hostname && whoami'
```

O último comando deve conectar sem pedir a senha do usuário `think`. A senha do
`sudo` remoto ainda poderá ser solicitada quando uma operação privilegiada for
executada. O dashboard web (`nexus_dashboard/`) elimina até esse pedido de
senha de `sudo`, usando Ansible Vault.

Comandos principais:

```bash
nexus-servers
nexus-remote-test teste-01
nexus-remote-logs teste-01
nexus-remote-users-dry teste-01
nexus-remote-users-apply teste-01
```

Use `all` para todos os servidores habilitados:

```bash
nexus-remote-users-dry all
nexus-remote-users-apply all
```

O apply em todos exige digitar `APLICAR` como confirmação. Execute o controlador
como usuário normal, sem `sudo`, para que ele encontre sua chave SSH. Ele pede
`sudo` apenas quando precisa criar a pasta local de relatórios. Os resultados
ficam separados por nome:

```text
/var/log/nexus/remotos/teste-01/
```

## Requisitos

- Linux e Bash;
- acesso `sudo` para gestão de usuários;
- comandos como `getent`, `useradd`, `usermod`, `userdel`, `chpasswd` e `chage`;
- `openssl` na máquina ponte para gerar hashes das senhas temporárias;
- SSH para a execução remota.

## Limitação de senhas locais

Cada servidor mantém seu próprio `/etc/shadow`. A senha temporária pode ser
aplicada em vários servidores pelo controlador, mas uma troca realizada
em um servidor não altera automaticamente os demais. Para uma senha única e
centralizada, o ambiente precisará usar Active Directory, LDAP ou FreeIPA.
