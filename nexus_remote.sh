#!/usr/bin/env bash
set -Eeuo pipefail

# NEXUS bridge controller. Scripts remain on the bridge and are copied only
# to a protected temporary directory while each remote operation is running.

BASE_DIR="${NEXUS_BASE_DIR:-/opt}"
SERVERS_FILE="${NEXUS_SERVERS_FILE:-${BASE_DIR}/servidores.conf}"
SANITIZER_SCRIPT="${BASE_DIR}/nexus_sanitize_users.sh"
USERS_CSV="${BASE_DIR}/usuarios.csv"
REPORT_ROOT="${NEXUS_REPORT_ROOT:-/var/log/nexus/remotos}"
PASSWORD_HASH_PAYLOAD=""

declare -A PASSWORD_HASH_CACHE=()

SSH_OPTIONS=(
  -o ConnectTimeout=10
  -o ServerAliveInterval=15
  -o ServerAliveCountMax=2
  -o ControlMaster=auto
  -o ControlPersist=120
  -o ControlPath=/tmp/nexus-ssh-%C
)

RED="\e[31m"
GREEN="\e[32m"
YELLOW="\e[33m"
BLUE="\e[34m"
BOLD="\e[1m"
RESET="\e[0m"

ok()    { echo -e "${GREEN}[OK]${RESET} $*"; }
warn()  { echo -e "${YELLOW}[ALERTA]${RESET} $*" >&2; }
crit()  { echo -e "${RED}[ERRO]${RESET} $*" >&2; }
info()  { echo -e "${BLUE}[INFO]${RESET} $*"; }

usage() {
  cat <<'EOF'
Uso:
  nexus_remote.sh list
  nexus_remote.sh test [alvo|all]
  nexus_remote.sh logs [alvo|all]
  nexus_remote.sh users-dry [alvo|all]
  nexus_remote.sh users-apply <alvo|all>

Alvo pode ser o nome ou IP definido em /opt/servidores.conf.
Comandos sem alvo usam todos os servidores habilitados, exceto users-apply.

Exemplos:
  nexus_remote.sh test teste-01
  nexus_remote.sh users-dry teste-01
  nexus_remote.sh users-apply teste-01
  nexus_remote.sh users-dry all
EOF
}

