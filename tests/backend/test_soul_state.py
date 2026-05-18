import pytest
import math
from core.social.soul_state import SoulState, apply_tanh_elastic, apply_decay, format_soul_for_prompt

def test_apply_tanh_elastic():
    # Large positive delta should be capped near 20
    val = apply_tanh_elastic(0, 100)
    assert 19.0 < val <= 20.0
    
    # Large negative delta should be capped near -20
    val = apply_tanh_elastic(0, -100)
    assert -20.0 <= val < -19.0
    
    # Small delta should be roughly linear
    val = apply_tanh_elastic(0, 1)
    assert 0 < val < 1.0

def test_apply_decay():
    state = SoulState(recall_depth=10.0, creativity=-5.0)
    decayed = apply_decay(state, 0.1)
    assert decayed.recall_depth == 9.0
    assert decayed.creativity == -4.5
    assert decayed.impression_depth == 0.0

def test_format_soul_for_prompt():
    state = SoulState()
    assert format_soul_for_prompt(state) == ""
    
    state.expression_desire = 5.0
    prompt = format_soul_for_prompt(state)
    assert "表达欲 +5.0/20" in prompt
    assert "偏高" in prompt
    
    state.recall_depth = -2.0
    prompt = format_soul_for_prompt(state)
    assert "记忆检索驱动 -2.0/20" in prompt
    assert "偏低" in prompt

def test_from_config():
    from core.social.soul_state import from_config
    from core.config import SoulConfig
    cfg = SoulConfig(recall_depth_init=1.0, creativity_init=2.0)
    state = from_config(cfg)
    assert state.recall_depth == 1.0
    assert state.creativity == 2.0
