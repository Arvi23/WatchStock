import pytest

from watchstock.symbols import tradingview_symbol


@pytest.mark.parametrize(
    ("yahoo", "tv"),
    [
        ("TLV.RO", "BVB:TLV"),
        ("snp.ro", "BVB:SNP"),
        ("SAP.DE", "XETR:SAP"),
        ("VOD.L", "LSE:VOD"),
        ("0700.HK", "HKEX:700"),
        ("MSFT", "MSFT"),
        ("BRK-B", "BRK.B"),
        ("FOO.XX", "FOO.XX"),
    ],
)
def test_tradingview_symbol(yahoo, tv):
    assert tradingview_symbol(yahoo) == tv