trim() {
  local value="$1"
  value="${value#"${value%%[![:space:]]*}"}"
  value="${value%"${value##*[![:space:]]}"}"
  value="${value%$'\r'}"
  printf '%s' "$value"
}

require_file() {
  local path="$1"
  local description="$2"
  if [[ ! -r "$path" ]]; then
    crit "$description nao encontrado ou sem leitura: $path"
    return 1
  fi
}

ensure_report_dir() {
  local target_dir="$1"

  if mkdir -p "$target_dir" 2>/dev/null && [[ -w "$target_dir" ]]; then
    return 0
  fi

  if ! command -v sudo >/dev/null 2>&1; then
    crit "Sem permissao para criar $target_dir e sudo nao esta disponivel."
    return 1
  fi

  sudo mkdir -p "$target_dir"
  sudo chown "$(id -u):$(id -g)" "$REPORT_ROOT" "$target_dir"
}

ssh_run() {
  local user="$1" host="$2" port="$3"
  shift 3
  ssh "${SSH_OPTIONS[@]}" -p "$port" "${user}@${host}" "$@"
}

ssh_tty() {
  local user="$1" host="$2" port="$3"
  shift 3
  # Interactive password prompts need an independent TTY. Reusing a multiplexed
  # session can leave local echo enabled even when the remote script disables it.
  ssh -tt "${SSH_OPTIONS[@]}" -o ControlMaster=no -o ControlPath=none \
    -p "$port" "${user}@${host}" "$@"
}

scp_to() {
  local user="$1" host="$2" port="$3" source="$4" destination="$5"
  scp "${SSH_OPTIONS[@]}" -P "$port" "$source" "${user}@${host}:${destination}"
}

scp_from() {
  local user="$1" host="$2" port="$3" source="$4" destination="$5"
  scp "${SSH_OPTIONS[@]}" -P "$port" "${user}@${host}:${source}" "$destination"
}

create_remote_temp() {
  local user="$1" host="$2" port="$3"
  ssh_run "$user" "$host" "$port" 'umask 077; mktemp -d /tmp/nexus-run.XXXXXX'
}

cleanup_remote_temp() {
  local user="$1" host="$2" port="$3" remote_dir="$4"

  if [[ "$remote_dir" != /tmp/nexus-run.* ]]; then
    warn "Limpeza ignorada por caminho temporario invalido: $remote_dir"
    return 1
  fi

  ssh_run "$user" "$host" "$port" "find '$remote_dir' -maxdepth 1 -type f -delete; rmdir '$remote_dir'" >/dev/null
}

valid_server_entry() {
  local name="$1" user="$2" host="$3" port="$4"

  [[ "$name" =~ ^[a-zA-Z0-9_.-]+$ ]] || { crit "Nome de servidor invalido: $name"; return 1; }
  [[ "$user" =~ ^[a-z_][a-z0-9_.-]*$ ]] || { crit "Usuario SSH invalido em $name: $user"; return 1; }
  [[ "$host" =~ ^[a-zA-Z0-9.-]+$ ]] || { crit "Host invalido em $name: $host"; return 1; }
  [[ "$port" =~ ^[0-9]+$ ]] || { crit "Porta SSH invalida em $name: $port"; return 1; }
  (( port >= 1 && port <= 65535 )) || { crit "Porta SSH fora do intervalo em $name: $port"; return 1; }
}

prepare_password_hash_payload() {
  local username action home reason ticket groups shell extra
  local password="" confirmation="" password_hash=""

  PASSWORD_HASH_PAYLOAD=""
  command -v openssl >/dev/null 2>&1 || {
    crit "openssl nao esta instalado na maquina ponte."
    return 1
  }

  while IFS=',' read -r username action home reason ticket groups shell extra || [[ -n "${username:-}" ]]; do
    username="$(trim "${username:-}")"
    action="$(trim "${action:-}")"
    action="${action,,}"

    [[ -z "$username" || "$username" == \#* || "$username" == "username" ]] && continue
    [[ "$action" != "create" && "$action" != "add" ]] && continue

    if [[ -z "${PASSWORD_HASH_CACHE[$username]:-}" ]]; then
      while true; do
        IFS= read -r -s -p "Senha temporaria para ${username}: " password < /dev/tty
        printf '\n' > /dev/tty
        IFS= read -r -s -p "Confirme a senha temporaria: " confirmation < /dev/tty
        printf '\n' > /dev/tty

        if [[ -z "$password" ]]; then
          warn "A senha nao pode ficar vazia."
        elif [[ "$password" != "$confirmation" ]]; then
          warn "As senhas nao conferem. Tente novamente."
        else
          password_hash="$(printf '%s' "$password" | openssl passwd -6 -stdin)"
          PASSWORD_HASH_CACHE[$username]="$password_hash"
          password=""
          confirmation=""
          password_hash=""
          break
        fi

        password=""
        confirmation=""
      done
    fi

    PASSWORD_HASH_PAYLOAD+="${username}:${PASSWORD_HASH_CACHE[$username]}"$'\n'
  done < "$USERS_CSV"
}

action_test() {
  local name="$1" user="$2" host="$3" port="$4"
  local result

  info "Testando ${name} (${user}@${host}:${port})"
  result="$(ssh_run "$user" "$host" "$port" 'printf "host=%s user=%s\n" "$(hostname -s 2>/dev/null || hostname)" "$(id -un)"')"
  printf '%s\n' "$result"
  ok "Conexao SSH funcionando em $name"
}

action_logs() {
  local name="$1" user="$2" host="$3" port="$4"
  info "Logs remotos de $name (${host})"
  ssh_tty "$user" "$host" "$port" 'sudo ls -lah /var/log/nexus'
}

action_users() {
  local mode="$1" name="$2" user="$3" host="$4" port="$5"
  local remote_dir="" remote_command password_option="" target_dir stamp json_file txt_file history_file status=0 remote_status=0

  require_file "$SANITIZER_SCRIPT" "Script sanitizer" || return 1
  require_file "$USERS_CSV" "CSV de usuarios" || return 1
  target_dir="${REPORT_ROOT}/${name}"
  ensure_report_dir "$target_dir" || return 1
  if [[ "$mode" == "apply" ]]; then
    prepare_password_hash_payload || return 1
  fi
  stamp="$(date +'%Y%m%d_%H%M%S')"
  json_file="${target_dir}/nexus_sanitize_users_${name}_${stamp}.json"
  txt_file="${target_dir}/nexus_sanitize_users_${name}_${stamp}.txt"
  history_file="${target_dir}/nexus_sanitize_users_history.csv"

  info "Executando sanitizer ${mode} em $name (${host})"
  remote_dir="$(create_remote_temp "$user" "$host" "$port")" || return 1
  remote_dir="$(trim "$remote_dir")"

  if ! scp_to "$user" "$host" "$port" "$SANITIZER_SCRIPT" "${remote_dir}/nexus_sanitize_users.sh" ||
     ! scp_to "$user" "$host" "$port" "$USERS_CSV" "${remote_dir}/usuarios.csv"; then
    cleanup_remote_temp "$user" "$host" "$port" "$remote_dir" || true
    return 1
  fi

  if [[ "$mode" == "apply" && -n "$PASSWORD_HASH_PAYLOAD" ]]; then
    if ! printf '%s' "$PASSWORD_HASH_PAYLOAD" | ssh_run "$user" "$host" "$port" "umask 077; cat > '${remote_dir}/password_hashes'"; then
      cleanup_remote_temp "$user" "$host" "$port" "$remote_dir" || true
      return 1
    fi
    password_option=" --password-hashes '${remote_dir}/password_hashes'"
  fi

  remote_command="chmod 700 '${remote_dir}/nexus_sanitize_users.sh'; chmod 600 '${remote_dir}/usuarios.csv'; sudo '${remote_dir}/nexus_sanitize_users.sh' --csv '${remote_dir}/usuarios.csv' --${mode}${password_option}; run_status=\$?; uid=\$(id -u); gid=\$(id -g); sudo bash -c 'set -e; dest=\"\$1\"; uid=\"\$2\"; gid=\"\$3\"; json=\$(ls -1t /var/log/nexus/nexus_sanitize_users_*.json 2>/dev/null | head -n 1); txt=\$(ls -1t /var/log/nexus/nexus_sanitize_users_*.txt 2>/dev/null | head -n 1); history=/var/log/nexus/nexus_sanitize_users_history.csv; test -n \"\$json\"; cp -- \"\$json\" \"\$dest/users.result.json\"; if test -n \"\$txt\"; then cp -- \"\$txt\" \"\$dest/users.result.txt\"; fi; if test -f \"\$history\"; then cp -- \"\$history\" \"\$dest/users.history.csv\"; fi; chown \"\$uid:\$gid\" \"\$dest\"/users.result.*; if test -f \"\$dest/users.history.csv\"; then chown \"\$uid:\$gid\" \"\$dest/users.history.csv\"; fi' _ '${remote_dir}' \"\$uid\" \"\$gid\"; stage_status=\$?; if test \"\$stage_status\" -ne 0; then exit \"\$stage_status\"; fi; exit \"\$run_status\""
  if ssh_tty "$user" "$host" "$port" "$remote_command"; then
    remote_status=0
  else
    remote_status=$?
    status=1
    crit "Falha durante o sanitizer em $name"
    if (( remote_status >= 128 )); then
      cleanup_remote_temp "$user" "$host" "$port" "$remote_dir" || true
      return "$remote_status"
    fi
  fi

  if scp_from "$user" "$host" "$port" "${remote_dir}/users.result.json" "$json_file" && [[ -s "$json_file" ]]; then
    ok "Coletado: $json_file"
  else
    rm -f "$json_file"
    warn "JSON do sanitizer nao foi coletado em $name"
    status=1
  fi
  if scp_from "$user" "$host" "$port" "${remote_dir}/users.result.txt" "$txt_file" && [[ -s "$txt_file" ]]; then
    ok "Coletado: $txt_file"
  else
    rm -f "$txt_file"
    warn "TXT do sanitizer nao foi coletado em $name"
  fi
  if scp_from "$user" "$host" "$port" "${remote_dir}/users.history.csv" "$history_file" && [[ -s "$history_file" ]]; then
    ok "Historico coletado: $history_file"
  else
    rm -f "$history_file"
    warn "Historico nao foi coletado em $name"
  fi
  cleanup_remote_temp "$user" "$host" "$port" "$remote_dir" || warn "Falha ao limpar temporarios em $name"

  [[ "$status" -eq 0 ]] && ok "Sanitizer remoto concluido: $name"
  return "$status"
}

dispatch() {
  local command="$1" name="$2" user="$3" host="$4" port="$5"
  case "$command" in
    test) action_test "$name" "$user" "$host" "$port" ;;
    logs) action_logs "$name" "$user" "$host" "$port" ;;
    users-dry) action_users "dry-run" "$name" "$user" "$host" "$port" ;;
    users-apply) action_users "apply" "$name" "$user" "$host" "$port" ;;
  esac
}

