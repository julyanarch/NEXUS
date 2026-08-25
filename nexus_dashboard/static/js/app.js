document.addEventListener("DOMContentLoaded", function () {
  document.querySelectorAll("[data-confirm]").forEach(function (el) {
    el.addEventListener("submit", function (event) {
      var message = el.getAttribute("data-confirm");
      if (!window.confirm(message)) {
        event.preventDefault();
      }
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
});
