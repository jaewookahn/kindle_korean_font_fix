import re
import json
import time
import urllib.request
import urllib.parse

from calibre.gui2.actions import InterfaceAction
from calibre.gui2 import info_dialog, error_dialog

try:
    from qt.core import QProgressDialog, Qt, QApplication
except ImportError:
    from PyQt5.Qt import QProgressDialog, Qt, QApplication

DEFAULT_COLUMN = 'pages'
REQUEST_DELAY  = 0.4   # 서버 부담 완화


class FetchPageCountAction(InterfaceAction):
    name        = 'Fetch Page Count'
    action_spec = ('페이지수 가져오기', None,
                   '선택 도서의 페이지수를 알라딘 / Google Books에서 자동으로 가져옵니다', None)

    def genesis(self):
        self.qaction.triggered.connect(self.fetch_pages)

    # ── 진입점 ────────────────────────────────────────────────────────────────

    def fetch_pages(self):
        book_ids = self.gui.current_view().get_selected_ids()
        if not book_ids:
            info_dialog(self.gui, '페이지수 가져오기', '책을 먼저 선택하세요.', show=True)
            return

        ttb_key, col = _parse_config(self.plugin_action.site_customization or '')
        db = self.gui.current_db

        if not _column_exists(db, col):
            error_dialog(
                self.gui, '컬럼 없음',
                f"사용자 정의 컬럼 '#{col}'이 존재하지 않습니다.\n"
                "Calibre 환경설정 > 사용자 정의 컬럼에서 먼저 추가하세요.",
                show=True,
            )
            return

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


# ── 설정 파싱 ──────────────────────────────────────────────────────────────────

def _parse_config(raw):
    """'ttbKEY,column=mycolumn' 형식 파싱. 키와 컬럼 이름 반환."""
    ttb_key = ''
    col = DEFAULT_COLUMN
    for part in raw.split(','):
        part = part.strip()
        if part.startswith('column='):
            col = part[7:].strip() or DEFAULT_COLUMN
        elif part:
            ttb_key = part
    return ttb_key, col


def _column_exists(db, label):
    try:
        return label in db.field_metadata.custom_field_metadata()
    except Exception:
        return False


# ── 소스 조회 순서 ─────────────────────────────────────────────────────────────

def _get_pages(mi, ttb_key=''):
    isbn    = re.sub(r'[^0-9X]', '', mi.isbn or '')
    title   = (mi.title or '').strip()
    authors = mi.authors or []

    steps = []

    if ttb_key:
        if isbn:
            steps.append(lambda: _aladdin_api_isbn(isbn, ttb_key))
        if title:
            steps.append(lambda: _aladdin_api_title(title, authors, ttb_key))

    if isbn:
        steps.append(lambda: _aladdin_scrape(isbn))

    if title:
        steps.append(lambda: _aladdin_search_scrape(title, authors))

    if isbn:
        steps.append(lambda: _google_books(q=f'isbn:{isbn}'))

    if title:
        q = f'intitle:{title}'
        if authors:
            q += f'+inauthor:{authors[0]}'
        steps.append(lambda: _google_books(q=q))

    for fn in steps:
        try:
            pages = fn()
            if pages and 10 < pages < 10000:
                return pages
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
    query = title
    if authors:
        query += ' ' + authors[0]
    url = (
        'https://www.aladin.co.kr/ttb/api/ItemSearch.aspx'
        f'?ttbkey={key}&Query={urllib.parse.quote(query)}'
        '&QueryType=Title&MaxResults=1&SearchTarget=Book'
        '&output=js&Version=20131101&OptResult=subInfo'
    )
    data = json.loads(_get(url))
    return int((data.get('item') or [{}])[0].get('subInfo', {}).get('itemPage') or 0)


# ── 알라딘 스크래핑 ────────────────────────────────────────────────────────────

_PAGE_RE = re.compile(r'쪽수[^<:]*:\s*(\d+)\s*쪽', re.IGNORECASE)


def _extract_pages_from_html(html):
    m = _PAGE_RE.search(html)
    if m:
        return int(m.group(1))
    return 0


def _aladdin_scrape(isbn):
    url  = f'https://www.aladin.co.kr/shop/wproduct.aspx?ISBN={isbn}'
    html = _get(url, decode=True)
    return _extract_pages_from_html(html)


def _aladdin_search_scrape(title, authors):
    query = title
    if authors:
        query += ' ' + authors[0]
    url  = (
        'https://www.aladin.co.kr/search/wsearchresult.aspx'
        f'?SearchTarget=Book&SearchWord={urllib.parse.quote(query)}'
    )
    html = _get(url, decode=True)

    # 첫 번째 결과 ItemId 추출
    m = re.search(r'wproduct\.aspx\?ItemId=(\d+)', html)
    if not m:
        return 0

    product_url  = f'https://www.aladin.co.kr/shop/wproduct.aspx?ItemId={m.group(1)}'
    product_html = _get(product_url, decode=True)
    return _extract_pages_from_html(product_html)


# ── Google Books ───────────────────────────────────────────────────────────────

def _google_books(q):
    url  = (
        'https://www.googleapis.com/books/v1/volumes'
        f'?q={urllib.parse.quote(q)}&maxResults=1&fields=items/volumeInfo/pageCount'
    )
    data = json.loads(_get(url))
    items = data.get('items') or []
    return int(items[0].get('volumeInfo', {}).get('pageCount') or 0) if items else 0


# ── HTTP 헬퍼 ──────────────────────────────────────────────────────────────────

def _get(url, decode=False, timeout=12):
    req = urllib.request.Request(
        url,
        headers={'User-Agent': 'Mozilla/5.0 (compatible; Calibre plugin/1.0)'},
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read()
    return raw.decode('utf-8', errors='replace') if decode else raw


# ── 결과 요약 ──────────────────────────────────────────────────────────────────

def _show_summary(gui, updated, not_found):
    lines = [f'업데이트: {len(updated)}권  /  미발견: {len(not_found)}권', '']

    if updated:
        lines.append('[업데이트 완료]')
        lines.extend(f'  · {t}' for t in updated[:15])
        if len(updated) > 15:
            lines.append(f'  ... 외 {len(updated) - 15}권')

    if not_found:
        lines.append('')
        lines.append('[찾지 못한 책]')
        lines.extend(f'  · {t}' for t in not_found[:10])
        if len(not_found) > 10:
            lines.append(f'  ... 외 {len(not_found) - 10}권')

    info_dialog(gui, '페이지수 가져오기 완료', '\n'.join(lines), show=True)
