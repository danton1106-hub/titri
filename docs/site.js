/* Портал «Титры» — клиентский слой.

Единый контракт хранилища, совпадающий с будущим личным кабинетом:
    {content_id, content_type, added_at, title, url, status}
content_id всегда стабильный внешний идентификатор вида tmdb:123456,
никогда не название и не позиция в массиве. После появления аккаунтов
эти же записи переносятся на сервер через TitriList.list().
*/
(function () {
  "use strict";

  var KEY = "titri-watchlist-v2";
  var LEGACY_KEYS = ["titri-watchlist-v1", "titri-watchlist"];
  var SCHEMA_VERSION = 2;

  /* ---------- хранилище ----------

     Формат записи:
       { content_id, content_type, title, url, poster, status, added_at }
     content_id — стабильный внешний идентификатор вида tmdb:123456.
     Название и постер здесь только снимок для интерфейса, чтобы список
     читался без обращения к каталогу. После появления аккаунтов этот же
     формат уйдёт на сервер без переделки интерфейса.
  */

  function normalize(raw) {
    var out = [];
    (raw || []).forEach(function (item) {
      if (!item || !item.content_id) return;
      out.push({
        content_id: String(item.content_id),
        content_type: item.content_type || "content",
        title: item.title || "",
        url: item.url || "",
        poster: item.poster || "",
        status: item.status || "want",
        added_at: item.added_at || new Date().toISOString()
      });
    });
    return out;
  }

  function readKey(key) {
    try {
      var parsed = JSON.parse(localStorage.getItem(key) || "null");
      if (!parsed) return null;
      if (Array.isArray(parsed)) return normalize(parsed);
      if (Array.isArray(parsed.items)) return normalize(parsed.items);
      return null;
    } catch (error) {
      return null;
    }
  }

  function load() {
    /* Новый формат: объект с версией и массивом items. */
    try {
      var stored = JSON.parse(localStorage.getItem(KEY) || "null");
      if (stored && Array.isArray(stored.items)) {
        return { version: stored.version || SCHEMA_VERSION, items: normalize(stored.items) };
      }
    } catch (error) { /* повреждённые данные лечим миграцией ниже */ }

    /* Миграция: старые ключи не теряем. */
    var legacy = null;
    for (var i = 0; i < LEGACY_KEYS.length; i++) {
      legacy = readKey(LEGACY_KEYS[i]);
      if (legacy) break;
    }
    legacy = legacy || [];
    var migrated = { version: SCHEMA_VERSION, items: legacy };
    persist(migrated);
    return migrated;
  }

  function persist(state) {
    try {
      localStorage.setItem(KEY, JSON.stringify(state));
      LEGACY_KEYS.forEach(function (key) { localStorage.removeItem(key); });
    } catch (error) {
      /* приватный режим: список не сохранится между визитами */
    }
    notify();
  }

  function list() { return load().items; }

  function has(id) {
    return list().some(function (item) { return item.content_id === id; });
  }

  function add(entry) {
    var state = load();
    if (state.items.some(function (item) { return item.content_id === entry.content_id; })) return;
    state.items.push(entry);
    persist(state);
    render();
  }

  function remove(id) {
    var state = load();
    state.items = state.items.filter(function (item) { return item.content_id !== id; });
    persist(state);
    render();
  }

  function toggle(id, entry) {
    if (has(id)) remove(id);
    else add(entry);
  }

  var subscribers = [];
  function subscribe(handler) {
    if (typeof handler !== "function") return function () {};
    subscribers.push(handler);
    return function () {
      subscribers = subscribers.filter(function (item) { return item !== handler; });
    };
  }

  function notify() {
    subscribers.forEach(function (handler) {
      try { handler(list()); } catch (error) { /* подписчик не должен ломать список */ }
    });
  }

  /* ---------- отрисовка ---------- */

  var TYPE_LABELS = {
    movie: "фильм",
    series: "сериал",
    anime: "аниме",
    reality: "реалити",
    competition: "соревнование",
    game_show: "игровое шоу",
    talk_show: "ток-шоу",
    comedy_show: "юмористическое шоу",
    web_show: "web-проект",
    special: "спецвыпуск",
    content: "проект"
  };

  function escape(text) {
    return String(text == null ? "" : text)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  }

  function typeLabel(type) {
    return TYPE_LABELS[type] || TYPE_LABELS.content;
  }

  function render() {
    var items = list();
    var total = items.length;

    document.querySelectorAll("[data-watch-count]").forEach(function (node) {
      node.textContent = total;
    });

    document.querySelectorAll("[data-watch-id]").forEach(function (button) {
      var saved = items.some(function (item) { return item.content_id === button.dataset.watchId; });
      button.classList.toggle("is-saved", saved);
      button.setAttribute("aria-pressed", saved ? "true" : "false");
      var title = saved ? "Убрать из моего списка" : "Добавить в мой список";
      if (button.classList.contains("card-mark")) {
        button.textContent = saved ? "\u2713" : "+";
      } else if (button.classList.contains("slide-watch")) {
        button.textContent = saved ? "\u2713 В моём списке" : "+ В мой список";
      } else {
        button.textContent = saved ? "\u2713 В моём списке" : "+ В мой список";
      }
      button.setAttribute("aria-label", title);
      button.title = title;
    });

    var panelList = document.querySelector("[data-watch-list]");
    if (panelList) {
      panelList.innerHTML = items.map(function (item) {
        var poster = item.poster
          ? '<img class="watch-poster" src="' + escape(item.poster) + '" alt="" loading="lazy">'
          : '<span class="watch-poster"></span>';
        var meta = typeLabel(item.content_type);
        return '<li class="watch-item"><a href="' + escape(item.url) + '">' + poster
          + '<span class="watch-text"><b>' + escape(item.title) + '</b>'
          + '<span class="watch-sub">' + escape(meta) + '</span></span></a>'
          + '<button class="watch-remove" type="button" data-watch-remove="' + escape(item.content_id)
          + '" aria-label="Убрать ' + escape(item.title) + ' из моего списка" title="Убрать">\u2212</button></li>';
      }).join("");
      var empty = document.querySelector("[data-watch-empty]");
      if (empty) empty.hidden = total > 0;
    }

    var grid = document.getElementById("my-list-grid");
    if (grid) {
      grid.innerHTML = items.map(function (item) {
        return '<article class="card my-item"><a href="' + escape(item.url) + '">'
          + '<h2 class="card-title h3">' + escape(item.title) + "</h2></a>"
          + '<div class="card-meta">' + escape(typeLabel(item.content_type)) + "</div>"
          + '<button class="btn btn-ghost my-remove" type="button" data-watch-remove="'
          + escape(item.content_id) + '">Убрать из списка</button></article>';
      }).join("");
      var pageEmpty = document.getElementById("my-list-empty");
      if (pageEmpty) pageEmpty.hidden = total > 0;
      var counter = document.getElementById("my-list-total");
      if (counter) counter.textContent = total;
    }
  }

  /* ---------- раскрывающаяся панель «мой список» ---------- */

  function watchPanel() {
    var root = document.querySelector("[data-watch-root]");
    if (!root) return;
    var button = root.querySelector(".bookmark-btn");
    var panel = root.querySelector(".watch-panel");
    if (!button || !panel) return;

    function setOpen(open) {
      button.setAttribute("aria-expanded", String(open));
      panel.hidden = !open;
    }

    button.addEventListener("click", function (event) {
      event.preventDefault();
      setOpen(button.getAttribute("aria-expanded") !== "true");
    });

    root.addEventListener("keydown", function (event) {
      if (event.key === "Escape") {
        setOpen(false);
        button.focus();
      }
    });

    document.addEventListener("click", function (event) {
      if (!root.contains(event.target)) setOpen(false);
    });
  }

  /* ---------- баннер-слайдер ---------- */

  function banner() {
    var box = document.querySelector("[data-slider]");
    if (!box) return;
    var slides = Array.prototype.slice.call(box.querySelectorAll("[data-slide]"));
    var dots = Array.prototype.slice.call(box.querySelectorAll("[data-slide-to]"));
    if (slides.length < 2) return;
    var index = 0;
    var timer = null;

    function show(next) {
      index = (next + slides.length) % slides.length;
      slides.forEach(function (slide, position) {
        slide.classList.toggle("is-active", position === index);
        if (position === index) slide.removeAttribute("aria-hidden");
        else slide.setAttribute("aria-hidden", "true");
      });
      dots.forEach(function (dot, position) {
        dot.classList.toggle("is-active", position === index);
        if (position === index) dot.setAttribute("aria-current", "true");
        else dot.removeAttribute("aria-current");
      });
    }

    function restart() {
      if (timer) clearInterval(timer);
      timer = setInterval(function () { show(index + 1); }, 7000);
    }

    var previous = box.querySelector("[data-slide-prev]");
    var next = box.querySelector("[data-slide-next]");
    if (previous) previous.addEventListener("click", function () { show(index - 1); restart(); });
    if (next) next.addEventListener("click", function () { show(index + 1); restart(); });
    dots.forEach(function (dot) {
      dot.addEventListener("click", function () { show(Number(dot.dataset.slideTo)); restart(); });
    });
    box.addEventListener("keydown", function (event) {
      if (event.key === "ArrowLeft") { show(index - 1); restart(); }
      if (event.key === "ArrowRight") { show(index + 1); restart(); }
    });
    box.addEventListener("mouseenter", function () { if (timer) clearInterval(timer); });
    box.addEventListener("mouseleave", restart);
    restart();
  }

  /* ---------- недельный календарь на главной ---------- */

  function homeCalendar() {
    var root = document.querySelector("[data-cal-panels]");
    var buttons = Array.prototype.slice.call(document.querySelectorAll("[data-cal-day]"));
    if (!root || !buttons.length) return;
    buttons.forEach(function (button) {
      button.addEventListener("click", function () {
        var day = button.dataset.calDay;
        var panel = root.querySelector('[data-cal-panel="' + day + '"]');
        if (!panel) return;
        buttons.forEach(function (item) {
          var active = item === button;
          item.classList.toggle("is-active", active);
          item.setAttribute("aria-pressed", active ? "true" : "false");
        });
        root.querySelectorAll("[data-cal-panel]").forEach(function (item) {
          item.hidden = item !== panel;
        });
      });
    });
  }

  /* ---------- дата и мобильное меню ---------- */

  function refreshDate() {
    var parts = new Intl.DateTimeFormat("ru-RU", {
      timeZone: "Europe/Moscow", day: "2-digit", month: "2-digit", year: "numeric"
    }).formatToParts(new Date());
    var value = {};
    parts.forEach(function (part) { if (part.type !== "literal") value[part.type] = part.value; });
    document.querySelectorAll("[data-current-date]").forEach(function (node) {
      node.textContent = value.day + " / " + value.month + " / " + value.year;
    });
  }

  function menu() {
    var toggle = document.querySelector(".menu-toggle");
    var nav = document.getElementById("mobile-nav");
    if (!toggle || !nav) return;
    function setOpen(open) {
      toggle.setAttribute("aria-expanded", String(open));
      nav.hidden = !open;
    }
    toggle.addEventListener("click", function () {
      setOpen(toggle.getAttribute("aria-expanded") !== "true");
    });
    [toggle, nav].forEach(function (node) {
      node.addEventListener("keydown", function (event) {
        if (event.key === "Escape") { setOpen(false); toggle.focus(); }
      });
    });
  }

  /* ---------- обработчики ---------- */

  document.addEventListener("click", function (event) {
    var removeButton = event.target.closest("[data-watch-remove]");
    if (removeButton) {
      event.preventDefault();
      remove(removeButton.dataset.watchRemove);
      return;
    }
    var mark = event.target.closest("[data-watch-id]");
    if (!mark) return;
    event.preventDefault();
    event.stopPropagation();
    toggle(mark.dataset.watchId, {
      content_id: mark.dataset.watchId,
      content_type: mark.dataset.watchType || "content",
      added_at: new Date().toISOString(),
      title: mark.dataset.watchTitle || "",
      url: mark.dataset.watchUrl || location.pathname,
      poster: mark.dataset.watchPoster || "",
      status: "want"
    });
  });

  document.addEventListener("DOMContentLoaded", function () {
    render();
    refreshDate();
    menu();
    watchPanel();
    banner();
    homeCalendar();
    /* Любое изменение списка обновляет счётчик, панель и страницу списка. */
    subscribe(render);
  });

  /* Публичный интерфейс: им воспользуется личный кабинет при переносе списка. */
  /* Публичный интерфейс. Личный кабинет подключится через ту же точку. */
  window.TitriList = {
    version: SCHEMA_VERSION,
    list: list,
    add: add,
    remove: remove,
    has: has,
    toggle: toggle,
    subscribe: subscribe
  };
})();
