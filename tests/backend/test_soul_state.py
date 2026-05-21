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

    # expression_desire=5.0 → mild high instruction
    state.expression_desire = 5.0
    prompt = format_soul_for_prompt(state)
    assert "表达欲稍强" in prompt

    # expression_desire=10.0 → strong high instruction
    state.expression_desire = 10.0
    prompt = format_soul_for_prompt(state)
    assert "表达欲强" in prompt

    # recall_depth=-2.0 → mild low instruction
    state.recall_depth = -2.0
    prompt = format_soul_for_prompt(state)
    assert "专注当下话题" in prompt

    # recall_depth=-10.0 → strong low instruction
    state.recall_depth = -10.0
    prompt = format_soul_for_prompt(state)
    assert "避免主动引入历史经历" in prompt

def test_from_config():
    from core.social.soul_state import from_config
    from core.config import SoulConfig
    cfg = SoulConfig(recall_depth_init=1.0, creativity_init=2.0)
    state = from_config(cfg)
    assert state.recall_depth == 1.0
    assert state.creativity == 2.0