list_servers() {
  printf '%-18s %-16s %-16s %-6s %-8s\n' "NOME" "USUARIO" "HOST" "PORTA" "ATIVO"
  while IFS=',' read -r name user host port enabled extra || [[ -n "${name:-}" ]]; do
    name="$(trim "${name:-}")"
    [[ -z "$name" || "$name" == \#* || "$name" == "name" ]] && continue
    printf '%-18s %-16s %-16s %-6s %-8s\n' "$name" "$(trim "${user:-}")" "$(trim "${host:-}")" "$(trim "${port:-22}")" "$(trim "${enabled:-yes}")"
  done < "$SERVERS_FILE"
}

run_for_targets() {
  local command="$1" selector="$2"
  local name user host port enabled extra matched=0 failures=0

  while IFS=',' read -r name user host port enabled extra || [[ -n "${name:-}" ]]; do
    name="$(trim "${name:-}")"
    user="$(trim "${user:-}")"
    host="$(trim "${host:-}")"
    port="$(trim "${port:-22}")"
    enabled="$(trim "${enabled:-yes}")"

    [[ -z "$name" || "$name" == \#* || "$name" == "name" ]] && continue
    [[ "$enabled" != "yes" && "$enabled" != "true" && "$enabled" != "1" ]] && continue
    [[ "$selector" != "all" && "$selector" != "$name" && "$selector" != "$host" ]] && continue

    matched=$((matched + 1))
    if ! valid_server_entry "$name" "$user" "$host" "$port"; then
      failures=$((failures + 1))
      continue
    fi
    echo
    echo -e "${BOLD}===== ${name} (${host}) =====${RESET}"
    if ! dispatch "$command" "$name" "$user" "$host" "$port"; then
      failures=$((failures + 1))
    fi
  done < "$SERVERS_FILE"

  if [[ "$matched" -eq 0 ]]; then
    crit "Nenhum servidor habilitado corresponde ao alvo: $selector"
    return 1
  fi

  if [[ "$failures" -gt 0 ]]; then
    crit "$failures de $matched servidor(es) apresentaram falha."
    return 1
  fi

  ok "Operacao concluida em $matched servidor(es)."
}

main() {
  local command="${1:-}"
  local selector="${2:-all}"
  local confirmation=""

  case "$command" in
    -h|--help|"") usage; exit 0 ;;
    list|test|logs|users-dry|users-apply) ;;
    *) crit "Comando invalido: $command"; usage; exit 1 ;;
  esac

  require_file "$SERVERS_FILE" "Arquivo de servidores" || exit 1

  if [[ "$command" == "list" ]]; then
    list_servers
    exit 0
  fi

  if [[ "$command" == "users-apply" && "$#" -lt 2 ]]; then
    crit "users-apply exige um alvo explicito: nome, IP ou all."
    exit 1
  fi

  if [[ "$command" == "users-apply" && "$selector" == "all" ]]; then
    warn "Voce esta prestes a aplicar o CSV em TODOS os servidores habilitados."
    read -r -p "Digite APLICAR para continuar: " confirmation
    [[ "$confirmation" == "APLICAR" ]] || { warn "Operacao cancelada."; exit 1; }
  fi

  run_for_targets "$command" "$selector"
}

main "$@"
