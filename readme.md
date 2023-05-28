Tradingview alerts.

Open Long (Buy)

{
  "ticker": "{{ticker}}",
  "strategy": {
    "order": {
      "action": "LongBuy"
    }
  }
}


Close Long (Sell)

{
  "ticker": "{{ticker}}",
  "strategy": {
    "order": {
      "action": "LongExit"
    }
  }
}


Open Short (Sell)

{
  "ticker": "{{ticker}}",
  "strategy": {
    "order": {
      "action": "ShortSell"
    }
  }
}


Close Short (Buy)

{
  "ticker": "{{ticker}}",
  "strategy": {
    "order": {
      "action": "ShortExit"
    }
  }
}