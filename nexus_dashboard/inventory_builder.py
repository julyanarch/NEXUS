import os

import yaml

import config
import models


def rebuild_inventory():
    """Regera ansible/inventory/hosts.yml a partir da tabela `servers`.

    A tabela SQLite e a fonte unica de verdade (tela "Servidores" da UI);
    este arquivo e sempre sobrescrito antes de cada execucao do Ansible.
    """
    servers = models.list_servers()
    hosts = {}
    for server in servers:
        if not server["enabled"]:
            continue
        hosts[server["name"]] = {
            "ansible_host": server["ssh_host"],
            "ansible_user": server["ssh_user"],
            "ansible_port": server["ssh_port"],
        }

    inventory = {"all": {"children": {"enabled": {"hosts": hosts}}}}

    os.makedirs(os.path.dirname(config.INVENTORY_PATH), exist_ok=True)
    with open(config.INVENTORY_PATH, "w", encoding="utf-8") as f:
        yaml.safe_dump(inventory, f, default_flow_style=False, sort_keys=False)

    return config.INVENTORY_PATH
