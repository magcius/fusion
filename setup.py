

from distutils.core import setup

setup(name='mecheye-fusion',
      version='0.1.8',
      description='SWF export/parse library',
      author='JP "magcius" St. Pierre, Josh Lory, Jon "Jonanin" Morton',
      author_email='jstpierre@mecheye.net',
      url='http://github.com/mecheye/mecheye-fusion',
      scripts=['bin/mf-swfdump', 'bin/mf-librarygen'],
      packages=['mech','mech.fusion','mech.fusion.swf',
                'mech.fusion.avm1','mech.fusion.avm2',
                'mech.fusion.bitstream'])
