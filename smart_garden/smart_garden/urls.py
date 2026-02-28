"""
URL configuration for smart_garden project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/4.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import include, path
from rest_framework.permissions import AllowAny
from rest_framework.schemas import get_schema_view

from plants.views import home

schema_view = get_schema_view(
    title='Smart Garden Manager API',
    description='Open API schema for Smart Garden Manager endpoints.',
    version='1.0.0',
    permission_classes=[AllowAny],
)

urlpatterns = [
    path('', home, name='home'),
    path('', include('plants.urls')),
    path('api/schema/', schema_view, name='openapi-schema'),
    path('admin/', admin.site.urls),
]
