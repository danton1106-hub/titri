(function () {
  var key = 'titri-watchlist-v1';
  function getList() {
    try { return JSON.parse(localStorage.getItem(key) || '[]'); }
    catch (error) { return []; }
  }
  function update() {
    var list = getList();
    document.querySelectorAll('[data-watch-id]').forEach(function (button) {
      var saved = list.some(function (item) { return item.id === button.dataset.watchId; });
      button.classList.toggle('is-saved', saved);
      button.setAttribute('aria-pressed', saved ? 'true' : 'false');
      button.title = saved ? 'Ubrat iz moih prosmotrov' : 'Dobavit v moi prosmotry';
      if (button.classList.contains('card-mark')) button.textContent = saved ? '+' : '+';
    });
    document.querySelectorAll('[data-watch-count]').forEach(function (node) { node.textContent = list.length; });
  }
  document.addEventListener('click', function (event) {
    var button = event.target.closest('[data-watch-id]');
    if (!button) return;
    event.preventDefault(); event.stopPropagation();
    var list = getList(), id = button.dataset.watchId;
    var index = list.findIndex(function (item) { return item.id === id; });
    if (index >= 0) list.splice(index, 1);
    else list.push({ id: id, title: button.dataset.watchTitle || '', url: button.dataset.watchUrl || location.href });
    localStorage.setItem(key, JSON.stringify(list)); update();
  });
  document.addEventListener('DOMContentLoaded', function () {
    var parts = new Intl.DateTimeFormat('ru-RU', { timeZone: 'Europe/Moscow', day: '2-digit', month: '2-digit', year: 'numeric' }).formatToParts(new Date());
    var values = Object.fromEntries(parts.filter(function (p) { return p.type !== 'literal'; }).map(function (p) { return [p.type, p.value]; }));
    document.querySelectorAll('[data-current-date]').forEach(function (node) { node.textContent = values.day + ' / ' + values.month + ' / ' + values.year; });
    update();
  });
})();
