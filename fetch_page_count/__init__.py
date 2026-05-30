from calibre.customize import InterfaceActionBase


class FetchPageCountPlugin(InterfaceActionBase):
    name                    = 'Fetch Page Count'
    description             = '선택 도서의 페이지수를 알라딘 / Google Books에서 가져와 pages 컬럼에 저장'
    supported_platforms     = ['windows', 'osx', 'linux']
    author                  = 'Custom'
    version                 = (1, 0, 0)
    minimum_calibre_version = (5, 0, 0)
    actual_plugin           = 'calibre_plugins.fetch_page_count.action:FetchPageCountAction'

    def customization_help(self, gui=False):
        return (
            '알라딘 TTB API 키 (선택사항, 없어도 스크래핑으로 동작).\n'
            '발급: https://www.aladin.co.kr/ttb/wbloglist.aspx\n'
            '형식: ttbXXXXXXXXXXXX\n\n'
            'pages 외 다른 컬럼 이름을 쓰려면 키 뒤에 쉼표로 구분해 추가:\n'
            '  ttbXXXX,column=mycolumn'
        )
