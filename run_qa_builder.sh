#!/bin/bash
cd /tmp/m3-jeg309
python3 pipelines/build_trade_qa_card.py
echo "exit=$?"