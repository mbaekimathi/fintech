function kenyaSalaryForm(config) {
  const num = (value) => {
    const n = Number(value);
    return Number.isFinite(n) ? n : 0;
  };
  const money = (value) => Math.round((num(value) + Number.EPSILON) * 100) / 100;
  const NSSF_LEL = 9000;
  const NSSF_UEL = 108000;
  const NSSF_RATE = 0.06;
  const SHIF_RATE = 0.0275;
  const SHIF_MIN = 300;
  const AHL_RATE = 0.015;
  const PERSONAL_RELIEF = 2400;
  const PAYE_BANDS = [
    [24000, 0.1],
    [32333, 0.25],
    [500000, 0.3],
    [800000, 0.325],
    [null, 0.35],
  ];

  const nssfEmployee = (pensionable) => {
    const pay = Math.min(Math.max(money(pensionable), 0), NSSF_UEL);
    const tierI = money(Math.min(pay, NSSF_LEL) * NSSF_RATE);
    const tierII = money(Math.max(pay - NSSF_LEL, 0) * NSSF_RATE);
    return money(tierI + tierII);
  };

  const payeBeforeRelief = (taxable) => {
    let remaining = Math.max(money(taxable), 0);
    let tax = 0;
    let lower = 0;
    for (const [upper, rate] of PAYE_BANDS) {
      if (remaining <= 0) break;
      const width = upper == null ? remaining : Math.max(Math.min(remaining, upper - lower), 0);
      tax += width * rate;
      remaining -= width;
      if (upper != null) lower = upper;
    }
    return money(tax);
  };

  return {
    basic: num(config.basic),
    house: num(config.house),
    transport: num(config.transport),
    other: num(config.other),
    isResident: Boolean(config.isResident),
    isPwd: Boolean(config.isPwd),
    paymentMethod: config.paymentMethod || "BANK",
    get gross() {
      return money(this.basic + this.house + this.transport + this.other);
    },
    get estimate() {
      const gross = this.gross;
      const nssf = nssfEmployee(gross);
      const shif = gross > 0 ? money(Math.max(gross * SHIF_RATE, SHIF_MIN)) : 0;
      const ahl = money(gross * AHL_RATE);
      let paye = 0;
      if (!this.isPwd) {
        const taxable = money(Math.max(gross - nssf - shif - ahl, 0));
        paye = payeBeforeRelief(taxable);
        if (this.isResident) paye = money(Math.max(paye - PERSONAL_RELIEF, 0));
      }
      const employeeDeductions = money(nssf + shif + ahl + paye);
      return {
        nssfEmployee: nssf,
        nssfEmployer: nssf,
        shif,
        ahlEmployee: ahl,
        ahlEmployer: ahl,
        paye,
        employeeDeductions,
        netPay: money(gross - employeeDeductions),
      };
    },
    formatMoney(value) {
      return `KES ${money(value).toLocaleString("en-KE", {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
      })}`;
    },
  };
}

function sendMoneyPanel(config) {
  const digits = (value) => String(value || "").replace(/\D/g, "");
  return {
    type: config.type || "PHONE",
    destination: digits(config.destination),
    accountRef: config.accountRef || config.accountExample || "",
    phoneReady: Boolean(config.phoneReady),
    b2bReady: Boolean(config.b2bReady),
    phoneExample: config.phoneExample || "254708374149",
    paybillExample: config.paybillExample || "600000",
    tillExample: config.tillExample || "600000",
    accountExample: config.accountExample || "NEXUS",
    isSandbox: Boolean(config.isSandbox),
    init() {
      if (this.type === "PHONE" && !this.phoneReady && this.b2bReady) this.type = "PAYBILL";
      if ((this.type === "PAYBILL" || this.type === "TILL") && !this.b2bReady && this.phoneReady) {
        this.type = "PHONE";
      }
      this.onTypeChange(true);
    },
    get readyForType() {
      return this.type === "PHONE" ? this.phoneReady : this.b2bReady;
    },
    get readyLabel() {
      if (!this.phoneReady && !this.b2bReady) return "Not ready";
      if (this.type === "PHONE") return this.phoneReady ? "Phone ready" : "Phone not ready";
      if (this.type === "TILL") return this.b2bReady ? "Till ready" : "Till not ready";
      return this.b2bReady ? "Paybill ready" : "Paybill not ready";
    },
    get destinationLabel() {
      if (this.type === "PHONE") return "Phone number";
      if (this.type === "TILL") return "Till number";
      return "Paybill number";
    },
    get destinationPlaceholder() {
      if (this.type === "PHONE") return this.phoneExample;
      if (this.type === "TILL") return this.tillExample;
      return this.paybillExample;
    },
    get destinationHint() {
      if (!this.isSandbox) {
        if (this.type === "PHONE") return "Kenyan mobile, e.g. 07XXXXXXXX.";
        if (this.type === "TILL") return "Buy Goods till that should receive the money.";
        return "Paybill shortcode that should receive the money.";
      }
      if (this.type === "PHONE") return `Sandbox test phone: ${this.phoneExample}`;
      if (this.type === "TILL") return `Sandbox till / shortcode: ${this.tillExample}`;
      return `Sandbox paybill: ${this.paybillExample}. Account number required.`;
    },
    get submitLabel() {
      if (this.type === "PHONE") return "Send to phone";
      if (this.type === "TILL") return "Send to till";
      return "Send to paybill";
    },
    onTypeChange(fromInit = false) {
      const current = digits(this.destination);
      const looksPhone = current.startsWith("254") || current.length >= 10;
      const looksShortcode = current.length >= 5 && current.length <= 8 && !looksPhone;
      if (this.type === "PHONE") {
        if (!fromInit || !looksPhone) this.destination = this.isSandbox ? this.phoneExample : looksPhone ? current : "";
      } else if (this.type === "PAYBILL") {
        if (!fromInit || looksPhone || !looksShortcode) {
          this.destination = this.isSandbox ? this.paybillExample : looksShortcode ? current : "";
        }
        if (!String(this.accountRef || "").trim()) this.accountRef = this.accountExample;
      } else if (!fromInit || looksPhone || !looksShortcode) {
        this.destination = this.isSandbox ? this.tillExample : looksShortcode ? current : "";
      }
    },
  };
}

