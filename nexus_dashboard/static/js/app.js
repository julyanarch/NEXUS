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

  // Grupos e Shell so fazem sentido na criacao do usuario - em bloquear/
  // remover/purgar esses campos sao ignorados pelo script, entao esconde
  // pra ninguem mexer a toa. (Home saiu do formulario: e sempre "yes" na
  // criacao, fixo no backend - as outras acoes nem usam esse campo.)
  var fieldsOnlyForCreate = ["groups_group", "shell_group"]
    .map(function (id) { return document.getElementById(id); })
    .filter(Boolean);
  function toggleCreateOnlyFields() {
    if (!actionSelect || !fieldsOnlyForCreate.length) return;
    var show = actionSelect.value === "create" || actionSelect.value === "add";
    fieldsOnlyForCreate.forEach(function (group) {
      group.style.display = show ? "block" : "none";
      group.querySelectorAll("input, select").forEach(function (el) { el.disabled = !show; });
    });
  }
  if (actionSelect) {
    actionSelect.addEventListener("change", toggleCreateOnlyFields);
    toggleCreateOnlyFields();
  }
});
