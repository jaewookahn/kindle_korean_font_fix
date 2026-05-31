from calibre.customize import InterfaceActionBase


class EpubDiagnosticsPlugin(InterfaceActionBase):
    name                    = 'EPUB Diagnostics'
    description             = '선택 EPUB 의 폰트 / 페이지 데이터 / 챕터 정보 진단'
    supported_platforms     = ['windows', 'osx', 'linux']
    author                  = 'Custom'
    version                 = (1, 0, 0)
    minimum_calibre_version = (5, 0, 0)
    actual_plugin           = 'calibre_plugins.epub_diagnostics:EpubDiagnosticsAction'


from calibre.gui2.actions import InterfaceAction  # noqa: E402


try:
    from qt.core import QToolButton
except ImportError:
    from PyQt5.Qt import QToolButton


class EpubDiagnosticsAction(InterfaceAction):
    name        = 'EPUB Diagnostics'
    action_spec = ('EPUB 진단', 'dialog_information.png',
                   '선택한 EPUB 의 폰트 / 페이지 / 챕터 정보를 분석', None)
    popup_type  = QToolButton.MenuButtonPopup

    def genesis(self):
        try:
            from qt.core import QMenu
        except ImportError:
            from PyQt5.Qt import QMenu

        menu = QMenu(self.gui)
        menu.addAction('선택 책 진단').triggered.connect(self._run)
        menu.addAction('라이브러리 전체 스캔').triggered.connect(self._scan_all)
        self.qaction.setMenu(menu)
        self.qaction.triggered.connect(self._run)

    def _selected_book_ids(self):
        view = self.gui.library_view
        sm   = view.selectionModel()
        rows = sm.selectedRows() if sm is not None else []
        m    = view.model()
        ids, seen = [], set()
        for r in rows:
            try:
                bid = m.id(r.row())
            except Exception:
                continue
            if bid is None or bid in seen:
                continue
            seen.add(bid)
            ids.append(bid)
        return ids

    def _run(self):
        from calibre.gui2 import info_dialog
        try:
            from qt.core import (QDialog, QVBoxLayout, QTextEdit,
                                 QDialogButtonBox)
        except ImportError:
            from PyQt5.Qt import (QDialog, QVBoxLayout, QTextEdit,
                                  QDialogButtonBox)

        book_ids = self._selected_book_ids()
        if not book_ids:
            info_dialog(self.gui, 'EPUB 진단', '책을 먼저 선택하세요.', show=True)
            return

        db = self.gui.current_db
        sections = []
        for bid in book_ids:
            mi = db.new_api.get_metadata(bid)
            try:
                path = db.new_api.format_abspath(bid, 'EPUB')
            except Exception:
                path = None
            if not path:
                sections.append(
                    f'<h2>{_esc(mi.title)}</h2>'
                    '<p style="color:#888">EPUB 포맷 없음</p>'
                )
                continue
            try:
                rpt = _analyze(path)
            except Exception as e:
                sections.append(
                    f'<h2>{_esc(mi.title)}</h2>'
                    f'<p style="color:#c33">분석 실패: '
                    f'{type(e).__name__}: {_esc(str(e))}</p>'
                )
                continue
            sections.append(_format_html(mi.title, rpt))

        html = (
            '<style>'
            'body { font-family: -apple-system, sans-serif; font-size: 13px; }'
            'h2 { margin: 16px 0 6px; padding-bottom: 4px; '
            '     border-bottom: 1px solid #888; }'
            'h3 { margin: 12px 0 4px; font-size: 13px; color: #555; }'
            'table { border-collapse: collapse; margin: 4px 0 8px 8px; }'
            'td { padding: 2px 12px 2px 0; vertical-align: top; }'
            'td.lbl { color: #666; }'
            'td.name { font-weight: 600; }'
            'td.warn { color: #c33; font-weight: 600; }'
            'td.ok { color: #2a7; }'
            '.muted { color: #888; }'
            '.warn-box { background: #fff4e5; border-left: 3px solid #f93; '
            '            padding: 4px 10px; margin: 4px 0 8px; }'
            '.stats { color: #666; margin-top: 8px; }'
            '</style>'
            + ''.join(sections)
        )

        _show_html_dialog(self.gui, 'EPUB 진단 결과', html)

    def _scan_all(self):
        from calibre.gui2 import info_dialog
        try:
            from qt.core import QProgressDialog, Qt, QApplication
        except ImportError:
            from PyQt5.Qt import QProgressDialog, Qt, QApplication

        db = self.gui.current_db
        all_ids = list(db.new_api.all_book_ids())
        # filter to books with EPUB format
        epub_ids = [
            bid for bid in all_ids
            if 'EPUB' in (db.new_api.formats(bid) or ())
        ]
        if not epub_ids:
            info_dialog(self.gui, 'EPUB 진단',
                        '라이브러리에 EPUB 포맷 책이 없습니다.', show=True)
            return

        pd = QProgressDialog('스캔 준비...', '취소', 0, len(epub_ids), self.gui)
        pd.setWindowTitle('라이브러리 전체 스캔')
        pd.setWindowModality(Qt.WindowModal)
        pd.show()

        # categorized findings
        mismatched, missing_fonts, page_list = [], [], []
        errors = []

        for i, bid in enumerate(epub_ids):
            if pd.wasCanceled():
                break
            try:
                mi = db.new_api.get_metadata(bid)
                title = mi.title
            except Exception:
                title = f'book_id={bid}'
            pd.setLabelText(f'({i+1}/{len(epub_ids)}) {title[:55]}')
            pd.setValue(i)
            QApplication.processEvents()

            try:
                path = db.new_api.format_abspath(bid, 'EPUB')
            except Exception:
                path = None
            if not path:
                continue
            try:
                rpt = _analyze(path)
            except Exception as e:
                errors.append((title, f'{type(e).__name__}: {e}'))
                continue

            missing_all = {n for n in rpt['missing']
                           if n.lower() not in GENERIC}
            korean_only = {n for n in missing_all if _is_korean_font_name(n)}
            if rpt['name_mismatches']:
                mismatched.append((title, rpt))
            if korean_only:
                missing_fonts.append((title, sorted(korean_only)))
            if rpt['pagelist_ncx'] or rpt['pagelist_nav']:
                page_list.append(title)

        pd.setValue(len(epub_ids))

        html = _format_scan_html(
            scanned=min(i + 1, len(epub_ids)),
            total=len(epub_ids),
            mismatched=mismatched,
            missing_fonts=missing_fonts,
            page_list=page_list,
            errors=errors,
        )
        _show_html_dialog(self.gui, '라이브러리 스캔 결과', html)


