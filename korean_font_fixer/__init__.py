import re
import zipfile

from calibre.customize import FileTypePlugin

KOREAN_UNICODE_RANGE = (
    'U+1100-U+11FF, U+302E-U+302F, U+3131-U+318E, '
    'U+3200-U+321E, U+3260-U+327E, U+A960-U+A97C, '
    'U+AC00-U+D7A3, U+D7B0-U+D7C6, U+D7CB-U+D7FB, '
    'U+FFA0-U+FFBE, U+FFC2-U+FFC7, U+FFCA-U+FFCF, '
    'U+FFD2-U+FFD7, U+FFD0-U+FFDB'
)


class KoreanFontFixer(FileTypePlugin):
    name                = 'Korean Font Fallback Fixer'
    description         = 'EPUB 변환 전 CSS에 한국어 폰트 폴백을 주입합니다'
    supported_platforms = ['windows', 'osx', 'linux']
    author              = 'Custom'
    version             = (1, 0, 0)
    minimum_calibre_version = (5, 0, 0)
    file_types          = frozenset(['epub'])
    on_preprocess       = True

    def run(self, path_to_ebook):
        from calibre.ptempfile import PersistentTemporaryFile

        font_name = (self.site_customization or '').strip() or 'NanumGothic'

        with zipfile.ZipFile(path_to_ebook, 'r') as zf:
            infos = zf.infolist()
            contents = {i.filename: (zf.read(i.filename), i) for i in infos}

        modified = _strip_page_lists(contents)

        # @font-face alias → 폰트 파일 실제 이름 매핑 (KFX 폴백 회피용)
        alias_map = _build_alias_remap(contents)

        css_names = [n for n in contents if n.lower().endswith('.css')]
        for name in css_names:
            data, info = contents[name]
            try:
                css = data.decode('utf-8')
            except UnicodeDecodeError:
                css = data.decode('latin-1')

            if alias_map:
                css = _apply_alias_remap(css, alias_map)

            if 'KoreanFallback' in css:
                # 이미 처리됨 — alias remap 만 적용했으면 저장
                if css != data.decode('utf-8', errors='replace'):
                    contents[name] = (css.encode('utf-8'), info)
                    modified = True
                continue

            new_css = _inject_korean(css, font_name)
            if new_css != css:
                contents[name] = (new_css.encode('utf-8'), info)
                modified = True

        if not modified:
            return None

        with PersistentTemporaryFile('.epub') as tmp:
            tmp_path = tmp.name
        _write_epub(contents, tmp_path)
        return tmp_path

    def customization_help(self, gui=False):
        return (
            'Kindle fonts 폴더에 업로드한 폰트의 family name을 입력하세요.\n'
            '예: NanumGothic, KoPub Dotum, Noto Sans KR\n'
            '(폰트 파일을 폰트 뷰어에서 열면 family name 확인 가능)'
        )


# ── alias remap (Option 1: KFX 폴백 우회) ────────────────────────────────────

def _build_alias_remap(contents):
    """모든 CSS 의 @font-face 를 훑어 alias → 실제 폰트 이름 매핑 생성.

    alias 가 폰트 파일 name table 의 어느 언어 변형과도 매칭 안 되는
    경우만 remap. (예: "은 돋움" alias 와 폰트 내부의 "UnDotum" 은
    같은 폰트의 한/영 이름이라 remap 불필요.)
    """
    # 폰트 파일 경로(소문자) → (primary_name, all_names_set)
    file_to_names = {}
    for name, (data, _) in contents.items():
        low = name.lower()
        if low.endswith(('.ttf', '.otf')):
            names = _all_font_names(data)
            if names:
                file_to_names[low] = (names[0], set(names))
    if not file_to_names:
        return {}

    alias_map = {}
    for name, (data, _) in contents.items():
        if not name.lower().endswith('.css'):
            continue
        try:
            css = data.decode('utf-8')
        except UnicodeDecodeError:
            css = data.decode('latin-1', errors='replace')
        css_dir = name.rsplit('/', 1)[0] if '/' in name else ''
        for m in re.finditer(
                r'@font-face\s*\{([^}]*)\}', css,
                re.IGNORECASE | re.DOTALL):
            body = m.group(1)
            fam_m = re.search(
                r'font-family\s*:\s*(["\']?)([^;"\']+)\1', body, re.IGNORECASE)
            src_m = re.search(r'src\s*:\s*([^;]+)', body, re.IGNORECASE)
            if not (fam_m and src_m):
                continue
            alias = fam_m.group(2).strip()
            url_m = re.search(r'url\(\s*[\'"]?([^\'")]+)', src_m.group(1))
            if not url_m:
                continue
            url = url_m.group(1)
            # 경로 정규화 (../ 처리)
            ref = url
            if css_dir:
                ref = css_dir + '/' + url
            parts = []
            for p in ref.split('/'):
                if p == '..':
                    if parts:
                        parts.pop()
                elif p and p != '.':
                    parts.append(p)
            zippath = '/'.join(parts).lower()
            entry = file_to_names.get(zippath)
            if not entry:
                continue
            primary, all_names = entry
            # alias 가 폰트 이름 중 어느 것과도 안 맞을 때만 remap
            if alias not in all_names:
                alias_map[alias] = primary
    return alias_map


