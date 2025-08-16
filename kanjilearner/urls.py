from django.urls import path

from . import views

urlpatterns = [
    path("api/lessons/", views.get_lessons, name="get_lessons"),
    path("api/reviews/", views.get_reviews, name="get_reviews"),
    path("api/mistakes/", views.get_recent_mistakes, name="get_recent_mistakes"),
]