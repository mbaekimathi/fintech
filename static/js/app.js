function nexusShell() {
  const mobileQuery = window.matchMedia("(max-width: 900px)");
  return {
    navOpen: false,
    collapsed: false,
    isMobile: mobileQuery.matches,
    init() {
      const sync = () => {
        this.isMobile = mobileQuery.matches;
        if (!this.isMobile) this.navOpen = false;
      };
      if (mobileQuery.addEventListener) {
        mobileQuery.addEventListener("change", sync);
      } else {
        mobileQuery.addListener(sync);
      }
    },
    toggleNav() {
      if (this.isMobile) {
        this.navOpen = !this.navOpen;
      } else {
        this.collapsed = !this.collapsed;
      }
    },
  };
}

document.addEventListener("input", (event) => {
  const field = event.target;
  if (!field.classList.contains("pin-field")) return;
  field.value = field.value.replace(/\D/g, "").slice(0, 6);
});

document.addEventListener("click", (event) => {
  const btn = event.target.closest(".password-toggle");
  if (!btn) return;
  const wrap = btn.closest(".password-field");
  const input = wrap && wrap.querySelector("input");
  if (!input) return;
  const show = input.type === "password";
  input.type = show ? "text" : "password";
  btn.classList.toggle("is-visible", show);
  btn.setAttribute("aria-pressed", show ? "true" : "false");
  btn.setAttribute("aria-label", show ? "Hide password" : "Show password");
});

function initDarajaSetup() {
  const form = document.querySelector("[data-daraja-setup]");
  if (!form) return;
  const envField = form.querySelector("#id_environment") || form.querySelector('[name="environment"]');
  const defaultsNode = document.getElementById("daraja-sandbox-defaults");
  if (!envField || !defaultsNode) return;
  const defaults = JSON.parse(defaultsNode.textContent);

  const setField = (name, value) => {
    const el =
      form.querySelector(`[name="${name}"]:not([type="hidden"])`) ||
      form.querySelector(`[name="${name}"]`);
    if (!el || value == null) return;
    if (el.type === "checkbox") {
      el.checked = Boolean(value);
      return;
    }
    el.value = value;
  };

  const revealSecrets = () => {
    form.querySelectorAll(".password-field").forEach((wrap) => {
      const input = wrap.querySelector("input");
      const btn = wrap.querySelector(".password-toggle");
      if (input) input.type = "text";
      if (btn) {
        btn.classList.add("is-visible");
        btn.setAttribute("aria-pressed", "true");
        btn.setAttribute("aria-label", "Hide password");
      }
    });
  };

  const sandboxValues = {
    hub_paybill: defaults.shortcode,
    shortcode: defaults.shortcode,
    org_shortcode: defaults.org_shortcode,
    passkey: defaults.passkey,
    initiator_name: defaults.initiator_name,
    security_credential: defaults.security_credential,
    stk_callback_url: defaults.stk_callback_url,
    result_url: defaults.result_url,
    timeout_url: defaults.timeout_url,
    stk_transaction_type: defaults.stk_transaction_type,
    stk_account_reference: defaults.stk_account_reference,
    stk_transaction_desc: defaults.stk_transaction_desc,
    balance_identifier_type: defaults.balance_identifier_type,
    balance_remarks: defaults.balance_remarks,
    b2c_command_id: defaults.b2c_command_id,
    b2c_remarks: defaults.b2c_remarks,
    b2c_occasion: defaults.b2c_occasion,
    b2b_sender_identifier_type: defaults.b2b_sender_identifier_type,
    b2b_paybill_command: defaults.b2b_paybill_command,
    b2b_till_command: defaults.b2b_till_command,
    b2b_remarks: defaults.b2b_remarks,
  };

  const portalFields = new Set(["org_shortcode", "initiator_name", "security_credential"]);

  const applySandbox = () => {
    Object.entries(sandboxValues).forEach(([name, value]) => {
      const el =
        form.querySelector(`[name="${name}"]:not([type="hidden"])`) ||
        form.querySelector(`[name="${name}"]`);
      if (portalFields.has(name) && el && String(el.value || "").trim()) return;
      setField(name, value);
    });
    setField("b2c_enabled", true);
    setField("b2b_enabled", true);
    const sandboxGuide = document.querySelector("[data-sandbox-guide]");
    const productionGuide = document.querySelector("[data-production-guide]");
    if (sandboxGuide) sandboxGuide.hidden = false;
    if (productionGuide) productionGuide.hidden = true;
  };

  const clearSandbox = () => {
    Object.entries(sandboxValues).forEach(([name, sandboxValue]) => {
      const el = form.querySelector(`[name="${name}"]`);
      if (el && el.value === sandboxValue) el.value = "";
    });
    setField("b2c_enabled", false);
    setField("b2b_enabled", false);
    const sandboxGuide = document.querySelector("[data-sandbox-guide]");
    const productionGuide = document.querySelector("[data-production-guide]");
    if (sandboxGuide) sandboxGuide.hidden = true;
    if (productionGuide) productionGuide.hidden = false;
  };

  const sync = () => {
    if (envField.value === "SANDBOX") applySandbox();
    else clearSandbox();
  };

  envField.addEventListener("change", sync);
  revealSecrets();
  if (envField.value === "SANDBOX") applySandbox();
  else {
    const sandboxGuide = document.querySelector("[data-sandbox-guide]");
    const productionGuide = document.querySelector("[data-production-guide]");
    if (sandboxGuide) sandboxGuide.hidden = true;
    if (productionGuide) productionGuide.hidden = false;
  }
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", () => {
    initDarajaSetup();
    initDarajaTests();
  });
} else {
  initDarajaSetup();
  initDarajaTests();
}