def _show_html_dialog(parent, title, html):
    try:
        from qt.core import (QDialog, QVBoxLayout, QTextEdit, QDialogButtonBox)
    except ImportError:
        from PyQt5.Qt import (QDialog, QVBoxLayout, QTextEdit, QDialogButtonBox)
    dlg = QDialog(parent)
    dlg.setWindowTitle(title)
    dlg.resize(820, 680)
    lay = QVBoxLayout(dlg)
    edit = QTextEdit()
    edit.setReadOnly(True)
    edit.setHtml(html)
    lay.addWidget(edit)
    bb = QDialogButtonBox(QDialogButtonBox.Close)
    bb.rejected.connect(dlg.reject)
    bb.accepted.connect(dlg.accept)
    bb.button(QDialogButtonBox.Close).clicked.connect(dlg.accept)
    lay.addWidget(bb)
    dlg.exec()


def _format_scan_html(scanned, total, mismatched, missing_fonts, page_list, errors):
    css = (
        '<style>'
        'body { font-family: -apple-system, sans-serif; font-size: 13px; }'
        'h2 { margin: 16px 0 6px; padding-bottom: 4px; '
        '     border-bottom: 1px solid #888; }'
        'h3 { margin: 12px 0 4px; font-size: 13px; color: #555; }'
        'ul { margin: 4px 0 8px 18px; padding: 0; }'
        'li { margin: 2px 0; }'
        '.muted { color: #888; }'
        '.warn { color: #c33; }'
        '.ok { color: #2a7; }'
        '.summary { background: #f4f4f4; padding: 8px 12px; '
        '           border-radius: 4px; margin-bottom: 12px; }'
        '</style>'
    )
    out = [css]
    out.append(
        f'<div class="summary">스캔 {scanned} / {total} 권 · '
        f'<span class="warn">누락 폰트 {len(missing_fonts)}권</span> · '
        f'<span class="warn">페이지 데이터 {len(page_list)}권</span> · '
        f'<span class="muted">alias 불일치 {len(mismatched)}권 (자동 처리)</span></div>'
    )

    if not (mismatched or missing_fonts or page_list or errors):
        out.append('<p class="ok">문제 없음.</p>')
        return ''.join(out)

    if mismatched:
        out.append(f'<h2 style="color:#888">alias 불일치 ({len(mismatched)}권)</h2>')
        out.append('<p class="muted">@font-face alias 가 폰트 파일 내부 이름과 다름. '
                   'KFX 가 alias 를 무시하는 경우 Korean Font Fixer 가 자동 교체 — '
                   '대부분 문제 없음, 참고용.</p>')
        out.append('<ul>')
        for title, rpt in mismatched[:30]:
            pairs = ', '.join(
                f'{_esc(css)}→{_esc(actual)}'
                for css, _, actual in rpt['name_mismatches'][:2])
            extra = (f' …외 {len(rpt["name_mismatches"])-2}개'
                     if len(rpt['name_mismatches']) > 2 else '')
            out.append(
                f'<li class="muted">{_esc(title)} — {pairs}{extra}</li>')
        if len(mismatched) > 30:
            out.append(f'<li class="muted">... 외 {len(mismatched)-30}권</li>')
        out.append('</ul>')

    if missing_fonts:
        out.append(f'<h2>누락 폰트 ({len(missing_fonts)}권)</h2>')
        out.append('<p class="muted">EPUB 에 임베드되지 않은 폰트 참조. '
                   '킨들 /fonts/ 에 업로드 필요.</p>')
        out.append('<ul>')
        for title, fonts in missing_fonts:
            preview = ', '.join(_esc(f) for f in fonts[:5])
            extra = f' …외 {len(fonts)-5}개' if len(fonts) > 5 else ''
            out.append(
                f'<li><b>{_esc(title)}</b> '
                f'<span class="muted">— {preview}{extra}</span></li>')
        out.append('</ul>')

    if page_list:
        out.append(f'<h2>페이지 데이터 ({len(page_list)}권)</h2>')
        out.append('<p class="muted">NCX 또는 EPUB3 nav 의 page-list 가 KFX 페이지 추정과 충돌. '
                   'Korean Font Fixer 가 변환 시 자동 제거.</p>')
        out.append('<ul>')
        for title in page_list:
            out.append(f'<li>{_esc(title)}</li>')
        out.append('</ul>')

    if errors:
        out.append(f'<h2>분석 실패 ({len(errors)}권)</h2>')
        out.append('<ul>')
        for title, err in errors:
            out.append(
                f'<li><b>{_esc(title)}</b> '
                f'<span class="warn">— {_esc(err)}</span></li>')
        out.append('</ul>')

    return ''.join(out)


