name: Backtest

on:
  workflow_dispatch:

permissions:
  contents: read

jobs:
  backtest:
    runs-on: ubuntu-latest
    timeout-minutes: 60
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
          cache: pip

      - run: pip install -r requirements.txt

      - name: Backtest calistir
        run: python backtest.py
        env:
          TELEGRAM_TOKEN: ${{ secrets.TELEGRAM_TOKEN }}
          TELEGRAM_CHAT_ID: ${{ secrets.TELEGRAM_CHAT_ID }}

      - name: Sonuclari sakla
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: backtest-sonuclari
          path: |
            backtest_islemler.csv
            backtest_rapor.md
