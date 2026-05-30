from calibre.utils.config import JSONConfig

try:
    from qt.core import (QDialog, QVBoxLayout, QFormLayout,
                         QLineEdit, QLabel, QDialogButtonBox)
except ImportError:
    from PyQt5.Qt import (QDialog, QVBoxLayout, QFormLayout,
                          QLineEdit, QLabel, QDialogButtonBox)

prefs = JSONConfig('plugins/fetch_page_count')
prefs.defaults['ttb_key']      = ''
prefs.defaults['pages_column'] = 'pages'


class ConfigDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle('페이지수 가져오기 — 설정')
        self.setMinimumWidth(440)

        layout = QVBoxLayout(self)
        form   = QFormLayout()

        self.ttb_key = QLineEdit(prefs['ttb_key'])
        self.ttb_key.setPlaceholderText('ttbXXXXXXXXXXXX  (없으면 스크래핑만 사용)')
        form.addRow('알라딘 TTB API 키:', self.ttb_key)

        self.col = QLineEdit(prefs['pages_column'])
        self.col.setPlaceholderText('pages')
        form.addRow('컬럼 이름 (#없이):', self.col)

        layout.addLayout(form)

        note = QLabel('<a href="https://www.aladin.co.kr/ttb/wbloglist.aspx">'
                      'TTB 키 발급 (무료)</a>')
        note.setOpenExternalLinks(True)
        layout.addWidget(note)

        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        layout.addWidget(bb)

    def commit(self):
        prefs['ttb_key']      = self.ttb_key.text().strip()
        prefs['pages_column'] = self.col.text().strip() or 'pages'
