"""
Custom pagination classes for the 254 Capital API.
"""

from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from collections import OrderedDict


class StandardPagination(PageNumberPagination):
    """
    Standard pagination class used across the API.

    Supports:
    - Default page size of 20 items
    - Custom page size via ?page_size= query parameter (max 100)
    - Page navigation via ?page= query parameter

    Response format:
    {
        "count": <total_items>,
        "next": <next_page_url>,
        "previous": <previous_page_url>,
        "page": <current_page>,
        "total_pages": <total_pages>,
        "results": [...]
    }
    """
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100
    page_query_param = 'page'

    def get_paginated_response(self, data):
        """
        Return a paginated style `Response` object with additional metadata.
        """
        return Response(OrderedDict([
            ('count', self.page.paginator.count),
            ('next', self.get_next_link()),
            ('previous', self.get_previous_link()),
            ('page', self.page.number),
            ('total_pages', self.page.paginator.num_pages),
            ('results', data)
        ]))


class LargePagination(PageNumberPagination):
    """
    Pagination class for larger datasets (e.g., exports, reports).
    Default page size of 50 items.
    """
    page_size = 50
    page_size_query_param = 'page_size'
    max_page_size = 200
    page_query_param = 'page'

    def get_paginated_response(self, data):
        return Response(OrderedDict([
            ('count', self.page.paginator.count),
            ('next', self.get_next_link()),
            ('previous', self.get_previous_link()),
            ('page', self.page.number),
            ('total_pages', self.page.paginator.num_pages),
            ('results', data)
        ]))