# ── 폰트 이름 추출 ────────────────────────────────────────────────────────────

def _all_font_names(font_data):
    """폰트 파일의 모든 family 관련 이름을 반환 (다국어 포함)."""
    try:
        from fontTools.ttLib import TTFont
        from io import BytesIO
    except Exception:
        # fallback: calibre 의 표준 이름만
        try:
            from calibre.utils.fonts.utils import get_all_font_names
            d = get_all_font_names(font_data)
            out = []
            for k in ('family_name', 'preferred_family_name',
                      'full_name', 'postscript_name'):
                v = d.get(k)
                if v:
                    out.append(v)
            # 중복 제거 (순서 유지)
            seen, uniq = set(), []
            for n in out:
                if n not in seen:
                    seen.add(n)
                    uniq.append(n)
            return uniq
        except Exception:
            return []

    try:
        tt = TTFont(BytesIO(font_data))
        # nameID 4 (full) 우선: weight 포함된 더 구체적인 이름
        order = (4, 16, 1)
        buckets = {nid: [] for nid in order}
        for r in tt['name'].names:
            if r.nameID in buckets:
                try:
                    v = r.toUnicode()
                except Exception:
                    continue
                if v:
                    buckets[r.nameID].append(v)
        out, seen = [], set()
        for nid in order:
            for v in buckets[nid]:
                if v not in seen:
                    seen.add(v); out.append(v)
        return out
    except Exception:
        return []


# ── EPUB 분석 ────────────────────────────────────────────────────────────────

