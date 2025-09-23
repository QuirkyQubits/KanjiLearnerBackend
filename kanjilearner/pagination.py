from rest_framework.pagination import PageNumberPagination


class SearchPagination(PageNumberPagination):
    page_size = 100  # default page size
    page_size_query_param = "page_size"  # allow ?page_size=50
    max_page_size = 200