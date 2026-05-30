from calibre.utils.config import JSONConfig

# Qt 임포트 없음 — 이 파일은 플러그인 로드 시 안전하게 임포트되어야 함
prefs = JSONConfig('plugins/fetch_page_count')
prefs.defaults['ttb_key']      = ''
prefs.defaults['pages_column'] = 'pages'
