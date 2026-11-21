"""Stage F: self-contained local index.html viewer.

No server, no Internet, no CDN. All text coming from the XML is inserted
via DOM textContent (no innerHTML), so escaping is guaranteed; the embedded
JSON payload has '</' escaped to prevent premature </script> termination.
"""
import html
import json


def _json_for_script(payload):
    return (json.dumps(payload, ensure_ascii=False)
            .replace('</', '<\\/'))


def build_document(data):
    meta = data['meta']
    parts = []
    parts.append('<!DOCTYPE html>\n<html lang="ru">\n<head>\n')
    parts.append('<meta charset="utf-8">\n')
    parts.append('<title>Домены RuWordNet — локальный обозреватель</title>\n')
    parts.append('<style>\n')
    parts.append(_CSS)
    parts.append('</style>\n</head>\n<body>\n')
    parts.append('<h1>Домены RuWordNet — локальный обозреватель</h1>\n')

    parts.append('<p class="muted">Поставка: %s · версия инструмента: %s · '
                 'сборка: %s</p>\n'
                 % (html.escape(str(meta['source_dir'])),
                    html.escape(str(meta['tool_version'])),
                    html.escape(str(meta['started_at']))))

    # Summary
    parts.append('<h2>Сводные показатели</h2>\n<ul id="summary"></ul>\n')

    # Warnings
    parts.append('<h2>Предупреждения о циклах</h2>\n')
    parts.append('<div id="warnings" class="warnings"></div>\n')

    # Search + sort + table
    parts.append('<h2>Домены</h2>\n')
    parts.append('<div class="controls">\n')
    parts.append('<input id="q" type="search" '
                 'placeholder="поиск по назвению или ID" size="40">\n')
    parts.append('<label>Сортировка: <select id="sort">\n')
    parts.append('<option value="name">по алфавиту</option>\n')
    parts.append('<option value="size">по размеру (убыв.)</option>\n')
    parts.append('</select></label>\n')
    parts.append('<span id="count" class="muted"></span>\n')
    parts.append('</div>\n')
    parts.append('<table id="tbl"><thead><tr>'
                 '<th>ID</th><th>Название</th><th>всего</th><th>N</th>'
                 '<th>Adj</th><th>V</th><th>многодом.</th>'
                 '<th>родит.</th><th>потомки</th>'
                 '</tr></thead><tbody></tbody></table>\n')

    # Card
    parts.append('<h2>Карточка домена</h2>\n')
    parts.append('<div id="card" class="card muted">Выберите домен в '
                 'таблице.</div>\n')

    # Isolated
    parts.append('<h2>Изолированные домены (в непосредственном подграфе)'
                 '</h2>\n')
    parts.append('<ul id="isolated"></ul>\n')

    # Legend
    parts.append('<h2>Легенда</h2>\n<ul id="legend">\n')
    parts.append('<li><b>Исходное (из XML)</b>: названия, определения, '
                 'леммы, связи domain и hypernym (ID синсетов).</li>\n')
    parts.append('<li><b>Вычислено</b>: множество доменов (цели domain), '
                 'размеры, состав по частям речи, непосредственный и '
                 'проецированный графы, пересечения, примеры (детерминированная '
                 'выборка по порядку ID, не экспертный отбор).</li>\n')
    parts.append('<li>Направление гиперонимии в данных: частное → общее '
                 '(child_id = более общее; проверено аудитом 001).</li>\n')
    parts.append('</ul>\n')

    parts.append('<p class="muted">Локальный исследовательский результат. '
                 'Условия публикации не установлены.</p>\n')

    parts.append('<script id="data" type="application/json">\n')
    parts.append(_json_for_script(data))
    parts.append('\n</script>\n')
    parts.append('<script>\n')
    parts.append(_JS)
    parts.append('\n</script>\n</body>\n</html>\n')
    return ''.join(parts)


