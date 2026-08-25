#!/usr/bin/env bash
set -Eeuo pipefail

# ------------------------------------------------------------
# NEXUS • Linux User Sanitizer
# Objetivo: executar onboarding/offboarding de usuários Linux
# Entrada: CSV exportado do chamado interno
# Saída: relatório .txt + .json para auditoria e IA interna (NEXUS)
# ------------------------------------------------------------

APP="nexus_sanitize_users"
OUT_DIR="/var/log/nexus"
HOST="$(hostname -s 2>/dev/null || hostname)"
STAMP="$(date +'%Y%m%d_%H%M%S')"
TXT="${OUT_DIR}/${APP}_${HOST}_${STAMP}.txt"
JSON="${OUT_DIR}/${APP}_${HOST}_${STAMP}.json"
HISTORY_FILE="${OUT_DIR}/${APP}_history.csv"

CSV_FILE=""
APPLY="false"
HISTORY_ENABLED="true"
DEFAULT_USER_SHELL="/bin/bash"
TTY_STATE=""
PASSWORD_HASH_FILE=""

PROTECTED_USERS="root daemon bin sys sync games man lp mail news uucp proxy www-data backup list irc gnats nobody systemd-network systemd-resolve messagebus sshd"

mkdir -p "$OUT_DIR"
chmod 0750 "$OUT_DIR" 2>/dev/null || true

exec > >(tee -a "$TXT") 2>&1

RED="\e[31m"
GREEN="\e[32m"
YELLOW="\e[33m"
BLUE="\e[34m"
CYAN="\e[36m"
BOLD="\e[1m"
RESET="\e[0m"

ok()    { echo -e "${GREEN}[OK]${RESET} $*" >&2; }
warn()  { echo -e "${YELLOW}[ALERTA]${RESET} $*" >&2; }
crit()  { echo -e "${RED}[CRITICO]${RESET} $*" >&2; }
info()  { echo -e "${BLUE}[INFO]${RESET} $*" >&2; }

restore_terminal() {
  if [[ -n "$TTY_STATE" && -w /dev/tty ]]; then
    stty "$TTY_STATE" < /dev/tty 2>/dev/null || true
    TTY_STATE=""
  fi
}

trap 'restore_terminal' EXIT
trap 'restore_terminal; exit 130' INT TERM

section() {
  echo >&2
  echo -e "${CYAN}${BOLD}========================================================${RESET}" >&2
  echo -e "${CYAN}${BOLD}$1${RESET}" >&2
  echo -e "${CYAN}${BOLD}========================================================${RESET}" >&2
}

usage() {
  cat <<EOF
Uso:
  sudo ./nexus_sanitize_users.sh --csv usuarios.csv --dry-run
  sudo ./nexus_sanitize_users.sh --csv usuarios.csv --apply
  sudo ./nexus_sanitize_users.sh --csv usuarios.csv --apply --password-hashes hashes.txt
  sudo ./nexus_sanitize_users.sh --csv usuarios.csv --apply --history /var/log/nexus/users_history.csv

Formato esperado do CSV:
  username,action,home,reason,ticket,groups,shell
  rebeca,create,yes,admissao,CHG12344,sudo,/bin/bash
  joao.silva,remove,yes,desligamento,CHG12345
  maria.souza,lock,no,afastamento,CHG12346

Acoes suportadas:
  create  Cria o usuario. Alias aceito: add.
  lock    Bloqueia a conta com usermod -L e expira o acesso.
  remove  Remove o usuario, mantendo a home por padrao.
  purge   Remove o usuario e a home, equivalente a remove_home=yes.

Observacoes:
  --dry-run e o comportamento seguro para simular a execucao.
  --apply executa alteracoes reais no servidor.
  Ao criar um usuario em modo --apply, a senha temporaria e solicitada
  de forma oculta e deve ser alterada no primeiro login.
  --history permite escolher o arquivo CSV acumulado de historico.
  --no-history desativa o registro acumulado.
  --password-hashes recebe hashes temporarios no formato username:hash.
EOF
}

