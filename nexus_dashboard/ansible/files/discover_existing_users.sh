#!/bin/bash
# NEXUS Dashboard - lista usuarios "de gente" (uid >= min_uid, shell
# interativo - exclui contas de sistema/servico) ja existentes no servidor,
# com status ativo/bloqueado. So leitura, nao cria/altera/remove nada.
#
# Rodado via "ansible.builtin.script" (nao "shell"/"command") de proposito:
# script copia e executa o arquivo direto por SSH, sem depender de um
# interpretador Python funcional no servidor remoto - necessario pra
# servidores antigos demais pra rodar o boilerplate dos modulos Ansible
# modernos (ex.: Python 2.6, ver secao 57 da documentacao tecnica).
#
# Uso: discover_existing_users.sh <min_uid>
#
# <min_uid> e so o valor padrao (convencao Debian/Ubuntu, onde login.defs
# tambem costuma ter UID_MIN=1000) - se o proprio servidor tiver um
# /etc/login.defs com UID_MIN diferente (ex.: CentOS/RHEL, que usa 500 por
# padrao), o valor detectado ali prevalece. Sem isso, servidor CentOS/RHEL
# aparenta "0 usuarios encontrados" mesmo tendo usuarios reais, porque os
# UIDs deles (500-999) ficam abaixo do corte fixo de 1000.
set -o pipefail

minuid="$1"
detected_uid_min=$(awk '/^UID_MIN[[:space:]]/{print $2}' /etc/login.defs 2>/dev/null)
if [ -n "$detected_uid_min" ]; then
  minuid="$detected_uid_min"
fi

awk -F: -v minuid="$minuid" \
  '($3 >= minuid) && ($3 != 65534) && ($7 !~ /(nologin|false)$/) {print $1","$3","$7}' \
  /etc/passwd | while IFS=, read -r nx_user nx_uid nx_shell; do
    nx_status=$(passwd -S "$nx_user" 2>/dev/null | awk '{print $2}')
    echo "${nx_user},${nx_uid},${nx_shell},${nx_status}"
  done