def _all_font_names(font_data):
    """폰트 파일의 모든 family 관련 이름 (다국어 포함)."""
    try:
        from fontTools.ttLib import TTFont
        from io import BytesIO
    except Exception:
        try:
            from calibre.utils.fonts.utils import get_all_font_names
            d = get_all_font_names(font_data)
            out, seen = [], set()
            for k in ('family_name', 'preferred_family_name',
                      'full_name', 'postscript_name'):
                v = d.get(k)
                if v and v not in seen:
                    seen.add(v); out.append(v)
            return out
        except Exception:
            return []
    try:
        tt = TTFont(BytesIO(font_data))
        # nameID 4 (full) 우선 → weight 포함된 더 구체적인 이름
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


def _apply_alias_remap(css, alias_map):
    """CSS 의 font-family 참조에서 alias 이름을 실제 이름으로 교체.

    @font-face 블록 안의 font-family 선언은 *유지* (브라우저 호환 위해).
    @font-face 외부의 font-family 참조만 교체.
    """
    # @font-face 블록 보호
    blocks = []

    def save(m):
        blocks.append(m.group(0))
        return f'__AFF{len(blocks)-1}__'

    protected = re.sub(
        r'@font-face\s*\{[^}]*\}', save, css,
        flags=re.IGNORECASE | re.DOTALL)

    def replace_in_value(m):
        value = m.group(1)
        new_value = value
        for alias, actual in alias_map.items():
            esc = re.escape(alias)
            # 따옴표 있는 케이스
            new_value = re.sub(
                r'(["\'])' + esc + r'\1', f'"{actual}"', new_value)
            # 따옴표 없는 케이스 (단어 경계로 분리)
            new_value = re.sub(
                r'(?<![\w"\'-])' + esc + r'(?![\w-])',
                f'"{actual}"', new_value)
        if new_value != value:
            return 'font-family:' + new_value
        return m.group(0)

    protected = re.sub(
        r'font-family\s*:\s*([^;}]+)', replace_in_value,
        protected, flags=re.IGNORECASE)

    for i, b in enumerate(blocks):
        protected = protected.replace(f'__AFF{i}__', b)
    return protected


# ── 페이지 리스트 제거 ─────────────────────────────────────────────────────────

def _strip_page_lists(contents):
    """NCX의 <pageList>와 EPUB3 nav의 <nav epub:type="page-list"> 제거.

    KFX 변환 후 킨들이 EPUB 페이지 데이터를 우선해 KFX 페이지 추정을 무시하는
    문제를 해결한다.
    """
    modified = False

    for name in list(contents.keys()):
        data, info = contents[name]
        lower = name.lower()

        if lower.endswith('.ncx'):
            try:
                text = data.decode('utf-8')
            except UnicodeDecodeError:
                text = data.decode('latin-1')

            new_text = re.sub(
                r'<pageList\b[^>]*>.*?</pageList\s*>',
                '',
                text,
                flags=re.DOTALL | re.IGNORECASE,
            )
            if new_text != text:
                contents[name] = (new_text.encode('utf-8'), info)
                modified = True

        elif lower.endswith(('.xhtml', '.html', '.htm')):
            try:
                text = data.decode('utf-8')
            except UnicodeDecodeError:
                continue

            # EPUB3 nav document의 page-list 섹션 제거
            new_text = re.sub(
                r'<nav\b[^>]*epub:type=["\']page-list["\'][^>]*>.*?</nav\s*>',
                '',
                text,
                flags=re.DOTALL | re.IGNORECASE,
            )
            if new_text != text:
                contents[name] = (new_text.encode('utf-8'), info)
                modified = True

    return modified


