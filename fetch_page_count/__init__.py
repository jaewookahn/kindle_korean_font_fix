from calibre.customize import InterfaceActionBase


class FetchPageCountPlugin(InterfaceActionBase):
    name                    = 'Fetch Page Count'
    description             = '선택 도서의 페이지수를 알라딘 / Google Books에서 가져와 pages 컬럼에 저장'
    supported_platforms     = ['windows', 'osx', 'linux']
    author                  = 'Custom'
    version                 = (1, 2, 0)
    minimum_calibre_version = (5, 0, 0)
    actual_plugin           = 'calibre_plugins.fetch_page_count:FetchPageCountAction'


# ── InterfaceAction (GUI 초기화 후 로드됨) ────────────────────────────────────

from calibre.gui2.actions import InterfaceAction  # noqa: E402


class FetchPageCountAction(InterfaceAction):
    name        = 'Fetch Page Count'
    action_spec = ('페이지수 가져오기', None,
                   '선택 도서의 페이지수를 알라딘 / Google Books에서 가져옵니다', None)

    def genesis(self):
        self.qaction.triggered.connect(self.fetch_pages)

    # ── 설정 ──────────────────────────────────────────────────────────────────

    def _prefs(self):
        from calibre.utils.config import JSONConfig
        p = JSONConfig('plugins/fetch_page_count')
        p.defaults['ttb_key']      = ''
        p.defaults['pages_column'] = 'pages'
        return p

    def configure(self):
        try:
            from qt.core import (QDialog, QVBoxLayout, QLabel,
                                 QLineEdit, QDialogButtonBox)
        except ImportError:
            from PyQt5.Qt import (QDialog, QVBoxLayout, QLabel,
                                  QLineEdit, QDialogButtonBox)

        p = self._prefs()

        class _Dlg(QDialog):
            def __init__(self, parent):
                super().__init__(parent)
                self.setWindowTitle('페이지수 가져오기 — 설정')
                self.setMinimumWidth(420)
                lay = QVBoxLayout(self)
                lay.addWidget(QLabel('알라딘 TTB API 키 (없으면 스크래핑만 사용):'))
                self.ttb = QLineEdit(p['ttb_key'])
                self.ttb.setPlaceholderText('ttbXXXXXXXXXXXX')
                lay.addWidget(self.ttb)
                lay.addWidget(QLabel('컬럼 이름 (# 없이):'))
                self.col = QLineEdit(p['pages_column'])
                lay.addWidget(self.col)
                bb = QDialogButtonBox(
                    QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
                bb.accepted.connect(self.accept)
                bb.rejected.connect(self.reject)
                lay.addWidget(bb)

        d = _Dlg(self.gui)
        if d.exec_():
            p['ttb_key']      = d.ttb.text().strip()
            p['pages_column'] = d.col.text().strip() or 'pages'

    # ── 메인 ──────────────────────────────────────────────────────────────────

    def fetch_pages(self):
        import re, json, time
        import urllib.request, urllib.parse

        try:
            from qt.core import QProgressDialog, QMenu, Qt, QApplication
        except ImportError:
            from PyQt5.Qt import QProgressDialog, QMenu, Qt, QApplication

        from calibre.gui2 import info_dialog, error_dialog

        # 첫 실행 시 메뉴로 전환 (설정 항목 추가)
        if not hasattr(self, '_menu_built'):
            self._menu_built = True
            menu = QMenu(self.gui)
            menu.addAction('페이지수 가져오기').triggered.connect(self._run_fetch)
            menu.addSeparator()
            menu.addAction('설정...').triggered.connect(self.configure)
            self.qaction.setMenu(menu)

        self._run_fetch()

    def _run_fetch(self):
        import re, json, time
        import urllib.request, urllib.parse

        try:
            from qt.core import QProgressDialog, Qt, QApplication
        except ImportError:
            from PyQt5.Qt import QProgressDialog, Qt, QApplication

        from calibre.gui2 import info_dialog, error_dialog

        book_ids = self.gui.current_view().get_selected_ids()
        if not book_ids:
            info_dialog(self.gui, '페이지수 가져오기', '책을 먼저 선택하세요.', show=True)
            return

        p   = self._prefs()
        col = p['pages_column']
        db  = self.gui.current_db

        if col not in db.field_metadata.custom_field_metadata():
            error_dialog(
                self.gui, '컬럼 없음',
                f"사용자 정의 컬럼 '#{col}'이 없습니다.\n"
                "'설정...'에서 컬럼 이름을 확인하세요.",
                show=True)
            return

        ttb = p['ttb_key']
        pd  = QProgressDialog('준비 중...', '취소', 0, len(book_ids), self.gui)
        pd.setWindowTitle('페이지수 가져오기')
        pd.setWindowModality(Qt.WindowModal)
        pd.show()

        updated, not_found = [], []

        for i, book_id in enumerate(book_ids):
            if pd.wasCanceled():
                break
            mi = db.get_metadata(book_id)
            pd.setLabelText(f'({i+1}/{len(book_ids)}) {mi.title[:55]}')
            pd.setValue(i)
            QApplication.processEvents()

            pages = _get_pages(mi, ttb)
            if pages:
                db.set_custom(book_id, pages, label=col, commit=False)
                updated.append(f'{mi.title}  →  {pages}쪽')
            else:
                not_found.append(mi.title)

            time.sleep(0.4)

        db.commit()
        pd.setValue(len(book_ids))
        self.gui.current_view().refresh_ids(book_ids)

        lines = [f'업데이트: {len(updated)}권  /  미발견: {len(not_found)}권', '']
        if updated:
            lines += ['[업데이트]'] + [f'  · {t}' for t in updated[:15]]
            if len(updated) > 15:
                lines.append(f'  ... 외 {len(updated)-15}권')
        if not_found:
            lines += ['', '[미발견]'] + [f'  · {t}' for t in not_found[:10]]
        info_dialog(self.gui, '완료', '\n'.join(lines), show=True)


# ── 페이지수 조회 ─────────────────────────────────────────────────────────────

def _get_pages(mi, ttb=''):
    import re
    isbn    = re.sub(r'[^0-9X]', '', mi.isbn or '')
    title   = (mi.title or '').strip()
    authors = mi.authors or []

    steps = []
    if ttb:
        if isbn:  steps.append(lambda: _al_api_isbn(isbn, ttb))
        if title: steps.append(lambda: _al_api_title(title, authors, ttb))
    if isbn:  steps.append(lambda: _al_scrape(isbn))
    if title: steps.append(lambda: _al_search(title, authors))
    if isbn:  steps.append(lambda: _google(f'isbn:{isbn}'))
    if title:
        q = f'intitle:{title}' + (f'+inauthor:{authors[0]}' if authors else '')
        steps.append(lambda: _google(q))

    for fn in steps:
        try:
            p = fn()
            if p and 10 < p < 10000:
                return p
        except Exception:
            pass
    return 0


def _http(url, decode=False):
    import urllib.request
    req = urllib.request.Request(
        url, headers={'User-Agent': 'Mozilla/5.0 (compatible; Calibre/1.0)'})
    with urllib.request.urlopen(req, timeout=12) as r:
        raw = r.read()
    return raw.decode('utf-8', errors='replace') if decode else raw


def _al_api_isbn(isbn, key):
    import json
    url = (f'https://www.aladin.co.kr/ttb/api/ItemLookUp.aspx'
           f'?ttbkey={key}&itemIdType=ISBN13&ItemId={isbn}'
           f'&output=js&Version=20131101&OptResult=subInfo')
    d = json.loads(_http(url))
    return int((d.get('item') or [{}])[0].get('subInfo', {}).get('itemPage') or 0)


def _al_api_title(title, authors, key):
    import json, urllib.parse
    q = title + (' ' + authors[0] if authors else '')
    url = (f'https://www.aladin.co.kr/ttb/api/ItemSearch.aspx'
           f'?ttbkey={key}&Query={urllib.parse.quote(q)}'
           f'&QueryType=Title&MaxResults=1&SearchTarget=Book'
           f'&output=js&Version=20131101&OptResult=subInfo')
    d = json.loads(_http(url))
    return int((d.get('item') or [{}])[0].get('subInfo', {}).get('itemPage') or 0)


def _al_scrape(isbn):
    import re
    html = _http(f'https://www.aladin.co.kr/shop/wproduct.aspx?ISBN={isbn}',
                 decode=True)
    m = re.search(r'쪽수[^<:]*:\s*(\d+)\s*쪽', html, re.IGNORECASE)
    return int(m.group(1)) if m else 0


def _al_search(title, authors):
    import re, urllib.parse
    q    = title + (' ' + authors[0] if authors else '')
    html = _http('https://www.aladin.co.kr/search/wsearchresult.aspx'
                 f'?SearchTarget=Book&SearchWord={urllib.parse.quote(q)}',
                 decode=True)
    m = re.search(r'wproduct\.aspx\?ItemId=(\d+)', html)
    if not m:
        return 0
    prod = _http(f'https://www.aladin.co.kr/shop/wproduct.aspx?ItemId={m.group(1)}',
                 decode=True)
    mm = re.search(r'쪽수[^<:]*:\s*(\d+)\s*쪽', prod, re.IGNORECASE)
    return int(mm.group(1)) if mm else 0


def _google(q):
    import json, urllib.parse
    url  = ('https://www.googleapis.com/books/v1/volumes'
            f'?q={urllib.parse.quote(q)}&maxResults=1&fields=items/volumeInfo/pageCount')
    d     = json.loads(_http(url))
    items = d.get('items') or []
    return int(items[0].get('volumeInfo', {}).get('pageCount') or 0) if items else 0
