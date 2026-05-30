import re
import json
import time
import urllib.request
import urllib.parse

from calibre.gui2.actions import InterfaceAction
from calibre.gui2 import info_dialog, error_dialog
from calibre_plugins.fetch_page_count.config import prefs

REQUEST_DELAY = 0.4


class FetchPageCountAction(InterfaceAction):
    name        = 'Fetch Page Count'
    action_spec = ('페이지수 가져오기', None,
                   '선택 도서의 페이지수를 알라딘 / Google Books에서 가져옵니다', None)

    def genesis(self):
        try:
            from qt.core import QMenu
        except ImportError:
            from PyQt5.Qt import QMenu

        self.menu = QMenu(self.gui)
        self.qaction.setMenu(self.menu)
        self.qaction.triggered.connect(self.fetch_pages)
        self.menu.addAction('페이지수 가져오기').triggered.connect(self.fetch_pages)
        self.menu.addSeparator()
        self.menu.addAction('설정...').triggered.connect(self.configure)

    # ── 설정 다이얼로그 ────────────────────────────────────────────────────────

    def configure(self):
        try:
            from qt.core import (QDialog, QVBoxLayout, QLabel,
                                 QLineEdit, QDialogButtonBox)
        except ImportError:
            from PyQt5.Qt import (QDialog, QVBoxLayout, QLabel,
                                  QLineEdit, QDialogButtonBox)

        class _Dlg(QDialog):
            def __init__(self, parent):
                super().__init__(parent)
                self.setWindowTitle('페이지수 가져오기 — 설정')
                self.setMinimumWidth(430)
                lay = QVBoxLayout(self)

                lay.addWidget(QLabel('알라딘 TTB API 키 (없으면 스크래핑만 사용):'))
                self.ttb = QLineEdit(prefs['ttb_key'])
                self.ttb.setPlaceholderText('ttbXXXXXXXXXXXX')
                lay.addWidget(self.ttb)

                lay.addWidget(QLabel('컬럼 이름 (# 없이):'))
                self.col = QLineEdit(prefs['pages_column'])
                lay.addWidget(self.col)

                note = QLabel(
                    '<a href="https://www.aladin.co.kr/ttb/wbloglist.aspx">'
                    'TTB 키 발급 (무료, 알라딘 로그인 필요)</a>'
                )
                note.setOpenExternalLinks(True)
                lay.addWidget(note)

                bb = QDialogButtonBox(
                    QDialogButtonBox.Ok | QDialogButtonBox.Cancel
                )
                bb.accepted.connect(self.accept)
                bb.rejected.connect(self.reject)
                lay.addWidget(bb)

        d = _Dlg(self.gui)
        if d.exec_():
            prefs['ttb_key']      = d.ttb.text().strip()
            prefs['pages_column'] = d.col.text().strip() or 'pages'

    # ── 메인 로직 ──────────────────────────────────────────────────────────────

    def fetch_pages(self):
        try:
            from qt.core import QProgressDialog, Qt, QApplication
        except ImportError:
            from PyQt5.Qt import QProgressDialog, Qt, QApplication

        book_ids = self.gui.current_view().get_selected_ids()
        if not book_ids:
            info_dialog(self.gui, '페이지수 가져오기', '책을 먼저 선택하세요.', show=True)
            return

        col = prefs['pages_column']
        db  = self.gui.current_db

        if not _column_exists(db, col):
            error_dialog(
                self.gui, '컬럼 없음',
                f"사용자 정의 컬럼 '#{col}'이 없습니다.\n"
                "환경설정 > 사용자 정의 컬럼에서 추가하거나,\n"
                "'설정...'에서 컬럼 이름을 수정하세요.",
                show=True,
            )
            return

        ttb_key = prefs['ttb_key']

        pd = QProgressDialog('준비 중...', '취소', 0, len(book_ids), self.gui)
        pd.setWindowTitle('페이지수 가져오기')
        pd.setWindowModality(Qt.WindowModal)
        pd.show()

        updated, not_found = [], []

        for i, book_id in enumerate(book_ids):
            if pd.wasCanceled():
                break

            mi = db.get_metadata(book_id)
            pd.setLabelText(f'({i + 1}/{len(book_ids)}) {mi.title[:55]}')
            pd.setValue(i)
            QApplication.processEvents()

            pages = _get_pages(mi, ttb_key)
            if pages:
                db.set_custom(book_id, pages, label=col, commit=False)
                updated.append(f'{mi.title}  →  {pages}쪽')
            else:
                not_found.append(mi.title)

            time.sleep(REQUEST_DELAY)

        db.commit()
        pd.setValue(len(book_ids))
        self.gui.current_view().refresh_ids(book_ids)
        _show_summary(self.gui, updated, not_found)