_CSS = """
body { font-family: system-ui, sans-serif; margin: 1.5rem; color: #1c1c1c;
       max-width: 70rem; }
h1 { font-size: 1.4rem; }
h2 { font-size: 1.1rem; margin-top: 1.4rem; border-bottom: 1px solid #ddd;
     padding-bottom: .2rem; }
table { border-collapse: collapse; width: 100%; font-size: .9rem; }
th, td { border: 1px solid #ccc; padding: .25rem .5rem; text-align: left; }
th { background: #f2f2f2; cursor: pointer; }
tbody tr:hover, tbody tr.sel { background: #eef4ff; cursor: pointer; }
.controls { display: flex; gap: 1rem; align-items: center; margin: .6rem 0; }
.muted { color: #666; }
.card { border: 1px solid #bbb; border-radius: 6px; padding: .8rem 1rem; }
.card h3 { margin: .2rem 0 .4rem; }
.sub { font-weight: 600; margin-top: .7rem; }
.warn { color: #a02020; }
ul { padding-left: 1.2rem; } li { margin: .15rem 0; }
.def { font-style: italic; }
.tag { display: inline-block; background: #e8e8f8; border-radius: 4px;
       padding: 0 .4rem; margin: 0 .3rem .3rem 0; font-size: .8rem; }
.path { font-family: monospace; font-size: .8rem; }
"""


