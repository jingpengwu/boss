"""boss URL Configuration

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/1.8/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  url(r'^$', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  url(r'^$', Home.as_view(), name='home')
Including another URLconf
    1. Add an import:  from blog import urls as blog_urls
    2. Add a URL to urlpatterns:  url(r'^blog/', include(blog_urls))
"""
from django.conf.urls import include, url
from django.contrib import admin
from django.conf.urls import patterns

#TODO: Think about versioning better. Think major version in url. minor in header?
#TODO: Update priya's urls to have a version
urlpatterns = [
    url(r'^admin/', include(admin.site.urls)),
    url(r'^v0.1/cutout/', include('bossspatialdb.urls')),
    url(r'^docs/', include('rest_framework_swagger.urls')),
    url(r'^', include('bosscore.urls')),
]