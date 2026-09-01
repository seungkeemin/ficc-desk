/* ficc-desk — 인라인 입력
 *
 * 프레임워크 없음. 규칙은 세 가지다.
 *
 *   1. 저장 버튼을 만들지 않는다.
 *      서술형은 타이핑이 멎으면(800ms), 숫자는 칸을 떠나거나 Enter 를 치면 저장된다.
 *      숫자에 시간 디바운스를 걸지 않는 이유: market_observation_log 는 append-only 라
 *      삭제가 불가능한데(CLAUDE.md 4), '2.845' 를 치는 도중 '2.' 가 저장되면 그 쓰레기
 *      관측이 영구히 남는다. Tab 이동이 blur 를 내므로 키보드 완주에는 지장이 없다.
 *
 *   2. 숫자는 서버가 포맷한다.
 *      자릿수 규칙이 여기에도 있으면 화면 최초 렌더와 저장 후 렌더가 언젠가 어긋난다.
 *      클라이언트는 서버가 만든 문자열을 그대로 넣을 뿐이다.
 *
 *   3. 실패는 침묵하지 않는다.
 *      토스트도 알림창도 만들지 않는다(화면에 자리가 없고 규칙이 금지한다). 대신 해당
 *      칸에 경고 테두리를 켜고, **사용자가 친 값을 지우지 않는다.**
 */