trim() {
  local value="$1"
  value="${value#"${value%%[![:space:]]*}"}"
  value="${value%"${value##*[![:space:]]}"}"
  value="${value%$'\r'}"
  echo "$value"
}

json_escape() {
  local value="$1"
  value="${value//\\/\\\\}"
  value="${value//\"/\\\"}"
  value="${value//$'\n'/\\n}"
  value="${value//$'\r'/}"
  echo "$value"
}

csv_escape() {
  local value="$1"
  value="${value//$'\r'/}"
  value="${value//$'\n'/ }"
  value="${value//\"/\"\"}"
  printf '"%s"' "$value"
}

is_protected_user() {
  local username="$1"
  for protected in $PROTECTED_USERS; do
    [[ "$username" == "$protected" ]] && return 0
  done
  return 1
}

valid_username() {
  local username="$1"
  [[ "$username" =~ ^[a-z_][a-z0-9_.-]*[$]?$ ]]
}

valid_group_list() {
  local groups="$1"
  [[ -z "$groups" || "$groups" =~ ^[a-zA-Z0-9_.-]+([;:][a-zA-Z0-9_.-]+)*$ ]]
}

valid_shell_path() {
  local shell="$1"
  [[ -z "$shell" || "$shell" =~ ^/[a-zA-Z0-9_./-]+$ ]]
}

have_user() {
  local username="$1"
  getent passwd "$username" >/dev/null 2>&1
}

have_group() {
  local group="$1"
  getent group "$group" >/dev/null 2>&1
}

password_hash_for() {
  local username="$1"
  [[ -n "$PASSWORD_HASH_FILE" ]] || return 1
  awk -F: -v expected_user="$username" '
    $1 == expected_user {
      sub(/^[^:]*:/, "")
      print
      exit
    }
  ' "$PASSWORD_HASH_FILE"
}

run_or_preview() {
  if [[ "$APPLY" == "true" ]]; then
    "$@"
  else
    info "DRY-RUN: $*"
  fi
}

read_temporary_password() {
  local username="$1"
  local password=""
  local confirmation=""

  if [[ ! -r /dev/tty ]]; then
    crit "Terminal interativo indisponivel para definir a senha de $username."
    return 1
  fi

  while true; do
    TTY_STATE="$(stty -g < /dev/tty)"
    stty -echo < /dev/tty
    printf 'Senha temporaria para %s: ' "$username" > /dev/tty
    IFS= read -r password < /dev/tty
    printf '\nConfirme a senha temporaria: ' > /dev/tty
    IFS= read -r confirmation < /dev/tty
    printf '\n' > /dev/tty
    restore_terminal

    if [[ -z "$password" ]]; then
      warn "A senha nao pode ficar vazia."
    elif [[ "$password" == *:* ]]; then
      warn "A senha nao pode conter dois-pontos (:)."
    elif [[ "$password" != "$confirmation" ]]; then
      warn "As senhas nao conferem. Tente novamente."
    else
      TEMP_PASSWORD="$password"
      password=""
      confirmation=""
      return 0
    fi

    password=""
    confirmation=""
  done
}

emit_json() {
  local json_items="$1"

  {
    echo "{"
    echo "  \"meta\": {"
    echo "    \"tool\": \"nexus_sanitize_users\","
    echo "    \"generated_at\": \"$(date -Is)\","
    echo "    \"host\": \"$(json_escape "$HOST")\","
    echo "    \"mode\": \"$([[ "$APPLY" == "true" ]] && echo "apply" || echo "dry-run")\","
    echo "    \"source_csv\": \"$(json_escape "$CSV_FILE")\""
    echo "  },"
    echo "  \"results\": ["
    printf "%s\n" "$json_items"
    echo "  ]"
    echo "}"
  } > "$JSON"

  chmod 0640 "$JSON" 2>/dev/null || true
  ok "JSON gerado: $JSON"
}

append_json_item() {
  local current="$1"
  local username="$2"
  local action="$3"
  local remove_home="$4"
  local status="$5"
  local reason="$6"
  local ticket="$7"
  local message="$8"
  local groups="${9:-}"
  local shell="${10:-}"
  local comma=""

  [[ -n "$current" ]] && comma=","

  cat <<EOF
${current}${comma}
    {
      "username": "$(json_escape "$username")",
      "action": "$(json_escape "$action")",
      "remove_home": "$(json_escape "$remove_home")",
      "groups": "$(json_escape "$groups")",
      "shell": "$(json_escape "$shell")",
      "status": "$(json_escape "$status")",
      "reason": "$(json_escape "$reason")",
      "ticket": "$(json_escape "$ticket")",
      "message": "$(json_escape "$message")"
    }
EOF
}

init_history() {
  [[ "$HISTORY_ENABLED" != "true" ]] && return 0

  local history_dir
  history_dir="$(dirname "$HISTORY_FILE")"
  mkdir -p "$history_dir"
  chmod 0750 "$history_dir" 2>/dev/null || true

  if [[ ! -f "$HISTORY_FILE" || ! -s "$HISTORY_FILE" ]]; then
    printf 'timestamp,host,mode,source_csv,username,action,home,reason,ticket,groups,shell,status,message,report_txt,report_json\n' > "$HISTORY_FILE"
    chmod 0640 "$HISTORY_FILE" 2>/dev/null || true
  fi
}

append_history_record() {
  [[ "$HISTORY_ENABLED" != "true" ]] && return 0

  local username="$1"
  local action="$2"
  local remove_home="$3"
  local reason="$4"
  local ticket="$5"
  local status="$6"
  local message="$7"
  local groups="${8:-}"
  local shell="${9:-}"
  local mode

  username="$(trim "$username")"
  action="$(trim "$action")"
  remove_home="$(trim "$remove_home")"
  reason="$(trim "$reason")"
  ticket="$(trim "$ticket")"
  groups="$(trim "$groups")"
  shell="$(trim "$shell")"
  mode="$([[ "$APPLY" == "true" ]] && echo "apply" || echo "dry-run")"

  {
    csv_escape "$(date -Is)"; printf ','
    csv_escape "$HOST"; printf ','
    csv_escape "$mode"; printf ','
    csv_escape "$CSV_FILE"; printf ','
    csv_escape "$username"; printf ','
    csv_escape "$action"; printf ','
    csv_escape "$remove_home"; printf ','
    csv_escape "$reason"; printf ','
    csv_escape "$ticket"; printf ','
    csv_escape "$groups"; printf ','
    csv_escape "$shell"; printf ','
    csv_escape "$status"; printf ','
    csv_escape "$message"; printf ','
    csv_escape "$TXT"; printf ','
    csv_escape "$JSON"; printf '\n'
  } >> "$HISTORY_FILE"
}

parse_args() {
  if [[ "$#" -eq 0 ]]; then
    usage
    exit 1
  fi

  while [[ "$#" -gt 0 ]]; do
    case "$1" in
      --csv)
        if [[ -z "${2:-}" ]]; then
          crit "Informe o caminho do CSV apos --csv."
          exit 1
        fi
        CSV_FILE="${2:-}"
        shift 2
        ;;
      --apply)
        APPLY="true"
        shift
        ;;
      --dry-run)
        APPLY="false"
        shift
        ;;
      --history)
        if [[ -z "${2:-}" ]]; then
          crit "Informe o caminho do historico apos --history."
          exit 1
        fi
        HISTORY_FILE="${2:-}"
        shift 2
        ;;
      --no-history)
        HISTORY_ENABLED="false"
        shift
        ;;
      --password-hashes)
        if [[ -z "${2:-}" ]]; then
          crit "Informe o arquivo de hashes apos --password-hashes."
          exit 1
        fi
        PASSWORD_HASH_FILE="${2:-}"
        shift 2
        ;;
      -h|--help)
        usage
        exit 0
        ;;
      *)
        crit "Argumento invalido: $1"
        usage
        exit 1
        ;;
    esac
  done

  if [[ -z "$CSV_FILE" ]]; then
    crit "Informe o arquivo CSV com --csv."
    exit 1
  fi

  if [[ "$HISTORY_ENABLED" == "true" && -z "$HISTORY_FILE" ]]; then
    crit "Informe o arquivo de historico com --history ou use --no-history."
    exit 1
  fi

  if [[ ! -r "$CSV_FILE" ]]; then
    crit "CSV nao encontrado ou sem permissao de leitura: $CSV_FILE"
    exit 2
  fi

  if [[ -n "$PASSWORD_HASH_FILE" && ! -r "$PASSWORD_HASH_FILE" ]]; then
    crit "Arquivo de hashes nao encontrado ou sem leitura: $PASSWORD_HASH_FILE"
    exit 2
  fi

  if [[ "$APPLY" == "true" && "${EUID:-$(id -u)}" -ne 0 ]]; then
    crit "Use sudo para executar em modo --apply."
    exit 3
  fi
}

