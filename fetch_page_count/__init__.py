from calibre.customize import InterfaceActionBase


class FetchPageCountPlugin(InterfaceActionBase):
    name                    = 'Fetch Page Count'
    description             = '선택 도서의 페이지수를 알라딘 / Google Books에서 가져와 pages 컬럼에 저장'
    supported_platforms     = ['windows', 'osx', 'linux']
    author                  = 'Custom'
    version                 = (1, 3, 0)
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
        try:
            from qt.core import QMenu
        except ImportError:
            from PyQt5.Qt import QMenu

        # 첫 실행 시 메뉴로 전환 (설정 항목 추가)
        if not hasattr(self, '_menu_built'):
            self._menu_built = True
            menu = QMenu(self.gui)
            menu.addAction('페이지수 가져오기').triggered.connect(self._run_fetch)
            menu.addSeparator()
            menu.addAction('설정...').triggered.connect(self.configure)
            self.qaction.setMenu(menu)

        self._run_fetch()

    def _selected_book_ids(self):
        """현재 library_view 에서 실제로 선택된 책의 id 목록을 반환.

        calibre 내부 액션(EditMetadataAction 등)이 사용하는 패턴과 동일하게
        selectionModel().selectedRows() → model().id(row) 로 매핑한다.
        get_selected_ids() 가 컨텍스트에 따라 엉뚱한 id 를 돌려주는 사례가
        있어 가장 신뢰성 있는 방식으로 통일한다.
        """
        view = self.gui.library_view
        sm   = view.selectionModel()
        rows = sm.selectedRows() if sm is not None else []
        m    = view.model()
        ids  = []
        seen = set()
        for r in rows:
            try:
                bid = m.id(r)
            except Exception:
                continue
            if bid is None or bid in seen:
                continue
            seen.add(bid)
            ids.append(bid)
        # selectedRows 가 비어있는 경우(드물게 셀 선택 모드 등) currentIndex 로 폴백
        if not ids:
            try:
                idx = view.currentIndex()
                if idx is not None and idx.isValid():
                    bid = m.id(idx)
                    if bid is not None:
                        ids.append(bid)
            except Exception:
                pass
        return ids

    def _run_fetch(self):
        import time

        try:
            from qt.core import QProgressDialog, Qt, QApplication
        except ImportError:
            from PyQt5.Qt import QProgressDialog, Qt, QApplication

        from calibre.gui2 import info_dialog, error_dialog

        book_ids = self._selected_book_ids()
        if not book_ids:
            info_dialog(self.gui, '페이지수 가져오기', '책을 먼저 선택하세요.', show=True)
            return

        p   = self._prefs()
        col = p['pages_column']
        db  = self.gui.current_db

        col_key = col if col.startswith('#') else f'#{col}'
        if col_key not in db.field_metadata.custom_field_metadata():
            error_dialog(
                self.gui, '컬럼 없음',
                f"사용자 정의 컬럼 '{col_key}'이 없습니다.\n"
                "'설정...'에서 컬럼 이름을 확인하세요.",
                show=True)
            return

        label = col.lstrip('#')
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
                db.set_custom(book_id, pages, label=label, commit=False)
                updated.append(f'{mi.title}  →  {pages}쪽')
            else:
                not_found.append(mi.title)

            time.sleep(0.4)

        db.commit()
        pd.setValue(len(book_ids))
        self.gui.library_view.refresh_grid()

        lines = [f'업데이트: {len(updated)}권  /  미발견: {len(not_found)}권', '']
        if updated:
            lines += ['[업데이트]'] + [f'  · {t}' for t in updated[:15]]
            if len(updated) > 15:
                lines.append(f'  ... 외 {len(updated)-15}권')
        if not_found:
            lines += ['', '[미발견]'] + [f'  · {t}' for t in not_found[:10]]
        info_dialog(self.gui, '완료', '\n'.join(lines), show=True)


# ── 페이지수 조회 ─────────────────────────────────────────────────────────────

def _has_hangul(s):
    if not s:
        return False
    for ch in s:
        if '가' <= ch <= '힣' or 'ᄀ' <= ch <= 'ᇿ' or '㄰' <= ch <= '㆏':
            return True
    return False


def _get_pages(mi, ttb=''):
    """페이지수 조회.

    한글 제목 → 알라딘 우선, 영어/기타 제목 → Google Books 우선.
    어느 쪽이 실패하더라도 ISBN/제목으로 가능한 모든 fallback 을 시도한다.
    """
    import re
    isbn    = re.sub(r'[^0-9X]', '', (mi.isbn or '').upper())
    title   = (mi.title or '').strip()
    authors = mi.authors or []

    korean = _has_hangul(title) or any(_has_hangul(a) for a in authors)

    aladin_steps = []
    if ttb:
        if isbn:  aladin_steps.append(lambda: _al_api_isbn(isbn, ttb))
        if title: aladin_steps.append(lambda: _al_api_title(title, authors, ttb))
    if isbn:  aladin_steps.append(lambda: _al_scrape(isbn))
    if title: aladin_steps.append(lambda: _al_search(title, authors))

    google_steps = []
    if isbn:
        google_steps.append(lambda: _google(f'isbn:{isbn}'))
    if title:
        q = f'intitle:"{title}"' + (f'+inauthor:"{authors[0]}"' if authors else '')
        google_steps.append(lambda: _google(q))
        # 따옴표 없는 느슨한 검색도 한 번 더 시도
        q2 = f'intitle:{title}' + (f'+inauthor:{authors[0]}' if authors else '')
        if q2 != q:
            google_steps.append(lambda: _google(q2))

    # 한글이면 알라딘 먼저, 영어면 Google Books 먼저
    steps = (aladin_steps + google_steps) if korean else (google_steps + aladin_steps)

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
    """Google Books 에서 페이지수를 찾는다.

    첫 결과에 pageCount 가 없는 경우가 많아 상위 몇 건을 훑어 페이지수가
    있는 첫 결과를 반환한다.
    """
    import json, urllib.parse
    url  = ('https://www.googleapis.com/books/v1/volumes'
            f'?q={urllib.parse.quote(q)}&maxResults=5'
            '&fields=items/volumeInfo/pageCount,items/volumeInfo/title')
    d     = json.loads(_http(url))
    for item in (d.get('items') or []):
        n = int(item.get('volumeInfo', {}).get('pageCount') or 0)
        if n:
            return n
    return 0
