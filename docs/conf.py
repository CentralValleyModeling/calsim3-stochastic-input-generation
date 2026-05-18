# Configuration file for the Sphinx documentation builder.
# https://www.sphinx-doc.org/en/master/usage/configuration.html

import os
import sys
from pathlib import Path

# Make the project importable for autodoc (optional, expand as needed)
sys.path.insert(0, str(Path(__file__).parent.parent))

# -- Project information -------------------------------------------------------
project   = 'CalSim Stochastic Hydroclimate'
copyright = '2026, California Department of Water Resources'
author    = 'Wyatt Arnold, Melika Mani, Mehrdad Bastani, Karandev Singh'
release   = '1.0'

# -- Extensions ----------------------------------------------------------------
extensions = [
    'myst_parser',               # Parse .md files with MyST
    'sphinx.ext.autodoc',        # Auto-generate API docs from docstrings
    'sphinx.ext.napoleon',       # Google / NumPy docstring styles
    'sphinx.ext.viewcode',       # Link to source code
    'sphinx.ext.intersphinx',    # Cross-reference Python docs
    'sphinx_copybutton',         # Copy button on code blocks
    'sphinxcontrib.mermaid',     # Mermaid diagram rendering
    'sphinx_design',             # Tabs, cards, grids
]

# MyST parser options
myst_enable_extensions = [
    'colon_fence',      # ::: fenced directives
    'deflist',          # definition lists
    'tasklist',         # - [x] task items
    'fieldlist',        # :key: value fields
    'dollarmath',       # $...$ and $$...$$ math
]
myst_heading_anchors = 3

# Accept both .rst and .md source files
source_suffix = {
    '.rst': 'restructuredtext',
    '.md':  'markdown',
}

# -- Build options -------------------------------------------------------------
templates_path   = ['_templates']
exclude_patterns = ['_build', 'Thumbs.db', '.DS_Store', 'source/MIGRATION.md', 'source/figures/README.md', 'manifests']

# -- HTML output ---------------------------------------------------------------
html_theme       = 'sphinx_book_theme'
html_title       = 'CalSim Stochastic Hydroclimate'
html_static_path = ['_static']
html_css_files   = ['custom.css']

html_theme_options = {
    'show_toc_level': 3,
    'navigation_with_keys': True,
}

# -- Mermaid -------------------------------------------------------------------
mermaid_init_config = {
    "startOnLoad": False,
    "theme": "base",
    "themeVariables": {
        "fontSize": "16px"
    },
    "flowchart": {
        "useMaxWidth": True,
        "htmlLabels": True
    }
}

# -- Intersphinx ---------------------------------------------------------------
intersphinx_mapping = {
    'python': ('https://docs.python.org/3', None),
    'pandas': ('https://pandas.pydata.org/docs/', None),
    'numpy':  ('https://numpy.org/doc/stable/', None),
}
