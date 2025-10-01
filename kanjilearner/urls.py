from django.urls import path

from . import views

urlpatterns = [
    path("api/csrf/", views.get_csrf_token),
    path("api/login/", views.login_view),
    path("api/lessons/", views.get_lessons, name="get_lessons"),
    path("api/reviews/", views.get_reviews, name="get_reviews"),
    path("api/mistakes/", views.get_recent_mistakes, name="get_recent_mistakes"),
    path("api/review_forecast/", views.get_review_forecast, name="get_review_forecast"),
    path('api/result/success/', views.result_success, name='result_success'),
    path('api/result/failure/', views.result_failure, name='result_failure'),
    path("api/search", views.search, name="search"),
    path("api/dictionary/<int:pk>/", views.entry_detail, name="entry_detail"),
    path("api/planned/", views.get_planned, name="get_planned"),
    path("api/plan_add/", views.plan_add, name="plan_add"),
    path("api/whoami/", views.whoami, name="whoami"),
    path("api/logout/", views.logout_view, name="api_logout"),
    path("api/register/", views.register_view, name="api_register"),
    path("api/verify-email/<int:uid>/<str:token>/", views.verify_email, name="api_verify_email"),
    path("api/delete_account/", views.delete_account, name="delete_account"),
]