function initDarajaTests() {
  const table = document.querySelector("[data-daraja-tests]");
  if (!table) return;
  const pollUrl = table.getAttribute("data-poll-url");
  const hint = document.querySelector("[data-poll-hint]");
  const tbody = table.querySelector("tbody");
  if (!pollUrl || !tbody) return;

  const csrf =
    document.querySelector('input[name="csrfmiddlewaretoken"]')?.value ||
    "";

  const escapeHtml = (value) =>
    String(value ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");

  const badge = (status, label) =>
    `<span class="badge badge-${escapeHtml(String(status || "").toLowerCase())}">${escapeHtml(label || status)}</span>`;

  const refreshCell = (row) => {
    if (!row.can_refresh) return "";
    return `<form method="post" class="inline-form">
      <input type="hidden" name="csrfmiddlewaretoken" value="${escapeHtml(csrf)}">
      <input type="hidden" name="intent" value="refresh">
      <input type="hidden" name="operation_id" value="${escapeHtml(row.id)}">
      <button type="submit" class="btn btn-ghost btn-small">Refresh</button>
    </form>`;
  };

  const renderRow = (row) => {
    const amount = row.amount ? `KES ${escapeHtml(row.amount)}` : "—";
    return `<tr data-id="${escapeHtml(row.id)}" data-status="${escapeHtml(row.status)}" data-watch="${row.watch ? "1" : ""}">
      <td data-col="when">${escapeHtml(row.when)}</td>
      <td data-col="kind">${escapeHtml(row.kind_label)}</td>
      <td data-col="destination">${escapeHtml(row.destination)}</td>
      <td data-col="amount">${amount}</td>
      <td data-col="status">${badge(row.status, row.status_label)}</td>
      <td data-col="summary">${escapeHtml(row.summary || "Waiting")}</td>
      <td data-col="refresh">${refreshCell(row)}</td>
    </tr>`;
  };

  let tries = 0;
  const tick = async () => {
    const queued = table.querySelectorAll('[data-watch="1"]');
    if (!queued.length || tries++ > 45) {
      if (hint && tries > 1 && !queued.length) {
        hint.textContent = "Latest Safaricom results are shown below.";
      }
      return;
    }
    if (hint) hint.textContent = "Listening for Safaricom… updating like STK.";
    try {
      const response = await fetch(pollUrl, {
        headers: { Accept: "application/json", "X-Requested-With": "XMLHttpRequest" },
      });
      if (response.ok) {
        const data = await response.json();
        const rows = data.operations || [];
        tbody.innerHTML = rows.length
          ? rows.map(renderRow).join("")
          : `<tr data-empty="1"><td colspan="7" class="empty">No tests yet. Prompt a number, request balance, or send money.</td></tr>`;
      }
    } catch (_err) {
      /* keep last table state */
    }
    window.setTimeout(tick, 1200);
  };

  if (table.querySelector('[data-watch="1"]')) {
    window.setTimeout(tick, 800);
  }
}