(function () {
  "use strict";

  var root = document.documentElement;
  var OBS_DATE = root.dataset.obsDate;
  var LIVE = root.dataset.mode === "live";

  var MISSING = "미수집";
  var NO_DELTA = "—";
  var TEXT_DEBOUNCE = 800;
  var TOGGLE_DEBOUNCE = 200;

  // ------------------------------------------------------------------ 유틸

  /** 연속 갱신에서도 애니메이션이 다시 재생되도록 클래스를 떼고 리플로를 강제한다. */
  function flash(el) {
    if (!el) return;
    el.classList.remove("flash");
    void el.offsetWidth;
    el.classList.add("flash");
    el.addEventListener(
      "animationend",
      function () { el.classList.remove("flash"); },
      { once: true }
    );
  }

  function cellOf(fieldKey) {
    return document.querySelector('.cell[data-field="' + fieldKey + '"]');
  }

  function setText(selector, value) {
    var el = document.querySelector(selector);
    if (el && value !== undefined && value !== null) el.textContent = String(value);
  }

  /** 저장 실패를 그 칸에서 보이게 한다. 값은 건드리지 않는다. */
  function markInvalid(el, bad) {
    if (!el) return;
    el.classList.toggle("is-invalid", !!bad);
  }

  function send(method, url, body) {
    return fetch(url, {
      method: method,
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body)
    }).then(function (response) {
      if (!response.ok) {
        return response.json().catch(function () { return {}; }).then(function (data) {
          var error = new Error((data && data.detail) || response.statusText);
          error.status = response.status;
          throw error;
        });
      }
      return response.status === 204 ? null : response.json();
    });
  }

  // 저장이 끝나기 전에 새로고침하면 마지막 한 줄이 날아간다. 대기 중인 것을 추적한다.
  var pending = {};
  var timers = {};

  function debounce(key, delay, fn) {
    if (timers[key]) clearTimeout(timers[key]);
    pending[key] = fn;
    timers[key] = setTimeout(function () { flush(key); }, delay);
  }

  function flush(key) {
    if (timers[key]) { clearTimeout(timers[key]); delete timers[key]; }
    var fn = pending[key];
    delete pending[key];
    if (fn) return fn();
  }

  function flushPending() {
    return Promise.all(Object.keys(pending).map(flush));
  }

  // --------------------------------------------------------- 스냅샷 셀 갱신

  /**
   * payload: { field_key: {value, delta, dir, mark, derived} }
   * value 가 null 이면 '미수집'. 0 으로 채우지 않는다 (CLAUDE.md 1).
   */
  function applyValues(payload) {
    Object.keys(payload || {}).forEach(function (fieldKey) {
      var cell = cellOf(fieldKey);
      if (!cell) return;

      var next = payload[fieldKey] || {};
      var valueEl = cell.querySelector('[data-role="value"]');
      var deltaEl = cell.querySelector('[data-role="delta"]');
      var markEl = cell.querySelector('[data-role="mark"]');
      var noteEl = cell.querySelector('[data-role="note"]');
      var missing = next.value === null || next.value === undefined;
      var changed = false;

      if (valueEl) {
        var text = missing ? "" : String(next.value);
        if (valueEl.tagName === "INPUT") {
          // 타이핑 중인 칸은 건드리지 않는다. 커서가 튀고 입력이 잘린다.
          if (valueEl !== document.activeElement && valueEl.value !== text) {
            valueEl.value = text;
            changed = true;
          }
        } else {
          var shown = missing ? MISSING : text;
          if (valueEl.textContent.trim() !== shown) {
            valueEl.textContent = shown;
            changed = true;
          }
        }
        cell.classList.toggle("cell--miss", missing);
      }

      if (deltaEl && next.delta !== undefined) {
        var delta = next.delta === null ? NO_DELTA : String(next.delta);
        if (deltaEl.textContent.trim() !== delta) {
          deltaEl.textContent = delta;
          changed = true;
        }
        if (next.dir) deltaEl.className = "cell__delta dir-" + next.dir;
      }

      // ᴹ 는 자동 수집값을 손으로 덮어쓴 순간 붙어야 한다. 안 붙으면 라벨이 거짓말한다.
      if (markEl && next.mark !== undefined) markEl.textContent = next.mark || "";
      // 오늘 값을 넣었으면 'as of 어제' / 'x 없음' 이 더는 사실이 아니다.
      if (noteEl && !missing) noteEl.textContent = "";

      if (changed) flash(cell);
    });
  }

  function applyHeader(header) {
    if (!header) return;
    setText('[data-role="manual-count"]', header.manual_count);
    setText('[data-role="miss-count"]', header.miss_count);
    setText('[data-role="streak"]', header.streak_days);
    setText('[data-role="undone"]', header.undone_today);
    setText('[data-role="total"]', header.total_today);
    if (header.total_today !== undefined && header.undone_today !== undefined) {
      setText('[data-role="done-today"]', header.total_today - header.undone_today);
      setText('[data-role="total-today"]', header.total_today);
    }
  }

  function applyUnchecked(count) {
    document.querySelectorAll('[data-role="unchecked"]').forEach(function (el) {
      el.textContent = String(count);
    });
    var item = document.querySelector('[data-role="unchecked-item"]');
    var foot = document.querySelector('[data-role="unchecked-foot"]');
    if (item) item.classList.toggle("is-hidden", !count);
    if (foot) foot.classList.toggle("is-hidden", !count);
  }

  // ------------------------------------------------------------ 스냅샷 저장

  function parseNumber(raw) {
    var text = String(raw).replace(/,/g, "").trim();
    if (!text) return undefined;              // 빈 칸은 저장하지 않는다. 삭제 API 는 없다
    var value = Number(text);
    return Number.isFinite(value) ? value : null;   // null = 숫자가 아니다
  }

  function saveObservation(input) {
    var cell = input.closest(".cell");
    var fieldKey = cell && cell.dataset.field;
    if (!fieldKey) return;

    var value = parseNumber(input.value);
    if (value === undefined) { markInvalid(input, false); return; }
    if (value === null) { markInvalid(input, true); return; }
    markInvalid(input, false);

    return send("PUT", "/api/observation", {
      obs_date: OBS_DATE, field_key: fieldKey, value: value
    }).then(function (data) {
      applyValues(data.cells);
      applyHeader(data.header);
    }).catch(function () {
      markInvalid(input, true);               // 값은 화면에 남는다
    });
  }

  function wireSnapshot() {
    document.querySelectorAll(".cell .cell__input").forEach(function (input) {
      var last = input.value;
      input.addEventListener("change", function () {
        if (input.value === last) return;
        last = input.value;
        saveObservation(input);
      });
      input.addEventListener("keydown", function (event) {
        if (event.key !== "Enter") return;
        event.preventDefault();
        last = input.value;
        saveObservation(input);
      });
      input.addEventListener("input", function () { markInvalid(input, false); });
    });
  }

  // -------------------------------------------------------------- 저널 저장

  function wireJournal() {
    document.querySelectorAll("[data-journal]").forEach(function (field) {
      var column = field.dataset.journal;
      var key = "journal:" + column;

      function save() {
        return send("PUT", "/api/journal", {
          obs_date: OBS_DATE, column: column, text: field.value
        }).then(function () {
          markInvalid(field, false);
        }).catch(function () {
          markInvalid(field, true);
        });
      }

      field.addEventListener("input", function () {
        debounce(key, TEXT_DEBOUNCE, save);
      });
      // 칸을 떠나면 기다리지 않는다. 다른 칸을 채우는 동안 여기 것이 미저장으로 남지 않게.
      field.addEventListener("blur", function () { flush(key); });
    });
  }

  // -------------------------------------------------------------- 루틴 체크

  function paintRoutine(button, done) {
    button.setAttribute("aria-checked", done ? "true" : "false");
    button.classList.toggle("routine--done", done && button.classList.contains("routine"));
    button.classList.toggle("weekly--done", done && button.classList.contains("weekly"));
    var box = button.querySelector(".routine__box, .weekly__box");
    if (box) box.textContent = done ? "☑" : "☐";
  }

  function wireRoutines() {
    document.querySelectorAll("[data-routine]").forEach(function (button) {
      button.addEventListener("click", function () {
        var next = button.getAttribute("aria-checked") !== "true";
        paintRoutine(button, next);           // 먼저 그리고 실패하면 되돌린다
        send("PUT", "/api/routine", {
          task_date: OBS_DATE,
          routine_key: button.dataset.routine,
          done: next
        }).then(function (data) {
          applyHeader(data.header);
          markInvalid(button, false);
        }).catch(function () {
          paintRoutine(button, !next);
          markInvalid(button, true);
        });
      });
    });
  }

  // ------------------------------------------------------ 무효화 조건 토글

  function paintPositions(positions) {
    (positions || []).forEach(function (position) {
      var broken = position.worst_state === "broken";
      var shaky = position.worst_state === "shaky";
      document.querySelectorAll('[data-position="' + position.id + '"]').forEach(function (el) {
        el.classList.toggle("is-broken", broken);
        el.classList.toggle("is-shaky", shaky);
      });
    });
  }

  function wireWatch() {
    document.querySelectorAll(".cond__radio").forEach(function (radio) {
      radio.addEventListener("change", function () {
        if (!radio.checked) return;
        var id = radio.dataset.invalidation;
        var block = radio.closest(".cond");
        if (block) {
          block.classList.remove("cond--unchecked");
          block.classList.toggle("cond--broken", radio.value === "broken");
        }
        // 화살표로 훑으면 저장이 연달아 난다. 마지막 값만 보낸다 (UPSERT 라 안전하다).
        debounce("cond:" + id, TOGGLE_DEBOUNCE, function () {
          return send("PUT", "/api/invalidation/" + id + "/check", {
            check_date: OBS_DATE, state: radio.value
          }).then(function (data) {
            applyUnchecked(data.unchecked_count);
            paintPositions(data.positions);
            markInvalid(block, false);
          }).catch(function () {
            markInvalid(block, true);
          });
        });
      });
    });
  }

  // ------------------------------------------------------------ 수동 마킹

  function wireMarks() {
    document.querySelectorAll(".blotter__mark").forEach(function (input) {
      var row = input.closest("tr");
      var ideaId = row && row.dataset.position;
      if (!ideaId) return;

      function save() {
        var value = parseNumber(input.value);
        if (value === undefined) { markInvalid(input, false); return; }
        if (value === null) { markInvalid(input, true); return; }
        markInvalid(input, false);

        return send("PUT", "/api/idea/" + ideaId + "/mark", {
          mark_date: OBS_DATE, level: value
        }).then(function (data) {
          row.querySelectorAll('[data-role="pnl"]').forEach(function (el) {
            el.textContent = data.pnl_bp;
            el.className = "num strong dir-" + data.dir;
          });
          var watchPnl = document.querySelector(
            '.wpos[data-position="' + ideaId + '"] [data-role="pnl"]');
          if (watchPnl) {
            watchPnl.textContent = data.pnl_bp + " bp";
            watchPnl.className = "num dir-" + data.dir;
          }
          flash(row);
        }).catch(function () {
          markInvalid(input, true);
        });
      }

      var last = input.value;
      input.addEventListener("change", function () {
        if (input.value === last) return;
        last = input.value;
        save();
      });
      input.addEventListener("keydown", function (event) {
        if (event.key !== "Enter") return;
        event.preventDefault();
        last = input.value;
        save();
      });
    });
  }

  // -------------------------------------------------------------- 이벤트

  function wireEvents() {
    document.querySelectorAll("[data-event]").forEach(function (field) {
      function save() {
        return send("PATCH", "/api/event/" + field.dataset.event, {
          column: field.dataset.column, value: field.value
        }).then(function () {
          markInvalid(field, false);
        }).catch(function () {
          markInvalid(field, true);
        });
      }

      if (field.tagName === "SELECT") {
        field.addEventListener("change", save);
        return;
      }
      var last = field.value;
      field.addEventListener("change", function () {
        if (field.value === last) return;
        last = field.value;
        save();
      });
      field.addEventListener("keydown", function (event) {
        if (event.key !== "Enter") return;
        event.preventDefault();
        last = field.value;
        save();
      });
    });

    var form = document.getElementById("event-add");
    if (!form) return;
    form.addEventListener("submit", function (event) {
      event.preventDefault();
      var data = new FormData(form);
      var name = String(data.get("name") || "").trim();
      if (!name) return;

      send("POST", "/api/event", {
        event_date: data.get("event_date"),
        region: data.get("region"),
        name: name
      }).then(function () {
        // 새 이벤트는 주 안의 정렬 위치가 달라진다. 한 줄만 끼워 넣으면 순서가 어긋난다.
        return flushPending().then(function () { location.reload(); });
      }).catch(function () {
        markInvalid(form.querySelector(".event-add__name"), true);
      });
    });
  }

  // ------------------------------------------------------ 아이디어 모달

  function wireIdeaModal() {
    var modal = document.getElementById("idea-modal");
    var form = document.getElementById("idea-form");
    if (!modal || !form) return;

    var errorEl = document.getElementById("idea-error");
    var opener = document.getElementById("idea-new");
    var conditions = document.getElementById("idea-conditions");

    function open() {
      if (modal.open) return;
      errorEl.textContent = "";
      modal.showModal();
      var first = form.querySelector('[name="position"]');
      if (first) first.focus();
    }

    if (opener) opener.addEventListener("click", open);

    var cancel = document.getElementById("idea-cancel");
    if (cancel) cancel.addEventListener("click", function () { modal.close(); });

    // <dialog> 는 Esc 로 닫히게 되어 있지만, 모달 머리에 'Esc 로 닫기' 라고 써 놓은 이상
    // 브라우저 기본 동작에만 기대지 않는다. 이미 닫혔으면 close() 는 아무 일도 안 한다.
    modal.addEventListener("keydown", function (event) {
      if (event.key !== "Escape") return;
      event.preventDefault();
      modal.close();
    });

    var addCondition = document.getElementById("idea-add-condition");
    if (addCondition) {
      addCondition.addEventListener("click", function () {
        var input = document.createElement("input");
        input.className = "field__input mcond";
        input.type = "text";
        input.name = "invalidation";
        conditions.appendChild(input);
        input.focus();
      });
    }

    // 입력 중이 아닐 때만. 'n' 을 치다가 모달이 열리면 그 타이핑이 사라진다.
    document.addEventListener("keydown", function (event) {
      if (event.key !== "n" && event.key !== "N") return;
      if (event.metaKey || event.ctrlKey || event.altKey) return;
      if (modal.open) return;
      var target = event.target;
      if (target instanceof Element &&
          target.closest("input, textarea, select, [contenteditable]")) return;
      event.preventDefault();
      open();
    });

    function values(name) {
      return Array.from(form.querySelectorAll('[name="' + name + '"]'))
        .map(function (el) { return el.value; })
        .filter(function (text) { return text.trim(); });
    }

    form.addEventListener("submit", function (event) {
      event.preventDefault();

      // 서버가 권위다 (CLAUDE.md 7). 여기는 왕복 한 번을 아끼는 것뿐이다.
      var invalidations = values("invalidation");
      if (!invalidations.length) {
        errorEl.textContent = "무효화 조건을 최소 1건 적어야 저장할 수 있다.";
        var first = conditions.querySelector("input");
        if (first) { first.classList.add("is-invalid"); first.focus(); }
        return;
      }

      var data = new FormData(form);
      var payload = {
        position: data.get("position"),
        strategy: data.get("strategy"),
        dv01_krw: Number(String(data.get("dv01_krw")).replace(/,/g, "")),
        holding_days: Number(data.get("holding_days")),
        level_unit: data.get("level_unit"),
        entry_level: Number(String(data.get("entry_level")).replace(/,/g, "")),
        target_level: Number(String(data.get("target_level")).replace(/,/g, "")),
        stop_level: Number(String(data.get("stop_level")).replace(/,/g, "")),
        opened_on: data.get("opened_on"),
        flow_agent: String(data.get("flow_agent") || "").trim() || null,
        pricing_key: data.get("pricing_key") || null,
        theses: values("thesis"),
        invalidations: invalidations
      };

      send("POST", "/api/idea", payload).then(function () {
        // 아이디어 1건이 블로터·워치·상단 바를 동시에 바꾼다. 부분 갱신을 손으로 짜면
        // 서버 렌더와 클라이언트 렌더가 두 벌이 된다. 하루 한 번 있을까 한 동작이다.
        return flushPending().then(function () { location.reload(); });
      }).catch(function (error) {
        errorEl.textContent = error.message || "저장하지 못했다.";
      });
    });
  }

  // ------------------------------------------------------------ 색 관례

  function wireConvention() {
    var toggle = document.getElementById("convention-toggle");
    if (!toggle) return;
    toggle.addEventListener("click", function () {
      var next = root.dataset.colorConvention === "kr" ? "bbg" : "kr";
      root.dataset.colorConvention = next;
      document.getElementById("convention-label").textContent =
        next === "kr" ? "국내색상" : "블룸버그색상";
      if (LIVE) {
        send("PUT", "/api/setting/color_convention", { value: next }).catch(function () {
          markInvalid(toggle, true);
        });
      }
    });
  }

  // ---------------------------------------------------------------- 기동

  wireConvention();

  if (LIVE) {
    wireSnapshot();
    wireJournal();
    wireRoutines();
    wireWatch();
    wireMarks();
    wireEvents();
    wireIdeaModal();

    // 탭을 덮거나 창을 닫아도 대기 중인 저장이 날아가지 않게 한다.
    document.addEventListener("visibilitychange", function () {
      if (document.visibilityState === "hidden") flushPending();
    });
    window.addEventListener("beforeunload", flushPending);
  }

  window.ficc = {
    flash: flash,
    applyValues: applyValues,
    flushPending: flushPending
  };
})();