function moneyRequestPanel(config) {
  const digits = (value) => String(value || "").replace(/\D/g, "");
  return {
    type: config.type || "PHONE",
    destination: digits(config.destination),
    accountRef: config.accountRef || "",
    lookupUrl: config.lookupUrl || "",
    lookupTimer: null,
    lookupToken: 0,
    lookupState: "idle",
    recipientName: "",
    lookupDetail: "",
    init() {
      this.onTypeChange(true);
      this.$watch("destination", () => this.scheduleLookup());
      this.$watch("type", () => this.scheduleLookup());
      this.scheduleLookup();
    },
    get destinationLabel() {
      if (this.type === "PHONE") return "Phone number";
      if (this.type === "TILL") return "Till number";
      return "Paybill number";
    },
    get destinationPlaceholder() {
      if (this.type === "PHONE") return "07XXXXXXXX or 2547XXXXXXXX";
      if (this.type === "TILL") return "Till number";
      return "Paybill shortcode";
    },
    get destinationHint() {
      if (this.type === "PHONE") return "Where the money should be sent (M-Pesa phone).";
      if (this.type === "TILL") return "Buy Goods till that should receive the transfer.";
      return "Paybill shortcode that should receive the transfer.";
    },
    get submitLabel() {
      if (this.type === "PHONE") return "Request transfer to phone";
      if (this.type === "TILL") return "Request transfer to till";
      return "Request transfer to paybill";
    },
    get showLookup() {
      return this.lookupState === "loading" || this.lookupState === "found" || this.lookupState === "missing";
    },
    readyForLookup(value) {
      const dest = digits(value);
      if (this.type === "PHONE") {
        return (
          (dest.startsWith("254") && dest.length === 12) ||
          (dest.startsWith("0") && dest.length === 10) ||
          dest.length === 9
        );
      }
      return dest.length >= 5 && dest.length <= 8 && !dest.startsWith("254");
    },
    clearLookup() {
      this.lookupState = "idle";
      this.recipientName = "";
      this.lookupDetail = "";
    },
    scheduleLookup() {
      if (this.lookupTimer) {
        clearTimeout(this.lookupTimer);
        this.lookupTimer = null;
      }
      this.clearLookup();
      if (!this.lookupUrl || !this.readyForLookup(this.destination)) return;
      this.lookupState = "loading";
      this.lookupTimer = setTimeout(() => this.runLookup(), 450);
    },
    async runLookup() {
      if (!this.lookupUrl || !this.readyForLookup(this.destination)) {
        this.clearLookup();
        return;
      }
      const token = ++this.lookupToken;
      const dest = digits(this.destination);
      const type = this.type;
      this.lookupState = "loading";
      this.recipientName = "";
      this.lookupDetail = "Checking recipient…";
      try {
        const url = new URL(this.lookupUrl, window.location.origin);
        url.searchParams.set("destination_type", type);
        url.searchParams.set("destination", dest);
        const response = await fetch(url.toString(), {
          headers: { Accept: "application/json", "X-Requested-With": "XMLHttpRequest" },
          credentials: "same-origin",
        });
        const data = await response.json().catch(() => ({}));
        if (token !== this.lookupToken || digits(this.destination) !== dest || this.type !== type) {
          return;
        }
        if (data.found && data.name) {
          this.lookupState = "found";
          this.recipientName = data.name;
          this.lookupDetail = "";
          return;
        }
        this.lookupState = "missing";
        this.recipientName = "";
        this.lookupDetail = data.detail || "Name not available yet.";
      } catch (error) {
        if (token !== this.lookupToken) return;
        this.lookupState = "missing";
        this.recipientName = "";
        this.lookupDetail = "Could not check recipient right now.";
      }
    },
    onTypeChange(fromInit = false) {
      const current = digits(this.destination);
      const looksPhone = current.startsWith("254") || current.startsWith("0") || current.length >= 9;
      const looksShortcode = current.length >= 5 && current.length <= 8 && !looksPhone;
      if (this.type === "PHONE") {
        if (!fromInit && !looksPhone) this.destination = "";
      } else if (this.type === "PAYBILL") {
        if (!fromInit && (looksPhone || !looksShortcode)) this.destination = "";
      } else if (!fromInit && (looksPhone || !looksShortcode)) {
        this.destination = "";
      }
      if (!fromInit) this.scheduleLookup();
    },
  };
}

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
  const scrollAnchor = form.getAttribute("data-scroll-anchor");
  if (scrollAnchor) {
    const target = document.getElementById(scrollAnchor);
    if (target) {
      window.requestAnimationFrame(() => {
        target.scrollIntoView({ behavior: "smooth", block: "start" });
      });
    }
  }
  const envField = form.querySelector("#id_environment") || form.querySelector('[name="environment"]');
  const channelField = form.querySelector("#id_channel") || form.querySelector('[name="channel"]');
  const numberField = form.querySelector("#id_hub_paybill") || form.querySelector('[name="hub_paybill"]');
  const defaultsNode = document.getElementById("daraja-sandbox-defaults");
  if (!envField || !defaultsNode) return;
  const defaults = JSON.parse(defaultsNode.textContent);
  const formUrls = defaults.form_urls || {};

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

  const fillEmpty = (name, value) => {
    const el = form.querySelector(`[name="${name}"]`);
    if (!el || el.type === "checkbox") return;
    if (!String(el.value || "").trim() && value) el.value = value;
  };

  const digits = (value) => String(value || "").replace(/\D/g, "");

  const setNumberLabel = (till) => {
    if (!numberField) return;
    const label = numberField.closest("label");
    if (!label) return;
    const textNode = [...label.childNodes].find((node) => node.nodeType === 3 && node.textContent.trim());
    if (textNode) textNode.textContent = till ? "Till number" : "Paybill number";
    const hint = label.querySelector(".field-hint");
    if (hint) {
      hint.textContent = till
        ? "Buy Goods till used to collect and disburse. Shortcode and callbacks fill from this."
        : "Paybill used to collect and disburse. Shortcode and callbacks fill from this.";
    }
    numberField.placeholder = till ? "Your live till, e.g. 123456" : "Your live paybill, e.g. 888555";
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
  const sandboxGuide = document.querySelector("[data-sandbox-guide]");
  const productionGuide = document.querySelector("[data-production-guide]");
  const stkHeading = document.querySelector("[data-stk-heading]");
  const stkCopy = document.querySelector("[data-stk-copy]");
  const balanceHeading = document.querySelector("[data-balance-heading]");
  const balanceCopy = document.querySelector("[data-balance-copy]");
  const paybillSections = form.querySelectorAll("[data-channel-paybill]");
  const tillSections = form.querySelectorAll("[data-channel-till]");
  const derivedFields = form.querySelectorAll("[data-channel-derived]");

  const syncChannelSections = (till) => {
    paybillSections.forEach((el) => {
      el.hidden = till;
    });
    tillSections.forEach((el) => {
      el.hidden = !till;
    });
    derivedFields.forEach((el) => {
      el.hidden = true;
    });
  };

  const applyChannel = () => {
    const till = channelField && channelField.value === "TILL";
    const mapping = till ? defaults.channel_till : defaults.channel_paybill;
    if (mapping) {
      Object.entries(mapping).forEach(([name, value]) => setField(name, value));
    }
    setNumberLabel(till);
    syncChannelSections(till);
    if (stkHeading) {
      stkHeading.textContent = till ? "STK push — collect into this till" : "STK push — collect into this paybill";
    }
    if (stkCopy) {
      stkCopy.textContent = till
        ? "Buy Goods / CustomerBuyGoodsOnline. Passkey is not used for balance or sending."
        : "Lipa Na M-Pesa Online / CustomerPayBillOnline. Passkey is not used for balance or sending.";
    }
    if (balanceHeading) {
      balanceHeading.textContent = till ? "Live till balance" : "Live paybill balance";
    }
    if (balanceCopy) {
      balanceCopy.innerHTML = till
        ? 'Account Balance API. Paste <strong>Shortcode 1</strong>, <strong>Initiator Name</strong>, and the initiator password from <a href="https://developer.safaricom.co.ke/test_credentials" target="_blank" rel="noopener">Daraja Test credentials</a> — Party A for sandbox is 600996.'
        : 'Account Balance API. Paste <strong>Shortcode 1</strong>, <strong>Initiator Name</strong>, and the initiator password from <a href="https://developer.safaricom.co.ke/test_credentials" target="_blank" rel="noopener">Daraja Test credentials</a> — not the STK till 174379.';
    }
    const number = digits(numberField && numberField.value);
    const sandbox = envField.value === "SANDBOX";
    if (number) {
      setField("shortcode", sandbox && !till ? defaults.shortcode : number);
      if (sandbox && !till) setField("org_shortcode", defaults.org_shortcode);
      else setField("org_shortcode", sandbox ? defaults.org_shortcode : number);
      if (till) setField("till_number", sandbox ? number || defaults.shortcode : number);
      else if (!String(form.querySelector('[name="till_number"]')?.value || "").trim()) {
        setField("till_number", "");
      }
    } else if (sandbox) {
      setField("hub_paybill", defaults.shortcode);
      setField("shortcode", defaults.shortcode);
      setField("org_shortcode", defaults.org_shortcode);
      if (till) setField("till_number", defaults.shortcode);
    }
  };

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
    if (sandboxGuide) sandboxGuide.hidden = false;
    if (productionGuide) productionGuide.hidden = true;
    setField("stk_callback_url", formUrls.stk_callback_url || "");
    setField("result_url", formUrls.result_url || "");
    setField("timeout_url", formUrls.timeout_url || "");
    applyChannel();
  };

  const applyProduction = () => {
    fillEmpty("stk_account_reference", defaults.stk_account_reference);
    fillEmpty("stk_transaction_desc", defaults.stk_transaction_desc);
    fillEmpty("balance_remarks", defaults.balance_remarks);
    fillEmpty("b2c_remarks", defaults.b2c_remarks);
    fillEmpty("b2c_occasion", defaults.b2c_occasion);
    fillEmpty("b2b_remarks", defaults.b2b_remarks);
    setField("stk_callback_url", formUrls.stk_callback_url || "");
    setField("result_url", formUrls.result_url || "");
    setField("timeout_url", formUrls.timeout_url || "");
    setField("b2c_enabled", true);
    setField("b2b_enabled", true);
    applyChannel();
  };

  const clearSandbox = () => {
    Object.entries(sandboxValues).forEach(([name, sandboxValue]) => {
      const el = form.querySelector(`[name="${name}"]`);
      if (el && el.value === sandboxValue) el.value = "";
    });
    if (sandboxGuide) sandboxGuide.hidden = true;
    if (productionGuide) productionGuide.hidden = false;
    applyProduction();
  };

  const syncEnv = () => {
    if (envField.value === "SANDBOX") applySandbox();
    else clearSandbox();
  };

  envField.addEventListener("change", syncEnv);
  if (channelField) channelField.addEventListener("change", applyChannel);
  if (numberField) {
    numberField.addEventListener("input", () => {
      numberField.value = digits(numberField.value);
      applyChannel();
    });
  }
  revealSecrets();
  if (envField.value === "SANDBOX") applySandbox();
  else {
    if (sandboxGuide) sandboxGuide.hidden = true;
    if (productionGuide) productionGuide.hidden = false;
    applyProduction();
  }
}

