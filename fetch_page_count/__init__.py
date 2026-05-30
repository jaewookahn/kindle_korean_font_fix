from calibre.customize import InterfaceActionBase


class FetchPageCountPlugin(InterfaceActionBase):
    name                    = 'Fetch Page Count'
    description             = '선택 도서의 페이지수를 알라딘 / Google Books에서 가져와 pages 컬럼에 저장'
    supported_platforms     = ['windows', 'osx', 'linux']
    author                  = 'Custom'
    version                 = (1, 1, 0)
    minimum_calibre_version = (5, 0, 0)
    actual_plugin           = 'calibre_plugins.fetch_page_count.action:FetchPageCountAction'