process_row() {
  local username="$1"
  local action="$2"
  local remove_home="$3"
  local reason="$4"
  local ticket="$5"
  local groups="${6:-}"
  local shell="${7:-}"
  local status="ok"
  local message=""

  username="$(trim "$username")"
  action="$(trim "$action")"
  remove_home="$(trim "$remove_home")"
  reason="$(trim "$reason")"
  ticket="$(trim "$ticket")"
  groups="$(trim "$groups")"
  shell="$(trim "$shell")"

  action="${action,,}"
  remove_home="${remove_home,,}"
  groups="${groups//:/;}"

  if [[ -z "$username" ]]; then
    echo "comment|linha vazia ignorada"
    return 0
  fi

  if [[ "$username" =~ ^# ]]; then
    echo "comment|comentario ignorado"
    return 0
  fi

  if [[ "$username" == "username" ]]; then
    echo "header|cabecalho ignorado"
    return 0
  fi

  if ! valid_username "$username"; then
    echo "failed|username invalido"
    return 0
  fi

  if ! valid_group_list "$groups"; then
    echo "failed|lista de grupos invalida"
    return 0
  fi

  if ! valid_shell_path "$shell"; then
    echo "failed|shell invalido"
    return 0
  fi

  if is_protected_user "$username"; then
    echo "blocked|usuario protegido nao pode ser alterado"
    return 0
  fi

  if [[ "$action" != "create" && "$action" != "add" ]] && ! have_user "$username"; then
    echo "skipped|usuario nao existe no servidor"
    return 0
  fi

  case "$action" in
    create|add)
      if have_user "$username"; then
        echo "skipped|usuario ja existe no servidor"
        return 0
      fi

      [[ -z "$shell" ]] && shell="$DEFAULT_USER_SHELL"
      [[ -x "$shell" ]] || shell="/bin/sh"

      local create_home_flag="-m"
      if [[ "$remove_home" == "no" || "$remove_home" == "false" || "$remove_home" == "0" ]]; then
        create_home_flag="-M"
      fi

      local group_array=()
      local missing_groups=()
      if [[ -n "$groups" ]]; then
        local IFS=';'
        read -ra group_array <<< "$groups"
        for group in "${group_array[@]}"; do
          if ! have_group "$group"; then
            missing_groups+=("$group")
          fi
        done
      fi

      if [[ "${#missing_groups[@]}" -gt 0 ]]; then
        echo "failed|grupos inexistentes: ${missing_groups[*]}"
        return 0
      fi

      local TEMP_PASSWORD=""
      local TEMP_PASSWORD_HASH=""
      local password_status=0
      if [[ "$APPLY" == "true" ]]; then
        if [[ -n "$PASSWORD_HASH_FILE" ]]; then
          TEMP_PASSWORD_HASH="$(password_hash_for "$username")"
          if [[ -z "$TEMP_PASSWORD_HASH" ]]; then
            echo "failed|hash de senha temporaria nao encontrado para o usuario"
            return 0
          fi
        elif ! read_temporary_password "$username"; then
          echo "failed|nao foi possivel ler a senha temporaria"
          return 0
        fi
      fi

      info "Criando usuario: $username"
      if run_or_preview useradd "$create_home_flag" -s "$shell" "$username"; then
        if [[ "${#group_array[@]}" -gt 0 ]]; then
          local group_csv
          group_csv="$(IFS=,; echo "${group_array[*]}")"
          if run_or_preview usermod -aG "$group_csv" "$username"; then
            message="usuario criado com grupos: $group_csv"
          else
            status="failed"
            message="usuario criado, mas falhou ao adicionar grupos"
          fi
        else
          message="usuario criado"
        fi

        if [[ "$APPLY" == "true" && "$status" == "ok" ]]; then
          if [[ -n "$TEMP_PASSWORD_HASH" ]]; then
            if usermod -p "$TEMP_PASSWORD_HASH" "$username"; then
              password_status=0
            else
              password_status=$?
            fi
          else
            if printf '%s:%s\n' "$username" "$TEMP_PASSWORD" | chpasswd; then
              password_status=0
            else
              password_status=$?
            fi
          fi

          if [[ "$password_status" -eq 0 ]] && chage -d 0 "$username"; then
            message="${message}; senha temporaria definida e troca obrigatoria ativada"
          else
            status="failed"
            message="${message}, mas falhou ao configurar a senha temporaria"
          fi
        elif [[ "$APPLY" != "true" ]]; then
          message="${message}; senha temporaria seria solicitada no modo apply"
        fi
        TEMP_PASSWORD=""
        TEMP_PASSWORD_HASH=""
      else
        status="failed"
        message="falha ao criar usuario"
      fi
      ;;
    lock)
      info "Bloqueando usuario: $username"
      if run_or_preview usermod -L "$username" && run_or_preview chage -E 0 "$username"; then
        message="usuario bloqueado e expirado"
      else
        status="failed"
        message="falha ao bloquear ou expirar usuario"
      fi
      ;;
    remove|delete)
      info "Removendo usuario: $username"
      if [[ "$remove_home" == "yes" || "$remove_home" == "true" || "$remove_home" == "1" ]]; then
        if run_or_preview userdel -r "$username"; then
          message="usuario removido com home"
        else
          status="failed"
          message="falha ao remover usuario com home"
        fi
      else
        if run_or_preview userdel "$username"; then
          message="usuario removido mantendo home"
        else
          status="failed"
          message="falha ao remover usuario mantendo home"
        fi
      fi
      ;;
    purge)
      info "Removendo usuario e home: $username"
      if run_or_preview userdel -r "$username"; then
        message="usuario removido com home"
      else
        status="failed"
        message="falha ao remover usuario com home"
      fi
      ;;
    *)
      status="failed"
      message="acao invalida: $action"
      ;;
  esac

  echo "${status}|${message}"
}

