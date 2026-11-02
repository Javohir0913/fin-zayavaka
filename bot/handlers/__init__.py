from . import admin, analytics, common, create, view

# Tartib muhim: common (start/cancel) birinchi, keyin menyu tugmalari bo'yicha routerlar
routers = [common.router, admin.router, analytics.router, create.router, view.router]
