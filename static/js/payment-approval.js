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

  function parseConfig() {
    const el = document.getElementById("approval-config");
    if (!el) return null;
    try {
      return JSON.parse(el.textContent || "{}");
    } catch (_err) {
      return null;
    }
  }

  function channels(config) {
    return { app: Boolean(config?.app), stk: Boolean(config?.stk) };
  }

  function approvalRequired(config) {
    const ch = channels(config);
    return ch.app || ch.stk;
  }

  function appReady(config, ch) {
    return Boolean(ch.app && config?.hasApprovalPassword !== false);
  }

  function stkReady(config, ch) {
    return Boolean(ch.stk && config?.hasPhone !== false);
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
      td.className = "muted";
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

      [
        formatWhen(row.created_at),
        `${row.requester_name || ""} · ${row.requester_code || ""}`.trim(),
        row.category || "—",
        destText,
        row.source_paybill || "—",
        `KES ${row.amount_label || row.amount || ""}`,
      ].forEach((text) => {
        const td = document.createElement("td");
        td.textContent = text;
        tr.appendChild(td);
      });

      const statusTd = document.createElement("td");
      const badge = document.createElement("span");
      badge.className = "badge badge-pending";
      badge.textContent = "Pending";
      statusTd.appendChild(badge);
      tr.appendChild(statusTd);

      const viewTd = document.createElement("td");
      viewTd.textContent = "—";
      tr.appendChild(viewTd);

      if (canReview) {
        const actionsTd = document.createElement("td");
        const toolbar = document.createElement("div");
        toolbar.className = "toolbar";

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

        const approveBtn = document.createElement("button");
        approveBtn.type = needsApproval ? "button" : "submit";
        approveBtn.className = "btn btn-primary btn-small";
        approveBtn.textContent = "Approve & send";
        if (needsApproval) approveBtn.setAttribute("data-approval-trigger", "");
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
        approveForm.innerHTML = `
          <input type="hidden" name="csrfmiddlewaretoken" value="${csrf}">
          <input type="hidden" name="intent" value="approve">
          <input type="hidden" name="next" value="${next}">
        `;
        const approveBtn = document.createElement("button");
        approveBtn.type = "button";
        approveBtn.className = "btn btn-primary btn-small";
        approveBtn.textContent = "Approve & send";
        approveBtn.setAttribute("data-approval-trigger", "");
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

  function profileIncompleteAlert(config) {
    const ch = channels(config);
    if (!approvalRequired(config)) return false;
    const needs = [];
    if (ch.app && config?.hasApprovalPassword === false) {
      needs.push("a 6-digit approval password on Profile");
    }
    if (ch.stk && config?.hasPhone === false) {
      needs.push("your phone number on Profile");
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
      appDetail: document.querySelector("[data-pin-approval-detail]"),
      stkBackdrop: document.querySelector("[data-stk-approval-backdrop]"),
      stkMessage: document.querySelector("[data-stk-approval-message]"),
      stkStatus: document.querySelector("[data-stk-approval-status]"),
      stkError: document.querySelector("[data-stk-approval-error]"),
      stkUseApp: document.querySelector("[data-stk-approval-use-app]"),
      stkCancel: document.querySelectorAll("[data-stk-approval-cancel]"),
      stkDetail: document.querySelector("[data-stk-approval-detail]"),
    };

    let pendingForm = null;
    let approvalPin = "";
    let stkPollTimer = null;
    let active = false;
    let deferredForm = null;
    let deferredHandler = null;

    const setContext = (form) => {
      const detail = [form.getAttribute("data-approval-title"), form.getAttribute("data-approval-body")]
        .filter(Boolean)
        .join(" · ");
      if (dom.appDetail) {
        dom.appDetail.textContent = detail;
        dom.appDetail.hidden = !detail;
      }
      if (dom.stkDetail) {
        dom.stkDetail.textContent = detail;
        dom.stkDetail.hidden = !detail;
      }
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
      if (dom.stkError) {
        dom.stkError.hidden = true;
        dom.stkError.textContent = "";
      }
      if (dom.stkStatus) dom.stkStatus.textContent = "Waiting for M-Pesa…";
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

    const postApprove = async (form, stkOperationId = "") => {
      attachHidden(form, "approval_pin", approvalPin);
      attachHidden(form, "stk_approval_operation_id", stkOperationId);
      const target = form;
      reset();

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

    const pollStk = (operationId) =>
      new Promise((resolve, reject) => {
        if (!config.stkPollUrl) {
          reject(new Error("Missing STK poll URL."));
          return;
        }
        const pollUrl = `${config.stkPollUrl}${operationId}/`;
        const finish = (ok, message) => {
          stopStkPoll();
          if (ok) resolve(operationId);
          else reject(new Error(message || "M-Pesa approval failed."));
        };

        const tick = async () => {
          try {
            const response = await fetch(pollUrl, {
              headers: { "X-Requested-With": "XMLHttpRequest" },
            });
            if (!response.ok) throw new Error("Could not check STK status.");
            const data = await response.json();
            if (dom.stkStatus) {
              dom.stkStatus.textContent = data.summary || "Waiting for M-Pesa…";
            }
            if (data.complete) {
              finish(
                Boolean(data.success),
                data.summary ||
                  "M-Pesa did not confirm this approval. Check your phone or try again.",
              );
            }
          } catch (err) {
            finish(false, err.message || "Could not check STK status.");
          }
        };

        tick();
        stkPollTimer = window.setInterval(tick, 2500);
      });

    const openApp = (form) => {
      if (!dom.appBackdrop || !dom.appInput) {
        window.alert("Approval password prompt is not available on this page.");
        reset();
        return;
      }
      pendingForm = form;
      setContext(form);
      dom.appInput.value = "";

      const needsPassword = config.hasApprovalPassword === false;
      const needsPhone = config.hasPhone === false;
      if (dom.appSetup) dom.appSetup.hidden = !needsPassword;
      if (dom.appPhoneSetup) {
        dom.appPhoneSetup.hidden = !(needsPhone && ch.stk && !needsPassword);
      }
      const showStkAlt = Boolean(
        ch.stk && config.hasPhone !== false && (config.dualApproval || needsPassword),
      );
      if (dom.appUseStk) dom.appUseStk.hidden = !showStkAlt;

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

      if (dom.stkUseApp) {
        dom.stkUseApp.hidden = !(ch.app && config.dualApproval && appReady(config, ch));
      }
      if (dom.stkMessage) {
        dom.stkMessage.textContent =
          "Sending an STK prompt to your phone. Enter your M-Pesa PIN when it arrives.";
      }
      if (dom.stkStatus) dom.stkStatus.textContent = "Sending STK prompt…";
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
        if (dom.stkMessage) {
          dom.stkMessage.textContent =
            data.summary || "Check your phone and enter your M-Pesa PIN to approve this payment.";
        }
        if (dom.stkStatus) dom.stkStatus.textContent = "Waiting for M-Pesa PIN…";

        const operationId = await pollStk(data.operation_id);
        await postApprove(form, operationId);
      } catch (err) {
        stopStkPoll();
        if (dom.stkError) {
          dom.stkError.textContent = err.message || "PIN approval failed.";
          dom.stkError.hidden = false;
        }
        if (dom.stkStatus) {
          dom.stkStatus.textContent = "STK prompt not completed. Fix the issue below or cancel.";
        }
        active = true;
        pendingForm = form;
        if (visible) showEl(dom.stkBackdrop);
      }
    };

    const pickChannel = ({ manual = false } = {}) => {
      const onlyApp = ch.app && !ch.stk;
      const onlyStk = ch.stk && !ch.app;
      const both = ch.app && ch.stk;

      if (onlyApp) return "app";
      if (onlyStk) return "stk";

      if (both) {
        if (manual || tabVisible()) {
          if (appReady(config, ch)) return "app";
          if (stkReady(config, ch)) return "stk";
          return ch.app ? "app" : "stk";
        }
        if (stkReady(config, ch)) return "stk";
        if (appReady(config, ch)) return "app";
        return ch.stk ? "stk" : "app";
      }
      return "none";
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
      active = true;
      pendingForm = form;
      approvalPin = "";

      const channel = pickChannel({ manual });

      if (channel === "app") {
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
      if (misconfigAlert(config)) return;
      if (profileIncompleteAlert(config)) return;
      postApprove(form);
    };

    const submitAppPin = () => {
      if (!pendingForm || !dom.appInput) return;
      if (config.hasApprovalPassword === false) {
        if (stkReady(config, ch)) {
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
      closeApp();
      postApprove(form);
    };

    document.addEventListener(
      "submit",
      (event) => {
        const form = event.target;
        if (!(form instanceof HTMLFormElement) || !form.hasAttribute("data-approval-form")) {
          return;
        }
        if (!approvalRequired(config)) return;
        event.preventDefault();
        event.stopPropagation();
        beginApprovalFlow(form, { force: true, manual: true });
      },
      true,
    );

    dom.appSubmit?.addEventListener("click", submitAppPin);
    dom.appUseStk?.addEventListener("click", () => {
      if (!pendingForm) return;
      const form = pendingForm;
      closeApp();
      active = true;
      pendingForm = form;
      runStk(form, { visible: true });
    });
    dom.stkUseApp?.addEventListener("click", () => {
      if (!pendingForm) return;
      const form = pendingForm;
      closeStk();
      active = true;
      pendingForm = form;
      openApp(form);
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
    dom.stkBackdrop?.addEventListener("click", (event) => {
      if (event.target === dom.stkBackdrop) cancel();
    });

    api.isActive = () => active;
    api.beginApprovalFlow = beginApprovalFlow;

    flowReady = true;
    window.__approvalFlowReady = true;

    return { config, csrf, beginApprovalFlow, isActive: () => active };
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
        if (window.nexusApproval?.ready) return;
        triggerFromForm(form, event, runtime);
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

    document.addEventListener(
      "click",
      (event) => {
        const btn = event.target.closest(
          "[data-approval-trigger], form[data-approval-form] .btn-primary.btn-small",
        );
        if (!btn) return;
        const form = btn.closest("form[data-approval-form]");
        if (!form) return;
        triggerFromForm(form, event, runtime);
      },
      true,
    );

    window.nexusApproval = {
      ready: true,
      config,
      isActive: () => (runtime?.isActive || api.isActive)(),
      beginApprovalFlow: runtime.beginApprovalFlow,
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