function initHubBalance() {
  const panel = document.querySelector("[data-hub-balance]");
  if (!panel) return;

  const pollUrl = panel.getAttribute("data-poll-url");
  const requestUrl = panel.getAttribute("data-request-url");
  const autoRefresh = panel.getAttribute("data-auto-refresh") === "1";
  const summaryEl = panel.querySelector("[data-balance-summary]");
  const whenEl = panel.querySelector("[data-balance-when]");
  const hintEl = panel.querySelector("[data-balance-hint]");
  const refreshBtn = panel.querySelector("[data-balance-refresh]");
  const utilityEl = panel.querySelector("[data-utility-balance]");
  const workingEl = panel.querySelector("[data-working-balance]");
  const utilityCurrencyEl = panel.querySelector("[data-utility-currency]");
  const workingCurrencyEl = panel.querySelector("[data-working-currency]");
  const transferPanel = document.querySelector("[data-utility-transfer]");
  const csrf =
    document.querySelector('meta[name="csrf-token"]')?.getAttribute("content") ||
    document.querySelector('input[name="csrfmiddlewaretoken"]')?.value ||
    document.cookie.match(/csrftoken=([^;]+)/)?.[1] ||
    "";

  const formatAmount = (amount) => {
    if (amount == null || amount === "") return "—";
    const value = Number(amount);
    if (!Number.isFinite(value)) return "—";
    return value.toLocaleString("en-KE", {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    });
  };

  const applyBalanceCard = (valueEl, currencyEl, currency, amount) => {
    if (valueEl) valueEl.textContent = formatAmount(amount);
    if (currencyEl) currencyEl.textContent = currency || "KES";
  };

  const syncTransferPanel = (data) => {
    if (!transferPanel) return;
    const utilityAmount = data.utility_amount;
    transferPanel.dataset.maxUtility = utilityAmount != null ? String(utilityAmount) : "";
    transferPanel.dataset.transferReady = data.transfer_ready ? "1" : "0";
    const amountField = transferPanel.querySelector("[data-utility-amount]");
    const submitBtn = transferPanel.querySelector("[data-utility-submit]");
    const maxBtn = transferPanel.querySelector("[data-utility-max]");
    const hasUtility = utilityAmount != null && Number(utilityAmount) > 0;
    if (amountField) {
      if (utilityAmount != null) amountField.max = String(utilityAmount);
      else amountField.removeAttribute("max");
    }
    if (submitBtn) submitBtn.disabled = !hasUtility || !data.transfer_ready;
    if (maxBtn) maxBtn.disabled = !hasUtility || !data.transfer_ready;
    const blockers = Array.isArray(data.transfer_blockers) ? data.transfer_blockers : [];
    if (blockers.length && !data.transfer_ready) {
      setHint(blockers[0]);
    } else if (data.transfer_ready) {
      setHint("");
    }
  };

  const setHint = (text) => {
    if (!hintEl) return;
    if (text) {
      hintEl.textContent = text;
      hintEl.hidden = false;
    } else {
      hintEl.textContent = "";
      hintEl.hidden = true;
    }
  };

  const applyPayload = (data) => {
    applyBalanceCard(utilityEl, utilityCurrencyEl, data.utility_currency, data.utility_amount);
    applyBalanceCard(workingEl, workingCurrencyEl, data.working_currency, data.working_amount);
    if (summaryEl) {
      summaryEl.textContent =
        data.summary ||
        (data.ready ? "Waiting for Safaricom…" : "Configure live balance to query Safaricom float.");
    }
    if (whenEl) {
      whenEl.textContent = data.when ? `Updated ${data.when}` : "Tap refresh for live balances";
    }
    if (refreshBtn) refreshBtn.disabled = !data.ready;
    panel.dataset.watch = data.watch ? "1" : "";
    syncTransferPanel(data);
  };

  const poll = async () => {
    if (!pollUrl) return;
    try {
      const response = await fetch(pollUrl, {
        headers: { Accept: "application/json", "X-Requested-With": "XMLHttpRequest" },
      });
      if (!response.ok) return;
      const data = await response.json();
      applyPayload(data);
      if (data.watch) {
        window.setTimeout(poll, 1500);
      } else if (data.queued) {
        setHint("Updating balances…");
      } else {
        setHint("");
      }
    } catch (_err) {
      /* keep last values */
    }
  };

  const requestBalance = async () => {
    if (!requestUrl || !refreshBtn) return;
    refreshBtn.disabled = true;
    setHint("Refreshing…");
    try {
      const body = new URLSearchParams({ intent: "hub-balance" });
      const response = await fetch(requestUrl, {
        method: "POST",
        headers: {
          Accept: "application/json",
          "Content-Type": "application/x-www-form-urlencoded",
          "X-CSRFToken": csrf,
          "X-Requested-With": "XMLHttpRequest",
        },
        body,
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        setHint(data.detail || "Could not request balance.");
        refreshBtn.disabled = false;
        return;
      }
      applyPayload(data);
      panel.dataset.watch = "1";
      window.setTimeout(poll, 800);
    } catch (_err) {
      setHint("Could not reach the server.");
      refreshBtn.disabled = false;
    }
  };

  if (refreshBtn) refreshBtn.addEventListener("click", requestBalance);
  if (autoRefresh && panel.dataset.watch === "1") {
    window.setTimeout(poll, 800);
  } else if (autoRefresh) {
    window.setTimeout(requestBalance, 400);
  }
}

function initUtilityTransfer() {
  const panel = document.querySelector("[data-utility-transfer]");
  const form = panel?.querySelector("[data-utility-transfer-form]");
  if (!panel || !form) return;

  const amountField = form.querySelector("[data-utility-amount]");
  const maxBtn = form.querySelector("[data-utility-max]");
  const submitBtn = form.querySelector("[data-utility-submit]");
  const csrf =
    document.querySelector('meta[name="csrf-token"]')?.getAttribute("content") ||
    form.querySelector('input[name="csrfmiddlewaretoken"]')?.value ||
    "";

  const maxUtility = () => {
    const raw = panel.dataset.maxUtility;
    const value = Number(raw);
    return Number.isFinite(value) && value > 0 ? value : null;
  };

  if (maxBtn && amountField) {
    maxBtn.addEventListener("click", () => {
      const max = maxUtility();
      if (max == null) return;
      amountField.value = String(Math.floor(max));
      amountField.focus();
    });
  }

  form.addEventListener("submit", async (event) => {
    if (!window.fetch || panel.dataset.transferReady !== "1") return;
    event.preventDefault();
    const max = maxUtility();
    const amount = Number(amountField?.value || 0);
    if (!amount || amount < 1) return;
    if (max != null && amount > max) {
      window.alert(`Amount exceeds utility balance of KES ${max.toLocaleString("en-KE")}.`);
      return;
    }
    if (submitBtn) {
      submitBtn.disabled = true;
      submitBtn.textContent = "Transferring…";
    }
    if (maxBtn) maxBtn.disabled = true;
    try {
      const body = new URLSearchParams(new FormData(form));
      const response = await fetch(form.action || window.location.pathname, {
        method: "POST",
        headers: {
          Accept: "application/json",
          "Content-Type": "application/x-www-form-urlencoded",
          "X-CSRFToken": csrf,
          "X-Requested-With": "XMLHttpRequest",
        },
        body,
      });
      const data = await response.json().catch(() => ({}));
      const hubPanel = document.querySelector("[data-hub-balance]");
      if (hubPanel && typeof initHubBalance === "function") {
        const pollUrl = hubPanel.getAttribute("data-poll-url");
        if (pollUrl) {
          const balanceResponse = await fetch(pollUrl, {
            headers: { Accept: "application/json", "X-Requested-With": "XMLHttpRequest" },
          });
          if (balanceResponse.ok) {
            const balanceData = await balanceResponse.json();
            const utilityValue = hubPanel.querySelector("[data-utility-balance]");
            const workingValue = hubPanel.querySelector("[data-working-balance]");
            const utilityCurrency = hubPanel.querySelector("[data-utility-currency]");
            const workingCurrency = hubPanel.querySelector("[data-working-currency]");
            if (utilityValue) {
              utilityValue.textContent =
                balanceData.utility_amount != null
                  ? Number(balanceData.utility_amount).toLocaleString("en-KE", {
                      minimumFractionDigits: 2,
                      maximumFractionDigits: 2,
                    })
                  : "—";
            }
            if (workingValue) {
              workingValue.textContent =
                balanceData.working_amount != null
                  ? Number(balanceData.working_amount).toLocaleString("en-KE", {
                      minimumFractionDigits: 2,
                      maximumFractionDigits: 2,
                    })
                  : "—";
            }
            if (utilityCurrency) utilityCurrency.textContent = balanceData.utility_currency || "KES";
            if (workingCurrency) workingCurrency.textContent = balanceData.working_currency || "KES";
            panel.dataset.maxUtility =
              balanceData.utility_amount != null ? String(balanceData.utility_amount) : "";
          }
        }
        const refreshBtn = hubPanel.querySelector("[data-balance-refresh]");
        refreshBtn?.click();
      }
      if (response.ok) {
        if (amountField) amountField.value = "";
        window.location.reload();
        return;
      }
      window.alert(data.detail || "Transfer failed.");
    } catch (_err) {
      window.alert("Could not reach the server.");
    } finally {
      if (submitBtn) {
        submitBtn.disabled = maxUtility() == null;
        submitBtn.textContent = "Move to working";
      }
      if (maxBtn) maxBtn.disabled = maxUtility() == null;
    }
  });
}

function initAppSettings() {
  const root = document.querySelector("[data-app-settings]");
  if (!root) return;
  const csrf =
    document.querySelector('input[name="csrfmiddlewaretoken"]')?.value ||
    document.querySelector('meta[name="csrf-token"]')?.content ||
    "";

  root.addEventListener("change", async (event) => {
    const input = event.target.closest(".app-settings-toggle");
    if (!input || input.disabled) return;
    const label = input.closest(".perm-switch");
    const url = input.getAttribute("data-toggle-url");
    const setting = input.getAttribute("data-setting");
    if (!url || !setting) return;

    const enabled = input.checked;
    label?.classList.add("is-saving");
    input.disabled = true;

    try {
      const body = new URLSearchParams({
        [setting]: enabled ? "1" : "0",
      });
      const response = await fetch(url, {
        method: "POST",
        headers: {
          "Content-Type": "application/x-www-form-urlencoded",
          "X-Requested-With": "XMLHttpRequest",
          "X-CSRFToken": csrf,
        },
        body,
      });
      if (!response.ok) throw new Error("save failed");
      const data = await response.json();
      input.checked = Boolean(data[setting]);
      if (setting === "app_approval_required" || setting === "stk_pin_approval_required") {
        window.location.reload();
        return;
      }
    } catch (_err) {
      input.checked = !enabled;
    } finally {
      input.disabled = false;
      label?.classList.remove("is-saving");
    }
  });
}

const APPROVAL_DISMISS_KEY = "nexus-approval-dismissed";

let paymentApprovalApi = {
  isActive: () => false,
  beginApprovalFlow: () => {},
};
let approvalBooted = false;

function getApprovalDismissed() {
  try {
    return new Set(JSON.parse(sessionStorage.getItem(APPROVAL_DISMISS_KEY) || "[]"));
  } catch (_err) {
    return new Set();
  }
}

function dismissApprovalNotification(notificationId) {
  if (!notificationId) return;
  const dismissed = getApprovalDismissed();
  dismissed.add(String(notificationId));
  sessionStorage.setItem(APPROVAL_DISMISS_KEY, JSON.stringify([...dismissed]));
}

function isUserInApp() {
  return typeof document !== "undefined" && document.visibilityState === "visible";
}

function updateNotifyCount(count) {
  const btn = document.querySelector(".notify-btn");
  if (!btn) return;
  let badge = btn.querySelector(".notify-count");
  const total = Number(count) || 0;
  if (!total) {
    badge?.remove();
    return;
  }
  if (!badge) {
    badge = document.createElement("span");
    badge.className = "notify-count";
    btn.appendChild(badge);
  }
  badge.textContent = String(total);
}

function parseApprovalConfig() {
  const configEl = document.getElementById("approval-config");
  if (!configEl) return null;
  try {
    return JSON.parse(configEl.textContent || "{}");
  } catch (_err) {
    return null;
  }
}

function approvalChannels(config) {
  return {
    app: Boolean(config?.app || config?.hubApp),
    stk: Boolean(config?.stk || config?.hubStk),
  };
}

function approvalRequired(config) {
  const channels = approvalChannels(config);
  return channels.app || channels.stk;
}

function appChannelReady(config, channels) {
  return Boolean(channels?.app && config?.hasApprovalPassword !== false);
}

function stkChannelReady(config, channels) {
  return Boolean(channels?.stk && config?.hasPhone !== false);
}

function showDialog(el) {
  if (!el) return;
  el.removeAttribute("hidden");
}

function hideDialog(el) {
  if (!el) return;
  el.hidden = true;
}

function formatRelativeTime(isoOrLabel) {
  if (!isoOrLabel) return "";
  if (typeof isoOrLabel === "string" && !isoOrLabel.includes("T")) return isoOrLabel;
  const then = new Date(isoOrLabel).getTime();
  if (Number.isNaN(then)) return "";
  const mins = Math.max(1, Math.floor((Date.now() - then) / 60000));
  if (mins < 60) return `${mins} min ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 48) return `${hours} hour${hours === 1 ? "" : "s"} ago`;
  const days = Math.floor(hours / 24);
  return `${days} day${days === 1 ? "" : "s"} ago`;
}

function renderNotificationList(config, notifications, csrf) {
  const list = document.querySelector("[data-notify-list]");
  if (!list) return;

  const items = Array.isArray(notifications) ? notifications : [];
  list.replaceChildren();

  if (!items.length) {
    const empty = document.createElement("p");
    empty.className = "notify-empty";
    empty.textContent = "No notifications yet.";
    list.appendChild(empty);
    return;
  }

  const next = `${window.location.pathname}${window.location.search}`;
  const needsApproval = approvalRequired(config);

  items.forEach((note) => {
    const article = document.createElement("article");
    article.className = `notify-item${note.is_read ? "" : " is-unread"}`;

    const copy = document.createElement("div");
    copy.className = "notify-copy";
    const title = document.createElement("strong");
    title.textContent = note.title || "Notification";
    copy.appendChild(title);
    if (note.body) {
      const body = document.createElement("p");
      body.textContent = note.body;
      copy.appendChild(body);
    }
    const when = document.createElement("small");
    when.textContent = note.created_ago || formatRelativeTime(note.created_at);
    copy.appendChild(when);

    const actions = document.createElement("div");
    actions.className = "notify-actions";

    const openForm = document.createElement("form");
    openForm.method = "post";
    openForm.action = note.open_url;
    openForm.className = "inline-form";
    openForm.innerHTML = `
      <input type="hidden" name="csrfmiddlewaretoken" value="${csrf}">
      <button type="submit" class="btn btn-ghost btn-small">Open</button>
    `;
    actions.appendChild(openForm);

    if (note.can_review) {
      const approveForm = document.createElement("form");
      approveForm.method = "post";
      approveForm.action = note.review_url;
      approveForm.className = "inline-form";
      approveForm.setAttribute("data-approval-form", "");
      approveForm.setAttribute("data-notification-id", String(note.id));
      if (note.money_request_id) {
        approveForm.setAttribute("data-money-request-id", String(note.money_request_id));
      }
      approveForm.setAttribute("data-approval-title", note.title || "");
      approveForm.setAttribute("data-approval-body", note.body || "");
      approveForm.innerHTML = `
        <input type="hidden" name="csrfmiddlewaretoken" value="${csrf}">
        <input type="hidden" name="intent" value="approve">
        <input type="hidden" name="next" value="${next}">
      `;
      const approveBtn = document.createElement("button");
      approveBtn.type = needsApproval ? "button" : "submit";
      approveBtn.className = "btn btn-primary btn-small";
      approveBtn.textContent = "Approve & send";
      if (needsApproval) approveBtn.setAttribute("data-approval-trigger", "");
      approveForm.appendChild(approveBtn);
      actions.appendChild(approveForm);

      const rejectForm = document.createElement("form");
      rejectForm.method = "post";
      rejectForm.action = note.review_url;
      rejectForm.className = "inline-form";
      rejectForm.innerHTML = `
        <input type="hidden" name="csrfmiddlewaretoken" value="${csrf}">
        <input type="hidden" name="intent" value="reject">
        <input type="hidden" name="next" value="${next}">
        <button type="submit" class="btn btn-ghost btn-small">Reject</button>
      `;
      actions.appendChild(rejectForm);
    }

    article.append(copy, actions);
    list.appendChild(article);
  });
}

function initPaymentApproval(config) {
  if (!config) return null;

  const channels = approvalChannels(config);
  if (!approvalRequired(config)) return null;

  const csrf =
    document.querySelector('input[name="csrfmiddlewaretoken"]')?.value ||
    document.querySelector('meta[name="csrf-token"]')?.content ||
    "";

  const appBackdrop = document.querySelector("[data-pin-approval-backdrop]");
  const appInput = document.querySelector("[data-pin-approval-input]");
  const appErrorEl = document.querySelector("[data-pin-approval-error]");
  const appSetupEl = document.querySelector("[data-pin-approval-setup]");
  const appPhoneSetupEl = document.querySelector("[data-pin-approval-phone-setup]");
  const appUseStkBtn = document.querySelector("[data-pin-approval-use-stk]");
  const appSubmitBtn = document.querySelector("[data-pin-approval-submit]");
  const appCancelBtn = document.querySelector("[data-pin-approval-cancel]");

  const stkBackdrop = document.querySelector("[data-stk-approval-backdrop]");
  const stkMessageEl = document.querySelector("[data-stk-approval-message]");
  const stkStatusEl = document.querySelector("[data-stk-approval-status]");
  const stkErrorEl = document.querySelector("[data-stk-approval-error]");
  const stkCancelBtns = document.querySelectorAll("[data-stk-approval-cancel]");

  let pendingForm = null;
  let approvalPin = "";
  let pollTimer = null;
  let approvalActive = false;

  const setApprovalContext = (form) => {
    const title = form.getAttribute("data-approval-title") || "";
    const body = form.getAttribute("data-approval-body") || "";
    const detail = [title, body].filter(Boolean).join(" · ");
    const appDetail = document.querySelector("[data-pin-approval-detail]");
    if (appDetail) {
      appDetail.textContent = detail;
      appDetail.hidden = !detail;
    }
    const stkDetail = document.querySelector("[data-stk-approval-detail]");
    if (stkDetail) {
      stkDetail.textContent = detail;
      stkDetail.hidden = !detail;
    }
  };

  const closeAppDialog = () => {
    if (appInput) {
      appInput.value = "";
      appInput.disabled = false;
    }
    if (appSubmitBtn) appSubmitBtn.disabled = false;
    if (appErrorEl) appErrorEl.hidden = true;
    if (appSetupEl) appSetupEl.hidden = true;
    if (appPhoneSetupEl) appPhoneSetupEl.hidden = true;
    if (appUseStkBtn) appUseStkBtn.hidden = true;
    hideDialog(appBackdrop);
  };

  const closeStkDialog = () => {
    if (pollTimer) {
      window.clearInterval(pollTimer);
      pollTimer = null;
    }
    if (stkErrorEl) {
      stkErrorEl.hidden = true;
      stkErrorEl.textContent = "";
    }
    if (stkStatusEl) stkStatusEl.textContent = "Waiting for M-Pesa…";
    hideDialog(stkBackdrop);
  };

  const resetFlow = () => {
    approvalActive = false;
    pendingForm = null;
    approvalPin = "";
    closeAppDialog();
    closeStkDialog();
  };

  const cancelFlow = () => {
    const notificationId = pendingForm?.getAttribute("data-notification-id");
    if (notificationId) dismissApprovalNotification(notificationId);
    resetFlow();
  };

  const submitForm = async (form, stkOperationId = "") => {
    if (approvalPin) {
      let hidden = form.querySelector('input[name="approval_pin"]');
      if (!hidden) {
        hidden = document.createElement("input");
        hidden.type = "hidden";
        hidden.name = "approval_pin";
        form.appendChild(hidden);
      }
      hidden.value = approvalPin;
    }
    if (stkOperationId) {
      let hidden = form.querySelector('input[name="stk_approval_operation_id"]');
      if (!hidden) {
        hidden = document.createElement("input");
        hidden.type = "hidden";
        hidden.name = "stk_approval_operation_id";
        form.appendChild(hidden);
      }
      hidden.value = stkOperationId;
    }
    const target = form;
    resetFlow();

    if (window.fetch && target.action) {
      const submitBtn = target.querySelector("button[type='submit'], button[data-approval-trigger]");
      const originalLabel = submitBtn?.textContent;
      if (submitBtn) {
        submitBtn.disabled = true;
        submitBtn.textContent = "Processing…";
      }
      try {
        const response = await fetch(target.action, {
          method: "POST",
          body: new FormData(target),
          headers: { "X-Requested-With": "XMLHttpRequest" },
          credentials: "same-origin",
        });
        const data = await response.json().catch(() => null);
        if (response.ok && data?.redirect) {
          window.location.assign(data.redirect);
          return;
        }
      } catch (_err) {
        /* fall back to a normal form post */
      } finally {
        if (submitBtn) {
          submitBtn.disabled = false;
          if (originalLabel) submitBtn.textContent = originalLabel;
        }
      }
    }

    target.submit();
  };

  const pollStkApproval = (form, operationId) =>
    new Promise((resolve, reject) => {
      if (!config.stkPollUrl) {
        reject(new Error("Missing poll URL."));
        return;
      }
      const pollUrl = `${config.stkPollUrl}${operationId}/`;
      const finish = (ok, message) => {
        if (pollTimer) {
          window.clearInterval(pollTimer);
          pollTimer = null;
        }
        if (ok) resolve(operationId);
        else reject(new Error(message || "PIN approval failed."));
      };

      const tick = async () => {
        try {
          const response = await fetch(pollUrl, {
            headers: { "X-Requested-With": "XMLHttpRequest" },
          });
          if (!response.ok) throw new Error("Could not check STK status.");
          const data = await response.json();
          if (stkStatusEl) stkStatusEl.textContent = data.summary || "Waiting for M-Pesa…";
          if (data.complete) finish(Boolean(data.success), data.summary);
        } catch (err) {
          finish(false, err.message);
        }
      };

      tick();
      pollTimer = window.setInterval(tick, 2500);
    });

  const chooseApprovalChannel = ({ manual = false } = {}) => {
    const appReady = appChannelReady(config, channels);
    const stkReady = stkChannelReady(config, channels);

    if (manual || isUserInApp()) {
      if (appReady) return "app";
      if (stkReady) return "stk";
      if (channels.app && !appReady && stkReady) return "stk";
      if (channels.stk && !stkReady && appReady) return "app";
      if (channels.stk) return "stk";
      if (channels.app) return "app";
      return "none";
    }
    if (stkReady) return "stk";
    if (appReady) return "app";
    if (channels.stk) return "stk";
    if (channels.app) return "app";
    return "none";
  };

  const runStkApproval = async (form, { silent = false } = {}) => {
    const moneyRequestId = form.getAttribute("data-money-request-id");
    if (!moneyRequestId) {
      window.alert("This approval form is missing the money request id.");
      resetFlow();
      return;
    }
    if (!config.stkInitiateUrl) {
      window.alert("STK approval is not configured.");
      resetFlow();
      return;
    }

    setApprovalContext(form);
    if (!silent) showDialog(stkBackdrop);
    else hideDialog(stkBackdrop);
    if (stkMessageEl) {
      stkMessageEl.textContent =
        "Sending an STK prompt to your phone. Enter your M-Pesa PIN when it arrives.";
    }
    if (stkStatusEl) stkStatusEl.textContent = "Sending STK prompt…";

    try {
      const body = new URLSearchParams({ money_request_id: moneyRequestId });
      const response = await fetch(config.stkInitiateUrl, {
        method: "POST",
        headers: {
          "Content-Type": "application/x-www-form-urlencoded",
          "X-Requested-With": "XMLHttpRequest",
          "X-CSRFToken": csrf,
        },
        body,
      });
      const data = await response.json();
      if (!response.ok || !data.ok) throw new Error(data.detail || "Could not send STK prompt.");
      if (stkMessageEl) {
        stkMessageEl.textContent =
          data.summary || "Check your phone and enter your M-Pesa PIN to approve this payment.";
      }
      if (stkStatusEl) stkStatusEl.textContent = "Waiting for M-Pesa PIN…";
      const operationId = await pollStkApproval(form, data.operation_id);
      submitForm(form, operationId);
    } catch (err) {
      if (stkErrorEl) {
        stkErrorEl.textContent = err.message || "PIN approval failed.";
        stkErrorEl.hidden = false;
      }
      if (stkStatusEl) stkStatusEl.textContent = "STK prompt not completed.";
      resetFlow();
    }
  };

  const openAppDialog = (form) => {
    if (!appBackdrop || !appInput) {
      window.alert("Approval password prompt is not available on this page.");
      resetFlow();
      return;
    }
    pendingForm = form;
    setApprovalContext(form);
    appInput.value = "";
    if (appErrorEl) appErrorEl.hidden = true;
    const needsPassword = config.hasApprovalPassword === false;
    const needsPhone = config.hasPhone === false;
    if (appSetupEl) appSetupEl.hidden = !needsPassword;
    if (appPhoneSetupEl) {
      appPhoneSetupEl.hidden = !(needsPhone && channels.stk && !needsPassword);
    }
    const showStkAlt = Boolean(
      channels.stk &&
        config.hasPhone !== false &&
        (config.dualApproval || needsPassword),
    );
    if (appUseStkBtn) appUseStkBtn.hidden = !showStkAlt;
    if (needsPassword) {
      appInput.disabled = true;
      if (appSubmitBtn) appSubmitBtn.disabled = true;
    } else {
      appInput.disabled = false;
      if (appSubmitBtn) appSubmitBtn.disabled = false;
    }
    showDialog(appBackdrop);
    if (!needsPassword) {
      window.requestAnimationFrame(() => appInput.focus());
    }
  };

  const beginApprovalFlow = (form, { force = false, manual = false } = {}) => {
    if (approvalActive && !force) return;
    approvalActive = true;
    pendingForm = form;
    approvalPin = "";
    const channel = chooseApprovalChannel({ manual });
    if (channel === "app") {
      if (!manual && !isUserInApp()) {
        if (stkChannelReady(config, channels)) {
          runStkApproval(form, { silent: true });
          return;
        }
        approvalActive = false;
        pendingForm = null;
        return;
      }
      if (!appChannelReady(config, channels) && stkChannelReady(config, channels)) {
        runStkApproval(form, { silent: false });
        return;
      }
      openAppDialog(form);
      return;
    }
    if (channel === "stk") {
      runStkApproval(form, { silent: !manual && !isUserInApp() });
      return;
    }
    submitForm(form);
  };

  paymentApprovalApi = {
    isActive: () => approvalActive,
    beginApprovalFlow,
  };

  const continueApproval = (form) => {
    submitForm(form);
  };

  const submitAppApproval = () => {
    if (!pendingForm || !appInput) return;
    if (config.hasApprovalPassword === false) {
      if (stkChannelReady(config, channels)) {
        runStkApproval(pendingForm, { silent: false });
        return;
      }
      if (appSetupEl) appSetupEl.hidden = false;
      return;
    }
    const pin = appInput.value.replace(/\D/g, "").slice(0, 6);
    if (pin.length !== 6) {
      if (appErrorEl) appErrorEl.hidden = false;
      appInput.focus();
      return;
    }
    approvalPin = pin;
    const form = pendingForm;
    closeAppDialog();
    continueApproval(form);
  };

  const handleApproveForm = (form, event) => {
    if (!(form instanceof HTMLFormElement) || !form.hasAttribute("data-approval-form")) return;
    if (!approvalRequired(config)) return;
    event?.preventDefault();
    event?.stopPropagation();
    beginApprovalFlow(form, { force: true, manual: true });
  };

  document.addEventListener(
    "click",
    (event) => {
      const btn = event.target.closest("[data-approval-trigger], form[data-approval-form] button[type='submit']");
      if (!btn) return;
      const form = btn.closest("form[data-approval-form]");
      if (!form) return;
      handleApproveForm(form, event);
    },
    true,
  );

  document.addEventListener(
    "submit",
    (event) => {
      handleApproveForm(event.target, event);
    },
    true,
  );

  appSubmitBtn?.addEventListener("click", submitAppApproval);
  appUseStkBtn?.addEventListener("click", () => {
    if (!pendingForm) return;
    const form = pendingForm;
    closeAppDialog();
    approvalActive = true;
    pendingForm = form;
    runStkApproval(form, { silent: false });
  });
  appCancelBtn?.addEventListener("click", cancelFlow);
  appBackdrop?.addEventListener("click", (event) => {
    if (event.target === appBackdrop) cancelFlow();
  });
  appInput?.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      event.preventDefault();
      submitAppApproval();
    }
    if (event.key === "Escape") cancelFlow();
  });
  stkCancelBtns.forEach((btn) => btn.addEventListener("click", cancelFlow));
  stkBackdrop?.addEventListener("click", (event) => {
    if (event.target === stkBackdrop) cancelFlow();
  });

  return { config, csrf, beginApprovalFlow, isActive: () => approvalActive };
}

function initApprovalLiveCheck(config, approvalRuntime = null) {
  if (!config?.pendingPollUrl) return;

  const csrf =
    document.querySelector('meta[name="csrf-token"]')?.content ||
    document.querySelector('input[name="csrfmiddlewaretoken"]')?.value ||
    "";

  const beginApprovalFlow =
    approvalRuntime?.beginApprovalFlow || paymentApprovalApi.beginApprovalFlow;
  const isApprovalActive = approvalRuntime?.isActive || paymentApprovalApi.isActive;

  const buildApprovalForm = (item) => {
    const existing = document.querySelector(`[data-auto-approval-id="${item.notification_id}"]`);
    if (existing instanceof HTMLFormElement) return existing;

    const form = document.createElement("form");
    form.method = "post";
    form.action = item.review_url;
    form.hidden = true;
    form.setAttribute("data-approval-form", "");
    form.setAttribute("data-money-request-id", String(item.money_request_id));
    form.setAttribute("data-notification-id", String(item.notification_id));
    form.setAttribute("data-approval-title", item.title || "");
    form.setAttribute("data-approval-body", item.body || "");
    form.setAttribute("data-auto-approval-id", String(item.notification_id));

    const next = `${window.location.pathname}${window.location.search}`;
    form.innerHTML = `
      <input type="hidden" name="csrfmiddlewaretoken" value="${csrf}">
      <input type="hidden" name="intent" value="approve">
      <input type="hidden" name="next" value="${next}">
    `;
    document.body.appendChild(form);
    return form;
  };

  let pollTimer = null;
  const pollDelay = () =>
    isUserInApp()
      ? Number(config.pollIntervalMs) || 3000
      : Number(config.pollIntervalHiddenMs) || 12000;

  const schedulePoll = () => {
    if (pollTimer) window.clearInterval(pollTimer);
    pollTimer = window.setInterval(tick, pollDelay());
  };

  const tick = async () => {
    if (isApprovalActive()) return;
    try {
      const response = await fetch(config.pendingPollUrl, {
        headers: { "X-Requested-With": "XMLHttpRequest" },
        credentials: "same-origin",
      });
      if (!response.ok) return;
      const data = await response.json();
      if (!data.ok) return;

      updateNotifyCount(data.unread_count || 0);
      renderNotificationList(config, data.notifications, csrf);

      if (!config.autoPrompt || !approvalRequired(config)) return;

      const dismissed = getApprovalDismissed();
      const pending = Array.isArray(data.pending) ? data.pending : [];
      const item =
        pending.find(
          (row) => row.is_unread !== false && !dismissed.has(String(row.notification_id)),
        ) || pending.find((row) => !dismissed.has(String(row.notification_id)));
      if (!item) return;

      const form = buildApprovalForm(item);
      beginApprovalFlow(form);
    } catch (_err) {
      // Ignore transient network errors during background polling.
    }
  };

  tick();
  schedulePoll();
  document.addEventListener("visibilitychange", () => {
    schedulePoll();
    if (document.visibilityState === "visible") tick();
  });
}

function initReviewApproval() {
  if (approvalBooted) return;
  const config = parseApprovalConfig();
  if (!config) return;
  approvalBooted = true;
  const runtime = initPaymentApproval(config);
  initApprovalLiveCheck(config, runtime);
  window.nexusApproval = {
    ready: true,
    config,
    beginApprovalFlow: runtime?.beginApprovalFlow || paymentApprovalApi.beginApprovalFlow,
    triggerFromButton(button, event) {
      const form = button?.closest?.("form[data-approval-form]");
      if (!form) return;
      event?.preventDefault?.();
      event?.stopPropagation?.();
      (runtime?.beginApprovalFlow || paymentApprovalApi.beginApprovalFlow)(form, {
        force: true,
        manual: true,
      });
    },
  };
}

function initEmployeePermissions() {
  const root = document.querySelector("[data-employee-permissions]");
  if (!root) return;
  const csrf =
    document.querySelector('input[name="csrfmiddlewaretoken"]')?.value ||
    document.querySelector('meta[name="csrf-token"]')?.content ||
    "";

  root.addEventListener("change", async (event) => {
    const input = event.target.closest(".perm-switch-input");
    if (!input || input.disabled) return;
    const label = input.closest(".perm-switch");
    const url = input.getAttribute("data-toggle-url");
    const activity = input.getAttribute("data-activity");
    if (!url || !activity) return;

    const enabled = input.checked;
    label?.classList.add("is-saving");
    input.disabled = true;

    try {
      const body = new URLSearchParams({
        activity,
        enabled: enabled ? "1" : "0",
      });
      const response = await fetch(url, {
        method: "POST",
        headers: {
          "Content-Type": "application/x-www-form-urlencoded",
          "X-Requested-With": "XMLHttpRequest",
          "X-CSRFToken": csrf,
        },
        body,
      });
      if (!response.ok) throw new Error("save failed");
      const data = await response.json();
      input.checked = Boolean(data.enabled);
    } catch (_err) {
      input.checked = !enabled;
    } finally {
      input.disabled = false;
      label?.classList.remove("is-saving");
    }
  });
}

function runShellInits() {
  initReviewApproval();
  const secondaryInits = [
    initDarajaSetup,
    initDarajaTests,
    initHubBalance,
    initUtilityTransfer,
    initWebPush,
    initEmployeePermissions,
    initAppSettings,
  ];
  secondaryInits.forEach((initFn) => {
    try {
      initFn();
    } catch (_err) {
      /* non-critical page widgets */
    }
  });
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", runShellInits);
} else {
  runShellInits();
}

function initWebPush() {
  const configEl = document.getElementById("webpush-config");
  const keyEl = document.getElementById("webpush-vapid-key");
  const enableBtn = document.querySelector("[data-webpush-enable]");
  if (!configEl || !keyEl || !("serviceWorker" in navigator) || !("PushManager" in window)) {
    if (enableBtn) {
      enableBtn.disabled = true;
      enableBtn.textContent = "Phone alerts unsupported";
    }
    return;
  }

  let config = {};
  try {
    config = JSON.parse(configEl.textContent || "{}");
  } catch (_err) {
    return;
  }
  let vapidKey = "";
  try {
    vapidKey = JSON.parse(keyEl.textContent || '""');
  } catch (_err) {
    return;
  }
  if (!config.subscribeUrl || !config.swUrl || !vapidKey) return;

  const csrf =
    document.querySelector('meta[name="csrf-token"]')?.getAttribute("content") ||
    document.querySelector('input[name="csrfmiddlewaretoken"]')?.value ||
    "";

  const urlBase64ToUint8Array = (base64String) => {
    const padding = "=".repeat((4 - (base64String.length % 4)) % 4);
    const base64 = (base64String + padding).replace(/-/g, "+").replace(/_/g, "/");
    const raw = window.atob(base64);
    const output = new Uint8Array(raw.length);
    for (let i = 0; i < raw.length; i += 1) output[i] = raw.charCodeAt(i);
    return output;
  };

  const syncLabel = async () => {
    if (!enableBtn) return;
    try {
      const reg = await navigator.serviceWorker.getRegistration(config.swUrl);
      const sub = reg && (await reg.pushManager.getSubscription());
      if (Notification.permission === "granted" && sub) {
        enableBtn.textContent = "Phone alerts on";
        enableBtn.classList.add("is-on");
      } else if (Notification.permission === "denied") {
        enableBtn.textContent = "Alerts blocked";
        enableBtn.disabled = true;
      } else {
        enableBtn.textContent = "Enable phone alerts";
        enableBtn.classList.remove("is-on");
      }
    } catch (_err) {
      /* leave default label */
    }
  };

  const postSubscription = async (sub) => {
    const response = await fetch(config.subscribeUrl, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "application/json",
        "X-CSRFToken": csrf,
        "X-Requested-With": "XMLHttpRequest",
      },
      body: JSON.stringify(sub.toJSON()),
      credentials: "same-origin",
    });
    if (!response.ok) throw new Error("Subscribe failed");
  };

  const bindExistingSubscription = async () => {
    // Re-attach an existing browser push endpoint to the current session user
    // so shared devices do not keep delivering another employee's alerts.
    if (Notification.permission !== "granted") return;
    try {
      const reg = await navigator.serviceWorker.getRegistration(config.swUrl);
      const sub = reg && (await reg.pushManager.getSubscription());
      if (sub) await postSubscription(sub);
    } catch (_err) {
      /* ignore bind failures; user can re-enable manually */
    }
  };

  const subscribe = async () => {
    const permission = await Notification.requestPermission();
    if (permission !== "granted") {
      if (enableBtn) enableBtn.textContent = "Permission needed";
      return;
    }
    const reg = await navigator.serviceWorker.register(config.swUrl, { scope: "/" });
    await navigator.serviceWorker.ready;
    let sub = await reg.pushManager.getSubscription();
    if (!sub) {
      sub = await reg.pushManager.subscribe({
        userVisibleOnly: true,
        applicationServerKey: urlBase64ToUint8Array(vapidKey),
      });
    }
    await postSubscription(sub);
    await syncLabel();
  };

  navigator.serviceWorker.register(config.swUrl, { scope: "/" }).catch(() => {});
  bindExistingSubscription().finally(syncLabel);
  if (enableBtn) {
    enableBtn.addEventListener("click", async () => {
      enableBtn.disabled = true;
      enableBtn.textContent = "Enabling…";
      try {
        await subscribe();
      } catch (_err) {
        enableBtn.textContent = "Enable failed";
      } finally {
        enableBtn.disabled = false;
        syncLabel();
      }
    });
  }
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
