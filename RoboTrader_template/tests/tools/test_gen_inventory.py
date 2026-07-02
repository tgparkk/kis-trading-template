"""gen_inventory 매처 — from-import alias가 서브모듈 참조로 인식되는지."""
import textwrap


def test_from_import_module_alias_detected(tmp_path):
    from tools.gen_inventory import imports_of_source
    src = textwrap.dedent('''
        from scripts.exit_multiverse import run, walkforward
        from scripts.discovery.rules import MeanReversionMA20Rule
        import scripts.strategy_gate
    ''')
    mods = imports_of_source(src)
    assert "scripts.exit_multiverse.run" in mods          # alias 결합 (신규)
    assert "scripts.exit_multiverse.walkforward" in mods  # alias 결합 (신규)
    assert "scripts.exit_multiverse" in mods              # 기존 동작 유지
    assert "scripts.discovery.rules" in mods              # 기존 동작 유지
    assert "scripts.strategy_gate" in mods                # 기존 동작 유지