def _analyze(epub_path):
    import zipfile
    rpt = {
        'embedded_fonts':   [],   # list of (family, src)
        'referenced_fonts': {},   # family → list of (file, selector)
        'pagelist_ncx':     [],   # files with <pageList>
        'pagelist_nav':     [],   # files with EPUB3 nav page-list
        'chapter_count':    0,
        'html_count':       0,
        'css_count':        0,
        'font_files':       [],
        'font_internal':    {},
        'name_mismatches':  [],
        'used_classes':     set(),  # HTML 에서 실제로 사용되는 클래스 이름
    }
    with zipfile.ZipFile(epub_path, 'r') as zf:
        names = zf.namelist()

        for n in names:
            low = n.lower()
            if low.endswith('.css'):
                rpt['css_count'] += 1
                _parse_css(zf.read(n), n, rpt)
            elif low.endswith(('.xhtml', '.html', '.htm')):
                rpt['html_count'] += 1
                try:
                    html = zf.read(n).decode('utf-8', errors='replace')
                except Exception:
                    html = ''
                import re
                if re.search(
                        r'<nav\b[^>]*epub:type=["\']page-list["\']',
                        html, re.IGNORECASE):
                    rpt['pagelist_nav'].append(n)
                # 사용된 클래스 수집
                for m in re.finditer(r'class\s*=\s*["\']([^"\']+)', html):
                    for cls in m.group(1).split():
                        rpt['used_classes'].add(cls)
            elif low.endswith('.ncx'):
                try:
                    text = zf.read(n).decode('utf-8', errors='replace')
                except Exception:
                    text = ''
                import re
                if re.search(r'<pageList\b', text, re.IGNORECASE):
                    rpt['pagelist_ncx'].append(n)
                rpt['chapter_count'] = len(
                    re.findall(r'<navPoint\b', text, re.IGNORECASE))
            elif low.endswith(('.otf', '.ttf', '.woff', '.woff2')):
                rpt['font_files'].append(n)
                if low.endswith(('.otf', '.ttf')):
                    names = _all_font_names(zf.read(n))
                    if names:
                        # store as (primary_display_name, set_of_all_names)
                        primary = names[0]
                        rpt['font_internal'][n] = (primary, set(names))

    # CSS @font-face 의 alias 와 실제 폰트 파일 이름 비교
    for css_name, src in rpt['embedded_fonts']:
        path = _src_to_zippath(src, rpt['font_files'])
        if not path:
            continue
        entry = rpt['font_internal'].get(path)
        if not entry:
            continue
        primary, all_names = entry
        # alias 가 폰트 내부 이름 중 어느 것과도 매칭 안 되면 mismatch
        if css_name not in all_names:
            rpt['name_mismatches'].append((css_name, path, primary))

    # 누락 = 참조 - 임베드. 실제 사용되는 셀렉터만 카운트.
    embedded_names = {f for f, _ in rpt['embedded_fonts']}
    rpt['missing'] = {}
    rpt['missing_unused'] = {}  # 사용 안되는 죽은 CSS 규칙
    for name, locs in rpt['referenced_fonts'].items():
        if name in embedded_names:
            continue
        used = [(f, sel) for f, sel in locs
                if _selector_is_used(sel, rpt['used_classes'])]
        if used:
            rpt['missing'][name] = used
        else:
            rpt['missing_unused'][name] = locs
    return rpt


def _selector_is_used(selector, used_classes):
    """셀렉터의 클래스 부분이 HTML 에서 실제 사용되는지 체크.

    클래스가 없는 셀렉터 (body, p 등) 는 사용된 것으로 간주.
    하나라도 사용 안 되는 클래스 포함 시 false.
    """
    import re
    classes = re.findall(r'\.([\w-]+)', selector)
    if not classes:
        return True  # 클래스 없는 셀렉터는 항상 적용됨
    return all(c in used_classes for c in classes)


def _src_to_zippath(src, font_files):
    """src 의 url() 파일명 → zip 안의 전체 경로 매칭."""
    import re
    m = re.search(r'url\(\s*[\'"]?([^\'")]+)', src)
    if not m:
        return None
    fname = m.group(1).rsplit('/', 1)[-1].lower()
    for fp in font_files:
        if fp.lower().endswith('/' + fname) or fp.lower() == fname:
            return fp
    return None


