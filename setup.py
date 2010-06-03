
from setuptools import setup, find_packages

from mech import fusion

CONFIG = dict(
    # Package Metadata
    name =              'mecheye-fusion',
    description =       'SWF creator/parse library',
    version =           fusion.__released__,
    author =            fusion.__author__,
    author_email =      fusion.__email__,
    url =               fusion.__url__,
    license =           fusion.__license__,
    keywords =          'swf avm1 avm2 tamarin mecheye mech fusion bitstream',

    # Dependencies
    install_requires = ['zope.interface',
                        'zope.component',
                        'distribute'],

    # Installation info
    packages = find_packages(),
    entry_points = dict(
        console_scripts=['mf-swfdump = mech.fusion.swf.swfdump:main',
                         'mf-extractabc = mech.fusion.avm2.extractabc:main',
                         'mf-librarygen = mech.fusion.avm2.library:librarygen_main',]),

    # Right now, playerglobal libraries.
    package_data = {'mech.fusion.avm2': ['playerglobal.pickle']},
)

setup(**CONFIG)
