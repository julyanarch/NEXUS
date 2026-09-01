# NEXUS User Sanitizer

Manual do `nexus_sanitize_users.sh`, responsável pelo onboarding e offboarding
de usuários Linux a partir do arquivo `/opt/usuarios.csv`.

> **Nota:** hoje a operação do dia a dia acontece pelo **dashboard web**
> (`nexus_dashboard/`, veja [nexus_dashboard/README_dashboard.md](nexus_dashboard/README_dashboard.md)),
> que executa este mesmo script por trás via Ansible — sem precisar editar CSV manualmente nem
> usar os aliases descritos aqui. Este documento continua servindo como referência técnica do
> script em si (usado tanto no fluxo manual abaixo quanto internamente pelo Ansible) e como
> alternativa de operação manual em caso de emergência (ex.: dashboard fora do ar).

## O que ele faz

| Ação | Resultado |
| --- | --- |
| `create` ou `add` | Cria usuário, home opcional, shell, grupos e senha temporária |
| `lock` | Bloqueia a senha e expira a conta |
| `remove` ou `delete` | Remove o usuário, mantendo ou apagando a home |
| `purge` | Remove o usuário e apaga a home |

O script possui dois modos:

- `--dry-run`: simula as ações sem alterar usuários;
- `--apply`: executa as alterações reais.

## Arquivos e caminhos

```text
/opt/nexus_sanitize_users.sh
/opt/usuarios.csv
/var/log/nexus/nexus_sanitize_users_history.csv
```

O `usuarios.csv` representa a demanda atual. O histórico é preenchido
automaticamente e preserva o resultado de todas as execuções.

## Preparação

```bash
sudo chmod +x /opt/nexus_sanitize_users.sh
bash -n /opt/nexus_sanitize_users.sh
```

Aliases recomendados no `~/.bashrc`:

```bash
alias nexus-users-dry='sudo /opt/nexus_sanitize_users.sh --csv /opt/usuarios.csv --dry-run'
alias nexus-users-apply='sudo /opt/nexus_sanitize_users.sh --csv /opt/usuarios.csv --apply'
```

Ative os aliases:

```bash
source ~/.bashrc
```

## Formato do CSV

Use este cabeçalho:

```csv
username,action,home,reason,ticket,groups,shell
```

Significado dos campos:

| Campo | Exemplo | Descrição |
| --- | --- | --- |
| `username` | `rebeca` | Login Linux em letras minúsculas |
| `action` | `create` | Ação que será executada |
| `home` | `yes` | Em `create`, cria a home; em `remove`, apaga a home |
| `reason` | `admissao` | Motivo sem vírgulas |
| `ticket` | `CHG1001` | Identificador do chamado |
| `groups` | `sudo;docker` | Grupos opcionais separados por ponto e vírgula |
| `shell` | `/bin/bash` | Shell opcional; padrão `/bin/bash` |

Não coloque senha no CSV. Ela será solicitada de forma oculta no modo
`--apply`.

## Exemplo completo

```csv
username,action,home,reason,ticket,groups,shell
rebeca,create,yes,admissao,CHG1001,sudo,/bin/bash
carlos,create,yes,admissao,CHG1002,,/bin/bash
joao.silva,lock,no,afastamento,CHG1003,,
maria.souza,remove,no,desligamento,CHG1004,,
usuario_teste,purge,yes,fim do teste,CHG1005,,
```

Observações:

- `rebeca` será criada com home, Bash e grupo `sudo`;
- `carlos` será criado sem grupos adicionais;
- `joao.silva` será bloqueado;
- `maria.souza` será removida, mas a home será mantida;
- `usuario_teste` será removido junto com a home;
- os grupos informados precisam existir no servidor;
- não use vírgulas dentro de `reason`.

## Criar Rebeca: passo a passo

Edite o CSV:

```bash
sudo vim /opt/usuarios.csv
```

Conteúdo:

```csv
username,action,home,reason,ticket,groups,shell
rebeca,create,yes,admissao,CHG1001,sudo,/bin/bash
```

### 1. Simular

```bash
nexus-users-dry
```

Saída esperada, de forma resumida:

```text
[ALERTA] Modo DRY-RUN: nenhuma alteracao real sera executada.
[INFO] Criando usuario: rebeca
[INFO] DRY-RUN: useradd -m -s /bin/bash rebeca
[INFO] DRY-RUN: usermod -aG sudo rebeca
[OK] rebeca: usuario criado com grupos: sudo; senha temporaria seria solicitada no modo apply
```

O usuário ainda não existirá após o dry-run:

```bash
getent passwd rebeca
```

### 2. Aplicar

```bash
nexus-users-apply
```

O terminal solicitará:

```text
Senha temporaria para rebeca:
Confirme a senha temporaria:
```

Os caracteres não aparecem enquanto a senha é digitada. Isso é esperado.

Resultado esperado:

```text
[OK] rebeca: usuario criado com grupos: sudo; senha temporaria definida e troca obrigatoria ativada
```

### 3. Validar a conta

```bash
getent passwd rebeca
id rebeca
sudo ls -ld /home/rebeca
sudo chage -l rebeca
```

O `chage -l` deve indicar que a senha precisa ser alterada.

### 4. Primeiro login

Em outra sessão:

