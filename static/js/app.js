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

function initAutomations() {
  const board = document.querySelector("[data-automations]");
  const page = document.querySelector(".automations-page");
  if (!board && !page) return;
  const copyRoot = page || board;
  if (!board) {
    page?.querySelectorAll("[data-copy-text], [data-copy-target]").forEach((btn) => {
      btn.addEventListener("click", async () => {
        let text = btn.getAttribute("data-copy-text") || "";
        if (!text) {
          const id = btn.getAttribute("data-copy-target");
          const el = id ? document.getElementById(id) : null;
          if (el instanceof HTMLTextAreaElement || el instanceof HTMLInputElement) {
            text = el.value?.trim() || "";
          } else {
            text = el?.textContent?.trim() || "";
          }
        }
        if (!text) return;
        try {
          await navigator.clipboard.writeText(text);
          const prev = btn.textContent;
          btn.textContent = "Copied";
          window.setTimeout(() => {
            btn.textContent = prev;
          }, 1600);
        } catch (_err) {
          /* ignore */
        }
      });
    });
    return;
  }

  const pollUrl = board.getAttribute("data-poll-url");
  const postUrl = board.getAttribute("data-post-url");
  const balanceReady = board.getAttribute("data-balance-ready") === "1";
  const tbody = board.querySelector("[data-automations-rows]");
  const hintEl = board.querySelector("[data-automations-hint]");
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

  const applyRow = (row, data) => {
    const tr = tbody?.querySelector(`[data-monitor-id="${data.id}"]`);
    if (!tr) return;
    tr.dataset.watch = data.balance_watch ? "1" : "";
    tr.dataset.autoRefresh = data.auto_refresh ? "1" : "";
    const set = (col, html) => {
      const cell = tr.querySelector(`[data-col="${col}"]`);
      if (cell) cell.innerHTML = html;
    };
    set("label", data.label);
    const codeEl = tr.querySelector('[data-col="code"]');
    if (codeEl && data.collection_code) codeEl.textContent = data.collection_code;
    const copyBtn = tr.querySelector("[data-copy-text]");
    if (copyBtn && data.collection_code) copyBtn.setAttribute("data-copy-text", data.collection_code);
    const typeEl = tr.querySelector('[data-col="type"]');
    if (typeEl) typeEl.textContent = data.account_type_label || "";
    let idHtml = data.identifier;
    if (data.account_ref) {
      idHtml += ` <span class="muted"> · ac ${data.account_ref}</span>`;
    }
    set("identifier", idHtml);
    set("collected", `KES ${formatAmount(data.collected_total)}`);
    if (data.live_amount != null) {
      set("live", `${data.live_currency || "KES"} ${formatAmount(data.live_amount)}`);
    } else {
      set("live", "—");
    }
    set("when", data.balance_when || "—");
  };

  const anyWatching = () => Boolean(tbody?.querySelector('[data-watch="1"]'));

  const poll = async () => {
    if (!pollUrl) return;
    try {
      const response = await fetch(pollUrl, {
        headers: { Accept: "application/json", "X-Requested-With": "XMLHttpRequest" },
      });
      if (!response.ok) return;
      const payload = await response.json();
      (payload.accounts || []).forEach((row) => applyRow(row, row));
      if (anyWatching()) {
        window.setTimeout(poll, 1500);
      } else if (hintEl && payload.balance_ready) {
        hintEl.textContent = "Balances are up to date.";
      }
    } catch (_err) {
      /* keep last values */
    }
  };

  const postIntent = async (body) => {
    const response = await fetch(postUrl, {
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
    return { response, data };
  };

  board.addEventListener("submit", async (event) => {
    const form = event.target;
    if (!(form instanceof HTMLFormElement) || !board.contains(form)) return;
    const intentInput = form.querySelector('input[name="intent"]');
    const intent = intentInput?.value;
    if (intent !== "refresh" && intent !== "refresh-all") return;
    event.preventDefault();
    if (!balanceReady) return;
    const body = new URLSearchParams(new FormData(form));
    if (hintEl) hintEl.textContent = "Requesting live balance from Safaricom…";
    const { response, data } = await postIntent(body);
    if (!response.ok) {
      if (hintEl) hintEl.textContent = data.detail || "Could not refresh balance.";
      return;
    }
    (data.accounts || []).forEach((row) => applyRow(row, row));
    if (hintEl) {
      hintEl.textContent = data.refreshed
        ? "Waiting for Safaricom callbacks…"
        : "Refresh sent.";
    }
    poll();
  });

  if (anyWatching()) poll();

  window.setInterval(async () => {
    if (!balanceReady || !postUrl) return;
    const autoRows = tbody?.querySelectorAll('[data-auto-refresh="1"]');
    if (!autoRows?.length) return;
    if (anyWatching()) return;
    const body = new URLSearchParams({ intent: "refresh-all" });
    body.append("csrfmiddlewaretoken", csrf);
    try {
      await postIntent(body);
      poll();
    } catch (_err) {
      /* ignore background refresh errors */
    }
  }, 30000);

  copyRoot.querySelectorAll("[data-copy-text], [data-copy-target]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      let text = btn.getAttribute("data-copy-text") || "";
      if (!text) {
        const id = btn.getAttribute("data-copy-target");
        const el = id ? document.getElementById(id) : null;
        if (el instanceof HTMLTextAreaElement || el instanceof HTMLInputElement) {
          text = el.value?.trim() || "";
        } else {
          text = el?.textContent?.trim() || "";
        }
      }
      if (!text) return;
      try {
        await navigator.clipboard.writeText(text);
        const prev = btn.textContent;
        btn.textContent = "Copied";
        window.setTimeout(() => {
          btn.textContent = prev;
        }, 1600);
      } catch (_err) {
        /* ignore */
      }
    });
  });

  poll();
}

