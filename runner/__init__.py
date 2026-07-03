"""The skill-pack runner: turns a pack.yaml into PASS / prescribed fix.

Parts (see the eng plan "Locked architecture"):
    matcher.py  -- pure PASS/FAIL decision for one check (the deterministic core)
    verify.py   -- (next) reads a pack, runs each step's check, escape-hatch loop
"""
