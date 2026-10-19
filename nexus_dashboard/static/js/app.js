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
  // criacao, fixo no backend - as outras acoes nem usam esse campo.) Os dois
  // ficam no proprio ".form-grid" (create_only_fields), separado do grid de
  // cima, pra sempre cairem juntos na mesma linha, alinhados.
  var createOnlyFields = document.getElementById("create_only_fields");
  function toggleCreateOnlyFields() {
    if (!actionSelect || !createOnlyFields) return;
    var show = actionSelect.value === "create" || actionSelect.value === "add";
    createOnlyFields.style.display = show ? "grid" : "none";
    createOnlyFields.querySelectorAll("input, select").forEach(function (el) { el.disabled = !show; });
  }
  if (actionSelect) {
    actionSelect.addEventListener("change", toggleCreateOnlyFields);
    toggleCreateOnlyFields();
  }

  // Feedback ao vivo da politica de senha (fica verde/vermelha enquanto
  // digita) - usado tanto na senha temporaria de Nova Acao quanto na senha
  // de Criar conta. O campo so precisa de data-password-policy="<minimo>";
  // o resto da regra (maiuscula, minuscula, caractere especial) e fixo,
  // igual a validacao do servidor (ver app.temp_password_errors).
  document.querySelectorAll("[data-password-policy]").forEach(function (el) {
    var min = el.getAttribute("data-password-policy");
    var rule = new RegExp("(?=.*[A-Z])(?=.*[a-z])(?=.*[^A-Za-z0-9]).{" + min + ",}");
    el.addEventListener("input", function () {
      el.classList.remove("pw-valid", "pw-invalid");
      if (!el.value) return;
      el.classList.add(rule.test(el.value) ? "pw-valid" : "pw-invalid");
    });
  });

  // NEXUS AI (suporte local) - abre/fecha o balaozinho e manda as perguntas
  // pro /chat (100% local, sem IA nem chamada de rede - ver support_bot.py).
  var chatBubble = document.getElementById("chat_bubble");
  var chatPanel = document.getElementById("chat_panel");
  var chatClose = document.getElementById("chat_close");
  var chatForm = document.getElementById("chat_form");
  var chatQuestion = document.getElementById("chat_question");
  var chatMessages = document.getElementById("chat_messages");

  function addChatMessage(text, who) {
    if (!chatMessages) return;
    var div = document.createElement("div");
    div.className = "chat-message chat-message-" + who;
    div.textContent = text;
    chatMessages.appendChild(div);
    chatMessages.scrollTop = chatMessages.scrollHeight;
  }

  if (chatBubble && chatPanel) {
    chatBubble.addEventListener("click", function () {
      chatPanel.hidden = !chatPanel.hidden;
      if (!chatPanel.hidden && chatQuestion) chatQuestion.focus();
    });
  }
  if (chatClose && chatPanel) {
    chatClose.addEventListener("click", function () { chatPanel.hidden = true; });
  }
  if (chatForm) {
    chatForm.addEventListener("submit", function (event) {
      event.preventDefault();
      var question = (chatQuestion.value || "").trim();
      if (!question) return;
      addChatMessage(question, "user");
      chatQuestion.value = "";
      var formData = new URLSearchParams();
      formData.set("csrf_token", chatForm.querySelector("[name=csrf_token]").value);
      formData.set("question", question);
      fetch("/chat", {
        method: "POST",
        headers: { "Content-Type": "application/x-www-form-urlencoded" },
        body: formData.toString(),
      })
        .then(function (res) { return res.json(); })
        .then(function (data) { addChatMessage(data.answer || "Sem resposta.", "bot"); })
        .catch(function () { addChatMessage("Não consegui falar com o servidor agora.", "bot"); });
    });
  }
});
