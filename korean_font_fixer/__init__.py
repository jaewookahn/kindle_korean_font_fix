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

        css_names = [n for n in contents if n.lower().endswith('.css')]
        if not css_names:
            return None

        modified = False
        for name in css_names:
            data, info = contents[name]
            try:
                css = data.decode('utf-8')
            except UnicodeDecodeError:
                css = data.decode('latin-1')

            if 'KoreanFallback' in css:
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


# ── CSS 처리 ───────────────────────────────────────────────────────────────────

def _inject_korean(css, font_name):
    font_face = (
        '/* Korean Font Fixer */\n'
        '@font-face {\n'
        '    font-family: "KoreanFallback";\n'
        f'    src: local("{font_name}");\n'
        f'    unicode-range: {KOREAN_UNICODE_RANGE};\n'
        '}\n\n'
    )

    # @font-face 블록 안의 font-family는 폰트 이름 정의이므로 보호
    font_face_blocks = []

    def save_block(m):
        font_face_blocks.append(m.group(0))
        return f'__FF{len(font_face_blocks) - 1}__'

    protected = re.sub(
        r'@font-face\s*\{[^}]*\}',
        save_block,
        css,
        flags=re.IGNORECASE | re.DOTALL,
    )

    protected = _add_fallback_to_families(protected, font_name)

    # font-family 선언 유무에 따라 폴백 규칙 추가
    _BROAD = (
        'body, p, div, h1, h2, h3, h4, h5, h6, '
        'li, blockquote, td, th, span'
    )
    has_any = bool(re.search(r'font-family\s*:', protected, re.IGNORECASE))
    if not has_any:
        # CSS에 font-family가 전혀 없음 → 주요 요소 전체 커버
        protected += f'\n{_BROAD} {{ font-family: "KoreanFallback", sans-serif; }}\n'
    elif not re.search(r'body\s*\{[^}]*font-family', protected, re.IGNORECASE | re.DOTALL):
        # body에만 없는 경우
        protected += '\nbody { font-family: "KoreanFallback", sans-serif; }\n'

    # 보호했던 @font-face 복원
    for idx, block in enumerate(font_face_blocks):
        protected = protected.replace(f'__FF{idx}__', block)

    return font_face + protected


GENERIC_RE = r'(?:serif|sans-serif|monospace|cursive|fantasy|system-ui)'


def _add_fallback_to_families(css, font_name):
    def replacer(m):
        value = m.group(1)
        if 'KoreanFallback' in value:
            return m.group(0)

        raw = value.rstrip()
        has_semi = raw.endswith(';')
        core = raw.rstrip(';').rstrip()

        # generic family 앞에 삽입
        new_core = re.sub(
            r'(,\s*)(' + GENERIC_RE + r')(\s*)$',
            r', "KoreanFallback", \2\3',
            core,
            flags=re.IGNORECASE,
        )

        if new_core == core:
            # generic 없으면 끝에 붙이기
            new_core = core + ', "KoreanFallback"'

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