# ── CSS 처리 ───────────────────────────────────────────────────────────────────

def _inject_korean(css, font_name):
    # @font-face 블록 보호 + 정의된 폰트 family 이름 수집
    font_face_blocks = []
    embedded_names   = set()

    def save_block(m):
        block = m.group(0)
        font_face_blocks.append(block)
        # @font-face 안의 font-family 값(따옴표 포함/제외 모두) 수집
        for ff in re.findall(
                r'font-family\s*:\s*([^;}]+)', block, re.IGNORECASE):
            for name in re.findall(r'"([^"]+)"|\'([^\']+)\'|([^,\s][^,]*)', ff):
                n = next((x for x in name if x), '').strip().strip('"\'')
                if n:
                    embedded_names.add(n)
        return f'__FF{len(font_face_blocks) - 1}__'

    protected = re.sub(
        r'@font-face\s*\{[^}]*\}',
        save_block,
        css,
        flags=re.IGNORECASE | re.DOTALL,
    )

    protected = _rewrite_families(protected, font_name, embedded_names)

    # font-family 선언 유무에 따라 폴백 규칙 추가
    _BROAD = (
        'body, p, div, h1, h2, h3, h4, h5, h6, '
        'li, blockquote, td, th, span'
    )
    fallback_chain = f'"{font_name}", sans-serif'
    has_any = bool(re.search(r'font-family\s*:', protected, re.IGNORECASE))
    if not has_any:
        protected += f'\n{_BROAD} {{ font-family: {fallback_chain}; }}\n'
    elif not re.search(r'body\s*\{[^}]*font-family', protected, re.IGNORECASE | re.DOTALL):
        protected += f'\nbody {{ font-family: {fallback_chain}; }}\n'

    for idx, block in enumerate(font_face_blocks):
        protected = protected.replace(f'__FF{idx}__', block)

    return protected


GENERIC_RE = r'(?:serif|sans-serif|monospace|cursive|fantasy|system-ui)'


def _rewrite_families(css, font_name, embedded_names):
    """font-family 첫 폰트가 embedded 면 사용자 폰트를 폴백으로 추가,
    embedded 가 아니면 사용자 폰트로 직접 교체 (KFX 가 폴백 체인을
    무시하는 케이스 대응)."""
    user = f'"{font_name}"'

    def replacer(m):
        value = m.group(1)
        if user in value:
            return m.group(0)

        raw = value.rstrip()
        has_semi = raw.endswith(';')
        core = raw.rstrip(';').rstrip()

        # 첫 폰트 이름 추출
        first_match = re.match(r'\s*(?:"([^"]+)"|\'([^\']+)\'|([^,\s][^,]*))', core)
        first = ''
        if first_match:
            first = next((x for x in first_match.groups() if x), '').strip().strip('"\'')

        if first in embedded_names:
            # 임베드 폰트는 유지, 폴백만 추가
            new_core = re.sub(
                r'(,\s*)(' + GENERIC_RE + r')(\s*)$',
                f', {user}, \\2\\3', core, flags=re.IGNORECASE,
            )
            if new_core == core:
                new_core = core + ', ' + user
        else:
            # 임베드 안 된 폰트 → 사용자 폰트로 교체
            new_core = user

        return 'font-family: ' + new_core + (';' if has_semi else '')

    return re.sub(
        r'font-family\s*:\s*([^;}]+;?)',
        replacer,
        css,
        flags=re.IGNORECASE,
    )


# ── EPUB 재패킹 ────────────────────────────────────────────────────────────────

def _write_epub(contents, output_path):
    with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED) as zout:
        if 'mimetype' in contents:
            data, _ = contents['mimetype']
            info = zipfile.ZipInfo('mimetype')
            info.compress_type = zipfile.ZIP_STORED
            zout.writestr(info, data)

        for name, (data, orig) in contents.items():
            if name == 'mimetype':
                continue
            new_info = zipfile.ZipInfo(name)
            new_info.date_time = orig.date_time
            new_info.compress_type = zipfile.ZIP_DEFLATED
            zout.writestr(new_info, data)
