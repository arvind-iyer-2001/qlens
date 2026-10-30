from qlens.discovery import discover, looks_like_q


def test_looks_like_q_ok():
    assert looks_like_q(b"f:{x+1}\n.ns.g:{x}\n\\d .a\nt:([] a:1 2)\n")[0]


def test_rejects_binary_empty_numeric_prose():
    assert not looks_like_q(b"\x00\x01\x02abc")[0]
    assert not looks_like_q(b"  \n")[0]
    assert not looks_like_q(b"\n".join(b"%d" % i for i in range(100)))[0]
    assert not looks_like_q(
        b"2020-01-01 SELECT * FROM x\n2020-01-02 error happened here\nthis is prose\n"
    )[0]


def test_rejects_long_lines():
    assert not looks_like_q(b"a:" + b"1 " * 20000 + b"\n")[0]


def test_comments_only_ok():
    assert looks_like_q(b"/ just a comment\n")[0]


def test_discover(tmp_path):
    (tmp_path / "a.q").write_text("f:{x}\n")
    (tmp_path / "b.k").write_text("f:{x}\n")
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "c.q").write_text("f:{x}\n")
    (tmp_path / "out").mkdir()
    (tmp_path / "out" / "d.q").write_text("f:{x}\n")
    (tmp_path / "big.q").write_bytes(b"a:1\n" * 400_000)
    (tmp_path / "log.q").write_text("hello world\nthis is a log\nnot q at all\n")
    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / "e.q").write_text("g:{y}\n")
    d = discover(tmp_path, out_dir=tmp_path / "out")
    assert [p.name for p in d.files] == ["a.q", "e.q"]
    reasons = {p.name: r for p, r in d.skipped}
    assert "too large" in reasons["big.q"]
    assert "look like q" in reasons["log.q"]
