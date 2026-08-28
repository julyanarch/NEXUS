document.addEventListener("DOMContentLoaded", function () {
  document.querySelectorAll("[data-confirm]").forEach(function (el) {
    el.addEventListener("submit", function (event) {
      var message = el.getAttribute("data-confirm");
      if (!window.confirm(message)) {
        event.preventDefault();
      }
    });
  });

  // Exclusao que precisa de motivo (ex.: servidor com historico) - pede o
  // motivo por prompt, grava no input escondido, e so deixa enviar se algo
  // foi digitado (senao a validacao do servidor barra de qualquer jeito).
  document.querySelectorAll("[data-prompt-reason]").forEach(function (el) {
    el.addEventListener("submit", function (event) {
      var message = el.getAttribute("data-prompt-reason");
      var reason = window.prompt(message, "");
      if (!reason || !reason.trim()) {
        event.preventDefault();
        return;
      }
      var input = el.querySelector(".js-delete-reason");
      if (input) input.value = reason.trim();
    });
  });

  var serverChecks = document.querySelectorAll(".js-server-check");
  var bulkField = document.getElementById("bulk_confirmation_group");
  function toggleBulkField() {
    if (!bulkField) return;
    var checkedCount = document.querySelectorAll(".js-server-check:checked").length;
    bulkField.style.display = checkedCount > 1 ? "flex" : "none";
  }
  serverChecks.forEach(function (el) { el.addEventListener("change", toggleBulkField); });
  toggleBulkField();

  // Selecionar todos os servidores de destino de uma vez (pula os desabilitados).
  var selectAllServers = document.getElementById("select_all_servers");
  var selectableServerChecks = document.querySelectorAll(".js-server-check:not(:disabled)");
  function syncSelectAllState() {
    if (!selectAllServers || !selectableServerChecks.length) return;
    var checkedCount = document.querySelectorAll(".js-server-check:not(:disabled):checked").length;
    selectAllServers.checked = checkedCount === selectableServerChecks.length;
    selectAllServers.indeterminate = checkedCount > 0 && checkedCount < selectableServerChecks.length;
  }
  if (selectAllServers) {
    selectAllServers.addEventListener("change", function () {
      selectableServerChecks.forEach(function (el) { el.checked = selectAllServers.checked; });
      toggleBulkField();
    });
    selectableServerChecks.forEach(function (el) { el.addEventListener("change", syncSelectAllState); });
    syncSelectAllState();
  }

  var actionSelect = document.getElementById("action_select");
  var passwordGroup = document.getElementById("password_group");
  function togglePasswordGroup() {
    if (!actionSelect || !passwordGroup) return;
    var show = actionSelect.value === "create" || actionSelect.value === "add";
    passwordGroup.style.display = show ? "block" : "none";
  }
  if (actionSelect) {
    actionSelect.addEventListener("change", togglePasswordGroup);
    togglePasswordGroup();
  }

  // Shell e Home nao fazem sentido para remover/purgar: a propria acao ja diz
  // se a home fica ou e apagada, entao esconde os dois pra ninguem mexer neles
  // manualmente (o backend tambem ignora/forca esses valores nesses casos).
  var shellGroup = document.getElementById("shell_group");
  var homeGroup = document.getElementById("home_group");
  function toggleShellHomeGroups() {
    if (!actionSelect || !shellGroup || !homeGroup) return;
    var hide = actionSelect.value === "remove" || actionSelect.value === "purge";
    shellGroup.style.display = hide ? "none" : "block";
    homeGroup.style.display = hide ? "none" : "block";
    shellGroup.querySelectorAll("input, select").forEach(function (el) { el.disabled = hide; });
    homeGroup.querySelectorAll("input, select").forEach(function (el) { el.disabled = hide; });
  }
  if (actionSelect) {
    actionSelect.addEventListener("change", toggleShellHomeGroups);
    toggleShellHomeGroups();
  }
});
