
from distutils.core import setup

setup(
    # Package Metadata
    name         = 'fusion',
    description  = 'SWF creator/parse library',
    version      = '0.5',
    author       = 'Jasper St. Pierre',
    author_email = 'jstpierre@mecheye.net',
    url          = 'https://github.com/magcius/fusion',
    license      = 'MPL 1.1',
    packages     = ['fusion', 'fusion.bitstream',
                    'fusion.swf', 'fusion.avm2'],
    package_data = {'fusion.avm2': ['playerglobal.pickle']},
    scripts      = ['bin/mf-swfdump'],
)
