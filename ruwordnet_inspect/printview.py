"""Static print/PDF digest of the domain catalog (for non-technical readers).

Pure static HTML, no JavaScript, no external resources: designed to be
turned into PDF either by the browser's Print -> Save as PDF or by a
headless Chrome run (see build notes). Content follows the owner's brief:
numbered list of all domains with word counts by part of speech, plus an
explicit explanation of multi-domain membership; no graph properties, no
diagnostics, no interactive elements.
"""


def build_print_document(data, multi_domain_synsets=None):
    domains = sorted(
        data['domains'],
        key=lambda d: (-d['assigned_count'], d['ruthes_name']))
    meta = data['meta']
    if multi_domain_synsets is None:
        multi_domain_synsets = meta.get('multi_domain_synsets', 0)

    total = sum(d['assigned_count'] for d in domains)
    total_n = sum(d['count_N'] for d in domains)
    total_adj = sum(d['count_Adj'] for d in domains)
    total_v = sum(d['count_V'] for d in domains)

    parts = []
    parts.append('<!DOCTYPE html>\n<html lang="ru">\n<head>\n')
    parts.append('<meta charset="utf-8">\n')
    parts.append('<title>Тематические категории RuWordNet</title>\n')
    parts.append('<style>\n')
    parts.append(_PRINT_CSS)
    parts.append('</style>\n</head>\n<body>\n')

    parts.append('<h1>Тематические категории RuWordNet</h1>\n')
    parts.append('<p class="sub">Всего категорий: %d · локальная поставка '
                 'RuWordNet, архив rwn-2021-05-02 · сборка %s</p>\n'
                 % (len(domains), meta['started_at'][:10]))

    parts.append(
        '<p class="intro">В поставке найдено %d тематические категории. '
        'Все они взяты из данных как есть: ни одна не добавлена и не '
        'придумана. Категория — это понятие словаря («БИОЛОГИЯ», «СПОРТ», '
        '«МУЗЫКАЛЬНОЕ ИСКУССТВО»), с которым связаны группы близких по '
        'смыслу слов. Ниже все категории пронумерованы и перечислены от '
        'крупных к узким; для каждой указано, сколько слов (значений) в неё '
        'входит и по частям речи. Всего к категориям привязано %s из %s '
        'значений (около %d%%).</p>\n'
        % (len(domains), _num(meta['assigned_synsets']),
           _num(meta['synset_count']), round(meta['assigned_share_pct'])))

    if multi_domain_synsets and meta['assigned_synsets']:
        share = 100.0 * multi_domain_synsets / meta['assigned_synsets']
        parts.append(
            '<p class="important"><b>Значения на пересечении тем.</b> '
            'Одно и то же значение может входить сразу в несколько '
            'категорий: таковых %s из %s привязанных значений, то есть '
            'около %d%%. Например, МЯСО числится одновременно в категориях '
            '«ЖИВОТНОВОДСТВО» и «СЕЛЬСКОЕ ХОЗЯЙСТВО»: это значение стоит на '
            'пересечении двух тем. Это свойство данных, а не ошибка: '
            'составители словаря отмечали все тематические сферы, к которым '
            'относится значение.</p>\n'
            % (_num(multi_domain_synsets), _num(meta['assigned_synsets']),
               round(share)))

    parts.append('<table>\n<thead>\n<tr>'
                 '<th class="num">№</th><th>Категория</th>'
                 '<th class="num">Всего слов</th>'
                 '<th class="num">Существительные</th>'
                 '<th class="num">Прилагательные</th>'
                 '<th class="num">Глаголы</th>'
                 '</tr>\n</thead>\n<tbody>\n')
    for i, d in enumerate(domains, 1):
        parts.append('<tr><td class="num">%d</td><td>%s</td>'
                     '<td class="num">%s</td><td class="num">%s</td>'
                     '<td class="num">%s</td><td class="num">%s</td></tr>\n'
                     % (i, _esc(d['ruthes_name']),
                        _num(d['assigned_count']), _num(d['count_N']),
                        _num(d['count_Adj']), _num(d['count_V'])))
    parts.append('</tbody>\n<tfoot>\n<tr>'
                 '<td class="num"></td><td>Итого назначений</td>'
                 '<td class="num">%s</td><td class="num">%s</td>'
                 '<td class="num">%s</td><td class="num">%s</td></tr>\n'
                 '</tfoot>\n</table>\n'
                 % (_num(total), _num(total_n), _num(total_adj), _num(total_v)))

    parts.append(
        '<p class="note">Числа в таблице — не отдельные слова, а синсеты: '
        'группы близких по смыслу слов (например, «ОКЕАН», «ОКЕАНЫ», '
        '«океанический» в одном значении). Поскольку одно значение может '
        'входить в несколько категорий (см. выше), «Итого назначений» '
        'больше числа разных привязанных значений (%s).</p>\n'
        % _num(meta['assigned_synsets']))
    parts.append('<p class="note">Категории связаны между собой иерархией '
                 '«частное — общее», но в этом документе связи не '
                 'показаны — представлен простой список.</p>\n')

    parts.append('<p class="origin">Локальный исследовательский результат. '
                 'Условия публикации не установлены. Источник: локальная '
                 'выгрузка RuWordNet (архив rwn-2021-05-02), связи '
                 '«domain» без изменений.</p>\n')

    parts.append('</body>\n</html>\n')
    return ''.join(parts)


def _num(n):
    """Format integers with spaces as thousand separators (12 345)."""
    return '{:,}'.format(n).replace(',', ' ')


def _esc(s):
    return (str(s).replace('&', '&amp;').replace('<', '&lt;')
            .replace('>', '&gt;'))


_PRINT_CSS = """
@page { size: A4; margin: 14mm 12mm; }
html { -webkit-print-color-adjust: exact; }
body { font-family: 'DejaVu Sans', 'Liberation Sans', Arial, sans-serif;
       font-size: 9.5pt; color: #111; margin: 0; line-height: 1.25; }
h1 { font-size: 15pt; margin: 0 0 2pt; }
.sub { color: #444; font-size: 9pt; margin: 0 0 8pt; }
.intro { margin: 0 0 8pt; text-align: justify; }
.important { border-left: 2.5pt solid #555; padding-left: 7pt;
             margin: 0 0 10pt; text-align: justify; }
table { width: 100%; border-collapse: collapse; }
th, td { border: 0.5pt solid #999; padding: 1.6pt 4pt; vertical-align: top; }
th { background: #eee; font-size: 9pt; text-align: left; }
thead { display: table-header-group; }
tfoot { display: table-row-group; }  /* keep the totals row only at table end */
tr { page-break-inside: avoid; }
td.num, th.num { text-align: right; white-space: nowrap; }
td:first-child, th:first-child { text-align: right; }
tfoot td { font-weight: bold; background: #f6f6f6; }
.note { font-size: 8.5pt; color: #333; margin: 6pt 0 0; }
.origin { font-size: 8.5pt; color: #555; margin-top: 10pt;
          border-top: 0.5pt solid #999; padding-top: 4pt; }
"""


def write_print_html(path, data, multi_domain_synsets=None):
    with open(path, 'w', encoding='utf-8') as fh:
        fh.write(build_print_document(data, multi_domain_synsets))
