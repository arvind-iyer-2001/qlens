from qlens.splitter import normalise_backslash, split_statements, strip_comment


def texts(src):
    return [(s.text, s.line, s.end_line) for s in split_statements(src)]


def test_basic_and_continuation():
    src = "a:1\nf:{[x]\n  x+1\n }\nb:2\n"
    assert texts(src) == [("a:1", 1, 1), ("f:{[x]\n  x+1\n }", 2, 4), ("b:2", 5, 5)]


def test_comments():
    src = "/ header\na:1 / trailing\n  / indented comment\nb:\"x / y\"\n"
    assert texts(src) == [("a:1", 2, 2), ('b:"x / y"', 4, 4)]


def test_slash_in_symbol_and_path_not_comment():
    assert strip_comment("a:`:data/x.csv") == "a:`:data/x.csv"
    assert strip_comment('a:"q\\"/ z" / c') == 'a:"q\\"/ z"'


def test_block_comment():
    src = "a:1\n/\nignored:2\nmore\n\\\nb:3\n"
    assert texts(src) == [("a:1", 1, 1), ("b:3", 6, 6)]


def test_lone_backslash_ends_script():
    assert texts("a:1\n\\\nb:2\n") == [("a:1", 1, 1)]


def test_double_backslash_exits():
    assert texts("a:1\n\\\\\nb:2\n") == [("a:1", 1, 1)]


def test_backslash_commands_become_system():
    src = "\\l lib/f.q\n\\d .gw\n\\w\n\\d .\n"
    assert [t for t, _, _ in texts(src)] == [
        'system "l lib/f.q"',
        'system "d .gw"',
        'system "w"',
        'system "d ."',
    ]


def test_normalise_escapes():
    assert normalise_backslash('\\l a"b.q') == 'system "l a\\"b.q"'
    assert normalise_backslash("a:1") == "a:1"
    assert normalise_backslash("\\") == "\\"


def test_backslash_command_trailing_comment():
    assert texts("\\d .ns / switch\n") == [('system "d .ns"', 1, 1)]


def test_blank_lines_and_whitespace_only():
    assert texts("\n  \na:1\n\n  \nb:2\n") == [("a:1", 3, 3), ("b:2", 6, 6)]


def test_crlf():
    assert texts("a:1\r\nb:2\r\n") == [("a:1", 1, 1), ("b:2", 2, 2)]
