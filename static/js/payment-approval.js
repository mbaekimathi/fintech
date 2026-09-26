/**
 * Payment approval: app 6-digit password and/or M-Pesa STK before Approve & send.
 */
(function () {
  "use strict";

  const DISMISS_KEY = "nexus-approval-dismissed";
  const AUTO_PROMPT_KEY = "nexus-approval-auto-started";

  let flowReady = false;
  let runtime = null;

  const api = {
    isActive: () => false,
    beginApprovalFlow: () => {},
  };

  function csrfToken() {
    return (
      document.querySelector('meta[name="csrf-token"]')?.content ||
      document.querySelector('input[name="csrfmiddlewaretoken"]')?.value ||
      ""
    );
  }

  function normalizeConfig(raw) {
    if (!raw || typeof raw !== "object") return null;
    const lipa = raw.stkLipaCharge === true;
    const paybill =
      raw.paybillPinAuth === true || raw.paybillPinAuth === "true" || !lipa;
    const phoneStk = raw.phoneStkPrompt === true || raw.phoneStkPrompt === "true";
    const smsOtp = raw.smsOtp === true || raw.smsOtp === "true";
    return {
      ...raw,
      stkLipaCharge: lipa,
      paybillPinAuth: paybill,
      phoneStkPrompt: phoneStk,
      smsOtp,
    };
  }

  function parseConfig() {
    const el = document.getElementById("approval-config");
    if (!el) return null;
    try {
      return normalizeConfig(JSON.parse(el.textContent || "{}"));
    } catch (_err) {
      return null;
    }
  }

  function lipaStkChargeEnabled(config) {
    return config?.stkLipaCharge === true;
  }

  function phoneStkPrompt(config) {
    return Boolean(config?.phoneStkPrompt && channels(config).stk);
  }

  function smsOtpForReviewer(config) {
    return Boolean(config?.smsOtp && channels(config).stk);
  }

  function paybillPinAuth(config) {
    if (phoneStkPrompt(config)) return false;
    return config?.paybillPinAuth !== false && !lipaStkChargeEnabled(config);
  }

  function channels(config) {
    return { app: Boolean(config?.app), stk: Boolean(config?.stk) };
  }

  function approvalRequired(config) {
    const ch = channels(config);
    return ch.app || ch.stk;
  }

  function appReady(config, ch) {
    const needsAppPin = ch.app || (ch.stk && paybillPinAuth(config));
    return Boolean(needsAppPin && config?.hasApprovalPassword !== false);
  }

  function stkReady(config, ch) {
    return Boolean(ch.stk && config?.hasPhone !== false);
  }

  function approvalAttr(form, name) {
    return (form.getAttribute(name) || "").trim();
  }

  function approvalMetaFromForm(form) {
    return {
      requester:
        approvalAttr(form, "data-approval-requester") ||
        approvalAttr(form, "data-approval-title"),
      destination:
        approvalAttr(form, "data-approval-destination") ||
        approvalAttr(form, "data-approval-body"),
      reason: approvalAttr(form, "data-approval-reason"),
      amount: approvalAttr(form, "data-approval-amount"),
      source: approvalAttr(form, "data-approval-source"),
    };
  }

  function approvalMetaFromPollRow(row) {
    const destParts = [row.destination_type, row.destination].filter(Boolean).join(" · ");
    const destination = row.account_ref ? `${destParts} / ${row.account_ref}` : destParts;
    const requester = [row.requester_name, row.requester_code].filter(Boolean).join(" · ");
    return {
      requester,
      destination: destination || (row.body || "").trim(),
      reason: (row.reason || "").trim(),
      amount: row.amount_label ? `KES ${row.amount_label}` : row.amount ? `KES ${row.amount}` : "",
      source: (row.source_paybill || "").trim(),
    };
  }

  function applyApprovalMetaToForm(form, meta) {
    if (!form || !meta) return;
    const set = (attr, val) => {
      if (val) form.setAttribute(attr, val);
      else form.removeAttribute(attr);
    };
    set("data-approval-requester", meta.requester);
    set("data-approval-destination", meta.destination);
    set("data-approval-reason", meta.reason);
    set("data-approval-amount", meta.amount);
    set("data-approval-source", meta.source);
  }

  function queryApprovalDetailRefs(prefix) {
    return {
      wrap: document.querySelector(`[data-${prefix}-approval-detail-wrap]`),
      requester: document.querySelector(`[data-${prefix}-approval-requester]`),
      destination: document.querySelector(`[data-${prefix}-approval-destination]`),
      reason: document.querySelector(`[data-${prefix}-approval-reason]`),
      amount: document.querySelector(`[data-${prefix}-approval-amount]`),
      source: document.querySelector(`[data-${prefix}-approval-source]`),
    };
  }

  function renderApprovalDetail(refs, meta) {
    const dash = "—";
    const set = (el, val) => {
      if (el) el.textContent = val || dash;
    };
    set(refs.requester, meta.requester);
    set(refs.destination, meta.destination);
    set(refs.reason, meta.reason);
    set(refs.amount, meta.amount);
    set(refs.source, meta.source);
    const reasonRow = refs.wrap?.querySelector("[data-pin-approval-reason-row]");
    if (reasonRow) reasonRow.hidden = !meta.reason;
    const hasAny = Object.values(meta).some((v) => Boolean(v));
    if (refs.wrap) refs.wrap.hidden = !hasAny;
    const pinSub = document.querySelector("[data-pin-approval-subtitle]");
    if (pinSub && refs.wrap?.hasAttribute("data-pin-approval-detail-wrap")) {
      pinSub.hidden = hasAny;
    }
  }

  function appendInlineApprovalPin(form) {
    if (!form || form.querySelector("[data-approval-inline]")) return;
    const wrap = document.createElement("div");
    wrap.className = "approval-inline-pin";
    wrap.setAttribute("data-approval-inline", "");
    const input = document.createElement("input");
    input.type = "password";
    input.name = "approval_pin";
    input.className = "pin-field approval-pin-inline";
    input.inputMode = "numeric";
    input.maxLength = 6;
    input.autocomplete = "current-password";
    input.placeholder = "6-digit PIN";
    input.setAttribute("aria-label", "6-digit approval password");
    wrap.appendChild(input);
    form.appendChild(wrap);
  }

  function hideInlineApprovalFields() {
    document.querySelectorAll("[data-approval-inline]").forEach((el) => hideEl(el));
  }

  function showEl(el) {
    if (!el) return;
    el.hidden = false;
    el.removeAttribute("hidden");
  }

  function hideEl(el) {
    if (!el) return;
    el.hidden = true;
    el.setAttribute("hidden", "");
  }

  function tabVisible() {
    return typeof document !== "undefined" && document.visibilityState === "visible";
  }

  function dismissedSet() {
    try {
      return new Set(JSON.parse(sessionStorage.getItem(DISMISS_KEY) || "[]"));
    } catch (_err) {
      return new Set();
    }
  }

  function dismissNotification(notificationId, moneyRequestId) {
    const set = dismissedSet();
    if (notificationId) set.add(String(notificationId));
    if (moneyRequestId) set.add(`mr-${moneyRequestId}`);
    sessionStorage.setItem(DISMISS_KEY, JSON.stringify([...set]));
  }

  function autoPromptSet() {
    try {
      return new Set(JSON.parse(sessionStorage.getItem(AUTO_PROMPT_KEY) || "[]"));
    } catch (_err) {
      return new Set();
    }
  }

  function saveAutoPrompt(set) {
    sessionStorage.setItem(AUTO_PROMPT_KEY, JSON.stringify([...set]));
  }

  function syncAutoPrompt(activeMoneyRequestIds) {
    const active =
      activeMoneyRequestIds instanceof Set ? activeMoneyRequestIds : new Set();
    const started = autoPromptSet();
    let changed = false;
    for (const id of [...started]) {
      if (!active.has(String(id))) {
        started.delete(id);
        changed = true;
      }
    }
    if (changed) saveAutoPrompt(started);
  }

  function rowDismissed(row, dismissed) {
    if (!row) return true;
    const noteId = String(row.notification_id ?? "");
    const mrKey = `mr-${row.money_request_id}`;
    if (noteId && dismissed.has(noteId)) return true;
    if (row.money_request_id != null && dismissed.has(mrKey)) return true;
    return false;
  }

  function openTransferDetail(detail) {
    if (!detail || typeof detail !== "object") return;
    window.dispatchEvent(new CustomEvent("open-transfer-detail", { detail }));
  }

  function formatWhen(iso) {
    if (!iso) return "—";
    const date = new Date(iso);
    if (Number.isNaN(date.getTime())) return "—";
    return date.toLocaleString(undefined, {
      day: "numeric",
      month: "short",
      hour: "2-digit",
      minute: "2-digit",
    });
  }

  function formatRelative(isoOrLabel) {
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

  function renderPendingTable(config, pendingRows, csrf) {
    const tbody = document.querySelector("[data-pending-requests-tbody]");
    if (!tbody || api.isActive()) return;

    const canReview = tbody.getAttribute("data-can-review") === "1";
    const needsApproval =
      tbody.getAttribute("data-approval-required") === "1" || approvalRequired(config);
    const rows = Array.isArray(pendingRows) ? pendingRows : [];
    const colSpan = canReview ? 9 : 8;

    tbody.replaceChildren();

    if (!rows.length) {
      const tr = document.createElement("tr");
      tr.setAttribute("data-pending-empty", "");
      const td = document.createElement("td");
      td.colSpan = colSpan;
      td.className = "muted ledger-table-empty";
      td.textContent = "No pending money requests.";
      tr.append(td);
      tbody.appendChild(tr);
      return;
    }

    rows.forEach((row) => {
      const tr = document.createElement("tr");
      tr.setAttribute("data-pending-row", String(row.money_request_id));

      const destParts = [row.destination_type, row.destination].filter(Boolean).join(" · ");
      const destText = row.account_ref ? `${destParts} / ${row.account_ref}` : destParts;
      const title = row.title || `${row.requester_name} requested KES ${row.amount_label}`;
      const body = row.body || destText;

      const addCell = (label, content, { className = "" } = {}) => {
        const td = document.createElement("td");
        if (label) td.setAttribute("data-label", label);
        if (className) td.className = className;
        if (content instanceof Node) td.appendChild(content);
        else td.textContent = content;
        tr.appendChild(td);
        return td;
      };

      addCell("When", formatWhen(row.created_at));
      addCell(
        "Initiator",
        `${row.requester_name || ""}${row.requester_code ? ` · ${row.requester_code}` : ""}`.trim() ||
          "—",
      );
      addCell("Category", row.category || "—");
      addCell("To", destText);
      addCell("From", row.source_paybill || "—");
      addCell("Amount", `KES ${row.amount_label || row.amount || ""}`);

      const badge = document.createElement("span");
      badge.className = "badge badge-pending";
      badge.textContent = "Pending";
      addCell("Status", badge);

      const viewTd = document.createElement("td");
      viewTd.className = "ledger-table-view";
      viewTd.setAttribute("data-label", "");
      const viewBtn = document.createElement("button");
      viewBtn.type = "button";
      viewBtn.className = "icon-btn row-view-btn";
      viewBtn.setAttribute("aria-label", "View transfer details");
      viewBtn.title = "View reason and details";
      viewBtn.innerHTML = `
        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true">
          <path d="M2.1 12s3.6-7 9.9-7 9.9 7 9.9 7-3.6 7-9.9 7-9.9-7-9.9-7Z"/>
          <circle cx="12" cy="12" r="3"/>
        </svg>
      `;
      const destFull = row.account_ref
        ? `${destText} / ${row.account_ref}`
        : destText;
      viewBtn.addEventListener("click", () => {
        openTransferDetail({
          when: formatWhen(row.created_at),
          initiator: row.requester_name || "",
          initiatorCode: row.requester_code || "",
          category: row.category || "",
          reason: row.reason || "",
          destination: destFull,
          source: row.source_paybill || "",
          amount: `KES ${row.amount_label || row.amount || ""}`,
          status: "Pending",
          statusBadge: row.status_badge || "pending",
          reference: `MR-${row.money_request_id}`,
        });
      });
      viewTd.appendChild(viewBtn);
      tr.appendChild(viewTd);

      if (canReview) {
        const actionsTd = document.createElement("td");
        actionsTd.className = "ledger-table-actions";
        actionsTd.setAttribute("data-label", "Actions");
        const toolbar = document.createElement("div");
        toolbar.className = "toolbar ledger-toolbar";

        const approveForm = document.createElement("form");
        approveForm.method = "post";
        approveForm.action = row.review_url;
        approveForm.className = "inline-form";
        approveForm.setAttribute("data-approval-form", "");
        approveForm.setAttribute("data-money-request-id", String(row.money_request_id));
        if (row.notification_id != null) {
          approveForm.setAttribute("data-notification-id", String(row.notification_id));
        }
        approveForm.setAttribute("data-approval-title", title);
        approveForm.setAttribute("data-approval-body", body);
        applyApprovalMetaToForm(approveForm, approvalMetaFromPollRow(row));

        const next = `${window.location.pathname}${window.location.search}`;
        approveForm.innerHTML = `
          <input type="hidden" name="csrfmiddlewaretoken" value="${csrf}">
          <input type="hidden" name="intent" value="approve">
        `;
        const nextInput = document.createElement("input");
        nextInput.type = "hidden";
        nextInput.name = "next";
        nextInput.value = next;
        approveForm.appendChild(nextInput);

        if (needsApproval) appendInlineApprovalPin(approveForm);
        const approveBtn = document.createElement("button");
        approveBtn.type = "submit";
        approveBtn.className = "btn btn-primary btn-small";
        approveBtn.textContent = "Approve & send";
        approveForm.appendChild(approveBtn);
        toolbar.appendChild(approveForm);

        const rejectForm = document.createElement("form");
        rejectForm.method = "post";
        rejectForm.action = row.review_url;
        rejectForm.className = "inline-form";
        rejectForm.innerHTML = `
          <input type="hidden" name="csrfmiddlewaretoken" value="${csrf}">
          <input type="hidden" name="intent" value="reject">
        `;
        const rejectNext = document.createElement("input");
        rejectNext.type = "hidden";
        rejectNext.name = "next";
        rejectNext.value = next;
        rejectForm.appendChild(rejectNext);
        const rejectBtn = document.createElement("button");
        rejectBtn.type = "submit";
        rejectBtn.className = "btn btn-ghost btn-small";
        rejectBtn.textContent = "Reject";
        rejectForm.appendChild(rejectBtn);
        toolbar.appendChild(rejectForm);

        actionsTd.appendChild(toolbar);
        tr.appendChild(actionsTd);
      }

      tbody.appendChild(tr);
    });
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
      when.textContent = note.created_ago || formatRelative(note.created_at);
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
        if (note.requester_name) {
          applyApprovalMetaToForm(approveForm, approvalMetaFromPollRow(note));
        }
        approveForm.innerHTML = `
          <input type="hidden" name="csrfmiddlewaretoken" value="${csrf}">
          <input type="hidden" name="intent" value="approve">
          <input type="hidden" name="next" value="${next}">
        `;
        appendInlineApprovalPin(approveForm);
        const approveBtn = document.createElement("button");
        approveBtn.type = "submit";
        approveBtn.className = "btn btn-primary btn-small";
        approveBtn.textContent = "Approve & send";
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

  function misconfigAlert(config) {
    const ch = channels(config);
    const hubOn = Boolean(config?.hubApp || config?.hubStk);
    if (hubOn && !ch.app && !ch.stk) {
      window.alert(
        "Hub payment approval is on, but your account is missing App on approve and/or PIN on approve under employee permissions. Ask an admin to enable them on your people profile, then refresh this page.",
      );
      return true;
    }
    return false;
  }

  function buildStkPollUrl(config, operationId) {
    const id = String(operationId ?? "").trim();
    if (!/^\d+$/.test(id)) return "";
    let tpl = (config?.stkPollUrl || "").trim();
    if (!tpl && config?.stkInitiateUrl) {
      tpl = String(config.stkInitiateUrl).replace(/\/?$/, "/0/");
    }
    if (!tpl) return "";
    if (tpl.includes("/0/")) return tpl.replace("/0/", `/${id}/`);
    if (/\/0\/?$/.test(tpl)) return tpl.replace(/\/0\/?$/, `/${id}/`);
    const base = tpl.endsWith("/") ? tpl : `${tpl}/`;
    return `${base}${id}/`;
  }

  function profileIncompleteAlert(config) {
    const ch = channels(config);
    if (!approvalRequired(config)) return false;
    const needs = [];
    const stkAuthorizesPaybill = ch.stk && paybillPinAuth(config);
    if (smsOtpForReviewer(config)) {
      if (config?.hasPhone === false) {
        needs.push("your phone number on Profile");
      }
    } else {
      if (
        (ch.app || stkAuthorizesPaybill) &&
        config?.hasApprovalPassword === false
      ) {
        needs.push("a 6-digit approval password on Profile");
      }
      if (ch.stk && config?.hasPhone === false) {
        needs.push("your phone number on Profile");
      }
    }
    if (needs.length) {
      window.alert(`Before you can approve, set ${needs.join(" and ")}.`);
      return true;
    }
    return false;
  }

  function createFlow(config) {
    const ch = channels(config);
    if (!approvalRequired(config)) return null;

    const csrf = csrfToken();

    const dom = {
      appBackdrop: document.querySelector("[data-pin-approval-backdrop]"),
      appInput: document.querySelector("[data-pin-approval-input]"),
      appError: document.querySelector("[data-pin-approval-error]"),
      appSetup: document.querySelector("[data-pin-approval-setup]"),
      appPhoneSetup: document.querySelector("[data-pin-approval-phone-setup]"),
      appUseStk: document.querySelector("[data-pin-approval-use-stk]"),
      appSubmit: document.querySelector("[data-pin-approval-submit]"),
      appCancel: document.querySelector("[data-pin-approval-cancel]"),
      appSubtitle: document.querySelector("[data-pin-approval-subtitle]"),
      appFieldLabel: document.querySelector("[data-pin-approval-field-label]"),
      appResendSms: document.querySelector("[data-pin-approval-resend-sms]"),
      appDetailRefs: queryApprovalDetailRefs("pin"),
      stkBackdrop: document.querySelector("[data-stk-approval-backdrop]"),
      stkDialog: document.querySelector("[data-stk-approval-dialog]"),
      stkMessage: document.querySelector("[data-stk-approval-message]"),
      stkStatus: document.querySelector("[data-stk-approval-status]"),
      stkError: document.querySelector("[data-stk-approval-error]"),
      stkUseApp: document.querySelector("[data-stk-approval-use-app]"),
      stkCancel: document.querySelectorAll("[data-stk-approval-cancel]"),
      stkDetailRefs: queryApprovalDetailRefs("stk"),
      stkHeadline: document.querySelector("[data-stk-approval-headline]"),
      stkLive: document.querySelector("[data-stk-approval-live]"),
      stkOutcomeSuccess: document.querySelector("[data-stk-approval-outcome-success]"),
      stkOutcomeFail: document.querySelector("[data-stk-approval-outcome-fail]"),
      stkSuccessReason: document.querySelector("[data-stk-approval-success-reason]"),
      stkFailReason: document.querySelector("[data-stk-approval-fail-reason]"),
      stkRetry: document.querySelector("[data-stk-approval-retry]"),
      stkPinPanel: document.querySelector("[data-stk-approval-pin-panel]"),
      stkPinInput: document.querySelector("[data-stk-approval-pin-input]"),
      stkPinError: document.querySelector("[data-stk-approval-pin-error]"),
      stkPinSubmit: document.querySelector("[data-stk-approval-pin-submit]"),
      stkBackStk: document.querySelector("[data-stk-approval-back-stk]"),
      stkTitle: document.getElementById("stk-approval-title"),
    };

    const STK_POLL_MS = 1500;

    const canUseAppPinAlt = () => ch.app && appReady(config, ch);

    const syncStkUseAppButton = () => {
      if (!dom.stkUseApp) return;
      const show = canUseAppPinAlt() && dom.stkDialog?.getAttribute("data-stk-approval-view") !== "pin";
      dom.stkUseApp.hidden = !show;
    };

    const hideStkPinEntry = () => {
      if (dom.stkDialog) dom.stkDialog.setAttribute("data-stk-approval-view", "stk");
      if (dom.stkPinPanel) hideEl(dom.stkPinPanel);
      if (dom.stkPinInput) {
        dom.stkPinInput.value = "";
        dom.stkPinInput.disabled = false;
      }
      if (dom.stkPinError) dom.stkPinError.hidden = true;
      if (dom.stkPinSubmit) dom.stkPinSubmit.hidden = true;
      if (dom.stkBackStk) dom.stkBackStk.hidden = true;
      if (dom.stkUseApp) {
        dom.stkUseApp.setAttribute("aria-expanded", "false");
      }
      syncStkUseAppButton();
    };

    const showStkPinEntry = () => {
      if (!pendingForm) return;
      active = true;
      if (!canUseAppPinAlt()) {
        openApp(pendingForm);
        return;
      }
      stopStkPoll();
      setStkState("idle");
      resetStkOutcomes();
      if (dom.stkDialog) dom.stkDialog.setAttribute("data-stk-approval-view", "pin");
      if (dom.stkTitle) dom.stkTitle.textContent = "Enter your approval password";
      if (dom.stkMessage) {
        dom.stkMessage.textContent =
          "Your 6-digit password authorizes the hub paybill payout — no M-Pesa charge on your phone.";
      }
      if (dom.stkPinPanel) showEl(dom.stkPinPanel);
      if (dom.stkPinSubmit) showEl(dom.stkPinSubmit);
      if (dom.stkBackStk && lipaStkChargeEnabled(config)) showEl(dom.stkBackStk);
      if (dom.stkUseApp) {
        dom.stkUseApp.hidden = true;
        dom.stkUseApp.setAttribute("aria-expanded", "true");
      }
      if (dom.stkRetry) dom.stkRetry.hidden = true;
      if (dom.stkError) {
        dom.stkError.hidden = true;
        dom.stkError.textContent = "";
      }
      showEl(dom.stkBackdrop);
      window.requestAnimationFrame(() => dom.stkPinInput?.focus());
    };

    const setStkState = (state) => {
      if (dom.stkDialog) dom.stkDialog.setAttribute("data-approval-state", state || "idle");
    };

    const resetStkOutcomes = () => {
      if (dom.stkOutcomeSuccess) dom.stkOutcomeSuccess.hidden = true;
      if (dom.stkOutcomeFail) dom.stkOutcomeFail.hidden = true;
      if (dom.stkSuccessReason) dom.stkSuccessReason.textContent = "";
      if (dom.stkFailReason) dom.stkFailReason.textContent = "";
      if (dom.stkLive) dom.stkLive.hidden = true;
      if (dom.stkRetry) dom.stkRetry.hidden = true;
    };

    const applyStkPoll = (data) => {
      if (!data) return;
      const phase = data.phase || (data.complete ? (data.success ? "success" : "failed") : "waiting");
      setStkState(data.complete ? (data.success ? "success" : "error") : phase);

      if (dom.stkHeadline) {
        dom.stkHeadline.textContent =
          data.headline ||
          (data.complete
            ? data.success
              ? "M-Pesa PIN accepted"
              : "M-Pesa did not approve"
            : "Checking M-Pesa status…");
      }
      if (dom.stkStatus) {
        dom.stkStatus.textContent = data.summary || data.reason || "Waiting for M-Pesa…";
      }

      const showLive = !data.complete;
      if (dom.stkLive) dom.stkLive.hidden = !showLive;

      if (dom.stkOutcomeSuccess) dom.stkOutcomeSuccess.hidden = !(data.complete && data.success);
      if (dom.stkOutcomeFail) dom.stkOutcomeFail.hidden = !(data.complete && !data.success);
      if (data.complete && data.success && dom.stkSuccessReason) {
        dom.stkSuccessReason.textContent = data.reason || data.summary || "Your PIN was verified.";
      }
      if (data.complete && !data.success) {
        const failText =
          data.reason ||
          data.summary ||
          "The STK prompt was cancelled, timed out, or declined.";
        if (dom.stkFailReason) dom.stkFailReason.textContent = failText;
        if (dom.stkError) {
          dom.stkError.textContent = failText;
          dom.stkError.hidden = false;
        }
        if (dom.stkRetry) dom.stkRetry.hidden = false;
        syncStkUseAppButton();
      } else if (dom.stkError && !data.complete) {
        dom.stkError.hidden = true;
        dom.stkError.textContent = "";
      }
    };

    let pendingForm = null;
    let approvalPin = "";
    let stkPollTimer = null;
    let active = false;
    let deferredForm = null;
    let deferredHandler = null;

    const setContext = (form) => {
      const meta = approvalMetaFromForm(form);
      renderApprovalDetail(dom.appDetailRefs, meta);
      renderApprovalDetail(dom.stkDetailRefs, meta);
    };

    const clearDeferred = () => {
      deferredForm = null;
      if (deferredHandler) {
        document.removeEventListener("visibilitychange", deferredHandler);
        deferredHandler = null;
      }
    };

    const closeApp = () => {
      if (dom.appInput) {
        dom.appInput.value = "";
        dom.appInput.disabled = false;
      }
      if (dom.appSubmit) dom.appSubmit.disabled = false;
      if (dom.appError) dom.appError.hidden = true;
      if (dom.appSetup) dom.appSetup.hidden = true;
      if (dom.appPhoneSetup) dom.appPhoneSetup.hidden = true;
      if (dom.appUseStk) dom.appUseStk.hidden = true;
      hideEl(dom.appBackdrop);
    };

    const stopStkPoll = () => {
      if (stkPollTimer) {
        window.clearInterval(stkPollTimer);
        stkPollTimer = null;
      }
    };

    const closeStk = () => {
      stopStkPoll();
      setStkState("idle");
      resetStkOutcomes();
      if (dom.stkError) {
        dom.stkError.hidden = true;
        dom.stkError.textContent = "";
      }
      if (dom.stkHeadline) dom.stkHeadline.textContent = "Waiting for M-Pesa…";
      if (dom.stkStatus) dom.stkStatus.textContent = "We check Safaricom every few seconds.";
      hideStkPinEntry();
      if (dom.stkUseApp) dom.stkUseApp.hidden = true;
      hideEl(dom.stkBackdrop);
    };

    const reset = () => {
      active = false;
      pendingForm = null;
      approvalPin = "";
      clearDeferred();
      closeApp();
      closeStk();
    };

    const cancel = () => {
      dismissNotification(
        pendingForm?.getAttribute("data-notification-id"),
        pendingForm?.getAttribute("data-money-request-id"),
      );
      reset();
    };

    const attachHidden = (form, name, value) => {
      if (!value) return;
      let input = form.querySelector(`input[name="${name}"]`);
      if (!input) {
        input = document.createElement("input");
        input.type = "hidden";
        input.name = name;
        form.appendChild(input);
      }
      input.value = value;
    };

    const postApprove = async (form, stkOperationId = "", { keepUi = false } = {}) => {
      attachHidden(form, "approval_pin", approvalPin);
      attachHidden(form, "stk_approval_operation_id", stkOperationId);
      const target = form;
      if (!keepUi) {
        reset();
      } else {
        active = true;
      }

      const submitBtn = target.querySelector(
        "button[type='submit'], button[data-approval-trigger]",
      );
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
        /* full page post fallback */
      } finally {
        if (submitBtn) {
          submitBtn.disabled = false;
          if (originalLabel) submitBtn.textContent = originalLabel;
        }
      }

      target.submit();
    };

    const offerAppPinAfterStkFailure = (message) => {
      if (!canUseAppPinAlt()) return false;
      if (dom.stkError) {
        dom.stkError.textContent =
          message ||
          "M-Pesa did not confirm this approval. Enter your approval password below instead.";
        dom.stkError.hidden = false;
      }
      showStkPinEntry();
      return true;
    };

    const pollStk = (operationId) =>
      new Promise((resolve, reject) => {
        const pollUrl = buildStkPollUrl(config, operationId);
        if (!pollUrl) {
          reject(new Error("Missing STK poll URL. Refresh the page and try again."));
          return;
        }
        let httpFailStreak = 0;
        const MAX_HTTP_FAILS = 8;

        const finish = (ok, message) => {
          stopStkPoll();
          if (ok) resolve(operationId);
          else reject(new Error(message || "M-Pesa approval failed."));
        };

        const tick = async () => {
          try {
            const response = await fetch(pollUrl, {
              headers: { "X-Requested-With": "XMLHttpRequest", Accept: "application/json" },
              cache: "no-store",
              credentials: "same-origin",
            });
            const contentType = response.headers.get("content-type") || "";
            let data = null;
            if (contentType.includes("application/json")) {
              data = await response.json();
            } else if (!response.ok) {
              throw new Error(
                response.status === 403 || response.status === 401
                  ? "Session expired or access denied. Refresh the page, sign in, and try again."
                  : `Could not check STK status (HTTP ${response.status}).`,
              );
            }

            if (!response.ok) {
              if (data?.complete) {
                finish(false, data.detail || data.reason || "M-Pesa approval failed.");
                return;
              }
              httpFailStreak += 1;
              const detail = data?.detail || data?.error || "";
              if (httpFailStreak >= MAX_HTTP_FAILS) {
                finish(
                  false,
                  detail ||
                    `Could not check STK status (HTTP ${response.status}). Use your approval password instead.`,
                );
              } else if (dom.stkStatus) {
                dom.stkStatus.textContent = detail || "Temporary error checking M-Pesa — retrying…";
              }
              syncStkUseAppButton();
              return;
            }

            httpFailStreak = 0;
            if (!data?.ok) {
              finish(false, data?.detail || "Could not check STK status.");
              return;
            }
            applyStkPoll(data);
            if (data.query_error && !data.complete && dom.stkStatus) {
              dom.stkStatus.textContent = `${data.query_error} (retrying…)`;
            }
            syncStkUseAppButton();
            if (data.complete) {
              finish(
                Boolean(data.success),
                data.reason ||
                  data.summary ||
                  "M-Pesa did not confirm this approval. Check your phone or try again.",
              );
            }
          } catch (err) {
            httpFailStreak += 1;
            if (httpFailStreak >= MAX_HTTP_FAILS) {
              finish(
                false,
                err.message ||
                  "Could not check STK status. Use your approval password instead.",
              );
            } else if (dom.stkStatus) {
              dom.stkStatus.textContent = "Connection issue — retrying M-Pesa status…";
            }
            syncStkUseAppButton();
          }
        };

        tick();
        stkPollTimer = window.setInterval(tick, STK_POLL_MS);
      });

    const sendApprovalSms = async (form, { force = false } = {}) => {
      const moneyRequestId = form.getAttribute("data-money-request-id");
      if (!moneyRequestId || !config.smsSendUrl) {
        window.alert("SMS approval is not configured on this page.");
        return false;
      }
      if (dom.appSubmit) dom.appSubmit.disabled = true;
      try {
        const body = new URLSearchParams({ money_request_id: moneyRequestId });
        if (force) body.set("force", "1");
        const response = await fetch(config.smsSendUrl, {
          method: "POST",
          headers: {
            "Content-Type": "application/x-www-form-urlencoded",
            "X-Requested-With": "XMLHttpRequest",
            "X-CSRFToken": csrf,
          },
          body,
        });
        const data = await response.json();
        if (!response.ok || !data.ok) {
          throw new Error(data.detail || "Could not send SMS code.");
        }
        if (dom.appSubtitle) {
          dom.appSubtitle.textContent =
            data.summary || "Enter the 6-digit code we sent to your phone.";
        }
        if (dom.appFieldLabel) dom.appFieldLabel.textContent = "6-digit code from SMS";
        if (dom.appInput) {
          dom.appInput.setAttribute("aria-label", "6-digit SMS approval code");
          dom.appInput.disabled = false;
        }
        if (dom.appResendSms) showEl(dom.appResendSms);
        if (dom.appError) dom.appError.hidden = true;
        return true;
      } catch (err) {
        const msg = err.message || "Could not send SMS code.";
        if (dom.appError) {
          dom.appError.textContent = msg;
          dom.appError.hidden = false;
        }
        window.alert(msg);
        return false;
      } finally {
        if (dom.appSubmit) dom.appSubmit.disabled = false;
      }
    };

    const loadPaybillAuthSummary = async (form) => {
      const sub = dom.appSubtitle || document.querySelector(".pin-approval-dialog__subtitle");
      const moneyRequestId = form.getAttribute("data-money-request-id");
      if (!sub || !moneyRequestId || !config.stkInitiateUrl) return;
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
        if (response.ok && data.ok && data.summary) {
          /* Summary lives in the detail card; keep subtitle short. */
          sub.textContent =
            "Enter your 6-digit hub approval password to approve and send.";
        }
      } catch (_err) {
        /* keep default subtitle */
      }
    };

    const openApp = (form, { useSmsOtp = false } = {}) => {
      if (!dom.appBackdrop || !dom.appInput) {
        window.alert("Approval password prompt is not available on this page.");
        reset();
        return;
      }
      pendingForm = form;
      setContext(form);
      dom.appInput.value = "";
      const smsMode = useSmsOtp || smsOtpForReviewer(config);
      if (dom.appResendSms) hideEl(dom.appResendSms);

      if (smsMode) {
        if (dom.appSetup) dom.appSetup.hidden = true;
        if (dom.appPhoneSetup) dom.appPhoneSetup.hidden = config.hasPhone !== false;
        if (dom.appUseStk) dom.appUseStk.hidden = true;
        if (dom.appFieldLabel) dom.appFieldLabel.textContent = "6-digit code from SMS";
        if (dom.appSubtitle) {
          dom.appSubtitle.textContent = "Sending a one-time code to your phone…";
        }
        dom.appInput.disabled = true;
        showEl(dom.appBackdrop);
        sendApprovalSms(form).then((ok) => {
          if (ok) window.requestAnimationFrame(() => dom.appInput?.focus());
        });
        return;
      }

      if (dom.appFieldLabel) {
        dom.appFieldLabel.textContent = "Approval password";
      }
      if (dom.appSubtitle && paybillPinAuth(config)) {
        dom.appSubtitle.textContent =
          "Enter your 6-digit hub approval password to approve and send.";
      }
      if (paybillPinAuth(config)) {
        loadPaybillAuthSummary(form);
      }

      const needsPassword = config.hasApprovalPassword === false;
      const needsPhone = config.hasPhone === false;
      if (dom.appSetup) dom.appSetup.hidden = !needsPassword;
      if (dom.appPhoneSetup) {
        dom.appPhoneSetup.hidden = !(
          needsPhone &&
          ch.stk &&
          !needsPassword &&
          lipaStkChargeEnabled(config)
        );
      }
      if (dom.appUseStk) {
        const showStkAlt = Boolean(
          !paybillPinAuth(config) &&
            ch.stk &&
            lipaStkChargeEnabled(config) &&
            config.hasPhone !== false &&
            (config.dualApproval || needsPassword),
        );
        dom.appUseStk.hidden = !showStkAlt;
      }

      if (needsPassword) {
        dom.appInput.disabled = true;
        if (dom.appSubmit) dom.appSubmit.disabled = true;
      } else {
        dom.appInput.disabled = false;
        if (dom.appSubmit) dom.appSubmit.disabled = false;
      }

      showEl(dom.appBackdrop);
      if (!needsPassword) {
        window.requestAnimationFrame(() => dom.appInput.focus());
      }
    };

    const runStk = async (form, { visible = true } = {}) => {
      const moneyRequestId = form.getAttribute("data-money-request-id");
      if (!moneyRequestId) {
        window.alert("This approval form is missing the money request id.");
        reset();
        return;
      }

      if (paybillPinAuth(config)) {
        openApp(form);
        return;
      }

      if (!config.stkInitiateUrl) {
        window.alert("STK approval is not configured.");
        reset();
        return;
      }

      pendingForm = form;
      active = true;
      setContext(form);

      if (visible) showEl(dom.stkBackdrop);
      else hideEl(dom.stkBackdrop);

      syncStkUseAppButton();
      resetStkOutcomes();
      setStkState("sending");
      if (dom.stkMessage) {
        dom.stkMessage.textContent =
          "Sending an STK prompt to your phone. Enter your M-Pesa PIN when it arrives.";
      }
      if (dom.stkHeadline) dom.stkHeadline.textContent = "Sending STK prompt…";
      if (dom.stkStatus) dom.stkStatus.textContent = "Connecting to Safaricom…";
      if (dom.stkError) dom.stkError.hidden = true;

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
        if (!response.ok || !data.ok) {
          throw new Error(
            data.detail ||
              "Could not send STK prompt. Check Daraja STK setup and your phone number on Profile.",
          );
        }
        if (data.mode === "paybill_payout") {
          closeStk();
          const pinSubtitle = document.querySelector(
            ".pin-approval-dialog .approval-dialog__subtitle",
          );
          if (pinSubtitle && data.summary) pinSubtitle.textContent = data.summary;
          openApp(form);
          return;
        }
        if (dom.stkMessage) {
          dom.stkMessage.textContent =
            data.summary || "Check your phone and enter your M-Pesa PIN to approve this payment.";
        }
        applyStkPoll({
          phase: "waiting",
          headline: "Enter your M-Pesa PIN on your phone",
          summary:
            data.summary || "STK sent — enter your PIN when prompted, then wait for confirmation.",
          reason: data.summary || "",
          complete: false,
          success: false,
        });

        const operationId = await pollStk(data.operation_id);
        applyStkPoll({
          phase: "success",
          headline: "M-Pesa PIN accepted",
          summary: "Sending the approved payment…",
          reason: dom.stkSuccessReason?.textContent || "Your M-Pesa PIN was verified.",
          complete: true,
          success: true,
        });
        await postApprove(form, operationId);
      } catch (err) {
        stopStkPoll();
        const failMsg = err.message || "PIN approval failed.";
        applyStkPoll({
          phase: "failed",
          headline: "M-Pesa did not approve this payment",
          summary: failMsg,
          reason: failMsg,
          complete: true,
          success: false,
        });
        active = true;
        pendingForm = form;
        if (visible) showEl(dom.stkBackdrop);
        if (offerAppPinAfterStkFailure(failMsg)) {
          return;
        }
      }
    };

    const pickChannel = () => {
      if (!ch.app && !ch.stk) return "none";
      if (smsOtpForReviewer(config) && ch.stk && config?.hasPhone !== false) return "sms";
      if (paybillPinAuth(config)) return "app";
      if (ch.app && appReady(config, ch)) return "app";
      if (phoneStkPrompt(config) && ch.stk && stkReady(config, ch)) return "stk";
      if (appReady(config, ch)) return "app";
      if (ch.stk && stkReady(config, ch)) return "stk";
      return ch.app ? "app" : "stk";
    };

    const deferUntilVisible = (form) => {
      pendingForm = form;
      active = false;
      deferredForm = form;
      if (deferredHandler) return;
      deferredHandler = () => {
        if (document.visibilityState !== "visible" || !deferredForm) return;
        const f = deferredForm;
        clearDeferred();
        beginApprovalFlow(f, { force: true, manual: false });
      };
      document.addEventListener("visibilitychange", deferredHandler);
    };

    const beginApprovalFlow = (form, { force = false, manual = false } = {}) => {
      if (active && !force) return;
      if (misconfigAlert(config)) return;
      if (profileIncompleteAlert(config)) return;
      active = true;
      pendingForm = form;
      approvalPin = "";

      const channel = pickChannel();

      if (channel === "sms") {
        openApp(form, { useSmsOtp: true });
        return;
      }

      if (channel === "app") {
        if (paybillPinAuth(config)) {
          openApp(form);
          return;
        }
        if (!manual && !tabVisible()) {
          if (stkReady(config, ch)) {
            runStk(form, { visible: false });
            return;
          }
          deferUntilVisible(form);
          return;
        }
        if (!appReady(config, ch) && stkReady(config, ch)) {
          runStk(form, { visible: true });
          return;
        }
        openApp(form);
        return;
      }

      if (channel === "stk") {
        const showUi = manual || tabVisible();
        runStk(form, { visible: showUi });
        return;
      }

      active = false;
      pendingForm = null;
      postApprove(form);
    };

    const submitStkPanelPin = () => {
      if (!pendingForm || !dom.stkPinInput) return;
      const pin = dom.stkPinInput.value.replace(/\D/g, "").slice(0, 6);
      if (pin.length !== 6) {
        if (dom.stkPinError) dom.stkPinError.hidden = false;
        dom.stkPinInput.focus();
        return;
      }
      approvalPin = pin;
      const form = pendingForm;
      closeStk();
      postApprove(form);
    };

    const submitAppPin = () => {
      if (!pendingForm || !dom.appInput) return;
      if (config.hasApprovalPassword === false) {
        if (stkReady(config, ch) && lipaStkChargeEnabled(config)) {
          closeApp();
          runStk(pendingForm, { visible: true });
          return;
        }
        if (dom.appSetup) dom.appSetup.hidden = false;
        return;
      }
      const pin = dom.appInput.value.replace(/\D/g, "").slice(0, 6);
      if (pin.length !== 6) {
        if (dom.appError) dom.appError.hidden = false;
        dom.appInput.focus();
        return;
      }
      approvalPin = pin;
      const form = pendingForm;
      if (dom.appError) dom.appError.hidden = true;
      if (dom.appSubtitle) {
        dom.appSubtitle.textContent =
          "Password accepted — sending approved payment from hub paybill…";
      }
      if (dom.appSubmit) {
        dom.appSubmit.disabled = true;
        dom.appSubmit.textContent = "Sending…";
      }
      if (dom.appInput) dom.appInput.disabled = true;
      postApprove(form, "", { keepUi: true });
    };

    document.addEventListener(
      "submit",
      (event) => {
        const form = event.target;
        if (!(form instanceof HTMLFormElement) || !form.hasAttribute("data-approval-form")) {
          return;
        }
        if (!approvalRequired(config)) return;
        const inlinePin = form.querySelector('input[name="approval_pin"]');
        const inlineVal = (inlinePin?.value || "").replace(/\D/g, "");
        if (!flowReady || !runtime) {
          if (inlineVal.length === 6) return;
          event.preventDefault();
          event.stopPropagation();
          window.alert(
            "Enter your 6-digit approval password in the PIN field, or run deploy.sh on the server and hard-refresh (Ctrl+F5).",
          );
          inlinePin?.focus();
          return;
        }
        if (paybillPinAuth(config) && inlineVal.length === 6) {
          approvalPin = inlineVal;
          return;
        }
        event.preventDefault();
        event.stopPropagation();
        beginApprovalFlow(form, { force: true, manual: true });
      },
      true,
    );

    dom.appSubmit?.addEventListener("click", submitAppPin);
    dom.appResendSms?.addEventListener("click", () => {
      if (pendingForm) sendApprovalSms(pendingForm, { force: true });
    });
    dom.appUseStk?.addEventListener("click", () => {
      if (paybillPinAuth(config)) {
        dom.appInput?.focus();
        return;
      }
      if (!pendingForm) return;
      const form = pendingForm;
      closeApp();
      active = true;
      pendingForm = form;
      runStk(form, { visible: true });
    });
    dom.stkUseApp?.addEventListener("click", (event) => {
      event.preventDefault();
      event.stopPropagation();
      active = true;
      showStkPinEntry();
    });
    dom.stkPinSubmit?.addEventListener("click", submitStkPanelPin);
    dom.stkBackStk?.addEventListener("click", () => {
      hideStkPinEntry();
      if (pendingForm) runStk(pendingForm, { visible: true });
    });
    dom.stkPinInput?.addEventListener("keydown", (event) => {
      if (event.key === "Enter") {
        event.preventDefault();
        submitStkPanelPin();
      }
      if (event.key === "Escape") cancel();
    });
    dom.appCancel?.addEventListener("click", cancel);
    dom.appBackdrop?.addEventListener("click", (event) => {
      if (event.target === dom.appBackdrop) cancel();
    });
    dom.appInput?.addEventListener("keydown", (event) => {
      if (event.key === "Enter") {
        event.preventDefault();
        submitAppPin();
      }
      if (event.key === "Escape") cancel();
    });
    dom.stkCancel.forEach((btn) => btn.addEventListener("click", cancel));
    dom.stkRetry?.addEventListener("click", () => {
      if (!pendingForm) return;
      const form = pendingForm;
      runStk(form, { visible: true });
    });
    dom.stkBackdrop?.addEventListener("click", (event) => {
      if (event.target === dom.stkBackdrop) cancel();
    });

    api.isActive = () => active;
    api.beginApprovalFlow = beginApprovalFlow;

    flowReady = true;
    window.__approvalFlowReady = true;

    return {
      config,
      csrf,
      beginApprovalFlow,
      isActive: () => active,
      showStkPinEntry,
    };
  }

  function initLivePoll(config, flow) {
    if (!config?.pendingPollUrl) return;

    const csrf = csrfToken();
    const begin =
      flow?.beginApprovalFlow ||
      api.beginApprovalFlow;
    const isActive = flow?.isActive || api.isActive;

    const buildHiddenForm = (item) => {
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
      applyApprovalMetaToForm(form, approvalMetaFromPollRow(item));
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
    let pendingPollBootstrapped = false;
    const pollDelay = () =>
      tabVisible()
        ? Number(config.pollIntervalMs) || 3000
        : Number(config.pollIntervalHiddenMs) || 12000;

    const schedulePoll = () => {
      if (pollTimer) window.clearInterval(pollTimer);
      pollTimer = window.setInterval(tick, pollDelay());
    };

    const tick = async () => {
      if (isActive()) return;
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

        const pending = Array.isArray(data.pending) ? data.pending : [];
        const activeIds = new Set(pending.map((row) => String(row.money_request_id)));
        syncAutoPrompt(activeIds);

        if (!pendingPollBootstrapped) {
          pendingPollBootstrapped = true;
          const seen = autoPromptSet();
          pending.forEach((row) => seen.add(String(row.money_request_id)));
          saveAutoPrompt(seen);
          renderPendingTable(config, data.pending, csrf);
          return;
        }

        renderPendingTable(config, data.pending, csrf);

        if (!config.autoPrompt || !approvalRequired(config)) return;

        const dismissed = dismissedSet();
        const started = autoPromptSet();
        const item = pending.find(
          (row) =>
            !rowDismissed(row, dismissed) && !started.has(String(row.money_request_id)),
        );
        if (!item) return;

        const form = buildHiddenForm(item);
        started.add(String(item.money_request_id));
        saveAutoPrompt(started);
        begin(form, { manual: false });
      } catch (_err) {
        /* ignore transient poll errors */
      }
    };

    tick();
    schedulePoll();
    document.addEventListener("visibilitychange", () => {
      schedulePoll();
      if (document.visibilityState === "visible") tick();
    });
  }

  function triggerFromForm(form, event, flow) {
    if (!(form instanceof HTMLFormElement) || !form.hasAttribute("data-approval-form")) {
      return;
    }
    const config = parseConfig();
    if (!config) {
      window.alert("Approval is not loaded. Refresh the page and try again.");
      return;
    }
    event?.preventDefault?.();
    event?.stopPropagation?.();

    if (misconfigAlert(config)) return;

    if (!approvalRequired(config)) {
      form.submit();
      return;
    }

    if (!flowReady) {
      window.alert(
        "Approval prompts failed to start. Hard-refresh the page (Ctrl+F5) and try again.",
      );
      return;
    }

    const begin =
      flow?.beginApprovalFlow ||
      window.nexusApproval?.beginApprovalFlow ||
      api.beginApprovalFlow;

    try {
      begin(form, { force: true, manual: true });
    } catch (err) {
      window.alert(err?.message || "Approval failed to start.");
    }
  }

  function installGlobalApprovalClickHandler() {
    if (document.documentElement.dataset.approvalClickInstalled) return;
    document.documentElement.dataset.approvalClickInstalled = "1";
    document.addEventListener(
      "click",
      (event) => {
        const btn = event.target.closest(
          "[data-approval-trigger], form[data-approval-form] .btn-primary",
        );
        if (!btn) return;
        const form = btn.closest("form[data-approval-form]");
        if (!form) return;
        const flow = runtime || window.__nexusApprovalRuntime;
        triggerFromForm(form, event, flow);
      },
      true,
    );
  }

  function boot() {
    installGlobalApprovalClickHandler();

    const config = parseConfig();
    if (!config) return;

    runtime = createFlow(config);
    if (!runtime) return;

    initLivePoll(config, runtime);

    hideInlineApprovalFields();

    window.nexusApproval = {
      ready: true,
      config,
      isActive: () => (runtime?.isActive || api.isActive)(),
      beginApprovalFlow: runtime.beginApprovalFlow,
      showStkPinEntry: () => runtime?.showStkPinEntry?.(),
      triggerFromButton(button, event) {
        const form = button?.closest?.("form[data-approval-form]");
        if (!form) return;
        triggerFromForm(form, event, runtime);
      },
    };
    window.__nexusApprovalRuntime = runtime;
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();
