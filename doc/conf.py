# -*- coding: utf-8 -*-

import sys, os
from mech import fusion

extensions = ['sphinx.ext.autodoc', 'sphinx.ext.intersphinx', 'sphinx.ext.todo', 'sphinx.ext.coverage', 'sphinx.ext.ifconfig']
templates_path = ['_templates']
source_suffix = '.rst'
master_doc = 'contents'

# General information about the project.
project = u'Fusion'
copyright = u'2012, Jasper St. Pierre'
version = release = fusion.__released__

today_fmt = '%B %d, %Y'
unused_docs = []
exclude_trees = ['_build']

html_theme = 'fusion'
html_theme_path = ['_themes']

# A shorter title for the navigation bar.  Default is the same as html_title.
html_short_title = "Fusion docs"
html_static_path = ['_static']
html_index = "index.html"
html_additional_pages = dict(index="index.html")
html_use_opensearch = 'http://fusion.mecheye.net'

htmlhelp_basename = 'FusionDoc'

autodoc_member_order = 'groupwise'
todo_include_todos = True

latex_documents = [
  ('contents', 'fusion.tex', u'Fusion Documentation',
   'Jasper St. Pierre', 'manual', 1),
]

intersphinx_mapping = {'http://docs.python.org/': None}
