import pandas as pd
from backend.core.data import build_features, label_crash, synth_ohlcv

def test_build_features_and_label():
    df = synth_ohlcv('ETH/USDT','1d',600)
    feats = build_features(df)
    assert set(['ret_1d','vol_20','rsi_15']).issubset(set(feats.columns))
    y = label_crash(feats['close'], horizon=10, crash_drop=0.2)
    assert y.isna().sum() > 0
