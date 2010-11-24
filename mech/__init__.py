# This file intentionally left STUPID SETUPTOOLS!
try:
    from pkg_resources import declare_namespace as d
    d('mech')
except ImportError:
    import pkgutil
    __path__ = pkgutil.extend_path(__path__, __name__)