function initAutomationAccountPage() {
  const page = document.querySelector(".automations-page-account");
  if (!page) return;

  const csrf =
    document.querySelector('meta[name="csrf-token"]')?.getAttribute("content") ||
    document.querySelector('input[name="csrfmiddlewaretoken"]')?.value ||
    document.cookie.match(/csrftoken=([^;]+)/)?.[1] ||
    "";

  const ledgerSection = page.querySelector("[data-automation-ledger]");
  const ledgerApiUrl = ledgerSection?.getAttribute("data-ledger-api-url") || "";
  const ledgerSearch = ledgerSection?.querySelector("[data-ledger-search]");
  const ledgerTbody = ledgerSection?.querySelector("[data-ledger-tbody]");
  const ledgerHint = ledgerSection?.querySelector("[data-ledger-hint]");
  const ledgerPagination = ledgerSection?.querySelector("[data-ledger-pagination]");
  const ledgerPrev = ledgerSection?.querySelector("[data-ledger-prev]");
  const ledgerNext = ledgerSection?.querySelector("[data-ledger-next]");
  const ledgerPageLabel = ledgerSection?.querySelector("[data-ledger-page-label]");
  const totalIn = ledgerSection?.querySelector("[data-ledger-total-in]");
  const totalOut = ledgerSection?.querySelector("[data-ledger-total-out]");
  const totalNet = ledgerSection?.querySelector("[data-ledger-total-net]");

  const waitBackdrop = page.querySelector("[data-daraja-wait-backdrop]");
  const waitStatus = page.querySelector("[data-daraja-wait-status]");
  const waitDetail = page.querySelector("[data-daraja-wait-detail]");
  const waitClose = page.querySelector("[data-daraja-wait-close]");

  const escapeHtml = (value) =>
    String(value ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");

  const formatKes = (raw) => {
    const value = Number(raw);
    if (!Number.isFinite(value)) return "—";
    return value.toLocaleString("en-KE", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  };

  const badge = (status, label) =>
    `<span class="badge badge-${escapeHtml(String(status || "").toLowerCase())}">${escapeHtml(label || status)}</span>`;

  const renderLedgerRow = (row) => {
    const dirClass = row.direction === "IN" ? "ledger-dir-in" : "ledger-dir-out";
    const mpesaCell = row.mpesa_reference
      ? `<code class="mono">${escapeHtml(row.mpesa_reference)}</code>`
      : `<span class="muted">${escapeHtml(row.reference.slice(0, 18))}${row.reference.length > 18 ? "…" : ""}</span>`;
    const amountSign = row.direction === "IN" ? "+" : "−";
    return `<tr>
      <td data-label="When">${escapeHtml(row.when)}</td>
      <td data-label="Direction"><span class="ledger-dir ${dirClass}">${escapeHtml(row.direction_label)}</span></td>
      <td data-label="M-Pesa ref">${mpesaCell}</td>
      <td data-label="Party">${escapeHtml(row.party)}</td>
      <td data-label="Ref"><code>${escapeHtml(row.account_ref)}</code></td>
      <td data-label="Amount" class="automation-ledger-amount">
        <span class="${escapeHtml(row.amount_class)}">${amountSign} ${escapeHtml(row.currency)} ${escapeHtml(row.amount)}</span>
      </td>
      <td data-label="Status">${badge(row.status, row.status_label)}</td>
      <td data-label="Narrative" class="automation-ledger-narrative">${escapeHtml(row.narrative)}</td>
    </tr>`;
  };

  let ledgerQuery = "";
  let ledgerPage = 1;
  let ledgerPollTimer = null;
  let ledgerFetchInFlight = false;

  const applyLedgerPayload = (data) => {
    if (!ledgerTbody || !data) return;
    const rows = data.entries || [];
    ledgerTbody.innerHTML = rows.length
      ? rows.map(renderLedgerRow).join("")
      : `<tr><td colspan="8" class="empty">No matching transactions.</td></tr>`;
    if (totalIn && data.totals) totalIn.textContent = `KES ${formatKes(data.totals.inbound)}`;
    if (totalOut && data.totals) totalOut.textContent = `KES ${formatKes(data.totals.outbound)}`;
    if (totalNet && data.totals) totalNet.textContent = `KES ${formatKes(data.totals.net)}`;
    if (ledgerPageLabel) {
      ledgerPageLabel.textContent = `Page ${data.page} of ${Math.max(data.num_pages || 1, 1)}`;
    }
    if (ledgerPagination) {
      ledgerPagination.hidden = (data.num_pages || 1) <= 1;
    }
    if (ledgerPrev) ledgerPrev.disabled = !data.has_previous;
    if (ledgerNext) ledgerNext.disabled = !data.has_next;
    ledgerPage = data.page || 1;
    if (ledgerHint) {
      const q = (data.query || "").trim();
      ledgerHint.textContent = q
        ? `${data.count} match${data.count === 1 ? "" : "es"} · live updates`
        : "Updates live — no refresh needed.";
    }
  };

  const fetchLedger = async () => {
    if (!ledgerApiUrl || !ledgerTbody || ledgerFetchInFlight) return;
    ledgerFetchInFlight = true;
    try {
      const params = new URLSearchParams({ poll: "ledger", page: String(ledgerPage) });
      if (ledgerQuery) params.set("q", ledgerQuery);
      const response = await fetch(`${ledgerApiUrl}?${params}`, {
        headers: { Accept: "application/json", "X-Requested-With": "XMLHttpRequest" },
        cache: "no-store",
      });
      if (!response.ok) return;
      const data = await response.json();
      applyLedgerPayload(data);
    } catch (_err) {
      /* keep table */
    } finally {
      ledgerFetchInFlight = false;
    }
  };

  const scheduleLedgerPoll = () => {
    if (ledgerPollTimer) window.clearInterval(ledgerPollTimer);
    ledgerPollTimer = window.setInterval(fetchLedger, 5000);
  };

  if (ledgerSearch) {
    let debounce = null;
    ledgerSearch.addEventListener("input", () => {
      window.clearTimeout(debounce);
      debounce = window.setTimeout(() => {
        ledgerQuery = ledgerSearch.value.trim();
        ledgerPage = 1;
        fetchLedger();
      }, 320);
    });
  }

  ledgerPrev?.addEventListener("click", () => {
    if (ledgerPage > 1) {
      ledgerPage -= 1;
      fetchLedger();
    }
  });
  ledgerNext?.addEventListener("click", () => {
    ledgerPage += 1;
    fetchLedger();
  });

  if (ledgerApiUrl && ledgerTbody) {
    scheduleLedgerPoll();
  }

  const showWaitModal = (title, status, detail = "") => {
    if (!waitBackdrop) return;
    const titleEl = waitBackdrop.querySelector("#automation-daraja-wait-title");
    if (titleEl && title) titleEl.textContent = title;
    if (waitStatus) waitStatus.textContent = status;
    if (waitDetail) waitDetail.textContent = detail;
    if (waitClose) waitClose.hidden = true;
    waitBackdrop.hidden = false;
    document.body.classList.add("modal-open");
  };

  const hideWaitModal = () => {
    if (!waitBackdrop) return;
    waitBackdrop.hidden = true;
    document.body.classList.remove("modal-open");
  };

  waitClose?.addEventListener("click", hideWaitModal);

  const pollOperation = (operationId) =>
    new Promise((resolve, reject) => {
      if (!ledgerApiUrl) {
        reject(new Error("Missing poll URL."));
        return;
      }
      let tries = 0;
      const maxTries = 90;
      const tick = async () => {
        tries += 1;
        try {
          const params = new URLSearchParams({ poll: "operation", operation_id: String(operationId) });
          const response = await fetch(`${ledgerApiUrl}?${params}`, {
            headers: { Accept: "application/json", "X-Requested-With": "XMLHttpRequest" },
            cache: "no-store",
          });
          if (!response.ok) throw new Error("Could not check status.");
          const data = await response.json();
          const op = data.operation;
          if (!op) throw new Error("Invalid response.");
          if (waitStatus) {
            waitStatus.textContent = op.summary || op.status_label || "Waiting for Safaricom…";
          }
          if (waitDetail) {
            const parts = [];
            if (op.destination) parts.push(`To ${op.destination}`);
            if (op.amount) parts.push(`KES ${formatKes(op.amount)}`);
            if (op.mpesa_reference) parts.push(`Receipt ${op.mpesa_reference}`);
            waitDetail.textContent = parts.join(" · ");
          }
          if (op.complete) {
            if (op.success) {
              if (waitStatus) waitStatus.textContent = op.summary || "Payment completed.";
              if (waitClose) waitClose.hidden = false;
              fetchLedger();
              resolve(op);
              return;
            }
            const msg = op.result_desc || op.summary || "M-Pesa reported a failure.";
            if (waitStatus) waitStatus.textContent = msg;
            if (waitClose) waitClose.hidden = false;
            reject(new Error(msg));
            return;
          }
          if (tries >= maxTries) {
            if (waitStatus) {
              waitStatus.textContent = "Still waiting — check Transactions below or try again later.";
            }
            if (waitClose) waitClose.hidden = false;
            fetchLedger();
            resolve(op);
            return;
          }
          window.setTimeout(tick, 1200);
        } catch (err) {
          if (tries >= maxTries) {
            reject(err);
            return;
          }
          window.setTimeout(tick, 1500);
        }
      };
      window.setTimeout(tick, 800);
    });

  const manualForm = page.querySelector("[data-manual-b2c-form]");
  manualForm?.addEventListener("submit", async (event) => {
    if (!window.fetch) return;
    event.preventDefault();
    const submitBtn = manualForm.querySelector('button[type="submit"]');
    const originalLabel = submitBtn?.textContent;
    if (submitBtn) {
      submitBtn.disabled = true;
      submitBtn.textContent = "Sending…";
    }
    showWaitModal("Sending via M-Pesa", "Submitting B2C payout…");
    try {
      const body = new URLSearchParams(new FormData(manualForm));
      const response = await fetch(manualForm.action, {
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
      if (!response.ok || !data.ok) {
        const detail =
          data.detail ||
          (data.errors && Object.values(data.errors).flat().map((e) => e.message || e).join(" ")) ||
          "Could not send payout.";
        hideWaitModal();
        window.alert(detail);
        return;
      }
      const op = data.operation;
      showWaitModal(
        "Waiting for Safaricom",
        op?.summary || "Queued — waiting for callback…",
        op?.destination ? `To ${op.destination}` : "",
      );
      await pollOperation(op.id);
    } catch (err) {
      if (waitBackdrop && !waitBackdrop.hidden && waitClose && !waitClose.hidden) {
        /* user saw timeout / failure in modal */
      } else {
        hideWaitModal();
        window.alert(err?.message || "Send failed.");
      }
    } finally {
      if (submitBtn) {
        submitBtn.disabled = manualForm.dataset.b2cReady !== "1";
        if (originalLabel) submitBtn.textContent = originalLabel;
      }
    }
  });
}

function runShellInits() {
  const secondaryInits = [
    initDarajaSetup,
    initDarajaTests,
    initHubBalance,
    initUtilityTransfer,
    initAutomations,
    initAutomationAccountPage,
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
