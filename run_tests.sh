#!/bin/bash
cd /tmp/m3-jeg309
python3 -m pytest tests/test_trade_qa_card.py -x -q 2>&1
echo "EXIT=$?"