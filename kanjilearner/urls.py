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
]