from .base import SystemController

class GenericController(SystemController):
    system='Generic'
    def _op_theme(self): return {'theme':'dark','source':'fallback','known':False}

    def _op_app_launch(self,app):
        raise NotImplementedError('App launch is unavailable on this unrecognized OS')
    def _op_installed_apps(self):
        raise NotImplementedError('App inventory is unavailable on this unrecognized OS')