def _parse_css(data, fname, rpt):
    import re
    try:
        css = data.decode('utf-8')
    except Exception:
        try:
            css = data.decode('utf-8', errors='replace')
        except Exception:
            return

    # @font-face blocks → embedded fonts
    for ff_block in re.finditer(
            r'@font-face\s*\{([^}]*)\}', css, re.IGNORECASE | re.DOTALL):
        body = ff_block.group(1)
        fam_m = re.search(
            r'font-family\s*:\s*(["\']?)([^;"\']+)\1', body, re.IGNORECASE)
        src_m = re.search(r'src\s*:\s*([^;]+)', body, re.IGNORECASE)
        family = fam_m.group(2).strip() if fam_m else '?'
        src    = src_m.group(1).strip() if src_m else ''
        rpt['embedded_fonts'].append((family, src))

    # strip comments and @font-face for non-embedded scanning
    css_clean = re.sub(r'/\*.*?\*/', '', css, flags=re.DOTALL)
    stripped = re.sub(
        r'@font-face\s*\{[^}]*\}', '', css_clean,
        flags=re.IGNORECASE | re.DOTALL)

    # Walk top-level rule blocks: selector { decls }
    # (does not handle nested @media perfectly but good enough)
    for block in re.finditer(
            r'([^{}]+)\{([^}]*)\}', stripped, re.DOTALL):
        selector = ' '.join(block.group(1).split())
        body = block.group(2)
        for ff in re.finditer(
                r'font-family\s*:\s*([^;]+)', body, re.IGNORECASE):
            value = ff.group(1)
            first = _first_font_name(value)
            if first:
                rpt['referenced_fonts'].setdefault(first, []).append(
                    (fname, selector))


def _first_font_name(value):
    import re
    m = re.match(
        r'\s*(?:"([^"]+)"|\'([^\']+)\'|([^,\s][^,]*))', value)
    if not m:
        return ''
    name = next((g for g in m.groups() if g), '').strip()
    return name.strip('"\'')


# ── 리포트 포매팅 ────────────────────────────────────────────────────────────

GENERIC = {'serif', 'sans-serif', 'monospace', 'cursive', 'fantasy',
           'system-ui', 'inherit', 'initial', 'unset'}

# Latin/시스템 폰트 — 킨들 기본 폴백으로 무리 없음
SYSTEM_FONTS = {
    # Apple
    'applegothic', 'applemyungjo', 'helvetica', 'helvetica neue',
    'sf pro', 'sf pro display', 'sf pro text', '.applesystemuifont',
    # Windows
    'arial', 'arial black', 'arial narrow', 'times new roman', 'times',
    'tahoma', 'verdana', 'georgia', 'courier', 'courier new', 'consolas',
    'calibri', 'cambria', 'segoe ui', 'trebuchet ms', 'lucida sans',
    'lucida console', 'comic sans ms', 'impact', 'palatino',
    'old english text mt', 'symbol', 'wingdings',
}


def _is_korean_font_name(name):
    """한글 폰트 후보 판정. 시스템 폰트 우선 제외."""
    if name.lower() in SYSTEM_FONTS:
        return False
    # 한글 문자 포함
    for ch in name:
        if '가' <= ch <= '힣' or 'ᄀ' <= ch <= 'ᇿ':
            return True
    # 영문 한글계 폰트 키워드 (단, AppleGothic 등 시스템은 위에서 제외됨)
    lower = name.lower()
    for kw in ('nanum', 'kopub', 'noto sans kr', 'noto sans cjk',
               'noto serif kr', 'noto serif cjk', 'pretendard',
               'batang', 'dotum', 'gulim', 'myungjo', 'gungsuh',
               'spoqa', 'sandol', 'tway', 'hangang'):
        if kw in lower:
            return True
    return False


def _esc(s):
    return (str(s).replace('&', '&amp;').replace('<', '&lt;')
            .replace('>', '&gt;'))


def _src_to_filename(src):
    import re
    m = re.search(r'url\(\s*[\'"]?([^\'")]+)', src)
    if m:
        return m.group(1).rsplit('/', 1)[-1]
    return src


