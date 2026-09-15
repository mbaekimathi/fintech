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

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", () => {
    initDarajaSetup();
    initDarajaTests();
    initWebPush();
  });
} else {
  initDarajaSetup();
  initDarajaTests();
  initWebPush();
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