main() {
  parse_args "$@"

  section "NEXUS USER SANITIZER - Inicio"
  info "Host       : $HOST"
  info "CSV        : $CSV_FILE"
  info "Relatorio  : $TXT"
  info "JSON       : $JSON"
  if [[ "$HISTORY_ENABLED" == "true" ]]; then
    info "Historico  : $HISTORY_FILE"
  else
    warn "Historico  : desativado"
  fi

  if [[ "$APPLY" == "true" ]]; then
    warn "Modo APPLY: alteracoes reais serao executadas."
  else
    warn "Modo DRY-RUN: nenhuma alteracao real sera executada."
  fi

  local json_items=""
  local total=0 ok_count=0 skipped_count=0 failed_count=0 blocked_count=0
  init_history

  section "Processamento do CSV"
  while IFS=',' read -r username action remove_home reason ticket groups shell extra || [[ -n "${username:-}" ]]; do
    total=$((total + 1))
    local result status message
    result="$(process_row "${username:-}" "${action:-}" "${remove_home:-}" "${reason:-}" "${ticket:-}" "${groups:-}" "${shell:-}")"
    status="${result%%|*}"
    message="${result#*|}"

    if [[ "$status" == "header" ]]; then
      total=$((total - 1))
      continue
    fi

    if [[ "$status" == "comment" ]]; then
      total=$((total - 1))
      continue
    fi

    case "$status" in
      ok)
        ok_count=$((ok_count + 1))
        ok "${username}: $message"
        ;;
      skipped)
        skipped_count=$((skipped_count + 1))
        warn "${username}: $message"
        ;;
      blocked)
        blocked_count=$((blocked_count + 1))
        crit "${username}: $message"
        ;;
      failed)
        failed_count=$((failed_count + 1))
        crit "${username}: $message"
        ;;
    esac

    json_items="$(append_json_item "$json_items" "${username:-}" "${action:-}" "${remove_home:-}" "${status:-}" "${reason:-}" "${ticket:-}" "${message:-}" "${groups:-}" "${shell:-}")"
    append_history_record "${username:-}" "${action:-}" "${remove_home:-}" "${reason:-}" "${ticket:-}" "${status:-}" "${message:-}" "${groups:-}" "${shell:-}"
  done < "$CSV_FILE"

  section "Resumo"
  info "Total processado : $total"
  ok   "Sucesso          : $ok_count"
  warn "Ignorados        : $skipped_count"
  crit "Bloqueados       : $blocked_count"
  crit "Falhas           : $failed_count"
  if [[ "$HISTORY_ENABLED" == "true" ]]; then
    ok   "Historico        : $HISTORY_FILE"
  fi

  emit_json "$json_items"

  section "NEXUS USER SANITIZER - Fim"
}

main "$@"