def _format_html(title, rpt):
    out = [f'<h2>{_esc(title)}</h2>']

    # ── 폰트 ──
    embedded = rpt['embedded_fonts']
    missing = {n: locs for n, locs in rpt['missing'].items()
               if n.lower() not in GENERIC}

    mismatches = {m[0]: m for m in rpt['name_mismatches']}

    out.append(f'<h3>임베드 폰트 ({len(embedded)})</h3>')
    if embedded:
        out.append('<table>')
        for fam, src in embedded:
            mm = mismatches.get(fam)
            if mm:
                _, _, actual = mm
                out.append(
                    '<tr>'
                    f'<td class="ok">✓</td>'
                    f'<td class="name">{_esc(fam)}</td>'
                    f'<td class="muted">{_esc(_src_to_filename(src))}</td>'
                    f'<td class="muted">내부이름: {_esc(actual)}</td>'
                    '</tr>'
                )
            else:
                out.append(
                    '<tr>'
                    f'<td class="ok">✓</td>'
                    f'<td class="name">{_esc(fam)}</td>'
                    f'<td class="muted">{_esc(_src_to_filename(src))}</td>'
                    '</tr>'
                )
        out.append('</table>')
        if mismatches:
            out.append(
                '<p class="muted" style="font-size:11px">'
                f'· {len(mismatches)}개 폰트의 @font-face alias 가 내부이름과 다름. '
                'KFX 가 alias 를 무시하는 경우 Korean Font Fixer 가 자동으로 내부이름으로 교체.'
                '</p>'
            )
    else:
        out.append('<p class="muted">없음</p>')

    korean_missing = {n: v for n, v in missing.items()
                      if _is_korean_font_name(n)}
    other_missing = {n: v for n, v in missing.items()
                     if not _is_korean_font_name(n)}
    dead = rpt.get('missing_unused') or {}

    out.append(
        f'<h3>누락 폰트 (한글 {len(korean_missing)} · 기타 {len(other_missing)}'
        + (f' · 미사용 {len(dead)}' if dead else '')
        + ')</h3>'
    )
    if korean_missing:
        out.append(
            '<div class="warn-box">한글 폰트 — 킨들 <code>/fonts/</code> 폴더에 '
            '아래 이름의 폰트 파일을 업로드해야 합니다.</div>'
        )
        out.append('<table>')
        for name in sorted(korean_missing.keys()):
            selectors = sorted({sel for _, sel in korean_missing[name]})
            preview = ', '.join(selectors[:6])
            if len(selectors) > 6:
                preview += f' … <span class="muted">외 {len(selectors)-6}개</span>'
            out.append(
                '<tr>'
                f'<td class="warn">⚠</td>'
                f'<td class="name">{_esc(name)}</td>'
                f'<td class="muted">{len(selectors)}곳 사용</td>'
                '</tr>'
                f'<tr><td></td><td colspan="2" class="muted" '
                f'style="padding-bottom:6px">{preview}</td></tr>'
            )
        out.append('</table>')
    elif other_missing:
        out.append('<p class="ok">한글 폰트 누락 없음</p>')
    else:
        out.append('<p class="ok">없음 — 모든 참조가 임베드됨</p>')

    if other_missing:
        out.append(
            '<p class="muted" style="font-size:11px">'
            f'기타 누락 폰트 (Latin/시스템 폰트 — 보통 문제없으나 책마다 다름): '
            + ', '.join(_esc(n) for n in sorted(other_missing.keys()))
            + '</p>'
        )

    if dead:
        out.append(
            '<p class="muted" style="font-size:11px">'
            f'미사용 (CSS 에 정의됐으나 HTML 에서 안 쓰는 폰트, 무시 가능): '
            + ', '.join(_esc(n) for n in sorted(dead.keys()))
            + '</p>'
        )

    # ── 페이지 데이터 ──
    pl_ncx = rpt['pagelist_ncx']
    pl_nav = rpt['pagelist_nav']
    out.append('<h3>페이지 데이터</h3>')
    if pl_ncx or pl_nav:
        rows = []
        if pl_ncx:
            rows.append(f'NCX <code>&lt;pageList&gt;</code>: '
                        f'<span class="muted">{_esc(", ".join(pl_ncx))}</span>')
        if pl_nav:
            rows.append(f'EPUB3 nav page-list: '
                        f'<span class="muted">{_esc(", ".join(pl_nav))}</span>')
        out.append(
            '<div class="warn-box">'
            'KFX 페이지 추정과 충돌. Korean Font Fixer 가 변환 시 자동 제거합니다.<br>'
            + '<br>'.join(rows) + '</div>'
        )
    else:
        out.append('<p class="ok">없음</p>')

    # ── 통계 ──
    out.append(
        f'<p class="stats">챕터 <b>{rpt["chapter_count"]}</b>장 · '
        f'HTML <b>{rpt["html_count"]}</b> · '
        f'CSS <b>{rpt["css_count"]}</b> · '
        f'폰트파일 <b>{len(rpt["font_files"])}</b></p>'
    )

    return ''.join(out)