_JS = r"""
'use strict';
function getJson() {
  var node = document.getElementById('data');
  return JSON.parse(node.textContent);
}
function el(tag, cls, text) {
  var e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text !== undefined && text !== null) e.textContent = text;
  return e;
}
var DATA = getJson();
var byId = {};
DATA.domains.forEach(function (d) { byId[d.domain_id] = d; });

// summary
(function () {
  var m = DATA.meta, ul = document.getElementById('summary');
  var items = [
    'синсетов в поставке: ' + m.synset_count,
    'уникальных доменов: ' + m.domain_count,
    'XML-записей domain: ' + m.domain_xml_rows +
      ' (уникальных назначений: ' + m.assignment_pairs + ')',
    'синсетов с прямым назначением: ' + m.assigned_synsets +
      ' (' + m.assigned_share_pct.toFixed(1) + '%)',
    'XML-записей hypernym между доменами: ' + m.hypernym_between_xml +
      ' (уникальных рёбер: ' + m.hypernym_between_unique + ')',
    'непосредственный подграф: узлов ' + m.direct_nodes +
      ', рёбер ' + m.direct_edges + '; без родителя: ' + m.direct_no_parent +
      '; изолированных: ' + m.direct_isolated +
      '; с несколькими родителями: ' + m.direct_multi_parent,
    'проецированный граф: рёбер ' + m.proj_total +
      ' (direct ' + m.proj_direct + ', via_non_domain ' + m.proj_via + ')'
  ];
  items.forEach(function (t) { ul.appendChild(el('li', null, t)); });
})();

// warnings
(function () {
  var box = document.getElementById('warnings');
  if (!DATA.warnings.length) {
    box.appendChild(el('p', null, 'Циклов не обнаружено.'));
    return;
  }
  DATA.warnings.forEach(function (w) {
    var p = el('p', 'warn');
    if (w.type === 'self_reachable') {
      p.textContent = 'Домен ' + w.domain + ' достижим из себя через ' +
        'недоменные узлы; собственным предком он не объявлен. Путь: ' +
        w.witness.join(' -> ');
    } else if (w.type === 'projected_domain_cycle') {
      p.textContent = 'Цикл между доменами в проецированном графе: ' +
        w.domains.join(', ');
    } else {
      p.textContent = JSON.stringify(w);
    }
    box.appendChild(p);
  });
})();

// isolated
(function () {
  var ul = document.getElementById('isolated');
  if (!DATA.isolated.length) {
    ul.appendChild(el('li', null, 'нет'));
    return;
  }
  DATA.isolated.forEach(function (id) {
    var li = el('li');
    li.appendChild(el('code', null, id));
    li.appendChild(document.createTextNode(' ' + byId[id].ruthes_name));
    ul.appendChild(li);
  });
})();

// table
var tbody = document.querySelector('#tbl tbody');
function nameOf(id) { return byId[id] ? byId[id].ruthes_name : id; }
function renderRows() {
  var q = document.getElementById('q').value.trim().toLowerCase();
  var mode = document.getElementById('sort').value;
  var list = DATA.domains.filter(function (d) {
    if (!q) return true;
    return d.ruthes_name.toLowerCase().indexOf(q) >= 0 ||
           d.domain_id.toLowerCase().indexOf(q) >= 0;
  });
  if (mode === 'name') {
    list.sort(function (a, b) {
      return a.ruthes_name.localeCompare(b.ruthes_name, 'ru');
    });
  } else {
    list.sort(function (a, b) { return b.assigned_count - a.assigned_count; });
  }
  while (tbody.firstChild) tbody.removeChild(tbody.firstChild);
  list.forEach(function (d) {
    var tr = el('tr');
    tr.dataset.id = d.domain_id;
    [d.domain_id, d.ruthes_name, d.assigned_count, d.count_N, d.count_Adj,
     d.count_V, d.multi_domain_assigned,
     d.parents_direct.length, d.children_direct.length]
      .forEach(function (v) { tr.appendChild(el('td', null, String(v))); });
    tr.addEventListener('click', function () {
      document.querySelectorAll('#tbl tbody tr.sel')
        .forEach(function (r) { r.classList.remove('sel'); });
      tr.classList.add('sel');
      showCard(d.domain_id);
    });
    tbody.appendChild(tr);
  });
  document.getElementById('count').textContent =
    'показано: ' + list.length + ' из ' + DATA.domains.length;
}
document.getElementById('q').addEventListener('input', renderRows);
document.getElementById('sort').addEventListener('change', renderRows);

// card
function showCard(id) {
  var d = byId[id], card = document.getElementById('card');
  while (card.firstChild) card.removeChild(card.firstChild);
  card.classList.remove('muted');
  var h = el('h3', null, d.ruthes_name + ' ');
  h.appendChild(el('code', null, d.domain_id));
  card.appendChild(h);
  if (d.definition) card.appendChild(el('p', 'def', d.definition));
  if (d.lemmas.length) {
    var p = el('p');
    p.appendChild(el('span', 'sub', 'Леммы: '));
    d.lemmas.forEach(function (l) { p.appendChild(el('span', 'tag', l)); });
    card.appendChild(p);
  }
  card.appendChild(el('p', null,
    'Прямо привязанных синсетов: ' + d.assigned_count +
    ' (N ' + d.count_N + ', Adj ' + d.count_Adj + ', V ' + d.count_V + ')' +
    '; из них с несколькими доменами: ' + d.multi_domain_assigned +
    '; гипернимов вне множества доменов: ' + d.hypernyms_outside));
  if (d.isolated) {
    card.appendChild(el('p', 'warn',
      'Изолирован в непосредственном подграфе доменов.'));
  }
  function linkList(title, ids) {
    var p = el('p');
    p.appendChild(el('span', 'sub', title));
    if (!ids.length) { p.appendChild(document.createTextNode(' нет')); }
    ids.forEach(function (pid) {
      p.appendChild(el('span', 'tag', pid + ' ' + nameOf(pid)));
    });
    return p;
  }
  card.appendChild(linkList('Непосредственные родительские домены (более общие): ',
                            d.parents_direct));
  card.appendChild(linkList('Непосредственные дочерние домены (более частные): ',
                            d.children_direct));
  var pp = el('p');
  pp.appendChild(el('span', 'sub',
    'Ближайшие доменные предки через общую гиперонимию: '));
  if (!d.projected.length) { pp.appendChild(document.createTextNode(' нет')); }
  d.projected.forEach(function (pr) {
    var tag = el('span', 'tag',
      pr.kind + ' (' + pr.path_length + '): ' +
      pr.path.map(nameOf).join(' -> '));
    pp.appendChild(tag);
  });
  card.appendChild(pp);
  var ex = el('p');
  ex.appendChild(el('span', 'sub',
    'Примеры привязанных синсетов (выборка по порядку ID, не экспертный ' +
    'отбор типичных представителей):'));
  card.appendChild(ex);
  ['N', 'Adj', 'V'].forEach(function (pos) {
    (d.examples[pos] || []).forEach(function (s) {
      var li = el('li');
      li.appendChild(el('code', null, s.synset_id));
      li.appendChild(document.createTextNode(' ' + s.ruthes_name));
      if (s.definition) {
        li.appendChild(document.createTextNode(' — ' + s.definition));
      }
      ex.appendChild(li);
    });
  });
}
renderRows();
"""


def write_index_html(path, data):
    with open(path, 'w', encoding='utf-8') as fh:
        fh.write(build_document(data))
