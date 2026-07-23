"""Pygments lexer for WRESL+ (WRESL) source, wired in as a Sphinx extension.

Vendored from the ``wresl-pygment`` package (MIT, Zachary Roy,
zachary.roy@water.ca.gov) so the docs build has no external dependency.
Register any ```wresl fenced code block for syntax highlighting.
"""

import re

from pygments.lexer import RegexLexer, words
from pygments.token import (
    Comment, Keyword, Name, Number, Operator,
    Punctuation, String, Text, Whitespace,
)


class WreslLexer(RegexLexer):
    name = 'WRESL'
    aliases = ['wresl']
    filenames = ['*.wresl']
    flags = re.IGNORECASE | re.MULTILINE  # grammar uses caseInsensitive = true

    # --- Token groups derived from the grammar ---

    # Keywords - top-level object types
    KEYWORDS_OBJECT = (
        'model', 'sequence', 'order', 'include', 'group',
        'initial', 'goal', 'objective', 'weight', 'define',
        'dvar', 'svar',
    )

    # Keywords - instructions / directives
    KEYWORDS_INSTRUCTION = (
        'value', 'external', 'timeseries', 'timestep', 'alias',
        'integer', 'std', 'kind', 'units', 'convert', 'nosolver',
        'case', 'condition', 'if', 'elseif', 'else',
        'select', 'given', 'use', 'where', 'from', 'sum',
        'penalty', 'variable', 'linear', 'maximum', 'minimum',
        'never', 'unbounded', 'constrain', 'upper', 'lower',
        'side',
    )

    # Keywords - constants / built-in values
    KEYWORDS_CONSTANT = (
        'local', 'global', 'always', 'daysin', 'month', 'wateryear',
        'jan', 'prevjan', 'feb', 'prevfeb', 'mar', 'prevmar',
        'apr', 'prevapr', 'may', 'prevmay', 'jun', 'prevjun',
        'jul', 'prevjul', 'aug', 'prevaug', 'sep', 'prevsep',
        'oct', 'prevoct', 'nov', 'prevnov', 'dec', 'prevdec',
        '1mon', '1day',
    )

    # Keywords - built-in functions
    KEYWORDS_FUNCTION = (
        'range', 'abs', 'int', 'real', 'exp', 'log', 'log10',
        'sqrt', 'round', 'pow', 'mod', 'min', 'max',
    )

    tokens = {
        'root': [
            # Whitespace
            (r'\s+', Whitespace),

            # Comments: !, //, and /* */
            (r'!.*$', Comment.Single),
            (r'//.*$', Comment.Single),
            (r'/\*', Comment.Multiline, 'block_comment'),

            # Special future-array token: $m
            (r'\$m\b', Name.Builtin),

            # Quoted strings (single and double)
            (r"'[^'\r\n]*'", String),
            (r'"[^"\r\n]*"', String),

            # lhs / rhs side tokens (e.g. lhs, rhs)
            (r'\b[lr]hs\b', Keyword.Type),

            # Logical operators written as words
            (r'\.not\.', Operator.Word),
            (r'\.and\.', Operator.Word),
            (r'\.or\.', Operator.Word),
            (r'\.ne\.', Operator.Word),

            # Built-in functions (before general keywords so min/max match here)
            (words(KEYWORDS_FUNCTION, suffix=r'\b'), Name.Builtin),

            # Object/structure keywords
            (words(KEYWORDS_OBJECT, suffix=r'\b'), Keyword),

            # Instruction keywords
            (words(KEYWORDS_INSTRUCTION, suffix=r'\b'), Keyword.Declaration),

            # Constant keywords (months, always, local, global, etc.)
            (words(KEYWORDS_CONSTANT, suffix=r'\b'), Keyword.Constant),

            # Comparison / math operators
            (r'>=|<=|==|>|<|=', Operator),
            (r'[+\-*/:]', Operator),

            # Punctuation / brackets
            (r'[{}()\[\],]', Punctuation),

            # Numbers: float before int
            (r'\d*\.\d*([eE][+-]?\d+)?', Number.Float),
            (r'\d+', Number.Integer),

            # Identifiers: must start with a letter (OBJECT_NAME: [A-Z][A-Z0-9_]*)
            # case-insensitive flag covers both cases
            (r'[A-Za-z][A-Za-z0-9_]*', Name),

            # Any remaining non-whitespace
            (r'.', Text),
        ],

        'block_comment': [
            (r'[^*/]+', Comment.Multiline),
            (r'\*/', Comment.Multiline, '#pop'),
            (r'[*/]', Comment.Multiline),
        ],
    }


def setup(app):
    """Sphinx extension hook: register the WRESL lexer under the 'wresl' alias."""
    app.add_lexer('wresl', WreslLexer)
    return {
        'version': '0.1.0',
        'parallel_read_safe': True,
        'parallel_write_safe': True,
    }