```bash
ssh rebeca@IP_DO_SERVIDOR
```

O usuário informa a senha temporária. O sistema pede a senha atual e depois a
nova senha. Esse fluxo depende de o SSH do servidor permitir autenticação por
senha e usar PAM.

## Bloquear usuário

CSV:

```csv
username,action,home,reason,ticket,groups,shell
joao.silva,lock,no,afastamento,CHG2001,,
```

Execute:

```bash
nexus-users-dry
nexus-users-apply
```

Valide:

```bash
sudo passwd -S joao.silva
sudo chage -l joao.silva
```

## Remover mantendo a home

```csv
username,action,home,reason,ticket,groups,shell
maria.souza,remove,no,desligamento,CHG3001,,
```

Após aplicar, a conta é removida, mas `/home/maria.souza` permanece.

## Remover apagando a home

Estas duas formas apagam a conta e a home:

```csv
username,action,home,reason,ticket,groups,shell
maria.souza,remove,yes,desligamento,CHG3002,,
usuario_teste,purge,yes,fim do teste,CHG3003,,
```

Sempre revise o dry-run antes, pois a exclusão da home é destrutiva.

## Senha temporária

No modo `--apply`, o script:

1. lê a senha diretamente de `/dev/tty` com a exibição desativada;
2. solicita confirmação;
3. rejeita senha vazia, diferente da confirmação ou contendo `:`;
4. aplica a senha por `chpasswd` sem colocá-la nos argumentos do processo;
5. executa `chage -d 0` para exigir a troca no primeiro login;
6. limpa a variável usada durante a operação.

A senha não é incluída em:

- `/opt/usuarios.csv`;
- relatório TXT;
- relatório JSON;
- histórico CSV.

Cada linha `create` pede sua própria senha. Se houver três novos usuários no
CSV, serão solicitadas três senhas temporárias.

## Relatórios e histórico

Cada execução gera:

```text
/var/log/nexus/nexus_sanitize_users_HOST_DATA.txt
/var/log/nexus/nexus_sanitize_users_HOST_DATA.json
/var/log/nexus/nexus_sanitize_users_history.csv
```

Para usar outro histórico:

```bash
sudo /opt/nexus_sanitize_users.sh --csv /opt/usuarios.csv --apply --history /var/log/nexus/users_history.csv
```

Para desativar o histórico em uma execução:

```bash
sudo /opt/nexus_sanitize_users.sh --csv /opt/usuarios.csv --dry-run --no-history
```

## Proteções

O script:

- exige `sudo` no modo `--apply`;
- ignora cabeçalho e linhas iniciadas com `#`;
- valida username, grupos e shell;
- impede alterações em contas protegidas, como `root`, `daemon` e `sshd`;
- não remove usuários inexistentes;
- não recria um usuário que já existe;
- usa `--dry-run` como modo padrão seguro.

## Problemas comuns

### Grupo inexistente

Mensagem:

```text
grupos inexistentes: sudo
```

Confira os grupos disponíveis:

```bash
getent group sudo
getent group wheel
```

Use o grupo administrativo existente na distribuição.

### O alias não foi encontrado

```bash
source ~/.bashrc
alias nexus-users-apply
```

Confira se o alias aponta para `/opt`, e não para `~` ou `/op`.

### A troca de senha não aparece no SSH

Confirme o estado:

```bash
sudo chage -l rebeca
sudo passwd -S rebeca
```

Depois verifique se o servidor permite login por senha e autenticação PAM. Não
altere a configuração SSH sem manter outra sessão administrativa aberta.

## Servidores remotos

O controlador `/opt/nexus_remote.sh` automatiza envio temporário, execução,
coleta dos relatórios e limpeza.

Servidor configurado:

```text
# name,user,host,port,enabled
teste-01,think,10.1.255.111,22,yes
```

Novos servidores são adicionados no arquivo `/opt/servidores.conf` da máquina
ponte, uma linha por servidor:

```bash
sudo vim /opt/servidores.conf
```

```text
# name,user,host,port,enabled
teste-01,think,10.1.255.111,22,yes
teste-02,think,10.1.255.112,22,yes
producao-01,admin,10.1.255.120,22,no
```

`yes` habilita o servidor nas operações com `all`; `no` mantém o cadastro
desativado. Depois de salvar, confirme com `nexus-servers`.

Simulação remota:

```bash
nexus-remote-users-dry teste-01
```

Aplicação remota:

```bash
nexus-remote-users-apply teste-01
```

Para cada usuário novo, a senha temporária será solicitada no terminal da
máquina ponte antes da execução remota. Os caracteres digitados não aparecem.
O controlador gera um hash SHA-512 em memória e envia somente esse hash para um
arquivo protegido na pasta temporária remota. O arquivo é removido ao final e
não é incluído nos relatórios ou históricos.

Para aplicar em todos os servidores habilitados:

```bash
nexus-remote-users-apply all
```

Esse comando exige a confirmação `APLICAR`. Os arquivos temporários são
removidos do servidor ao final, enquanto os relatórios permanecem no servidor
remoto e também são coletados para:

```text
/var/log/nexus/remotos/teste-01/
```

As contas locais continuam independentes: a troca feita pelo usuário em um
servidor não atualiza os outros. Sincronização real de senha exige Active
Directory, LDAP ou FreeIPA.