# ── 소스 조회 ──────────────────────────────────────────────────────────────────

def _get_pages(mi, ttb_key=''):
    isbn    = re.sub(r'[^0-9X]', '', mi.isbn or '')
    title   = (mi.title or '').strip()
    authors = mi.authors or []

    steps = []
    if ttb_key:
        if isbn:  steps.append(lambda: _aladdin_api_isbn(isbn, ttb_key))
        if title: steps.append(lambda: _aladdin_api_title(title, authors, ttb_key))
    if isbn:  steps.append(lambda: _aladdin_scrape(isbn))
    if title: steps.append(lambda: _aladdin_search_scrape(title, authors))
    if isbn:  steps.append(lambda: _google_books(f'isbn:{isbn}'))
    if title:
        q = f'intitle:{title}' + (f'+inauthor:{authors[0]}' if authors else '')
        steps.append(lambda: _google_books(q))

    for fn in steps:
        try:
            p = fn()
            if p and 10 < p < 10000:
                return p
        except Exception:
            pass
    return 0


# ── 알라딘 API ─────────────────────────────────────────────────────────────────

def _aladdin_api_isbn(isbn, key):
    url = (
        'https://www.aladin.co.kr/ttb/api/ItemLookUp.aspx'
        f'?ttbkey={key}&itemIdType=ISBN13&ItemId={isbn}'
        '&output=js&Version=20131101&OptResult=subInfo'
    )
    data = json.loads(_get(url))
    return int((data.get('item') or [{}])[0].get('subInfo', {}).get('itemPage') or 0)


def _aladdin_api_title(title, authors, key):
    q = title + (' ' + authors[0] if authors else '')
    url = (
        'https://www.aladin.co.kr/ttb/api/ItemSearch.aspx'
        f'?ttbkey={key}&Query={urllib.parse.quote(q)}'
        '&QueryType=Title&MaxResults=1&SearchTarget=Book'
        '&output=js&Version=20131101&OptResult=subInfo'
    )
    data = json.loads(_get(url))
    return int((data.get('item') or [{}])[0].get('subInfo', {}).get('itemPage') or 0)


# ── 알라딘 스크래핑 ────────────────────────────────────────────────────────────

_PAGE_RE = re.compile(r'쪽수[^<:]*:\s*(\d+)\s*쪽', re.IGNORECASE)


def _aladdin_scrape(isbn):
    html = _get(f'https://www.aladin.co.kr/shop/wproduct.aspx?ISBN={isbn}', decode=True)
    m = _PAGE_RE.search(html)
    return int(m.group(1)) if m else 0


def _aladdin_search_scrape(title, authors):
    q    = title + (' ' + authors[0] if authors else '')
    url  = ('https://www.aladin.co.kr/search/wsearchresult.aspx'
            f'?SearchTarget=Book&SearchWord={urllib.parse.quote(q)}')
    html = _get(url, decode=True)
    m    = re.search(r'wproduct\.aspx\?ItemId=(\d+)', html)
    if not m:
        return 0
    product = _get(
        f'https://www.aladin.co.kr/shop/wproduct.aspx?ItemId={m.group(1)}',
        decode=True,
    )
    mm = _PAGE_RE.search(product)
    return int(mm.group(1)) if mm else 0


# ── Google Books ───────────────────────────────────────────────────────────────

def _google_books(q):
    url  = (
        'https://www.googleapis.com/books/v1/volumes'
        f'?q={urllib.parse.quote(q)}&maxResults=1&fields=items/volumeInfo/pageCount'
    )
    data  = json.loads(_get(url))
    items = data.get('items') or []
    return int(items[0].get('volumeInfo', {}).get('pageCount') or 0) if items else 0


# ── 유틸 ───────────────────────────────────────────────────────────────────────

def _get(url, decode=False, timeout=12):
    req = urllib.request.Request(
        url, headers={'User-Agent': 'Mozilla/5.0 (compatible; Calibre plugin/1.0)'},
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read()
    return raw.decode('utf-8', errors='replace') if decode else raw


def _column_exists(db, label):
    try:
        return label in db.field_metadata.custom_field_metadata()
    except Exception:
        return False


def _show_summary(gui, updated, not_found):
    lines = [f'업데이트: {len(updated)}권  /  미발견: {len(not_found)}권', '']
    if updated:
        lines += ['[업데이트]'] + [f'  · {t}' for t in updated[:15]]
        if len(updated) > 15:
            lines.append(f'  ... 외 {len(updated) - 15}권')
    if not_found:
        lines += ['', '[찾지 못한 책]'] + [f'  · {t}' for t in not_found[:10]]
        if len(not_found) > 10:
            lines.append(f'  ... 외 {len(not_found) - 10}권')
    info_dialog(gui, '완료', '\n'.join(lines), show=True)
